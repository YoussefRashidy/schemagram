from dataclasses import dataclass , field
from typing import Any


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
class TableSchema:
    name: str
    columns: list[Column] = field(default_factory=list)
    foreignKeys: list[ForeignKey] = field(default_factory=list)

@dataclass
class DBSchema:
    tables: list[TableSchema] = field(default_factory=list)

@dataclass
class Table:
    tableSchema: TableSchema
    rows: list[dict[str,Any]] = field(default_factory=list)

    @property
    def name(self):
        return self.tableSchema.name

    @property
    def columns(self):
        return [column.name for column in self.tableSchema.columns]

@dataclass
class DataBase:
    tables: dict[str, Table] = field(default_factory=dict)