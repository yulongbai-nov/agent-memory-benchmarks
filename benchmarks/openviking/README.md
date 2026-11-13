# OpenViking benchmark adapter

The adapter uses OpenViking's HTTP session commit and memory search APIs. Each
benchmark sample gets its own trusted-mode user namespace; it must only be used
with a private, isolated benchmark server. The server must be configured with
the models passed to the benchmark. Commit processing is awaited before search.
Each source session is submitted as one user message containing its dated,
speaker-labelled transcript. This mapping should be considered when comparing
it with systems that receive individual dialogue turns.

Set `--param index_transcripts=true` to also preserve the original dated turns
in the sample's private OpenViking resources. The server embeds the turns and
ranks them together with extracted memories in one search. The adapter returns
full content and attaches source session and turn IDs to the indexed turns.
Extracted memories carry attribution only when a source is known. Server model
usage is unavailable. Remove the benchmark server's disposable volume after
the run.

The `openviking-e2e` workflow compares the transcript-enabled adapter with BM25
on three matching LoCoMo questions. Both receive the same 40 source turns.
The scores describe that sample only.
