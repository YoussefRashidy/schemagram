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
    erdiagram = ERDiagram.fromDict(data)
    graph = graphviz.Graph(format="png", engine=engine)
    entity_ids = {}

    def attribute_label(attribute: Attribute) -> str:
        if attribute.isPrimaryKey:
            return f"<<U>{html.escape(attribute.name)}</U>>"
        return html.escape(attribute.name)

    def render_attribute(attribute: Attribute, parent_id: str) -> None:
        attribute_id = f"{parent_id}_{attribute.name}"
        graph.node(attribute_id, label=attribute_label(attribute), shape="ellipse")
        graph.edge(parent_id, attribute_id)
        for child in attribute.composite:
            render_attribute(child, attribute_id)

    for index, entity in enumerate(erdiagram.entities):
        entity_id = f"entity_{index}"
        entity_ids[entity.name] = entity_id
        graph.node(entity_id, label=entity.name, shape="box",
                   peripheries="2" if entity.isWeak else "1")
        for attribute in entity.attributes:
            render_attribute(attribute, entity_id)

    for index, relationship in enumerate(erdiagram.relationships):
        relationship_id = f"relationship_{index}"
        graph.node(relationship_id, label=relationship.name, shape="diamond",
                   peripheries="2" if relationship.isIdentifying else "1")
        for participant in relationship.participants:
            graph.edge(relationship_id, entity_ids[participant.entity],
                       label=participant.cardinality)
        for attribute in relationship.attributes:
            render_attribute(attribute, relationship_id)

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    target = graph.render(output, cleanup=True)
    return target


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
