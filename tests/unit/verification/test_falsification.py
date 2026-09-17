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
from pramana.verification.falsification import generator, templates
from pramana.verification.falsification.generator import (
    FalsificationProgram,
    GeneratorError,
    generate_from_llm,
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


# --- LLM path doubles -----------------------------------------------------
#
# The resample count and seed are substituted from the live config rather than
# written here, so these fixtures keep working when `configs/verification.yaml`
# changes and never become a second, competing source of truth (AGENTS.md 3.3).

_N = "__N_PERMUTATIONS__"
_S = "__SEED__"
_M = "__MIN_OBSERVATIONS__"


def _llm_config(config: VerificationConfig) -> VerificationConfig:
    """The same config with the LLM generator selected."""
    return config.model_copy(
        update={"llm": config.llm.model_copy(update={"generator": "llm"})}
    )


def _responds(template: str):
    """A `_call_deepseek` double returning `template` with the config values filled in."""

    def responder(system: str, user: str, config: VerificationConfig) -> str:
        return (
            template.replace(_N, str(config.statistics.n_permutations))
            .replace(_S, str(config.statistics.seed))
            .replace(_M, str(config.statistics.min_observations))
        )

    return responder


def _raises(error: Exception):
    """A `_call_deepseek` double standing in for a failed API call."""

    def responder(system: str, user: str, config: VerificationConfig) -> str:
        raise error

    return responder


#: Well-formed output: parses, defines falsify(frame), carries the configured seed
#: and resample count, and imports only what the whitelist permits.
_VALID_LLM_MODULE = f'''```python
"""Falsification test written by the model."""

import pandas as pd

from pramana.verification.stats import permutation_test, spearman_rho

VAR_X = 'age'
VAR_Y = 'bmi'
N_PERMUTATIONS = {_N}
SEED = {_S}
MIN_OBSERVATIONS = {_M}


def falsify(frame):
    pair = frame[[VAR_X, VAR_Y]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(pair) < MIN_OBSERVATIONS:
        raise ValueError("too few usable rows to conclude anything")
    x = pair[VAR_X].to_numpy(dtype=float)
    y = pair[VAR_Y].to_numpy(dtype=float)
    result = permutation_test(
        x, y, spearman_rho,
        n_permutations=N_PERMUTATIONS, seed=SEED, alternative="two-sided",
    )
    return {{
        "p_value": result.p_value,
        "effect_size": result.statistic,
        "effect_metric": "spearman_rho",
        "n_observations": int(x.size),
        "seed": result.seed,
        "n_permutations": result.n_permutations,
        "statistic": result.statistic,
        "provenance": result.provenance,
    }}
```'''

#: The failure the sandbox exists for: code that computes its own p-value.
_FORBIDDEN_IMPORT_MODULE = f'''```python
import scipy.stats as st

N_PERMUTATIONS = {_N}
SEED = {_S}


def falsify(frame):
    rho, p = st.spearmanr(frame['age'], frame['bmi'])
    return {{"p_value": p, "effect_size": rho}}
```'''

#: Parses, but the harness would have nothing to call.
_NO_FALSIFY_MODULE = f'''```python
import pandas as pd

N_PERMUTATIONS = {_N}
SEED = {_S}


def helper(frame):
    return frame.shape
```'''

#: A model that quietly reseeded the run. The executor refuses the payload later;
#: this is the earlier, cheaper lock on the same guarantee (AGENTS.md 3.4).
_WRONG_SEED_MODULE = f'''```python
import pandas as pd

from pramana.verification.stats import permutation_test, spearman_rho

N_PERMUTATIONS = {_N}
SEED = 1


def falsify(frame):
    return {{"p_value": 1.0}}
```'''


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


# was: unbuilt generator raises. now: built generator fails closed, never falls back
# silently. The original reasoning still holds and is what the two tests below split
# between them -- "a run that believes it is measuring the LLM must not quietly
# measure something else." Before Phase 6 the only way to honour that was to refuse
# the selection outright; now the generator exists, so the same guarantee is that
# selecting it routes there (test 1) and that its failures stay failures (test 2).


def test_selecting_the_llm_generator_routes_to_the_llm_path(
    config: VerificationConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Selecting `llm` must reach the LLM generator, not fall back to the template."""
    selected = get_generator(_llm_config(config))
    assert selected is not generate_from_template
    assert selected is generate_from_llm

    monkeypatch.setattr(generator, "_call_deepseek", _responds(_VALID_LLM_MODULE))
    program = selected(TRUE_CORRELATION, _llm_config(config))

    assert isinstance(program, FalsificationProgram)
    assert program.generator == "llm"
    assert program.insight_id == TRUE_CORRELATION.insight_id
    assert program.test_type is TestType.PERMUTATION
    assert "def falsify(frame)" in program.source
    # Not the template's output: the LLM condition must not be the template condition
    # wearing a different label.
    assert program.source != generate_from_template(TRUE_CORRELATION, config).source


@pytest.mark.parametrize(
    ("name", "responder"),
    [
        ("api_error", _raises(GeneratorError("DeepSeek request failed"))),
        ("unparseable_output", _responds("I'm sorry, I can't help with that.")),
        ("forbidden_import", _responds(_FORBIDDEN_IMPORT_MODULE)),
        ("no_entry_point", _responds(_NO_FALSIFY_MODULE)),
        ("wrong_seed", _responds(_WRONG_SEED_MODULE)),
    ],
)
def test_llm_generator_fails_closed_and_never_falls_back(
    name: str,
    responder: object,
    config: VerificationConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every LLM failure mode raises, rather than returning template output.

    This is the half of the retired test that must not be lost. An API error, a model
    that answers in prose, and a model that writes code importing scipy are all
    "no falsification test exists for this claim". The gateway can only turn that into
    REJECT / NOT_TESTABLE -- never a PASS, and never a quiet substitution of the
    deterministic renderer, which would make an LLM run measure the template path.
    """
    llm_config = _llm_config(config)
    monkeypatch.setattr(generator, "_call_deepseek", responder)

    with pytest.raises(GeneratorError):
        generate_from_llm(TRUE_CORRELATION, llm_config)


def test_llm_failure_is_catchable_without_catching_everything(
    config: VerificationConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`GeneratorError` is a specific type, so the gateway can record the failure and
    issue a verdict rather than swallowing unrelated bugs along with it.
    """
    monkeypatch.setattr(generator, "_call_deepseek", _responds(_FORBIDDEN_IMPORT_MODULE))
    try:
        generate_from_llm(TRUE_CORRELATION, _llm_config(config))
    except GeneratorError as error:
        assert "import policy" in str(error)
    else:  # pragma: no cover -- the call above must raise
        pytest.fail("a policy-violating module must not produce a program")


def test_missing_api_key_does_not_silently_use_the_template(
    config: VerificationConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The offline default is the TEMPLATE generator, chosen by config. A run that
    asked for the LLM and has no key is a misconfigured run, not a template run.
    """
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(GeneratorError, match="DEEPSEEK_API_KEY"):
        generate_from_llm(TRUE_CORRELATION, _llm_config(config))


def test_a_non_deepseek_provider_is_refused(
    config: VerificationConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AGENTS.md 2 reserves verification for DeepSeek. Swapping in a local model would
    change what a PASS means without changing a single test.
    """
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-used")
    local = config.model_copy(
        update={
            "llm": config.llm.model_copy(update={"generator": "llm", "provider": "ollama"})
        }
    )
    with pytest.raises(GeneratorError, match="deepseek"):
        generate_from_llm(TRUE_CORRELATION, local)
