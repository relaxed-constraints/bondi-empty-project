"""Generate a workload from a required Yanex schema dependency, without database access."""

from pathlib import Path

import yanex

from json_storm.artifacts import GenerationArtifacts
from json_storm.generation import generate_queries
from json_storm.models import DEFAULT_SYSTEM_INSTRUCTIONS, LiteLLMModel, load_credentials
from json_storm.prompts import PROMPTS
from json_storm.sampling import validate_schema_artifact
from json_storm.schema import render_schema_catalog


def main():
    # load environment variables and credentials
    root = Path(__file__).resolve().parents[1]
    if (root / ".env").is_file():
        load_credentials(root / ".env")

    # This script requires tracked lineage; Yanex searches the dependency chain.
    yanex.assert_dependency("schema.py", slot="schema")

    manifest = yanex.load_artifact("schema_manifest.json")
    schemas = yanex.load_artifact("schemas.pkl")
    database = validate_schema_artifact(schemas, manifest)
    examples = yanex.get_param("examples_per_type", 0)
    template = PROMPTS[yanex.get_param("prompt_id", "p3")]

    model_cfg = yanex.get_param("model")
    model = LiteLLMModel(
        model_cfg["name"],
        api_base=model_cfg.get("api_base", "http://localhost:11434"),
        timeout_seconds=model_cfg.get("timeout_seconds", 120),
        parameters=model_cfg.get("parameters", {"think": False}),
        system_instructions=model_cfg.get("system_instructions", DEFAULT_SYSTEM_INSTRUCTIONS),
    )
    recorder = GenerationArtifacts(yanex.save_artifact)
    recorder.checkpoint("running")
    try:
        yanex.save_artifact(
            render_schema_catalog(schemas, examples_per_type=examples), "schema.txt"
        )
        for batch in generate_queries(
            model,
            template,
            schemas,
            database=database,
            num_queries=yanex.get_param("num_queries", 10),
            batch_size=yanex.get_param("batch_size", 2),
            target_collection=yanex.get_param("target_collection", "posts"),
            relationship_hints=yanex.get_param("relationship_hints", None),
            examples_per_type=examples,
        ):
            recorder.add(batch)
            recorder.checkpoint("failed" if batch.error else "running")
            print(
                f"Batch {batch.batch_index}: {recorder.metrics['queries_accepted']} accepted so far",
                flush=True,
            )
            if batch.error:
                raise RuntimeError(
                    f"Generation call failed: {type(batch.error).__name__}"
                ) from None
        recorder.checkpoint("completed")
    except BaseException as original:
        # Cleanup failures must not replace the original experiment failure.
        try:
            recorder.checkpoint("failed")
        except Exception as checkpoint_error:
            original.add_note(f"Failure checkpoint also failed: {type(checkpoint_error).__name__}")
        try:
            yanex.log_metrics(recorder.metrics)
        except Exception as metrics_error:
            original.add_note(f"Failure metrics also failed: {type(metrics_error).__name__}")
        raise
    else:
        yanex.log_metrics(recorder.metrics)


if __name__ == "__main__":
    main()
