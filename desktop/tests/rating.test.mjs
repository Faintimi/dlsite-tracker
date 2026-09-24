import assert from "node:assert/strict";
import test from "node:test";
import { cardRatingColor, preciseRatingColor, preciseRatingText, ratingColor, ratingText } from "../src/lib/ui.ts";

test("card score label stays 5 while hover details show official two-decimal scores", () => {
  const game = { rating: 5, rating_precise: 4.83, rating_count: 31 };
  assert.equal(ratingText(game), "5（31）");
  assert.equal(preciseRatingText(game), "4.83（31）");
  assert.equal(preciseRatingText({ rating_precise: 4.7 }), "4.70");
  assert.equal(preciseRatingText({ rating: 5, rating_precise: null }), "暂无精确评分");
});

test("4.0–4.5 and precise 4.70+ exchange their former colors", () => {
  assert.equal(ratingColor(4), "#bf5af2");
  assert.equal(ratingColor(4.5), "var(--rating-warm)");
  assert.equal(ratingColor(5), "#ffc700");
  assert.equal(preciseRatingColor(4.5), "var(--rating-warm)");
  assert.equal(preciseRatingColor(4.69), "#ffc700");
  assert.equal(preciseRatingColor(4.7), "#ff375f");
  assert.equal(preciseRatingColor(4.83), "#ff375f");
  assert.equal(preciseRatingColor(null), "var(--muted)");
});

test("new top rating tier shares the card's 5 label but has a distinct color", () => {
  const game = { rating: 5, rating_precise: 4.7, rating_count: 31 };
  assert.equal(ratingText(game), "5（31）");
  assert.equal(cardRatingColor(game), "#ff375f");
  assert.equal(cardRatingColor({ rating: 5, rating_precise: 4.69 }), "#ffc700");
  assert.equal(cardRatingColor({ rating: 5, rating_precise: null }), "#ffc700");
  assert.equal(cardRatingColor({ rating: 4.5, rating_precise: null }), "var(--rating-warm)");
  assert.equal(cardRatingColor({ rating: 4.5, rating_precise: 4.83 }), "#ff375f");
});
