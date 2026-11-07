async function postJson(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "Coach unavailable");
  return data;
}

export function askCoach(payload) {
  return postJson("/api/coach", payload);
}

export function submitPurchase(payload) {
  return postJson("/api/purchase-verdict", payload);
}