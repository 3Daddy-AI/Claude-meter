const MODELS = [
  { key: "opus",   label: "Opus"   },
  { key: "sonnet", label: "Sonnet" },
  { key: "haiku",  label: "Haiku"  },
];

function fmtReset(iso) {
  if (!iso) return null;
  const diff = Math.max(0, Math.round((new Date(iso) - Date.now()) / 1000));
  if (diff < 60)   return `${diff}秒後にリセット`;
  if (diff < 3600) return `${Math.floor(diff / 60)}分後にリセット`;
  return `${Math.floor(diff / 3600)}時間後にリセット`;
}

function colorCls(pct) {
  if (pct >= 0.9) return "danger";
  if (pct >= 0.7) return "warn";
  return "ok";
}

function renderMeter(key, label, info) {
  const rem   = info?.remaining ?? null;
  const limit = info?.limit     ?? null;
  const used  = (limit != null && rem != null) ? Math.max(limit - rem, 0) : null;
  const pct   = (limit && rem != null) ? Math.min(used / limit, 1) : 0;
  const resetTxt = fmtReset(info?.reset);

  const cls   = colorCls(pct);
  const pctPx = Math.round(pct * 100);

  const countHtml = (rem != null && limit != null)
    ? `<span class="${cls}">${rem}</span> / ${limit}`
    : rem != null
      ? `<span class="${cls}">${rem} 残り</span>`
      : `<span style="color:var(--muted)">—</span>`;

  return `
    <div class="meter-card">
      <div class="meter-top">
        <span class="model-name">${label}</span>
        <span class="model-count">${countHtml}</span>
      </div>
      <div class="bar-bg">
        <div class="bar-fill ${key}" style="width:${pctPx}%"></div>
      </div>
      ${resetTxt ? `<div class="reset-time">↺ ${resetTxt}</div>` : ""}
    </div>`;
}

function load() {
  chrome.storage.local.get("claudeMeter", (stored) => {
    const data = stored.claudeMeter;

    if (!data || !data.limits) {
      document.getElementById("no-data").style.display   = "block";
      document.getElementById("meters").style.display    = "none";
      document.getElementById("updated-at").textContent  = "";
      return;
    }

    document.getElementById("no-data").style.display  = "none";
    document.getElementById("meters").style.display   = "flex";

    if (data.plan) {
      document.getElementById("plan-label").textContent = data.plan;
    }

    const container = document.getElementById("meters");
    container.innerHTML = MODELS
      .map(({ key, label }) => renderMeter(key, label, data.limits?.[key]))
      .join("");

    if (data.updatedAt) {
      const d = new Date(data.updatedAt);
      document.getElementById("updated-at").textContent =
        `更新: ${d.toLocaleTimeString("ja-JP")}`;
    }
  });
}

document.addEventListener("DOMContentLoaded", load);
