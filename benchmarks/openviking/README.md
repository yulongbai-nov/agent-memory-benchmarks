# OpenViking benchmark adapter

The adapter uses OpenViking's HTTP session commit and memory search APIs. Each
benchmark sample gets its own trusted-mode user namespace; it must only be used
with a private, isolated benchmark server. The server must be configured with
the models passed to the benchmark. Commit processing is awaited before search.

The server stores extracted memories in its own namespace. Search results do not
currently expose verified source-session IDs to this adapter, so attribution is
left unavailable instead of guessing it. Model usage inside the server is not
yet measured, and is reported as unavailable rather than zero. The benchmark
server's disposable volume should be removed after the run.

The `openviking-e2e` workflow is a small functional check, not a scored or
fairness-qualified benchmark run.
