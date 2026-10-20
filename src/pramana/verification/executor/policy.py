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

from pramana.contracts.enums import ClaimType

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
        # Reflection: `getattr(obj, "__subclasses__")` walks straight past the dunder
        # attribute check below, and `type` builds classes at runtime.
        "getattr",
        "setattr",
        "delattr",
        "type",
    }
)

#: The one module under the permitted stats package that generated code may never
#: touch. `provenance.stamp` is what turns a number into evidence; code that can call
#: it can stamp a fabricated number, and the whole check becomes decorative. Blocked
#: by name in every form -- module path, imported name, attribute -- because a
#: submodule of a whitelisted package is otherwise permitted by prefix.
PROVENANCE_MODULE = "provenance"

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
    if PROVENANCE_MODULE in module.split("."):
        raise ImportPolicyViolation(
            f"line {line}: generated code requests {module!r}. The provenance module is "
            f"what stamps a result as evidence; code that can reach it can stamp a "
            f"fabricated number, so it is off the import surface entirely."
        )
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
    anywhere in the tree AND the provenance module and every private (`_`-prefixed)
    name of the stats package stay unreachable. Raises `ImportPolicyViolation`
    otherwise -- there is no "warn and continue" path, because a warning nobody reads
    is not a policy.

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

    module_names = _imported_names(tree)
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
            for alias in node.names:
                _check_imported_name(alias.name, node)

        elif isinstance(node, ast.Name) and node.id == PROVENANCE_MODULE:
            raise ImportPolicyViolation(
                f"line {node.lineno}: generated code names {PROVENANCE_MODULE!r}. The "
                f"provenance module stamps results as evidence and is off limits."
            )

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

        elif isinstance(node, ast.Attribute) and node.attr == PROVENANCE_MODULE:
            # `result.provenance` is the stamp STRING on a vetted result, and the
            # templates must read it to build the payload. `stats.provenance` is the
            # MODULE. Syntactically identical, so the chain's root decides: rooted at
            # an imported name (or an alias of one), it is the module.
            root = _chain_root(node)
            if root is None or root in module_names:
                raise ImportPolicyViolation(
                    f"line {node.lineno}: generated code reaches for the attribute "
                    f"{node.attr!r} through an imported module. Importing a submodule "
                    f"binds it on its package, so `pramana.verification.stats.provenance` "
                    f"is reachable as an attribute even when never imported by name."
                )

        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ImportPolicyViolation(
                f"line {node.lineno}: generated code reaches for the private attribute "
                f"{node.attr!r}. The stats package's private helpers include the one that "
                f"stamps a result, and a leading underscore is the only thing marking "
                f"them as not part of the vetted surface."
            )


def _imported_names(tree: ast.AST) -> frozenset[str]:
    """Every local name bound to a module or an imported object, plus plain aliases.

    `import a.b as m` binds `m`; `import a.b` binds `a`; `from a import f` binds `f`.
    A bare `x = m` rebinding is followed one hop, so `x.provenance` is still caught.
    Anything more indirect is outside the threat model (an LLM taking a shortcut,
    not an adversary), and the runner's stamp check is the lock behind this one.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Name)
            and node.value.id in names
        ):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return frozenset(names)


def _chain_root(node: ast.Attribute) -> str | None:
    """The `Name` an attribute chain hangs off, or None when it hangs off an expression.

    None is treated as suspicious by the caller: `(x).provenance` where `x` is not a
    plain name could be anything, and fail-closed means refusing what cannot be read.
    """
    value: ast.expr = node.value
    while isinstance(value, ast.Attribute):
        value = value.value
    return value.id if isinstance(value, ast.Name) else None


def _check_imported_name(name: str, node: ast.AST) -> None:
    """Refuse `from <module> import <name>` when `name` is private or the stamper.

    `from pramana.verification.stats.permutation import _stamped` would hand generated
    code the function that signs a result, with no forbidden module on the line.
    """
    line = getattr(node, "lineno", "?")
    if name == PROVENANCE_MODULE:
        raise ImportPolicyViolation(
            f"line {line}: generated code imports {name!r}. The provenance module stamps "
            f"results as evidence; code that can reach it can stamp a fabricated number."
        )
    if name.startswith("_"):
        raise ImportPolicyViolation(
            f"line {line}: generated code imports the private name {name!r}. Only the "
            f"public, vetted surface of the stats package is available to generated code."
        )


def _is_dunder(name: str) -> bool:
    """Whether `name` is a `__dunder__`, the usual door out of a restricted scope."""
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


# ---------------------------------------------------------------------------
# W1: the column check
# ---------------------------------------------------------------------------
#
# The HMAC stamp proves a number came out of our library. It cannot prove the library
# was handed the claim's own data: generated code could pass a different column, or a
# silently filtered subset, and the stamp would still verify. This check closes that
# gap statically, before anything runs.
#
# Stated honestly, because it is a static AST check and not a proof: it refuses every
# form of column access and row selection it cannot resolve to the claim's own
# columns, so it errs toward NOT_TESTABLE. It does not execute anything, and it cannot
# see data-dependent filtering hidden inside arithmetic (for example multiplying by a
# 0/1 weight). It closes the common, accidental ways an LLM drifts off the claim; it
# is not a defence against code written to evade it.

#: Methods that select, drop or reorder rows or columns of pandas data. Referencing
#: one anywhere is refused, as with the builtin blacklist, so `f = df.head` followed by
#: `f(10)` cannot slip past a call-only check. Dropping missing values (`dropna`) is
#: deliberately NOT here: pairwise deletion is the stated, documented treatment.
ROW_OR_COLUMN_SELECTING_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "query", "where", "mask", "filter", "head", "tail", "sample", "iloc", "iat",
        "at", "nlargest", "nsmallest", "drop_duplicates", "drop", "isin", "between",
        "truncate", "take", "pipe", "eval", "xs", "pop", "select_dtypes", "reindex",
    }
)  # fmt: skip

_COMPARISON_OPS = (ast.Eq, ast.NotEq)


class ColumnPolicyViolation(Exception):
    """Generated code reads a column or selects rows the claim does not state.

    Raised before execution, always, and never recoverable by retrying: the source is
    deterministic. The gateway records it as a failed test, never a PASS.
    """


def _module_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level `NAME = 'literal'` bindings that are never rebound anywhere else.

    A name that is also assigned inside any function, or assigned twice at module level,
    is dropped: its value could differ at the point of use, so it cannot be resolved
    statically and every use of it is refused.
    """
    counts: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            counts[node.id] = counts.get(node.id, 0) + 1
        elif isinstance(node, ast.arg):
            counts[node.arg] = counts.get(node.arg, 0) + 1
    constants: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and counts.get(node.targets[0].id, 0) == 1
        ):
            constants[node.targets[0].id] = node.value.value
    return constants


def _labels(node: ast.AST, constants: dict[str, str]) -> list[str] | None:
    """The column labels an expression names, or None if it cannot be resolved."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Name) and node.id in constants:
        return [constants[node.id]]
    if isinstance(node, (ast.List, ast.Tuple)):
        resolved: list[str] = []
        for element in node.elts:
            labels = _labels(element, constants)
            if labels is None:
                return None
            resolved.extend(labels)
        return resolved
    return None


def _loads(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def _assigned_names(target: ast.AST) -> list[str]:
    return [n.id for n in ast.walk(target) if isinstance(n, ast.Name)]


def _tainted_names(tree: ast.Module, raw: set[str]) -> set[str]:
    """Names that (transitively) hold data derived from the frame.

    Dict displays do not propagate: a returned result dict that happens to contain a
    data-derived value is not itself a table, and treating it as one would refuse the
    ordinary `out['p_value']` idiom.
    """
    tainted = set(raw)
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            pairs: list[tuple[ast.AST, ast.AST | None]] = []
            if isinstance(node, ast.Assign):
                pairs = [(target, node.value) for target in node.targets]
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                pairs = [(node.target, node.value)]
            elif isinstance(node, (ast.For, ast.comprehension)):
                pairs = [(node.target, node.iter)]
            elif isinstance(node, ast.NamedExpr):
                pairs = [(node.target, node.value)]
            for target, value in pairs:
                if value is None or isinstance(value, ast.Dict):
                    continue
                if _loads(value) & tainted:
                    for name in _assigned_names(target):
                        if name not in tainted:
                            tainted.add(name)
                            changed = True
    return tainted


def _raw_frame_names(tree: ast.Module, functions: dict[str, ast.FunctionDef]) -> set[str]:
    """Names bound to the WHOLE frame: falsify's first parameter and any helper
    parameter that receives it, positionally, from a call in this module."""
    entry = functions["falsify"]
    if not entry.args.args:
        raise ColumnPolicyViolation("falsify must take the frame as its first parameter")
    raw = {entry.args.args[0].arg}
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            callee = functions.get(node.func.id)
            if callee is None:
                continue
            for index, argument in enumerate(node.args):
                if (
                    isinstance(argument, ast.Name)
                    and argument.id in raw
                    and index < len(callee.args.args)
                ):
                    name = callee.args.args[index].arg
                    if name not in raw:
                        raw.add(name)
                        changed = True
    return raw


def _is_full_slice(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Slice)
        and node.lower is None
        and node.upper is None
        and node.step is None
    )


def _is_int_index(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        node = node.operand
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    )


def _is_int_only_index(node: ast.AST) -> bool:
    """`0`, `-1`, or a tuple of them: a position, which cannot express a filter."""
    if isinstance(node, ast.Tuple):
        return bool(node.elts) and all(_is_int_index(element) for element in node.elts)
    return _is_int_index(node)


_POSITIONAL_ACCESSORS = frozenset({"iloc", "iat"})


class _ColumnChecker:
    """Walks one module and raises `ColumnPolicyViolation` at the first problem."""

    def __init__(self, tree: ast.Module, variables: Sequence[str], claim_type: ClaimType) -> None:
        self.tree = tree
        self.allowed = set(variables)
        self.group_column = variables[0] if variables else None
        self.group_claim = claim_type is ClaimType.GROUP_DIFFERENCE
        self.constants = _module_constants(tree)
        functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        if "falsify" not in functions:
            raise ColumnPolicyViolation("the module does not define falsify(frame)")
        self.functions = functions
        self.raw = _raw_frame_names(tree, functions)
        self.tainted = _tainted_names(tree, self.raw)
        self.parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                self.parents[child] = parent

    # -- helpers -----------------------------------------------------------

    def _fail(self, node: ast.AST, message: str) -> ColumnPolicyViolation:
        return ColumnPolicyViolation(f"line {getattr(node, 'lineno', '?')}: {message}")

    def _is_data(self, node: ast.AST) -> bool:
        return bool(_loads(node) & self.tainted)

    def _require_claim_labels(self, node: ast.AST, slice_node: ast.AST) -> None:
        labels = _labels(slice_node, self.constants)
        if labels is None:
            raise self._fail(
                node,
                "a column is selected by an expression that cannot be resolved to the "
                "claim's own columns; name them as string literals or module constants",
            )
        extra = sorted(set(labels) - self.allowed)
        if extra:
            raise self._fail(
                node,
                f"generated code reads column(s) {extra}, which the claim does not "
                f"name; the claim's columns are {sorted(self.allowed)}",
            )

    def _is_group_mask(self, mask: ast.AST) -> bool:
        """`<column of the grouping variable> ==/!= <anything that is not a column>`."""
        if not (
            self.group_claim
            and isinstance(mask, ast.Compare)
            and len(mask.ops) == 1
            and isinstance(mask.ops[0], _COMPARISON_OPS)
        ):
            return False
        left, right = mask.left, mask.comparators[0]
        for column_side, other in ((left, right), (right, left)):
            root = column_side
            while isinstance(root, (ast.Call, ast.Attribute)):
                root = root.func if isinstance(root, ast.Call) else root.value
            if not (isinstance(root, ast.Subscript) and self._is_data(root.value)):
                continue
            if _labels(root.slice, self.constants) != [self.group_column]:
                continue
            reads_a_column = any(
                isinstance(n, ast.Subscript) and _labels(n.slice, self.constants) is not None
                for n in ast.walk(other)
            )
            return not reads_a_column
        return False

    # -- the three kinds of access ----------------------------------------

    def _check_loc(self, subscript: ast.Subscript, on_raw: bool) -> None:
        index = subscript.slice
        if not (isinstance(index, ast.Tuple) and len(index.elts) == 2):
            raise self._fail(subscript, ".loc must be written as .loc[rows, columns]")
        rows, columns = index.elts
        if not _is_full_slice(rows) and not self._is_group_mask(rows):
            raise self._fail(
                subscript,
                "generated code filters rows in a way the claim does not state; only "
                "all rows, or one level of a group_difference claim's own grouping "
                "column, may be selected",
            )
        if _is_full_slice(columns):
            if on_raw:
                raise self._fail(subscript, "selecting every column of the frame is refused")
        else:
            self._require_claim_labels(subscript, columns)

    def _check_raw_use(self, name: ast.Name) -> None:
        parent = self.parents.get(name)
        if isinstance(name.ctx, ast.Store):
            raise self._fail(name, f"the frame name {name.id!r} is re-bound; refused")
        if isinstance(parent, ast.Subscript) and parent.value is name:
            self._require_claim_labels(parent, parent.slice)
            return
        if isinstance(parent, ast.Attribute) and parent.value is name and parent.attr == "loc":
            grand = self.parents.get(parent)
            if isinstance(grand, ast.Subscript) and grand.value is parent:
                self._check_loc(grand, on_raw=True)
                return
        if (
            isinstance(parent, ast.Call)
            and name in parent.args
            and isinstance(parent.func, ast.Name)
            and (parent.func.id in self.functions or parent.func.id == "len")
        ):
            return
        raise self._fail(
            name,
            f"the whole frame {name.id!r} is used outside a column selection "
            f"(attribute access, copy, alias or a call); select the claim's columns "
            f"first, for example frame[[VAR_X, VAR_Y]]",
        )

    def _is_int_positional(self, attribute: ast.Attribute) -> bool:
        """`x.iloc[0, 1]` / `x.iat[0, 1]`: integer positions only, never a slice or mask."""
        parent = self.parents.get(attribute)
        return (
            isinstance(parent, ast.Subscript)
            and parent.value is attribute
            and _is_int_only_index(parent.slice)
        )

    def _check_other_node(self, node: ast.AST) -> None:
        if isinstance(node, ast.Attribute):
            if node.attr in _POSITIONAL_ACCESSORS and self._is_int_positional(node):
                return
            if node.attr in ROW_OR_COLUMN_SELECTING_ATTRIBUTES:
                raise self._fail(
                    node,
                    f"`.{node.attr}` selects or drops rows/columns the claim does not "
                    f"state; refused",
                )
            if node.attr == "loc":
                grand = self.parents.get(node)
                if not (isinstance(grand, ast.Subscript) and grand.value is node):
                    raise self._fail(node, "`.loc` used other than as .loc[rows, columns]")
            return
        if not isinstance(node, ast.Subscript):
            return
        base = node.value
        if (
            isinstance(base, ast.Attribute)
            and base.attr in _POSITIONAL_ACCESSORS
            and _is_int_only_index(node.slice)
        ):
            return
        if isinstance(base, ast.Attribute) and base.attr == "loc":
            if not (isinstance(base.value, ast.Name) and base.value.id in self.raw):
                self._check_loc(node, on_raw=False)
            return
        if isinstance(base, ast.Name) and base.id in self.raw:
            return  # handled by _check_raw_use
        if not self._is_data(base):
            return  # indexing a list of labels or a result dict is not reading the data
        index = node.slice
        if _is_int_index(index):
            return
        if _labels(index, self.constants) is not None:
            self._require_claim_labels(node, index)
            return
        raise self._fail(
            node,
            "data is indexed by a slice, mask or expression the claim does not state "
            "(a row filter); only the claim's own columns may be selected",
        )

    def run(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Name) and node.id in self.raw:
                self._check_raw_use(node)
            self._check_other_node(node)


def check_columns(source: str, variables: Sequence[str], claim_type: ClaimType) -> None:
    """Refuse `source` unless it reads only the claim's columns and filters only as stated.

    Guarantees: returns None only when the source parses, defines `falsify`, and every
    column access resolves statically to a member of `variables`; the whole frame is
    never aliased, copied or handed to anything but a helper defined in the same
    module; and no row is selected except all of them, or -- for a group_difference
    claim only -- by equality on the grouping column (`variables[0]`), which is how
    such a claim defines its groups. Anything it cannot resolve is refused, so a
    failure to understand the code is never a pass (AGENTS.md 4).

    Raises `ColumnPolicyViolation` otherwise. This is a static check: see the note at
    the top of this section for what it does not see.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise ColumnPolicyViolation(f"the module does not parse: {error}") from error
    _ColumnChecker(tree, variables, claim_type).run()
