"""Run the public 30-question LoCoMo-Refined cohort through the shared harness."""

import argparse
import hashlib
import json
import urllib.request
from collections import defaultdict
from pathlib import Path

from amb.contracts import Conversation, QAPair, Sample, Session, Turn
from amb.datasets.locomo import CATEGORIES
from amb.registry import get_benchmark
from amb.reporting import RunReport
from amb.runner import RunConfig, Runner

ROOT = Path(__file__).parent
DATASET = "locomo-refined"


def load_file(source: dict, cache: Path) -> list[dict]:
    """Read a pinned public dataset file.

    Raises:
        ValueError: If the file hash differs from the pinned release.
    """
    path = cache / source["path"]
    if not path.exists():
        urllib.request.urlretrieve(source["url"], path)
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != source["sha256"]:
        raise ValueError(f"Unexpected hash for {path}")
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def load_samples(cache: Path) -> list[Sample]:
    """Join fixed question IDs to their full released text histories.

    Raises:
        ValueError: If a question or its required history cannot be verified.
    """
    cache.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "locomo_refined_30.json").read_text())
    questions, conversations = [
        load_file(source, cache) for source in manifest["files"]
    ]
    by_id = {row["qa_id"]: row for row in questions}
    grouped: dict[str, list[QAPair]] = defaultdict(list)
    for ref in manifest["questions"]:
        row = by_id[ref["id"]]
        if hashlib.sha256(row["question"].encode()).hexdigest() != ref["prompt_sha256"]:
            raise ValueError(f"Question changed: {ref['id']}")
        if not row["answer"] or row["is_multi_modality"]:
            raise ValueError(f"Invalid textual question: {ref['id']}")
        evidence = row["evidence"]
        grouped[row["sample_id"]].append(
            QAPair(
                question_id=row["qa_id"],
                question=row["question"],
                answer="Accept any of these reference answers: "
                + " | ".join(row["answer"]),
                category=CATEGORIES[int(row["category"])],
                evidence_turn_ids=evidence,
                evidence_session_ids=sorted(
                    {ident.split(":")[0].removeprefix("D") for ident in evidence}
                ),
            )
        )
    samples = []
    for row in conversations:
        ident = row["sample_id"]
        if ident not in grouped:
            continue
        sessions = [
            Session(
                session_id=str(session["session_index"]),
                timestamp=session["date_time"],
                turns=[
                    Turn(
                        turn_id=message["dia_id"],
                        speaker=message["speaker"],
                        text=message["text"],
                    )
                    for message in session["messages"]
                    if message["text"]
                ],
            )
            for session in row["sessions"]
        ]
        turn_ids = {turn.turn_id for session in sessions for turn in session.turns}
        if any(not set(q.evidence_turn_ids) <= turn_ids for q in grouped[ident]):
            raise ValueError(f"Missing textual evidence in {ident}")
        samples.append(
            Sample(
                sample_id=ident,
                dataset=DATASET,
                qa=grouped[ident],
                conversation=Conversation(
                    conversation_id=ident,
                    speakers=[row["speaker_a"], row["speaker_b"]],
                    sessions=sessions,
                ),
            )
        )
    if sum(len(sample.qa) for sample in samples) != 30:
        raise ValueError("Expected all 30 questions")
    return samples


def main() -> None:
    """Evaluate one memory framework with the shared reader and judge."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("system")
    parser.add_argument("--model", required=True)
    parser.add_argument("--embedding", required=True)
    args = parser.parse_args()
    params = {}
    if args.system not in {"naive", "agent-memory-lab"}:
        params["embedding_model"] = args.embedding
    if args.system not in {"naive", "opensquilla", "agent-memory-lab"}:
        params["model"] = args.model
    if args.system == "openviking":
        params["index_transcripts"] = True
    benchmark = get_benchmark(args.system).benchmark_class()(params=params)
    root = Path("comparator-runs")
    config = RunConfig(dataset=DATASET, model=args.model, k=10, workers=1, out=root)
    report = RunReport(
        Runner(benchmark, config, load_samples(root / "locomo-input")).run()
    )
    if args.model != "test":
        report.judge(args.model)
    report.save(root)


if __name__ == "__main__":
    main()
