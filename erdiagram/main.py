import html
import itertools
import graphviz
import json
from classes import ERDiagram, Attribute, Entity, Relationship
from model import generateJson
from relationalvisualizer.classes import Column, ForeignKey, TableSchema, DBSchema
from relationalvisualizer.renderer import renderSchema


def renderERDiagram(data ,out: str , engine: str = 'sfdp') -> None:
    erdiagram : ERDiagram = ERDiagram.fromDict(data)
    counter = itertools.count()
    entitiesIds : dict = {}
    graph = graphviz.Graph(
        format='png',
        engine=engine,
        graph_attr={'overlap': 'false', 'splines': 'true', 'sep': '+12', 'dpi': '200'},
        node_attr={'fontname': 'Times-Roman', 'fontsize': '10'},
        edge_attr={'penwidth': '0.6', 'fontname': 'Times-Roman', 'fontsize': '10'}
        )

    def getId() -> str :
        return str(next(counter))

    def getAttributeLabel(attribute : Attribute) -> str:
        if attribute.isPrimaryKey:
            return f"<<U>{html.escape(attribute.name)}</U>>"
        elif attribute.isPartialKey:
            return (
                '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0">'
                f'<TR><TD BORDER="1" SIDES="B" STYLE="dashed">{html.escape(attribute.name)}</TD></TR>'
                '</TABLE>>'
            )
        else :
            return attribute.name

    def renderEntity(entity: Entity) :
        entityId = getId()
        peripheries = "2" if entity.isWeak else "1"
        graph.node(entityId,label=entity.name,shape='box',peripheries=peripheries,style='filled', fillcolor='gray', color='black',)
        entitiesIds[entity.name] = entityId
        for attribute in entity.attributes:
            renderAttribute(attribute, entityId)

    def renderAttribute(attribute : Attribute , entityId:str) :
        attributeId = f"{entityId}_{attribute.name}"
        peripheries = "2" if attribute.isMultiValue else "1"
        style = "dashed" if attribute.isDerived else "solid"
        graph.node(attributeId, label=getAttributeLabel(attribute), shape='ellipse',style=style,peripheries=peripheries)
        graph.edge(entityId, attributeId)

        for innerAttribute in attribute.composite :
            renderAttribute(innerAttribute, attributeId)

    def renderRelationship(relationship : Relationship):
        relationshipId = getId()
        peripheries = "2" if relationship.isIdentifying else "1"
        graph.node(relationshipId, label=relationship.name, shape='diamond', peripheries=peripheries,style='filled', fillcolor='gray', color='black')
        for p in relationship.participants:
            penwidth = "2" if p.isTotalParticipation else "1"
            label = f"{p.role} ({p.cardinality})" if p.role else p.cardinality
            graph.edge(relationshipId, entitiesIds[p.entity], label=label,penwidth=penwidth)
        for attribute in relationship.attributes:
            renderAttribute(attribute, relationshipId)

    for entity in erdiagram.entities :
        renderEntity(entity)
    for relationship in erdiagram.relationships :
        renderRelationship(relationship)

    graph.render(out, cleanup=True)


def main() -> None:
    print("=== ER Diagram Generator ===")
    print("Choose your input format:")
    print("1. JSON file")
    print("2. Text description file")
    choice = input("Enter your choice (1/2): ").strip()

    if choice not in ("1", "2"):
        print("Invalid choice. Please enter 1 or 2.")
        return

    file_name = input("Enter the input file name: ").strip()

    try:
        if choice == "1":
            with open(file_name, "r", encoding="utf-8") as f:
                jsonData = json.load(f)

        else:
            with open(file_name, "r", encoding="utf-8") as f:
                description = f.read()

            rawData = generateJson(description)
            jsonData = json.loads(rawData)

        output_name = input(
            "Enter the output file name (without extension): "
        ).strip()

        if not output_name:
            output_name = "er_diagram"

        renderERDiagram(jsonData, output_name)
        print(f"ER diagram generated successfully: {output_name}.png")

    except FileNotFoundError:
        print(f"Error: File '{file_name}' not found.")
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON data. {e}")
    except Exception as e:
        print(f"Error: {e}")


# ---------- the example in your screenshot ----------
if __name__ == "__main__":
    schema = DBSchema([
        TableSchema("Employee",
                    [Column("SSN", True), Column("FirstName"),
               Column("DeptID", False, True), Column("SuperSSN", False, True)],
                    [ForeignKey("Department", ["DeptID"], ["DeptID"]),
               ForeignKey("Employee", ["SuperSSN"], ["SSN"])]),
        TableSchema("Department", [Column("DeptID", True), Column("Name")]),
        TableSchema("Works_On",
                    [Column("SSN", True, True), Column("ProjID", True, True), Column("Hours")],
                    [ForeignKey("Employee", ["SSN"], ["SSN"]),
               ForeignKey("Project", ["ProjID"], ["ProjID"])]),
        TableSchema("Project", [Column("ProjID", True), Column("Title")]),
    ])
    renderSchema(schema, "schema_test")   # writes schema_test.png



