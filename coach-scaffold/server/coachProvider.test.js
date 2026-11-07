import assert from "node:assert/strict";
import test from "node:test";
import { createCoachProvider } from "./coachProvider.js";

test("mock provider explains deterministic facts without changing the contract", async () => {
  const provider = createCoachProvider();
  const result = await provider.explain({
    message: "Can I afford my trip?",
    facts: { currency: "GBP", trip: { verdict: "THINK TWICE", total: 1200 } }
  });

  assert.equal(result.provider, "mock");
  assert.equal(typeof result.answer, "string");
  assert.ok(Array.isArray(result.actions));
});

test("future provider names fail explicitly instead of silently calling a service", () => {
  assert.throws(
    () => createCoachProvider({ name: "future-agent" }),
    (error) => error.code === "PROVIDER_NOT_IMPLEMENTED"
  );
});
