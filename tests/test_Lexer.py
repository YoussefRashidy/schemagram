
import pytest

from queryexecutor.Lexer import Lexer
from queryexecutor.Tokens import TokenType


def tokenize(source: str):
    return Lexer(source).tokenize()


def test_select_query():
    tokens = tokenize("SELECT(Salary >= 5500, Employee)")

    assert [t.type for t in tokens] == [
        TokenType.SELECT,
        TokenType.LPAREN,
        TokenType.IDENTIFIER,
        TokenType.GE,
        TokenType.NUMBER,
        TokenType.COMMA,
        TokenType.IDENTIFIER,
        TokenType.RPAREN,
        TokenType.EOF,
    ]

    assert tokens[2].value == "Salary"
    assert tokens[4].value == 5500


def test_keywords_are_case_insensitive():
    tokens = tokenize("select(Name, Employee)")

    assert tokens[0].type == TokenType.SELECT
    assert tokens[2].value == "Name"
    assert tokens[3].value == TokenType.COMMA or tokens[3].type == TokenType.COMMA


def test_identifiers_with_underscores_and_digits():
    tokens = tokenize("Employee_2.Dept_ID")

    assert [(t.type, t.value) for t in tokens[:-1]] == [
        (TokenType.IDENTIFIER, "Employee_2"),
        (TokenType.DOT, "."),
        (TokenType.IDENTIFIER, "Dept_ID"),
    ]


@pytest.mark.parametrize(
    ("operator", "expected_type"),
    [
        ("==", TokenType.EQ),
        ("!=", TokenType.NE),
        ("<", TokenType.LT),
        ("<=", TokenType.LE),
        (">", TokenType.GT),
        (">=", TokenType.GE),
    ],
)
def test_operators(operator, expected_type):
    tokens = tokenize(f"SELECT(A {operator} 10, Employee)")

    assert tokens[3].type == expected_type
    assert tokens[3].value == operator


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("42", 42),
        ("-5", -5),
        ("3.14", 3.14),
        (".5", 0.5),
        ("-.5", -0.5),
        ("1.2e-3", 0.0012),
    ],
)
def test_numbers(source, expected):
    tokens = tokenize(source)

    assert tokens[0].type == TokenType.NUMBER
    assert tokens[0].value == pytest.approx(expected)
    assert tokens[1].type == TokenType.EOF


def test_string():
    tokens = tokenize('SELECT(Name == "Alexandria", Employee)')

    assert tokens[4].type == TokenType.STRING
    assert tokens[4].value == "Alexandria"


def test_nested_query():
    tokens = tokenize(
        "PROJECT([Name], SELECT(Salary > 5000, Employee))"
    )

    assert tokens[0].type == TokenType.PROJECT
    assert tokens[1].type == TokenType.LPAREN
    assert tokens[2].type == TokenType.LBRACKET
    assert tokens[4].type == TokenType.RBRACKET
    assert tokens[6].type == TokenType.SELECT
    assert tokens[7].type == TokenType.LPAREN
    assert tokens[-2].type == TokenType.RPAREN
    assert tokens[-1].type == TokenType.EOF


def test_whitespace_is_ignored():
    tokens = tokenize("  SELECT ( Name , Employee ) \n")

    assert [t.type for t in tokens] == [
        TokenType.SELECT,
        TokenType.LPAREN,
        TokenType.IDENTIFIER,
        TokenType.COMMA,
        TokenType.IDENTIFIER,
        TokenType.RPAREN,
        TokenType.EOF,
    ]


def test_unclosed_string_raises_syntax_error():
    with pytest.raises(SyntaxError):
        tokenize('SELECT(Name == "Alexandria)')


def test_unexpected_character_raises_syntax_error():
    with pytest.raises(SyntaxError):
        tokenize("SELECT(@, Employee)")
