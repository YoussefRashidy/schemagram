import pytest

from queryexecutor.Tokens import Token, TokenType
from queryexecutor.Parser import Parser
from queryexecutor.ASTNodes import (
    Relation,
    Select,
    Project,
    Join,
    Union,
    Intersect,
    Difference,
    Aggregate,
    ColumnRef,
    Comparison,
    And,
    Or,
    Literal,
)



def token(token_type, value=None, position=0):
    """Create a token for testing."""
    return Token(
        type=token_type,
        value=value,
        position=position,
    )


def parse(*tokens):
    """Parse a sequence of tokens, automatically appending EOF."""
    if not tokens or tokens[-1].type != TokenType.EOF:
        tokens = (*tokens, token(TokenType.EOF))

    return Parser(list(tokens)).parse()


def ident(name, position=0):
    return token(TokenType.IDENTIFIER, name, position)


def number(value, position=0):
    return token(TokenType.NUMBER, value, position)


def string(value, position=0):
    return token(TokenType.STRING, value, position)


def symbol(token_type, position=0):
    return token(token_type, position=position)


# --------------------------------------------------
# Basic queries
# --------------------------------------------------

def test_parse_relation():
    ast = parse(ident("Students"))

    assert isinstance(ast, Relation)
    assert ast.name == "Students"


def test_parse_projection():
    ast = parse(
        symbol(TokenType.PROJECT),
        symbol(TokenType.LPAREN),
        symbol(TokenType.LBRACKET),
        ident("name"),
        symbol(TokenType.COMMA),
        ident("age"),
        symbol(TokenType.RBRACKET),
        symbol(TokenType.COMMA),
        ident("Students"),
        symbol(TokenType.RPAREN),
    )

    assert isinstance(ast, Project)
    assert len(ast.columns) == 2
    assert isinstance(ast.query, Relation)
    assert ast.query.name == "Students"


def test_parse_selection():
    ast = parse(
        symbol(TokenType.SELECT),
        symbol(TokenType.LPAREN),
        ident("age"),
        symbol(TokenType.GT),
        number(18),
        symbol(TokenType.COMMA),
        ident("Students"),
        symbol(TokenType.RPAREN),
    )

    assert isinstance(ast, Select)
    assert isinstance(ast.condition, Comparison)
    assert isinstance(ast.query, Relation)


def test_parse_join():
    ast = parse(
        symbol(TokenType.JOIN),
        symbol(TokenType.LPAREN),
        ident("Students"),
        symbol(TokenType.DOT),
        ident("id"),
        symbol(TokenType.EQ),
        ident("Enrollments"),
        symbol(TokenType.DOT),
        ident("student_id"),
        symbol(TokenType.COMMA),
        ident("Students"),
        symbol(TokenType.COMMA),
        ident("Enrollments"),
        symbol(TokenType.RPAREN),
    )

    assert isinstance(ast, Join)
    assert isinstance(ast.condition, Comparison)
    assert isinstance(ast.left, Relation)
    assert isinstance(ast.right, Relation)


@pytest.mark.parametrize(
    ("token_type", "ast_type"),
    [
        (TokenType.UNION, Union),
        (TokenType.INTERSECT, Intersect),
        (TokenType.DIFFERENCE, Difference),
    ],
)
def test_parse_set_operations(token_type, ast_type):
    ast = parse(
        symbol(token_type),
        symbol(TokenType.LPAREN),
        ident("Students"),
        symbol(TokenType.COMMA),
        ident("Graduates"),
        symbol(TokenType.RPAREN),
    )

    assert isinstance(ast, ast_type)
    assert isinstance(ast.left, Relation)
    assert isinstance(ast.right, Relation)


def test_parse_aggregate():
    ast = parse(
        symbol(TokenType.AGGREGATE),
        symbol(TokenType.LPAREN),
        ident("sum"),
        symbol(TokenType.COMMA),
        ident("salary"),
        symbol(TokenType.COMMA),
        ident("Employees"),
        symbol(TokenType.RPAREN),
    )

    assert isinstance(ast, Aggregate)
    assert ast.function == "SUM"
    assert isinstance(ast.column, ColumnRef)
    assert isinstance(ast.query, Relation)


# --------------------------------------------------
# Column references
# --------------------------------------------------

def test_parse_unqualified_column():
    ast = parse(
        symbol(TokenType.SELECT),
        symbol(TokenType.LPAREN),
        ident("age"),
        symbol(TokenType.GT),
        number(18),
        symbol(TokenType.COMMA),
        ident("Students"),
        symbol(TokenType.RPAREN),
    )

    assert ast.condition.left.name == "age"
    assert ast.condition.left.table is None


def test_parse_qualified_column():
    ast = parse(
        symbol(TokenType.SELECT),
        symbol(TokenType.LPAREN),
        ident("Students"),
        symbol(TokenType.DOT),
        ident("age"),
        symbol(TokenType.GT),
        number(18),
        symbol(TokenType.COMMA),
        ident("Students"),
        symbol(TokenType.RPAREN),
    )

    column = ast.condition.left

    assert isinstance(column, ColumnRef)
    assert column.table == "Students"
    assert column.name == "age"


# --------------------------------------------------
# Comparisons and literals
# --------------------------------------------------

@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        (TokenType.EQ, "="),
        (TokenType.NE, "!="),
        (TokenType.LT, "<"),
        (TokenType.GT, ">"),
        (TokenType.LE, "<="),
        (TokenType.GE, ">="),
    ],
)
def test_parse_comparison_operators(operator, expected):
    ast = parse(
        symbol(TokenType.SELECT),
        symbol(TokenType.LPAREN),
        ident("age"),
        symbol(operator),
        number(18),
        symbol(TokenType.COMMA),
        ident("Students"),
        symbol(TokenType.RPAREN),
    )

    assert isinstance(ast.condition, Comparison)
    assert ast.condition.operator == expected


def test_parse_string_literal():
    ast = parse(
        symbol(TokenType.SELECT),
        symbol(TokenType.LPAREN),
        ident("name"),
        symbol(TokenType.EQ),
        string("Alice"),
        symbol(TokenType.COMMA),
        ident("Students"),
        symbol(TokenType.RPAREN),
    )

    assert isinstance(ast.condition.right, Literal)
    assert ast.condition.right.value == "Alice"


# --------------------------------------------------
# Logical operators and precedence
# --------------------------------------------------

def test_and_has_higher_precedence_than_or():
    # age > 18 AND grade >= 90 OR name = "Alice"
    #
    # Expected:
    # Or(
    #     And(age > 18, grade >= 90),
    #     name = "Alice"
    # )

    ast = parse(
        symbol(TokenType.SELECT),
        symbol(TokenType.LPAREN),

        ident("age"),
        symbol(TokenType.GT),
        number(18),

        symbol(TokenType.AND),

        ident("grade"),
        symbol(TokenType.GE),
        number(90),

        symbol(TokenType.OR),

        ident("name"),
        symbol(TokenType.EQ),
        string("Alice"),

        symbol(TokenType.COMMA),
        ident("Students"),
        symbol(TokenType.RPAREN),
    )

    condition = ast.condition

    assert isinstance(condition, Or)
    assert isinstance(condition.left, And)
    assert isinstance(condition.right, Comparison)


def test_parentheses_override_precedence():
    # age > 18 AND (grade >= 90 OR name = "Alice")
    #
    # Expected:
    # And(
    #     age > 18,
    #     Or(grade >= 90, name = "Alice")
    # )

    ast = parse(
        symbol(TokenType.SELECT),
        symbol(TokenType.LPAREN),

        ident("age"),
        symbol(TokenType.GT),
        number(18),

        symbol(TokenType.AND),
        symbol(TokenType.LPAREN),

        ident("grade"),
        symbol(TokenType.GE),
        number(90),

        symbol(TokenType.OR),

        ident("name"),
        symbol(TokenType.EQ),
        string("Alice"),

        symbol(TokenType.RPAREN),
        symbol(TokenType.COMMA),
        ident("Students"),
        symbol(TokenType.RPAREN),
    )

    condition = ast.condition

    assert isinstance(condition, And)
    assert isinstance(condition.right, Or)


# --------------------------------------------------
# Nested queries
# --------------------------------------------------

def test_parse_nested_projection_and_selection():
    # PROJECT([name], SELECT(age > 18, Students))

    ast = parse(
        symbol(TokenType.PROJECT),
        symbol(TokenType.LPAREN),
        symbol(TokenType.LBRACKET),
        ident("name"),
        symbol(TokenType.RBRACKET),
        symbol(TokenType.COMMA),

        symbol(TokenType.SELECT),
        symbol(TokenType.LPAREN),
        ident("age"),
        symbol(TokenType.GT),
        number(18),
        symbol(TokenType.COMMA),
        ident("Students"),
        symbol(TokenType.RPAREN),

        symbol(TokenType.RPAREN),
    )

    assert isinstance(ast, Project)
    assert isinstance(ast.query, Select)
    assert isinstance(ast.query.query, Relation)


# --------------------------------------------------
# Invalid input
# --------------------------------------------------

def test_empty_input_raises_syntax_error():
    with pytest.raises(SyntaxError):
        parse()


def test_missing_closing_parenthesis_raises_syntax_error():
    with pytest.raises(SyntaxError):
        parse(
            symbol(TokenType.SELECT),
            symbol(TokenType.LPAREN),
            ident("age"),
            symbol(TokenType.GT),
            number(18),
            symbol(TokenType.COMMA),
            ident("Students"),
        )


def test_missing_comparison_operator_raises_syntax_error():
    with pytest.raises(SyntaxError):
        parse(
            symbol(TokenType.SELECT),
            symbol(TokenType.LPAREN),
            ident("age"),
            number(18),
            symbol(TokenType.COMMA),
            ident("Students"),
            symbol(TokenType.RPAREN),
        )


def test_missing_right_operand_raises_syntax_error():
    with pytest.raises(SyntaxError):
        parse(
            symbol(TokenType.SELECT),
            symbol(TokenType.LPAREN),
            ident("age"),
            symbol(TokenType.GT),
            symbol(TokenType.COMMA),
            ident("Students"),
            symbol(TokenType.RPAREN),
        )


def test_trailing_tokens_raise_syntax_error():
    with pytest.raises(SyntaxError):
        parse(
            ident("Students"),
            ident("Unexpected"),
        )
