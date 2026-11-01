from __future__ import annotations

import html
import json
from pathlib import Path

import graphviz

from erdiagram.classes import Attribute, ERDiagram, Entity, Relationship
from relationalvisualizer.classes import DBSchema
from relationalvisualizer.mapper import mapERDiagram
from relationalvisualizer.renderer import renderSchema


def renderERDiagram(data: dict, output: str, engine: str = "sfdp") -> str:
    """Render an ER JSON dict to PNG (same visual conventions as erdiagram/main.py)."""
    erdiagram = ERDiagram.fromDict(data)
    graph = graphviz.Graph(
        format="png", engine=engine,
        graph_attr={"overlap": "false", "splines": "true", "sep": "+12", "dpi": "200"},
        node_attr={"fontname": "Times-Roman", "fontsize": "10"},
        edge_attr={"penwidth": "0.6", "fontname": "Times-Roman", "fontsize": "10"},
    )
    entity_ids: dict[str, str] = {}

    def attribute_label(attribute: Attribute) -> str:
        if attribute.isPrimaryKey:
            return f"<<U>{html.escape(attribute.name)}</U>>"
        if attribute.isPartialKey:
            return (
                '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
                f'<TR><TD BORDER="1" SIDES="B" STYLE="dashed">{html.escape(attribute.name)}</TD></TR>'
                "</TABLE>>"
            )
        return attribute.name

    def render_attribute(attribute: Attribute, parent_id: str) -> None:
        attribute_id = f"{parent_id}_{attribute.name}"
        graph.node(attribute_id, label=attribute_label(attribute), shape="ellipse",
                   peripheries="2" if attribute.isMultiValue else "1",
                   style="dashed" if attribute.isDerived else "solid")
        graph.edge(parent_id, attribute_id)
        for child in attribute.composite:
            render_attribute(child, attribute_id)

    for index, entity in enumerate(erdiagram.entities):
        entity_id = f"entity_{index}"
        entity_ids[entity.name] = entity_id
        graph.node(entity_id, label=entity.name, shape="box",
                   peripheries="2" if entity.isWeak else "1",
                   style="filled", fillcolor="gray", color="black")
        for attribute in entity.attributes:
            render_attribute(attribute, entity_id)

    for index, relationship in enumerate(erdiagram.relationships):
        relationship_id = f"relationship_{index}"
        graph.node(relationship_id, label=relationship.name, shape="diamond",
                   peripheries="2" if relationship.isIdentifying else "1",
                   style="filled", fillcolor="gray", color="black")
        for participant in relationship.participants:
            label = (f"{participant.role} ({participant.cardinality})"
                     if participant.role else participant.cardinality)
            graph.edge(relationship_id, entity_ids[participant.entity], label=label,
                       penwidth="2" if participant.isTotalParticipation else "1")
        for attribute in relationship.attributes:
            render_attribute(attribute, relationship_id)

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    return graph.render(output, cleanup=True)


def renderRelationalSchema(data: dict, output: str) -> tuple[str, str]:
    tables = mapERDiagram(ERDiagram.fromDict(data))
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    target = renderSchema(DBSchema(tables), output)
    return target, describeSchema(tables)


def describeSchema(tables) -> str:
    lines = []
    for table in tables:
        lines.append(table.name)
        for column in table.columns:
            flags = ", ".join(flag for flag, enabled in
                              (("PK", column.isPrimaryKey), ("FK", column.isForeignKey))
                              if enabled)
            lines.append(f"  {column.name}" + (f" ({flags})" if flags else ""))
        for foreign_key in table.foreignKeys:
            lines.append(f"  FK ({', '.join(foreign_key.columns)}) -> "
                         f"{foreign_key.refTable}({', '.join(foreign_key.refColumns)})")
    return "\n".join(lines)
