/**
 * injected.js — ページのコンテキストで動作
 * Claude.ai の fetch 通信を傍受して使用量データを収集する
 */
(function () {
  if (window.__claudeMeterInjected) return;
  window.__claudeMeterInjected = true;

  const orig = window.fetch.bind(window);

  window.fetch = async function (input, init) {
    const res = await orig(input, init);
    const url = (typeof input === "string" ? input : input?.url) ?? "";

    // Claude.ai の API レスポンスのみ処理
    if (!url.includes("claude.ai") && !url.startsWith("/")) {
      return res;
    }

    try {
      const clone = res.clone();
      const contentType = clone.headers.get("content-type") ?? "";
      if (!contentType.includes("application/json")) return res;

      clone.json().then((data) => {
        const extracted = extractUsage(url, data);
        if (extracted) {
          window.postMessage({ type: "CLAUDE_METER_DATA", payload: extracted }, "*");
        }
      }).catch(() => {});
    } catch (_) {}

    return res;
  };

  /**
   * APIレスポンスから使用量情報を抽出する
   * Claude.ai の内部 API 構造に合わせてパターンマッチング
   */
  function extractUsage(url, data) {
    const result = {};

    // ── アカウント / プラン情報 ──
    if (data?.account?.subscription || data?.subscription) {
      const sub = data.account?.subscription ?? data.subscription;
      result.plan = sub.plan ?? sub.name ?? sub.tier ?? null;
    }

    // ── モデル別使用量 ──
    // 例: { limits: { claude-opus-4-6: { remaining: 20, limit: 30, reset_at: "..." } } }
    const limits = data?.limits ?? data?.usage_limits ?? data?.rate_limits;
    if (limits && typeof limits === "object") {
      result.limits = parseLimits(limits);
    }

    // ── メッセージ残量（フラット形式）──
    // 例: { remaining_messages: 18, message_limit: 30, model: "claude-opus-4-6" }
    if (data?.remaining_messages != null || data?.messages_remaining != null) {
      const rem   = data.remaining_messages ?? data.messages_remaining;
      const total = data.message_limit ?? data.messages_limit ?? data.total_messages;
      const model = data.model ?? data.model_id ?? classifyFromUrl(url);
      result.limits = result.limits ?? {};
      const key = classifyModel(model ?? "");
      if (key) result.limits[key] = { remaining: rem, limit: total, reset: data.reset_at ?? data.reset };
    }

    // ── 利用可能モデル一覧 ──
    if (Array.isArray(data?.models)) {
      result.availableModels = data.models.map((m) => m.id ?? m.name ?? m).filter(Boolean);
    }

    return Object.keys(result).length > 0 ? result : null;
  }

  function parseLimits(obj) {
    const out = {};
    for (const [k, v] of Object.entries(obj)) {
      const key = classifyModel(k);
      if (!key) continue;
      out[key] = {
        remaining: v.remaining ?? v.remaining_messages ?? null,
        limit:     v.limit ?? v.total ?? v.message_limit ?? null,
        reset:     v.reset_at ?? v.reset ?? null,
      };
    }
    return Object.keys(out).length > 0 ? out : null;
  }

  function classifyModel(s) {
    s = s.toLowerCase();
    if (s.includes("opus"))   return "opus";
    if (s.includes("sonnet")) return "sonnet";
    if (s.includes("haiku"))  return "haiku";
    return null;
  }

  function classifyFromUrl(url) {
    if (url.includes("opus"))   return "opus";
    if (url.includes("sonnet")) return "sonnet";
    if (url.includes("haiku"))  return "haiku";
    return null;
  }
})();
