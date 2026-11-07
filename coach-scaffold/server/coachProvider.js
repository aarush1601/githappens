export function mockCoachResponse(message) {
  let answer = "You’re doing the right thing by checking before acting. Start with your essentials, keep a small buffer, and make the next step specific.";
  let actions = ["Review this month’s essentials", "Set a small safety buffer"];
  if (message.includes("trip") || message.includes("travel")) {
    answer = "A trip can be a great reset. Use the simulator to include one-time costs, monthly costs, and a 10% currency cushion before you commit.";
    actions = ["Open trip simulator", "Compare a shorter trip"];
  } else if (message.includes("rent") || message.includes("housing")) {
    answer = "Keep rent and utilities protected first. If a payment feels tight, contact your school’s international student or financial support office early rather than waiting for a missed payment.";
    actions = ["List bills due this month", "Find campus support"];
  } else if (message.includes("home") || message.includes("send")) {
    answer = "For money sent home, choose an amount that still leaves your essentials and buffer intact. Compare the total fee and exchange rate, not just the advertised transfer fee.";
    actions = ["Set a monthly sending limit", "Check the full exchange cost"];
  }
  return { answer, actions, provider: "mock" };
}

export function createCoachProvider({ name = "mock" } = {}) {
  if (name !== "mock") {
    const error = new Error(`Coach provider "${name}" is not implemented yet.`);
    error.code = "PROVIDER_NOT_IMPLEMENTED";
    throw error;
  }
  return {
    name,
    explain: async ({ message }) => mockCoachResponse(message.toLowerCase())
  };
}
