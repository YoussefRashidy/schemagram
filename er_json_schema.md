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

| Key | Type | Required | Default | Notes |
|---|---|---|---|---|
| `entity` | string | yes | | Must match an entity `name` exactly |
| `cardinality` | string | yes | | `"1"`, `"N"`, `"M"`, etc. Becomes the edge label |
| `role` | string | no | | For recursive relationships (same entity twice) |
| `isTotalParticipation` | boolean | no | `false` | Draw the entity–relationship edge as a double line; `true` means total participation, `false` means partial participation |

## Validation rules (Part 2)

1. Entity names are unique.
2. Every relationship has at least 2 participants.
3. Every `participants[].entity` names an existing entity.
4. No attribute is both `isPrimaryKey` and `isMultiValued`, or both `isPartialKey` and `isMultiValued`.
5. No attribute is both `isPrimaryKey` and `isPartialKey`.
6. Every non-weak entity has at least one `isPrimaryKey` attribute and no `isPartialKey` attribute.
7. Every weak entity has at least one `isPartialKey` attribute and no `isPrimaryKey` attribute.
8. A weak entity takes part in at least one identifying relationship.
9. An identifying relationship includes at least one weak and one non-weak entity.
10. Key flags (`isPrimaryKey`, `isPartialKey`) appear only on top-level entity attributes.

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

## Notes

- JSON keys are camelCase (`isPrimaryKey`, `isPartialKey`, `isMultiValued`, `isWeak`, `isIdentifying`). In `classes.py` the multivalued field is currently named `isMultiValue`, but `fromDict` reads the JSON key `isMultiValued`, so that is fine.
- `isWeak` / `isIdentifying` are drawn with `peripheries="2"` in the renderer.
- `isPartialKey` is drawn as a dashed underline (HTML-like label table with a dashed bottom border).
- Part 1 trusts its input; Part 2 runs `validate()` before rendering.
