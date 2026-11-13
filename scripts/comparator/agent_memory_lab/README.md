# Agent Memory Lab

The LoCoMo comparator imports only benchmark messages through the native
DSH importer, saves originals and versioned records in a fresh SQLite archive,
and queries the native scoped keyword lookup. The adapter ranks returned
records by the number of distinct question terms matched and emits exact
turn and session IDs. The worker runs with no provider credentials.

This measures the native archive and keyword lookup with an adapter-level
ranker. Reviewed decision and task state, graph and wiki views, and optional
model-generated drafts are outside this comparison.
