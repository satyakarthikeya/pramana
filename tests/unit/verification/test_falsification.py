"""Template renderer and generator interface tests.

The renderer is the DEFAULT generator, so these are tests of the production path, not
of a fallback. Two properties matter most: the output is deterministic (or the
`falsification_code` in a proof object is not a reproducible record), and it never
emits code that the import policy would reject (or the gateway fails closed on its
own templates).
"""

from __future__ import annotations

import pytest

from pramana.contracts.enums import ClaimType, TestType
from pramana.verification.config import VerificationConfig, load_config
from pramana.verification.executor.policy import check_imports
from pramana.verification.falsification import templates
from pramana.verification.falsification.generator import (
    generate_from_template,
    get_generator,
)
from tests.fixtures.candidates import (
    TESTABLE_CANDIDATES,
    TRUE_CORRELATION,
    TRUE_GROUP_DIFFERENCE,
    TRUE_TREND,
)


@pytest.fixture(scope="module")
def config() -> VerificationConfig:
    return load_config()


@pytest.mark.parametrize("candidate", TESTABLE_CANDIDATES, ids=lambda c: c.insight_id)
def test_every_testable_candidate_renders(candidate, config: VerificationConfig) -> None:
    program = generate_from_template(candidate, config)
    assert "def falsify(frame)" in program.source
    assert program.test_type is TestType.PERMUTATION
    assert program.generator == "template"


@pytest.mark.parametrize("candidate", TESTABLE_CANDIDATES, ids=lambda c: c.insight_id)
def test_rendered_code_satisfies_the_import_policy(candidate, config: VerificationConfig) -> None:
    """Our own templates must pass the same check generated code does. If they did
    not, the gateway would fail closed on every claim and the failure would look like
    a statistics bug rather than a policy one.
    """
    program = generate_from_template(candidate, config)
    check_imports(program.source, config.executor.allowed_imports)


@pytest.mark.parametrize("candidate", TESTABLE_CANDIDATES, ids=lambda c: c.insight_id)
def test_rendering_is_deterministic(candidate, config: VerificationConfig) -> None:
    """Byte-identical, or the `falsification_code` field is not a reproducible record
    of what ran (AGENTS.md 3.4).
    """
    first = generate_from_template(candidate, config)
    second = generate_from_template(candidate, config)
    assert first.source == second.source


def test_seed_and_permutation_count_come_from_config(config: VerificationConfig) -> None:
    """Never hardcoded in the template (AGENTS.md 3.3)."""
    program = generate_from_template(TRUE_CORRELATION, config)
    assert f"N_PERMUTATIONS = {config.statistics.n_permutations}" in program.source
    assert f"SEED = {config.statistics.seed}" in program.source
    assert f"MIN_OBSERVATIONS = {config.statistics.min_observations}" in program.source


def test_every_template_is_two_sided(config: VerificationConfig) -> None:
    """A one-sided test plus the gate's direction check would use the asserted
    direction twice -- once to halve the p-value, once to gate.
    """
    for candidate in (TRUE_CORRELATION, TRUE_GROUP_DIFFERENCE, TRUE_TREND):
        assert 'alternative="two-sided"' in generate_from_template(candidate, config).source


def test_templates_call_the_vetted_functions(config: VerificationConfig) -> None:
    source = generate_from_template(TRUE_CORRELATION, config).source
    assert "from pramana.verification.stats import" in source
    assert "permutation_test(" in source


def test_reference_group_is_rendered_when_present(config: VerificationConfig) -> None:
    source = generate_from_template(TRUE_GROUP_DIFFERENCE, config).source
    assert "REFERENCE_GROUP = 'urban'" in source


def test_distribution_has_no_template() -> None:
    """Fail-closed, not a generic fallback (SCOPE.md 4 step 8). The admissibility
    screen refuses these earlier; this is the second line of the same defence.
    """
    assert ClaimType.DISTRIBUTION not in templates.SUPPORTED_CLAIM_TYPES
    with pytest.raises(ValueError, match="no falsification template"):
        templates.render(
            insight_id="c-1",
            claim="income is right-skewed",
            claim_type=ClaimType.DISTRIBUTION,
            var_x="income",
            var_y="area",
            n_permutations=1000,
            seed=1,
            min_observations=10,
        )


def test_generator_selection_follows_config(config: VerificationConfig) -> None:
    assert get_generator(config) is generate_from_template


def test_selecting_the_unbuilt_llm_generator_raises(config: VerificationConfig) -> None:
    """Rather than silently falling back to the template: a run that believes it is
    measuring the LLM must not quietly measure something else.
    """
    llm_config = config.model_copy(
        update={"llm": config.llm.model_copy(update={"generator": "llm"})}
    )
    with pytest.raises(NotImplementedError, match="not implemented yet"):
        get_generator(llm_config)
