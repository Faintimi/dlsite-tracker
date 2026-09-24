import assert from "node:assert/strict";
import test from "node:test";
import { matchingGenreCandidates } from "../src/lib/genreCatalog.ts";

test("only exact official names map to an importable genre ID", () => {
  const catalog = [{ id: "016", name: "奇幻" }, { id: "046", name: "后宫" }];
  assert.deepEqual(matchingGenreCandidates(" 奇幻 ", catalog, []), [{ id: "016", name: "奇幻" }]);
  assert.deepEqual(matchingGenreCandidates("奇", catalog, []), []);
  assert.deepEqual(matchingGenreCandidates("幻想", catalog, []), []);
});

test("duplicate names remain separate choices, while imported IDs are deduplicated", () => {
  const catalog = [{ id: "016", name: "奇幻" }, { id: "999", name: "奇幻" }];
  const imported = [{ id: "016", name: "奇幻", depth: 200 }];
  assert.deepEqual(matchingGenreCandidates("奇幻", catalog, imported), catalog);
  assert.deepEqual(matchingGenreCandidates("奇幻", [], imported), [{ id: "016", name: "奇幻" }]);
});
