"""Hand-built tables whose Exact answers are known in advance (PLAN §14 interim gate).

Every expected number in the tests is derived here by arithmetic a reader can redo,
never by running the code under test.
"""

from __future__ import annotations

import pandas as pd

MONTHS = [f"2025-{m:02d}-01" for m in range(1, 13)]
REGION_BASE = {"North": 100.0, "South": 80.0, "East": 60.0, "West": 40.0}
REGION_STEP = {"North": 10.0, "South": 1.0, "East": 1.0, "West": 1.0}
COST_SHARE = 0.6
SPIKE_REGION, SPIKE_MONTH, SPIKE = "West", "2025-03-01", 500.0


def finance_year() -> pd.DataFrame:
    """12 months x 4 regions. North grows 10 a month, the others 1; one cost spike.

    revenue(region, m) = base + step * m for m = 0..11
    cost = 0.6 * revenue, plus 500 for West in March
    profit = revenue - cost (an accounting identity the data-quality check must find)
    """
    rows = []
    for m, month in enumerate(MONTHS):
        for region, base in REGION_BASE.items():
            revenue = base + REGION_STEP[region] * m
            cost = COST_SHARE * revenue + (
                SPIKE if (region, month) == (SPIKE_REGION, SPIKE_MONTH) else 0.0
            )
            rows.append(
                {
                    "month": month,
                    "region": region,
                    "revenue": revenue,
                    "cost": cost,
                    "profit": revenue - cost,
                }
            )
    return pd.DataFrame(rows)


def revenue_total(month_index: int) -> float:
    return sum(base + REGION_STEP[r] * month_index for r, base in REGION_BASE.items())


def finance_two_years() -> pd.DataFrame:
    """24 months x 2 regions with a December peak.

    North = 100 + m/10 and South = 100 - m/10, so the monthly total is 200 (300 in
    December, when both regions get +50) while each column still varies.
    """
    rows = []
    for year in (2024, 2025):
        for m in range(1, 13):
            for region, sign in (("North", 1.0), ("South", -1.0)):
                rows.append(
                    {
                        "month": f"{year}-{m:02d}-01",
                        "region": region,
                        "revenue": 100.0 + sign * m / 10 + (50.0 if m == 12 else 0.0),
                    }
                )
    return pd.DataFrame(rows)


N_HEALTH = 40
N_OBESE = 10
OBESE_WEIGHT, OTHER_WEIGHT = 3.0, 1.0


def health_sample(with_weights: bool = True) -> pd.DataFrame:
    """40 respondents, NHANES names. 10 have BMI >= 30 and carry survey weight 3.

    Unweighted obesity share: 10 / 40 = 25%.
    Weighted: (10 * 3) / (10 * 3 + 30 * 1) = 50%.
    """
    rows = []
    for i in range(N_HEALTH):
        obese = i < N_OBESE
        rows.append(
            {
                "SEQN": 1000 + i,
                "RIDAGEYR": 20 + (i * 3) % 60,
                "RIAGENDR": 1 if i % 2 == 0 else 2,
                "BMXBMI": 32.0 + (i % 5) if obese else 22.0 + (i % 6),
                "WTMEC2YR": OBESE_WEIGHT if obese else OTHER_WEIGHT,
            }
        )
    frame = pd.DataFrame(rows)
    return frame if with_weights else frame.drop(columns=["WTMEC2YR"])


def transactions() -> pd.DataFrame:
    """Many invoices per day, repeated customers: a transactions table."""
    rows = []
    for day in range(1, 29):
        for k in range(6):
            rows.append(
                {
                    "invoice_date": f"2025-02-{day:02d}",
                    "customer": f"C{(day + k) % 3}",
                    "amount": 10.0 + k,
                }
            )
    return pd.DataFrame(rows)


def cross_section() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "height": [150.0 + i for i in range(50)],
            "score": [float(i % 7) for i in range(50)],
            "group": ["a", "b"] * 25,
        }
    )


def time_series() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [f"2024-{m:02d}-01" for m in range(1, 13)]
            + [f"2025-{m:02d}-01" for m in range(1, 13)],
            "sales": [100.0 + i for i in range(24)],
        }
    )
