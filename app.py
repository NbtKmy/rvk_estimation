#!/usr/bin/env python3
"""
app.py — RVK-Klassifikationsagent (Gradio ChatUI + Ollama + Qdrant)

Usage:
    uv run app.py
"""

from __future__ import annotations

import json

import gradio as gr
import httpx
from qdrant_client import QdrantClient

# ─── Configuration ────────────────────────────────────────────────────────────

OLLAMA_BASE = "http://localhost:11434"
EMBED_MODEL = "bge-m3"
LLM_MODEL = "gpt-oss"
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "rvk"
SCORE_THRESHOLD = 0.45  # cosine similarity (0–1)
MAX_TURNS = 8
MIN_RESULTS = 3  # Mindestanzahl garantierter Ergebnisse auch unterhalb des Schwellenwerts

# ─── Qdrant client ────────────────────────────────────────────────────────────

_qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# ─── Embedding ────────────────────────────────────────────────────────────────


def embed(text: str) -> list[float]:
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{OLLAMA_BASE}/api/embed",
            json={"model": EMBED_MODEL, "input": [text]},
        )
        resp.raise_for_status()
        return resp.json()["embeddings"][0]


# ─── Qdrant Search ────────────────────────────────────────────────────────────


def _format_hits(hits, below_threshold: bool = False) -> list[dict]:
    results = []
    for hit in hits:
        p = hit.payload
        notation = p.get("notation", "")
        if p.get("notation_end"):
            notation += f" – {p['notation_end']}"
        entry = {
            "score": round(hit.score, 4),
            "notation": notation,
            "label": p.get("label", ""),
            "breadcrumb": p.get("breadcrumb", ""),
            "gnd_terms": p.get("gnd_terms", [])[:5],
            "usage_note": p.get("usage_note"),
        }
        if below_threshold:
            entry["below_threshold"] = True
        results.append(entry)
    return results


def search_rvk(
    query: str,
    limit: int = 15,
    score_threshold: float = SCORE_THRESHOLD,
) -> tuple[list[dict], int]:
    """
    Bettet die Anfrage ein und durchsucht Qdrant.
    Falls weniger als MIN_RESULTS Treffer, wird ohne Schwellenwert gesucht (Fallback).
    Rückgabe: (Ergebnisliste, Anzahl per Fallback hinzugefügter Einträge)
    """
    vec = embed(query)
    hits = _qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=vec,
        limit=min(limit, 30),
        score_threshold=score_threshold,
        with_payload=True,
    ).points

    results = _format_hits(hits)
    fallback_added = 0

    # Fallback: Mindestens MIN_RESULTS Ergebnisse sicherstellen
    if len(results) < MIN_RESULTS:
        fallback_hits = _qdrant.query_points(
            collection_name=COLLECTION_NAME,
            query=vec,
            limit=MIN_RESULTS,
            with_payload=True,
        ).points
        seen = {r["notation"] for r in results}
        for hit in fallback_hits:
            if len(results) >= MIN_RESULTS:
                break
            p = hit.payload
            notation = p.get("notation", "")
            if p.get("notation_end"):
                notation += f" – {p['notation_end']}"
            if notation not in seen:
                entry = {
                    "score": round(hit.score, 4),
                    "notation": notation,
                    "label": p.get("label", ""),
                    "breadcrumb": p.get("breadcrumb", ""),
                    "gnd_terms": p.get("gnd_terms", [])[:5],
                    "usage_note": p.get("usage_note"),
                    "below_threshold": True,
                }
                results.append(entry)
                seen.add(notation)
                fallback_added += 1

    return results, fallback_added


# ─── Tool Definition ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_rvk",
            "description": (
                "Search the RVK (Regensburger Verbundklassifikation) vector database "
                "for matching classification notations. "
                "Call multiple times with different queries (German synonyms, "
                "broader/narrower terms, English translations) to improve recall."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query — preferably in German.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 15, max 30).",
                        "default": 15,
                    },
                    "score_threshold": {
                        "type": "number",
                        "description": (
                            f"Min cosine similarity (0–1). Default {SCORE_THRESHOLD}. "
                            "Lower = broader results."
                        ),
                        "default": SCORE_THRESHOLD,
                    },
                },
                "required": ["query"],
            },
        },
    }
]

SYSTEM_PROMPT = """\
You are an expert librarian specialising in the Regensburger Verbundklassifikation (RVK).
Help the user find the most appropriate RVK notation(s) through dialogue.

Strategy:
1. Search with the original query using search_rvk.
2. If results are sparse or irrelevant, search again with German synonyms, \
broader/narrower terms, or English translations.
3. Rerank candidates — prefer notations whose label and breadcrumb closely match the subject.
4. Output the top 1–3 best-fitting RVK notations with a brief justification.
5. Results with 'below_threshold: true' are low-confidence fallback matches — clearly note this.
6. When the user follows up (e.g. "more specific", "different field", "only CS"), \
search again with refined terms. Ask a clarifying question if the subject is ambiguous.

Respond in the same language as the user's input.
"""

# ─── Agent Loop ───────────────────────────────────────────────────────────────


def _normalize_content(content) -> str:
    """Ollama akzeptiert nur string-Inhalte — konvertiert Arrays im Gradio/OpenAI-Format in Strings."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "".join(parts)
    if content is None:
        return ""
    return str(content)


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def run_agent_chat(
    message: str,
    history: list[dict],
    log_lines: list[str],
):
    """
    Agenten-Schleife im Chat-Format.
    history ist eine Liste im Gradio-Chatbot-Format (type="messages").
    Gibt (new_history, log_text, new_log_lines) per yield zurück.
    """
    # Nachrichtenverlauf für LLM aufbauen
    # Gradio kann content als Array speichern, Ollama erwartet jedoch nur Strings
    llm_messages: list[dict] = [_msg("system", SYSTEM_PROMPT)]
    for m in history:
        llm_messages.append(_msg(m["role"], _normalize_content(m["content"])))
    llm_messages.append(_msg("user", message))

    log_lines = list(log_lines)
    if log_lines:
        log_lines.append("─" * 36)
    log_lines.append(f'▶ "{message}"')

    def _partial(status: str) -> list[dict]:
        return history + [_msg("user", message), _msg("assistant", status)]

    def _emit(status: str | None = None):
        partial = _partial(status) if status else history
        return partial, "\n".join(log_lines), log_lines

    # Initiale Anzeige während der Verarbeitung
    yield _emit("⏳ Wird verarbeitet...")

    search_count = 0

    for _turn in range(MAX_TURNS):
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": LLM_MODEL,
                    "messages": llm_messages,
                    "tools": TOOLS,
                    "stream": False,
                },
            )
            if not resp.is_success:
                print(f"[DEBUG] Ollama 400 error body: {resp.text}")
                print(f"[DEBUG] llm_messages: {json.dumps(llm_messages, ensure_ascii=False, indent=2)}")
            resp.raise_for_status()
            data = resp.json()

        msg = data["message"]
        # content als Array → normalisieren für erneute Übermittlung an Ollama
        if isinstance(msg.get("content"), list):
            msg = {**msg, "content": _normalize_content(msg["content"])}
        llm_messages.append(msg)
        tool_calls = msg.get("tool_calls") or []

        # Kein Tool-Aufruf → Endantwort
        if not tool_calls:
            result = msg.get("content", "(Keine Antwort)")
            final = history + [_msg("user", message), _msg("assistant", result)]
            yield final, "\n".join(log_lines), log_lines
            return

        # Tool-Aufrufe ausführen
        for tc in tool_calls:
            fn = tc.get("function", {})
            if fn.get("name") != "search_rvk":
                continue

            args = fn.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)

            q = args.get("query", message)
            limit = min(int(args.get("limit", 15)), 30)
            threshold = float(args.get("score_threshold", SCORE_THRESHOLD))

            search_count += 1
            log_lines.append(
                f'🔍 [{search_count}] "{q}"'
                f"  limit={limit}  threshold={threshold:.2f}"
            )
            yield _emit(f"🔍 Suche nach \u201e{q}\u201c... ({search_count}. Anfrage)")

            hits, fallback_added = search_rvk(q, limit=limit, score_threshold=threshold)

            fallback_note = (
                f"  ⚠ Fallback: {fallback_added} Einträge unter Schwellenwert hinzugefügt" if fallback_added else ""
            )
            log_lines.append(f"   └ {len(hits)} Treffer{fallback_note}")
            yield _emit(f"🔍 Suche nach \u201e{q}\u201c... ({search_count}. Anfrage)")

            tool_msg: dict = {
                "role": "tool",
                "content": json.dumps(hits, ensure_ascii=False),
            }
            if tc.get("id"):
                tool_msg["tool_call_id"] = tc["id"]
            llm_messages.append(tool_msg)

    # Maximale Rundenzahl erreicht
    result = "Maximale Anzahl an Runden erreicht. Es konnte kein Ergebnis ermittelt werden."
    final = history + [_msg("user", message), _msg("assistant", result)]
    yield final, "\n".join(log_lines), log_lines


# ─── Gradio UI ────────────────────────────────────────────────────────────────


def on_submit(message: str, history: list, log_state: list):
    if not message or not message.strip():
        yield history, "\n".join(log_state or []), log_state or [], ""
        return
    for new_history, log_text, new_log in run_agent_chat(
        message, history or [], log_state or []
    ):
        yield new_history, log_text, new_log, ""


def reset_all():
    return [], [], "", ""


with gr.Blocks(title="RVK-Klassifikationsagent") as demo:
    gr.Markdown(
        "# RVK-Klassifikationsagent\n"
        "Geben Sie Titel oder Thema eines Dokuments ein, um passende RVK-Notationen zu ermitteln. "
        "Im Chat-Format können Sie die Ergebnisse weiter eingrenzen oder korrigieren.\n\n"
        f"> Modell: `{LLM_MODEL}` / Embedding: `{EMBED_MODEL}`"
        f" / Schwellenwert: `{SCORE_THRESHOLD}` / Mindestergebnisse: `{MIN_RESULTS}`"
    )

    log_state = gr.State([])

    with gr.Row():
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(
                label="RVK-Agent",
                height=520,
                placeholder=(
                    "**RVK-Klassifikationsagent**\n\n"
                    "Bitte geben Sie Titel oder Thema ein.\n"
                    "Falls das Ergebnis nicht passt, können Sie die Suche per Nachricht verfeinern.\n\n"
                    "*Beispiel: Maschinelles Lernen / Quantum Computing / Künstliche Intelligenz*"
                ),
            )
            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="z. B.: Maschinelles Lernen / Künstliche Intelligenz / Quantum Computing ...",
                    scale=4,
                    show_label=False,
                    container=False,
                    lines=1,
                )
                submit_btn = gr.Button("Senden", variant="primary", scale=1, min_width=80)
            clear_btn = gr.Button("Gespräch zurücksetzen", variant="secondary")

        with gr.Column(scale=1):
            log_output = gr.Textbox(
                label="Suchprotokoll",
                lines=28,
                max_lines=50,
                interactive=False,
            )

    submit_btn.click(
        fn=on_submit,
        inputs=[msg_input, chatbot, log_state],
        outputs=[chatbot, log_output, log_state, msg_input],
    )
    msg_input.submit(
        fn=on_submit,
        inputs=[msg_input, chatbot, log_state],
        outputs=[chatbot, log_output, log_state, msg_input],
    )
    clear_btn.click(
        fn=reset_all,
        outputs=[chatbot, log_state, log_output, msg_input],
    )

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft())
