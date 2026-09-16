"""Provenance stamping: proof that a number came from OUR function.

The problem this closes
-----------------------
The sandbox whitelist blocks statistics LIBRARIES, not arithmetic. Generated code
that only has numpy and pandas can still write its own shuffle loop, or call
`frame.corr(method="spearman")` -- which needs no scipy at all -- and hand back a
number that never went near `permutation_test`. The whitelist alone therefore
supports a weaker claim than PROJECT.md 3 makes.

The fix: `permutation_test` HMACs its own result with a per-run nonce the parent
generated. The parent recomputes the digest over the numbers it received and rejects
anything that does not verify. A fabricated p-value cannot be stamped, because
producing the stamp requires having called the real function.

What this is and is not
-----------------------
This is an ADHERENCE check, not a security boundary. The threat model is generated
code that is lazy or wrong -- an LLM that reimplements the test badly, or shortcuts
it -- not an adversary with code execution trying to defeat us. A determined attacker
running inside the subprocess can reach the nonce: Python has no private state, and
`_NONCE` is reachable from any code that can import this module.

Two things raise the bar anyway, and both are cheap:
  * the nonce is POPPED from the environment when this module is imported, and the
    runner imports it before the generated code runs, so `os.environ` no longer
    carries it by the time that code executes;
  * the nonce is fresh per execution, so a stamp cannot be replayed from an earlier
    run or hardcoded by a model that saw one during training.

The honest summary for the report: the whitelist makes importing an unaudited
statistics library impossible, and the stamp makes accidentally bypassing the vetted
one detectable. Neither claims to stop hostile code, and we do not need it to --
the code is written by our own generator against our own prompt.

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 2 component 2
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

#: The runner passes the nonce through this variable.
NONCE_ENV_VAR = "PRAMANA_PROVENANCE_NONCE"

#: Read ONCE at import and removed from the environment in the same breath. The runner
#: imports this package before handing control to generated code, so that code sees an
#: environment with no nonce in it.
_NONCE: str | None = os.environ.pop(NONCE_ENV_VAR, None)


def new_nonce() -> str:
    """A fresh nonce for one execution. Parent side only."""
    return secrets.token_hex(16)


def digest(fields: tuple[object, ...], nonce: str) -> str:
    """The stamp for `fields` under `nonce`.

    Fields are rendered with `repr` and joined with a separator that cannot appear in
    a float or an int repr, so distinct field tuples cannot collide by concatenation.
    """
    payload = "\x1f".join(repr(field) for field in fields).encode("utf-8")
    return hmac.new(nonce.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def stamp(fields: tuple[object, ...]) -> str | None:
    """Stamp `fields` with the nonce this process was given.

    Returns None when no nonce is present -- the normal case for unit tests and for
    library use outside the sandbox. An absent stamp is not a failure here; deciding
    what an absent stamp MEANS belongs to the caller that required one.
    """
    if _NONCE is None:
        return None
    return digest(fields, _NONCE)


def verify(candidate_digest: str | None, fields: tuple[object, ...], nonce: str) -> bool:
    """Whether `candidate_digest` is the stamp of `fields` under `nonce`.

    Constant-time comparison, and a missing digest is False rather than an exception:
    the caller is deciding whether to trust a number, and "no stamp" and "wrong stamp"
    both mean "do not trust it".
    """
    if not candidate_digest:
        return False
    return hmac.compare_digest(candidate_digest, digest(fields, nonce))
