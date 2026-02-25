from pathlib import Path

import httpx
from huggingface_hub import HfApi
from qdrant_client import QdrantClient

COLLECTION = "rvk"
QDRANT_URL = "http://localhost:6333"
HF_REPO_ID = "nkamiy/rvk_notation_vector"

client = QdrantClient(url=QDRANT_URL, timeout=600)

print("Creating snapshot...")
snapshot = client.create_snapshot(collection_name=COLLECTION)
snapshot_name = snapshot.name
print(f"Snapshot created: {snapshot_name}")

print("Downloading snapshot...")
download_url = f"{QDRANT_URL}/collections/{COLLECTION}/snapshots/{snapshot_name}"
snapshot_path = Path(snapshot_name)
with httpx.stream("GET", download_url, timeout=600.0) as resp:
    resp.raise_for_status()
    with snapshot_path.open("wb") as f:
        for chunk in resp.iter_bytes():
            f.write(chunk)
print(f"Downloaded: {snapshot_path} ({snapshot_path.stat().st_size / 1024**3:.2f} GB)")

print(f"Uploading to {HF_REPO_ID}...")
api = HfApi()
api.upload_file(
    path_or_fileobj=str(snapshot_path),
    path_in_repo=snapshot_name,
    repo_id=HF_REPO_ID,
    repo_type="dataset",
)
print("Upload complete.")

snapshot_path.unlink()
print("Local snapshot file removed.")
