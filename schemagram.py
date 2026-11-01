QUERY_HELP = """\
Query syntax (prefix, nestable; keywords are case-sensitive, '==' is equality)
  <Table>                                    a base table
  SELECT(<cond>, <q>)                        rows of <q> satisfying <cond>
  PROJECT([a, T.b, ...], <q>)                keep the listed columns (duplicates removed)
  JOIN(<cond>, <q1>, <q2>)                   theta join (cross product filtered by <cond>)
  UNION(<q1>, <q2>)   INTERSECT(<q1>, <q2>)   DIFFERENCE(<q1>, <q2>)
  AGGREGATE(<COUNT|SUM|AVG|MIN|MAX>, <col>, <q>)
  <cond>: comparisons (== != < > <= >=) of columns / numbers / "strings", joined by AND, OR, ( )
  Qualify a column with its table when it is ambiguous:  Student.StudentID
"""

import json

from erdiagram.classes import ERDiagram
from relationalvisualizer.classes import DBSchema
from relationalvisualizer.mapper import mapERDiagram
from relationalvisualizer.renderer import renderSchema
from queryexecutor.Lexer import Lexer
from queryexecutor.Parser import Parser
from queryexecutor.Executor import Executor
from queryexecutor.loader import loadDatabases


def renderRelationalSchema() -> None:
    file_name = input("Enter the ER diagram JSON file: ").strip()
    output_name = input("Enter the output file name (without extension): ").strip() or "relational_schema"

    with open(file_name, "r", encoding="utf-8") as f:
        data = json.load(f)

    tables = mapERDiagram(ERDiagram.fromDict(data))
    renderSchema(DBSchema(tables), output_name)
    print(f"Relational schema generated successfully: {output_name}.png")


def printResult(result) -> None:
    header = [column.columnName for column in result.columns]
    rows = [["NULL" if v is None else str(v) for v in row] for row in result.rows]
    widths = [max(len(cell) for cell in column) for column in zip(header, *rows)]
    for line in [header, ["-" * w for w in widths], *rows]:
        print(" | ".join(cell.ljust(w) for cell, w in zip(line, widths)))
    print(f"({len(rows)} rows)")


def runQueries() -> None:
    files = input("Enter the table JSON file(s), separated by commas: ").split(",")
    db = loadDatabases([f.strip() for f in files if f.strip()])
    print("Loaded tables: " + ", ".join(f"{name} ({len(t.rows)} rows)" for name, t in db.items()))
    print(QUERY_HELP)
    executor = Executor(db)
    print("Type a query, or 'quit' to go back.")
    while True:
        text = input("query> ").strip()
        if text.lower() in ("quit", "exit"):
            break
        if not text:
            continue
        try:
            printResult(executor.execute(Parser(Lexer(text).tokenize()).parse()))
        except Exception as e:
            print(f"Error: {e}")


def main() -> None:
    from tui import main as tui_main
    tui_main()


if __name__ == "__main__":
    main()