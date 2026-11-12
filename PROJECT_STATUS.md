# OpenViking benchmark project

## Goal

Compare OpenViking with the existing agent memory systems using the same
datasets, models, evaluation protocol and GitHub-hosted runner class. Preserve
evidence and make incomplete runs visible. Keep iteration focused on a working
end-to-end path before expanding the benchmark.

## Current milestone: OpenViking

- [x] Fork the upstream benchmark into a public repository.
- [ ] Verify the fork's existing tests and an offline baseline locally.
- [ ] Implement an OpenViking adapter with isolated sample state, chronological
  ingestion, processing completion, search and source provenance.
- [ ] Add an OpenViking GitHub Actions workflow using the existing OpenAI
  embedding model and `TEXT_EMBEDDING_3_SMALL_OPENAI_KEY` repository secret.
- [ ] Run a small end-to-end benchmark and retain its results and configuration.
- [ ] Run a matching comparison against an existing provider.
- [ ] Record actual runner CPU, core count and memory; report elapsed time and
  resource use without pretending different CPUs are identical.
- [ ] Display comparison results with clear quality, speed, cost, resource and
  completion status.

## Later

- [ ] Evaluate integration of https://github.com/yulongbai-nov/agent-memory-lab
  as a benchmark participant. Its API and actual scope need inspection first.
- [ ] Add further datasets or candidates only after the first end-to-end path
  works; document-based candidates are out of the current milestone.

## Constraints

Use public GitHub-hosted runners and pin comparable evaluation settings.
The embedding secret covers embeddings only: ingestion, answering and judging
also require a configured language model. Do not copy secrets into the repo or
print them. API use can incur charges even when the runner is free.
