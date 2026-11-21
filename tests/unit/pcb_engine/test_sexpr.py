import pytest

from via_pcb.parser import SExpr, SExprParseError, Symbol, parse_sexpr


def test_parses_nested_lists_and_atoms():
    root = parse_sexpr('(kicad_pcb (version 20240108) (net 1 "GND") (at 1.5 -2))')
    assert root.name == "kicad_pcb"
    assert root.atom("version") == "20240108"
    assert root.child("net").atoms() == ["1", "GND"]
    assert root.numbers("at") == [1.5, -2.0]


def test_distinguishes_quoted_and_unquoted_atoms():
    root = parse_sexpr('(a sym "quoted")')
    assert isinstance(root[1], Symbol)
    assert not isinstance(root[2], Symbol)
    assert root[2] == "quoted"


def test_handles_escapes_and_parens_inside_strings():
    root = parse_sexpr(r'(t "a \"b\" (c) \\ d\ne")')
    assert root[1] == 'a "b" (c) \\ d\ne'


def test_empty_string_atom():
    assert parse_sexpr('(net 0 "")').atoms() == ["0", ""]


def test_deep_nesting_does_not_recurse():
    depth = 20000
    root = parse_sexpr("(" * depth + ")" * depth)
    assert isinstance(root, SExpr)


@pytest.mark.parametrize(
    "text, message",
    [
        ("", "Empty document"),
        ("(a (b)", "unclosed"),
        ("(a))", "Unbalanced"),
        ('(a "unterminated)', "Unterminated string"),
        ("(a) (b)", "after top-level"),
        ("atom", "outside"),
    ],
)
def test_malformed_input_raises(text, message):
    with pytest.raises(SExprParseError, match=message):
        parse_sexpr(text)


def test_error_reports_line_and_column():
    with pytest.raises(SExprParseError) as info:
        parse_sexpr('(a\n  (b "x)\n')
    assert info.value.line == 2
    assert info.value.column == 6


def test_accessor_defaults():
    root = parse_sexpr("(fp (at 1 2))")
    assert root.atom("missing") is None
    assert root.number("missing", default=3.0) == 3.0
    assert root.numbers("missing") == []
    assert root.atom("at", 5) is None
