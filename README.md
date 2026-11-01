# Schemagram

**An interactive toolkit for ER modeling, relational schema design, and relational algebra.**

Schemagram brings database modeling and querying into a single terminal application. Design and visualize ER diagrams, map conceptual models to relational schemas, inspect primary and foreign key relationships, and execute relational algebra queries against sample databases—all through an interactive terminal UI.

### What you can do

| Feature | Description | Module |
|---|---|---|
| **ER Modeling** | Define entities, attributes, and relationships; visualize your model; inspect structural properties; and export diagrams as PNGs. | `erdiagram/` |
| **Relational Schema Design** | Transform ER models into relational schemas, inspect tables and key constraints, visualize foreign-key relationships, and generate SQL DDL. | `relationalvisualizer/` |
| **Relational Algebra** | Write, parse, and execute relational algebra expressions against JSON-based databases, with support for nested queries, intermediate results, and execution plans. | `queryexecutor/` |
| **Interactive Terminal UI** | Explore all three modules through a unified interface with syntax highlighting, autocompletion, query history, and interactive visualizations. | `tui.py`, `tui_render.py` |

Each module can be explored independently, and each directory contains its own README with further details.

## Setup

```bash
pip install -r requirements.txt     # textual, graphviz
```

PNG export also needs the [Graphviz](https://graphviz.org/download/) program (the `dot` command) on your PATH. Everything else, including the whole TUI, works without it.

The optional text-to-ER feature in the plain CLI (`erdiagram/main.py`, choice 2) also needs the `google-genai` package, `python-dotenv`, and `GEMINI_API_KEY` / `GEMINI_MODEL` in your environment or `.env`. The TUI never uses Gemini.

## Run

```bash
python schemagram.py
```

It opens with the sample project in `examples/` already loaded.

### Tabs

- **① ER Diagram (F2):** entity cards, a relationship map, structural checks, and PNG export.
  - Key attributes are underlined, partial keys double-underlined, multi-valued attributes marked `◎`, derived attributes `◌`.
  - In the relationship map `═` means total participation, `─` partial, and `◈` an identifying relationship.
- **② Relational Schema (F3):** the mapped tables as cards, a foreign-key map, or SQL DDL. Column types in the SQL are inferred from the database loaded in the Query Lab, and default to `VARCHAR(100)`, so review them before use.
- **③ Query Lab (F4):**
  - Live syntax highlighting, Tab completion, and an error caret pointing at the exact position.
  - The query is shown in relational-algebra notation as you type.
  - An execution plan shows rows, columns and time per operator. Click or arrow onto any operator to see its intermediate result.
  - History, examples, and CSV export.

### Keys

| Key | Action |
|---|---|
| F1 | Syntax help |
| F2 / F3 / F4 | ER / Schema / Query Lab (`1`, `2`, `3` also work outside text fields) |
| F5, Ctrl+R | Run the query |
| Tab | Complete a keyword, table or column; press again to cycle |
| Ctrl+L | Toggle live execution |
| Ctrl+E | Export the current diagram as PNG |
| Ctrl+P | Command palette (includes theme switching) |
| Esc | Leave the editor |

## Input formats

**ER diagram:** JSON with `entities` and `relationships`. See `erdiagram/er_json_schema.md`; a full example is `examples/university_er.json`.

**Database:** JSON object of table name to list of records. Column names are the union of keys across records. Missing values are `NULL`, nested values are rejected, and duplicate rows are removed.

```json
{ "Students": [ { "StudentID": 1, "Name": "Sara", "GPA": 3.8 } ] }
```

Load several files at once by separating paths with `;`. A table name may appear in only one file.

## Query language

Prefix, nestable, keywords are uppercase and case-sensitive.

| Query | Notation | Meaning |
|---|---|---|
| `Table` | R | base table |
| `SELECT(cond, q)` | σ | rows satisfying `cond` |
| `PROJECT([a, T.b], q)` | π | keep columns, drop duplicates |
| `JOIN(cond, q1, q2)` | ⋈ | theta join |
| `UNION(q1, q2)` | ∪ | rows in either (same arity) |
| `INTERSECT(q1, q2)` | ∩ | rows in both |
| `DIFFERENCE(q1, q2)` | − | rows in `q1` but not `q2` |
| `AGGREGATE(FN, col, q)` | γ | `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`; NULLs ignored |

Conditions compare columns, numbers and `"strings"` with `==  !=  <  >  <=  >=`, combined with `AND`, `OR` and parentheses. Qualify a column as `Table.column` when names clash. Comparing with `NULL` is never true.

```text
PROJECT([FirstName, DeptName],
  SELECT(GPA >= 3.5,
    JOIN(Student.Department_DeptID == Department.DeptID, Student, Department)))
```

More examples: `examples/university_queries.rql`.

## Python API

```python
import json
from erdiagram.classes import ERDiagram
from relationalvisualizer.mapper import mapERDiagram
from queryexecutor.loader import loadDatabases
from queryexecutor.Lexer import Lexer
from queryexecutor.Parser import Parser
from queryexecutor.Executor import Executor

tables = mapERDiagram(ERDiagram.fromDict(json.load(open("examples/university_er.json"))))

db = loadDatabases(["examples/university_people.json", "examples/university_courses.json"])
ast = Parser(Lexer("PROJECT([FirstName, GPA], SELECT(GPA >= 3.5, Student))").tokenize()).parse()
result = Executor(db).execute(ast)
print([c.columnName for c in result.columns], result.rows)
```

## Layout

```text
schemagram.py            entry point (launches the TUI)
tui.py                   Textual app: tabs, editor, plan tree, dialogs
tui_render.py            Rich renderers, highlighter, tracer (no Textual imports)
schemagram_core.py       shared helpers (schema description, PNG export)
erdiagram/               ER model, JSON schema, ER renderer, Gemini text-to-ER
relationalvisualizer/    ER -> relational mapper and schema renderer
queryexecutor/           lexer, parser, AST, executor, JSON loader
examples/                sample ER, tables and queries
```

