# Relational Query Executor

The query executor loads one or more JSON files containing table data and
evaluates a small, nestable relational-algebra language. It includes a lexer,
parser, AST, and executor, and is exposed through the interactive shell in
`schemagram.py`.

## Features

- Relations, selection, projection, theta joins, and set operations
- `UNION`, `INTERSECT`, and directional `DIFFERENCE`
- `COUNT`, `SUM`, `AVG`, `MIN`, and `MAX` aggregates
- Nested queries and parenthesized boolean conditions
- Qualified column references such as `Student.StudentID`
- SQL-style behavior where comparisons involving `NULL` are false
- Set semantics: duplicate input records and duplicate projected rows are
  removed while preserving first-seen order
- Validation for unknown relations or columns, ambiguous references,
  incompatible set-operation arity, invalid syntax, and unsupported values

## Project Structure

| File | Purpose |
|---|---|
| `loader.py` | Loads and merges JSON tables into `Result` objects |
| `Lexer.py` | Tokenizes query text |
| `Parser.py` | Parses tokens into query and condition AST nodes |
| `ASTNodes.py` | Dataclasses representing queries, expressions, and operands |
| `Executor.py` | Evaluates the AST against the loaded database |
| `classes.py` | `Column` and `Result` data structures |
| `../schemagram.py` | Interactive query shell |

## Input Format

Each JSON file is an object whose keys are table names and whose values are
arrays of records:

```json
{
  "Students": [
    { "StudentID": 1, "Name": "Sara", "GPA": 3.8 },
    { "StudentID": 2, "Name": "Omar", "GPA": 3.4 }
  ]
}
```

Column names are the union of keys found across all records in first-seen
order. Missing values are represented as `NULL` (`None` in Python). Nested
arrays and objects are rejected. When multiple files are loaded, a table name
may appear in only one file.

## Usage

Run the application from the repository root:

```bash
python schemagram.py
```

Choose **2. Load tables and run queries**, then enter one or more comma-
separated JSON paths:

```text
Enter the table JSON file(s), separated by commas: examples/university_people.json, examples/university_courses.json
```

After loading the database, the shell prints the query syntax reference and
accepts queries directly at `query>`. Enter `quit` or `exit` to leave the
prompt. The included
[`examples/university_queries.rql`](../examples/university_queries.rql)
contains a collection of queries that can be copied into the shell.

## Query Syntax

The query prompt displays this reference:

```text
Query syntax (prefix, nestable; keywords are case-sensitive, '==' is equality)
  <Table>                                    a base table
  SELECT(<cond>, <q>)                        rows of <q> satisfying <cond>
  PROJECT([a, T.b, ...], <q>)                keep the listed columns (duplicates removed)
  JOIN(<cond>, <q1>, <q2>)                   theta join (cross product filtered by <cond>)
  UNION(<q1>, <q2>)   INTERSECT(<q1>, <q2>)   DIFFERENCE(<q1>, <q2>)
  AGGREGATE(<COUNT|SUM|AVG|MIN|MAX>, <col>, <q>)
  <cond>: comparisons (== != < > <= >=) of columns / numbers / "strings", joined by AND, OR, ( )
  Qualify a column with its table when it is ambiguous:  Student.StudentID
```

Keywords are case-sensitive and must be uppercase. Queries are prefix
expressions and can be nested:

```text
<Table>
SELECT(<condition>, <query>)
PROJECT([column, Table.column, ...], <query>)
JOIN(<condition>, <query>, <query>)
UNION(<query>, <query>)
INTERSECT(<query>, <query>)
DIFFERENCE(<query>, <query>)
AGGREGATE(<COUNT|SUM|AVG|MIN|MAX>, <column>, <query>)
```

Conditions support column references, numeric literals, double-quoted string
literals, comparisons, `AND`, `OR`, and parentheses:

```text
PROJECT([StudentID, Name],
  SELECT(GPA >= 3.5 AND Name != "Omar", Students))
```

Supported comparison operators are `==`, `!=`, `<`, `>`, `<=`, and `>=`.
Use `==` for equality; a single `=` is not valid query syntax. Qualify a
column when a query contains duplicate column names:

```text
JOIN(Student.StudentID == Enrolled_In.Student_StudentID,
     Student, Enrolled_In)
```

## Semantics and Errors

- `PROJECT` removes duplicate result rows.
- Set operations require both operands to have the same number of columns.
  Result column names come from the left operand.
- `JOIN` concatenates the left and right schemas and keeps rows satisfying its
  condition.
- Aggregates ignore `NULL` values. On an empty input, `COUNT` and `SUM` return
  `0`; `AVG`, `MIN`, and `MAX` return `NULL`.
- `DIFFERENCE(left, right)` returns rows present in `left` but not in `right`.
- Errors are reported by the shell as `Error: ...`; the parser and executor
  raise `SyntaxError`, `NameError`, `TypeError`, or `ValueError` for callers
  using the Python API.

## Python API

```python
from queryexecutor.Executor import Executor
from queryexecutor.Lexer import Lexer
from queryexecutor.Parser import Parser
from queryexecutor.loader import loadDatabases

database = loadDatabases(["examples/university_people.json"])
query = "PROJECT([FirstName, GPA], SELECT(GPA >= 3.5, Student))"
ast = Parser(Lexer(query).tokenize()).parse()
result = Executor(database).execute(ast)

print([column.columnName for column in result.columns])
print(result.rows)
```
