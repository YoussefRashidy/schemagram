from dataclasses import dataclass


@dataclass
class Relation:
    name: str


@dataclass
class Select:
    condition: "Condition"
    query: "Query"


@dataclass
class Project:
    columns: list["ColumnRef"]
    query: "Query"


@dataclass
class Join:
    condition: "Condition"
    left: "Query"
    right: "Query"


@dataclass
class Union:
    left: "Query"
    right: "Query"


@dataclass
class Intersect:
    left: "Query"
    right: "Query"


@dataclass
class Difference:
    left: "Query"
    right: "Query"


@dataclass
class Aggregate:
    function: str
    column: "ColumnRef"
    query: "Query"


# ---------- Conditions ----------

@dataclass
class Comparison:
    left: "Operand"
    operator: str
    right: "Operand"


@dataclass
class And:
    left: "Condition"
    right: "Condition"


@dataclass
class Or:
    left: "Condition"
    right: "Condition"


# ---------- Operands ----------

@dataclass
class ColumnRef:
    name: str
    table: str | None = None


@dataclass
class Literal:
    value: int | float | str


Condition = Comparison | And | Or
Operand = ColumnRef | Literal

Query = Relation | Select | Project | Join | Union | Intersect | Difference | Aggregate
