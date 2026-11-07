import express from "express";
import cors from "cors";
import { systemPrompt } from "./coachPrompt.js";
import { createCoachProvider } from "./coachProvider.js";

const app = express();
app.use(cors());
app.use(express.json({ limit: "20kb" }));

const synthetic = {
  profile: { name: "Amina Okafor", school: "Northeastern University", country: "Nigeria", currency: "GBP" },
  disclaimer: "Synthetic demo data — not connected to a bank. Educational guidance only; not financial, immigration, tax, or legal advice."
};

function validate(body) {
  if (!body || typeof body.message !== "string" || body.message.trim().length < 2) return "message must be at least 2 characters";
  if (body.message.length > 500) return "message must be 500 characters or fewer";
  if (body.consent !== true) return "consent is required";
  if (body.profile && typeof body.profile !== "object") return "profile must be an object";
  if (body.facts && typeof body.facts !== "object") return "facts must be an object";
  return null;
}

function validateCoachResponse(value) {
  return value
    && typeof value.answer === "string"
    && value.answer.length > 0
    && Array.isArray(value.actions)
    && value.actions.length <= 4
    && value.actions.every((action) => typeof action === "string");
}

function validatePurchase(body) {
  if (!body || typeof body.item !== "string" || body.item.trim().length < 2) return "item must be at least 2 characters";
  if (!Number.isFinite(Number(body.amount)) || Number(body.amount) <= 0) return "amount must be greater than zero";
  if (body.currency !== "GBP") return "currency must be GBP";
  if (!body.facts || typeof body.facts !== "object") return "deterministic purchase facts are required";
  if (!["GO", "THINK TWICE", "SKIP FOR NOW"].includes(body.facts.verdict)) return "facts.verdict is invalid";
  if (!Number.isFinite(Number(body.facts.impact))) return "facts.impact must be numeric";
  return null;
}

app.get("/api/health", (_req, res) => res.json({
  ok: true,
  service: "harbor-coach",
  provider: process.env.COACH_PROVIDER || "mock"
}));
app.post("/api/coach", (req, res) => {
  const error = validate(req.body);
  if (error) return res.status(400).json({ error, code: "VALIDATION_ERROR" });
  const message = req.body.message.toLowerCase();
  const complete = (coach) => {
    const response = {
      answer: coach.answer,
      actions: coach.actions,
      provider: coach.provider,
      synthetic: true,
      consent: true,
      disclaimer: synthetic.disclaimer,
      context: {
        ...synthetic.profile,
        prompt: systemPrompt,
        factsReceived: Boolean(req.body.facts)
      }
    };
    if (!validateCoachResponse(response)) {
      return res.status(502).json({ error: "coach response failed schema validation", code: "RESPONSE_SCHEMA_ERROR" });
    }
    return res.json(response);
  };

  let provider;
  try {
    provider = createCoachProvider({ name: process.env.COACH_PROVIDER || "mock" });
  } catch (providerError) {
    return res.status(502).json({
      error: providerError.message,
      code: providerError.code || "PROVIDER_ERROR",
      provider: process.env.COACH_PROVIDER || "mock"
    });
  }
  provider.explain({ message, facts: req.body.facts, profile: req.body.profile })
    .then(complete)
    .catch((providerError) => res.status(502).json({
      error: providerError.message,
      code: providerError.code || "PROVIDER_ERROR",
      provider: process.env.COACH_PROVIDER || "mock"
    }));
});

app.post("/api/purchase-verdict", (req, res) => {
  const error = validatePurchase(req.body);
  if (error) return res.status(400).json({ error, code: "VALIDATION_ERROR" });
  const verdict = req.body.facts.verdict;
  const message = verdict === "GO"
    ? `£${Number(req.body.amount).toFixed(2)} for ${req.body.item.trim()} fits within today's planned spending.`
    : verdict === "THINK TWICE"
      ? `£${Number(req.body.amount).toFixed(2)} for ${req.body.item.trim()} is possible, but check upcoming bills first.`
      : `£${Number(req.body.amount).toFixed(2)} for ${req.body.item.trim()} would put your flexible budget under pressure.`;
  res.json({
    item: req.body.item.trim(),
    amount: Number(req.body.amount),
    currency: "GBP",
    verdict,
    impact: Number(req.body.facts.impact),
    message,
    synthetic: true,
    disclaimer: synthetic.disclaimer
  });
});

app.use(express.static("../client/dist"));
app.get("*", (_req, res) => res.sendFile("index.html", { root: "../client/dist" }));

const port = process.env.PORT || 3001;
app.listen(port, () => console.log(`Harbor coach API listening on ${port}`));