import html
import itertools
import graphviz
import json
from classes import ERDiagram, Attribute, Entity, Relationship
from model import generateJson


def renderERDiagram(data ,out: str , engine: str = 'dot') -> None:
    erdiagram : ERDiagram = ERDiagram.fromDict(data)
    counter = itertools.count()
    entitiesIds : dict = {}
    graph = graphviz.Graph(
        format='png',
        engine=engine,
        graph_attr={'overlap': 'false', 'splines': 'true', 'sep': '+8', 'dpi': '200'},
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
        graph.node(entityId,label=entity.name,shape='box',peripheries=peripheries)
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
        graph.node(relationshipId, label=relationship.name, shape='diamond', peripheries=peripheries)
        for p in relationship.participants:
            penwidth = "2" if p.isTotalParticipation else "1"
            graph.edge(relationshipId, entitiesIds[p.entity], label=p.cardinality,penwidth=penwidth)
        for attribute in relationship.attributes:
            renderAttribute(attribute, relationshipId)

    for entity in erdiagram.entities :
        renderEntity(entity)
    for relationship in erdiagram.relationships :
        renderRelationship(relationship)

    graph.render(out, cleanup=True)


# with open('scratch.json', 'r') as f:
#     data = json.load(f)
#     renderERDiagram(data,"res")
DESCRIPTION = """
We are designing a database for a university.

Students are identified by a student ID. For each student we store their name (first and last), date of birth, several email addresses, and a home address made of a street (street number and street name), a city, and a ZIP code. Each student majors in exactly one department, and a department has many students.

Departments are identified by a department code and have a name and several office locations. Professors work for exactly one department, while a department employs many professors.

Professors are identified by an employee ID. We store their name (first and last), their rank, a salary, several phone numbers, and their office hours, which can be several per professor and each consist of a day, a start time and an end time. A professor can supervise other professors, and each professor has at most one supervisor.

Courses are identified by a course code and have a title and a number of credit hours. A course can have other courses as prerequisites, and a course can be a prerequisite for many courses.

Every course is offered in sections. A section does not exist without its course and is identified only within its course by the combination of its semester and its section number. A section also has a schedule and a maximum capacity. Each course has many sections.

Each section is taught by exactly one professor, and a professor can teach many sections. Each section meets in one classroom. Classrooms have a building, a room number and a capacity, and the room number is only unique within a building. A classroom can host many sections.

Students enroll in sections. A student can enroll in many sections and a section has many students. Each enrollment records the enrollment date and the final grade.

Finally, professors recommend textbooks for courses. Textbooks are identified by their ISBN and have a title, a publisher, and several authors. A professor can recommend many textbooks for many courses, and each recommendation records the edition number.
"""

rawData = generateJson(DESCRIPTION)
jsonData = json.loads(rawData)
renderERDiagram(jsonData, "university_er_diagram")



