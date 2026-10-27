from dataclasses import dataclass , field



@dataclass
class Attribute:
    name: str
    isPrimaryKey: bool = False
    isMultiValue: bool = False
    isPartialKey: bool = False
    isDerived: bool = False
    composite: list["Attribute"] = field(default_factory=list)

    @classmethod
    def fromDict(cls, d: dict) -> "Attribute":
        return cls(name = d["name"],
                   isPrimaryKey = d.get("isPrimaryKey",False),
                   isPartialKey = d.get("isPartialKey",False),
                   isMultiValue = d.get("isMultiValued",False),
                   isDerived = d.get("isDerived",False),
                   composite = [Attribute.fromDict(att) for att in  d.get("composite",[])])


@dataclass
class Entity:
    name: str
    attributes: list[Attribute] = field(default_factory=list)
    isWeak: bool = False
    @classmethod
    def fromDict(cls, d: dict) -> "Entity":
        return cls(name = d["name"],
                   attributes = [Attribute.fromDict(a) for a in d["attributes"]],
                   isWeak = d.get("isWeak", False))


@dataclass
class Participant:
    entity: str
    cardinality: str
    role: str = ""
    isTotalParticipation: bool = False
    @classmethod
    def fromDict(cls, d: dict) -> "Participant":
        return cls(entity = d["entity"],
                   cardinality = d["cardinality"],
                   role = d.get("role", ""),
                   isTotalParticipation = d.get("isTotalParticipation", False))

@dataclass
class Relationship:
    name: str
    participants: list[Participant] = field(default_factory=list)
    attributes: list[Attribute] = field(default_factory=list)
    isIdentifying: bool = False
    @classmethod
    def fromDict(cls, d: dict) -> "Relationship":
        return cls(name = d["name"],
                   participants = [Participant.fromDict(p) for p in d["participants"]],
                   attributes = [Attribute.fromDict(a) for a in d.get("attributes",[])],
                   isIdentifying = d.get("isIdentifying", False))


@dataclass
class ERDiagram:
    entities: list[Entity] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    @classmethod
    def fromDict(cls, d: dict) -> "ERDiagram":
        return cls(entities = [Entity.fromDict(e) for e in d["entities"]],
                   relationships = [Relationship.fromDict(r) for r in d.get("relationships",[])])
