"""Fixed, tested tools the analyst calls instead of doing arithmetic itself.

Every number the analyst sees comes from one of these functions or from the Python
sandbox, so the model never has to produce a statistic from memory. The tools are
descriptive: they return counts, medians and rank correlations with n, and never a
p-value or a verdict. They are leads for the gateway to test, not findings.

Each call is recorded in the exploration ledger with the number of hypotheses it
examined, so the run can say how much was screened versus how much was tested.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pramana.analysis.config import HypothesesConfig
from pramana.analysis.hypotheses.trend import _as_ordered_numeric
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile
from pramana.analysis.workspace.config import WorkspaceConfig
from pramana.analysis.workspace.ledger import ExplorationLedger
from pramana.analysis.workspace.sandbox import run_python
from pramana.common.logging import get_logger

MAX_GROUPS = 12
MAX_LEVELS_SHOWN = 10
MAX_TREND_ROWS = 3000
MAX_MISSINGNESS_COLUMNS = 60
MAX_SCAN_TOP = 25


class ToolResult(BaseModel):
    """What a tool call returned. A failure is a result, never an exception."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    entry_id: str
    output: dict[str, Any] | None = None
    error: str | None = None
    examined: int = 0


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DescribeArgs(_Args):
    column: str


class CompareGroupsArgs(_Args):
    value: str
    group: str


class RelateArgs(_Args):
    x: str
    y: str


class TrendArgs(_Args):
    value: str
    order: str


class MissingnessArgs(_Args):
    pass


class OverviewArgs(_Args):
    pass


class ScanPairsArgs(_Args):
    top: int = Field(default=10, ge=1, le=MAX_SCAN_TOP)


class PythonArgs(_Args):
    code: str = Field(min_length=1, max_length=6000)


#: name -> (arguments model, one-line description shown to the model)
TOOL_SPECS: dict[str, tuple[type[_Args], str]] = {
    "describe": (
        DescribeArgs,
        "Summary of one column: counts, missing, numeric sum/mean/spread or top levels.",
    ),
    "overview": (
        OverviewArgs,
        "What this table contains: exact row/column counts and a bounded list of column "
        "names, detected roles and missing counts. Use for a general dataset introduction.",
    ),
    "compare_groups": (
        CompareGroupsArgs,
        "Per-group n, sum, mean, median and quartiles of numeric `value` "
        "across categorical `group`.",
    ),
    "relate": (RelateArgs, "Spearman and Pearson correlation of two numeric columns, with n."),
    "trend": (TrendArgs, "Kendall tau-b of a numeric `value` against a time-like `order` column."),
    "missingness": (MissingnessArgs, "Missing counts for every usable column."),
    "scan_pairs": (
        ScanPairsArgs,
        "Rank all numeric column pairs by absolute Spearman correlation; returns the top ones.",
    ),
    "python": (
        PythonArgs,
        "Run numpy/pandas code on the table (`df`); call emit(value) to return results. "
        "No files, no network, no statistics libraries.",
    ),
}


def _r(value: Any) -> float | None:
    """A finite float rounded for display, or None."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 6) if math.isfinite(number) else None


class Workspace:
    """The analyst's desk: the cleaned table, its schema, the tools and the ledger."""

    def __init__(
        self,
        frame: pd.DataFrame,
        schema: SchemaProfile,
        config: WorkspaceConfig,
        hypotheses: HypothesesConfig,
        ledger: ExplorationLedger | None = None,
    ) -> None:
        self.frame = frame
        self.schema = schema
        self.config = config
        self.hypotheses = hypotheses
        self.ledger = ledger or ExplorationLedger()
        self._tools: dict[str, Callable[[Any], tuple[dict[str, Any], int]]] = {
            "describe": self._describe,
            "overview": self._overview,
            "compare_groups": self._compare_groups,
            "relate": self._relate,
            "trend": self._trend,
            "missingness": self._missingness,
            "scan_pairs": self._scan_pairs,
            "python": self._python,
        }

    # ---- public ----------------------------------------------------------------
    def tool_descriptions(self) -> list[dict[str, Any]]:
        return [
            {"name": name, "does": text, "args": model.model_json_schema()["properties"]}
            for name, (model, text) in TOOL_SPECS.items()
            if name != "python" or self.config.sandbox.enabled
        ]

    @property
    def examined_budget_left(self) -> int:
        return max(0, self.config.agent.max_hypotheses_examined - self.ledger.examined)

    def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        """Run one tool. Unknown tools, bad arguments and failures come back as results."""
        entry_id = self.ledger.next_id()
        started = time.monotonic()
        kind: Literal["python", "tool"] = "python" if name == "python" else "tool"
        examined = 0
        output: dict[str, Any] | None = None
        error: str | None = None
        try:
            if name not in TOOL_SPECS or (name == "python" and not self.config.sandbox.enabled):
                available = ", ".join(item["name"] for item in self.tool_descriptions())
                raise ValueError(f"Unknown tool {name!r}. Tools: {available}.")
            parsed = TOOL_SPECS[name][0].model_validate(args)
            output, examined = self._tools[name](parsed)
        except ValidationError as problem:
            first = problem.errors()[0]
            error = f"Bad arguments for {name}: {first['loc']} {first['msg']}"
        except ValueError as problem:
            error = str(problem)
        except Exception as problem:  # a pandas surprise on odd data is a tool error, not a crash
            get_logger(component="workspace").warning(
                "tool_failed", tool=name, error_type=type(problem).__name__
            )
            error = f"The {name} tool could not handle this data."
        duration = int((time.monotonic() - started) * 1000)
        self.ledger.add(
            entry_id,
            kind=kind,
            name=name,
            args=dict(args) if isinstance(args, dict) else {},
            ok=error is None,
            output=output if error is None else error,
            examined=examined if error is None else 0,
            duration_ms=duration,
        )
        return ToolResult(
            ok=error is None,
            entry_id=entry_id,
            output=output,
            error=error,
            examined=examined if error is None else 0,
        )

    # ---- helpers ---------------------------------------------------------------
    def _column(self, name: str) -> pd.Series:
        if name not in self.frame.columns:
            raise ValueError(f"No column named {name!r}.")
        return self.frame[name]

    def _usable(self, name: str, *roles: ColumnRole) -> None:
        self._column(name)
        profile = self.schema.columns.get(name)
        if profile is None or not profile.usable_for_hypotheses:
            raise ValueError(f"{name!r} is not usable for analysis (see the schema).")
        if roles and profile.role not in roles:
            wanted = " or ".join(role.value for role in roles)
            raise ValueError(f"{name!r} is {profile.role.value}; this needs {wanted}.")

    def _numeric(self, name: str, *roles: ColumnRole) -> pd.Series:
        self._usable(name, *roles)
        return pd.to_numeric(self.frame[name], errors="coerce").replace([np.inf, -np.inf], np.nan)

    def _spend(self, count: int) -> None:
        if count > self.examined_budget_left:
            raise ValueError(
                f"This would examine {count} hypotheses but only {self.examined_budget_left} "
                "remain in the budget. Stop exploring and propose claims."
            )

    # ---- tools -----------------------------------------------------------------
    def _describe(self, args: DescribeArgs) -> tuple[dict[str, Any], int]:
        self._usable(args.column)
        series = self._column(args.column)
        present = series.dropna()
        out: dict[str, Any] = {
            "column": args.column,
            "n": int(len(present)),
            "missing": int(series.isna().sum()),
            "unique": int(present.nunique()),
        }
        if pd.api.types.is_numeric_dtype(series):
            numbers = present.astype(float)
            if len(numbers):
                out.update(
                    sum=_r(numbers.sum()),
                    mean=_r(numbers.mean()),
                    std=_r(numbers.std()),
                    min=_r(numbers.min()),
                    q1=_r(numbers.quantile(0.25)),
                    median=_r(numbers.median()),
                    q3=_r(numbers.quantile(0.75)),
                    max=_r(numbers.max()),
                )
        else:
            counts = present.astype(str).value_counts().head(MAX_LEVELS_SHOWN)
            out["levels"] = [{"label": str(k)[:64], "count": int(v)} for k, v in counts.items()]
        return out, 0

    def _compare_groups(self, args: CompareGroupsArgs) -> tuple[dict[str, Any], int]:
        self._spend(1)
        self._usable(args.group, ColumnRole.CATEGORICAL, ColumnRole.ORDINAL)
        values = self._numeric(args.value, ColumnRole.NUMERIC)
        both = pd.DataFrame({"g": self.frame[args.group].astype("string"), "v": values}).dropna()
        if both.empty:
            raise ValueError("No rows have both columns present.")
        sizes = both["g"].value_counts()
        levels = sorted(sizes.index[:MAX_GROUPS])
        groups = []
        for level in levels:
            v = both.loc[both["g"] == level, "v"]
            groups.append(
                {
                    "group": str(level)[:64],
                    "n": int(len(v)),
                    "sum": _r(v.sum()),
                    "median": _r(v.median()),
                    "q1": _r(v.quantile(0.25)),
                    "q3": _r(v.quantile(0.75)),
                    "mean": _r(v.mean()),
                }
            )
        grand = both["v"].mean()
        total = float(((both["v"] - grand) ** 2).sum())
        between = float(
            sum(len(g) * (g.mean() - grand) ** 2 for _, g in both.groupby("g", observed=True)["v"])
        )
        eta = between / total if total > 0 else None
        return {
            "value": args.value,
            "group": args.group,
            "n": int(len(both)),
            "groups": groups,
            "eta_squared": _r(eta),
            "note": "descriptive only; no significance test",
        }, 1

    def _relate(self, args: RelateArgs) -> tuple[dict[str, Any], int]:
        if args.x == args.y:
            raise ValueError("Pick two different columns.")
        self._spend(1)
        pair = pd.DataFrame(
            {
                "x": self._numeric(args.x, ColumnRole.NUMERIC),
                "y": self._numeric(args.y, ColumnRole.NUMERIC),
            }
        ).dropna()
        if len(pair) < 3 or pair["x"].nunique() < 2 or pair["y"].nunique() < 2:
            raise ValueError("Too few distinct paired values to relate these columns.")
        return {
            "x": args.x,
            "y": args.y,
            "n": int(len(pair)),
            "spearman_rho": _r(pair["x"].corr(pair["y"], method="spearman")),
            "pearson_r": _r(pair["x"].corr(pair["y"], method="pearson")),
            "note": "descriptive only; no significance test",
        }, 1

    def _trend(self, args: TrendArgs) -> tuple[dict[str, Any], int]:
        self._spend(1)
        self._usable(args.order)
        if not self.schema.columns[args.order].is_time_like:
            raise ValueError(f"{args.order!r} is not a time-like column.")
        values = self._numeric(args.value, ColumnRole.NUMERIC)
        order = _as_ordered_numeric(self.frame[args.order])
        pair = pd.DataFrame({"o": order, "v": values}).dropna()
        if len(pair) < 3 or pair["o"].nunique() < 2 or pair["v"].nunique() < 2:
            raise ValueError("Too few distinct paired values for a trend.")
        if len(pair) > MAX_TREND_ROWS:
            raise ValueError(f"Trend is limited to {MAX_TREND_ROWS} rows; this has {len(pair)}.")
        return {
            "value": args.value,
            "order": args.order,
            "n": int(len(pair)),
            "kendall_tau_b": _r(pair["o"].corr(pair["v"], method="kendall")),
            "note": "descriptive only; no significance test",
        }, 1

    def _missingness(self, _args: MissingnessArgs) -> tuple[dict[str, Any], int]:
        columns = self.schema.usable()[:MAX_MISSINGNESS_COLUMNS]
        rows = len(self.frame)
        return {
            "rows": rows,
            "columns": [
                {
                    "column": str(name),
                    "missing": int(self.frame[name].isna().sum()),
                    "missing_pct": _r(100 * self.frame[name].isna().mean()),
                }
                for name in columns
            ],
        }, 0

    def _overview(self, _args: OverviewArgs) -> tuple[dict[str, Any], int]:
        """Describe the table's dimensions, including columns not eligible for claims."""
        columns = list(self.frame.columns)[:MAX_MISSINGNESS_COLUMNS]
        return {
            "rows": len(self.frame),
            "column_count": len(self.frame.columns),
            "columns_shown": len(columns),
            "omitted_columns": len(self.frame.columns) - len(columns),
            "columns": [
                {
                    "column": name,
                    "role": self.schema.columns[name].role.value
                    if name in self.schema.columns else "unknown",
                    "usable_for_claims": self.schema.columns[name].usable_for_hypotheses
                    if name in self.schema.columns else False,
                    "missing": int(self.frame[name].isna().sum()),
                }
                for name in columns
            ],
            "note": "Detected roles describe the table, not its origin or sampling design.",
        }, 0

    def _scan_pairs(self, args: ScanPairsArgs) -> tuple[dict[str, Any], int]:
        names = self.schema.usable(ColumnRole.NUMERIC)
        pairs = len(names) * (len(names) - 1) // 2
        if pairs == 0:
            raise ValueError("Fewer than two usable numeric columns.")
        self._spend(pairs)
        numbers = pd.DataFrame({name: self._numeric(name) for name in names})
        floor = self.hypotheses.min_observations
        rho = numbers.corr(method="spearman", min_periods=floor)
        present = numbers.notna().astype(int)
        counts = present.T @ present
        ranked = []
        for i, left in enumerate(names):
            for right in names[i + 1 :]:
                value = rho.loc[left, right]
                if pd.notna(value) and counts.loc[left, right] >= floor:
                    ranked.append((abs(float(value)), left, right, float(value)))
        ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
        return {
            "pairs_examined": pairs,
            "pairs_with_enough_rows": len(ranked),
            "top": [
                {
                    "x": left,
                    "y": right,
                    "spearman_rho": _r(value),
                    "n": int(counts.loc[left, right]),
                }
                for _, left, right, value in ranked[: args.top]
            ],
            "note": "descriptive only; no significance test",
        }, pairs

    def _python(self, args: PythonArgs) -> tuple[dict[str, Any], int]:
        result = run_python(args.code, self.frame, self.config.sandbox)
        if not result.ok:
            raise ValueError(result.error or "The program failed.")
        return {"emitted": result.output, "printed": result.stdout}, 0
