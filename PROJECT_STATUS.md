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
- [x] Validate the OpenViking adapter's session ingestion and retrieval against
  a live isolated server on GitHub Actions (run 43240058396). Unique user
  namespaces are covered by a local HTTP contract test; source-session
  attribution remains unavailable until the server supplies evidence.
- [x] Test the `Develop` environment's `TEXT_EMBEDDING_3_SMALL_OPENAI_KEY`
  with text-embedding-3-small and GPT-6 Luna on GitHub Actions.
- [x] Validate an OpenViking ingest-and-recall GitHub Actions smoke workflow.
- [x] Validate a scored OpenViking LoCoMo smoke run and save its output. Run
  43241258533 completed three judged questions with zero execution errors; its
  score was 0/3 and is too small to rank systems. Run 43240475091 is invalid:
  all three answers errored despite a successful workflow exit. The smoke job
  now installs OpenAI SDK 3.49.0 after the locked sync and checks for errors
  and unjudged answers. This temporary smoke-only override differs from the
  workspace lock; other candidates have not been validated against it.
- [x] Run a small end-to-end benchmark and retain its results and configuration.
- [x] Run a three-question comparison against BM25 with the same question IDs
  and runner (43242463379). OpenViking scored 0/3 with no recorded hits; BM25
  scored 2/3. This sample is too small to rank systems.
- [ ] Investigate the lack of OpenViking hits on the LoCoMo smoke questions.
  Run 43243874437 showed zero memory writes for all three LoCoMo sessions,
  although the synthetic fact produced a memory. Test one dated, speaker-labelled
  transcript per source session and report this mapping in comparisons. Direct
  synthetic recall passed in several runs and failed once.
- [ ] Extend recorded CPU, core count and memory capacity with measured
  complete-stack resource use and report elapsed times transparently.
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
charges even when the runner is free. A smoke test is not a representative
benchmark comparison.
