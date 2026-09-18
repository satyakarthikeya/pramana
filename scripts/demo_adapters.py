"""Real, in-process adapters for the team-review demo of the orchestration graph.

Nothing here is a stub and nothing goes through Celery or Redis. Every adapter calls
the owning module's public function and returns exactly the update shape the graph
node validates (see `orchestration/nodes/*.py`):

  ingest       -> {dataset, dataset_ref, dataset_metadata, cleaning_report}
                  load_dataset + clean_dataset; dataset_ref becomes the cleaned-frame
                  hash ref (handlers.cleaned_dataset_ref) so analysis_node's
                  candidate.dataset_ref == state.dataset_ref check holds.
  subagents    -> {schema_profile}   infer_schema, optional LLM SemanticRefiner
  analyze      -> {candidate_insights}   generate_candidates (rules), optional
                  LLM pair proposer merged under the same cap
  verify       -> {proof_objects}   verification.gateway.verify_batch in-process;
                  one ProofObject per candidate, same insight_ids, which is what
                  verification_node requires
  memory_write -> {memory_receipts: []}   explicit no-op for this demo
  report       -> orchestration.adapters.safe_report_adapter, unchanged

Optional LLM assists are behind env vars and never make a network call when unset.
Provider selection for the ANALYSIS step (schema refiner + candidate proposer):

  primary   DEEPSEEK_API_KEY           the same key the gateway uses. Base URL from
                                       DEEPSEEK_BASE_URL (default https://api.deepseek.com),
                                       model from DEEPSEEK_ANALYSIS_MODEL (default
                                       "deepseek-flash"). Deliberately NOT the gateway's
                                       llm.model from configs/verification.yaml: the
                                       analysis step is not the trust-critical one.
  fallback  OPENROUTER_API_KEY +       used only when DEEPSEEK_API_KEY is unset.
            OPENROUTER_MODEL           OpenAI-compatible client at openrouter.ai.

The GATEWAY's falsification-code generator is a separate switch: `--enable-gateway-llm`
flips configs/verification.yaml's llm.generator to "llm" for the run, and the
gateway itself reads DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL (falsification/generator.py).

This file does not edit orchestration/adapters.py (B. Karthikeya's) or anything under
verification/ or analysis/. It is demo glue only.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from pramana.analysis.cleaning import clean_dataset
from pramana.analysis.config import AnalysisConfig
from pramana.analysis.config import load_config as load_analysis_config
from pramana.analysis.handlers import cleaned_dataset_ref
from pramana.analysis.hypotheses.base import emit, usable_pair
from pramana.analysis.hypotheses.generation import generate_candidates
from pramana.analysis.ingestion import get_dataset_metadata, load_dataset
from pramana.analysis.schema_inference import (
    USABLE_ROLES,
    ColumnProfile,
    ColumnRole,
    SchemaProfile,
    describe_unusable,
    infer_schema,
)
from pramana.contracts import CandidateInsight, ClaimType, Direction, ProofObject
from pramana.orchestration.adapters import WorkflowAdapters, safe_report_adapter
from pramana.orchestration.state import PramanaState
from pramana.verification.config import VerificationConfig
from pramana.verification.config import load_config as load_verification_config
from pramana.verification.gateway import verify_batch

DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_ANALYSIS_MODEL = "deepseek-flash"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
RULES_SOURCE = "rules"


@dataclass(frozen=True)
class DemoSettings:
    """Everything the adapters need that is not already in graph state."""

    csv_path: Path
    enable_gateway_llm: bool = False
    #: Demo-only override of configs/verification.yaml's llm.model for this run.
    #: None keeps the YAML value. Exists because that YAML currently names a model id
    #: the live DeepSeek API does not accept; fixing the YAML is the gateway owner's call.
    gateway_model: str | None = None
    deepseek_api_key: str | None = None
    deepseek_base_url: str = DEEPSEEK_DEFAULT_BASE_URL
    deepseek_analysis_model: str = DEEPSEEK_DEFAULT_ANALYSIS_MODEL
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None

    @property
    def llm_provider(self) -> str | None:
        """Which provider the ANALYSIS step's optional LLM path uses, or None."""
        if self.deepseek_api_key:
            return "deepseek"
        if self.openrouter_api_key and self.openrouter_model:
            return "openrouter"
        return None

    @property
    def llm_model(self) -> str | None:
        if self.llm_provider == "deepseek":
            return self.deepseek_analysis_model
        if self.llm_provider == "openrouter":
            return self.openrouter_model
        return None

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider is not None

    @property
    def llm_label(self) -> str:
        return f"{self.llm_provider}:{self.llm_model}" if self.llm_enabled else "off"

    @classmethod
    def from_env(
        cls, csv_path: Path, *, enable_gateway_llm: bool, gateway_model: str | None = None
    ) -> DemoSettings:
        return cls(
            csv_path=csv_path,
            enable_gateway_llm=enable_gateway_llm,
            gateway_model=gateway_model or None,
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or None,
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL") or DEEPSEEK_DEFAULT_BASE_URL,
            deepseek_analysis_model=(
                os.getenv("DEEPSEEK_ANALYSIS_MODEL") or DEEPSEEK_DEFAULT_ANALYSIS_MODEL
            ),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY") or None,
            openrouter_model=os.getenv("OPENROUTER_MODEL") or None,
        )


@dataclass
class DemoTrace:
    """Provenance the demo prints afterwards. Kept out of PramanaState on purpose:
    the state model is `extra="forbid"` and these facts are demo bookkeeping, not
    run data."""

    unusable_columns: list[str] = field(default_factory=list)
    refiner_decisions: dict[str, str] = field(default_factory=dict)
    candidate_sources: dict[str, str] = field(default_factory=dict)
    candidates_before_cap: int = 0
    llm_proposals: list[str] = field(default_factory=list)
    proposer_error: str | None = None
    gateway_generator: str = "template"
    gateway_model: str | None = None


# --------------------------------------------------------------------------- LLM client


def _llm_chat(settings: DemoSettings, system: str, user: str) -> str:
    """One OpenAI-compatible completion against the selected provider.

    Caller handles errors. Temperature 0 so a re-run with the same frame asks the
    same question and, as far as the provider allows, gets the same answer.
    """
    from openai import OpenAI

    if settings.llm_provider == "deepseek":
        client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
    elif settings.llm_provider == "openrouter":
        client = OpenAI(api_key=settings.openrouter_api_key, base_url=OPENROUTER_BASE_URL)
    else:
        raise RuntimeError("no LLM provider configured")
    response = client.chat.completions.create(
        model=str(settings.llm_model),
        temperature=0.0,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    content = response.choices[0].message.content if response.choices else None
    if not content or not content.strip():
        raise RuntimeError(f"{settings.llm_provider} returned an empty response")
    return content


class LLMRefiner:
    """`schema_inference.SemanticRefiner` backed by the selected provider.

    Offered only the columns the heuristics left UNKNOWN (infer_schema enforces that).
    Returns a usable ColumnRole or None; infer_schema records the role at exactly
    `min_confidence` and treats a raise or a nonsense answer as "leave UNKNOWN".
    """

    _SYSTEM = (
        "You classify one dataframe column for hypothesis generation. Answer with exactly "
        "one word from: numeric, categorical, ordinal, datetime, unknown. Say unknown "
        "unless you are confident. Never guess."
    )

    def __init__(self, settings: DemoSettings, trace: DemoTrace) -> None:
        self._settings = settings
        self._trace = trace

    def refine(self, profile: ColumnProfile) -> ColumnRole | None:
        user = json.dumps(
            {
                "column": profile.name,
                "dtype": profile.dtype,
                "n_non_null": profile.n_non_null,
                "n_unique": profile.n_unique,
                "unique_ratio": round(profile.unique_ratio, 3),
                "missing_ratio": round(profile.missing_ratio, 3),
                "heuristic_reasons": profile.reasons,
            }
        )
        try:
            answer = _llm_chat(self._settings, self._SYSTEM, user).strip().lower()
            word = re.split(r"\W+", answer)[0] if answer else ""
            role = ColumnRole(word) if word in {r.value for r in ColumnRole} else None
        except Exception as error:  # noqa: BLE001 - refiner failure must not fail the run
            self._trace.refiner_decisions[profile.name] = f"error: {error}"
            return None
        if role is None or role not in USABLE_ROLES:
            self._trace.refiner_decisions[profile.name] = "declined"
            return None
        self._trace.refiner_decisions[profile.name] = role.value
        return role


# --------------------------------------------------------------------------- LLM proposer


def _eta_squared(groups: list[pd.Series]) -> float:
    """Same exploratory magnitude group_difference.py uses; recomputed here for
    LLM-proposed pairs so their evidence is computed from the data, not the LLM."""
    values = pd.concat(groups)
    total = float(((values - values.mean()) ** 2).sum())
    if total <= 0.0:
        return 0.0
    between = float(sum(len(g) * (g.mean() - values.mean()) ** 2 for g in groups))
    return max(0.0, min(1.0, between / total))


def _candidate_for_pair(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    config: AnalysisConfig,
    x: str,
    y: str,
    claim_type: ClaimType,
    *,
    dataset_ref: str,
    source: str,
) -> CandidateInsight | str:
    """Build a contract-valid candidate for an LLM-proposed pair, or say why not.

    The LLM only names the pair and the claim shape. The exploratory statistic, the
    hedged wording, the direction and the reference group are all computed here the
    way the rule-based strategies compute them, and the same pre-filters apply.
    Nothing the LLM says becomes evidence. Returns a reason string when dropped.
    """
    hyp = config.hypotheses
    if x == y:
        return "x and y are the same column"
    if x not in schema.columns or y not in schema.columns:
        return "names a column that is not in the frame"
    if not (schema.columns[x].usable_for_hypotheses and schema.columns[y].usable_for_hypotheses):
        return "uses a column schema inference marked unusable"
    numeric = set(schema.usable(ColumnRole.NUMERIC))
    groupings = set(schema.usable(ColumnRole.CATEGORICAL, ColumnRole.ORDINAL))
    note = f"exploratory scan of a {source}-proposed pair; not a test result"

    if claim_type is ClaimType.CORRELATION:
        if x not in numeric or y not in numeric:
            return "correlation needs two numeric columns"
        pair = usable_pair(frame, x, y, hyp.min_observations)
        if pair is None:
            return f"fewer than min_observations={hyp.min_observations} complete rows"
        rho = float(pair[x].corr(pair[y], method="spearman"))
        if math.isnan(rho) or abs(rho) < hyp.min_abs_correlation:
            return f"|rho|={abs(rho):.3f} below min_abs_correlation={hyp.min_abs_correlation}"
        candidate = emit(
            strategy=source,
            claim=f"{y} is associated with {x}",
            claim_type=claim_type,
            variables=[x, y],
            dataset_ref=dataset_ref,
            direction=Direction.POSITIVE if rho > 0 else Direction.NEGATIVE,
            evidence={
                "stat": "spearman_rho",
                "raw_value": rho,
                "n_observations": int(len(pair)),
                "source": note,
            },
        )
        return candidate if candidate is not None else "contract refused the candidate"

    if claim_type is ClaimType.GROUP_DIFFERENCE:
        if x not in groupings or y not in numeric:
            return "group_difference needs x categorical/ordinal and y numeric"
        pair = frame[[x, y]].dropna()
        labels = pair[x].astype(str)
        counts = labels.value_counts()
        kept = sorted(str(lvl) for lvl, n in counts.items() if n >= hyp.min_group_size)
        if not (hyp.min_group_levels <= len(kept) <= hyp.max_group_levels):
            return f"{len(kept)} usable levels outside the configured group-level range"
        pair = pair.loc[labels.isin(kept)]
        if len(pair) < hyp.min_observations or pair[y].nunique() < 2:
            return "too few rows or a constant measure"
        grouped = pair.groupby(pair[x].astype(str), observed=True)[y]
        groups = [grouped.get_group(lvl) for lvl in kept]
        effect = _eta_squared(groups)
        if effect < hyp.min_group_effect:
            return f"eta^2={effect:.3f} below min_group_effect={hyp.min_group_effect}"
        medians = {lvl: float(g.median()) for lvl, g in zip(kept, groups, strict=True)}
        if len(kept) == 2:
            higher = max(medians, key=lambda lvl: medians[lvl])
            claim = f"{y} tends to be higher when {x} is {higher}"
            direction: Direction | None = Direction.POSITIVE
            reference: str | None = higher
        else:
            claim, direction, reference = f"{y} tends to differ between {x} groups", None, None
        candidate = emit(
            strategy=source,
            claim=claim,
            claim_type=claim_type,
            variables=[x, y],
            dataset_ref=dataset_ref,
            direction=direction,
            reference_group=reference,
            evidence={
                "stat": "eta_squared",
                "raw_value": effect,
                "n_observations": int(len(pair)),
                "group_levels": kept,
                "group_medians": medians,
                "source": note,
            },
        )
        return candidate if candidate is not None else "contract refused the candidate"

    if claim_type is ClaimType.TREND:
        if not schema.columns[x].is_time_like or y not in numeric:
            return "trend needs a time-like x and a numeric y"
        pair = usable_pair(frame, x, y, hyp.min_observations)
        if pair is None:
            return f"fewer than min_observations={hyp.min_observations} complete rows"
        if pd.api.types.is_datetime64_any_dtype(pair[x]):
            axis = pair[x].astype("int64")
        else:
            axis = pd.to_numeric(pair[x], errors="coerce")
        ordered = pd.DataFrame({x: axis, y: pair[y]}).dropna()
        tau = float(ordered[x].corr(ordered[y], method="kendall"))
        if math.isnan(tau) or abs(tau) < hyp.min_abs_trend_tau:
            return f"|tau|={abs(tau):.3f} below min_abs_trend_tau={hyp.min_abs_trend_tau}"
        candidate = emit(
            strategy=source,
            claim=f"{y} is associated with {x}",
            claim_type=claim_type,
            variables=[x, y],
            dataset_ref=dataset_ref,
            direction=Direction.POSITIVE if tau > 0 else Direction.NEGATIVE,
            evidence={
                "stat": "kendall_tau_b",
                "raw_value": tau,
                "n_observations": int(len(ordered)),
                "source": note,
            },
        )
        return candidate if candidate is not None else "contract refused the candidate"
    return f"claim_type {claim_type.value} is not proposable here"


def _propose_with_llm(
    frame: pd.DataFrame,
    schema: SchemaProfile,
    config: AnalysisConfig,
    settings: DemoSettings,
    trace: DemoTrace,
    *,
    dataset_ref: str,
    rules: Sequence[CandidateInsight],
) -> list[CandidateInsight]:
    """Ask the model for (x, y, claim_type) pairs; keep only those the data supports.

    Every proposal is recorded in `trace.llm_proposals` with what happened to it:
    added, duplicate of a rules candidate (which is then labelled `rules+<provider>`),
    or dropped with the pre-filter that refused it.
    """
    columns = {
        name: {
            "role": p.role.value,
            "is_time_like": p.is_time_like,
            "levels": p.levels[:12],
            "n_non_null": p.n_non_null,
        }
        for name, p in schema.columns.items()
        if p.usable_for_hypotheses
    }
    system = (
        "You propose hypotheses about a tabular dataset for a statistical verifier to test. "
        'Reply with ONLY a JSON array, no prose. Each item: {"x": <column>, "y": <column>, '
        '"claim_type": one of correlation | group_difference | trend}. Rules: correlation '
        "needs two numeric columns; group_difference needs x categorical/ordinal and y numeric; "
        "trend needs x time-like and y numeric. Propose at most 8 pairs. Prefer pairs a domain "
        "expert would expect to be real. Do not invent columns."
    )
    user = json.dumps({"columns": columns, "n_rows": int(len(frame))})
    try:
        raw = _llm_chat(settings, system, user)
        match = re.search(r"\[.*\]", raw, flags=re.DOTALL)
        items = json.loads(match.group(0) if match else raw)
        if not isinstance(items, list):
            raise ValueError("model did not return a JSON array")
    except Exception as error:  # noqa: BLE001 - an unhelpful proposer must not fail the run
        trace.proposer_error = f"{type(error).__name__}: {error}"
        return []

    label = settings.llm_label
    by_pair = {(frozenset(c.variables), c.claim_type): c for c in rules}
    seen: set[tuple[frozenset[str], ClaimType]] = set()
    extras: list[CandidateInsight] = []
    for item in items[:8]:
        if not isinstance(item, dict):
            trace.llm_proposals.append(f"{item!r}: dropped (not an object)")
            continue
        x, y = str(item.get("x", "")), str(item.get("y", ""))
        raw_type = str(item.get("claim_type", "")).strip().lower()
        try:
            claim_type = ClaimType(raw_type)
        except ValueError:
            trace.llm_proposals.append(f"{x} ~ {y} [{raw_type}]: dropped (unknown claim_type)")
            continue
        key = (frozenset((x, y)), claim_type)
        if key in seen:
            trace.llm_proposals.append(f"{x} ~ {y} [{claim_type.value}]: duplicate proposal")
            continue
        seen.add(key)
        existing = by_pair.get(key)
        if existing is not None:
            trace.candidate_sources[existing.insight_id] = f"{RULES_SOURCE}+{label}"
            trace.llm_proposals.append(
                f"{x} ~ {y} [{claim_type.value}]: also found by rules -> {existing.insight_id}"
            )
            continue
        result = _candidate_for_pair(
            frame, schema, config, x, y, claim_type,
            dataset_ref=dataset_ref, source=str(settings.llm_provider),
        )
        if isinstance(result, str):
            trace.llm_proposals.append(f"{x} ~ {y} [{claim_type.value}]: dropped ({result})")
            continue
        extras.append(result)
        trace.candidate_sources[result.insight_id] = label
        trace.llm_proposals.append(f"{x} ~ {y} [{claim_type.value}]: ADDED -> {result.insight_id}")
    return extras


# --------------------------------------------------------------------------- adapters


def build_demo_adapters(settings: DemoSettings) -> tuple[WorkflowAdapters, DemoTrace]:
    """Assemble the six real adapters plus the trace the demo prints at the end."""
    analysis_config = load_analysis_config()
    trace = DemoTrace()

    def ingest_adapter(state: PramanaState) -> dict[str, Any]:
        """Real ingestion + cleaning. The cleaned frame and its hash ref go into state."""
        source = Path(state.dataset_ref or settings.csv_path).resolve()
        raw = load_dataset(source)
        metadata = get_dataset_metadata(raw, source_path=source)
        cleaned, report = clean_dataset(raw)
        return {
            "dataset": cleaned,
            "dataset_ref": cleaned_dataset_ref(str(source), cleaned),
            "dataset_metadata": metadata.model_dump(mode="json", by_alias=True),
            "cleaning_report": report.model_dump(mode="json"),
        }

    def subagents_adapter(state: PramanaState) -> dict[str, Any]:
        """Real schema inference; the LLM refiner only sees UNKNOWN columns."""
        frame = state.dataset
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("schema inference requires the cleaned DataFrame in state")
        refiner = LLMRefiner(settings, trace) if settings.llm_enabled else None
        schema = infer_schema(frame, analysis_config.schema_inference, refiner=refiner)
        trace.unusable_columns = describe_unusable(schema)
        return {"schema_profile": schema.model_dump(mode="json")}

    def analyze_adapter(state: PramanaState) -> dict[str, Any]:
        """Real rule-based candidate generation, plus optional LLM-proposed pairs,
        capped together at analysis.yaml's max_candidates_per_run."""
        frame = state.dataset
        if not isinstance(frame, pd.DataFrame) or not state.dataset_ref:
            raise ValueError("candidate generation requires the cleaned frame and its ref")
        schema = SchemaProfile.model_validate(state.schema_profile)
        hyp = analysis_config.hypotheses
        candidates = generate_candidates(frame, schema, hyp, dataset_ref=state.dataset_ref)
        for candidate in candidates:
            trace.candidate_sources[candidate.insight_id] = RULES_SOURCE

        if settings.llm_enabled:
            extras = _propose_with_llm(
                frame, schema, analysis_config, settings, trace,
                dataset_ref=state.dataset_ref, rules=candidates,
            )
            candidates = [*candidates, *extras]
        trace.candidates_before_cap = len(candidates)
        if len(candidates) > hyp.max_candidates_per_run:
            # Same ranking rule generation.py uses: largest exploratory effect, id tiebreak.
            def magnitude(candidate: CandidateInsight) -> float:
                return abs(float(candidate.analysis_evidence.get("raw_value", 0.0)))

            candidates = sorted(candidates, key=lambda c: (-magnitude(c), c.insight_id))
            candidates = candidates[: hyp.max_candidates_per_run]
        return {"candidate_insights": candidates}

    def verify_adapter(state: PramanaState) -> dict[str, Any]:
        """verify_batch in this process. One ProofObject per candidate, in input order,
        with matching insight_ids -- exactly what verification_node checks."""
        config: VerificationConfig = load_verification_config()
        if settings.enable_gateway_llm:
            llm_update: dict[str, Any] = {"generator": "llm"}
            if settings.gateway_model:
                llm_update["model"] = settings.gateway_model
            config = config.model_copy(update={"llm": config.llm.model_copy(update=llm_update)})
        trace.gateway_generator = config.llm.generator
        trace.gateway_model = config.llm.model if config.llm.generator == "llm" else None
        if not state.candidate_insights:
            return {"proof_objects": []}
        if not isinstance(state.dataset, pd.DataFrame):
            raise ValueError("in-process verification requires the cleaned frame in state")
        proofs = verify_batch(state.candidate_insights, state.dataset, config)
        return {"proof_objects": proofs}

    def memory_write_adapter(
        _state: PramanaState, _proofs: Sequence[ProofObject]
    ) -> dict[str, Any]:
        """Explicit no-op. Stands in for M. Karthik Reddy's ChromaDB writer for THIS
        DEMO ONLY: writes nothing, returns no receipts, never raises."""
        return {"memory_receipts": []}

    adapters = WorkflowAdapters(
        ingest=ingest_adapter,
        subagents=subagents_adapter,
        analyze=analyze_adapter,
        verify=verify_adapter,
        memory_write=memory_write_adapter,
        report=safe_report_adapter,
        is_stub=False,
    )
    return adapters, trace
