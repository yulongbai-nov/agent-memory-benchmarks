# MIT License
#
# Copyright (c) 2026 René-Jean Corneille
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Run one bounded comparator job and sample local stack memory on Linux."""

import argparse
import json
import os
import platform
import subprocess
import time
from pathlib import Path

SYSTEMS = (
    "naive",
    "agent-memory-lab",
    "opensquilla",
    "openviking",
    "cognee",
    "everos",
    "fraise",
    "graphiti",
    "hindsight",
    "langmem",
    "mem0",
    "memos",
)
MODEL = "openai:gpt-6-luna"
EMBEDDING = "openai:text-embedding-3-small"


def command_for(system: str, suite: str = "locomo-refined") -> list[str]:
    """Build the shared LoCoMo invocation with the adapter's native entry point."""
    args = [
        "run",
        "--system",
        system,
        "--dataset",
        "locomo",
        "--model",
        MODEL,
        "--judge",
        "--judge-model",
        MODEL,
        "--limit",
        "1",
        "--turns",
        "40",
        "--questions",
        "3",
        "--workers",
        "1",
        "--k",
        "10",
        "--runs-dir",
        "comparator-runs",
    ]
    if system == "openviking":
        args += ["--param", "index_transcripts=true"]
    if system not in {"naive", "opensquilla", "agent-memory-lab"}:
        args += ["--llm", MODEL]
    if system not in {"naive", "agent-memory-lab"}:
        args += ["--embedding", EMBEDDING]
    invocation = ["amb", *args]
    if suite == "locomo-refined":
        invocation = [
            "python",
            "scripts/comparator/locomo_refined.py",
            system,
            "--model",
            MODEL,
            "--embedding",
            EMBEDDING,
        ]
    if system in {"naive", "opensquilla", "openviking", "agent-memory-lab"}:
        return [f".venv/bin/{invocation[0]}", *invocation[1:]]
    return [
        "docker",
        "compose",
        "-f",
        f"benchmarks/{system}/docker-compose.yaml",
        "run",
        "--rm",
        "-T",
        "-v",
        f"{Path('comparator-runs').resolve()}:/amb/comparator-runs",
        "--entrypoint",
        "/bin/sh",
        "benchmark",
        "-ec",
        "uv pip install --no-config --python /amb/.venv/bin/python openai==3.49.0; "
        'executable="$1"; shift; exec "/amb/.venv/bin/$executable" "$@"',
        "amb",
        *invocation,
    ]


def process_rss_kib(pid: int) -> int:
    """Sum RSS of the harness and its children from one process-table snapshot."""
    lines = subprocess.check_output(["ps", "-eo", "pid=,ppid=,rss="], text=True)
    rows = [tuple(map(int, line.split())) for line in lines.splitlines()]
    descendants = {pid}
    while True:
        expanded = descendants | {
            child for child, parent, _ in rows if parent in descendants
        }
        if expanded == descendants:
            return sum(rss for child, _, rss in rows if child in descendants)
        descendants = expanded


def docker_memory_kib(system: str) -> int:
    """Sum Docker's working-set estimate for the active candidate's containers."""
    if system in {"naive", "opensquilla", "agent-memory-lab"}:
        return 0
    filter_arg = (
        "name=^/amb-openviking$"
        if system == "openviking"
        else f"label=com.docker.compose.project=amb-{system}"
    )
    ids = subprocess.check_output(
        ["docker", "ps", "-q", "--filter", filter_arg], text=True
    ).split()
    if not ids:
        return 0
    lines = subprocess.check_output(
        ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", *ids],
        text=True,
        timeout=12,
    ).splitlines()
    units = {"B": 1 / 1024, "KiB": 1, "MiB": 1024, "GiB": 1024**2, "TiB": 1024**3}
    total = 0.0
    for line in lines:
        usage = line.split("/", 1)[0].strip()
        for unit, factor in sorted(units.items(), key=lambda pair: -len(pair[0])):
            if usage.endswith(unit):
                total += float(usage.removesuffix(unit)) * factor
                break
    return round(total)


def main() -> None:
    """Write run-level metrics even when the candidate exits with errors.

    Raises:
        SystemExit: If the candidate did not complete all judged questions.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("system", choices=SYSTEMS)
    parser.add_argument(
        "--suite", choices=["locomo", "locomo-refined"], default="locomo-refined"
    )
    args = parser.parse_args()
    system, suite = args.system, args.suite
    root = Path("comparator-runs")
    root.mkdir(exist_ok=True)
    cpu = subprocess.check_output(["lscpu", "--json"], text=True)
    host = {row["field"].rstrip(":"): row["data"] for row in json.loads(cpu)["lscpu"]}
    host_info = {
        "cpu": host.get("Model name"),
        "logical_cpus": os.cpu_count(),
        "architecture": platform.machine(),
        "memory_kib": int(Path("/proc/meminfo").read_text().splitlines()[0].split()[1]),
        "image_version": os.environ.get("ImageVersion"),
    }
    start = time.monotonic()
    samples = []
    dropped = 0
    with subprocess.Popen(command_for(system, suite)) as process:
        while process.poll() is None:
            try:
                samples.append(process_rss_kib(process.pid) + docker_memory_kib(system))
            except (OSError, ValueError, subprocess.SubprocessError):
                dropped += 1
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                continue
    metrics = {
        "wall_seconds": time.monotonic() - start,
        "sampled_peak_kib": max(samples) if samples else None,
        "memory_samples": len(samples),
        "dropped_memory_samples": dropped,
        "runner": host_info,
        "exit_code": process.returncode,
    }
    (root / "runtime.json").write_text(json.dumps(metrics, indent=2))
    matches = list(root.glob(f"{suite}/{system}/*/summary.json"))
    if process.returncode or len(matches) != 1:
        raise SystemExit(f"{system} did not produce one complete benchmark run")
    summary = json.loads(matches[0].read_text())
    rows = [
        json.loads(line)
        for line in (matches[0].parent / "results.jsonl").read_text().splitlines()
    ]
    if (
        len(rows) != (30 if suite == "locomo-refined" else 3)
        or summary.get("errors")
        or any(row.get("judge_correct") is None for row in rows)
    ):
        raise SystemExit(f"{system} returned errors or unjudged questions")
    print(
        "COMPARATOR_SUMMARY "
        + json.dumps({"summary": summary, "runtime": metrics}, separators=(",", ":"))
    )
    for row in rows:
        print("COMPARATOR_QUESTION " + json.dumps(row, separators=(",", ":")))
    print(
        "COMPARATOR_RESULT "
        + json.dumps(
            {
                "summary": summary,
                "questions": rows,
                "runtime": metrics,
                "ingestion": json.loads(
                    (matches[0].parent / "ingest.json").read_text()
                ),
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
