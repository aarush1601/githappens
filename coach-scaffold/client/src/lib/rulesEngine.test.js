import assert from "node:assert/strict";
import test from "node:test";
import { calculateTrip, evaluatePurchase } from "./rulesEngine.js";

test("new purchase input produces a deterministic GBP verdict", () => {
  const result = evaluatePurchase({
    balance: 1800,
    billsDue: 260,
    safeToSpend: 90,
    amount: 60,
    category: "flexible"
  });

  assert.equal(result.verdict, "THINK TWICE");
  assert.equal(result.impact, 30);
  assert.match(result.alternative, /£/);
});

test("long GBP trip includes the currency cushion and inflation", () => {
  const result = calculateTrip({
    balance: 1800,
    monthlyIncome: 1350,
    monthlyCosts: 1180,
    oneTimeCosts: 500,
    monthlyCosts: 700,
    months: 12
  });

  assert.equal(result.currencyCushionRate, 0.1);
  assert.ok(result.inflationMultiplier > 1);
  assert.ok(result.cushion > 0);
  assert.ok(["GO", "THINK TWICE", "SKIP FOR NOW"].includes(result.verdict));
});
