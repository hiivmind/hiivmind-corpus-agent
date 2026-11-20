# index.yaml Fields

`index.yaml` is the source of truth for the corpus's entry metadata. Source-level tracking (commit, timestamps, repository) stays in `config.yaml`.

## Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Canonical identifier: `{source_id}:{path}`. Join key to graph.yaml |
| `source` | string | yes | Source ID from config.yaml |
| `path` | string | yes | Relative path within the source |
| `title` | string | yes | Human-readable title |
| `summary` | string | yes | 1-2 sentence description of the content |
| `tags` | string[] | yes | Curated search facets |
| `keywords` | string[] | yes | Significant terms from the content body; broader than tags |
| `concepts` | string[] | no | Concept IDs this entry belongs to (keys of graph.yaml). Empty list if not yet mapped. Part of the embedded text |
| `category` | enum | yes | `reference`, `tutorial`, `guide`, `api`, `config`, `navigation`, `journal`, or `unknown` (the placeholder of an added file, replaced on re-scan) |
| `section` | string | no | Grouping key for tiered corpora; matches a `render.sections[].id` in config.yaml |
| `content_type` | enum | yes | `markdown`, `yaml`, `json`, `text`, `rst` |
| `size` | enum | yes | `standard` or `large`. Large means the file exceeds 1000 lines |
| `grep_hint` | string or null | no | For large files: a search command with `FILE` where the file goes, e.g. `grep -n "^## " FILE`. Null for standard files |
| `headings` | object[] | no | Sub-file anchors, each with `anchor` (slugified) and `title` |
| `links_to` | string[] | no | Outbound links: entry IDs this file references |
| `links_from` | string[] | no | Inbound links: entry IDs that reference this file |
| `frontmatter` | object | no | The source file's YAML frontmatter |
| `stale` | boolean | yes | True when the content changed since the last scan |
| `stale_since` | datetime or null | no | When the entry was marked stale; null when it is not stale |
| `last_indexed` | datetime or null | no | When the entry was last scanned; null when it never was |

## Section Entries

A section entry describes a heading-bounded section of a large or structured file. It lives in the same `entries` list as file entries.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `parent` | string | yes | ID of the parent file entry |
| `tier` | enum | yes | Always `section`. File entries omit it or use `file` |
| `anchor` | string | yes | Slugified heading text (URL fragment) |
| `heading_level` | integer | yes | Heading level (2-6) |
| `line_range` | integer[2] | yes | `[start_line, end_line]`, 1-indexed, inclusive |

The ID of a section entry is `{parent_id}#{anchor}`, e.g. `polars:expressions.md#window-functions`. A section entry is embedded with the file entries.

## Meta Section

| Field | Type | Description |
|-------|------|-------------|
| `meta.generated_at` | datetime | When the index was last written |
| `meta.entry_count` | integer | Total entries in the index |
