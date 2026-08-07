---
name: podcast-knowledge
description: Use when the user asks a question about the content of their podcast transcripts or "問 podcast / 節目內容 / 哪一集 / 逐字稿". Answers grounded in the local ChromaDB RAG (rag/query.py, Ollama bge-m3). Trigger on words like podcast, 逐字稿, 某集講什麼, 財經皓角, 科技浪, RAG.
---

# Podcast 知識檢索（RAG）

使用者常會問「我的 podcast 有沒有講過 X？」或「幫我從逐字稿找 ...」。用本地 RAG 回答，不要憑空猜。

## 流程

1. 確認 Ollama 在跑：`Test-NetConnection localhost -Port 11434`（或直接試查，失敗會提示）。
2. 查詢（在專案根目錄執行，用批次式取得 JSON，避免超大輸出）：
   ```
   python rag/query.py "<使用者的問題>" --json --no-full --topk 8
   ```
   若專案有 `playlist-admin`（npm）也可：`playlist-admin rag query "<問題>" --no-full --topk 8`。
   若要看特定節目的命中：加上 `--show 節目名`。
3. 依 `best_similarity`（1.0 最高）挑 2–3 個命中，用 `show` / `date` / `file` 標出處。
   `hits[].chunk` 已是可引用的原文片段。需要更長上下文時可讀該 `.txt`（chunk 有 offset）。
4. 用繁體中文回答，列出引用來源（節目、日期、檔名）。

## 注意

- 若報「連線 Ollama 失敗」→ 先 `ollama serve`；若報 collection 不存在 → 先跑 `playlist-admin rag build`（或 `python3 rag/build_db.py`，會花較久時間）。
- 路徑與 DB 都從 config.json 自動解析（見 rag/_resolve.py），不要假設路徑。
- 問題要保持原意，可直接用使用者原句。