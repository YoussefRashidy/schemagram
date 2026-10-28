from Tokens import Token, TokenType
from ASTNodes import *

class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.position = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.position]

    def advance(self):
        token = self.current
        if token.type != TokenType.EOF:
            self.position += 1
        return token

    def expectToken(self, tokenType: TokenType):
        if self.tokens[self.position].type != tokenType:
            raise SyntaxError(f"Expected {tokenType.name}, "
                f"got {self.current.type.name} "
                f"at position {self.current.position}"
            )
        return self.advance()

    def parse(self) -> "Query" :
        query = self.parseQuery()
        self.expectToken(TokenType.EOF)
        return query

    def parseQuery(self)-> "Query" :
        currentType = self.current.type
        if currentType == TokenType.IDENTIFIER:
            return Relation(self.advance().value)
        if currentType == TokenType.SELECT:
            return self.parseSelect()
        if currentType == TokenType.PROJECT:
            return  self.parseProject()

        if currentType == TokenType.JOIN:
            return self.parseJoin()

        if currentType == TokenType.UNION:
            return self.parseSetOperation(Union)

        if currentType == TokenType.INTERSECT:
            return self.parseSetOperation(Intersect)

        if currentType == TokenType.DIFFERENCE:
            return self.parseSetOperation(Difference)

        if currentType == TokenType.AGGREGATE:
            return self.parseAggregate()

        raise SyntaxError(
            f"Expected a query, got {self.current.type.name} "
            f"at position {self.current.position}"
        )


    def parseSelect(self):
        self.expectToken(TokenType.SELECT)
        self.expectToken(TokenType.LPAREN)
        condition = self.parseCondition()
        self.expectToken(TokenType.COMMA)
        query = self.parseQuery()
        self.expectToken(TokenType.RPAREN)
        return Select(condition, query)


    def parseProject(self):
        self.expectToken(TokenType.PROJECT)
        self.expectToken(TokenType.LPAREN)
        columns = self.parseColumnList()
        self.expectToken(TokenType.COMMA)
        query = self.parseQuery()
        self.expectToken(TokenType.RPAREN)
        return Project(columns,query)

    def parseJoin(self):
        self.expectToken(TokenType.JOIN)
        self.expectToken(TokenType.LPAREN)
        condition = self.parseCondition()
        self.expectToken(TokenType.COMMA)
        query1 = self.parseQuery()
        self.expectToken(TokenType.COMMA)
        query2 = self.parseQuery()
        self.expectToken(TokenType.RPAREN)
        return Join(condition,query1,query2)


    def parseSetOperation(self, operator):
        self.advance()
        self.expectToken(TokenType.LPAREN)
        query1 = self.parseQuery()
        self.expectToken(TokenType.COMMA)
        query2 = self.parseQuery()
        self.expectToken(TokenType.RPAREN)
        return operator(query1,query2)

    def parseAggregate(self):
        self.expectToken(TokenType.AGGREGATE)
        self.expectToken(TokenType.LPAREN)
        func = self.expectToken(TokenType.IDENTIFIER)
        self.expectToken(TokenType.COMMA)
        column = self.parseColumnRef()
        self.expectToken(TokenType.COMMA)
        query = self.parseQuery()
        self.expectToken(TokenType.RPAREN)
        return Aggregate(func.value.upper(), column, query)

    def parseCondition(self):
        pass

    def parseColumnList(self):
        self.expectToken(TokenType.LBRACKET)

        columns = [self.parseColumnRef()]

        while self.current.type == TokenType.COMMA:
            self.advance()
            columns.append(self.parseColumnRef())

        self.expectToken(TokenType.RBRACKET)
        return columns

    def parseColumnRef(self) -> "ColumnRef":
        first = self.expectToken(TokenType.IDENTIFIER)
        if self.current.type == TokenType.DOT:
            self.advance()
            second = self.expectToken(TokenType.IDENTIFIER)
            return ColumnRef(name=second.value, table=first.value)
        return ColumnRef(name=first.value)

    COMPARISON_OPS = {
        TokenType.EQ, TokenType.NE, TokenType.LT,
        TokenType.GT, TokenType.LE, TokenType.GE,
    }

    def parseCondition(self) -> "Condition":
        return self.parseOr()

    def parseOr(self) -> "Condition":
        left = self.parseAnd()
        while self.current.type == TokenType.OR:
            self.advance()
            right = self.parseAnd()
            left = Or(left, right)
        return left

    def parseAnd(self) -> "Condition":
        left = self.parseConditionPrimary()
        while self.current.type == TokenType.AND:
            self.advance()
            right = self.parseConditionPrimary()
            left = And(left, right)
        return left

    def parseConditionPrimary(self) -> "Condition":
        if self.current.type == TokenType.LPAREN:
            self.advance()
            condition = self.parseCondition()
            self.expectToken(TokenType.RPAREN)
            return condition
        return self.parseComparison()

    OP_SYMBOLS = {
        TokenType.EQ: "=",
        TokenType.NE: "!=",
        TokenType.LT: "<",
        TokenType.GT: ">",
        TokenType.LE: "<=",
        TokenType.GE: ">=",
    }

    def parseComparison(self) -> "Comparison":
        left = self.parseOperand()

        if self.current.type not in self.OP_SYMBOLS:
            raise SyntaxError(
                f"Expected a comparison operator, got {self.current.type.name} "
                f"at position {self.current.position}"
            )
        op = self.advance()

        right = self.parseOperand()
        return Comparison(left, self.OP_SYMBOLS[op.type], right)

    def parseOperand(self) -> "Operand":
        t = self.current.type
        if t == TokenType.NUMBER or t == TokenType.STRING:
            return Literal(self.advance().value)
        if t == TokenType.IDENTIFIER:
            return self.parseColumnRef()
        raise SyntaxError(
            f"Expected a column or literal, got {self.current.type.name} "
            f"at position {self.current.position}"
        )
