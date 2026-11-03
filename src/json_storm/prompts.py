"""Research prompt definitions with a shared, parser-compatible response contract."""

import json
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PromptTemplate:
    """Research instructions for one query kind, independent of model providers."""

    instructions: str
    query_kind: Literal["find", "aggregate"]

    def __post_init__(self) -> None:
        if not isinstance(self.instructions, str) or not self.instructions.strip():
            raise ValueError("instructions must be a nonempty string")
        if self.query_kind not in ("find", "aggregate"):
            raise ValueError("query_kind must be 'find' or 'aggregate'")

    def render(
        self,
        schema_text: str,
        *,
        num_queries: int,
        relationship_hints: str | None = None,
        target_collection: str | None = None,
    ) -> str:
        """Render one call's prompt without altering the supplied schema text.

        target_collection constrains starting collections, not join references.
        The caller must ensure it belongs to the supplied catalogue: schema_text
        is opaque text, not a machine-readable collection registry. This function
        instructs the model; it cannot enforce response compliance or safe execution.
        """
        if not isinstance(schema_text, str) or not schema_text.strip():
            raise ValueError("schema_text must be a nonempty string")
        if type(num_queries) is not int or num_queries <= 0:
            raise ValueError("num_queries must be a positive integer")
        if relationship_hints is not None and (
            not isinstance(relationship_hints, str) or not relationship_hints.strip()
        ):
            raise ValueError("relationship_hints must be a nonempty string or None")
        if target_collection is not None and (
            not isinstance(target_collection, str)
            or not target_collection
            or "\0" in target_collection
        ):
            raise ValueError("target_collection must be a nonempty name without null characters")
        sections = [f"Task\n{self.instructions}", f"Schema catalogue\n{schema_text}"]
        if relationship_hints is not None:
            sections.append(f"Relationship hints (caller supplied)\n{relationship_hints}")
        selection = "Choose each query's starting collection from the schema catalogue."
        if target_collection is not None:
            selection = (
                f"Every query must use {json.dumps(target_collection)} as its starting collection. "
                "Other collections in the catalogue remain available for joins."
            )
        sections.append(f"Batch request\nGenerate exactly {num_queries} queries.\n{selection}")
        example = {"collection": target_collection or "<collection from catalogue>"}
        rules = [
            "Return only JSON, without Markdown fences or commentary.",
            'Return an object containing exactly one key, "queries", whose value is an array.',
            'Every entry must include "collection", naming its starting collection.',
        ]
        if self.query_kind == "find":
            example["filter"] = {}
            rules.extend(
                [
                    'Each entry requires "filter" (an object).',
                    'Optional fields: "projection" (object or null), "sort" (ordered arrays of '
                    '[field, direction] pairs), "skip" (nonnegative integer), '
                    'and "limit" (positive integer or null).',
                    "Sort fields must be nonempty strings without null characters; directions "
                    "must be integer 1 or -1. Booleans are not integers.",
                    "Omitted options mean no projection, no sort, skip 0, and unlimited results. "
                    "Use null for unlimited limit, not 0; use [] for no sort, not null.",
                    "No other entry keys are allowed.",
                ]
            )
        else:
            example["pipeline"] = []
            rules.extend(
                [
                    'Each entry requires "pipeline", an array of single-key stage objects. '
                    "Stage names must start with $. No other entry keys are allowed.",
                    "Generate read-only pipelines. Do not use write stages such as $out or $merge.",
                ]
            )
        rules.extend(
            [
                "Use MongoDB Extended JSON for BSON values; use ordinary JSON for other values.",
                'Date example: {"creationDate": {"$gte": {"$date": "2023-01-01T00:00:00Z"}}}',
                'ObjectId example: {"_id": {"$oid": "507f1f77bcf86cd799439011"}}',
                'Regex example: {"name": {"$regex": "^tom", "$options": "i"}}',
                "Do not use ISODate(...), ObjectId(...), new Date(...), or Python expressions.",
                "The following is a structural example with one entry, not a query to copy; "
                "return the requested number of entries:",
                json.dumps({"queries": [example]}),
            ]
        )
        sections.append("Response format\n" + "\n".join(rules))
        return "\n\n".join(sections) + "\n"


PROMPTS = {
    "p1": PromptTemplate(
        "Generate an interesting and elaborate MongoDB aggregation pipeline for performance benchmarking, potentially including constructs such as $lookup (joins), nested pipelines (subquery-like behavior), multi-stage transformations, $group, $setWindowFields, $facet, complex $match predicates, computed expressions, string manipulations, and handling of missing or null fields.",
        "aggregate",
    ),
    "p2": PromptTemplate(
        "Generate an interesting and elaborate MongoDB find query for performance benchmarking.",
        "find",
    ),
    "p3": PromptTemplate(
        "Generate a MongoDB find query suitable for performance benchmarking.", "find"
    ),
    "p4": PromptTemplate(
        "Generate a simple MongoDB aggregation pipeline for benchmarking, using basic constructs such as $match, $project, $sort, and $limit.",
        "aggregate",
    ),
    "p5": PromptTemplate(
        "Generate an interesting and elaborate MongoDB aggregation pipeline for performance benchmarking, potentially including $lookup, nested pipelines, $group, $setWindowFields, $facet, complex expressions, string operations, and handling of null or missing fields. Incorporate obscure semantic corner cases, unusual operator combinations, edge cases in array handling, type inconsistencies, and non-obvious query behaviors.",
        "aggregate",
    ),
    "p6": PromptTemplate(
        "Generate an interesting and elaborate MongoDB find query for benchmarking string processing, using operators such as $regex and text-based filtering.",
        "find",
    ),
    "p7": PromptTemplate(
        "Generate an interesting and elaborate MongoDB aggregation pipeline for performance benchmarking, potentially including $lookup, $graphLookup (recursive traversal), nested pipelines, $setWindowFields, $group, $facet, complex expressions, string processing, and handling of null or missing values. Aim to maximize structural and computational complexity.",
        "aggregate",
    ),
}
