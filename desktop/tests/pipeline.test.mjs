import assert from "node:assert/strict";
import test from "node:test";

import { isRunning, isStaleActive, staleUpdateSummary } from "../src/lib/pipeline.ts";

test("recent quick update remains active", () => {
  const state = { phase: "rankings", years: "quick", updated_ts: 1000 };
  assert.equal(isRunning(state, 1050), true);
  assert.equal(isStaleActive(state, 1050), false);
});

test("abandoned quick update stops blocking the UI", () => {
  const state = { phase: "rankings", years: "quick", updated_ts: 1000 };
  assert.equal(isRunning(state, 4601), false);
  assert.equal(isStaleActive(state, 4601), true);
  assert.match(staleUpdateSummary(state), /可能已中断/);
});

test("missing timestamp is not treated as proof of a running process", () => {
  assert.equal(isRunning({ phase: "rankings", years: "quick" }, 5000), false);
  assert.equal(isStaleActive({ phase: "rankings", years: "quick" }, 5000), true);
});

test("long-running full maintenance keeps its wider time window", () => {
  const state = { phase: "import", years: "daily", updated_ts: 1000 };
  assert.equal(isRunning(state, 1000 + 6 * 3600), true);
  assert.equal(isStaleActive(state, 1000 + 49 * 3600), true);
  assert.equal(isStaleActive({ phase: "done", years: "quick", updated_ts: 1000 }, 999999), false);
});
