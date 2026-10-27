from dataclasses import dataclass , field

@dataclass
class Column:
    name: str
    isPrimaryKey: bool = False
    isForeignKey: bool = False

@dataclass
class ForeignKey:
    refTable: str
    columns: list[str] = field(default_factory=list)
    refColumns: list[str] = field(default_factory=list)

@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)
    foreignKeys: list[ForeignKey] = field(default_factory=list)

@dataclass
class DBSchema:
    tables: list[Table] = field(default_factory=list)