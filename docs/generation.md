# Batch generation

`generate_queries` connects schema rendering, prompts, model access and parsing.
It makes no database calls and does not save files or log Yanex metrics.

```python
from bondi.schema import Schema
from json_storm.generation import generate_queries
from json_storm.models import LiteLLMModel
from json_storm.prompts import PROMPTS

model = LiteLLMModel(
    "ollama_chat/qwen3.6:latest",
    api_base="http://localhost:11434",
    parameters={"think": False},
)
records = generate_queries(
    model,
    PROMPTS["p3"],
    {"businesses": Schema.from_documents([{"stars": 4.5}])},
    database="research",
    num_queries=5,
    batch_size=2,
    target_collection="businesses",
)
for batch in records:
    if batch.error is not None:
        print("Generation failed:", type(batch.error).__name__)
        break
    print(batch.batch_index, batch.requested_count, batch.parsed.actual_count)
```

The iterator requests batches of 2, 2, and 1. Each call is independent; previous
answers are not included in subsequent prompts. Rendering and configuration
validation occur when the function is called. Model calls occur only as the
iterator advances, allowing the caller to persist each record immediately.
Schema text is rendered once, so subsequent schema mutations do not affect calls.

Each `GeneratedBatch` retains its index, requested count, exact prompt, full model
response (including instructions and usage), and parsed candidates. Short/oversized
batches, duplicates, invalid entries and invalid JSON are preserved without retries
or replacements. An absent final answer stays `None` in the model response and is
parsed as an empty string, producing `invalid_json`.

A configured starting target must belong to the schema catalogue. Structurally
valid queries selecting another catalogued collection are listed by position in
`target_violations`. They remain visible in `parsed` but must not be executed.
Unknown collections already produce parser errors. Join references remain native
pipeline content. A later evaluator must exclude invalid/violating candidates and
apply read-only execution policy before building its workload.

A model-call exception is retained on one failed batch and iteration then ends.
Earlier records remain usable. KeyboardInterrupt and other BaseExceptions
propagate. Errors outside the model call also propagate. Merely exhausting this
iterator is not proof that generation succeeded: inspect each record's `error`.
Exceptions are in-memory diagnostic objects, not ready-made serializable artifacts;
future experiment code should persist appropriate error details without credentials.

This component is reusable code in `src/`. Thin Yanex scripts and durable artifact
serialization remain later steps, along with MongoDB evaluation.
