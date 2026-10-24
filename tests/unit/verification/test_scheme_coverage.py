"""Every (claim type, scheme) pair the gate can assign has a prompt and a template.

A pair missing from either path fails only at run time on that path, so it is checked
here for both: the DeepSeek prompt builds with no placeholder left, and the reference
template compiles with none left either.
"""

from __future__ import annotations

import pytest

from pramana.contracts.enums import ClaimType as C
from pramana.contracts.enums import PermutationScheme as S
from pramana.verification.falsification import prompts, templates
from pramana.verification.schemes import PERIOD_COLUMN, TestPlan
from tests.fixtures.candidates import candidate

ASSIGNABLE = [
    (C.CORRELATION, S.FREE),
    (C.TREND, S.FREE),
    (C.GROUP_DIFFERENCE, S.FREE),
    (C.PERIOD_CHANGE, S.FREE),
    (C.TREND, S.BLOCK_DIFFERENCED),
    (C.CORRELATION, S.BLOCK_DIFFERENCED),
    (C.CORRELATION, S.STRATIFIED),
    (C.GROUP_DIFFERENCE, S.STRATIFIED),
    (C.GROUP_DIFFERENCE, S.CLUSTER),
    (C.PERIOD_CHANGE, S.PAIRED),
    (C.SEASONALITY, S.STRATIFIED),
]
PLACEHOLDERS = (
    "{var_x}",
    "{var_y}",
    "{entity}",
    "{entity_argument}",
    "{structure_columns}",
    "{group_call}",
    "{entity_column}",
)


def _plan(claim_type: C, scheme: S) -> TestPlan | None:
    if scheme is S.FREE and claim_type is not C.PERIOD_CHANGE:
        return None
    return TestPlan(
        scheme=scheme,
        period_column=None if scheme is S.CLUSTER else PERIOD_COLUMN,
        entity_column="region" if scheme in (S.CLUSTER, S.PAIRED) else None,
        block_length=3 if scheme is S.BLOCK_DIFFERENCED else None,
        min_periods=20 if scheme is S.BLOCK_DIFFERENCED else None,
        cycle_length=12 if claim_type is C.SEASONALITY else None,
    )


@pytest.mark.parametrize(("claim_type", "scheme"), ASSIGNABLE)
def test_both_generators_cover_the_pair(claim_type: C, scheme: S) -> None:
    plan = _plan(claim_type, scheme)
    claim = candidate("x", "b tends to differ in this data", claim_type, ["a", "b"])
    _, user = prompts.build_prompt(
        claim, var_x="a", var_y="b", n_permutations=999, seed=1, min_observations=20, plan=plan
    )
    source = templates.render(
        insight_id="x",
        claim="c",
        claim_type=claim_type,
        var_x="a",
        var_y="b",
        n_permutations=999,
        seed=1,
        min_observations=20,
        scheme=scheme,
        period_column=plan.period_column if plan else None,
        entity_column=plan.entity_column if plan else None,
        block_length=plan.block_length if plan else None,
        min_periods=plan.min_periods if plan else None,
        cycle_length=plan.cycle_length if plan else None,
    )
    compile(source, "falsification_program", "exec")
    left = [token for token in PLACEHOLDERS if token in user or token in source]
    assert not left, left
