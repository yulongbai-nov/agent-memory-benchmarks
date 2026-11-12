# OpenViking benchmark project

## Goal

Compare OpenViking with the existing agent memory systems using the same
datasets, models, evaluation protocol and GitHub-hosted runner class. Preserve
evidence and make incomplete runs visible. Keep iteration focused on a working
end-to-end path before expanding the benchmark.

## Current milestone: OpenViking

- [x] Fork the upstream benchmark into a public repository.
- [x] Verify the fork's existing tests and an offline baseline locally: 395
  tests passed; a three-question LoCoMo smoke run completed without a judge.
- [ ] Validate the OpenViking adapter's isolated sample state, chronological
  ingestion, processing completion and search against a live server. Source
  session attribution remains unavailable until the server supplies evidence.
- [x] Test the `Develop` environment's `TEXT_EMBEDDING_3_SMALL_OPENAI_KEY`
  with text-embedding-3-small and GPT-6 Luna on GitHub Actions.
- [ ] Validate the OpenViking end-to-end GitHub Actions smoke workflow.
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
The configured key is used for embeddings and GPT-6 Luna for the initial
smoke test. Do not copy secrets into the repo or print them. API use can incur
charges even when the runner is free. A smoke test is not a scored comparison.
