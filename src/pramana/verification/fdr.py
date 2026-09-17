"""Benjamini-Hochberg FDR correction -- applied ONCE per run, across every hypothesis.

Why this module exists
----------------------
An agent that proposes forty candidate insights and tests each at alpha = 0.05 expects
two false positives by construction. Reporting them as findings is not a bug in any
single test; it is the multiple-comparisons problem, and it is precisely how a
"self-evolving" agent poisons its own memory with noise it mistook for signal.

BH controls the FALSE DISCOVERY RATE -- the expected share of reported findings that
are false -- rather than the family-wise error rate. That is the right trade for
exploratory analysis: Bonferroni would hold the probability of ANY false positive to
alpha and, on a family of forty, reject nearly everything true along with it.

Once per run, not once per insight
----------------------------------
`apply_bh` corrects whatever list it is handed, in a single call (AGENTS.md 3.2). It
knows nothing about runs, and that is deliberate -- it cannot enforce the rule itself,
so the rule lives with the caller: the gateway collects every raw p-value in the batch,
calls this once, and only then issues verdicts. Calling it per insight would return
`q == p` every time and silently disable the correction while still looking corrected.

A direct consequence, which reviewers do probe: a claim's verdict depends on what else
was tested alongside it. p = 0.01 survives in a family of two and does not in a family
of fifty. That is not a flaw in the method, it is the method working -- and it is why
the proof object records `bh_family_id` and `n_hypotheses_in_batch`.

The implementation is ours rather than statsmodels' so the correction is auditable line
by line; `test_fdr.py` pins it against `multipletests(method="fdr_bh")`, including under
heavy ties.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 3
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike


def _validated_p_values(p_values: ArrayLike) -> np.ndarray:
    """`p_values` as a float array, or a refusal naming what was wrong with it.

    Guarantees: every returned value is finite and in (0, 1]. Exact zero is refused
    along with the out-of-range cases: a permutation p-value is add-one floored at
    `1 / (B + 1)`, so a zero did not come from the vetted library and correcting it
    would launder a fabricated number into a q-value.
    """
    array = np.asarray(p_values, dtype=float).ravel()
    if array.size == 0:
        return array
    if np.any(np.isnan(array)):
        raise ValueError(
            "p_values contains NaN: a crashed or malformed test produces no p-value, and "
            "a missing result must fail closed upstream rather than enter the BH family"
        )
    if not np.all(np.isfinite(array)):
        raise ValueError("p_values contains a non-finite value")
    if np.any(array <= 0.0):
        raise ValueError(
            f"p_values must be strictly positive; got a minimum of {array.min()}. A "
            f"permutation p-value is floored at 1/(B+1), so zero means the number did "
            f"not come from the vetted stats library."
        )
    if np.any(array > 1.0):
        raise ValueError(f"p_values must be at most 1.0; got a maximum of {array.max()}")
    return array


def _validated_alpha(alpha: float) -> float:
    """Alpha, or a refusal. Strictly between 0 and 1 -- both endpoints are degenerate.

    This function takes alpha as an argument and never as a literal: the configured
    value lives in `configs/verification.yaml` and reaches here through
    `config.statistics.alpha` (AGENTS.md 3.3).
    """
    if not np.isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ValueError(
            f"alpha must be strictly between 0 and 1; got {alpha}. At 0 nothing can ever "
            f"be reported and at 1 nothing is ever corrected."
        )
    return float(alpha)


def apply_bh(p_values: ArrayLike, alpha: float) -> list[float]:
    """Benjamini-Hochberg q-values for one family of hypotheses.

    `q_i = min over j >= rank(i) of (n / j) * p_(j)`, clipped at 1.0 -- the step-up
    procedure with the cumulative-minimum enforcement of monotonicity.

    Guarantees:
      * output order matches input order, so the caller can zip q-values back against
        insight_ids without a second data structure;
      * `q >= p` for every element, and every q lands in (0, 1];
      * q-values are monotone in p: a larger p never receives a smaller q. Omitting the
        cumulative minimum is the classic BH bug -- it lets a weaker claim be reported
        while a stronger one is not;
      * an empty family returns an empty list (a run where every claim was screened out
        is legitimate, not a crash), and a single hypothesis is returned uncorrected,
        since `n / 1 * p = p`.

    `alpha` does not change the q-values -- BH q-values are alpha-free by construction.
    It is taken here so that an invalid threshold is refused at the same point the
    family is corrected, rather than surfacing later at verdict time.
    """
    _validated_alpha(alpha)
    array = _validated_p_values(p_values)
    n = array.size
    if n == 0:
        return []

    order = np.argsort(array, kind="stable")
    ranks = np.arange(1, n + 1, dtype=float)
    scaled = array[order] * n / ranks
    # Right-to-left running minimum: each q is capped by every less-significant one,
    # which is what makes the sequence monotone. Ties need no special handling -- an
    # equal pair scaled by different ranks is flattened by this same step.
    monotone = np.minimum.accumulate(scaled[::-1])[::-1]

    q_values = np.empty(n, dtype=float)
    q_values[order] = np.minimum(monotone, 1.0)
    return [float(q) for q in q_values]


def bh_rejections(q_values: Sequence[float], alpha: float) -> list[bool]:
    """Which hypotheses clear the FDR threshold, in input order.

    The rule is STRICT (`q < alpha`), matching the gate in `evidence.py`: a q-value
    sitting exactly on alpha is not evidence, and the two places that compare a q
    against alpha must not disagree about the boundary.

    This is a convenience for reporting and for tests. The gateway's verdicts come
    from `evaluate_gate`, which weighs the effect size as well -- significance alone
    was never sufficient for a PASS (AGENTS.md 3.5).
    """
    threshold = _validated_alpha(alpha)
    return [bool(float(q) < threshold) for q in q_values]
