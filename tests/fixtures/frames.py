"""The toy dataframe: a miniature of the live demo (PROJECT.md 7).

It contains, by construction and from a fixed seed:

  * one strong planted relationship the gate MUST find      (age  ~ bmi)
  * one planted group difference the gate MUST find         (area ~ income)
  * one planted monotonic trend the gate MUST find          (month ~ visits)
  * one FALSE correlation the gate MUST reject              (age ~ decoy)
  * pure-noise columns that must stay null                  (noise_a, noise_b)

`decoy` is the important one. It is a shuffled copy of `bmi`, so it has bmi's exact
marginal distribution and no association with anything at all. It is what a real
false positive looks like: it survives a glance at the summary statistics and dies
under a permutation test. A gate that passes `decoy` is broken no matter what else
it gets right.

Effect sizes are chosen to sit ABOVE the configured floors but BELOW the reference
values in `configs/verification.yaml`, so the fixture exercises the interesting part
of the scale rather than saturating it.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd

#: Fixed so every test in the suite sees the same frame.
DEFAULT_SEED: Final = 20260903
DEFAULT_N_ROWS: Final = 240

#: What was planted, for tests to assert against. Keys are (var_x, var_y).
PLANTED: Final[dict[tuple[str, str], str]] = {
    ("age", "bmi"): "positive correlation",
    ("area", "income"): "group difference, urban higher",
    ("month", "visits"): "positive monotonic trend",
    ("age", "decoy"): "NULL -- decoy is a shuffled copy of bmi",
    ("noise_a", "noise_b"): "NULL -- independent noise",
}


def toy_frame(n_rows: int = DEFAULT_N_ROWS, seed: int = DEFAULT_SEED) -> pd.DataFrame:
    """Build the toy frame. Deterministic for a given `(n_rows, seed)`.

    Guarantees: `decoy` is a permutation of `bmi` -- identical marginal, zero
    association -- and `noise_a`/`noise_b` are independent draws. Any association the
    gate reports between those pairs is a false positive by construction.
    """
    rng = np.random.default_rng(seed)

    # Planted correlation: bmi tracks age with substantial noise on top.
    age = rng.normal(45.0, 14.0, size=n_rows)
    bmi = 18.0 + 0.16 * age + rng.normal(0.0, 4.0, size=n_rows)

    # Planted group difference: urban incomes sit higher, with heavy overlap.
    area = rng.choice(["urban", "rural"], size=n_rows, p=[0.55, 0.45])
    income = rng.lognormal(mean=10.0, sigma=0.55, size=n_rows)
    income = np.where(area == "urban", income * 1.9, income)

    # Planted trend: visits rise through the year, on top of noise.
    month = rng.integers(1, 13, size=n_rows).astype(float)
    visits = 2.0 + 0.30 * month + rng.normal(0.0, 2.2, size=n_rows)

    # The false correlation: bmi's exact values, association destroyed.
    decoy = rng.permutation(bmi)

    frame = pd.DataFrame(
        {
            "age": age,
            "bmi": bmi,
            "area": area,
            "income": income,
            "month": month,
            "visits": visits,
            "decoy": decoy,
            "noise_a": rng.normal(0.0, 1.0, size=n_rows),
            "noise_b": rng.normal(0.0, 1.0, size=n_rows),
            "region": rng.choice(["north", "south", "east"], size=n_rows),
        }
    )
    return frame
