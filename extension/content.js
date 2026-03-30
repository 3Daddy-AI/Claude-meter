/**
 * content.js — Claude.ai のページで動作するコンテンツスクリプト
 * 1. injected.js をページコンテキストに注入（fetch 傍受）
 * 2. DOM から使用量テキストを定期スキャン
 * 3. 取得したデータを chrome.storage.local に保存
 */

// ── injected.js をページコンテキストに注入 ──────────────────────────────────
const script = document.createElement("script");
script.src = chrome.runtime.getURL("injected.js");
(document.head ?? document.documentElement).appendChild(script);
script.onload = () => script.remove();

// ── injected.js からのメッセージ受信 ────────────────────────────────────────
window.addEventListener("message", (e) => {
  if (e.source !== window) return;
  if (e.data?.type !== "CLAUDE_METER_DATA") return;
  mergeAndSave(e.data.payload);
});

// ── DOM スキャン（定期実行）──────────────────────────────────────────────────
function scanDOM() {
  const update = {};

  // 「X messages remaining」系のテキストを探す
  const allText = document.body?.innerText ?? "";

  // パターン例: "20 of 30 messages remaining"
  const m1 = allText.match(/(\d+)\s+of\s+(\d+)\s+(?:opus|sonnet|haiku)?\s*messages?\s+remaining/i);
  if (m1) {
    const modelHint = (allText.match(/opus|sonnet|haiku/i)?.[0] ?? "").toLowerCase();
    const key = modelHint || "sonnet"; // 不明な場合 sonnet と仮定
    update.limits = update.limits ?? {};
    update.limits[key] = { remaining: Number(m1[1]), limit: Number(m1[2]), reset: null };
  }

  // パターン例: "30 messages left"
  const m2 = allText.match(/(\d+)\s+messages?\s+left/i);
  if (m2 && !m1) {
    update.limits = update.limits ?? {};
    update.limits["sonnet"] = { remaining: Number(m2[1]), limit: null, reset: null };
  }

  // 使用中モデル名を取得（セレクターやヘッダーから）
  const modelEl = document.querySelector('[data-testid="model-selector-button"], [class*="model-name"], [class*="ModelSelector"]');
  if (modelEl) {
    update.currentModel = classifyModel(modelEl.innerText ?? "");
  }

  if (Object.keys(update).length > 0) mergeAndSave(update);
}

function classifyModel(s) {
  s = s.toLowerCase();
  if (s.includes("opus"))   return "opus";
  if (s.includes("sonnet")) return "sonnet";
  if (s.includes("haiku"))  return "haiku";
  return null;
}

// DOMContentLoaded 後にスキャン開始
document.addEventListener("DOMContentLoaded", () => {
  scanDOM();
  setInterval(scanDOM, 5_000);
});
// SPA でのルート変更にも対応
const obs = new MutationObserver(() => scanDOM());
const startObs = () => {
  if (document.body) obs.observe(document.body, { childList: true, subtree: true });
};
if (document.body) startObs();
else document.addEventListener("DOMContentLoaded", startObs);

// ── storage へ保存（既存データとマージ）────────────────────────────────────
function mergeAndSave(incoming) {
  chrome.storage.local.get("claudeMeter", (stored) => {
    const prev = stored.claudeMeter ?? {};
    const next = deepMerge(prev, incoming);
    next.updatedAt = new Date().toISOString();
    chrome.storage.local.set({ claudeMeter: next });
  });
}

function deepMerge(target, source) {
  const out = { ...target };
  for (const [k, v] of Object.entries(source)) {
    if (v && typeof v === "object" && !Array.isArray(v) && typeof target[k] === "object") {
      out[k] = deepMerge(target[k], v);
    } else if (v != null) {
      out[k] = v;
    }
  }
  return out;
}
