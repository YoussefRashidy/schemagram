from erdiagram.classes import ERDiagram, Entity, Attribute, Relationship
from relationalvisualizer.classes import Column, TableSchema, ForeignKey


def gettingIdentifyingEntity(entity: Entity, relationships: list, entitiesByName: dict) -> list[Entity]:
    identifyingRelationship = next(
        (
            rel for rel in relationships
            if rel.isIdentifying
               and any(part.entity == entity.name for part in rel.participants)
        ),
        None,
    )
    if identifyingRelationship is None:
        raise ValueError(
            f"Weak entity {entity.name} has no identifying relationship"
        )
    return [
        entitiesByName[part.entity]
        for part in identifyingRelationship.participants
        if part.entity != entity.name
    ]


def mapERDiagram(er_diagram: ERDiagram):
    tables = []
    entitiesByName = {entity.name: entity for entity in er_diagram.entities}
    mappedTables: dict[str, TableSchema] = {}
    mappingTables: set[str] = set()

    def mapEntity(entity: Entity):
        if entity.name in mappedTables:
            return mappedTables[entity.name]
        if entity.name in mappingTables:
            raise ValueError(f"Circular dependency detected while mapping entity {entity.name}")
        mappingTables.add(entity.name)
        if entity.isWeak:
            table = mapWeekEntity(entity)
        else:
            table = mapStrongEntity(entity)
        mappingTables.remove(entity.name)
        mappedTables[entity.name] = table
        return table

    def mapAttribute(attribute: Attribute, isPrimaryKey=False):
        isPrimaryKey = isPrimaryKey or attribute.isPrimaryKey or attribute.isPartialKey
        if attribute.composite:
            return [col for sub_attribute in attribute.composite for col in
                    mapAttribute(sub_attribute, isPrimaryKey=isPrimaryKey)]
        else:
            return [Column(name=attribute.name, isPrimaryKey=isPrimaryKey)]

    def mapStrongEntity(entity: Entity):
        table_name = entity.name
        columns = []
        multivalued = []

        def mapMultiValuedAttribute(attribute: Attribute):
            entityColumns = [Column(name=attr.name, isPrimaryKey=True, isForeignKey=True) for attr in primaryKeys]
            multiValueColumns = [Column(name=attr.name, isPrimaryKey=True) for attr in mapAttribute(attribute)]
            fk = ForeignKey(refTable=table_name, columns=[col.name for col in entityColumns],
                            refColumns=[col.name for col in entityColumns])
            return TableSchema(name=f"{table_name}_{attribute.name}", columns=entityColumns + multiValueColumns,
                               foreignKeys=[fk])

        for attribute in entity.attributes:
            if attribute.isDerived:
                continue
            if attribute.isMultiValue:
                multivalued.append(attribute)
            else:
                columns.extend(mapAttribute(attribute, isPrimaryKey=attribute.isPrimaryKey))

        primaryKeys = [pk for pk in columns if pk.isPrimaryKey]

        for multiAttribute in multivalued:
            tables.append(mapMultiValuedAttribute(multiAttribute))
        return TableSchema(name=table_name, columns=columns, foreignKeys=[])

    def mapWeekEntity(entity: Entity):
        owners = [mapEntity(owner) for owner in
                  gettingIdentifyingEntity(entity, er_diagram.relationships, entitiesByName)]
        columns = []
        fks = []
        for owner in owners:
            ownerPK = [col for col in owner.columns if col.isPrimaryKey]
            for pk in ownerPK:
                columns.append(Column(name=pk.name, isPrimaryKey=True, isForeignKey=True))
            fks.append(ForeignKey(refTable=owner.name, columns=[col.name for col in ownerPK],
                                  refColumns=[col.name for col in ownerPK]))
        for attribute in entity.attributes:
            if attribute.isDerived:
                continue
            if attribute.isMultiValue:
                raise ValueError("Weak entity cannot have multivalued attributes")
            columns.extend(mapAttribute(attribute, isPrimaryKey=False))

        if not any(column.isPrimaryKey and not column.isForeignKey for column in columns):
            raise ValueError(
                f"Weak entity {entity.name} must have a partial key"
            )
        return TableSchema(name=entity.name, columns=columns, foreignKeys=fks)

    def addForeignKey(
            targetTable: TableSchema,
            referencedTable: TableSchema,
            prefix: str | None = None,
    ):
        primaryKeys = [
            col for col in referencedTable.columns
            if col.isPrimaryKey
        ]

        fkColumns = []

        for pk in primaryKeys:
            name = f"{prefix or referencedTable.name}_{pk.name}" if prefix else pk.name

            targetTable.columns.append(
                Column(
                    name=name,
                    isPrimaryKey=False,
                    isForeignKey=True
                )
            )

            fkColumns.append(name)

        targetTable.foreignKeys.append(
            ForeignKey(
                refTable=referencedTable.name,
                columns=fkColumns,
                refColumns=[pk.name for pk in primaryKeys]
            )
        )

    def addRelationShipAttributesToTable(table: TableSchema, relationship: Relationship):
        for attr in relationship.attributes:
            if attr.isDerived:
                continue
            if attr.isMultiValue:
                raise ValueError("Relationship cannot have multivalued attributes")
            table.columns.extend(mapAttribute(attr, isPrimaryKey=False))

    def mapBinaryRelation(relationShip: Relationship):
        participants1, participants2 = relationShip.participants
        table1, table2 = mapEntity(entitiesByName[participants1.entity]), mapEntity(
            entitiesByName[participants2.entity])

        if participants1.entity == participants2.entity:
            if participants1.cardinality == "1" and participants2.cardinality == "1":
                target = table1
                referenced = table1
                prefix = participants2.role or "related"
                addForeignKey(target, referenced, prefix=prefix)
                addRelationShipAttributesToTable(target, relationShip)
            elif participants1.cardinality == "1":
                target = table1
                referenced = table1
                prefix = participants1.role or "related"
                addForeignKey(target, referenced, prefix=prefix)
                addRelationShipAttributesToTable(target, relationShip)
            elif participants2.cardinality == "1":
                target = table2
                referenced = table2
                prefix = participants1.role or "related"
                addForeignKey(target, referenced, prefix=prefix)
                addRelationShipAttributesToTable(target, relationShip)
            else:
                tableName = relationShip.name
                columns = []
                fks = []
                for index, participant in enumerate(relationShip.participants):
                    prefix = participant.role or f"role{index + 1}"
                    fkColumns = []
                    for pk in [col for col in table1.columns if col.isPrimaryKey]:
                        columnName = f"{prefix}_{pk.name}"
                        columns.append(Column(
                            name=columnName,
                            isPrimaryKey=True,
                            isForeignKey=True,
                        ))
                        fkColumns.append(columnName)
                    fks.append(ForeignKey(
                        refTable=table1.name,
                        columns=fkColumns,
                        refColumns=[col.name for col in table1.columns if col.isPrimaryKey],
                    ))
                junctionTable = TableSchema(name=tableName, columns=columns, foreignKeys=fks)
                addRelationShipAttributesToTable(junctionTable, relationShip)
                tables.append(junctionTable)
            return

        if participants1.cardinality == "1" and participants2.cardinality == "1":
            totalParticipation1, totalParticipation2 = participants1.isTotalParticipation, participants2.isTotalParticipation
            tableToHoldKeys = table1 if totalParticipation1 else table2
            tableNotToHoldKeys = table2 if totalParticipation1 else table1
            addForeignKey(tableToHoldKeys, tableNotToHoldKeys)
            addRelationShipAttributesToTable(tableToHoldKeys, relationShip)

        elif participants1.cardinality == "1" and participants2.cardinality != "1":
            addForeignKey(table2, table1)
            addRelationShipAttributesToTable(table2, relationShip)

        elif participants1.cardinality != "1" and participants2.cardinality == "1":
            addForeignKey(table1, table2)
            addRelationShipAttributesToTable(table1, relationShip)

        elif participants1.cardinality != "1" and participants2.cardinality != "1":
            tableName = relationShip.name
            columns = []
            fks = []

            for table in [table1, table2]:
                fksColumns = []
                for pk in [col for col in table.columns if col.isPrimaryKey]:
                    columns.append(Column(name=f"{table.name}_{pk.name}", isPrimaryKey=True, isForeignKey=True))
                    fksColumns.append(f"{table.name}_{pk.name}")
                fks.append(ForeignKey(refTable=table.name, columns=fksColumns,
                                      refColumns=[col.name for col in table.columns if col.isPrimaryKey]))

            junctionTable = TableSchema(name=tableName, columns=columns, foreignKeys=fks)
            addRelationShipAttributesToTable(junctionTable, relationShip)

            tables.append(junctionTable)

    def mapNaryRelation(relationShip: Relationship):
        tableName = relationShip.name
        columns = []
        fks = []
        participantColumns = []

        for participant in relationShip.participants:
            table = mapEntity(entitiesByName[participant.entity])
            fksColumns = []
            participantKeyColumns = []
            for pk in [col for col in table.columns if col.isPrimaryKey]:
                columnName = f"{table.name}_{pk.name}"
                participantKeyColumns.append(columnName)
                fksColumns.append(columnName)
            fks.append(ForeignKey(refTable=table.name, columns=fksColumns,
                                  refColumns=[col.name for col in table.columns if col.isPrimaryKey]))
            participantColumns.append(participantKeyColumns)

        oneSideCount = sum(participant.cardinality == "1" for participant in relationShip.participants)

        if oneSideCount == 1:
            primaryKeyParticipants = [
                index for index, participant in enumerate(relationShip.participants)
                if participant.cardinality != "1"
            ]
        else:
            # With zero or multiple one-sides, cardinality alone does not
            # identify one unambiguous minimal candidate key.
            primaryKeyParticipants = list(range(len(relationShip.participants)))

        primaryKeyColumns = {
            columnName
            for index in primaryKeyParticipants
            for columnName in participantColumns[index]
        }
        for participantKeyColumns in participantColumns:
            for columnName in participantKeyColumns:
                columns.append(Column(
                    name=columnName,
                    isPrimaryKey=columnName in primaryKeyColumns,
                    isForeignKey=True,
                ))

        junctionTable = TableSchema(name=tableName, columns=columns, foreignKeys=fks)
        addRelationShipAttributesToTable(junctionTable, relationShip)

        tables.append(junctionTable)

    for entity in er_diagram.entities:
        tables.append(mapEntity(entity))
    for relationship in er_diagram.relationships:
        if relationship.isIdentifying:
            weakParticipants = [
                participant for participant in relationship.participants
                if entitiesByName[participant.entity].isWeak
            ]
            if len(weakParticipants) == 1:
                addRelationShipAttributesToTable(
                    mappedTables[weakParticipants[0].entity],
                    relationship,
                )
            continue
        if len(relationship.participants) == 2:
            mapBinaryRelation(relationship)
        else:
            mapNaryRelation(relationship)

    return tables
