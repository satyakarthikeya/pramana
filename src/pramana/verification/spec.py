"""A fingerprint of the test plan, fixed before the held-back rows are read (design v3, S4).

The hash covers everything that decides what the gate computes: the stored test code, the
seed, the number of permutations, the null the gate assigned, the rows it will see (the
split digest), the direction asserted and alpha. It is logged before the code runs and
stamped on the proof, so a reviewer can recompute it from the proof alone and see that the
test was not changed after the data was looked at. It is tamper evidence for what the
proof records, not a secret: it does not stop the operator from running a different plan
and recording that one.
"""

from __future__ import annotations

import hashlib
import json
import re

from pramana.contracts import PermutationScheme, ProofObject

_N_PERMUTATIONS = re.compile(r"^N_PERMUTATIONS\s*=\s*(\d+)\s*$", re.M)


def declared_permutations(code: str) -> int | None:
    """The permutation count the stored program declares, or None."""
    match = _N_PERMUTATIONS.search(code or "")
    return int(match[1]) if match else None


def spec_hash(
    *,
    code: str,
    seed: int,
    n_permutations: int | None,
    scheme: PermutationScheme,
    split_digest: str | None,
    direction: str | None,
    alpha: float,
) -> str:
    """SHA-256 of the canonical JSON of the plan fields (sorted keys, no whitespace)."""
    plan = {
        "alpha": alpha,
        "code_sha256": hashlib.sha256(code.encode("utf-8")).hexdigest(),
        "direction": direction,
        "n_permutations": n_permutations,
        "scheme": scheme.value,
        "seed": seed,
        "split_digest": split_digest,
    }
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def recompute(proof: ProofObject, alpha: float) -> str | None:
    """The hash `proof` should carry, from its own stored fields; None when untested."""
    if proof.falsification_code is None or proof.permutation_scheme is None:
        return None
    return spec_hash(
        code=proof.falsification_code,
        seed=proof.seed,
        n_permutations=declared_permutations(proof.falsification_code),
        scheme=proof.permutation_scheme,
        split_digest=proof.split.confirmation_digest if proof.split else None,
        direction=proof.asserted_direction.value if proof.asserted_direction else None,
        alpha=alpha,
    )


def matches(proof: ProofObject, alpha: float) -> bool:
    """True when the stamped hash equals the one recomputed from the proof's own fields."""
    return proof.spec_hash is not None and proof.spec_hash == recompute(proof, alpha)
