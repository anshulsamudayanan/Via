"""A small, fast, non-recursive S-expression parser.

KiCad (and several other EDA formats) store designs as S-expressions. This
module only deals with *syntax*; turning the tree into PCB semantics is the job
of a format adapter.

Representation
--------------
* A list node is a :class:`SExpr` (a ``list`` subclass) whose first element is
  normally a :class:`Symbol` naming the node, e.g. ``(at 1 2)`` ->
  ``SExpr([Symbol("at"), Symbol("1"), Symbol("2")])``.
* Unquoted atoms are :class:`Symbol` instances, quoted atoms are plain ``str``.
  Both are ``str`` so callers rarely need to care, but the distinction is kept
  for round-tripping and for formats where it matters.

The parser is iterative so deeply nested files cannot exhaust the Python
recursion limit, and it never evaluates input.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

__all__ = ["SExpr", "SExprParseError", "Symbol", "parse_sexpr"]

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<open>\()
  | (?P<close>\))
  | (?P<string>"(?:[^"\\]|\\.)*")
  | (?P<atom>[^\s()"]+)
  | (?P<bad>")
    """,
    re.VERBOSE | re.DOTALL,
)

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}


class SExprParseError(ValueError):
    """Raised when the input is not a well-formed S-expression."""

    def __init__(self, message: str, text: str = "", pos: int | None = None) -> None:
        if pos is not None and text:
            line = text.count("\n", 0, pos) + 1
            col = pos - (text.rfind("\n", 0, pos) + 1) + 1
            message = f"{message} (line {line}, column {col})"
            self.line: int | None = line
            self.column: int | None = col
        else:
            self.line = None
            self.column = None
        super().__init__(message)


class Symbol(str):
    """An unquoted atom."""

    __slots__ = ()

    def __repr__(self) -> str:
        return f"Symbol({str.__repr__(self)})"


class SExpr(list):
    """A list node with convenience accessors used by adapters."""

    __slots__ = ()

    @property
    def name(self) -> str | None:
        head = self[0] if self else None
        return str(head) if isinstance(head, str) else None

    @property
    def args(self) -> list:
        """Everything after the node name."""
        return self[1:]

    def atoms(self) -> list[str]:
        """Atom arguments only (nested lists skipped)."""
        return [a for a in self[1:] if not isinstance(a, SExpr)]

    def children(self, name: str | None = None) -> Iterator[SExpr]:
        for item in self[1:]:
            if isinstance(item, SExpr) and (name is None or item.name == name):
                yield item

    def child(self, name: str) -> SExpr | None:
        return next(self.children(name), None)

    def has_atom(self, value: str) -> bool:
        return any(not isinstance(a, SExpr) and a == value for a in self[1:])

    def atom(self, name: str, index: int = 0, default: str | None = None) -> str | None:
        """Return the ``index``-th atom of the first child called ``name``."""
        node = self.child(name)
        if node is None:
            return default
        atoms = node.atoms()
        return atoms[index] if index < len(atoms) else default

    def number(self, name: str, index: int = 0, default: float | None = None) -> float | None:
        raw = self.atom(name, index)
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    def numbers(self, name: str) -> list[float]:
        node = self.child(name)
        if node is None:
            return []
        out: list[float] = []
        for a in node.atoms():
            try:
                out.append(float(a))
            except ValueError:
                continue
        return out


def _unescape(raw: str) -> str:
    body = raw[1:-1]
    if "\\" not in body:
        return body
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            out.append(_ESCAPES.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_sexpr(text: str) -> SExpr:
    """Parse ``text`` and return the single top-level expression.

    Raises :class:`SExprParseError` on malformed input or when the document
    contains anything other than exactly one top-level list.
    """
    stack: list[SExpr] = []
    root: SExpr | None = None
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup
        if kind == "ws":
            continue
        if kind == "open":
            if root is not None and not stack:
                raise SExprParseError("Unexpected data after top-level expression", text, m.start())
            node = SExpr()
            if stack:
                stack[-1].append(node)
            stack.append(node)
        elif kind == "close":
            if not stack:
                raise SExprParseError("Unbalanced ')'", text, m.start())
            node = stack.pop()
            if not stack:
                root = node
        elif kind == "string" or kind == "atom":
            if not stack:
                raise SExprParseError("Atom outside of any expression", text, m.start())
            value = _unescape(m.group()) if kind == "string" else Symbol(m.group())
            stack[-1].append(value)
        else:  # bad
            raise SExprParseError("Unterminated string literal", text, m.start())
    if stack:
        raise SExprParseError(f"Unexpected end of input: {len(stack)} unclosed '('")
    if root is None:
        raise SExprParseError("Empty document")
    return root
