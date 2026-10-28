import re

from queryexecutor.Tokens import Token, TokenType

KEYWORDS = {
    "SELECT": TokenType.SELECT,
    "PROJECT": TokenType.PROJECT,
    "JOIN": TokenType.JOIN,
    "UNION": TokenType.UNION,
    "INTERSECT": TokenType.INTERSECT,
    "DIFFERENCE": TokenType.DIFFERENCE,
    "AGGREGATE": TokenType.AGGREGATE,
    "AND": TokenType.AND,
    "OR": TokenType.OR,
}

SINGLE_CHAR_TOKENS = {
    ".": TokenType.DOT,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
    ",": TokenType.COMMA,
    "<": TokenType.LT,
    ">": TokenType.GT,
}

MULTI_CHAR_TOKENS = {
    "==": TokenType.EQ,
    "!=": TokenType.NE,
    "<=": TokenType.LE,
    ">=": TokenType.GE,
}

NUMBER_PATTERN = re.compile(
    r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
)


class Lexer:
    def __init__(self, input_string: str):
        self.source = input_string
        self.position = 0
        self.length = len(input_string)

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while self.position < self.length:
            char = self.source[self.position]
            if char.isspace():
                self.position += 1
                continue

            if char.isalpha():
                tokens.append(self.tokenizeKeyIdentifier())
                continue

            if self.isNumberStart():
                tokens.append(self.tokenizeNumber())
                continue

            if char == '"':
                tokens.append(self.tokenizeString())
                continue

            if self.tokenizeOperator(tokens):
                continue
            if char in SINGLE_CHAR_TOKENS:
                tokens.append(Token(value=char, type=SINGLE_CHAR_TOKENS[char], position=self.position))
                self.position += 1
                continue

            raise SyntaxError(
                f"Unexpected character {char!r} "
                f"at position {self.position}"
            )

        tokens.append(Token(value=None, type=TokenType.EOF, position=self.position))

        return tokens

    def tokenizeKeyIdentifier(self):
        start = self.position
        while self.position < self.length:
            char = self.source[self.position]
            if char.isalnum() or char == "_":
                self.position += 1
                continue
            else:
                break
        value: str = self.source[start:self.position]
        tokenType: TokenType = KEYWORDS.get(value.upper(), TokenType.IDENTIFIER)
        return Token(value=value, type=tokenType, position=start)

    def isNumberStart(self):
        start = self.position
        char = self.source[self.position]
        if char.isdigit():
            return True
        elif char == ".":
            return start + 1 < self.length and self.source[self.position + 1].isdigit()
        elif char == '-':
            return start + 1 < self.length and (self.source[self.position + 1].isdigit() or (start + 2 < self.length and self.source[self.position + 1] == "." and self.source[self.position + 2].isdigit()))
        return False

    def tokenizeNumber(self):
        start = self.position
        match = NUMBER_PATTERN.match(self.source, self.position)
        if match:
            value = match.group()
            self.position = match.end()

            if '.' in value or 'e' in value.lower():
                number = float(value)
            else:
                number = int(value)
            return Token(value=number, type=TokenType.NUMBER, position=start)
        else:
            raise SyntaxError(f"Invalid number at position {start}")

    def tokenizeString(self):
        start = self.position
        self.position += 1
        while self.position < self.length and self.source[self.position] != '"':
            self.position += 1
        if self.position == self.length and self.source[self.position-1] != '"':
            raise SyntaxError(f"Invalid string at position {start}")

        value = self.source[start+1:self.position]
        self.position += 1

        return Token(value=value, type=TokenType.STRING, position=start)

    def tokenizeOperator(self, tokens) -> bool:
        start = self.position
        for operator, tokenType in MULTI_CHAR_TOKENS.items():
            if self.source.startswith(operator, self.position):
                tokens.append(Token(value=operator, type=tokenType, position=start))
                self.position += len(operator)
                return True

        return False
