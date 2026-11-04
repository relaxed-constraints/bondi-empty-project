# Schema catalogue rendering

`render_schema_catalog` describes already-inspected BONDI schemas. It performs no
sampling or database access and does not modify its inputs.

```python
from bondi.schema import Schema
from json_storm.schema import render_schema_catalog

schemas = {
    "businesses": Schema.from_documents(
        [
            {"address": {"city": "Sydney"}, "categories": ["Cafe"]},
            {"address": {}},
        ]
    ),
    "reviews": Schema.from_documents([{"business_id": "b1", "rating": 5}]),
}
text = render_schema_catalog(schemas)
print(text)
```

The output includes a notation legend and collection sections like:

```text
Collection: "businesses"
Documents inspected: 2
Fields:
- address: object; missing in 0/2 parent objects
- address.city: string; missing in 1/2 parent objects
- categories: array; missing in 1/2 parent objects
- categories[]: string
```

Every bullet has an explicit structural path. `.` marks nesting; `[]` marks array
elements and is not literal MongoDB query syntax. Literal names that are not
ASCII identifiers use JSON bracket quoting: `["address.city"]` is a single field,
while `address.city` is nested. This also escapes newlines and quotes in names.
Arrays of objects use paths such as `reviews[].rating`; nested arrays use `[][]`.

Collections, rendered paths, and type labels are sorted, so input insertion order
does not change output. String, integer, and boolean types use those readable
labels; other BONDI type names are retained. Multiple types are joined with `|`.
Empty arrays have an unknown element type rather than an inferred type.

Counts describe inspected data, not guarantees about all documents. Missing-field
counts use immediate parent objects, including objects inside arrays. Null is a
present value and remains a separate type. Array elements have no missing-field
count. Empty collections and empty catalogues are explicitly labelled.

## Optional examples

Examples are disabled by default. To include them, construct every schema with
`values="distinct"` or `values="full"`, then set `examples_per_type`:

```python
schema = Schema.from_documents([{"city": "Sydney"}], values="distinct")
text = render_schema_catalog({"businesses": schema}, examples_per_type=2)
```

Examples are selected by sorting Python representations, not by frequency or
random sampling. The cap applies separately to each field/type. Representations
are descriptive Python literals, not MongoDB query syntax. Containers are shown
through their structure rather than whole-object examples. Requesting examples
without value retention raises `ValueError`.

The cap limits the number of displayed values, not their string lengths, schema
memory use, or the total prompt size. No fields are silently truncated.

Prompt-template rendering and collection sampling are separate future components.
