"""
Restore the RVK vector snapshot from Hugging Face into a local Qdrant instance.

Requirements:
    - Qdrant running at localhost:6333  (docker compose up -d)
    - uv run restore_snapshot.py
"""

from pathlib import Path

import httpx
from huggingface_hub import hf_hub_download

HF_REPO_ID = "nkamiy/rvk_notation_vector"
SNAPSHOT_FILENAME = "rvk_vector_2025_4.snapshot"
COLLECTION = "rvk"
QDRANT_URL = "http://localhost:6333"


def main() -> None:
    # 1. Download snapshot from Hugging Face (uses local cache if already present)
    print(f"Downloading snapshot from {HF_REPO_ID} …")
    snapshot_path = Path(
        hf_hub_download(
            repo_id=HF_REPO_ID,
            filename=SNAPSHOT_FILENAME,
            repo_type="dataset",
        )
    )
    print(f"Downloaded: {snapshot_path} ({snapshot_path.stat().st_size / 1024**3:.2f} GB)")

    # 2. Upload snapshot to Qdrant (this creates/replaces the collection)
    print(f"Uploading snapshot to Qdrant ({QDRANT_URL}/collections/{COLLECTION}) …")
    url = f"{QDRANT_URL}/collections/{COLLECTION}/snapshots/upload"
    with httpx.Client(timeout=600) as client:
        with snapshot_path.open("rb") as f:
            resp = client.post(
                url,
                files={"snapshot": (snapshot_path.name, f, "application/octet-stream")},
                params={"priority": "snapshot"},
            )
        resp.raise_for_status()

    print("Snapshot restored successfully.")
    print(f"Collection '{COLLECTION}' is ready at {QDRANT_URL}.")


if __name__ == "__main__":
    main()
