"""The verification config as the suite must use it: pinned to the template generator.

`configs/verification.yaml` names the generator the PRODUCT runs. Once that is `llm`,
a test that calls bare `load_config()` would reach for the DeepSeek API: slow, costly,
non-deterministic and impossible to run offline. Every test that needs a verification
config therefore goes through `load_pinned_config()`, which is the shipped config with
exactly one value changed. Tests of the LLM path build their config from this and
select `llm` explicitly, with the model call replaced by a double.

Owner: P.P. Satya Karthikeya (verification tests)
"""

from __future__ import annotations

from pramana.verification.config import VerificationConfig, load_config


def load_pinned_config() -> VerificationConfig:
    """The shipped config with `llm.generator` forced to `template`.

    Guarantees: the result selects the offline, deterministic generator whatever the
    YAML says, and every other value is the shipped one, so thresholds are still read
    from `configs/verification.yaml` and never copied into a test.
    """
    shipped = load_config()
    return shipped.model_copy(
        update={"llm": shipped.llm.model_copy(update={"generator": "template"})}
    )
