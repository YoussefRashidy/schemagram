from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

class TokenType(Enum):
    IDENTIFIER = auto()
    NUMBER = auto()
    STRING = auto()

    SELECT = auto()
    PROJECT = auto()
    JOIN = auto()
    UNION = auto()
    INTERSECT = auto()
    DIFFERENCE = auto()
    AGGREGATE = auto()

    AND = auto()
    OR = auto()

    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    DOT = auto()

    EQ = auto()
    NE = auto()
    LT = auto()
    GT = auto()
    LE = auto()
    GE = auto()

    EOF = auto()

@dataclass(frozen=True)
class Token:
    type: TokenType
    value: Any
    position: int