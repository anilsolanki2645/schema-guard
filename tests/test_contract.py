"""
Tests for schema_guard.contract — YAML loading, env resolution, and validation.
"""
import os
import pytest
import tempfile
import yaml
from schema_guard.contract import load_contract, validate_contract


def _write_yaml(tmp_path, data: dict, filename="test_contract.yaml"):
    """Write a dict as YAML to a temp file and return the path."""
    path = os.path.join(tmp_path, filename)
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


@pytest.fixture
def valid_contract_data():
    return {
        "source": {
            "name": "test_table",
            "type": "postgres",
            "connection": "postgresql://user:pass@localhost/db",
            "schema": "public",
            "table": "orders",
        },
        "columns": [
            {"name": "id", "type": "integer", "nullable": False},
            {"name": "amount", "type": "numeric(10,2)", "nullable": False},
        ]
    }


# ─── Valid contracts ─────────────────────────────────────────────────────────

class TestValidContract:
    def test_loads_valid_contract(self, tmp_path, valid_contract_data):
        path = _write_yaml(str(tmp_path), valid_contract_data)
        cfg = load_contract(path)
        assert cfg["source"]["type"] == "postgres"
        assert len(cfg["columns"]) == 2

    def test_contract_without_columns_section(self, tmp_path):
        """Columns are optional — a contract with only 'source' is valid."""
        data = {
            "source": {
                "type": "postgres",
                "connection": "postgresql://user:pass@localhost/db",
                "schema": "public",
                "table": "orders",
            }
        }
        path = _write_yaml(str(tmp_path), data)
        cfg = load_contract(path)
        assert "columns" not in cfg


# ─── Env resolution ──────────────────────────────────────────────────────────

class TestEnvResolution:
    def test_resolves_env_variable(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_DB_CONN", "postgresql://resolved@localhost/db")
        data = {
            "source": {
                "type": "postgres",
                "connection": "env:TEST_DB_CONN",
                "schema": "public",
                "table": "orders",
            }
        }
        path = _write_yaml(str(tmp_path), data)
        cfg = load_contract(path)
        assert cfg["source"]["connection"] == "postgresql://resolved@localhost/db"

    def test_missing_env_variable_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_VAR_12345", raising=False)
        data = {
            "source": {
                "type": "postgres",
                "connection": "env:NONEXISTENT_VAR_12345",
                "schema": "public",
                "table": "orders",
            }
        }
        path = _write_yaml(str(tmp_path), data)
        with pytest.raises(ValueError, match="NONEXISTENT_VAR_12345"):
            load_contract(path)


# ─── Validation failures (Fix #8) ───────────────────────────────────────────

class TestContractValidation:
    def test_missing_source_section(self, tmp_path):
        path = _write_yaml(str(tmp_path), {"columns": []})
        with pytest.raises(ValueError, match="missing the required 'source'"):
            load_contract(path)

    def test_missing_source_type(self, tmp_path):
        data = {
            "source": {
                "connection": "postgresql://x",
                "schema": "public",
                "table": "orders",
            }
        }
        path = _write_yaml(str(tmp_path), data)
        with pytest.raises(ValueError, match="missing required key: 'type'"):
            load_contract(path)

    def test_missing_source_connection(self, tmp_path):
        data = {
            "source": {
                "type": "postgres",
                "schema": "public",
                "table": "orders",
            }
        }
        path = _write_yaml(str(tmp_path), data)
        with pytest.raises(ValueError, match="missing required key: 'connection'"):
            load_contract(path)

    def test_unsupported_source_type(self, tmp_path):
        data = {
            "source": {
                "type": "snowflake",
                "connection": "xxx",
                "schema": "public",
                "table": "orders",
            }
        }
        path = _write_yaml(str(tmp_path), data)
        with pytest.raises(ValueError, match="Unsupported source type"):
            load_contract(path)

    def test_column_missing_name(self, tmp_path):
        data = {
            "source": {
                "type": "postgres",
                "connection": "postgresql://x",
                "schema": "public",
                "table": "orders",
            },
            "columns": [{"type": "integer", "nullable": False}],
        }
        path = _write_yaml(str(tmp_path), data)
        with pytest.raises(ValueError, match="missing required key: 'name'"):
            load_contract(path)

    def test_column_missing_type(self, tmp_path):
        data = {
            "source": {
                "type": "postgres",
                "connection": "postgresql://x",
                "schema": "public",
                "table": "orders",
            },
            "columns": [{"name": "id", "nullable": False}],
        }
        path = _write_yaml(str(tmp_path), data)
        with pytest.raises(ValueError, match="missing required key: 'type'"):
            load_contract(path)

    def test_malformed_allowed_drift(self, tmp_path):
        data = {
            "source": {
                "type": "postgres",
                "connection": "postgresql://x",
                "schema": "public",
                "table": "orders",
            },
            "columns": [{
                "name": "amount",
                "type": "numeric",
                "nullable": False,
                "allowed_drift": [{"from": "numeric"}]  # missing 'to'
            }],
        }
        path = _write_yaml(str(tmp_path), data)
        with pytest.raises(ValueError, match="must have 'from' and 'to'"):
            load_contract(path)

    def test_empty_yaml_raises(self, tmp_path):
        path = os.path.join(str(tmp_path), "empty.yaml")
        with open(path, "w") as f:
            f.write("")
        with pytest.raises(ValueError, match="empty or invalid"):
            load_contract(path)
