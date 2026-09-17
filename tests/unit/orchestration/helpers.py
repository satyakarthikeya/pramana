"""Contract-valid fixtures local to the orchestration test suite."""

from pramana.common.config import RuntimeConfig
from pramana.contracts import (
    CandidateInsight,
    ClaimType,
    EffectMetric,
    GateOutcome,
    ProofObject,
    ScoreComponents,
    TestType,
    Verdict,
)
from pramana.orchestration.run_lifecycle import new_run
from pramana.orchestration.state import PramanaState


def runtime_config() -> RuntimeConfig:
    """Return deterministic runtime settings independent of developer environment."""
    return RuntimeConfig.model_validate(
        {
            "run": {
                "graph_timeout_seconds": 30,
                "max_node_retries": 2,
                "on_exhausted_retries": "degrade",
            },
            "queue": {
                "broker_url": "redis://test.invalid/0",
                "result_backend": "redis://test.invalid/1",
                "task_soft_time_limit": 5,
                "task_hard_time_limit": 6,
                "result_timeout_seconds": 7,
            },
            "langfuse": {"enabled": False},
            "logging": {"level": "INFO", "format": "json"},
        }
    )


def make_run(
    dataset_ref: str | None = None,
    *,
    user_query: str | None = None,
) -> PramanaState:
    """Create a run whose configuration never depends on YAML or shell variables."""
    return new_run(dataset_ref, runtime=runtime_config(), user_query=user_query)


def candidate(insight_id: str) -> CandidateInsight:
    """Build a minimal valid candidate for orchestration-only tests."""
    return CandidateInsight(
        insight_id=insight_id,
        claim=f"x is associated with y ({insight_id})",
        claim_type=ClaimType.CORRELATION,
        variables=["x", "y"],
        dataset_ref="toy.csv",
    )


def proof(insight_id: str, *, passed: bool) -> ProofObject:
    """Build a complete contract-valid proof without performing statistics."""
    return ProofObject(
        insight_id=insight_id,
        verdict=Verdict.PASS if passed else Verdict.REJECT,
        gate_outcome=GateOutcome.SUPPORTED if passed else GateOutcome.INCONCLUSIVE,
        bh_family_id="bh-orchestration-test",
        seed=1,
        p_value=0.001 if passed else 0.8,
        q_value=0.002 if passed else 0.9,
        effect_size=0.5 if passed else 0.01,
        effect_metric=EffectMetric.SPEARMAN_RHO,
        test_type=TestType.PERMUTATION,
        falsification_code="# fixture only",
        n_hypotheses_in_batch=1,
        evidence_score=0.8 if passed else None,
        score_components=(ScoreComponents(s_q=0.8, s_e=0.8, s_r=0.8) if passed else None),
    )
