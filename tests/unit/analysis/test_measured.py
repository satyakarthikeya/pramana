"""Measured tier (PLAN §5.2): planted known answers, leakage lint, wording, budget."""

from __future__ import annotations

import re
import time

import pandas as pd
import pytest

from pramana.analysis.computed.charts import ForecastChart
from pramana.analysis.measured import (
    MEASURED_VERSION,
    MeasuredItem,
    MeasuredRequest,
    compute_measured,
    load_measured_config,
)
from pramana.analysis.measured.adjusted import run_adjusted
from pramana.analysis.measured.anomalies import run_anomalies
from pramana.analysis.measured.drivers import run_driver
from pramana.analysis.measured.forecast import run_forecast
from pramana.analysis.measured.leakage import lint_features
from pramana.analysis.measured.runner import pick_target
from pramana.analysis.measured.segments import run_segments
from pramana.analysis.measured.threshold import run_threshold
from pramana.verification.admissibility import CAUSAL_TERMS, UNIVERSAL_TERMS, _matched_terms
from tests.unit.analysis import measured_fixtures as fx

CONFIG = fx.fast_config()


def _driver(frame: pd.DataFrame, target: str, task: str = "regression", **kw) -> MeasuredItem:
    schema, shape = fx.prepare(frame)
    return run_driver(frame, schema, shape, task=task, target=target, config=CONFIG, **kw)


# --- config -------------------------------------------------------------------------


def test_config_loads_strictly_and_marks_the_seed() -> None:
    config = load_measured_config()
    assert config.seed == 20260817
    assert config.leakage.proxy_cutoff < config.too_good_cutoff
    with pytest.raises(ValueError):
        type(config).model_validate({**config.model_dump(), "surprise": 1})


# --- M1 / M2 ------------------------------------------------------------------------


def test_planted_driver_ranks_first_and_beats_the_baseline() -> None:
    item = _driver(fx.driver_table(), "sales")
    assert item.status == "ok"
    assert item.lift is not None and item.lift > CONFIG.lift_floor
    assert item.lift > 0.5  # sales = 3 * ad_spend + unit noise: R² near 0.9
    assert item.values["top_feature"] == "ad_spend"
    assert item.table[0]["feature"] == "ad_spend"
    assert item.table[0]["share_pct"] > 80
    assert item.models_tried > 0 and item.split.endswith("folds KFold") is False
    assert "3-fold KFold" in item.split
    assert item.baseline == "mean of the training rows"
    assert item.spread is not None and item.spread >= 0
    assert "beats the mean of the training rows baseline" in item.sentence
    assert "row_id" in [e.column for e in item.leakage]


def test_pure_noise_target_gets_no_lift_and_says_so() -> None:
    item = _driver(fx.driver_table(), "noise_target")
    assert item.status == "no_lift"
    assert item.sentence.startswith("No model")
    assert item.table == [] and item.chart is None


def test_classification_target_uses_balanced_accuracy() -> None:
    item = _driver(fx.driver_table(), "is_high", task="classification")
    assert item.status == "ok", item.sentence
    assert item.kind == "driver_classification"
    assert item.metric == "balanced accuracy"
    assert item.baseline_score == pytest.approx(0.5)
    assert item.lift is not None and item.lift > 0.25
    assert item.values["top_feature"] == "ad_spend"
    # the column the label was cut from is a restatement of it and must not be offered
    assert "sales" not in item.features


def test_a_score_too_good_to_be_true_is_withheld() -> None:
    strict = fx.fast_config(too_good_cutoff=0.6)
    frame = fx.driver_table()
    schema, shape = fx.prepare(frame)
    item = run_driver(frame, schema, shape, task="regression", target="sales", config=strict)
    assert item.status == "withheld"
    assert item.lift is None and item.model_score is None
    assert "too good to be true" in item.sentence


def test_too_few_rows_is_a_reasoned_not_run() -> None:
    item = _driver(fx.driver_table(n=30), "sales")
    assert item.status == "not_run" and item.reason


# --- leakage lint -------------------------------------------------------------------


def test_leakage_lint_catches_ids_identities_and_proxies() -> None:
    frame = fx.leaky_table()
    schema, _ = fx.prepare(frame)
    kept, excluded = lint_features(
        frame,
        schema,
        "revenue",
        frame["revenue"],
        ["ad_spend", "cost", "net", "rev_copy", "row_id"],
        task="regression",
        config=CONFIG,
    )
    reasons = {e.column: e.reason for e in excluded}
    assert "row_id" in reasons and "identifier" in reasons["row_id"]
    assert "net" in reasons and "add up to revenue" in reasons["net"]
    assert "cost" in reasons  # the other half of the identity
    assert "rev_copy" in reasons and "close to restating" in reasons["rev_copy"]
    assert kept == ["ad_spend"]


def test_exact_straight_line_restatement_is_excluded() -> None:
    frame = fx.leaky_table()
    frame["revenue_k"] = frame["revenue"] / 1000
    schema, _ = fx.prepare(frame)
    kept, excluded = lint_features(
        frame, schema, "revenue", frame["revenue"], ["ad_spend", "revenue_k"],
        task="regression", config=CONFIG,
    )  # fmt: skip
    assert kept == ["ad_spend"]
    assert "straight-line restatement" in excluded[0].reason


def test_driver_item_reports_what_the_lint_removed() -> None:
    item = _driver(fx.leaky_table(), "revenue")
    names = {e.column for e in item.leakage}
    assert {"row_id", "net", "rev_copy"} <= names
    assert "net" not in item.features and "ad_spend" in item.features


# --- M3 -----------------------------------------------------------------------------


def _adjusted_frame(redundant: bool) -> pd.DataFrame:
    import numpy as np

    rng = np.random.default_rng(8)
    n = 300
    c = rng.normal(size=n)
    x = c + rng.normal(scale=0.3, size=n) if redundant else 0.5 * c + rng.normal(size=n)
    y = 3 * c + rng.normal(size=n) if redundant else 2 * x + 3 * c + rng.normal(size=n)
    return pd.DataFrame({"y": y, "x": x, "c": c})


def test_adjusted_association_adds_held_out_skill_with_stable_sign() -> None:
    frame = _adjusted_frame(redundant=False)
    schema, shape = fx.prepare(frame)
    item = run_adjusted(
        frame, schema, shape, target="y", variable="x", controls=["c"], config=CONFIG
    )
    assert item.status == "ok", item.sentence
    assert item.lift is not None and item.lift > 0.1
    assert item.values["sign_agreement"] == 1.0
    assert float(item.values["partial_effect_per_sd"]) > 0  # type: ignore[arg-type]
    assert item.baseline == "model without the variable"


def test_adjusted_association_with_a_redundant_variable_has_no_lift() -> None:
    frame = _adjusted_frame(redundant=True)
    schema, shape = fx.prepare(frame)
    item = run_adjusted(
        frame, schema, shape, target="y", variable="x", controls=["c"], config=CONFIG
    )
    assert item.status == "no_lift"


# --- M4 -----------------------------------------------------------------------------


def test_three_planted_clusters_are_found_and_stable() -> None:
    frame = fx.three_blobs()
    schema, shape = fx.prepare(frame)
    item = run_segments(frame, schema, shape, config=CONFIG)
    assert item.status == "ok", item.sentence
    assert item.values["k"] == 3
    assert float(item.values["ari_mean"]) >= CONFIG.segments.ari_cutoff  # type: ignore[arg-type]
    assert [r["rows"] for r in item.table] == [100, 100, 100]
    assert item.lift is not None and item.lift > CONFIG.segments.silhouette_margin


def test_a_single_cloud_has_no_stable_segments() -> None:
    frame = fx.no_clusters()
    schema, shape = fx.prepare(frame)
    item = run_segments(frame, schema, shape, config=CONFIG)
    assert item.status == "no_lift"
    assert item.sentence.startswith("No stable segments")
    assert item.table == []


# --- M5 -----------------------------------------------------------------------------


def test_planted_multivariate_outliers_are_flagged_in_combination() -> None:
    frame = fx.outlier_table()
    schema, shape = fx.prepare(frame)
    item = run_anomalies(frame, schema, shape, config=CONFIG)
    assert item.status == "ok", item.sentence
    listed = {r["row_number"] for r in item.table if r["part"] == "flagged row"}
    planted = {p + 1 for p in fx.PLANTED_OUTLIER_ROWS}
    assert planted <= listed
    # each planted value is ordinary on its own, so the single-column rule misses them
    assert item.values["flagged_in_combination_only"] >= len(planted)  # type: ignore[operator]
    assert float(item.values["rank_agreement_across_seeds"]) >= 0.8  # type: ignore[arg-type]


# --- M6 -----------------------------------------------------------------------------


def test_seasonal_series_is_forecast_better_than_seasonal_naive() -> None:
    frame = fx.monthly_series(48)
    schema, shape = fx.prepare(frame)
    assert shape.period == "month" and shape.shape.value == "time_series"
    item = run_forecast(frame, schema, shape, target="revenue", config=CONFIG)
    assert item.status == "ok", item.sentence
    assert item.baseline == "seasonal-naive"
    assert item.model_score is not None and item.baseline_score is not None
    assert item.model_score < item.baseline_score
    assert item.lift is not None and item.lift > 0
    assert item.values["error_reduction_pct"] > 30  # type: ignore[operator]
    assert 0 < float(item.values["interval_backtest_coverage"]) <= 1  # type: ignore[arg-type]
    assert "rolling-origin backtest" in item.split
    chart = item.chart
    assert isinstance(chart, ForecastChart)
    assert len(chart.forecast) == len(chart.lower) == len(chart.upper) == 6
    assert all(lo <= f <= up for (_, lo), (_, f), (_, up) in
               zip(chart.lower, chart.forecast, chart.upper, strict=True))  # fmt: skip


def test_twelve_months_is_too_short_for_seasonality() -> None:
    frame = fx.monthly_series(12)
    # the schema floor of 20 rows would hide the date column of a 12-row table
    schema, shape = fx.prepare(frame, min_non_null=5)
    assert shape.shape.value == "time_series"
    item = run_forecast(frame, schema, shape, target="revenue", config=CONFIG)
    assert item.status == "not_run"
    assert "too short to model seasonality" in (item.reason or "").lower()


def test_no_time_axis_means_no_forecast() -> None:
    frame = fx.driver_table()
    schema, shape = fx.prepare(frame)
    item = run_forecast(frame, schema, shape, target="sales", config=CONFIG)
    assert item.status == "not_run" and "date or period" in (item.reason or "")


# --- M7 -----------------------------------------------------------------------------


def test_piecewise_data_finds_the_planted_breakpoint() -> None:
    frame = fx.bend_table()
    schema, shape = fx.prepare(frame)
    item = run_threshold(frame, schema, shape, target="y", variable="x", config=CONFIG)
    assert item.status == "ok", item.sentence
    bend = float(item.values["bend_at"])  # type: ignore[arg-type]
    assert abs(bend - fx.PLANTED_BEND) < 0.8
    assert float(item.values["bend_range_low"]) <= fx.PLANTED_BEND  # type: ignore[arg-type]
    assert float(item.values["bend_range_high"]) >= fx.PLANTED_BEND  # type: ignore[arg-type]
    assert item.lift is not None and item.lift > CONFIG.lift_floor
    assert float(item.values["slope_above"]) > 1.5  # type: ignore[arg-type]


def test_a_straight_relationship_has_no_threshold() -> None:
    frame = fx.driver_table()
    frame = frame.assign(sales_line=2 * frame["ad_spend"] + frame["footfall"] * 0)  # noqa: F841
    schema, shape = fx.prepare(frame)
    item = run_threshold(frame, schema, shape, target="sales", variable="footfall", config=CONFIG)
    assert item.status == "no_lift"
    assert item.sentence.startswith("No threshold")


# --- runner -------------------------------------------------------------------------


@pytest.mark.slow
def test_default_plan_runs_each_applicable_analysis_and_is_reproducible() -> None:
    frame = fx.driver_table()
    schema, shape = fx.prepare(frame)
    first = compute_measured(frame, schema, shape, config=CONFIG)
    second = compute_measured(frame, schema, shape, config=CONFIG)
    kinds = [i.kind for i in first.items]
    assert kinds[0] == "driver_regression"
    assert {"driver_classification", "segments", "anomalies"} <= set(kinds)
    assert first.version == MEASURED_VERSION and first.seed == CONFIG.seed
    assert {e.column for e in first.excluded} >= {"row_id"}
    strip = lambda a: [i.model_dump() for i in a.items]  # noqa: E731
    assert strip(first) == strip(second)


def test_explicit_requests_run_exactly_those_analyses() -> None:
    frame = fx.bend_table()
    schema, shape = fx.prepare(frame)
    result = compute_measured(
        frame,
        schema,
        shape,
        config=CONFIG,
        requests=[
            MeasuredRequest(task="threshold", target="y", features=["x"]),
            MeasuredRequest(task="driver_regression", target="missing"),
        ],
    )
    assert [i.kind for i in result.items] == ["threshold", "driver_regression"]
    assert result.items[0].status == "ok"
    assert result.items[1].status == "not_run"


def test_large_tables_are_sampled_with_the_logged_seed() -> None:
    frame = fx.driver_table(n=300)
    schema, shape = fx.prepare(frame)
    small = fx.fast_config(max_rows=100)
    result = compute_measured(
        frame, schema, shape, config=small,
        requests=[MeasuredRequest(task="driver_regression", target="sales")],
    )  # fmt: skip
    assert result.sampled_rows == 100 and result.n_rows == 300
    assert result.items[0].n_rows <= 100


def test_a_spent_time_budget_skips_the_remaining_analyses_visibly() -> None:
    frame = fx.driver_table()
    schema, shape = fx.prepare(frame)
    tight = fx.fast_config(time_budget_seconds=0.001)
    time.sleep(0.01)
    result = compute_measured(frame, schema, shape, config=tight)
    assert result.items and all(i.status == "not_run" for i in result.items)
    assert all("time budget" in (i.reason or "") for i in result.items)


def test_one_failing_analysis_does_not_hide_the_others(monkeypatch: pytest.MonkeyPatch) -> None:
    from pramana.analysis.measured import runner

    def boom(*args: object, **kwargs: object) -> MeasuredItem:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(runner, "run_segments", boom)
    frame = fx.three_blobs()
    schema, shape = fx.prepare(frame)
    result = compute_measured(
        frame, schema, shape, config=CONFIG,
        requests=[MeasuredRequest(task="segments"), MeasuredRequest(task="anomalies")],
    )  # fmt: skip
    assert result.items[0].status == "not_run"
    assert "secret detail" not in (result.items[0].reason or "")
    assert result.items[1].kind == "anomalies"


# --- default plan, shapes, targets --------------------------------------------------


def test_a_single_measure_time_series_is_forecast_by_the_default_plan() -> None:
    frame = fx.monthly_series(48)
    schema, shape = fx.prepare(frame)
    result = compute_measured(frame, schema, shape, config=CONFIG)
    forecasts = [i for i in result.items if i.kind == "forecast"]
    assert len(forecasts) == 1 and forecasts[0].status == "ok"
    assert forecasts[0].model_score < forecasts[0].baseline_score  # type: ignore[operator]


def test_default_target_prefers_the_packs_measure_roles() -> None:
    frame = fx.driver_table()
    schema, shape = fx.prepare(frame)
    roles = {"footfall": "traffic", "ad_spend": "spend", "sales": "amount"}
    chosen = pick_target(frame, schema, shape, CONFIG, roles, ["amount"])
    assert chosen == "sales"
    assert pick_target(frame, schema, shape, CONFIG, roles, []) in {"sales", "ad_spend", "footfall"}


def test_transactions_are_not_modelled_row_by_row_against_time() -> None:
    import numpy as np

    rng = np.random.default_rng(9)
    n = 240
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=n, freq="D")
            .strftime("%Y-%m-%d")
            .tolist()[: n // 4]
            * 4,
            "amount": rng.normal(100, 10, n),
            "units": rng.normal(10, 2, n),
        }
    )
    schema, shape = fx.prepare(frame)
    assert shape.shape.value == "transactions"
    for task in ("driver_regression", "threshold"):
        result = compute_measured(
            frame, schema, shape, config=CONFIG,
            requests=[MeasuredRequest(task=task, target="amount", features=["units"])],
        )  # fmt: skip
        assert result.items[0].status == "not_run"
        assert "transactions" in (result.items[0].reason or "")


def test_adjusted_and_threshold_results_too_good_to_be_true_are_withheld() -> None:
    strict = fx.fast_config(too_good_cutoff=0.6)
    frame = _adjusted_frame(redundant=False)
    schema, shape = fx.prepare(frame)
    adjusted = run_adjusted(
        frame, schema, shape, target="y", variable="x", controls=["c"], config=strict
    )
    assert adjusted.status == "withheld" and adjusted.model_score is None
    bend = fx.bend_table()
    schema, shape = fx.prepare(bend)
    threshold = run_threshold(bend, schema, shape, target="y", variable="x", config=strict)
    assert threshold.status == "withheld" and threshold.lift is None
    assert threshold.values["withheld_score"] is not None


# --- wording and numbers ------------------------------------------------------------


def _gallery() -> list[MeasuredItem]:
    """One item of every kind and status, from planted tables."""
    items: list[MeasuredItem] = []
    plans = [
        (
            fx.driver_table(),
            [
                MeasuredRequest(task="driver_regression", target="sales"),
                MeasuredRequest(task="driver_regression", target="noise_target"),
                MeasuredRequest(task="driver_classification", target="is_high"),
                MeasuredRequest(task="driver_regression", target="missing"),
            ],
        ),
        (fx.leaky_table(), [MeasuredRequest(task="driver_regression", target="revenue")]),
        (fx.three_blobs(), [MeasuredRequest(task="segments")]),
        (fx.no_clusters(), [MeasuredRequest(task="segments")]),
        (fx.outlier_table(), [MeasuredRequest(task="anomalies")]),
        (fx.bend_table(), [MeasuredRequest(task="threshold", target="y", features=["x"])]),
        (fx.monthly_series(48), [MeasuredRequest(task="forecast", target="revenue")]),
        (fx.monthly_series(12), [MeasuredRequest(task="forecast", target="revenue")]),
    ]
    for frame, requests in plans:
        schema, shape = fx.prepare(frame, min_non_null=5)
        items += compute_measured(frame, schema, shape, config=CONFIG, requests=requests).items
    adjusted = _adjusted_frame(redundant=False)
    schema, shape = fx.prepare(adjusted)
    for frame in (adjusted, _adjusted_frame(redundant=True)):
        items.append(
            run_adjusted(
                frame, schema, shape, target="y", variable="x", controls=["c"], config=CONFIG
            )
        )
    items.append(
        run_adjusted(adjusted, schema, shape, target="y", variable="x", controls=[], config=CONFIG)
    )
    strict = fx.fast_config(too_good_cutoff=0.6)
    items.append(
        run_adjusted(
            adjusted, schema, shape, target="y", variable="x", controls=["c"], config=strict
        )
    )
    return items


@pytest.fixture(scope="module")
def gallery() -> list[MeasuredItem]:
    return _gallery()


@pytest.mark.slow
def test_every_kind_and_status_is_in_the_gallery(gallery: list[MeasuredItem]) -> None:
    assert {i.status for i in gallery} == {"ok", "no_lift", "withheld", "not_run"}
    assert {i.kind for i in gallery} == {
        "driver_regression",
        "driver_classification",
        "adjusted_association",
        "segments",
        "anomalies",
        "forecast",
        "threshold",
    }


@pytest.mark.slow
def test_no_text_uses_causal_or_universal_wording(gallery: list[MeasuredItem]) -> None:
    for item in gallery:
        texts = [item.title, item.sentence, item.reason or "", *(e.reason for e in item.leakage)]
        for text in texts:
            assert not _matched_terms(text, CAUSAL_TERMS), text
            assert not _matched_terms(text, UNIVERSAL_TERMS), text
        assert item.level == "measured"


_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")


def _stored_numbers(item: MeasuredItem) -> list[float]:
    found: list[float] = []

    def add(value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return
        found.extend([float(value), abs(float(value)), float(value) * 100])

    for field in ("baseline_score", "model_score", "lift", "spread", "n_rows", "models_tried"):
        add(getattr(item, field))
    for value in item.values.values():
        add(value)
    for entry in item.table:
        for value in entry.values():
            add(value)
    return found


@pytest.mark.slow
def test_every_number_in_a_sentence_is_a_stored_number(gallery: list[MeasuredItem]) -> None:
    for item in gallery:
        names = " ".join([item.title, item.split, item.target or "", *item.features])
        allowed = {t for t in _NUMBER.findall(names)}
        stored = _stored_numbers(item)
        for token in _NUMBER.findall(item.sentence):
            places = len(token.split(".")[1]) if "." in token else 0
            matched = token in allowed or any(f"{v:.{places}f}" == token for v in stored)
            assert matched, f"{token!r} in {item.id}: {item.sentence}"


def test_a_whole_number_measure_distinct_per_row_is_not_an_identifier() -> None:
    import numpy as np
    import pandas as pd

    from pramana.analysis import infer_schema, load_config
    from pramana.analysis.measured.config import load_measured_config
    from pramana.analysis.measured.leakage import _is_identifier

    rng = np.random.default_rng(1)
    frame = pd.DataFrame(
        {
            "revenue": rng.choice(np.arange(10_000, 900_000), size=300, replace=False),
            "invoice_no": np.arange(1, 301),
            "row_counter": np.arange(5000, 5300),
        }
    )
    schema = infer_schema(frame, load_config().schema_inference)
    config = load_measured_config()
    assert not _is_identifier(frame, schema, "revenue", config)
    assert _is_identifier(frame, schema, "invoice_no", config)
    assert _is_identifier(frame, schema, "row_counter", config)


def test_beating_a_baseline_worse_than_a_flat_line_is_not_skill() -> None:
    """Held-out R² below zero is no skill even when the baseline is lower still."""
    import numpy as np
    import pandas as pd

    from pramana.analysis import infer_schema, load_config
    from pramana.analysis.measured import compute_measured
    from pramana.analysis.measured.models import MeasuredRequest
    from pramana.analysis.shape import classify_shape

    rng = np.random.default_rng(4)
    rows = []
    for e in range(10):
        level = rng.normal(0, 5)
        for m in range(24):
            rows.append(
                {
                    "month": (pd.Timestamp("2022-01-01") + pd.DateOffset(months=m)).strftime(
                        "%Y-%m-%d"
                    ),
                    "region": f"r{e}",
                    "sales": level + rng.normal(),
                    "noise": rng.normal(),
                }
            )
    frame = pd.DataFrame(rows)
    schema = infer_schema(frame, load_config().schema_inference)
    shape = classify_shape(frame, schema)
    result = compute_measured(
        frame,
        schema,
        shape,
        requests=[MeasuredRequest(task="driver_regression", target="sales", features=["noise"])],
    )
    item = result.items[0]
    assert item.status == "no_lift", item.sentence
    assert "beats" not in item.sentence


def test_transactions_with_an_entity_are_modelled_on_period_totals_held_out_whole() -> None:
    import numpy as np

    rng = np.random.default_rng(4)
    rows = []
    for month in pd.date_range("2022-01-01", periods=36, freq="MS"):
        for region in ("North", "South", "East", "West"):
            for _ in range(3):
                units = rng.uniform(5, 15)
                ads = rng.uniform(1, 5)
                rows.append(
                    {
                        "date": month.strftime("%Y-%m-%d"),
                        "region": region,
                        "units": units,
                        "ad_spend": ads,
                        "amount": 8 * units + 12 * ads + rng.normal(0, 25),
                    }
                )
    frame = pd.DataFrame(rows)
    schema, shape = fx.prepare(frame)
    assert shape.shape.value == "transactions" and shape.entity_column == "region"
    result = compute_measured(
        frame, schema, shape, config=CONFIG,
        requests=[MeasuredRequest(task="driver_regression", target="amount",
                                  features=["units", "ad_spend"])],
    )  # fmt: skip
    item = result.items[0]
    assert item.status == "ok", item.reason
    assert "totals per month and region" in item.sentence
    assert "never split between training and testing" in item.sentence
    assert "entity" in item.split.lower()  # folds hold out whole regions
