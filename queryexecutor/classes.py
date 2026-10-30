from dataclasses import dataclass

@dataclass(frozen=True)
class Column:
    columnName: str
    qualifier: str | None

@dataclass
class Result:
    columns: list[Column]
    rows: list[tuple]