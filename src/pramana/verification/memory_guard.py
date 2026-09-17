"""THE gate. The single function every ChromaDB write flows through.

    memory_write => verdict == PASS        (AGENTS.md 0)

This is the narrowest point in PRAMANA. Every other module in the system exists to
produce a trustworthy `ProofObject`; this file exists so that an untrustworthy one
cannot be written no matter what the rest of the system does. If this file is wrong,
nothing else being right can save the product claim.

Why it raises instead of returning a boolean
--------------------------------------------
A predicate invites `if guard(proof): write(proof)`, and the failure mode of that
shape is an `else` branch nobody wrote. The bug is invisible in review, because the
line that is missing is the line that is not there. `assert_writable` returns the proof
itself on success, so the natural way to call it is `write(assert_writable(proof))` --
a shape where forgetting the check means having nothing to write.

Why the refusal is not a ValueError
-----------------------------------
`MemoryWriteRefused` inherits from `RuntimeError`. A generic `except ValueError` around
serialisation or parsing is common, and it must never be able to swallow an attempt to
write unverified material. A breach attempt should escape ordinary error handling and
reach someone.

Why both fields are checked
---------------------------
`ProofObject` already guarantees that `PASS` and `SUPPORTED` occur together, so testing
either one alone would be sufficient today. Both are tested anyway: this function is
the last line of defence, and it should not inherit its correctness from an invariant
enforced somewhere else. If that invariant were ever loosened, this file would still
hold.

Why nothing here imports the memory module
------------------------------------------
`pramana.memory` imports this function; this function knows nothing about ChromaDB
(OWNERSHIP.md). The dependency points one way on purpose. A guard that imported the
thing it guards could be circumvented by changing the thing it guards, and it could
not be tested without standing up a vector store.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 4 step 8
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable

from pramana.contracts.enums import GateOutcome, Verdict
from pramana.contracts.proof_object import ProofObject

_log = logging.getLogger(__name__)

#: The one verdict that may be written, and the one gate outcome that may accompany it.
#: Named constants rather than literals at each comparison: there is exactly one
#: definition of "writable" in this module, and it is these two lines.
_WRITABLE_VERDICT = Verdict.PASS
_WRITABLE_OUTCOME = GateOutcome.SUPPORTED


class MemoryWriteRefused(RuntimeError):
    """An attempt to write a proof object that did not pass verification.

    Carries the identity of the refused claim so a handler can log or report it
    without re-deriving anything. Deliberately a `RuntimeError` and deliberately not a
    `ValueError`, so ordinary error handling around parsing or serialisation cannot
    absorb a breach attempt.
    """

    def __init__(self, proof: ProofObject) -> None:
        self.insight_id: str = proof.insight_id
        self.verdict: Verdict = proof.verdict
        self.gate_outcome: GateOutcome = proof.gate_outcome
        super().__init__(
            f"refusing to write insight {proof.insight_id!r} to memory: verdict is "
            f"{proof.verdict.name}, gate outcome is {proof.gate_outcome.name}. Only a "
            f"{_WRITABLE_VERDICT.name} / {_WRITABLE_OUTCOME.name} proof object may be "
            f"written (AGENTS.md 0); there is no other path into memory."
        )


def assert_writable(proof: ProofObject) -> ProofObject:
    """Return `proof` if it may be written to memory, and raise if it may not.

    Guarantees: the returned object is the SAME object that was passed in, and it
    always carries `verdict == PASS` and `gate_outcome == SUPPORTED`. There is no
    argument, no configuration and no environment in which this function returns
    anything else, and no path through it that returns `None`.

    Raises `MemoryWriteRefused` for every other proof object, including
    `NOT_TESTABLE` -- a claim that could not even be tested is the last thing that
    should reach long-term memory.

    Call it as `write(assert_writable(proof))`. That way a caller who forgets the
    guard has nothing to write, rather than something unverified to write.
    """
    if proof.verdict is not _WRITABLE_VERDICT or proof.gate_outcome is not _WRITABLE_OUTCOME:
        _log.info(
            json.dumps(
                {
                    "event": "memory_write_refused",
                    "insight_id": proof.insight_id,
                    "verdict": proof.verdict.value,
                    "gate_outcome": proof.gate_outcome.value,
                }
            )
        )
        raise MemoryWriteRefused(proof)

    _log.info(
        json.dumps(
            {
                "event": "memory_write_permitted",
                "insight_id": proof.insight_id,
                "verdict": proof.verdict.value,
                "gate_outcome": proof.gate_outcome.value,
                "evidence_score": proof.evidence_score,
            }
        )
    )
    return proof


def writable(proofs: Iterable[ProofObject]) -> list[ProofObject]:
    """The subset of `proofs` that may be written, in the order they arrived.

    Guarantees: every element of the returned list would also survive
    `assert_writable`, because this function decides nothing itself -- it delegates
    each proof to `assert_writable` and keeps the ones that come back. The two entry
    points cannot drift apart, because there is only one of them.

    An empty result is a legitimate outcome, not an error: a run in which nothing
    passed is exactly what the gate is for, and it is the honest thing to report.
    """
    accepted: list[ProofObject] = []
    refused = 0
    for proof in proofs:
        try:
            accepted.append(assert_writable(proof))
        except MemoryWriteRefused:
            # Already logged with its insight_id at the point of refusal. Filtering a
            # batch is routine -- most claims in a healthy run do not pass -- so this
            # is a normal path, not an error one.
            refused += 1

    _log.info(
        json.dumps(
            {
                "event": "memory_batch_filtered",
                "n_accepted": len(accepted),
                "n_refused": refused,
            }
        )
    )
    return accepted
