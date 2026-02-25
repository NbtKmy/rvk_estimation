# RVK-Klassifikationsagent

Ein interaktiver Chat-Agent zur Ermittlung passender
[RVK-Notationen](https://rvk.uni-regensburg.de/) (Regensburger Verbundklassifikation)
auf Basis von Vektorsuche (Qdrant) und einem lokalen LLM (Ollama).

---

## Schnellstart

Zuerst bitte die Softwares wie uv, Docker und Ollama installieren!  


```bash
# 1. Repository klonen
git clone https://github.com/nkamiy/rvk_estimation.git
cd rvk_estimation

# 2. Abhängigkeiten installieren (uv erforderlich)
uv sync

# 3. Qdrant starten
docker compose up -d

# 4. Vektordatenbank aus Snapshot wiederherstellen
uv run restore_snapshot.py

# 5. Ollama-Modelle herunterladen
ollama pull gpt-oss
ollama pull bge-m3

# 6. Anwendung starten
uv run app.py
```

Die Gradio-Oberfläche ist anschließend im Browser erreichbar (standardmäßig unter
`http://localhost:7860`).

---

## Voraussetzungen

### uv

Dieses Projekt verwendet [uv](https://docs.astral.sh/uv/) als Paketmanager.
Installationsanleitung: <https://docs.astral.sh/uv/getting-started/installation/>

### Docker

Qdrant läuft als Docker-Container. Voraussetzung ist eine installierte
[Docker](https://docs.docker.com/get-docker/)-Umgebung (Docker Desktop oder Docker Engine
mit dem Compose-Plugin).

### Ollama

[Ollama](https://ollama.com/) muss lokal installiert und gestartet sein.
Zusätzlich werden die folgenden zwei Modelle benötigt:

| Modell | Verwendung |
|--------|------------|
| `gpt-oss` | LLM (Konversation & Reasoning) |
| `bge-m3` | Embedding (Vektorisierung der Suchanfragen) |

---

## Installation

### 1. Repository klonen

```bash
git clone https://github.com/nkamiy/rvk_estimation.git
cd rvk_estimation
```

### 2. Abhängigkeiten installieren

```bash
uv sync
```

### 3. Qdrant starten

```bash
docker compose up -d
```

Qdrant läuft anschließend auf `localhost:6333` (REST-API) und `localhost:6334` (gRPC).

### 4. Vektordatenbank einrichten

Der Agent setzt eine befüllte Qdrant-Collection voraus. Dafür gibt es zwei Möglichkeiten:

#### Option A: Snapshot wiederherstellen (empfohlen)

Ein fertiger Snapshot der Collection ist auf Hugging Face verfügbar
([nkamiy/rvk_notation_vector](https://huggingface.co/datasets/nkamiy/rvk_notation_vector)).
Das Skript `restore_snapshot.py` lädt ihn herunter und importiert ihn direkt in Qdrant:

```bash
uv run restore_snapshot.py
```

> Der Download umfasst knapp 1 GB. Der Import selbst dauert nur wenige Minuten.

#### Option B: Neu aufbauen aus MARCXML

Alternativ kann die Collection aus dem offiziellen RVK-MARCXML-Dump neu erstellt werden.
Details dazu im Abschnitt [Vektordatenbank neu aufbauen](#vektordatenbank-neu-aufbauen).

### 5. Ollama-Modelle herunterladen

```bash
ollama pull gpt-oss
ollama pull bge-m3
```

---

## Anwendung starten

```bash
uv run app.py
```

Die Gradio-Oberfläche ist anschließend im Browser erreichbar (standardmäßig unter
`http://localhost:7860`).

---

## Vektordatenbank neu aufbauen

Dieser Abschnitt ist nur relevant, wenn die Collection nicht per Snapshot wiederhergestellt
werden soll (z. B. bei einer neueren RVK-Version).

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
