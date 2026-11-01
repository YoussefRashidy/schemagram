import html
import itertools
import graphviz
import json
from erdiagram.classes import ERDiagram, Attribute, Entity, Relationship
from relationalvisualizer.classes import Column, ForeignKey, TableSchema, DBSchema
from relationalvisualizer.renderer import renderSchema


def renderERDiagram(data ,out: str , engine: str = 'sfdp') -> None:
    erdiagram : ERDiagram = ERDiagram.fromDict(data)
    counter = itertools.count()
    entitiesIds : dict = {}
    graph = graphviz.Graph(
        format='png',
        engine=engine,
        graph_attr={'overlap': 'false', 'splines': 'true', 'sep': '+14', 'dpi': '200',
                    'bgcolor': 'white', 'pad': '0.4'},
        node_attr={'fontname': 'Helvetica', 'fontsize': '11', 'fontcolor': '#1f2a44'},
        edge_attr={'penwidth': '1.1', 'color': '#7a8fb5', 'fontname': 'Helvetica-Bold',
                   'fontsize': '11', 'fontcolor': '#c0392b'}
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
        graph.node(entityId, label=f'<<B>{html.escape(entity.name)}</B>>', shape='box', peripheries=peripheries,
                   style='filled,rounded', fillcolor='#2b4c7e', fontcolor='white', color='#2b4c7e',
                   fontsize='13', penwidth='1.6', margin='0.2,0.12')
        entitiesIds[entity.name] = entityId
        for attribute in entity.attributes:
            renderAttribute(attribute, entityId)

    def renderAttribute(attribute : Attribute , entityId:str) :
        attributeId = f"{entityId}_{attribute.name}"
        peripheries = "2" if attribute.isMultiValue else "1"
        style = "dashed" if attribute.isDerived else "solid"
        fill = '#fff3c4' if (attribute.isPrimaryKey or attribute.isPartialKey) else '#eef3fb'
        border = '#c9a227' if (attribute.isPrimaryKey or attribute.isPartialKey) else '#7a8fb5'
        graph.node(attributeId, label=getAttributeLabel(attribute), shape='ellipse',
                   style=f'filled,{style}', fillcolor=fill, color=border, peripheries=peripheries)
        graph.edge(entityId, attributeId)

        for innerAttribute in attribute.composite :
            renderAttribute(innerAttribute, attributeId)

    def renderRelationship(relationship : Relationship):
        relationshipId = getId()
        peripheries = "2" if relationship.isIdentifying else "1"
        graph.node(relationshipId, label=relationship.name, shape='diamond', peripheries=peripheries,
                   style='filled', fillcolor='#ffd9a8', color='#d9822b', penwidth='1.4', margin='0.05')
        for p in relationship.participants:
            penwidth = "2.6" if p.isTotalParticipation else "1.1"
            label = f"{p.role} ({p.cardinality})" if p.role else p.cardinality
            graph.edge(relationshipId, entitiesIds[p.entity], label=label, penwidth=penwidth,
                   color='#2b4c7e' if p.isTotalParticipation else '#7a8fb5')
        for attribute in relationship.attributes:
            renderAttribute(attribute, relationshipId)

    for entity in erdiagram.entities :
        renderEntity(entity)
    for relationship in erdiagram.relationships :
        renderRelationship(relationship)

    graph.render(out, cleanup=True)


def main() -> None:
    from erdiagram.model import generateJson  # lazy: needs the Gemini package + API key
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




