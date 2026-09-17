"""Static import policy -- the first of two locks on untrusted generated code.

This module reads the generated source and refuses it BEFORE a subprocess ever sees
it. That ordering is the point: a sandbox that catches a violation at runtime has
already run whatever came before the violating line, and on a machine without
container isolation (a teammate's laptop, CI) there may be no sandbox worth the name.
Static rejection costs microseconds and does not depend on the environment being
configured correctly.

What it is defending
--------------------
PROJECT.md 3 claims no statistical inference passes through the LLM. That claim
survives only if generated code cannot reach a statistics library. Blocking
`import scipy` while leaving `__import__("scipy")` open would make the claim
decorative, so the dynamic escape hatches are blocked by the same pass.

The line it draws, and the one it does not
------------------------------------------
The check is on the generated code's OWN import statements, never transitively.
`pramana.verification.stats` is permitted and internally imports scipy -- that is the
whole design: our audited, known-answer-tested path may use scipy, and untrusted code
may not import it directly. A transitive check would ban the gateway's own stats
module and the gate would fail closed on every claim.

And it is not a security boundary. A determined attacker with code execution has more
paths than an AST walk can enumerate; the threat model here is an LLM that takes a
shortcut, not an adversary. The honest claim is "generated code cannot import an
unaudited statistics library", and `stats/provenance.py` covers the complementary hole
(hand-rolled arithmetic that imports nothing forbidden at all).

Owner: P.P. Satya Karthikeya
Scope: SCOPE.md 2 component 2
"""

from __future__ import annotations

import ast
from collections.abc import Sequence

#: Builtins that would let generated code reach outside the policy: import machinery,
#: arbitrary code execution, and the filesystem. Referencing one at all is a violation,
#: not just calling one -- `f = open` followed by `f(path)` would slip past a
#: call-only check.
FORBIDDEN_BUILTINS: frozenset[str] = frozenset(
    {
        "__import__",
        "eval",
        "exec",
        "compile",
        "open",
        "globals",
        "locals",
        "vars",
        "input",
        "breakpoint",
        "memoryview",
    }
)

#: Modules that are import machinery in their own right. Listed separately from the
#: whitelist check so the refusal says WHY rather than just "not permitted".
IMPORT_MACHINERY: frozenset[str] = frozenset({"importlib", "imp", "runpy", "builtins"})


class ImportPolicyViolation(Exception):
    """Generated code asked for something the policy does not permit.

    Raised before execution, always. The gateway turns it into a fail-closed
    INCONCLUSIVE verdict; it is never recoverable by retrying, since the source that
    violated the policy is deterministic.
    """


def _is_permitted(module: str, allowed: Sequence[str]) -> bool:
    """Whether `module` is on the whitelist, or is a submodule of something on it.

    Prefix matching is on DOTTED SEGMENTS, so `pramana.verification.stats` permits
    `pramana.verification.stats.permutation` but a hypothetical `numpyfoo` is not
    permitted by an entry for `numpy`.
    """
    return any(module == entry or module.startswith(f"{entry}.") for entry in allowed)


def _check_module(module: str, allowed: Sequence[str], node: ast.AST) -> None:
    line = getattr(node, "lineno", "?")
    if module.split(".")[0] in IMPORT_MACHINERY:
        raise ImportPolicyViolation(
            f"line {line}: generated code requests {module!r}, which is import machinery. "
            f"Blocking `import scipy` is pointless if the code can import it dynamically."
        )
    if not _is_permitted(module, allowed):
        raise ImportPolicyViolation(
            f"line {line}: generated code requests {module!r}, which is not on the import "
            f"whitelist {list(allowed)}. Statistics must come from "
            f"pramana.verification.stats, which is audited and known-answer tested -- "
            f"code that computes its own number produces a p-value nobody verified."
        )


def check_imports(source: str, allowed_imports: Sequence[str]) -> None:
    """Refuse `source` unless every import and name it uses is permitted.

    Guarantees: returns None only when the source parses AND every `import` /
    `from ... import` names a permitted module AND no dynamic escape hatch appears
    anywhere in the tree. Raises `ImportPolicyViolation` otherwise -- there is no
    "warn and continue" path, because a warning nobody reads is not a policy.

    Raises `ValueError` for an empty whitelist: that is a misconfiguration, not a
    statement about the code, and it must not be read as "permit nothing" (the gate
    would fail closed on every claim for a reason that looks statistical) or as
    "permit everything".
    """
    if not allowed_imports:
        raise ValueError(
            "allowed_imports is empty. That is a misconfiguration, not a policy: "
            "refusing here rather than guessing whether it means all or nothing."
        )

    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise ImportPolicyViolation(
            f"generated code does not parse ({error.msg} at line {error.lineno}). "
            f"Code we cannot read is code we cannot vouch for."
        ) from error

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_module(alias.name, allowed_imports, node)

        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise ImportPolicyViolation(
                    f"line {node.lineno}: relative import ('{'.' * node.level}"
                    f"{node.module or ''}'). Generated code is a standalone module with no "
                    f"package around it, so a relative import can only be an attempt to "
                    f"reach somewhere it should not."
                )
            _check_module(node.module or "", allowed_imports, node)

        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_BUILTINS:
            raise ImportPolicyViolation(
                f"line {node.lineno}: generated code requests the builtin {node.id!r}, "
                f"which can execute or import arbitrary code regardless of the whitelist."
            )

        elif isinstance(node, ast.Attribute) and _is_dunder(node.attr):
            raise ImportPolicyViolation(
                f"line {node.lineno}: generated code reaches for the dunder attribute "
                f"{node.attr!r}. Introspection chains such as "
                f"().__class__.__subclasses__() walk out of the policy entirely."
            )


def _is_dunder(name: str) -> bool:
    """Whether `name` is a `__dunder__`, the usual door out of a restricted scope."""
    return len(name) > 4 and name.startswith("__") and name.endswith("__")
