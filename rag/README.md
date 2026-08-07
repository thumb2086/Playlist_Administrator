# Podcast RAG

對 podcast 逐字稿做本地語意檢索（embeddings + ChromaDB）。

## 前置需求

- 安裝 Ollama：`https://ollama.com/download`
  ```bash
  ollama pull bge-m3          # embedding 模型
  ollama pull qwen2.5:7b      # （選用）本機生成
  ```
- Python 套件：
  ```bash
  pip install chromadb requests
  ```
- 逐字稿：`podcast_downloads/<節目>/*.txt`（podcast pipeline 會自動產生 .txt）

## 指令

CLI（需已 build exe 或直接 python 執行）：

```bash
playlist-admin rag build            # 增量索引（沒被 index 過的 .txt）
playlist-admin rag build --reset    # 全部重建
playlist-admin rag query "2026年台股會一直漲嗎?" --topk 8
playlist-admin rag query "問題" --json        # JSON 含全文
playlist-admin rag query "問題" --show 游庭皓  # 只搜指定節目
```

直接用 Python（路徑從 config.json 自動解析）：

```bash
python rag/build_db.py
python rag/query.py "問題"
python rag/srt_to_text.py            # 把缺 .txt 的 .srt 補轉成 .txt
```

## Pipeline 整合

podcast pipeline 產生/更新逐字稿後，跑 `playlist-admin rag build`
即可把新集數加進向量庫（程式會自動跳過已索引的檔名）。

## 檔案

- `build_db.py` — 逐字稿切 chunk → Ollama embeddings → ChromaDB（cosine）
- `query.py` — 問題 embedding → top-k 片段 → 輸出命中的節目/日期/全文偏移
- `srt_to_text.py` — srt → 純文字
- `_resolve.py` — 從 app config 解析 podcast_downloads 與 chroma_db 路徑