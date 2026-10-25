"""M8: which columns move together, and how many independent directions the table has.

Guarantees: components are kept only if their eigenvalue is above the configured quantile
of the same-rank eigenvalues of column-shuffled copies of the table (parallel analysis;
shuffling keeps every column's values and removes any joint structure); the kept
components must also reappear when rows are resampled (mean, over kept components, of the
best absolute cosine of their loadings against the resampled ones, at or above the cutoff).
Otherwise the result is "no components beyond chance", which is shown, not hidden.
A description of the table, never a
cause and never a claim.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from pramana.analysis.computed.charts import Bar, BarChart
from pramana.analysis.measured.common import TITLES, clean, not_run, row
from pramana.analysis.measured.config import MeasuredConfig
from pramana.analysis.measured.models import MeasuredItem
from pramana.analysis.measured.prep import num
from pramana.analysis.measured.segments import _shuffle_columns, numeric_columns
from pramana.analysis.schema_inference import SchemaProfile
from pramana.analysis.shape import ShapeProfile


def _loadings(columns: list[str], vector: np.ndarray, top: int) -> tuple[str, list[float]]:
    order = np.argsort(-np.abs(vector))[:top]
    shown = [(columns[i], float(vector[i])) for i in order if abs(vector[i]) >= 0.2]
    return ", ".join(f"{c} ({v:+.2f})" for c, v in shown), [v for _, v in shown]


def run_components(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    *,
    config: MeasuredConfig,
    columns: list[str] | None = None,
    roles: dict[str, str] | None = None,
) -> MeasuredItem:
    kind = "components"
    chosen = numeric_columns(frame, schema, shape, config, requested=columns, roles=roles)
    if len(chosen) < 3:
        return not_run(kind, "Components need at least three numeric columns.")
    data = pd.DataFrame({c: num(frame[c]) for c in chosen}).dropna(how="all")
    if len(data) < config.min_rows:
        return not_run(kind, f"Fewer than {config.min_rows} rows have values.", features=chosen)
    cfg = config.components
    filled = SimpleImputer(strategy="median").fit_transform(data)
    spread = filled.std(axis=0)
    varying = [c for c, s in zip(chosen, spread, strict=True) if s > 0]
    if len(varying) < 3:
        return not_run(kind, "Fewer than three columns vary.", features=chosen)
    scaled = StandardScaler().fit_transform(filled[:, spread > 0])
    pca = PCA().fit(scaled)
    eig = pca.explained_variance_
    null = np.array(
        [
            PCA()
            .fit(_shuffle_columns(scaled, np.random.default_rng(config.seed + 1 + r)))
            .explained_variance_
            for r in range(cfg.null_repeats)
        ]
    )
    threshold = np.quantile(null, cfg.null_quantile, axis=0)
    above = eig > threshold
    n_keep = len(above) if above.all() else int(np.argmin(above))  # the leading run only
    level = int(cfg.null_quantile * 100)
    common = dict(
        id=kind,
        kind=kind,
        title=TITLES[kind],
        features=varying,
        model_family="principal components",
        models_tried=cfg.null_repeats,
        split=f"{cfg.null_repeats} column-shuffled copies of the table; "
        f"{cfg.bootstrap_repeats} bootstrap resamples",
        baseline=f"{level}th percentile of eigenvalues from shuffled copies",
        metric="eigenvalue",
        baseline_score=float(threshold[0]),
        model_score=float(eig[0]),
        lift=float(eig[0] - threshold[0]),
        n_rows=len(data),
    )
    values: dict[str, object] = {
        "components_kept": n_keep,
        "first_eigenvalue": float(eig[0]),
        "first_null_threshold": float(threshold[0]),
        "null_copies": cfg.null_repeats,
        "null_percentile": level,
    }
    if n_keep == 0:
        return MeasuredItem(
            status="no_lift",
            sentence=(
                f"No components beyond chance: the strongest direction has an eigenvalue of "
                f"{eig[0]:.2f}, against {threshold[0]:.2f} at the {level}th percentile of "
                "column-shuffled copies, so the columns do not move together more than shuffled "
                "columns do."
            ),
            values={k: clean(v) for k, v in values.items()},
            **common,
        )
    first = pca.components_[0]
    sims = []
    for b in range(cfg.bootstrap_repeats):
        boot = np.random.default_rng(config.seed + 1000 + b)
        sample = scaled[boot.integers(0, len(scaled), len(scaled))]
        # best-matching resampled component for each kept one, so two components of similar
        # strength swapping places between resamples is not counted as instability
        resampled = PCA(n_components=n_keep).fit(sample).components_
        sims.append(float(np.mean(np.abs(pca.components_[:n_keep] @ resampled.T).max(axis=1))))
    stability = float(np.mean(sims))
    explained = float(pca.explained_variance_ratio_[:n_keep].sum() * 100)
    text, loads = _loadings(varying, first, cfg.max_loadings)
    values.update(
        {
            "component_stability": stability,
            "stability_cutoff": cfg.stability_cutoff,
            "variance_explained_pct": explained,
            "columns_used": len(varying),
            **{f"first_loading_{i}": v for i, v in enumerate(loads, start=1)},
        }
    )
    table = []
    for k in range(n_keep):
        loads_on, _ = _loadings(varying, pca.components_[k], cfg.max_loadings)
        table.append(
            row(
                component=f"Component {k + 1}",
                eigenvalue=float(eig[k]),
                null_threshold=float(threshold[k]),
                variance_explained_pct=float(pca.explained_variance_ratio_[k] * 100),
                loads_on=loads_on or "no column above 0.2",
            )
        )
    stable = stability >= cfg.stability_cutoff
    sentence = (
        f"{n_keep} component{'s stand' if n_keep != 1 else ' stands'} above shuffled copies, "
        f"together holding {explained:.1f}% of the variation in {len(varying)} columns."
    )
    if text:
        sentence += f" The first loads on {text}."
    if stable:
        sentence += (
            f" The components reappear when rows are resampled (agreement {stability:.2f}, "
            f"cutoff {cfg.stability_cutoff:.2f})."
        )
    else:
        sentence += (
            f" The components did not hold up when rows were resampled (agreement {stability:.2f}, "
            f"cutoff {cfg.stability_cutoff:.2f}), so read it with care."
        )
    return MeasuredItem(
        status="ok" if stable else "no_lift",
        sentence=sentence,
        table=table,
        chart=BarChart(
            x_label="Component",
            y_label="Variance explained (%)",
            bars=[
                Bar(label=f"Component {k + 1}", value=float(pca.explained_variance_ratio_[k] * 100))
                for k in range(min(len(eig), max(n_keep + 2, 4)))
            ],
        ),
        values={k: clean(v) for k, v in values.items()},
        **common,
    )


__all__ = ["run_components"]
