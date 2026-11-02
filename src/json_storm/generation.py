"""Sequential batch generation, independent of experiment tracking and databases."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from bondi.mongodb import MongoCollectionRef
from bondi.schema import Schema

from json_storm.models import Model, ModelResponse
from json_storm.parsing import ParsedBatch, parse_batch
from json_storm.prompts import PromptTemplate
from json_storm.schema import render_schema_catalog


@dataclass(frozen=True)
class GeneratedBatch:
    """One attempted model call, including failures and candidate provenance.

    Exactly one of response and error is populated by generate_queries. parsed
    exists for every response; absent final text is parsed as an empty string,
    while response.text retains None. target_violations contains zero-based
    positions of structurally valid queries selecting the wrong starting target.
    These queries remain in parsed for inspection but must not be executed.
    error retains the original exception; it is not a serializable artifact.
    """

    batch_index: int
    requested_count: int
    prompt: str
    response: ModelResponse | None = None
    parsed: ParsedBatch | None = None
    target_violations: tuple[int, ...] = ()
    error: Exception | None = None


def generate_queries(
    model: Model,
    template: PromptTemplate,
    schemas: Mapping[str, Schema],
    *,
    database: str,
    num_queries: int,
    batch_size: int,
    target_collection: str | None = None,
    relationship_hints: str | None = None,
    examples_per_type: int = 0,
) -> Iterator[GeneratedBatch]:
    """Yield independently prompted batches, preserving short and invalid responses.

    Validation and schema rendering occur immediately; model calls are lazy.
    At most ceil(num_queries / batch_size) sequential calls are attempted.
    One model-call exception is yielded as a failed batch, then iteration stops.
    KeyboardInterrupt and other BaseExceptions propagate. Parsing failures and
    target violations do not stop subsequent calls. No retries or replacements,
    workload execution, persistence, or Yanex logging occur here.
    """
    for name, value in (("num_queries", num_queries), ("batch_size", batch_size)):
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if not isinstance(template, PromptTemplate):
        raise TypeError("template must be a PromptTemplate")
    schema_text = render_schema_catalog(schemas, examples_per_type=examples_per_type)
    if not schemas:
        raise ValueError("schemas must contain at least one collection")
    collections = tuple(schemas)
    for name in collections:
        MongoCollectionRef(database, name)
    if target_collection is not None and target_collection not in collections:
        raise ValueError("target_collection must belong to the schema catalogue")
    # Validate all rendering arguments before any call, without retaining mutable schemas.
    template.render(
        schema_text,
        num_queries=1,
        target_collection=target_collection,
        relationship_hints=relationship_hints,
    )

    def batches() -> Iterator[GeneratedBatch]:
        for batch_index, offset in enumerate(range(0, num_queries, batch_size)):
            count = min(batch_size, num_queries - offset)
            prompt = template.render(
                schema_text,
                num_queries=count,
                target_collection=target_collection,
                relationship_hints=relationship_hints,
            )
            try:
                response = model.generate(prompt)
            except Exception as error:
                yield GeneratedBatch(batch_index, count, prompt, error=error)
                return
            parsed = parse_batch(
                response.text if response.text is not None else "",
                batch_index=batch_index,
                query_kind=template.query_kind,
                database=database,
                collections=collections,
                expected_count=count,
            )
            violations = tuple(
                candidate.position
                for candidate in parsed.candidates
                if candidate.query is not None
                and target_collection is not None
                and candidate.query.target.collection != target_collection
            )
            yield GeneratedBatch(batch_index, count, prompt, response, parsed, violations)

    return batches()
