"""Measure retrieval of prior same-repository issues on SWE-ContextBench Full."""

import argparse
import hashlib
import json
import statistics
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from pyarrow.parquet import read_table

from amb.contracts import Session, Turn
from amb.registry import get_benchmark

FILES = {
    "Experience": "e10d452123257fabc604e77985e34184ad7504788106ee3ac3e7e8f621303610",
    "Related": "394ce86dbf8e5b7471264625ad4879d70c676a5b43dd16e4d7416592547c8892",
    "Relationship": "f59b1a0fd021c6608bd185f15113cbbd26f804c20494da6d4827adb9ea70edb5",
}
REVISION = "12c65bd15e2559bc808065565e941ee7bbbd008f"


def date(row: dict) -> datetime:
    """Normalize release timestamps to UTC for eligibility checks."""
    stamp = datetime.fromisoformat(row["created_at"])
    return stamp.astimezone(UTC) if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def load(root: Path, name: str, columns: list[str]) -> list[dict]:
    """Validate release bytes and read the exact columns needed.

    Raises:
        ValueError: If the file differs from the pinned release.
    """
    path = root / f"SWEContextBench_{name}.parquet"
    if hashlib.sha256(path.read_bytes()).hexdigest() != FILES[name]:
        raise ValueError(f"Unexpected SHA-256 for {path}")
    return read_table(path, columns=columns).to_pylist()


def run(system: str, root: Path) -> dict:
    """Rank eligible source issues and account for coverage across the release."""
    fields = ["instance_id", "repo", "created_at", "problem_statement"]
    experience = load(root, "Experience", fields)
    targets = load(root, "Related", fields)
    relations = load(
        root, "Relationship", ["experience_instance_id", "related_instance_id"]
    )
    gold = defaultdict(set)
    for link in relations:
        gold[link["related_instance_id"]].add(link["experience_instance_id"])
    prior = defaultdict(list)
    for row in experience:
        prior[row["repo"]].append(row)
    by_repo = defaultdict(list)
    for index, row in enumerate(targets):
        by_repo[row["repo"]].append((index, row))
    benchmark = get_benchmark(system).benchmark_class()()
    version = benchmark.create_system().version()
    output = []
    total_ingest = 0.0
    for repo, group in sorted(by_repo.items()):
        target_ids = {row["instance_id"] for _, row in group}
        memory = benchmark.create_system()
        memory.setup()
        try:
            histories = iter(sorted(prior[repo], key=date))
            source = next(histories, None)
            available = set()
            for index, task in sorted(group, key=lambda pair: date(pair[1])):
                cutoff = date(task)
                start = time.perf_counter()
                while source is not None and date(source) < cutoff:
                    ident = source["instance_id"]
                    if ident not in target_ids:
                        memory.ingest_session(
                            repo,
                            Session(
                                session_id=ident,
                                timestamp=date(source).strftime("%Y-%m-%d"),
                                turns=[
                                    Turn(
                                        turn_id=ident,
                                        speaker="Issue",
                                        text=source["problem_statement"],
                                    )
                                ],
                            ),
                        )
                        available.add(ident)
                    source = next(histories, None)
                total_ingest += time.perf_counter() - start
                target_id = task["instance_id"]
                labels = gold[target_id] & available
                if not labels:
                    output.append(
                        {
                            "id": f"{target_id}:{index}",
                            "repo": repo,
                            "status": "no eligible label",
                        }
                    )
                    continue
                start = time.perf_counter()
                hits = memory.search(repo, task["problem_statement"], k=10)
                search_s = time.perf_counter() - start
                ranks = [
                    i
                    for i, hit in enumerate(hits, 1)
                    if labels.intersection(hit.session_ids)
                ]
                retrieved = set().union(*(set(hit.session_ids) for hit in hits))
                output.append(
                    {
                        "id": f"{target_id}:{index}",
                        "repo": repo,
                        "status": "scored",
                        "search_s": search_s,
                        "first_rank": min(ranks, default=None),
                        "recall": len(labels & retrieved) / len(labels),
                    }
                )
        finally:
            memory.teardown()
    scored = [row for row in output if row["status"] == "scored"]
    ranks = [row["first_rank"] for row in scored]
    return {
        "suite": "swe-contextbench-full",
        "revision": REVISION,
        "system": system,
        "system_version": version,
        "target_rows": len(targets),
        "experience_rows": len(experience),
        "scorable": len(scored),
        "unscorable": len(targets) - len(scored),
        "hit_at_1": sum(rank == 1 for rank in ranks) / len(ranks),
        "hit_at_10": sum(rank is not None for rank in ranks) / len(ranks),
        "recall_at_10": statistics.mean(row["recall"] for row in scored),
        "mrr_at_10": sum(1 / rank for rank in ranks if rank is not None) / len(ranks),
        "search_p50_s": statistics.median(row["search_s"] for row in scored),
        "ingest_s": total_ingest,
        "rows": output,
    }


def main() -> None:
    """Run the selected offline coding-memory comparator."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("system", choices=["naive", "agent-memory-lab"])
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = run(args.system, args.data)
    args.output.write_text(json.dumps(report, separators=(",", ":")) + "\n")
    print(
        "SWE_RETRIEVAL "
        + json.dumps(
            {k: v for k, v in report.items() if k != "rows"}, separators=(",", ":")
        )
    )


if __name__ == "__main__":
    main()
