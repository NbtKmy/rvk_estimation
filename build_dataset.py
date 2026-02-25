#!/usr/bin/env python3
"""
build_dataset.py — RVK MARCXML → Qdrant embeddings pipeline

Usage:
    uv run build_dataset.py

Requirements:
    - Ollama running at localhost:11434 with bge-m3 pulled
    - Qdrant running at localhost:6333 (via docker-compose up -d)
"""

from __future__ import annotations

import sys
from itertools import islice
from pathlib import Path
from typing import Iterator

import httpx
from lxml import etree
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from tqdm import tqdm

# ─── Configuration ────────────────────────────────────────────────────────────

XML_FILE = Path("rvko_marcxml_2025_4.xml")
OLLAMA_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "bge-m3"
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "rvk"
VECTOR_DIM = 1024
EMBED_BATCH_SIZE = 32
UPSERT_BATCH_SIZE = 256
MAX_HIERARCHY_DEPTH = 5
TOTAL_RECORDS_ESTIMATE = 783_000  # approximate, for tqdm display

MARC_NS = "http://www.loc.gov/MARC21/slim"
NS = {"m": MARC_NS}

# Records without a numeric ID (e.g. "1:", "2:") get IDs above this offset
# to avoid collision with real numeric IDs
FALLBACK_ID_OFFSET = 100_000_000


# ─── XML Parsing ──────────────────────────────────────────────────────────────


def _sf(datafield: etree._Element, code: str) -> str | None:
    """Return first subfield text matching code, or None."""
    el = datafield.find(f"m:subfield[@code='{code}']", NS)
    return el.text if el is not None and el.text else None


def _parse_hierarchy(df153: etree._Element) -> list[dict]:
    """
    Extract ordered parent hierarchy from tag=153 subfields.

    Subfields $e/$h (and optionally $f) are read in document order.
    Each $e starts a new hierarchy entry:
        $e  → notation (start)
        $f  → notation_end (optional, only for range parents)
        $h  → label
    Returns list ordered from top-most ancestor to direct parent.
    """
    hierarchy: list[dict] = []
    subs = list(df153)

    i = 0
    while i < len(subs):
        code = subs[i].get("code")
        if code == "e":
            h_notation = subs[i].text or ""
            h_notation_end: str | None = None
            h_label = ""
            # Optional $f (range end of parent)
            if i + 1 < len(subs) and subs[i + 1].get("code") == "f":
                h_notation_end = subs[i + 1].text or None
                i += 1
            # $h (parent label)
            if i + 1 < len(subs) and subs[i + 1].get("code") == "h":
                h_label = subs[i + 1].text or ""
                i += 1
            hierarchy.append(
                {
                    "notation": h_notation,
                    "notation_end": h_notation_end,
                    "label": h_label,
                }
            )
        i += 1

    return hierarchy


def parse_xml(xml_path: Path) -> Iterator[tuple[str, dict, int]]:
    """
    Stream-parse MARCXML with lxml iterparse.
    Yields (embedding_text, payload, point_id) for each valid record.
    """
    fallback_counter = 0
    context = etree.iterparse(
        str(xml_path),
        events=("end",),
        tag=f"{{{MARC_NS}}}record",
        recover=True,
    )

    for _, record in context:
        try:
            # ── Point ID from controlfield 001 ────────────────────────
            cf001 = record.find("m:controlfield[@tag='001']", NS)
            raw_id = cf001.text.strip() if cf001 is not None and cf001.text else ""

            if ":" in raw_id:
                num_part = raw_id.split(":", 1)[1].strip()
                if num_part.isdigit():
                    point_id = int(num_part)
                else:
                    fallback_counter += 1
                    point_id = FALLBACK_ID_OFFSET + fallback_counter
            else:
                fallback_counter += 1
                point_id = FALLBACK_ID_OFFSET + fallback_counter

            # ── tag=153: notation, label, hierarchy ───────────────────
            df153 = record.find("m:datafield[@tag='153']", NS)
            if df153 is None:
                continue

            notation = _sf(df153, "a") or ""
            notation_end = _sf(df153, "c")
            label = _sf(df153, "j") or ""

            if not notation or not label:
                continue

            hierarchy = _parse_hierarchy(df153)
            breadcrumb = " > ".join(h["label"] for h in hierarchy if h["label"])

            # ── GND index terms (700, 710, 748, 750, 751) ─────────────
            gnd_terms: list[str] = []
            gnd_ids: list[str] = []
            gnd_types: list[str] = []
            for tag in ("700", "710", "748", "750", "751"):
                for df in record.findall(f"m:datafield[@tag='{tag}']", NS):
                    term = _sf(df, "a")
                    if term:
                        gnd_terms.append(term)
                        gnd_ids.append(_sf(df, "0") or "")
                        gnd_types.append(tag)

            # ── Notes: 253 (see also) and 684 (usage note) ────────────
            see_also_parts: list[str] = []
            for df in record.findall("m:datafield[@tag='253']", NS):
                txt = _sf(df, "i")
                if txt:
                    see_also_parts.append(txt)

            usage_note_parts: list[str] = []
            for df in record.findall("m:datafield[@tag='684']", NS):
                txt = _sf(df, "i")
                if txt:
                    usage_note_parts.append(txt)

            see_also = " ".join(see_also_parts) or None
            usage_note = " ".join(usage_note_parts) or None

            # ── Build embedding_text ───────────────────────────────────
            # Limit hierarchy to last MAX_HIERARCHY_DEPTH levels
            hier_labels = [h["label"] for h in hierarchy if h["label"]]
            if len(hier_labels) > MAX_HIERARCHY_DEPTH:
                hier_labels = hier_labels[-MAX_HIERARCHY_DEPTH:]

            lines: list[str] = []
            notation_str = f"Notation: {notation}"
            if notation_end:
                notation_str += f" \u2013 {notation_end}"
            lines.append(notation_str)
            lines.append(f"Bezeichnung: {label}")
            if hier_labels:
                lines.append(f"Hierarchie: {' > '.join(hier_labels)}")
            if gnd_terms:
                lines.append(f"Schlagw\u00f6rter: {'; '.join(gnd_terms)}")
            hints: list[str] = []
            if see_also:
                hints.append(see_also)
            if usage_note:
                hints.append(usage_note)
            if hints:
                lines.append(f"Hinweis: {' '.join(hints)}")

            embedding_text = "\n".join(lines)

            # ── Build Qdrant payload ───────────────────────────────────
            payload: dict = {
                "notation": notation,
                "notation_end": notation_end,
                "label": label,
                "is_range": notation_end is not None,
                "hierarchy": hierarchy,
                "breadcrumb": breadcrumb,
                "gnd_terms": gnd_terms,
                "gnd_ids": gnd_ids,
                "gnd_types": gnd_types,
                "see_also": see_also,
                "usage_note": usage_note,
                "record_id": raw_id,
            }

            yield embedding_text, payload, point_id

        except Exception as exc:
            logger.warning(f"Skipping record '{raw_id}': {exc}")

        finally:
            # Free memory: clear the processed element and detach from root
            record.clear()
            while record.getprevious() is not None:
                del record.getparent()[0]


# ─── Ollama Embedding ─────────────────────────────────────────────────────────


def embed_batch(texts: list[str], client: httpx.Client) -> list[list[float]]:
    """POST to Ollama /api/embed and return list of dense vectors."""
    resp = client.post(
        OLLAMA_URL,
        json={"model": EMBED_MODEL, "input": texts},
        timeout=300.0,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"]


# ─── Qdrant Setup ─────────────────────────────────────────────────────────────


def ensure_collection(qdrant: QdrantClient) -> None:
    """Create the Qdrant collection if it does not already exist."""
    existing = {c.name for c in qdrant.get_collections().collections}
    if COLLECTION_NAME not in existing:
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        logger.info(
            f"Created collection '{COLLECTION_NAME}' "
            f"(dim={VECTOR_DIM}, distance=Cosine, index=HNSW)"
        )
    else:
        info = qdrant.get_collection(COLLECTION_NAME)
        count = info.points_count or 0
        logger.info(
            f"Collection '{COLLECTION_NAME}' exists ({count:,} points) — will upsert"
        )


def get_existing_ids(qdrant: QdrantClient) -> set[int]:
    """Scroll through all stored point IDs in Qdrant (for resume support)."""
    existing: set[int] = set()
    offset = None
    while True:
        result, next_offset = qdrant.scroll(
            collection_name=COLLECTION_NAME,
            offset=offset,
            limit=10_000,
            with_payload=False,
            with_vectors=False,
        )
        for point in result:
            existing.add(point.id)
        if next_offset is None:
            break
        offset = next_offset
    return existing


# ─── Helpers ──────────────────────────────────────────────────────────────────


def batched(iterable, n: int):
    """Yield successive non-overlapping chunks of size n."""
    it = iter(iterable)
    while chunk := list(islice(it, n)):
        yield chunk


# ─── Main Pipeline ────────────────────────────────────────────────────────────


def main() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        colorize=True,
    )

    if not XML_FILE.exists():
        logger.error(f"XML file not found: {XML_FILE.resolve()}")
        raise SystemExit(1)

    # ── Connect to Qdrant ─────────────────────────────────────────────
    logger.info(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
    try:
        qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        ensure_collection(qdrant)
    except Exception as exc:
        logger.error(f"Cannot connect to Qdrant: {exc}")
        raise SystemExit(1)

    # ── Verify Ollama ─────────────────────────────────────────────────
    logger.info(f"Verifying Ollama at {OLLAMA_URL} (model: {EMBED_MODEL})")
    with httpx.Client() as probe:
        try:
            probe.get("http://localhost:11434/", timeout=5.0).raise_for_status()
        except Exception as exc:
            logger.error(f"Cannot reach Ollama: {exc}")
            raise SystemExit(1)

    # ── Load existing IDs for resume support ──────────────────────────
    existing_ids: set[int] = set()
    already_done = qdrant.get_collection(COLLECTION_NAME).points_count or 0
    if already_done > 0:
        logger.info(f"Resuming: loading {already_done:,} existing IDs from Qdrant …")
        existing_ids = get_existing_ids(qdrant)
        logger.info(f"Will skip {len(existing_ids):,} already-stored records")

    # ── Main loop ─────────────────────────────────────────────────────
    total_upserted = 0
    upsert_buffer: list[PointStruct] = []

    with httpx.Client() as http_client:
        record_stream = (
            item for item in parse_xml(XML_FILE)
            if item[2] not in existing_ids
        )

        with tqdm(
            total=TOTAL_RECORDS_ESTIMATE,
            initial=len(existing_ids),
            desc="Embedding & storing",
            unit="rec",
            dynamic_ncols=True,
        ) as pbar:
            for embed_chunk in batched(record_stream, EMBED_BATCH_SIZE):
                texts, payloads, point_ids = zip(*embed_chunk)

                try:
                    vectors = embed_batch(list(texts), http_client)
                except httpx.HTTPStatusError as exc:
                    logger.error(f"Ollama HTTP error: {exc.response.status_code} — {exc.response.text}")
                    raise SystemExit(1)
                except httpx.RequestError as exc:
                    logger.error(f"Ollama request failed: {exc}")
                    raise SystemExit(1)

                for vec, payload, pid in zip(vectors, payloads, point_ids):
                    upsert_buffer.append(
                        PointStruct(id=pid, vector=vec, payload=payload)
                    )

                pbar.update(len(embed_chunk))

                # Flush upsert buffer when full
                if len(upsert_buffer) >= UPSERT_BATCH_SIZE:
                    qdrant.upsert(collection_name=COLLECTION_NAME, points=upsert_buffer)
                    total_upserted += len(upsert_buffer)
                    upsert_buffer.clear()
                    pbar.set_postfix(upserted=f"{total_upserted:,}")

            # Flush remainder
            if upsert_buffer:
                qdrant.upsert(collection_name=COLLECTION_NAME, points=upsert_buffer)
                total_upserted += len(upsert_buffer)
                upsert_buffer.clear()

    logger.success(
        f"Done — {total_upserted:,} records upserted to '{COLLECTION_NAME}'"
    )


if __name__ == "__main__":
    main()
