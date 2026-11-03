"""Read-only MongoDB sampling for schema inputs."""

from collections.abc import Sequence

from bondi.mongodb import MongoAggregateQuery, MongoCollectionRef, MongoExecutor
from bondi.schema import Schema


def collection_targets(namespaces: Sequence[str]) -> tuple[MongoCollectionRef, ...]:
    """Validate distinct namespaces in one database, splitting at the first dot.

    BONDI 0.1.4 has no from_namespace constructor. Keep collection-name dots.
    The current prompt/parser contract supplies a single database per experiment.
    """
    if isinstance(namespaces, str) or not isinstance(namespaces, Sequence) or not namespaces:
        raise ValueError("namespaces must be a nonempty sequence")
    targets = []
    for namespace in namespaces:
        if not isinstance(namespace, str) or "." not in namespace:
            raise ValueError("Each namespace must be database.collection")
        database, collection = namespace.split(".", 1)
        targets.append(MongoCollectionRef(database, collection))
    if len({target.database for target in targets}) != 1:
        raise ValueError("This generation contract requires namespaces in one database")
    if len({target.collection for target in targets}) != len(targets):
        raise ValueError("Duplicate namespaces are not allowed")
    return tuple(targets)


def sample_schemas(
    executor: MongoExecutor,
    namespaces: Sequence[str],
    *,
    sample_size: int = 100,
    retain_values: bool = False,
) -> tuple[dict[str, Schema], list[dict]]:
    """Use native $sample and BONDI inspection; return schemas and BSON sample records.

    sample_size is a per-collection maximum. Sampling is unseeded. Empty samples
    raise rather than silently proceeding with an empty or missing collection.
    The caller owns the executor. No collection is created or modified.
    """
    targets = collection_targets(namespaces)
    if type(sample_size) is not int or sample_size <= 0:
        raise ValueError("sample_size must be a positive integer")
    if type(retain_values) is not bool:
        raise TypeError("retain_values must be a boolean")
    schemas, records = {}, []
    for target in targets:
        result = executor.run(
            MongoAggregateQuery(target, [{"$sample": {"size": sample_size}}]), collect_results=True
        )
        documents = result.documents
        if not documents:
            raise ValueError(f"No sample documents found for {target.database}.{target.collection}")
        schemas[target.collection] = Schema.from_documents(
            documents, values="distinct" if retain_values else "none"
        )
        records.extend(
            {"namespace": f"{target.database}.{target.collection}", "document": doc}
            for doc in documents
        )
    return schemas, records


def validate_schema_artifact(schemas, manifest) -> str:
    """Validate a trusted, version-matched BONDI schema snapshot; return its database.

    Pickled schemas are version-sensitive. Sample documents remain a reconstruction
    source if a future BONDI upgrade requires a new snapshot.
    """
    from importlib.metadata import version

    if not isinstance(manifest, dict) or manifest.get("format_version") != 1:
        raise ValueError("Missing or unsupported schema_manifest.json")
    if manifest.get("status") != "completed":
        raise ValueError("Schema artifact is not completed")
    if manifest.get("bondi_version") != version("bondi"):
        raise ValueError("Schema artifact BONDI version differs from installed version")
    targets = collection_targets(manifest.get("namespaces"))
    expected = [target.collection for target in targets]
    if manifest.get("database") != targets[0].database or manifest.get("collections") != expected:
        raise ValueError("Schema manifest database/collections disagree with namespaces")
    if not isinstance(schemas, dict) or list(schemas) != expected:
        raise ValueError("Missing schemas.pkl or mismatched collection catalogue")
    if any(not isinstance(schema, Schema) for schema in schemas.values()):
        raise TypeError("Schema catalogue must contain BONDI Schema objects")
    return targets[0].database
