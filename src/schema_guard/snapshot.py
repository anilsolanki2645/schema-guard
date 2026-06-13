import json
import hashlib
from datetime import datetime, timezone
import os


def _compute_hash(schema_dict: dict) -> str:
    """Compute a SHA-256 hash of the schema dictionary for integrity verification."""
    return hashlib.sha256(json.dumps(schema_dict, sort_keys=True).encode()).hexdigest()


def capture_snapshot(schema_dict: dict, output_path: str = "schema_snapshot.json"):
    """Capture the current schema as a JSON snapshot with an integrity hash."""
    # Create directory if it doesn't exist
    dir_name = os.path.dirname(output_path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "hash": _compute_hash(schema_dict),
        "schema": schema_dict
    }
    with open(output_path, "w") as f:
        json.dump(snapshot, f, indent=2)
    return snapshot


def load_snapshot(path: str = "schema_snapshot.json") -> dict:
    """
    Load a snapshot and verify its integrity hash.
    Raises ValueError if the snapshot has been tampered with.
    """
    with open(path) as f:
        data = json.load(f)

    # --- Fix #2: Verify hash integrity on load ---
    stored_hash = data.get("hash")
    if stored_hash is None:
        raise ValueError(
            f"Snapshot '{path}' is missing the 'hash' field. "
            "It may be corrupted or manually created. Re-capture with 'schema-guard snap'."
        )

    computed_hash = _compute_hash(data["schema"])
    if computed_hash != stored_hash:
        raise ValueError(
            f"Snapshot integrity check FAILED for '{path}'.\n"
            f"  Stored hash:   {stored_hash}\n"
            f"  Computed hash: {computed_hash}\n"
            "The snapshot file has been tampered with or corrupted. "
            "Re-capture a trusted snapshot with 'schema-guard snap'."
        )

    return data