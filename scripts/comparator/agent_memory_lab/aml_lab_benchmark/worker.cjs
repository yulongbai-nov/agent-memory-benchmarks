"use strict";

const { join } = require("node:path");
const { stat, writeFile, rm } = require("node:fs/promises");
const { createInterface } = require("node:readline");

const [root, dir] = process.argv.slice(2);
const { openArchive } = require(join(root, "lib/archive.cjs"));
const { readDsh } = require(join(root, "lib/adapters"));
const { migrateJsonToSqlite } = require(join(root, "lib/storage-sqlite.cjs"));
const { originalCapture } = require(join(root, "lib/originals.cjs"));
const { openStorage } = require(join(root, "lib/storage.cjs"));

let archive;
let imported = 0;
const provenance = new Map();

async function ingest({ project, session, timestamp, turns }) {
  const file = join(dir, "lo-co-mo-input.jsonl");
  const lines = turns.map((turn, index) => ({
    type: "user/message", seq: index + 1,
    ...(timestamp ? { time: timestamp } : {}),
    data: { role: "user", id: turn.id, text: turn.content },
  }));
  await writeFile(file, lines.map((line) => JSON.stringify(line)).join("\n") + "\n", { mode: 0o600 });
  try {
    for await (const batch of readDsh({
      owner: "benchmark", project, instance: "locomo", session, file,
      captureOriginal: originalCapture(dir),
    })) {
      const receipt = await archive.importBatch(batch);
      imported += receipt.imported;
      for (const item of batch.items) {
        const turn = turns[item.metadata.coordinate - 1];
        provenance.set(item.id, { session, turn: turn.id });
      }
    }
  } finally {
    await rm(file, { force: true });
  }
}

async function search({ project, query, k }) {
  const words = new Set(query.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []);
  const scope = { owner: "benchmark", project };
  // Native archive keyword lookup is substring-based. Count the query terms
  // found in each native record to produce a deterministic question ranking.
  const ranked = new Map();
  for (const keyword of words) {
    for (const row of await archive.listItems(scope, { keyword })) {
      const item = ranked.get(row.versionId) ?? { row, score: 0 };
      item.score++;
      ranked.set(row.versionId, item);
    }
  }
  return [...ranked.values()]
    .sort((a, b) => b.score - a.score || a.row.item.id.localeCompare(b.row.item.id))
    .slice(0, k)
    .map(({ row, score }) => {
      const ref = provenance.get(row.item.id);
      return { content: row.item.text, score, session_ids: [ref.session], turn_ids: [ref.turn] };
    });
}

async function handle(request) {
  switch (request.op) {
    case "setup": {
      const storage = await openStorage({ dir });
      await storage.transaction(() => {});
      await migrateJsonToSqlite({ dir });
      archive = await openArchive({ dir });
      return {};
    }
    case "ingest":
      await ingest(request);
      return {};
    case "search":
      return { hits: await search(request) };
    case "stats":
      return { stored_turns: imported, sqlite_bytes: (await stat(archive.indexFile)).size };
    default:
      throw new Error("Unknown Agent Memory Lab operation");
  }
}

async function main() {
  for await (const line of createInterface({ input: process.stdin, crlfDelay: Infinity })) {
    try {
      const result = await handle(JSON.parse(line));
      process.stdout.write(JSON.stringify(result) + "\n");
    } catch (error) {
      process.stdout.write(JSON.stringify({ error: error.message }) + "\n");
    }
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
