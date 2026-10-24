"""M4: do the rows fall into groups that are real in the sense of being stable?

Guarantees: k is chosen by silhouette on a training part only and judged on the held-out
part; the baseline is the same procedure on copies of the table whose columns were
shuffled independently (which keeps every column's values and removes any joint
structure); groups are called stable only if the held-out silhouette beats the best
shuffled copy by the configured margin AND bootstrap re-clusterings agree with the
full-data grouping (adjusted Rand index at or above the cutoff) AND no group is a sliver.
Otherwise the result is "no stable segments", which is shown, not hidden.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

from pramana.analysis.computed.charts import Bar, BarChart
from pramana.analysis.measured.common import TITLES, clean, not_run, row, sd
from pramana.analysis.measured.config import MeasuredConfig
from pramana.analysis.measured.models import MeasuredItem
from pramana.analysis.measured.prep import eligible_columns, num
from pramana.analysis.schema_inference import ColumnRole, SchemaProfile
from pramana.analysis.shape import ShapeProfile

_SILHOUETTE_SAMPLE = 1000


def numeric_columns(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    config: MeasuredConfig,
    *,
    requested: list[str] | None = None,
    roles: dict[str, str] | None = None,
) -> list[str]:
    """Numeric measurement columns for the unsupervised analyses, fullest columns first.

    Identifiers, survey weights, the time axis and the entity column are never used.
    """
    roles = roles or {}
    skip = {shape.time_column, shape.entity_column} - {None}
    pool = requested or [
        c
        for c, p in schema.columns.items()
        if p.role in {ColumnRole.NUMERIC, ColumnRole.ORDINAL} and c in frame.columns
    ]
    pool = [c for c in pool if c not in skip and roles.get(c) != "survey_weight"]
    kept, _ = eligible_columns(frame, schema, pool, config=config)
    kept = [c for c in kept if schema.role_of(c) is not ColumnRole.ID_LIKE]
    missing = {c: float(num(frame[c]).isna().mean()) for c in kept}
    ordered = sorted(kept, key=lambda c: missing[c])
    return ordered if requested else ordered[: config.max_features]


def _best_k(train: np.ndarray, config: MeasuredConfig, seed: int) -> tuple[int, KMeans]:
    """The k in the fixed range with the best silhouette on `train`, and its fitted model."""
    k_cfg = config.segments
    best: tuple[float, int, KMeans] | None = None
    top = min(k_cfg.k_max, len(train) - 1)
    for k in range(k_cfg.k_min, top + 1):
        model = KMeans(n_clusters=k, n_init=5, random_state=seed).fit(train)
        if len(set(model.labels_)) < 2:
            continue
        score = silhouette_score(
            train,
            model.labels_,
            sample_size=min(len(train), _SILHOUETTE_SAMPLE),
            random_state=seed,
        )
        if best is None or score > best[0]:
            best = (float(score), k, model)
    if best is None:
        raise ValueError("no k produced two or more groups")
    return best[1], best[2]


def _held_out_silhouette(model: KMeans, test: np.ndarray, seed: int) -> float | None:
    labels = model.predict(test)
    if len(set(labels)) < 2 or len(test) <= len(set(labels)):
        return None
    return float(
        silhouette_score(
            test, labels, sample_size=min(len(test), _SILHOUETTE_SAMPLE), random_state=seed
        )
    )


def _shuffle_columns(matrix: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    out = matrix.copy()
    for j in range(out.shape[1]):
        out[:, j] = out[rng.permutation(len(out)), j]
    return out


def run_segments(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    shape: ShapeProfile,
    *,
    config: MeasuredConfig,
    columns: list[str] | None = None,
    roles: dict[str, str] | None = None,
) -> MeasuredItem:
    """M4 on the numeric columns of the table (or the requested ones)."""
    kind = "segments"
    chosen = numeric_columns(frame, schema, shape, config, requested=columns, roles=roles)
    if len(chosen) < 2:
        return not_run(kind, "Segments need at least two numeric columns.")
    data = pd.DataFrame({c: num(frame[c]) for c in chosen}).dropna(how="all")
    if len(data) < config.min_rows:
        return not_run(kind, f"Fewer than {config.min_rows} rows have values.", features=chosen)
    cfg = config.segments
    rng = np.random.default_rng(config.seed)
    filled = SimpleImputer(strategy="median").fit_transform(data)
    order = rng.permutation(len(filled))
    n_train = int(len(filled) * cfg.train_fraction)
    train_idx, test_idx = order[:n_train], order[n_train:]
    scaler = StandardScaler().fit(filled[train_idx])
    scaled = scaler.transform(filled)
    train, test = scaled[train_idx], scaled[test_idx]

    k, model = _best_k(train, config, config.seed)
    train_sil = float(
        silhouette_score(
            train,
            model.labels_,
            sample_size=min(len(train), _SILHOUETTE_SAMPLE),
            random_state=config.seed,
        )
    )
    held = _held_out_silhouette(model, test, config.seed)
    if held is None:
        return not_run(kind, "The held-out rows fell into one group.", features=chosen)

    nulls: list[float] = []
    for r in range(cfg.null_repeats):
        null_rng = np.random.default_rng(config.seed + 1 + r)
        shuffled_train = _shuffle_columns(train, null_rng)
        shuffled_test = _shuffle_columns(test, null_rng)
        try:
            _, null_model = _best_k(shuffled_train, config, config.seed + 1 + r)
        except ValueError:
            continue
        score = _held_out_silhouette(null_model, shuffled_test, config.seed + 1 + r)
        if score is not None:
            nulls.append(score)
    if not nulls:
        return not_run(kind, "The shuffled copies could not be clustered.", features=chosen)

    full = KMeans(n_clusters=k, n_init=5, random_state=config.seed).fit(scaled)
    aris = []
    for b in range(cfg.bootstrap_repeats):
        boot_rng = np.random.default_rng(config.seed + 1000 + b)
        sample = scaled[boot_rng.integers(0, len(scaled), len(scaled))]
        boot = KMeans(n_clusters=k, n_init=3, random_state=config.seed + b).fit(sample)
        aris.append(float(adjusted_rand_score(full.labels_, boot.predict(scaled))))
    ari, ari_sd = float(np.mean(aris)), sd(aris)

    sizes = np.bincount(full.labels_, minlength=k)
    order_sizes = np.argsort(-sizes, kind="stable")
    smallest_share = float(sizes.min() / len(scaled))
    null_max, null_mean = float(np.max(nulls)), float(np.mean(nulls))
    beats_null = held >= null_max + cfg.silhouette_margin
    stable = beats_null and ari >= cfg.ari_cutoff and smallest_share >= cfg.min_segment_share

    values = {
        "k": k,
        "silhouette_train": train_sil,
        "silhouette_held_out": held,
        "silhouette_null_max": null_max,
        "silhouette_null_mean": null_mean,
        "ari_mean": ari,
        "ari_sd": ari_sd,
        "smallest_share_pct": smallest_share * 100,
        "null_copies": len(nulls),
        "bootstrap_repeats": cfg.bootstrap_repeats,
        "ari_cutoff": cfg.ari_cutoff,
    }
    split_text = (
        f"{int(cfg.train_fraction * 100)}% of rows to choose k, the rest to judge it; "
        f"{cfg.bootstrap_repeats} bootstrap re-clusterings"
    )
    common = dict(
        id=kind,
        kind=kind,
        title=TITLES[kind],
        features=chosen,
        model_family="k-means",
        models_tried=cfg.k_max - cfg.k_min + 1,
        split=split_text,
        baseline=f"best of {len(nulls)} column-shuffled copies of the table",
        metric="silhouette",
        baseline_score=null_max,
        model_score=held,
        lift=held - null_max,
        spread=ari_sd,
        n_rows=len(data),
        values={key: clean(v) for key, v in values.items()},
    )
    if not stable:
        return MeasuredItem(
            status="no_lift",
            sentence=(
                f"No stable segments: the best grouping (k = {k}) had a held-out silhouette of "
                f"{held:.2f} against {null_max:.2f} for column-shuffled copies, and bootstrap "
                f"agreement of {ari:.2f} against a cutoff of {cfg.ari_cutoff:.2f}."
            ),
            **common,
        )
    original = pd.DataFrame({c: num(frame[c]) for c in chosen}).loc[data.index]
    shown = chosen[: cfg.max_profile_columns]
    table = []
    for rank, cluster in enumerate(order_sizes, start=1):
        members = original[full.labels_ == cluster]
        profile = {f"mean {c}": float(members[c].mean()) for c in shown}
        table.append(
            row(
                segment=f"Segment {rank}",
                rows=int(sizes[cluster]),
                share_pct=float(sizes[cluster] / len(scaled) * 100),
                **profile,
            )
        )
    return MeasuredItem(
        status="ok",
        sentence=(
            f"Rows fall into {k} segments that hold up when the data is resampled: bootstrap "
            f"agreement {ari:.2f} (cutoff {cfg.ari_cutoff:.2f}) and a held-out silhouette of "
            f"{held:.2f} against {null_max:.2f} for column-shuffled copies of the same table."
        ),
        table=table,
        chart=BarChart(
            x_label="Segment",
            y_label="Rows",
            bars=[
                Bar(label=f"Segment {rank}", value=float(sizes[c]), n=int(sizes[c]))
                for rank, c in enumerate(order_sizes, start=1)
            ],
        ),
        **common,
    )


__all__ = ["numeric_columns", "run_segments"]
