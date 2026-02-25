# RVK-Klassifikationsagent

Ein interaktiver Chat-Agent zur Ermittlung passender
[RVK-Notationen](https://rvk.uni-regensburg.de/) (Regensburger Verbundklassifikation)
auf Basis von Vektorsuche (Qdrant) und einem lokalen LLM (Ollama).

---

## Voraussetzungen

### Qdrant

Qdrant läuft als Docker-Container. Voraussetzung ist eine installierte
[Docker](https://docs.docker.com/get-docker/)-Umgebung (Docker Desktop oder Docker Engine
mit dem Compose-Plugin).

Container starten:

```bash
docker compose up -d
```

Dadurch läuft Qdrant auf `localhost:6333` (REST-API) und `localhost:6334` (gRPC).

### Ollama

[Ollama](https://ollama.com/) muss lokal installiert und gestartet sein.
Zusätzlich werden die folgenden zwei Modelle benötigt:

| Modell | Verwendung |
|--------|------------|
| `gpt-oss` | LLM (Konversation & Reasoning) |
| `bge-m3` | Embedding (Vektorisierung der Suchanfragen) |

Modelle herunterladen:

```bash
ollama pull gpt-oss
ollama pull bge-m3
```

---

## Installation

Dieses Projekt verwendet [uv](https://docs.astral.sh/uv/) als Paketmanager.

```bash
# Abhängigkeiten installieren und virtuelle Umgebung erstellen
uv sync
```

---

## Anwendung starten

```bash
uv run app.py
```

Die Gradio-Oberfläche ist anschließend im Browser erreichbar (standardmäßig unter
`http://localhost:7860`).

---

## Vektordatenbank aufbauen

Der Agent setzt eine befüllte Qdrant-Collection voraus. Das Skript `build_dataset.py`
liest das offizielle RVK-MARCXML-Dump und erzeugt daraus die Embeddings.

### Quelldatei

Das MARCXML-Dump der RVK kann von der offiziellen RVK-Webseite heruntergeladen werden:

> <https://rvk.uni-regensburg.de/regensburger-verbundklassifikation-online/rvk-download>

Die heruntergeladene Datei muss als `rvko_marcxml_2025_4.xml` im Projektverzeichnis
abgelegt werden (Dateiname ggf. anpassen).

### Pipeline

Das Skript verarbeitet jeden MARCXML-Datensatz nach folgendem Schema:

1. **Parsen** — Notation, Bezeichnung, Hierarchiepfad, GND-Schlagwörter und Hinweistexte
   werden aus den MARC-Feldern extrahiert (insbesondere `tag=153`, `700`–`751`, `253`, `684`).
2. **Embedding** — Aus den extrahierten Feldern wird ein strukturierter Text zusammengesetzt
   und via Ollama (`bge-m3`, 1024-dim) in einen Vektor umgewandelt.
3. **Speichern** — Die Vektoren werden zusammen mit dem Payload (Notation, Breadcrumb,
   GND-Terme usw.) per Batch-Upsert in Qdrant abgelegt.

Das Skript unterstützt **Resume**: bereits gespeicherte Einträge werden übersprungen,
sodass ein unterbrochener Lauf fortgesetzt werden kann.

### Ausführen

```bash
uv run build_dataset.py
```

> Der vollständige Lauf über alle ~783.000 RVK-Einträge kann je nach Hardware
> mehrere Stunden dauern.
