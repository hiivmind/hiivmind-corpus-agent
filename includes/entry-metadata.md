### Entry Metadata Generation

For each documentation file, generate the entry metadata. Code fills in the other fields of the entry; make these six and no others:

1. **path**: the path exactly as it was given, not the full path.
2. **title**: from the YAML frontmatter `title` field, or the first `# Heading`, or derived from the filename (hyphens and underscores become spaces, title case).
3. **summary**: 1-2 sentences describing the file's content. Focus on what a reader will find, not on the file's structure.
4. **tags**: 2-5 curated facets. Use the controlled vocabulary where the corpus has conventions. Prefer lowercase, hyphenated terms.
5. **keywords**: 3-10 significant terms from the content body: function names, API terms, domain-specific identifiers. Broader than tags.
6. **category**: one of `reference` (API docs, config reference), `tutorial` (step-by-step guides), `guide` (conceptual explanations), `api` (API endpoint docs), `config` (configuration reference), `navigation` (index and overview pages), `journal` (changelogs, release notes).
