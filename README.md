# Claude Usage Meter

Claude (Opus / Sonnet / Haiku) の使用量をモデルごとにメーター表示するツール。

## Web版（GitHub Pages）

👉 **[https://3Daddy-AI.github.io/Claude-meter](https://3Daddy-AI.github.io/Claude-meter)**

1. `~/.claude/projects` フォルダをページにドラッグ&ドロップ
2. Opus / Sonnet / Haiku の残量がリアルタイムで表示される

## ローカル版（自動読み込み）

```bash
python3 claude_meter.py
```

`http://localhost:7453` が自動で開き、30秒ごとに自動更新される。

## 上限の変更

`claude_meter.py` または `index.html` の `LIMITS` を変更：

```python
LIMITS = {
    "opus":   900_000,    # 5h window
    "sonnet": 2_000_000,
    "haiku":  5_000_000,
}
```
