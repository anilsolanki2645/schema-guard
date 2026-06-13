"""
Tests for schema_guard.snapshot — save/load round-trip and integrity verification.
"""
import json
import os
import pytest
from schema_guard.snapshot import capture_snapshot, load_snapshot, _compute_hash


@pytest.fixture
def sample_schema():
    return {
        "table": "public.orders",
        "columns": [
            {"name": "id", "type": "INTEGER", "nullable": False, "primary_key": True},
            {"name": "amount", "type": "NUMERIC(10,2)", "nullable": False, "primary_key": False},
        ]
    }


# ─── Round-trip ──────────────────────────────────────────────────────────────

class TestRoundTrip:
    def test_save_and_load(self, tmp_path, sample_schema):
        path = os.path.join(str(tmp_path), "snap.json")
        capture_snapshot(sample_schema, path)
        loaded = load_snapshot(path)
        assert loaded["schema"] == sample_schema
        assert "captured_at" in loaded
        assert "hash" in loaded

    def test_hash_is_deterministic(self, sample_schema):
        h1 = _compute_hash(sample_schema)
        h2 = _compute_hash(sample_schema)
        assert h1 == h2

    def test_creates_parent_directories(self, tmp_path, sample_schema):
        path = os.path.join(str(tmp_path), "deep", "nested", "snap.json")
        capture_snapshot(sample_schema, path)
        assert os.path.exists(path)


# ─── Integrity verification (Fix #2) ────────────────────────────────────────

class TestIntegrityVerification:
    def test_tampered_schema_raises(self, tmp_path, sample_schema):
        """If someone edits the schema JSON, the hash won't match."""
        path = os.path.join(str(tmp_path), "snap.json")
        capture_snapshot(sample_schema, path)

        # Tamper with the snapshot
        with open(path) as f:
            data = json.load(f)
        data["schema"]["columns"][0]["nullable"] = True  # tamper!
        with open(path, "w") as f:
            json.dump(data, f)

        with pytest.raises(ValueError, match="integrity check FAILED"):
            load_snapshot(path)

    def test_tampered_hash_raises(self, tmp_path, sample_schema):
        """If someone replaces the hash with a fake one, it still fails."""
        path = os.path.join(str(tmp_path), "snap.json")
        capture_snapshot(sample_schema, path)

        with open(path) as f:
            data = json.load(f)
        data["hash"] = "deadbeef" * 8  # fake hash
        with open(path, "w") as f:
            json.dump(data, f)

        with pytest.raises(ValueError, match="integrity check FAILED"):
            load_snapshot(path)

    def test_missing_hash_raises(self, tmp_path, sample_schema):
        """Snapshot without a hash field should fail."""
        path = os.path.join(str(tmp_path), "snap.json")
        capture_snapshot(sample_schema, path)

        with open(path) as f:
            data = json.load(f)
        del data["hash"]
        with open(path, "w") as f:
            json.dump(data, f)

        with pytest.raises(ValueError, match="missing the 'hash' field"):
            load_snapshot(path)

    def test_valid_snapshot_passes(self, tmp_path, sample_schema):
        """An untampered snapshot should load without error."""
        path = os.path.join(str(tmp_path), "snap.json")
        capture_snapshot(sample_schema, path)
        loaded = load_snapshot(path)  # should NOT raise
        assert loaded["schema"] == sample_schema
