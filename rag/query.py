"""RAG 檢索: 問題 -> bge-m3 -> top-k 片段 -> 自動附加命中檔案的完整原文
用法:
  python rag/query.py "問題" --topk 8          # 文字輸出
  python rag/query.py "問題" --json            # JSON 輸出 (含 full_text)
  python rag/query.py "問題" --no-full         # 不回傳全文, 只回傳命中片段
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chromadb
import requests

from build_db import read_text_file
from _resolve import chroma_db_dir

OLLAMA_URL = "http://localhost:11434"


def embed_one(model: str, text: str) -> list[float]:
    resp = requests.post(
        f"{OLLAMA_URL}/api/embed", json={"model": model, "input": [text]}, timeout=120
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def locate_chunk(full_norm: str, chunk: str, window: int = 100) -> int:
    head = chunk[:window]
    idx = full_norm.find(head)
    if idx < 0:
        head = chunk[:window // 2]
        idx = full_norm.find(head)
    return idx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", help="要查的問題")
    ap.add_argument("--db", default=str(chroma_db_dir()))
    ap.add_argument("--embed", default="bge-m3")
    ap.add_argument("--topk", type=int, default=8)
    ap.add_argument("--json", action="store_true", help="輸出 JSON (含 full_text)")
    ap.add_argument("--no-full", action="store_true", help="不回傳全文")
    ap.add_argument("--out", default="", help="JSON 輸出檔路徑 (與 --json 併用)")
    ap.add_argument("--show", default="", help="只搜指定節目")
    args = ap.parse_args()

    if not args.question:
        args.question = input("問題: ").strip()
    if not args.question:
        sys.exit(1)

    client = chromadb.PersistentClient(path=args.db)
    col = client.get_collection("podcasts")
    qvec = embed_one(args.embed, args.question)
    fetch_n = max(args.topk * 5, 50) if args.show else args.topk
    res = col.query(query_embeddings=[qvec], n_results=fetch_n)

    raw_hits = []
    for doc, meta, dist in zip(
        res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        if args.show and args.show not in meta.get("show", ""):
            continue
        raw_hits.append({
            "similarity": round(1 - dist, 3),
            "show": meta.get("show", "?"),
            "date": meta.get("date", ""),
            "file": meta.get("file", "?"),
            "path": meta.get("path", ""),
            "chunk": doc,
        })

    by_file: dict[str, dict] = {}
    for h in raw_hits:
        key = h["path"] or h["file"]
        if key not in by_file:
            e = {k: h[k] for k in ("show", "date", "file", "path")}
            e["hits"] = []
            e["best_similarity"] = 0.0
            by_file[key] = e
        by_file[key]["hits"].append(h)
        by_file[key]["best_similarity"] = max(
            by_file[key]["best_similarity"], h["similarity"]
        )

    results = []
    for key, e in sorted(
        by_file.items(), key=lambda kv: kv[1]["best_similarity"], reverse=True
    ):
        entry = {
            "show": e["show"],
            "date": e["date"],
            "file": e["file"],
            "best_similarity": e["best_similarity"],
            "hits": [
                {"similarity": h["similarity"], "chunk": h["chunk"]}
                for h in e["hits"]
            ],
        }
        if not args.no_full and e["path"]:
            full = read_text_file(Path(e["path"]))
            full_norm = normalize(full)
            entry["full_text"] = full
            entry["full_text_norm_len"] = len(full_norm)
            entry["offsets"] = [
                locate_chunk(full_norm, h["chunk"]) for h in e["hits"]
            ]
        results.append(entry)

    if args.json:
        payload = {"question": args.question, "results": results}
        out = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(out, encoding="utf-8")
            print(f"已寫入 {args.out}")
        else:
            print(out)
        return

    for r in results:
        print(f"\n[相似度 {r['best_similarity']}] {r['show']} | {r['date']} | {r['file']}")
        if "full_text" in r:
            print(f"  (全文 {len(r['full_text'])} 字, 命中偏移 {r['offsets']})")
        for h in r["hits"][:2]:
            print(f"  > {h['chunk'][:120]}...")


if __name__ == "__main__":
    main()