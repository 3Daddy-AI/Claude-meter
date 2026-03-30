#!/usr/bin/env python3
"""
Claude Usage Meter
~/.claude/projects/ 以下のセッションデータを読み込み、
モデルごとの使用状況をブラウザで表示する。
"""

import json
import glob
import os
import sys
import http.server
import threading
import webbrowser
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# ─── 設定 ──────────────────────────────────────────────────────────────────────
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")

# 集計ウィンドウ（時間）
WINDOW_HOURS = 5

# モデルごとのトークン上限（ウィンドウ内）
# Claude Max / Pro の目安。自由に変更してください。
# 入力トークン（キャッシュ含む）ベース
LIMITS = {
    "opus":   900_000,    # Opus: 5h window limit (approx)
    "sonnet": 2_000_000,  # Sonnet
    "haiku":  5_000_000,  # Haiku
}

PORT = 7453
# ───────────────────────────────────────────────────────────────────────────────


def classify_model(model_str: str) -> str | None:
    """モデル文字列を opus / sonnet / haiku に分類。"""
    m = model_str.lower()
    if "opus" in m:
        return "opus"
    if "sonnet" in m:
        return "sonnet"
    if "haiku" in m:
        return "haiku"
    return None


def load_usage():
    """全セッションファイルを読み込み、モデル×時間帯ごとに集計する。"""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=WINDOW_HOURS)
    day_start    = now - timedelta(hours=24)

    totals = {
        "window": defaultdict(lambda: {"input": 0, "output": 0, "cache_create": 0, "cache_read": 0, "calls": 0}),
        "day":    defaultdict(lambda: {"input": 0, "output": 0, "cache_create": 0, "cache_read": 0, "calls": 0}),
        "all":    defaultdict(lambda: {"input": 0, "output": 0, "cache_create": 0, "cache_read": 0, "calls": 0}),
    }
    timeline = []  # (timestamp, model_key, tokens)

    pattern = os.path.join(PROJECTS_DIR, "**", "*.jsonl")
    files = glob.glob(pattern, recursive=True)

    for filepath in files:
        try:
            with open(filepath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if obj.get("type") != "assistant":
                        continue
                    msg = obj.get("message", {})
                    model_str = msg.get("model", "")
                    usage = msg.get("usage", {})

                    model_key = classify_model(model_str)
                    if not model_key:
                        continue

                    inp  = usage.get("input_tokens", 0) or 0
                    out  = usage.get("output_tokens", 0) or 0
                    cc   = usage.get("cache_creation_input_tokens", 0) or 0
                    cr   = usage.get("cache_read_input_tokens", 0) or 0

                    if inp + out + cc + cr == 0:
                        continue

                    ts_str = obj.get("timestamp", "")
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except Exception:
                        ts = now  # fallback: count as now

                    # all-time
                    totals["all"][model_key]["input"]        += inp
                    totals["all"][model_key]["output"]       += out
                    totals["all"][model_key]["cache_create"] += cc
                    totals["all"][model_key]["cache_read"]   += cr
                    totals["all"][model_key]["calls"]        += 1

                    # last 24h
                    if ts >= day_start:
                        totals["day"][model_key]["input"]        += inp
                        totals["day"][model_key]["output"]       += out
                        totals["day"][model_key]["cache_create"] += cc
                        totals["day"][model_key]["cache_read"]   += cr
                        totals["day"][model_key]["calls"]        += 1

                    # window
                    if ts >= window_start:
                        totals["window"][model_key]["input"]        += inp
                        totals["window"][model_key]["output"]       += out
                        totals["window"][model_key]["cache_create"] += cc
                        totals["window"][model_key]["cache_read"]   += cr
                        totals["window"][model_key]["calls"]        += 1

                    timeline.append({
                        "ts": ts.isoformat(),
                        "model": model_key,
                        "tokens": inp + out + cc + cr,
                    })
        except Exception:
            continue

    # JSON シリアライズ用に通常の dict に変換
    for period in totals:
        totals[period] = dict(totals[period])
        for k in totals[period]:
            totals[period][k] = dict(totals[period][k])

    return {
        "totals": totals,
        "limits": LIMITS,
        "window_hours": WINDOW_HOURS,
        "now": now.isoformat(),
        "timeline": sorted(timeline, key=lambda x: x["ts"]),
    }


# ─── HTML テンプレート ─────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Usage Meter</title>
<style>
  :root {
    --bg: #0d0d12;
    --surface: #16161e;
    --border: #2a2a3a;
    --text: #e8e8f0;
    --muted: #666688;
    --opus-from: #a855f7;
    --opus-to:   #f59e0b;
    --sonnet-from: #3b82f6;
    --sonnet-to:   #06b6d4;
    --haiku-from: #10b981;
    --haiku-to:   #84cc16;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 40px 20px;
  }
  h1 {
    font-size: 1.5rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    color: var(--text);
    margin-bottom: 6px;
  }
  .subtitle {
    font-size: 0.8rem;
    color: var(--muted);
    margin-bottom: 40px;
  }
  .period-tabs {
    display: flex;
    gap: 8px;
    margin-bottom: 36px;
  }
  .tab {
    padding: 6px 18px;
    border-radius: 99px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--muted);
    font-size: 0.82rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  .tab.active {
    background: var(--border);
    color: var(--text);
    border-color: transparent;
  }
  .cards {
    display: flex;
    gap: 28px;
    flex-wrap: wrap;
    justify-content: center;
    width: 100%;
    max-width: 960px;
  }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 32px 28px 28px;
    flex: 1 1 260px;
    max-width: 300px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 20px;
    position: relative;
    overflow: hidden;
  }
  .card::before {
    content: '';
    position: absolute;
    top: -60px; left: 50%;
    transform: translateX(-50%);
    width: 200px; height: 200px;
    border-radius: 50%;
    opacity: 0.07;
    pointer-events: none;
  }
  .card.opus::before   { background: radial-gradient(circle, #a855f7, #f59e0b); }
  .card.sonnet::before { background: radial-gradient(circle, #3b82f6, #06b6d4); }
  .card.haiku::before  { background: radial-gradient(circle, #10b981, #84cc16); }

  .model-label {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
  }

  /* Circular gauge */
  .gauge-wrap {
    position: relative;
    width: 180px;
    height: 180px;
  }
  .gauge-wrap svg { transform: rotate(-90deg); }
  .gauge-bg { fill: none; stroke: var(--border); stroke-width: 10; }
  .gauge-fill { fill: none; stroke-width: 10; stroke-linecap: round;
                transition: stroke-dashoffset 0.8s cubic-bezier(0.4,0,0.2,1); }
  .gauge-center {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
  }
  .gauge-pct {
    font-size: 2rem;
    font-weight: 700;
    line-height: 1;
  }
  .gauge-remaining {
    font-size: 0.7rem;
    color: var(--muted);
  }

  .stats {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .stat-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.78rem;
  }
  .stat-label { color: var(--muted); }
  .stat-val   { font-variant-numeric: tabular-nums; font-weight: 500; }

  .divider {
    width: 100%;
    height: 1px;
    background: var(--border);
  }

  .limit-note {
    font-size: 0.68rem;
    color: var(--muted);
    text-align: center;
    opacity: 0.7;
  }

  .footer {
    margin-top: 48px;
    font-size: 0.72rem;
    color: var(--muted);
    text-align: center;
    line-height: 1.8;
  }
  .refresh-btn {
    margin-top: 16px;
    padding: 6px 20px;
    border-radius: 99px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--muted);
    font-size: 0.78rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  .refresh-btn:hover { color: var(--text); border-color: #444; }

  /* Warning colors */
  .warn { color: #f59e0b !important; }
  .danger { color: #ef4444 !important; }
  .ok { color: #10b981 !important; }
</style>
</head>
<body>

<h1>Claude Usage Meter</h1>
<p class="subtitle" id="updated-at">読み込み中…</p>

<div class="period-tabs">
  <button class="tab active" onclick="setPeriod('window')">直近 5h</button>
  <button class="tab" onclick="setPeriod('day')">直近 24h</button>
  <button class="tab" onclick="setPeriod('all')">全期間</button>
</div>

<div class="cards" id="cards"></div>

<div class="footer">
  <div>トークン上限は LIMITS 変数で変更できます（<code>claude_meter.py</code>）</div>
  <button class="refresh-btn" onclick="fetchData()">↻ 更新</button>
</div>

<script>
let currentPeriod = 'window';
let currentData = null;

const MODEL_INFO = {
  opus:   { label: 'Opus',   gradFrom: '#a855f7', gradTo: '#f59e0b', gradId: 'gradOpus' },
  sonnet: { label: 'Sonnet', gradFrom: '#3b82f6', gradTo: '#06b6d4', gradId: 'gradSonnet' },
  haiku:  { label: 'Haiku',  gradFrom: '#10b981', gradTo: '#84cc16', gradId: 'gradHaiku' },
};

function fmtN(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

function totalTokens(usage) {
  return (usage.input || 0) + (usage.output || 0)
       + (usage.cache_create || 0) + (usage.cache_read || 0);
}

function buildGaugeSVG(pct, gradId, gradFrom, gradTo) {
  const R = 80, CX = 90, CY = 90;
  const circ = 2 * Math.PI * R;
  const fill = circ * Math.min(pct, 1);
  const gap  = circ - fill;
  return `<svg width="180" height="180" viewBox="0 0 180 180">
    <defs>
      <linearGradient id="${gradId}" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%"   stop-color="${gradFrom}"/>
        <stop offset="100%" stop-color="${gradTo}"/>
      </linearGradient>
    </defs>
    <circle class="gauge-bg"   cx="${CX}" cy="${CY}" r="${R}"/>
    <circle class="gauge-fill" cx="${CX}" cy="${CY}" r="${R}"
      stroke="url(#${gradId})"
      stroke-dasharray="${fill} ${gap}"
      stroke-dashoffset="0"/>
  </svg>`;
}

function colorClass(pct) {
  if (pct >= 0.9) return 'danger';
  if (pct >= 0.7) return 'warn';
  return 'ok';
}

function renderCards(data, period) {
  const container = document.getElementById('cards');
  container.innerHTML = '';

  const models = ['opus', 'sonnet', 'haiku'];
  const periodData = data.totals[period] || {};
  const limits = data.limits;
  const isWindow = period === 'window';

  for (const key of models) {
    const info  = MODEL_INFO[key];
    const usage = periodData[key] || { input: 0, output: 0, cache_create: 0, cache_read: 0, calls: 0 };
    const used  = totalTokens(usage);
    const limit = limits[key];
    const pct   = isWindow ? Math.min(used / limit, 1) : null;
    const remaining = isWindow ? Math.max(limit - used, 0) : null;

    const card = document.createElement('div');
    card.className = `card ${key}`;

    // gauge
    const gaugeDiv = document.createElement('div');
    gaugeDiv.className = 'gauge-wrap';
    if (isWindow) {
      gaugeDiv.innerHTML = buildGaugeSVG(pct, info.gradId, info.gradFrom, info.gradTo);
      const center = document.createElement('div');
      center.className = 'gauge-center';
      const pctVal = Math.round(pct * 100);
      center.innerHTML = `
        <span class="gauge-pct ${colorClass(pct)}">${pctVal}%</span>
        <span class="gauge-remaining">残り ${fmtN(remaining)}</span>`;
      gaugeDiv.appendChild(center);
    } else {
      // non-window: show total with empty gauge style
      gaugeDiv.innerHTML = buildGaugeSVG(0, info.gradId, info.gradFrom, info.gradTo);
      const center = document.createElement('div');
      center.className = 'gauge-center';
      center.innerHTML = `
        <span class="gauge-pct" style="font-size:1.5rem">${fmtN(used)}</span>
        <span class="gauge-remaining">tokens</span>`;
      gaugeDiv.appendChild(center);
    }

    // stats
    const stats = `
      <div class="stats">
        <div class="stat-row">
          <span class="stat-label">入力</span>
          <span class="stat-val">${fmtN(usage.input || 0)}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">出力</span>
          <span class="stat-val">${fmtN(usage.output || 0)}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">キャッシュ作成</span>
          <span class="stat-val">${fmtN(usage.cache_create || 0)}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">キャッシュ読込</span>
          <span class="stat-val">${fmtN(usage.cache_read || 0)}</span>
        </div>
        <div class="divider"></div>
        <div class="stat-row">
          <span class="stat-label">API呼び出し</span>
          <span class="stat-val">${(usage.calls || 0).toLocaleString()} 回</span>
        </div>
        ${isWindow ? `<div class="limit-note">上限: ${fmtN(limit)} tokens / ${data.window_hours}h</div>` : ''}
      </div>`;

    card.innerHTML = `
      <div class="model-label">${info.label}</div>`;
    card.appendChild(gaugeDiv);
    card.insertAdjacentHTML('beforeend', stats);
    container.appendChild(card);
  }
}

function setPeriod(p) {
  currentPeriod = p;
  document.querySelectorAll('.tab').forEach((t, i) => {
    t.classList.toggle('active', ['window','day','all'][i] === p);
  });
  if (currentData) renderCards(currentData, p);
}

async function fetchData() {
  try {
    const res = await fetch('/api/usage');
    const data = await res.json();
    currentData = data;
    const ts = new Date(data.now);
    document.getElementById('updated-at').textContent =
      `最終更新: ${ts.toLocaleString('ja-JP')}`;
    renderCards(data, currentPeriod);
  } catch (e) {
    console.error(e);
  }
}

fetchData();
setInterval(fetchData, 30_000);
</script>
</body>
</html>"""


# ─── HTTP サーバー ─────────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # ログ抑制

    def do_GET(self):
        if self.path == "/api/usage":
            data = json.dumps(load_usage(), ensure_ascii=False, default=str)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data.encode())
        elif self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode())
        else:
            self.send_response(404)
            self.end_headers()


def main():
    server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Claude Usage Meter  →  {url}")
    print("終了するには Ctrl+C を押してください。\n")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました。")
        server.shutdown()


if __name__ == "__main__":
    main()
