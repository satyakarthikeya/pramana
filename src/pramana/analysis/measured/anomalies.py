"""M5: rows that are unusual in combination, set beside the single-column rule.

Guarantees: the multivariate score is an isolation forest averaged over several seeds, so
a flag does not depend on one seed; the comparison is with the Exact tier's robust-z rule
(a row is "extreme on a column" when any column is at or past the cutoff); the result is
shown only if the ranking of rows agrees across seeds at the configured level; the output
is a list of row numbers and what the flagged rows have in common, never a statement that
a row is wrong.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer

from pramana.analysis.computed.charts import Bar, BarChart
from pramana.analysis.measured.common import TITLES, clean, not_run, row
from pramana.analysis.measured.common import label as _label
from pramana.analysis.measured.config import MeasuredConfig
from pramana.analysis.measured.models import MeasuredItem
from pramana.analysis.measured.prep import num
from pramana.analysis.measured.segments import numeric_columns
from pramana.analysis.schema_inference import SchemaProfile
from pramana.analysis.shape import ShapeProfile

_MAD_SCALE = 1.4826


def robust_extreme(data: pd.DataFrame, cutoff: float) -> pd.Series:
    """True for rows where any column's robust z is at or past `cutoff`."""
    flags = pd.Series(False, index=data.index)
    for column in data.columns:
        values = data[column]
        median = values.median()
        mad = (values - median).abs().median()
        if not mad or np.isnan(mad):
            continue
        z = (values - median).abs() / (_MAD_SCALE * mad)
        flags |= z >= cutoff
    return flags


def run_anomalies(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    *,
    config: MeasuredConfig,
    columns: list[str] | None = None,
    roles: dict[str, str] | None = None,
) -> MeasuredItem:
    """M5 on the numeric columns of the table (or the requested ones)."""
    kind = "anomalies"
    chosen = numeric_columns(frame, schema, shape, config, requested=columns, roles=roles)
    if len(chosen) < 2:
        return not_run(kind, "Rows can be unusual in combination only with two or more numbers.")
    data = pd.DataFrame({c: num(frame[c]) for c in chosen}).dropna(how="all")
    if len(data) < config.min_rows:
        return not_run(kind, f"Fewer than {config.min_rows} rows have values.", features=chosen)
    cfg = config.anomalies
    filled = pd.DataFrame(
        SimpleImputer(strategy="median").fit_transform(data), index=data.index, columns=data.columns
    )
    scores = []
    for s in range(cfg.seeds):
        forest = IsolationForest(n_estimators=100, random_state=config.seed + s)
        forest.fit(filled)
        scores.append(-forest.score_samples(filled))  # higher = more unusual
    matrix = np.vstack(scores)
    ranks = pd.DataFrame(matrix.T).rank()
    pair = ranks.corr(method="pearson").to_numpy()
    stability = float(pair[np.triu_indices_from(pair, k=1)].mean())
    mean_score = matrix.mean(axis=0)
    n_flag = max(1, int(round(cfg.flag_fraction * len(filled))))
    top = np.argsort(-mean_score, kind="stable")[:n_flag]
    flagged = np.zeros(len(filled), dtype=bool)
    flagged[top] = True
    extreme = robust_extreme(filled, cfg.robust_z).to_numpy()
    both = int((flagged & extreme).sum())
    forest_only = int((flagged & ~extreme).sum())
    z_only = int((~flagged & extreme).sum())

    # What the flagged rows share: columns where their middle value sits far from the rest.
    shared = []
    for column in filled.columns:
        rest = filled.loc[~flagged, column]
        mad = (rest - rest.median()).abs().median()
        spread = _MAD_SCALE * mad if mad else float(rest.std() or 1.0)
        shift = (filled.loc[flagged, column].median() - rest.median()) / spread
        shared.append((column, float(shift), float(filled.loc[flagged, column].median())))
    shared.sort(key=lambda t: -abs(t[1]))

    positions = {label: i for i, label in enumerate(frame.index)}
    listed = []
    for i in top[: cfg.max_listed]:
        original = filled.index[i]
        listed.append(
            row(
                part="flagged row",
                row_number=positions[original] + 1,
                score=float(mean_score[i]),
                extreme_on_one_column=bool(extreme[i]),
            )
        )
    values = {
        "flagged": n_flag,
        "rows": len(filled),
        "flagged_by_both": both,
        "flagged_in_combination_only": forest_only,
        "extreme_column_only": z_only,
        "rank_agreement_across_seeds": stability,
        "seeds": cfg.seeds,
        "robust_z_cutoff": cfg.robust_z,
        "rank_stability_cutoff": cfg.rank_stability_cutoff,
    }
    common = dict(
        id=kind,
        kind=kind,
        title=TITLES[kind],
        features=chosen,
        model_family="isolation forest",
        models_tried=1,
        split=f"scores averaged over {cfg.seeds} seeds",
        baseline=f"single-column robust z of {cfg.robust_z:g} or more",
        metric="rank agreement across seeds",
        model_score=stability,
        n_rows=len(filled),
        values={k: clean(v) for k, v in values.items()},
    )
    if stability < cfg.rank_stability_cutoff:
        return MeasuredItem(
            status="no_lift",
            sentence=(
                f"No stable list of unusual rows: the ranking of rows agreed across seeds at "
                f"{stability:.2f}, below the cutoff of {cfg.rank_stability_cutoff:.2f}."
            ),
            **common,
        )
    notable = [t for t in shared if abs(t[1]) >= cfg.shared_min_shift][: cfg.max_shared_columns]
    table = [
        row(part="shared column", column=c, flagged_median=m, shift_in_robust_sd=s)
        for c, s, m in notable
    ]
    sentence = (
        f"An isolation forest flags {n_flag} of {len(filled)} rows as unusual in combination; "
        f"{both} of them are also extreme on a single column, and {forest_only} are unusual "
        f"only in combination. The ranking agrees across {cfg.seeds} seeds at {stability:.2f}."
    )
    if notable:
        names = ", ".join(_label(c) for c, _, _ in notable[:3])
        sentence += f" The flagged rows differ most on {names}."
    return MeasuredItem(
        status="ok",
        sentence=sentence,
        table=[*table, *listed] if table else listed,
        chart=BarChart(
            x_label="Rows flagged by",
            y_label="Rows",
            bars=[
                Bar(label="Both rules", value=float(both)),
                Bar(label="Combination only", value=float(forest_only)),
                Bar(label="Single column only", value=float(z_only)),
            ],
        ),
        **common,
    )
