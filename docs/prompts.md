# Prompt rendering

`PromptTemplate` separates research instructions from the shared batch response
contract. `PROMPTS` contains adaptations of student prompts `p1`–`p7`: their research
instructions are retained, while their original single-query output instructions
are replaced. `p2`, `p3`, and `p6` request find queries; the others request pipelines.
These are adapted prompts, not byte-for-byte replicas of the student experiment.

```python
from bondi.schema import Schema
from json_storm.schema import render_schema_catalog
from json_storm.prompts import PROMPTS

schema_text = render_schema_catalog(
    {
        "businesses": Schema.from_documents([{"business_id": "b1"}]),
        "reviews": Schema.from_documents([{"business_id": "b1", "rating": 5}]),
    }
)
prompt = PROMPTS["p1"].render(
    schema_text,
    num_queries=8,
    target_collection="businesses",
    relationship_hints="reviews.business_id references businesses.business_id",
)
```

The returned string contains the task, exact schema text, optional relationship
hints, batch request, and response format, in that order. Save this exact string
as an experiment artifact. Provider message wrapping belongs to the model adapter.
`num_queries` is the count requested in this call, normally the batch size, and
may be smaller for the last call.

Without a target, the model may select each starting collection from the catalogue.
With a target, every query is instructed to start there; all schemas remain in the
prompt for joins. The caller must ensure the target belongs to the catalogue:
the renderer does not parse schema text back into collection metadata. A target
instruction does not guarantee model compliance. The current parser validates
catalogue membership, not a per-experiment target restriction.

The shared format matches the parser's envelope and includes find sorting and
pagination. Aggregation prompts request read-only pipelines. Prompt instructions
are not execution-policy enforcement; the evaluator must check this separately.
No requirement for unique queries or nonempty results is added.

Custom prompts can use `PromptTemplate("Research instructions here.", "find")`.
Instructions should describe the research task; avoid conflicting output formats.
Extended JSON is requested for BSON values, with date, ObjectId, and regex examples.
Shell constructors are explicitly prohibited. The parser normalizes these values
using PyMongo while retaining the original response.
