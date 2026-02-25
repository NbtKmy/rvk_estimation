#!/usr/bin/env python3
"""
search.py — クエリテキストでRVKをベクトル検索するシンプルなCLIツール

Usage:
    uv run search.py "Künstliche Intelligenz"
    uv run search.py "机械学習" --limit 5
"""

from __future__ import annotations

import sys
import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import NamedVector, Query

OLLAMA_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "bge-m3"
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "rvk"


def embed(text: str) -> list[float]:
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(OLLAMA_URL, json={"model": EMBED_MODEL, "input": [text]})
        resp.raise_for_status()
        return resp.json()["embeddings"][0]


def search(query: str, limit: int = 10) -> None:
    print(f'\nQuery: "{query}"')
    print("Embedding...", end=" ", flush=True)
    vec = embed(query)
    print("done.\n")

    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    results = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=vec,
        limit=limit,
        with_payload=True,
    ).points

    print(f"{'Score':>6}  {'Notation':<12}  {'Bezeichnung'}")
    print("-" * 70)
    for hit in results:
        p = hit.payload
        notation = p.get("notation", "")
        if p.get("notation_end"):
            notation += f" – {p['notation_end']}"
        label = p.get("label", "")
        breadcrumb = p.get("breadcrumb", "")
        score = hit.score

        print(f"{score:>6.4f}  {notation:<12}  {label}")
        if breadcrumb:
            print(f"{'':>6}  {'':>12}  └ {breadcrumb}")
        gnd = p.get("gnd_terms", [])
        if gnd:
            print(f"{'':>6}  {'':>12}  Schlagw.: {'; '.join(gnd[:5])}")
        print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RVK vector search")
    parser.add_argument("query", help="検索クエリ（ドイツ語・英語・日本語など）")
    parser.add_argument("--limit", type=int, default=10, help="返す件数 (default: 10)")
    args = parser.parse_args()

    search(args.query, limit=args.limit)
