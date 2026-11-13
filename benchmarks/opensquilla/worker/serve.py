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

"""Run native OpenSquilla session indexing and retrieval over local pipes."""

import asyncio
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from opensquilla.memory import (
    LongTermMemoryStore,
    MemoryRetriever,
    MemorySearchOpts,
    MemorySource,
    OpenAIEmbeddingProvider,
)
from opensquilla.memory.session_source import build_session_source_document


async def serve() -> None:
    """Keep one SQLite store and one event loop for a benchmark sample.

    Raises:
        RuntimeError: If native hybrid search cannot initialize.
        ValueError: If the caller requests an unknown operation.
    """
    reply = sys.stdout
    store = None
    sources: dict[str, tuple[str, dict[int, str]]] = {}
    chunks = 0
    db_path: Path | None = None
    with redirect_stdout(sys.stderr):
        try:
            for line in sys.stdin:
                try:
                    request = json.loads(line)
                    op = request["op"]
                    if op == "initialize":
                        model = request["embedding_model"]
                        provider = (
                            OpenAIEmbeddingProvider(
                                os.environ["OPENAI_API_KEY"], model=model
                            )
                            if model
                            else None
                        )
                        db_path = Path(request["db_path"])
                        store = LongTermMemoryStore(
                            db_path, embedding_provider=provider
                        )
                        await store.initialize()
                        if model and not store._vec_available:
                            raise RuntimeError(
                                "sqlite-vec is unavailable for hybrid search"
                            )
                        retriever = MemoryRetriever(store)
                        result: dict = {}
                    elif op == "index":
                        assert store is not None
                        session_id = request["session_id"]
                        timestamp = request["timestamp"]
                        session = SimpleNamespace(
                            session_id=session_id,
                            updated_at=int(timestamp * 1000)
                            if timestamp is not None
                            else None,
                        )
                        turns = request["turns"]
                        entries = [
                            SimpleNamespace(id=i, role="user", content=turn["text"])
                            for i, turn in enumerate(turns, 1)
                        ]
                        document = build_session_source_document(session, entries)
                        chunks += await store.index_file(
                            document.path,
                            document.content,
                            source=MemorySource.sessions,
                            mtime=document.mtime,
                        )
                        turn_lines = {}
                        for number, text in enumerate(document.content.splitlines(), 1):
                            if text.startswith("[entry "):
                                entry_id = int(text[7:].partition("]")[0])
                                turn_lines[number] = turns[entry_id - 1]["id"]
                        sources[document.path] = (session_id, turn_lines)
                        result = {}
                    elif op == "search":
                        hits = await retriever.search(
                            request["query"],
                            MemorySearchOpts(
                                max_results=request["k"],
                                min_score=0.0,
                                source=MemorySource.sessions,
                            ),
                        )
                        result = {"hits": []}
                        for hit in hits:
                            session_id, turn_lines = sources[hit.path]
                            result["hits"].append(
                                {
                                    "content": hit.text or hit.snippet,
                                    "score": hit.score,
                                    "session_ids": [session_id],
                                    "turn_ids": [
                                        turn_id
                                        for number, turn_id in turn_lines.items()
                                        if hit.start_line <= number <= hit.end_line
                                    ],
                                    "metadata": {
                                        "path": hit.path,
                                        "start_line": hit.start_line,
                                        "end_line": hit.end_line,
                                    },
                                }
                            )
                    else:
                        raise ValueError(f"Unknown operation {op}")
                    assert store is not None
                    assert db_path is not None
                    usage = store.consume_embedding_usage()
                    result["usage"] = {
                        "embedding_calls": usage["request_count"],
                        "embedding_tokens": usage["input_tokens"],
                    }
                    result["stats"] = {
                        "indexed_sessions": len(sources),
                        "indexed_chunks": chunks,
                        "index_bytes": sum(
                            p.stat().st_size
                            for p in db_path.parent.glob("memory.sqlite*")
                        ),
                        "embedding_model": usage["model"],
                    }
                except (KeyError, RuntimeError, ValueError, OSError) as exc:
                    result = {"error": f"{type(exc).__name__}: {exc}"}
                print(json.dumps(result), file=reply, flush=True)
        finally:
            if store is not None:
                await store.close()


if __name__ == "__main__":
    asyncio.run(serve())
