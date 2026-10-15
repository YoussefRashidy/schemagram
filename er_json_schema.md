# ER Diagram JSON Schema

Schema used by the renderer (Part 1) and the Gemini prompt (Part 2).
This is a deliberate extension of the PDF's format (TA approved schema changes).

## Top level

```json
{
  "entities": [ <Entity>, ... ],
  "relationships": [ <Relationship>, ... ]
}
```

| Key | Type | Required | Notes |
|---|---|---|---|
| `entities` | array of Entity | yes | |
| `relationships` | array of Relationship | yes (may be empty) | |

## Entity

```json
{
  "name": "Employee",
  "isWeak": false,
  "attributes": [ <Attribute>, ... ]
}
```

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | string | yes | | Unique across all entities |
| `isWeak` | boolean | no | `false` | Drawn with a double border |
| `attributes` | array of Attribute | no | `[]` | |

## Attribute

Used for entity attributes, relationship attributes, and composite children (recursive).  
**Every attribute is an object, at any depth.** Never a plain string.

```json
{
  "name": "Age",
  "isDerived": true,
  "isMultiValued": false,
  "composite": []
}
```

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | string | yes | | |
| `isPrimaryKey` | boolean | no | `false` | Solid underline. Only on attributes of non-weak entities |
| `isPartialKey` | boolean | no | `false` | Dashed underline. Only on attributes of weak entities |
| `isMultiValued` | boolean | no | `false` | Drawn with a double border |
| `isDerived` | boolean | no | `false` | Drawn as an ellipse with a dashed border |
| `composite` | array of Attribute | no | `[]` | Children; can nest to any depth |

Rules:
- A key attribute (primary or partial) must never be multivalued.
- An attribute is never both `isPrimaryKey` and `isPartialKey`.
- Every non-weak entity needs at least one `isPrimaryKey` attribute and no `isPartialKey` attributes.
- Every weak entity needs at least one `isPartialKey` attribute and no `isPrimaryKey` attributes.
- Several `isPrimaryKey` attributes in one entity form a composite key; several `isPartialKey` attributes form a composite partial key.
- Key flags are only meaningful on top-level entity attributes, not on composite children or relationship attributes.
- `isDerived` may be used on entity attributes or relationship attributes. It indicates that the attribute is derived rather than stored directly.
- A derived attribute must not be a primary key or partial key.

## Relationship

```json
{
  "name": "Works_In",
  "isIdentifying": false,
  "participants": [
    { "entity": "Employee", "cardinality": "N" },
    { "entity": "Department", "cardinality": "1" }
  ],
  "attributes": [ { "name": "StartDate" } ]
}
```

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `name` | string | yes | | Label on the diamond |
| `isIdentifying` | boolean | no | `false` | Drawn with a double diamond |
| `participants` | array of Participant | yes | | At least 2; any number allowed (n-ary) |
| `attributes` | array of Attribute | no | `[]` | Attributes of the relationship itself |

## Participant

```json
{
  "entity": "Employee",
  "cardinality": "N",
  "isTotalParticipation": true
}
```

| Key | Type | Required | Default | Notes                                                                                                                   |
|---|---|---|---|-------------------------------------------------------------------------------------------------------------------------|
| `entity` | string | yes | | Must match an entity `name` exactly                                                                                     |
| `cardinality` | string | yes | | `"1"`, `"N"`, `"M"`, etc. Becomes the edge label                                                                        |
| `isTotalParticipation` | boolean | no | `false` | Draw the entity–relationship edge with penwidth=2; `true` means total participation, `false` means partial participation |

## Full example

```json
{
  "entities": [
    {
      "name": "Employee",
      "attributes": [
        { "name": "SSN", "isPrimaryKey": true },
        { "name": "Name", "composite": [ { "name": "FirstName" }, { "name": "LastName" } ] },
        { "name": "Phone", "isMultiValued": true },
        { "name": "Address", "composite": [
            { "name": "Street" },
            { "name": "City" },
            { "name": "State" },
            { "name": "ZIP" }
        ] },
        { "name": "Salary" }
      ]
    },
    {
      "name": "Department",
      "attributes": [
        { "name": "DeptID", "isPrimaryKey": true },
        { "name": "Name" },
        { "name": "Location", "isMultiValued": true }
      ]
    },
    {
      "name": "Dependent",
      "isWeak": true,
      "attributes": [
        { "name": "FirstName", "isPartialKey": true },
        { "name": "BirthDate" }
      ]
    }
  ],
  "relationships": [
    {
      "name": "Works_In",
      "participants": [
        { "entity": "Employee", "cardinality": "N" },
        { "entity": "Department", "cardinality": "1" }
      ]
    },
    {
      "name": "Has_Dependent",
      "isIdentifying": true,
      "participants": [
        { "entity": "Employee", "cardinality": "1" },
        { "entity": "Dependent", "cardinality": "N" }
      ]
    }
  ]
}
```

