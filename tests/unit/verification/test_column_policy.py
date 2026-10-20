"""W1: generated code may read only the claim's own columns and filter only as stated.

The HMAC stamp proves a number came from our library. It does not prove the library was
handed the right data: LLM-written code could pass another column, or a quietly
filtered subset, and still carry a perfectly valid stamp. `check_columns` is the static
check that closes that gap, and every refusal here is a way of doing exactly that.

Two kinds of test: things that MUST be refused (each a distinct way to read the wrong
data), and things that MUST pass (the shipped templates, and the minimal honest forms),
because a check that refuses its own generator is not a check, it is an outage.
"""

from __future__ import annotations

import pytest

from pramana.contracts.enums import ClaimType
from pramana.verification.config import VerificationConfig
from pramana.verification.executor.policy import ColumnPolicyViolation, check_columns
from pramana.verification.executor.runner import execute
from pramana.verification.falsification.generator import (
    FalsificationProgram,
    generate_from_template,
)
from tests.fixtures.candidates import (
    TESTABLE_CANDIDATES,
)
from tests.fixtures.config import load_pinned_config
from tests.fixtures.frames import toy_frame

VARS = ("age", "bmi")


def _module(body: str) -> str:
    """A generated-looking module whose `falsify` has the given body."""
    indented = "\n".join("    " + line for line in body.strip().splitlines())
    return (
        "import numpy as np\n"
        "import pandas as pd\n"
        "VAR_X = 'age'\n"
        "VAR_Y = 'bmi'\n"
        f"def falsify(frame):\n{indented}\n"
    )


def _passes(body: str, claim_type: ClaimType = ClaimType.CORRELATION) -> None:
    check_columns(_module(body), VARS, claim_type)


def _refused(body: str, claim_type: ClaimType = ClaimType.CORRELATION) -> str:
    with pytest.raises(ColumnPolicyViolation) as caught:
        check_columns(_module(body), VARS, claim_type)
    return str(caught.value)


# --- the shipped templates must pass ---------------------------------------


@pytest.fixture(scope="module")
def config() -> VerificationConfig:
    return load_pinned_config()


@pytest.mark.parametrize("candidate", TESTABLE_CANDIDATES, ids=lambda c: c.insight_id)
def test_every_shipped_template_passes_its_own_column_check(candidate, config) -> None:
    program = generate_from_template(candidate, config)
    check_columns(program.source, (program.var_x, program.var_y), candidate.claim_type)


# --- reading only the claim's columns passes -------------------------------


def test_pair_selected_by_list_passes() -> None:
    _passes("pair = frame[['age', 'bmi']].dropna()\nreturn pair")


def test_pair_selected_by_module_constants_passes() -> None:
    _passes("pair = frame[[VAR_X, VAR_Y]].apply(pd.to_numeric, errors='coerce').dropna()")


def test_single_column_in_the_claim_passes() -> None:
    _passes("x = frame['age'].to_numpy(dtype=float)\ny = frame[VAR_Y].to_numpy(dtype=float)")


def test_loc_with_claim_columns_and_all_rows_passes() -> None:
    _passes("pair = frame.loc[:, ['age', 'bmi']]")


def test_helper_in_the_same_module_may_receive_the_frame() -> None:
    source = (
        "VAR_X = 'age'\nVAR_Y = 'bmi'\n"
        "def _pair(frame):\n    return frame[[VAR_X, VAR_Y]].dropna()\n"
        "def falsify(frame):\n    return _pair(frame)\n"
    )
    check_columns(source, VARS, ClaimType.CORRELATION)


# --- an extra column is refused --------------------------------------------


def test_extra_column_in_a_list_is_refused() -> None:
    assert "income" in _refused("pair = frame[['age', 'bmi', 'income']]")


def test_extra_single_column_is_refused() -> None:
    assert "income" in _refused("z = frame['income']")


def test_extra_column_hidden_behind_a_module_constant_is_refused() -> None:
    source = (
        "EXTRA = 'income'\n"
        "def falsify(frame):\n    return frame[['age', 'bmi', EXTRA]]\n"
    )
    with pytest.raises(ColumnPolicyViolation, match="income"):
        check_columns(source, VARS, ClaimType.CORRELATION)


def test_extra_column_through_loc_is_refused() -> None:
    assert "income" in _refused("z = frame.loc[:, ['age', 'income']]")


def test_attribute_access_to_a_column_is_refused() -> None:
    _refused("z = frame.income")


def test_get_is_refused() -> None:
    _refused("z = frame.get('income')")


def test_a_column_name_that_cannot_be_resolved_is_refused() -> None:
    """Fail closed: a label built at runtime could be anything."""
    _refused("name = 'inc' + 'ome'\nz = frame[name]")


def test_reading_every_column_at_once_is_refused() -> None:
    _refused("z = frame.to_numpy()")
    _refused("z = frame.copy()")
    _refused("z = list(frame.columns)")
    _refused("df = frame\nz = df['income']")


def test_passing_the_frame_to_an_unknown_function_is_refused() -> None:
    _refused("z = np.asarray(frame)")


def test_dropping_columns_instead_of_selecting_is_refused() -> None:
    _refused("pair = frame.drop(columns=['income'])")


# --- a row filter the claim does not state is refused ----------------------


def test_boolean_mask_on_the_frame_is_refused() -> None:
    _refused("pair = frame[frame['age'] > 60][['age', 'bmi']]")


def test_query_is_refused() -> None:
    _refused("pair = frame[['age', 'bmi']].query('age > 60')")


@pytest.mark.parametrize(
    "call",
    ["head(100)", "tail(100)", "sample(frac=0.5)", "nlargest(50, 'age')", "drop_duplicates()"],
)
def test_row_selecting_methods_are_refused(call: str) -> None:
    _refused(f"pair = frame[['age', 'bmi']].{call}")


def test_positional_row_slicing_is_refused() -> None:
    _refused("pair = frame[['age', 'bmi']].iloc[:100]")


def test_slicing_or_masking_the_extracted_arrays_is_refused() -> None:
    _refused("x = frame['age'].to_numpy()\nx = x[x > 0]")
    _refused("x = frame['age'].to_numpy()\nx = x[:50]")


def test_row_mask_in_loc_is_refused_for_a_non_group_claim() -> None:
    _refused("pair = frame[['age', 'bmi']]\nz = pair.loc[pair['age'] > 60, 'bmi']")


def test_group_split_on_the_grouping_column_passes_for_a_group_claim() -> None:
    """Selecting the rows of one level of the claim's grouping column IS the claim."""
    body = (
        "cols = frame[['age', 'bmi']].dropna()\n"
        "for name in ['a', 'b']:\n"
        "    g = cols.loc[cols['age'].astype(str) == name, 'bmi']"
    )
    _passes(body, ClaimType.GROUP_DIFFERENCE)


def test_group_split_on_the_value_column_is_refused() -> None:
    """Comparing the OUTCOME column is a filter on the thing being tested."""
    body = "cols = frame[['age', 'bmi']]\ng = cols.loc[cols['bmi'] > 25, 'bmi']"
    _refused(body, ClaimType.GROUP_DIFFERENCE)


def test_group_split_is_not_available_to_a_correlation_claim() -> None:
    body = (
        "cols = frame[['age', 'bmi']]\n"
        "g = cols.loc[cols['age'].astype(str) == 'a', 'bmi']"
    )
    _refused(body, ClaimType.CORRELATION)


# --- malformed source fails closed -----------------------------------------


def test_unparseable_source_is_refused() -> None:
    with pytest.raises(ColumnPolicyViolation):
        check_columns("def falsify(frame:", VARS, ClaimType.CORRELATION)


def test_source_without_falsify_is_refused() -> None:
    with pytest.raises(ColumnPolicyViolation, match="falsify"):
        check_columns("x = 1\n", VARS, ClaimType.CORRELATION)


# --- wired into the executor ------------------------------------------------


def _program(source: str) -> FalsificationProgram:
    from pramana.contracts.enums import TestType

    return FalsificationProgram(
        insight_id="c-columns",
        claim_type=ClaimType.CORRELATION,
        var_x="age",
        var_y="bmi",
        test_type=TestType.PERMUTATION,
        n_permutations=1000,
        seed=0,
        source=source,
        generator="llm",
    )


def test_executor_refuses_a_program_reading_an_extra_column_before_running_it(config) -> None:
    source = _module("pair = frame[['age', 'bmi', 'income']]\nreturn {}")
    result = execute(_program(source), toy_frame(), config)
    assert not result.ok
    assert result.payload is None
    assert "column policy violation" in (result.failure_reason or "")
    assert "income" in (result.failure_reason or "")


def test_integer_only_iloc_reads_a_scalar_and_is_not_a_row_filter() -> None:
    """`pair.corr().iloc[0, 1]` is the standard way to read one value out of a 2x2."""
    _passes("pair = frame[['age', 'bmi']].dropna()\nr = pair.corr(method='spearman').iloc[0, 1]")
    _passes("pair = frame[['age', 'bmi']]\nv = pair.iat[0, 1]")


def test_iloc_with_a_slice_or_a_name_is_still_refused() -> None:
    _refused("pair = frame[['age', 'bmi']].iloc[:100]")
    _refused("rows = [0, 1]\npair = frame[['age', 'bmi']].iloc[rows]")
