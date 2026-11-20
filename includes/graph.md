# Per-Corpus Concept Graph (graph.yaml)

## Purpose

`graph.yaml` is a concept-centric relationship graph stored in each corpus. Concepts are knowledge graph nodes; entries are evidence; relationships are typed edges between concepts.

### Schema Definition (Strict)

**Schema version 2**: concepts define labels, descriptions and tags only. Entry membership is stored in `index.yaml`, in the `concepts` list of each entry (the link goes both ways).

```yaml
schema_version: 2

# Concepts: knowledge graph nodes
# Key: concept ID (slugified label: lowercase, hyphens, no spaces)
# Entry membership is in index.yaml, in each entry's `concepts` list.
concepts:
  {concept-id}:
    label: "{Human-Readable Label}"           # Required. Display name.
    description: "{One-line description}"      # Required. What this concept covers.
    tags: ["{tag1}", "{tag2}"]                 # Optional. Used for concept matching.

# Relationships: typed edges between concepts
relationships:
  - from: "{concept-id}"                       # Required. Source concept ID.
    to: "{concept-id}"                         # Required. Target concept ID.
    type: "{relationship-type}"                # Required. One of the controlled vocabulary.
    origin: "{origin-type}"                    # Required. How this relationship was discovered.
    evidence: "{source_id}:{path}"             # Optional. File that established this link. Null for manual.

# Metadata about graph state
meta:
  generated_at: "{ISO-8601 timestamp}"         # Required. When the graph was last generated or updated.
  concept_count: {integer}                     # Required. Number of concepts.
  relationship_count: {integer}                # Required. Number of relationships.
```

### Concept ID Conventions

A concept ID is slugified from the label: lowercase, spaces replaced with hyphens, special characters removed (alphanumerics and hyphens stay), repeated hyphens collapsed.

| Label | Concept ID |
|-------|------------|
| Family Activities | `family-activities` |
| Query Optimization | `query-optimization` |
| Q1 2022 Budget | `q1-2022-budget` |
| IT Cybersecurity | `it-cybersecurity` |

### Relationship Type Vocabulary (Controlled)

| Type | Meaning | Example |
|------|---------|---------|
| `includes` | Concept A contains or encompasses Concept B | family-activities → recipes |
| `depends-on` | Concept A requires understanding of Concept B | lazy-frames → query-optimization |
| `see-also` | Concepts are related but independent | work-projects → budget-review |
| `extends` | Concept A builds upon Concept B | advanced-queries → basic-queries |
| `contrast-with` | Concepts represent alternative approaches | lazy-evaluation → eager-evaluation |

### Origin Types

| Origin | Meaning |
|--------|---------|
| `wikilink` | Discovered from a `[[wikilink]]` or a markdown link |
| `tag` | Inferred from shared `#tag` co-occurrence |
| `frontmatter` | Inferred from frontmatter metadata |
| `manual` | Curated by a person |

### Validation Rules

1. **Schema compliance**: all required fields present, correct types, `schema_version` is 2.
2. **Dangling concept references**: an entry in `index.yaml` lists a concept ID that `graph.yaml` does not define.
3. **Dangling relationships**: `from` and `to` name defined concept IDs.
4. **Orphan concepts**: concepts that no entry of `index.yaml` lists (a warning, not an error).
5. **Relationship type vocabulary**: only the controlled types are used.
6. **Origin type vocabulary**: only the defined origins are used.
