# Relational Schema Visualizer

The relational schema visualizer converts an ER diagram JSON document into a
PNG diagram of the relational schema. It applies the ER-to-relational mapping
rules implemented in `mapper.py`, then uses Graphviz to render tables,
columns, primary keys, and foreign-key relationships.

## Features

- Maps strong entities to tables.
- Converts composite attributes into their component columns.
- Omits derived attributes.
- Converts multivalued attributes into separate tables linked to their owner.
- Maps weak entities using the identifying entity keys and partial keys.
- Maps binary and n-ary relationships, including many-to-many relationships,
  to foreign keys or junction tables as appropriate.
- Preserves relationship attributes on the table that represents the
  relationship.
- Highlights primary-key columns and marks foreign-key columns in the output.
- Detects table-name and column-name collisions before rendering.

## Project Structure

| File | Purpose |
|---|---|
| `classes.py` | Dataclasses for columns, foreign keys, tables, and database schemas |
| `mapper.py` | Converts an `ERDiagram` into a list of `TableSchema` objects |
| `renderer.py` | Builds and renders the Graphviz relational-schema diagram |
| `../schemagram.py` | Interactive entry point that loads the ER JSON and invokes the visualizer |

## Requirements

- Python 3.10+
- The [Graphviz](https://graphviz.org/download/) binaries installed and on
  your `PATH` (the Python package alone is not enough)
- Python packages:

```bash
pip install -r requirements.txt
```

The required packages include `graphviz`, `google-genai`, `python-dotenv`, and
`textual`. Only `graphviz` is needed by the visualizer itself.

## Usage

Run the application from the repository root:

```bash
python schemagram.py
```

Choose **1. Render relational schema from an ER diagram file**, then provide:

1. The path to an ER diagram JSON file following
   [`erdiagram/er_json_schema.md`](../erdiagram/er_json_schema.md)
2. An output name without an extension

The result is written as `<output_name>.png`. If the output name is empty,
`relational_schema.png` is used.

For example:

```text
=== Schemagram ===
1. Render relational schema from an ER diagram file
2. Load tables and run queries
3. Exit
Enter your choice (1/2/3): 1
Enter the ER diagram JSON file: examples/university_er.json
Enter the output file name (without extension): out/university_relational_schema
```

The renderer uses Graphviz's `dot` layout engine and cleans up the
intermediate `.gv` file after creating the PNG.

## Mapping Notes

- Primary keys are underlined in the diagram.
- Foreign keys are italicized. A column that is both a primary key and a
  foreign key is shown with both roles.
- A one-to-many relationship places the referenced key in the many-side table.
- A many-to-many relationship creates a junction table containing foreign keys
  to both participating tables.
- A multivalued attribute of a weak entity creates a separate table containing
  the weak entity's complete primary key and the multivalued value. The key
  columns also form a foreign key back to the weak entity.
- Relationship roles are used to disambiguate self-referential relationships.
- Weak entities require an identifying relationship and a partial key.
- Unsupported or ambiguous mappings raise `ValueError` with a diagnostic
  message instead of producing an incomplete diagram.

## Python API

The main functions can also be used directly:

```python
import json

from erdiagram.classes import ERDiagram
from relationalvisualizer.classes import DBSchema
from relationalvisualizer.mapper import mapERDiagram
from relationalvisualizer.renderer import renderSchema

with open("examples/university_er.json", encoding="utf-8") as file:
    diagram = ERDiagram.fromDict(json.load(file))

tables = mapERDiagram(diagram)
renderSchema(DBSchema(tables), "out/university_relational_schema")
```
