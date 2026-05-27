import json
import hashlib
from datetime import datetime, timezone
import os

def capture_snapshot(schema_dict: dict, output_path: str = "schema_snapshot.json"):
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "hash": hashlib.sha256(json.dumps(schema_dict, sort_keys=True).encode()).hexdigest(),
        "schema": schema_dict
    }
    with open(output_path, "w") as f:
        json.dump(snapshot, f, indent=2)
    return snapshot

def load_snapshot(path: str = "schema_snapshot.json") -> dict:
    with open(path) as f:
        return json.load(f)