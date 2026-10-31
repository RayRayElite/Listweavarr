# Combining saved lists

In My Lists, choose **Select lists**, select at least two collections, then choose
**Combine lists**. The selection order is displayed in the preview dialog.

- Combine keeps unique entries from each source in order.
- Common entries keeps the first source's order, requiring a match in every source.
- Subtract keeps entries from the first source that are absent from the others.
- An optional exclusion list removes matching entries from any result.

Matching uses shared provider IDs and the same movie/show/season/episode scope.
Conflicting provider IDs prevent a match. Unknown identities stay separate; names
alone never deduplicate. A whole-show entry does not absorb episode entries.
Correct unresolved metadata before relying on common/subtracted results.

Preview shows the count and first 100 entries. Creating the collection checks the
exact source revisions again. If a source changes, preview again. Generated items
start unchecked; run Compare with Plex for current availability. Nothing is
downloaded or published to Plex by generation.

The result stores its source rule and local per-entry provenance. **Rebuild from
sources** creates a fresh reviewed snapshot, preserving the earlier snapshot and
manual changes. This first increment deliberately does not overwrite edited
results or run automatic cascades. Deleted source lists must be restored/replaced
before rebuilding. Rules refer to local saved sources, including working Official
copies; install those copies before composing them.

Portable JSON/CSV exports share the generated contents, not private workspace
source IDs, provenance or an automatic subscription to someone else's local lists.
