# OpenSquilla memory benchmark

The adapter starts a separate Python process containing OpenSquilla 0.5.8.
It sends dated turns through OpenSquilla's session formatter, indexes the
result with the native SQLite store, and searches using its memory retriever.
The benchmark harness supplies the answerer and judge. OpenSquilla's agent,
gateway, router, and consolidation are outside this benchmark.

The comparison uses the native OpenAI embedding provider with
`text-embedding-3-small`. Pass `--embedding none` for a keyword-only smoke test.
Set `OPENSQUILLA_PYTHON` to the Python executable in the separate environment.
The comparator workflow pins the official release wheel and SHA-256.

An isolated SQLite database is created per sample. Embedding token usage
is estimated by OpenSquilla. Source IDs are mapped from the native session
paths and chunk line spans.
