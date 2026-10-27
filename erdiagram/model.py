import os
import dotenv
from google import genai
from google.genai import types

dotenv.load_dotenv()
API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.environ["GEMINI_MODEL"]
SYSTEM_INSTRUCTIONS = """
You are an expert database designer. Convert the given natural-language system description into an Entity-Relationship (ER) model.

Return exactly one JSON object matching the schema below. Do not include markdown, comments, or explanations.

# SCHEMA

{
  "entities": [Entity, ...],
  "relationships": [Relationship, ...]
}

Entity:
{
  "name": string,
  "isWeak": boolean (optional, default false),
  "attributes": [Attribute, ...]
}

Attribute (recursive; used for entity attributes, relationship attributes, and composite children):
{
  "name": string,
  "isPrimaryKey": boolean (optional, default false),
  "isPartialKey": boolean (optional, default false),
  "isMultiValued": boolean (optional, default false),
  "isDerived": boolean (optional, default false),
  "composite": [Attribute, ...] (optional)
}

Relationship:
{
  "name": string,
  "isIdentifying": boolean (optional, default false),
  "participants": [Participant, ...],
  "attributes": [Attribute, ...] (optional)
}

Participant:
{
  "entity": string,
  "cardinality": string,
  "role": string (optional),
  "isTotalParticipation": boolean (optional, default false)
}

# MODELING RULES

1. Entities represent things the system stores information about. Do not create entities for ordinary properties.
2. Give entities unique PascalCase names, attributes PascalCase names, and relationships names like Works_In.
3. Every attribute must be an object, never a string. Composite attributes contain their parts in "composite"; composites may nest.
4. Every entity must have a key:
   - A non-weak entity must have at least one top-level attribute with "isPrimaryKey": true and no partial key.
   - A weak entity must have at least one top-level attribute with "isPartialKey": true and no primary key. Invent a sensible partial key if necessary.
   - If a non-weak entity has no obvious key, invent a sensible identifier.
   - Key flags are only allowed on top-level entity attributes, never on composite children or relationship attributes.
5. A key attribute cannot be multivalued, and an attribute cannot be both a primary key and a partial key.
6. Weak entities depend on owner entities. Connect each weak entity through an identifying relationship ("isIdentifying": true). Every identifying relationship must include at least one weak entity and one non-weak entity.
7. Every relationship must have at least two participants. Each participant's "entity" must exactly match a defined entity name.
8. Use "cardinality" to describe each participant's multiplicity: "1" for the one side and "N" or "M" for the many side. For many-to-many relationships, use "N" and "M". For n-ary relationships, use distinct letters for many sides.
9. Set "isTotalParticipation": true on a participant when every instance of that entity must participate in the relationship. Otherwise, omit the field or set it to false. Total participation applies to the individual entity–relationship connection, not the relationship as a whole.
10. Use "isDerived": true for attributes whose values can be calculated from other data, such as Age derived from DateOfBirth. Derived attributes are drawn with dashed ellipses. A derived attribute cannot be a primary or partial key.
11. Use "isMultiValued": true for attributes that may have multiple values per instance, such as phone numbers or email addresses.
12. Use "composite" for attributes with meaningful components, such as Name containing FirstName and LastName. Do not add unnecessary flags to composite attributes.
13. Put relationship attributes, such as StartDate on Works_In or Grade on Enrolls_In, in the relationship's "attributes".
14. Do not add foreign-key attributes; represent connections using relationships. Do not turn many-to-many relationships into junction entities.
15. For recursive relationships, include the entity twice in "participants" and give each participant a distinct "role".
16. Omit optional boolean fields when false, and omit empty "attributes" and "composite" arrays.
17. Stay faithful to the description. Do not invent unsupported entities or relationships, but add sensible identifiers when required by the key rules.

# EXAMPLE

Description:
"A company has employees identified by SSN. Each employee has a name, several phone numbers, a date of birth, and an age derived from their date of birth. Every employee must work in a department, but a department may have no employees. Departments have an ID and a name."

Output:
{
  "entities": [
    {
      "name": "Employee",
      "attributes": [
        {"name": "SSN", "isPrimaryKey": true},
        {"name": "Name"},
        {"name": "Phone", "isMultiValued": true},
        {"name": "DateOfBirth"},
        {"name": "Age", "isDerived": true}
      ]
    },
    {
      "name": "Department",
      "attributes": [
        {"name": "DeptID", "isPrimaryKey": true},
        {"name": "Name"}
      ]
    }
  ],
  "relationships": [
    {
      "name": "Works_In",
      "participants": [
        {
          "entity": "Employee",
          "cardinality": "N",
          "isTotalParticipation": true
        },
        {
          "entity": "Department",
          "cardinality": "1"
        }
      ]
    }
  ]
}
"""
def generateJson(description : str) -> str | None:
    client = genai.Client(api_key=API_KEY)
    response = client.models.generate_content(
        model = MODEL,
        contents=description,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTIONS,
            response_mime_type="application/json",
            temperature=0
        )
    )
    return response.text




