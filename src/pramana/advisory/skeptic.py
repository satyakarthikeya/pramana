"""The Skeptic: after the gate, look for a column that may account for part of a finding.

For a passed claim about x and y, every other usable column z is examined: does z go with both
x and y, and does the association between x and y shrink when rows are compared at a similar
value of z? Code computes every number from the table (rank-based partial association). The
output is descriptive caveats and questions for a NEXT run. It never changes a verdict, never
adds a claim to the run, and never says a column "explains away" anything: a column that
weakens an association may be a confounder, a step between the two, or something both
influence, and this table cannot tell which.

Covered: correlation and trend claims, and group-difference claims with numeric controls.
Anything else, and any finding where no other column could actually be compared, is reported
as "not checked" with the reason, never as clean. A wall-clock budget bounds the work.
"""

from __future__ import annotations

import math
import time
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
    """How strongly a categorical column goes with a numeric one, from 0 to 1.

    Rank eta-squared cannot reach 1 even when the groups are perfectly separated: with k equal
    groups its ceiling is 1 - 1/k squared (0.75 for two groups). Dividing by that ceiling makes
    a column that fully separates the groups score 1, which the near-duplicate rule relies on.
    """
    share = _eta2(a.rank(), z)
    if share is None:
        return None
    k = int(z.nunique())
    ceiling = 1 - 1 / (k * k) if k > 1 else 1.0
    return math.sqrt(min(1.0, max(0.0, share) / ceiling))


def _levels_ok(z: pd.Series, config: SkepticConfig) -> bool:
    """Enough levels, each with enough rows, on the rows actually used."""
    counts = z.value_counts()
    return 2 <= len(counts) <= config.max_levels and int(counts.min()) >= config.min_level_rows


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


def _not_checked(
    finding: Finding, reason: str, *, duplicates: int = 0, checked: int = 0
) -> FindingReview:
    return FindingReview(
        insight_id=finding.insight_id,
        status="not_checked",
        reason=reason,
        controls_checked=checked,
        skipped_near_duplicates=duplicates,
    )


def _check_pair(
    finding: Finding,
    frame: pd.DataFrame,
    schema: SchemaProfile,
    config: SkepticConfig,
    x: pd.Series,
    y: pd.Series,
    measure: str,
    group: pd.Series | None,
    deadline: float | None,
) -> FindingReview:
    caveats: list[Caveat] = []
    checked = duplicates = 0
    unmet: set[str] = set()
    timed_out = False
    controls = _usable_controls(frame, schema, set(finding.variables), config)
    for control, categorical in controls:
        if deadline is not None and time.monotonic() > deadline:
            timed_out = True
            break
        if group is not None and categorical:
            unmet.add("categorical columns are not covered for group-difference claims")
            continue
        data = pd.DataFrame({"x": x, "y": y, "z": frame[control]}).dropna()
        if group is not None:
            data["g"] = group.reindex(data.index)
            data = data.dropna()
        if len(data) < config.min_rows:
            unmet.add("no other usable column had enough complete rows")
            continue
        zc = data["z"].astype(str) if categorical else pd.to_numeric(data["z"], errors="coerce")
        if categorical and not _levels_ok(zc, config):
            unmet.add("a categorical column had too few rows per level on the rows used")
            continue
        if not categorical and zc.nunique() < 2:
            unmet.add("no other usable column varied on the rows used")
            continue
        if group is None:
            link_x = _link_group(data["x"], zc) if categorical else _link_numeric(data["x"], zc)
            link_y = _link_group(data["y"], zc) if categorical else _link_numeric(data["y"], zc)
            raw = _corr(data["x"].rank(), data["y"].rank())
            if raw is None or link_x is None or link_y is None:
                unmet.add("the comparison could not be computed on the rows used")
                continue
            if abs(raw) < config.min_original_rho:
                unmet.add("the association on these rows is too small to compare")
                continue
            limit = config.max_duplicate_group_link if categorical else config.max_duplicate_rho
            if max(link_x, link_y) >= limit:
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
            if before_value is None or link_x is None or link_y is None:
                unmet.add("the comparison could not be computed on the rows used")
                continue
            if before_value < config.min_original_eta2:
                unmet.add("the group difference on these rows is too small to compare")
                continue
            if link_x >= config.max_duplicate_group_link or link_y >= config.max_duplicate_rho:
                duplicates += 1  # a column that encodes the group, or the outcome, is a proxy
                continue
            after_value = _eta2(_residual(ranks, zc, False), data["g"])
            before, after, kind_measure = before_value, after_value, "rank_eta_squared"
        checked += 1
        if after is None or min(link_x, link_y) < config.min_link_to_control:
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
                    finding, control, link_x, link_y, before, after, len(data), kind_measure
                ),
                follow_ups=_follow_ups(finding, control, kind, group is None),
            )
        )
    caveats.sort(key=lambda c: (c.after / c.before if c.before else 1.0, c.control))
    caveats = caveats[: config.max_caveats_per_finding]
    budget = f"the time budget ran out after {checked} of {len(controls)} other columns"
    if caveats:
        return FindingReview(
            insight_id=finding.insight_id,
            status="flagged",
            reason=budget if timed_out else None,
            controls_checked=checked,
            skipped_near_duplicates=duplicates,
            caveats=caveats,
        )
    if timed_out:
        return _not_checked(finding, budget, duplicates=duplicates, checked=checked)
    if checked == 0:
        if duplicates and not unmet:
            reason = "the only other columns look like the same measurement as a claim column"
        else:
            reason = "; ".join(sorted(unmet)) or "there was no other usable column to compare"
        return _not_checked(finding, reason, duplicates=duplicates)
    return FindingReview(
        insight_id=finding.insight_id,
        status="none_found",
        controls_checked=checked,
        skipped_near_duplicates=duplicates,
    )


def review_finding(
    finding: Finding,
    frame: pd.DataFrame,
    schema: SchemaProfile,
    config: SkepticConfig,
    deadline: float | None = None,
) -> FindingReview:
    """Check one PASS finding. Never raises for odd data: that is reported as not checked."""
    if len(finding.variables) != 2 or any(v not in frame.columns for v in finding.variables):
        return _not_checked(finding, "the claim's columns are not in the cleaned table")
    if deadline is not None and time.monotonic() > deadline:
        return _not_checked(finding, "the time budget ran out before this finding")
    a, b = finding.variables
    try:
        if finding.claim_type == "correlation":
            x = pd.to_numeric(frame[a], errors="coerce")
            y = pd.to_numeric(frame[b], errors="coerce")
            return _check_pair(finding, frame, schema, config, x, y, "spearman_rho", None, deadline)
        if finding.claim_type == "trend":
            x = _as_ordered_numeric(frame[a])
            y = pd.to_numeric(frame[b], errors="coerce")
            return _check_pair(finding, frame, schema, config, x, y, "spearman_rho", None, deadline)
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
                deadline,
            )
    except Exception:
        return _not_checked(finding, "the check could not run on this data")
    return _not_checked(finding, f"{finding.claim_type} claims are not covered by this check")


def review_findings(
    findings: Sequence[Finding],
    frame: pd.DataFrame,
    schema: SchemaProfile,
    config: SkepticConfig,
    deadline: float | None = None,
) -> list[FindingReview]:
    return [review_finding(f, frame, schema, config, deadline) for f in findings]
