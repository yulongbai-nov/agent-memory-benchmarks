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

"""Run the native Agent Memory Lab archive in a persistent Node process."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import ClassVar

from amb.agent.toolset import MemoryToolset
from amb.base import Benchmark, Memory
from amb.contracts import MemoryHit, Session


class LabMemory(Memory):
    """Import DSH-format source turns and retrieve native archive records."""

    name: ClassVar[str] = "agent-memory-lab"
    description: ClassVar[str] = "Agent Memory Lab native SQLite keyword archive"

    def version(self) -> str:
        """Report the exact framework checkout used for the benchmark."""
        if revision := os.environ.get("AGENT_MEMORY_LAB_REVISION"):
            return revision
        return subprocess.check_output(
            ["git", "-C", os.environ["AGENT_MEMORY_LAB_ROOT"], "rev-parse", "HEAD"],
            text=True,
            timeout=10,
        ).strip()

    def setup(self) -> None:
        """Start a worker with a private, temporary archive."""
        self.scratch = tempfile.TemporaryDirectory(prefix="amb-memory-lab-")
        self.worker = subprocess.Popen(
            [
                "node",
                str(Path(__file__).with_name("worker.cjs")),
                os.environ["AGENT_MEMORY_LAB_ROOT"],
                self.scratch.name,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env={
                key: os.environ[key] for key in ("PATH", "TMPDIR") if key in os.environ
            },
        )
        try:
            self._request("setup")
        except BaseException:
            self.teardown()
            raise

    def _request(self, op: str, **values: object) -> dict:
        assert self.worker.stdin is not None
        assert self.worker.stdout is not None
        self.worker.stdin.write(json.dumps({"op": op, **values}) + "\n")
        self.worker.stdin.flush()
        line = self.worker.stdout.readline()
        if not line:
            raise RuntimeError("Agent Memory Lab worker exited")
        response = json.loads(line)
        if error := response.get("error"):
            raise RuntimeError(error)
        return response

    def ingest_session(self, conversation_id: str, session: Session) -> None:
        """Send dated turns to the native source importer."""
        if session.turns:
            when = session.time()
            self._request(
                "ingest",
                project=conversation_id,
                session=session.session_id,
                timestamp=when.isoformat() if when else None,
                turns=[
                    {"id": turn.turn_id, "content": session.dated(turn)}
                    for turn in session.turns
                ],
            )

    def search(self, conversation_id: str, query: str, k: int = 10) -> list[MemoryHit]:
        """Return ranked native archive records with their exact source IDs."""
        return [
            MemoryHit.model_validate(hit)
            for hit in self._request(
                "search", project=conversation_id, query=query, k=k
            )["hits"]
        ]

    def stats(self) -> dict:
        """Report native index size and imported source-turn count."""
        return self._request("stats")

    def teardown(self) -> None:
        """Stop the worker before removing its archive."""
        try:
            if self.worker.stdin is not None:
                self.worker.stdin.close()
            try:
                self.worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.worker.kill()
                self.worker.wait()
            if self.worker.stdout is not None:
                self.worker.stdout.close()
        finally:
            self.scratch.cleanup()


class LabBenchmark(Benchmark):
    """Expose Agent Memory Lab through the common harness."""

    name: ClassVar[str] = "agent-memory-lab"
    system_class = LabMemory
    search_toolset_class = MemoryToolset
