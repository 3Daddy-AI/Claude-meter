/**
 * Vercel Serverless Function
 * POST /api/probe
 *
 * Calls Anthropic's count_tokens endpoint (zero cost) with the user's API key
 * and returns the rate-limit headers, which tell us:
 *   - token limit per window
 *   - tokens remaining
 *   - when the window resets
 *
 * The API key is used only in-transit over HTTPS and is never stored.
 */
export default async function handler(req, res) {
  // CORS — allow any origin so the GitHub Pages front-end can call this
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    return res.status(204).end();
  }
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  const { apiKey, model } = req.body ?? {};

  if (!apiKey || typeof apiKey !== "string" || !apiKey.startsWith("sk-ant-")) {
    return res.status(400).json({ error: "Invalid API key format" });
  }
  if (!model || typeof model !== "string") {
    return res.status(400).json({ error: "Model is required" });
  }

  // Use count_tokens endpoint — returns input_tokens count, costs nothing
  const upstream = await fetch("https://api.anthropic.com/v1/messages/count_tokens", {
    method: "POST",
    headers: {
      "x-api-key":         apiKey,
      "anthropic-version": "2023-06-01",
      "content-type":      "application/json",
    },
    body: JSON.stringify({
      model,
      messages: [{ role: "user", content: "hi" }],
    }),
  });

  // Extract rate-limit headers (present even on count_tokens)
  const pick = (name) => upstream.headers.get(name);

  const rateLimits = {
    requests: {
      limit:     pick("anthropic-ratelimit-requests-limit"),
      remaining: pick("anthropic-ratelimit-requests-remaining"),
      reset:     pick("anthropic-ratelimit-requests-reset"),
    },
    tokens: {
      limit:     pick("anthropic-ratelimit-tokens-limit"),
      remaining: pick("anthropic-ratelimit-tokens-remaining"),
      reset:     pick("anthropic-ratelimit-tokens-reset"),
    },
    inputTokens: {
      limit:     pick("anthropic-ratelimit-input-tokens-limit"),
      remaining: pick("anthropic-ratelimit-input-tokens-remaining"),
      reset:     pick("anthropic-ratelimit-input-tokens-reset"),
    },
    outputTokens: {
      limit:     pick("anthropic-ratelimit-output-tokens-limit"),
      remaining: pick("anthropic-ratelimit-output-tokens-remaining"),
      reset:     pick("anthropic-ratelimit-output-tokens-reset"),
    },
  };

  if (!upstream.ok) {
    const body = await upstream.json().catch(() => ({}));
    return res.status(upstream.status).json({
      error: body?.error?.message ?? "Anthropic API error",
    });
  }

  const body = await upstream.json();

  return res.status(200).json({
    model,
    inputTokensUsed: body.input_tokens ?? null,
    rateLimits,
  });
}
