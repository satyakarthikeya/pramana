"""The Skeptic: after the gate, look for a column that may account for part of a finding.

For a passed claim about x and y, every other usable column z is examined: does z go with both
x and y, and does the association between x and y shrink when rows are compared at a similar
value of z? Code computes every number from the table (rank-based partial association). The
output is descriptive caveats and questions for a NEXT run. It never changes a verdict, never
adds a claim to the run, and never says a column "explains away" anything: a column that
weakens an association may be a confounder, a step between the two, or something that both
influence, and this table cannot tell which.

Covered: correlation and trend claims, and group-difference claims with numeric controls.
Anything else is reported as "not checked", not as clean.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

from pramana.advisory.config import SkepticConfig
from pramana.advisory.findings import Finding
from pramana.advisory.models import Caveat, FindingReview, FollowUp
from pramana.analysis.hypotheses.trend import _as_ordered_numeric
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile


def _corr(a: pd.Series, b: pd.Series) -> float | None:
    """Pearson correlation, or None when either side is constant."""
    if a.nunique() < 2 or b.nunique() < 2:
        return None
    value = float(np.corrcoef(a.to_numpy(float), b.to_numpy(float))[0, 1])
    return value if math.isfinite(value) else None


def _residual(rank: pd.Series, z: pd.Series, categorical: bool) -> pd.Series:
    """What is left of `rank` after removing what the control z accounts for."""
    if categorical:
        return rank - rank.groupby(z.to_numpy()).transform("mean")
    rz = z.rank()
    spread = float(((rz - rz.mean()) ** 2).sum())
    if spread == 0:
        return rank - rank.mean()
    slope = float(((rz - rz.mean()) * (rank - rank.mean())).sum()) / spread
    return rank - (rank.mean() + slope * (rz - rz.mean()))


def _eta2(values: pd.Series, groups: pd.Series) -> float | None:
    """Share of the variation in `values` that lies between `groups` (0 to 1)."""
    total = float(((values - values.mean()) ** 2).sum())
    if total <= 0:
        return None
    between = float(
        sum(len(g) * (g.mean() - values.mean()) ** 2 for _, g in values.groupby(groups.to_numpy()))
    )
    return between / total


def _link_numeric(a: pd.Series, z: pd.Series) -> float | None:
    value = _corr(a.rank(), z.rank())
    return None if value is None else abs(value)


def _link_group(a: pd.Series, z: pd.Series) -> float | None:
    """How strongly a categorical control goes with a numeric column: sqrt of rank eta-squared."""
    share = _eta2(a.rank(), z)
    return None if share is None else math.sqrt(max(0.0, share))


def _usable_controls(
    frame: pd.DataFrame, schema: SchemaProfile, exclude: set[str], config: SkepticConfig
) -> list[tuple[str, bool]]:
    """(column, is_categorical) for columns that can act as a control, in schema order."""
    controls: list[tuple[str, bool]] = []
    for name in schema.usable(ColumnRole.NUMERIC, ColumnRole.CATEGORICAL, ColumnRole.ORDINAL):
        if name in exclude or name not in frame.columns:
            continue
        role = schema.columns[name].role
        if role is ColumnRole.NUMERIC:
            controls.append((name, False))
            continue
        counts = frame[name].dropna().astype(str).value_counts()
        if 2 <= len(counts) <= config.max_levels and int(counts.min()) >= config.min_level_rows:
            controls.append((name, True))
    return controls[: config.max_controls_checked]


def _sentence(
    finding: Finding,
    control: str,
    kind: str,
    link_first: float,
    link_second: float,
    before: float,
    after: float,
    n: int,
    measure: str,
) -> str:
    first, second = finding.variables[0], finding.variables[1]
    what = "rank correlation" if measure == "spearman_rho" else "share of variation between groups"
    return (
        f"{control} goes with both {first} and {second} (association {link_first:.2f} and "
        f"{link_second:.2f}). On the {n} rows where all three are recorded, the {what} between "
        f"{first} and {second} is {before:.2f}; comparing rows with a similar {control}, it is "
        f"{after:.2f}. {control} could be a confounder, a step between them, or something "
        "that both of them influence; this table cannot tell which. The verdict above "
        "is unchanged."
    )


def _follow_ups(finding: Finding, control: str, kind: str, numeric_pair: bool) -> list[FollowUp]:
    """Questions for a next run, rendered from templates. They are never tested automatically."""
    first, second = finding.variables[0], finding.variables[1]
    out: list[FollowUp] = []
    for column in (second, first) if numeric_pair else (second,):
        if kind == "numeric" and column != control:
            out.append(
                FollowUp(
                    sentence=f"Is {control} associated with {column}? (test in a next run)",
                    claim_type="correlation",
                    variables=[control, column],
                )
            )
        elif kind == "categorical":
            out.append(
                FollowUp(
                    sentence=f"Does {column} differ by {control}? (test in a next run)",
                    claim_type="group_difference",
                    variables=[control, column],
                )
            )
    return out[:2]


def _check_pair(
    finding: Finding,
    frame: pd.DataFrame,
    schema: SchemaProfile,
    config: SkepticConfig,
    x: pd.Series,
    y: pd.Series,
    measure: str,
    group: pd.Series | None,
) -> FindingReview:
    caveats: list[Caveat] = []
    checked = duplicates = 0
    exclude = set(finding.variables)
    for control, categorical in _usable_controls(frame, schema, exclude, config):
        if group is not None and categorical:
            continue  # a categorical control for a group claim is not covered
        z = frame[control]
        data = pd.DataFrame({"x": x, "y": y, "z": z}).dropna()
        if group is not None:
            data["g"] = group.reindex(data.index)
            data = data.dropna()
        if len(data) < config.min_rows:
            continue
        checked += 1
        zc = data["z"].astype(str) if categorical else pd.to_numeric(data["z"], errors="coerce")
        if not categorical and zc.nunique() < 2:
            continue
        if group is None:
            link_x = _link_group(data["x"], zc) if categorical else _link_numeric(data["x"], zc)
            link_y = _link_group(data["y"], zc) if categorical else _link_numeric(data["y"], zc)
            raw = _corr(data["x"].rank(), data["y"].rank())
            if (
                raw is None
                or link_x is None
                or link_y is None
                or abs(raw) < config.min_original_rho
            ):
                continue
            if max(link_x, link_y) >= config.max_duplicate_rho and not categorical:
                duplicates += 1
                continue
            part = _corr(
                _residual(data["x"].rank(), zc, categorical),
                _residual(data["y"].rank(), zc, categorical),
            )
            before, after, kind_measure = abs(raw), None if part is None else abs(part), measure
        else:
            ranks = data["y"].rank()
            before_value = _eta2(ranks, data["g"])
            link_x = _link_group(zc, data["g"])
            link_y = _link_numeric(data["y"], zc)
            if (
                before_value is None
                or link_x is None
                or link_y is None
                or before_value < config.min_original_eta2
            ):
                continue
            if link_y >= config.max_duplicate_rho:
                duplicates += 1
                continue
            after_value = _eta2(_residual(ranks, zc, False), data["g"])
            before, after, kind_measure = before_value, after_value, "rank_eta_squared"
        if after is None:
            continue
        if min(link_x, link_y) < config.min_link_to_control:
            continue
        if after > (1 - config.min_drop_fraction) * before:
            continue
        kind = "categorical" if categorical else "numeric"
        caveats.append(
            Caveat(
                insight_id=finding.insight_id,
                control=control,
                control_kind=kind,
                measure=kind_measure,  # type: ignore[arg-type]
                link_first=round(link_x, 4),
                link_second=round(link_y, 4),
                before=round(before, 4),
                after=round(after, 4),
                n=len(data),
                text=_sentence(
                    finding, control, kind, link_x, link_y, before, after, len(data), kind_measure
                ),
                follow_ups=_follow_ups(finding, control, kind, group is None),
            )
        )
    caveats.sort(key=lambda c: (c.after / c.before if c.before else 1.0, c.control))
    caveats = caveats[: config.max_caveats_per_finding]
    return FindingReview(
        insight_id=finding.insight_id,
        status="flagged" if caveats else "none_found",
        controls_checked=checked,
        skipped_near_duplicates=duplicates,
        caveats=caveats,
    )


def review_finding(
    finding: Finding, frame: pd.DataFrame, schema: SchemaProfile, config: SkepticConfig
) -> FindingReview:
    """Check one PASS finding. Never raises for odd data: that is reported as not checked."""

    def not_checked(reason: str) -> FindingReview:
        return FindingReview(insight_id=finding.insight_id, status="not_checked", reason=reason)

    if len(finding.variables) != 2 or any(v not in frame.columns for v in finding.variables):
        return not_checked("the claim's columns are not in the cleaned table")
    a, b = finding.variables
    try:
        if finding.claim_type == "correlation":
            x = pd.to_numeric(frame[a], errors="coerce")
            y = pd.to_numeric(frame[b], errors="coerce")
            return _check_pair(finding, frame, schema, config, x, y, "spearman_rho", None)
        if finding.claim_type == "trend":
            x = _as_ordered_numeric(frame[a])
            y = pd.to_numeric(frame[b], errors="coerce")
            return _check_pair(finding, frame, schema, config, x, y, "spearman_rho", None)
        if finding.claim_type == "group_difference":
            y = pd.to_numeric(frame[b], errors="coerce")
            group = frame[a].astype("string")
            return _check_pair(
                finding,
                frame,
                schema,
                config,
                group.astype(str).rank(),
                y,
                "rank_eta_squared",
                group,
            )
    except Exception:
        return not_checked("the check could not run on this data")
    return not_checked(f"{finding.claim_type} claims are not covered by this check")


def review_findings(
    findings: Sequence[Finding], frame: pd.DataFrame, schema: SchemaProfile, config: SkepticConfig
) -> list[FindingReview]:
    return [review_finding(f, frame, schema, config) for f in findings]
