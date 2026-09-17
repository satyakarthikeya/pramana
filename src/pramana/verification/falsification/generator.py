"""The generator interface: a candidate insight in, an executable program out.

Two generators sit behind one interface. `generate_from_template` renders the
deterministic, per-`ClaimType` code in `templates.py`; `generate_from_llm` asks
DeepSeek V4 to write it. `get_generator` picks between them from
`configs/verification.yaml`, and both return the same `FalsificationProgram`, so
everything downstream -- executor, gate, proof object -- is identical either way.

    CandidateInsight + VerificationConfig  ->  FalsificationProgram

`FalsificationProgram` carries the rendered source together with the metadata needed
to interpret the result, so a proof object can record WHAT ran, with WHICH seed and
how many resamples, WITHOUT re-deriving any of it from the candidate afterwards.
`generator` names which path produced the code, so an ablation can tell a template run
from an LLM run in the audit trail rather than by inference.

Why the template path is the default
------------------------------------
It needs no API key and no network, and its output is byte-reproducible. The LLM path
is the secondary generator measured against it, not a replacement for it.

What the LLM is trusted with, and what it is not
------------------------------------------------
The model writes code. It never reports a statistic (AGENTS.md 3.1). Before any
generated source is returned it must survive four checks, in this order: it parses as
Python, it defines `falsify(frame)`, its module-level `N_PERMUTATIONS` and `SEED` are
the values this run is configured for, and it passes the same import whitelist the
template path passes. Failing any of them raises `GeneratorError`.

There is no fallback. A model that fails to produce usable code does NOT quietly get
replaced by the template renderer: a run that believes it is measuring the LLM must
not silently measure something else, and an insight whose test could not be generated
is an insight that was never tested. `GeneratorError` is catchable precisely so the
gateway can turn it into REJECT / NOT_TESTABLE, which is the only thing it may become.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 6
"""

from __future__ import annotations

import ast
import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType, TestType
from pramana.verification.config import VerificationConfig
from pramana.verification.executor.policy import ImportPolicyViolation, check_imports
from pramana.verification.falsification import prompts, templates

#: Every supported claim type is a relationship between exactly two columns, and the
#: templates render `VAR_X` / `VAR_Y` from them in that order.
_REQUIRED_VARIABLES = 2

#: The function the executor's harness calls. A module without it is not a test.
_ENTRY_POINT = "falsify"

#: Module-level constants the generated source must bind to this run's config. The
#: executor re-checks the values that actually come back from the run (a stamped
#: result from a differently seeded test is still refused there); checking the source
#: here turns that late failure into an early one with a readable reason.
_DICTATED_CONSTANTS = ("N_PERMUTATIONS", "SEED")

#: ```python ... ``` or a bare ``` ... ``` block. The system prompt asks for exactly
#: one; when none is present the whole response is treated as source and the parse
#: check below decides, which is how a prose refusal becomes a `GeneratorError`.
_CODE_FENCE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)

#: The provider this module will talk to. AGENTS.md 2 reserves verification for
#: DeepSeek V4 and forbids substituting a local model: the trust thesis is that the
#: gate's code is written by a strong model and then executed, so silently accepting
#: a weaker provider here would hollow out the claim without changing any test.
_REQUIRED_PROVIDER = "deepseek"

#: DeepSeek speaks the OpenAI wire format, so the OpenAI SDK is pointed at its host.
_DEFAULT_BASE_URL = "https://api.deepseek.com"


class GeneratorError(RuntimeError):
    """A falsification program could not be generated, for any reason.

    Raised by the LLM path when the API call fails, the response cannot be read as a
    module, or the module fails a safety check. It is a distinct, catchable type so
    the gateway can record the failure and issue REJECT / NOT_TESTABLE. There is no
    path from this exception to a PASS, and no path from it back to the template
    renderer.
    """


class FalsificationProgram(BaseModel):
    """One rendered falsification test, ready to execute.

    Guarantees: frozen, so the source that was policy-checked is the source that runs
    and the source recorded in the proof object. `source` is the complete module --
    the executor writes it to disk unmodified, adding nothing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    insight_id: str = Field(min_length=1)
    claim_type: ClaimType
    var_x: str = Field(min_length=1)
    var_y: str = Field(min_length=1)
    test_type: TestType = Field(description="Which vetted procedure the code calls.")
    n_permutations: int = Field(ge=1, description="Resamples the rendered code will run.")
    seed: int = Field(description="Baked into the source, so the run is reproducible.")
    source: str = Field(min_length=1, description="The complete generated module.")
    generator: str = Field(
        min_length=1,
        description="Which path produced this code ('template', 'llm'). Recorded so an "
        "ablation can distinguish them in the audit trail rather than by inference.",
    )


def _two_variables(candidate: CandidateInsight) -> tuple[str, str]:
    """The claim's two columns, or a refusal.

    In practice the admissibility screen has already refused a claim with any other
    arity, so this is the second of two locks.
    """
    if len(candidate.variables) != _REQUIRED_VARIABLES:
        raise ValueError(
            f"{candidate.insight_id}: a falsification template needs exactly "
            f"{_REQUIRED_VARIABLES} variables; got {candidate.variables}"
        )
    var_x, var_y = candidate.variables
    return var_x, var_y


def generate_from_template(
    candidate: CandidateInsight, config: VerificationConfig
) -> FalsificationProgram:
    """Render `candidate` into an executable falsification program, with no LLM.

    Guarantees: byte-identical output for the same `(candidate, config)`, so the
    `falsification_code` stored in a proof object is a reproducible record of exactly
    what ran (AGENTS.md 4.4). Every tunable in the rendered source -- resample count,
    seed, minimum observations -- comes from `configs/verification.yaml`, never from a
    literal here or in the template.

    Raises for a claim that does not name exactly two columns, and (via
    `templates.render`) for a claim type with no template: the gateway fails closed
    rather than substituting a generic test. In practice the admissibility screen has
    already refused both, so this is the second of two locks.
    """
    var_x, var_y = _two_variables(candidate)
    source = templates.render(
        insight_id=candidate.insight_id,
        claim=candidate.claim,
        claim_type=candidate.claim_type,
        var_x=var_x,
        var_y=var_y,
        n_permutations=config.statistics.n_permutations,
        seed=config.statistics.seed,
        min_observations=config.statistics.min_observations,
        reference_group=candidate.reference_group,
    )
    return FalsificationProgram(
        insight_id=candidate.insight_id,
        claim_type=candidate.claim_type,
        var_x=var_x,
        var_y=var_y,
        test_type=TestType.PERMUTATION,
        n_permutations=config.statistics.n_permutations,
        seed=config.statistics.seed,
        source=source,
        generator="template",
    )


@contextmanager
def _traced(insight_id: str, config: VerificationConfig) -> Iterator[None]:
    """Trace one generation through Langfuse when it is configured (AGENTS.md 2).

    Tracing is observability, so it never decides anything and never breaks a run: an
    unconfigured or unreachable Langfuse yields a no-op rather than an exception. The
    shared client in `pramana.common.langfuse_client` is another member's module and
    is still a stub, so this reaches the SDK directly for now; when that client lands
    this body should delegate to it rather than build a second one.
    """
    required = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
    if any(not os.getenv(name) for name in required):
        yield
        return
    try:
        from langfuse import Langfuse

        client: Any = Langfuse(
            public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
            secret_key=os.environ["LANGFUSE_SECRET_KEY"],
            host=os.environ["LANGFUSE_HOST"],
        )
        observe = getattr(client, "start_as_current_observation", None)
        if observe is None:
            yield
            return
        with observe(
            name="falsification-generation",
            as_type="generation",
            metadata={
                "insight_id": insight_id,
                "provider": config.llm.provider,
                "model": config.llm.model,
                "temperature": config.llm.temperature,
            },
        ):
            yield
    except Exception:  # observability must never take the gateway down with it
        yield


def _call_deepseek(system: str, user: str, config: VerificationConfig) -> str:
    """Send one completion request to DeepSeek and return the raw response text.

    Isolated as a module-level function so tests can substitute it without a live API
    call, and so every network failure funnels through one `GeneratorError`.
    """
    if config.llm.provider != _REQUIRED_PROVIDER:
        raise GeneratorError(
            f"the falsification generator is configured for provider "
            f"{config.llm.provider!r}, but verification runs on "
            f"{_REQUIRED_PROVIDER!r} only (AGENTS.md 2). Routing the gate through "
            f"another model changes what the PASS means, so it is refused here "
            f"rather than silently honoured."
        )

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise GeneratorError(
            "DEEPSEEK_API_KEY is not set, so the LLM generator cannot run. The "
            "template generator is the offline default; selecting 'llm' without a "
            "key fails closed rather than quietly falling back to it."
        )

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", _DEFAULT_BASE_URL),
        )
        response = client.chat.completions.create(
            model=config.llm.model,
            temperature=config.llm.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    except Exception as error:  # any transport/API failure is a generation failure
        raise GeneratorError(
            f"the DeepSeek request failed ({type(error).__name__}: {error}). A claim "
            f"whose test could not be generated has not been tested."
        ) from error

    content = response.choices[0].message.content if response.choices else None
    if not content or not content.strip():
        raise GeneratorError(
            "DeepSeek returned an empty response; there is no falsification program "
            "to run, so the claim cannot be verified."
        )
    return content


def _extract_source(response: str) -> str:
    """The module source inside `response`.

    Prefers the fenced block the system prompt asks for. With no fence the whole
    response is treated as source, which lets the parse check below turn a prose
    answer ("I cannot write that") into a `GeneratorError` rather than a silent pass.
    """
    match = _CODE_FENCE.search(response)
    source = match.group(1) if match else response
    stripped = source.strip()
    if not stripped:
        raise GeneratorError(
            "the model's response contained no code; there is nothing to execute."
        )
    return stripped + "\n"


def _module_constants(tree: ast.Module) -> dict[str, Any]:
    """Module-level names bound to a literal, for the dictated-constant check."""
    found: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                found[target.id] = value
    return found


def _validate_llm_source(source: str, config: VerificationConfig) -> None:
    """Refuse generated source that is not a usable, policy-clean falsification test.

    Guarantees: returns None only when the source parses, defines `falsify(frame)`,
    binds every dictated constant to this run's configured value, and passes the same
    import whitelist the template path passes. Raises `GeneratorError` otherwise --
    the LLM path gets no looser sandbox than the deterministic one (AGENTS.md 4).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise GeneratorError(
            f"the generated module does not parse (line {error.lineno}: {error.msg}). "
            f"Code we cannot read is code we cannot run."
        ) from error

    entry = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == _ENTRY_POINT
    ]
    if not entry:
        raise GeneratorError(
            f"the generated module defines no {_ENTRY_POINT}(frame) function, so the "
            f"executor's harness has nothing to call."
        )
    if len(entry[0].args.args) != 1:
        raise GeneratorError(
            f"{_ENTRY_POINT}() must take exactly one argument (the dataframe); the "
            f"generated module declares {len(entry[0].args.args)}."
        )

    expected = {
        "N_PERMUTATIONS": config.statistics.n_permutations,
        "SEED": config.statistics.seed,
    }
    constants = _module_constants(tree)
    for name in _DICTATED_CONSTANTS:
        if name not in constants:
            raise GeneratorError(
                f"the generated module does not define {name} at module level. This "
                f"run's resample count and seed are what make it reproducible "
                f"(AGENTS.md 3.4), so they are dictated, not left to the model."
            )
        if constants[name] != expected[name]:
            raise GeneratorError(
                f"the generated module sets {name} = {constants[name]!r}, but this run "
                f"is configured for {expected[name]!r}. A test that quietly changed "
                f"its own resample count or seed is not the test this run promised."
            )

    try:
        check_imports(source, config.executor.allowed_imports)
    except ImportPolicyViolation as error:
        raise GeneratorError(
            f"the generated module fails the sandbox import policy: {error}. The LLM "
            f"path runs under the same whitelist as the template path; it does not "
            f"get a looser sandbox."
        ) from error


def generate_from_llm(
    candidate: CandidateInsight, config: VerificationConfig
) -> FalsificationProgram:
    """Ask DeepSeek V4 for a falsification program, and return it only if it is safe.

    Guarantees: the returned source parses, defines `falsify(frame)`, carries this
    run's configured resample count and seed, and satisfies the sandbox import
    whitelist. Every other outcome raises `GeneratorError`.

    There is no fallback to `generate_from_template`. Substituting the deterministic
    renderer when the model fails would make an LLM-condition run silently measure the
    template condition, and would let a claim reach the executor by a route its own
    generator could not produce. A failure here is a claim that was not tested, and
    the only verdicts it may become are REJECT and NOT_TESTABLE.
    """
    var_x, var_y = _two_variables(candidate)
    if candidate.claim_type not in prompts.SUPPORTED_CLAIM_TYPES:
        raise GeneratorError(
            f"{candidate.insight_id}: no falsification prompt for claim_type "
            f"{candidate.claim_type.value!r}; the gateway fails closed rather than "
            f"asking for a generic test."
        )

    system, user = prompts.build_prompt(
        candidate,
        var_x=var_x,
        var_y=var_y,
        n_permutations=config.statistics.n_permutations,
        seed=config.statistics.seed,
        min_observations=config.statistics.min_observations,
    )

    with _traced(candidate.insight_id, config):
        response = _call_deepseek(system, user, config)

    source = _extract_source(response)
    _validate_llm_source(source, config)

    return FalsificationProgram(
        insight_id=candidate.insight_id,
        claim_type=candidate.claim_type,
        var_x=var_x,
        var_y=var_y,
        test_type=TestType.PERMUTATION,
        n_permutations=config.statistics.n_permutations,
        seed=config.statistics.seed,
        source=source,
        generator="llm",
    )


#: The two paths, keyed by what `configs/verification.yaml` may name.
_GENERATORS: dict[
    str, Callable[[CandidateInsight, VerificationConfig], FalsificationProgram]
] = {
    "template": generate_from_template,
    "llm": generate_from_llm,
}


def get_generator(
    config: VerificationConfig,
) -> Callable[[CandidateInsight, VerificationConfig], FalsificationProgram]:
    """The generator `config` selects.

    Guarantees: returns exactly the path named by `llm.generator`, never a substitute.
    A run configured for the LLM gets the LLM generator even when no API key is
    present -- the failure then surfaces at generation time as a `GeneratorError`,
    which is a recorded, fail-closed outcome, rather than as a silent downgrade to the
    template path that would make the run measure something other than what it claims.
    """
    try:
        return _GENERATORS[config.llm.generator]
    except KeyError:  # pragma: no cover -- LLMConfig.generator is a Literal
        raise ValueError(
            f"unknown falsification generator {config.llm.generator!r}; "
            f"expected one of {sorted(_GENERATORS)}"
        ) from None
