"""The analysis -> verification handoff: does the gateway accept what analysis emits?

This is an integration property, not a unit one. It spans two members' modules -- it
runs P. Rohith's candidate generation and then P.P. Satya Karthikeya's admissibility
screen over the result -- so it lives here rather than under `tests/unit/analysis/`,
where it would have made the analysis unit suite unrunnable without the verification
module present and correct (`tests/OWNERSHIP.md`: tests mirror `src/` ownership).

What it protects is the handoff criterion: every `CandidateInsight` the analysis
module emits must pass the gateway UNPATCHED. Analysis builds its claims from fixed
hedged templates ("is associated with", "tends to be higher when") precisely so they
clear the screen's universal and causal vocabulary by construction. If that vocabulary
changes, or a claim template drifts, this test fails here rather than the whole batch
quietly turning into NOT_TESTABLE verdicts in a run.

It uses the same toy frame as the gateway acceptance test
(`tests/fixtures/frames.py`), so both sides of the handoff are provably looking at the
same data.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pramana.analysis.config import AnalysisConfig, load_config
from pramana.analysis.hypotheses.generation import generate_candidates
from pramana.analysis.schema_inference import SchemaProfile, infer_schema
from pramana.contracts.candidate_insight import CandidateInsight
from pramana.contracts.enums import ClaimType
from pramana.verification.admissibility import screen
from tests.fixtures.frames import toy_frame

pytestmark = pytest.mark.integration

DATASET_REF = "toy_frame"


@pytest.fixture
def config() -> AnalysisConfig:
    """The shipped config -- these tests assert against what the project actually runs."""
    return load_config()


@pytest.fixture
def frame() -> pd.DataFrame:
    return toy_frame()


@pytest.fixture
def schema(frame: pd.DataFrame, config: AnalysisConfig) -> SchemaProfile:
    return infer_schema(frame, config.schema_inference)


@pytest.fixture
def candidates(
    frame: pd.DataFrame, schema: SchemaProfile, config: AnalysisConfig
) -> list[CandidateInsight]:
    return generate_candidates(
        frame, schema, config.hypotheses, dataset_ref=DATASET_REF
    )


def test_every_candidate_survives_the_gateway_admissibility_screen(
    candidates: list[CandidateInsight], frame: pd.DataFrame
) -> None:
    """The handoff criterion: the gateway accepts the whole batch, unpatched.

    A claim template that trips the universal or causal vocabulary should fail here,
    not in a run.
    """
    columns = [str(name) for name in frame.columns]

    refused = {
        candidate.insight_id: screen(candidate, columns).reason
        for candidate in candidates
        if not screen(candidate, columns).admissible
    }
    assert refused == {}


def test_the_gateway_screen_itself_can_be_passed_as_the_claim_screen(
    frame: pd.DataFrame, schema: SchemaProfile, config: AnalysisConfig
) -> None:
    """Orchestration imports both modules; wiring the real screen in must work."""
    columns = [str(name) for name in frame.columns]

    def gateway_screen(claim: str, claim_type: ClaimType, variables: list[str]) -> bool:
        return screen(
            CandidateInsight(
                insight_id="screen-probe",
                claim=claim,
                claim_type=claim_type,
                variables=variables,
                dataset_ref=DATASET_REF,
            ),
            columns,
        ).admissible

    screened = generate_candidates(
        frame, schema, config.hypotheses, dataset_ref=DATASET_REF, claim_screen=gateway_screen
    )
    unscreened = generate_candidates(
        frame, schema, config.hypotheses, dataset_ref=DATASET_REF
    )

    assert screened == unscreened
