"""Shared pytest fixtures.

Owner: shared. Module-specific fixtures belong in that module's test folder.

The toy dataframe fixture is deliberately shared between the analysis acceptance test
and the gateway acceptance test, so both modules are provably testing the same data:
one strong planted relationship, one pure-noise pair, one group difference.

TODO: implement alongside the contracts (SCOPE.md §4 step 1).
"""


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _offline_template_generator(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the verification generator to `template` for every test.

    The shipped default is `llm` (DECISIONS_LLM_ROLES D1), which fails closed without a
    key. Tests that need the shipped default or the LLM path set the variable themselves.
    """
    monkeypatch.setenv("PRAMANA_VERIFICATION_GENERATOR", "template")
    monkeypatch.setenv("PRAMANA_ANALYSIS_ENGINE", "deterministic")
    monkeypatch.setenv("PRAMANA_SECTOR_ENGINE", "rules")
    monkeypatch.setenv("PRAMANA_SUMMARY_ENGINE", "template")
    # The Measured tier fits models after an upload; only tests that look at it turn it on.
    monkeypatch.setenv("PRAMANA_MEASURED_ENABLED", "0")
