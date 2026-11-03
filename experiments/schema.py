"""Sample MongoDB once and persist parsed BONDI schemas for dependent runs."""

import os
from importlib.metadata import version
from pathlib import Path

import yanex
from bondi.mongodb import MongoExecutor

from json_storm.artifacts import save_bson_jsonl
from json_storm.models import load_credentials
from json_storm.sampling import collection_targets, sample_schemas
from json_storm.schema import render_schema_catalog


def main():
    root = Path(__file__).resolve().parents[1]
    if (root / ".env").is_file():
        load_credentials(root / ".env")
    namespaces = yanex.get_param(
        "namespaces", ["mathexchange.users", "mathexchange.posts", "mathexchange.postHistory"]
    )
    targets = collection_targets(namespaces)
    uri = os.environ.get("JSON_STORM_MONGODB_URI") or yanex.get_param(
        "mongodb.uri", "mongodb://localhost:27018"
    )
    with MongoExecutor.from_uri(
        uri, timeout_seconds=yanex.get_param("mongodb.timeout_seconds", 30)
    ) as executor:
        schemas, samples = sample_schemas(
            executor,
            namespaces,
            sample_size=yanex.get_param("sample_size", 100),
            retain_values=yanex.get_param("retain_values", True),
        )
    yanex.save_artifact(samples, "schema_samples.jsonl", saver=save_bson_jsonl)
    yanex.save_artifact(schemas, "schemas.pkl")
    yanex.save_artifact(render_schema_catalog(schemas), "schema_preview.txt")
    yanex.save_artifact(
        {
            "format_version": 1,
            "status": "completed",
            "bondi_version": version("bondi"),
            "database": targets[0].database,
            "namespaces": namespaces,
            "collections": list(schemas),
            "sampling_method": "$sample",
            "sampling_seed": None,
            "sampled_documents": {name: schema.document_count for name, schema in schemas.items()},
            "value_modes": {name: schema.value_mode for name, schema in schemas.items()},
        },
        "schema_manifest.json",
    )
    yanex.log_metrics({"collections_sampled": len(schemas), "documents_sampled": len(samples)})
    print(f"Saved {len(schemas)} schemas from {len(samples)} documents.")


if __name__ == "__main__":
    main()
