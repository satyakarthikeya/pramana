"""Known-answer checks for the Skeptic: planted confounds are flagged, clean findings are not."""

from __future__ import annotations

import time
import types

import numpy as np
import pandas as pd
import pytest

from pramana.advisory.config import SkepticConfig, load_advisory_config
from pramana.advisory.findings import Finding
from pramana.advisory.skeptic import review_finding
from pramana.analysis import infer_schema, load_config

N = 600


@pytest.fixture(scope="module")
def config() -> SkepticConfig:
    return load_advisory_config().skeptic


def finding(kind: str, a: str, b: str, **extra: object) -> Finding:
    base = dict(
        insight_id=f"{kind}-{a}-{b}",
        claim="c",
        claim_type=kind,
        variables=(a, b),
        direction=None,
        reference_group=None,
        q_value=0.001,
        p_value=0.0001,
        effect_size=0.5,
        effect_metric="spearman_rho",
        band="medium",
        n=N,
        family_size=5,
        alpha=0.05,
    )
    base.update(extra)
    return Finding(**base)  # type: ignore[arg-type]


def review(frame: pd.DataFrame, f: Finding, config: SkepticConfig):
    schema = infer_schema(frame, load_config().schema_inference)
    return review_finding(f, frame, schema, config)


def test_a_planted_confounder_is_flagged_with_its_numbers(config: SkepticConfig) -> None:
    rng = np.random.default_rng(1)
    z = rng.normal(size=N)
    frame = pd.DataFrame(
        {
            "x": z + rng.normal(scale=0.7, size=N),
            "y": z + rng.normal(scale=0.7, size=N),
            "z": z,
            "noise": rng.normal(size=N),
        }
    )
    result = review(frame, finding("correlation", "x", "y"), config)
    assert result.status == "flagged"
    top = result.caveats[0]
    assert top.control == "z" and top.control_kind == "numeric" and top.n == N
    assert top.before > 0.4 and top.after < 0.15  # z accounts for nearly all of it
    assert top.link_first > 0.5 and top.link_second > 0.5
    assert [c.control for c in result.caveats] == ["z"]  # the noise column is not flagged
    assert "could be a confounder, a step between them, or something that both of them" in top.text
    assert "influence; this table cannot tell which" in top.text
    assert "explain" not in top.text.lower() and "caus" not in top.text.lower()
    assert "significan" not in top.text.lower() and "p-value" not in top.text.lower()
    assert {f.claim_type for f in top.follow_ups} == {"correlation"}
    assert all("next run" in f.sentence for f in top.follow_ups)


def test_a_direct_relationship_with_independent_columns_is_not_flagged(
    config: SkepticConfig,
) -> None:
    rng = np.random.default_rng(2)
    x = rng.normal(size=N)
    frame = pd.DataFrame(
        {
            "x": x,
            "y": x + rng.normal(scale=0.7, size=N),
            "other": rng.normal(size=N),
            "another": rng.normal(size=N),
        }
    )
    result = review(frame, finding("correlation", "x", "y"), config)
    assert result.status == "none_found" and result.caveats == []
    assert result.controls_checked == 2


def test_a_near_duplicate_of_a_claim_column_is_skipped_not_flagged(config: SkepticConfig) -> None:
    rng = np.random.default_rng(3)
    x = rng.normal(size=N)
    frame = pd.DataFrame(
        {
            "x": x,
            "y": x + rng.normal(scale=0.7, size=N),
            "x_copy": x + rng.normal(scale=0.01, size=N),
        }
    )
    result = review(frame, finding("correlation", "x", "y"), config)
    # The only other column is the same measurement, so nothing could be compared.
    assert result.status == "not_checked" and result.skipped_near_duplicates == 1
    assert "same measurement" in (result.reason or "")


def test_a_categorical_confounder_is_flagged(config: SkepticConfig) -> None:
    rng = np.random.default_rng(4)
    site = rng.choice(["a", "b", "c"], N)
    offset = pd.Series(site).map({"a": 0.0, "b": 2.0, "c": 4.0}).to_numpy()
    frame = pd.DataFrame(
        {
            "x": offset + rng.normal(size=N),
            "y": offset + rng.normal(size=N),
            "site": site,
        }
    )
    result = review(frame, finding("correlation", "x", "y"), config)
    assert result.status == "flagged"
    assert result.caveats[0].control == "site" and result.caveats[0].control_kind == "categorical"
    assert result.caveats[0].follow_ups[0].claim_type == "group_difference"


def test_a_group_difference_that_a_numeric_column_accounts_for_is_flagged(
    config: SkepticConfig,
) -> None:
    rng = np.random.default_rng(5)
    age = rng.normal(50, 10, N)
    group = np.where(age + rng.normal(0, 8, N) > 50, "older", "younger")
    frame = pd.DataFrame({"group": group, "outcome": age * 0.5 + rng.normal(0, 6, N), "age": age})
    result = review(frame, finding("group_difference", "group", "outcome"), config)
    assert result.status == "flagged"
    assert result.caveats[0].control == "age" and result.caveats[0].measure == "rank_eta_squared"
    assert result.caveats[0].after < 0.5 * result.caveats[0].before


def test_a_group_difference_with_independent_controls_is_not_flagged(
    config: SkepticConfig,
) -> None:
    rng = np.random.default_rng(6)
    group = rng.choice(["a", "b"], N)
    frame = pd.DataFrame(
        {
            "group": group,
            "outcome": np.where(group == "a", 1.0, 0.0) + rng.normal(size=N),
            "age": rng.normal(50, 10, N),
        }
    )
    assert review(frame, finding("group_difference", "group", "outcome"), config).status == (
        "none_found"
    )


def test_claim_types_that_are_not_covered_are_reported_not_checked_never_clean(
    config: SkepticConfig,
) -> None:
    frame = pd.DataFrame({"x": np.arange(N, dtype=float), "y": np.arange(N, dtype=float)})
    result = review(frame, finding("distribution", "x", "y"), config)
    assert result.status == "not_checked" and "not covered" in (result.reason or "")


def test_too_few_complete_rows_checks_nothing(config: SkepticConfig) -> None:
    rng = np.random.default_rng(7)
    z = rng.normal(size=20)
    frame = pd.DataFrame({"x": z + rng.normal(size=20), "y": z + rng.normal(size=20), "z": z})
    result = review(frame, finding("correlation", "x", "y"), config)
    assert result.controls_checked == 0 and result.caveats == []
    assert result.status == "not_checked" and "enough complete rows" in (result.reason or "")


def test_the_caveat_cap_and_ordering_come_from_config(config: SkepticConfig) -> None:
    rng = np.random.default_rng(8)
    base = rng.normal(size=N)
    frame = pd.DataFrame(
        {
            "x": base + rng.normal(scale=0.5, size=N),
            "y": base + rng.normal(scale=0.5, size=N),
            **{f"z{i}": base + rng.normal(scale=0.4 + 0.1 * i, size=N) for i in range(6)},
        }
    )
    result = review(frame, finding("correlation", "x", "y"), config)
    assert len(result.caveats) <= config.max_caveats_per_finding
    ratios = [c.after / c.before for c in result.caveats]
    assert ratios == sorted(ratios)


def test_a_missing_column_is_reported_not_raised(config: SkepticConfig) -> None:
    frame = pd.DataFrame({"x": np.arange(N, dtype=float), "z": np.arange(N, dtype=float)})
    result = review(frame, finding("correlation", "x", "gone"), config)
    assert result.status == "not_checked"


# ---- second review: honesty about what was and was not checked ---------------------------------
def test_a_finding_with_nothing_comparable_is_never_reported_as_clean(
    config: SkepticConfig,
) -> None:
    rng = np.random.default_rng(21)
    x = rng.normal(size=N)
    alone = pd.DataFrame({"x": x, "y": x + rng.normal(size=N)})
    result = review(alone, finding("correlation", "x", "y"), config)
    assert result.status == "not_checked" and result.controls_checked == 0
    assert "no other usable column" in (result.reason or "")

    group = rng.choice(["a", "b"], N)
    only_categorical = pd.DataFrame(
        {
            "group": group,
            "outcome": np.where(group == "a", 1.0, 0.0) + rng.normal(size=N),
            "site": rng.choice(["p", "q", "r"], N),
        }
    )
    result = review(only_categorical, finding("group_difference", "group", "outcome"), config)
    assert result.status == "not_checked" and "categorical" in (result.reason or "")


def test_a_numeric_column_that_encodes_the_group_is_a_proxy_not_a_flag(
    config: SkepticConfig,
) -> None:
    rng = np.random.default_rng(22)
    group = rng.choice(["a", "b"], N)
    frame = pd.DataFrame(
        {
            "group": group,
            "outcome": np.where(group == "a", 1.0, 0.0) + rng.normal(size=N),
            "gcode": np.where(group == "a", 1.0, 0.0) + rng.normal(scale=0.1, size=N),
        }
    )
    result = review(frame, finding("group_difference", "group", "outcome"), config)
    assert result.caveats == [] and result.skipped_near_duplicates == 1
    assert result.status == "not_checked"


def test_a_categorical_column_is_rechecked_on_the_rows_actually_used(
    config: SkepticConfig,
) -> None:
    rng = np.random.default_rng(23)
    site = np.repeat(["a", "b", "c"], N // 3)
    x = rng.normal(size=N)
    y = x + rng.normal(size=N)
    y[site == "c"] = np.nan
    y[np.flatnonzero(site == "c")[:2]] = 0.5  # level c keeps only 2 usable rows
    frame = pd.DataFrame({"x": x, "y": y, "site": site})
    result = review(frame, finding("correlation", "x", "y"), config)
    assert result.status == "not_checked" and "per level" in (result.reason or "")


def test_the_time_budget_marks_unreached_findings_and_columns_not_checked(
    config: SkepticConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng = np.random.default_rng(24)
    z = rng.normal(size=N)
    frame = pd.DataFrame(
        {
            "z": z,
            "x": z + rng.normal(scale=0.7, size=N),
            "y": z + rng.normal(scale=0.7, size=N),
            "w": rng.normal(size=N),
        }
    )
    schema = infer_schema(frame, load_config().schema_inference)
    expired = review_finding(
        finding("correlation", "x", "y"), frame, schema, config, time.monotonic() - 1
    )
    assert expired.status == "not_checked" and "time budget" in (expired.reason or "")

    clock = iter([0.0, 0.0] + [100.0] * 50)  # start ok, first column ok, then out of time
    monkeypatch.setattr(
        "pramana.advisory.skeptic.time", types.SimpleNamespace(monotonic=lambda: next(clock))
    )
    partial = review_finding(finding("correlation", "x", "y"), frame, schema, config, deadline=10.0)
    assert partial.status == "flagged" and "time budget" in (partial.reason or "")
    assert partial.controls_checked == 1 and partial.caveats[0].control == "z"
