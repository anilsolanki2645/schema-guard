"""
Tests for new features: dry-run, verbose, config, contract integrity.
"""
import os
import json
import pytest
import yaml
from unittest.mock import patch

from schema_guard.config import load_config, merge_config, apply_email_config
from schema_guard.contract import hash_contract, lock_contract, verify_contract_integrity
from schema_guard.logger import setup_logger, get_logger


# ─── Config tests ────────────────────────────────────────────────────────────

class TestConfigLoading:
    def test_loads_flat_config(self, tmp_path):
        config_data = {
            "contract": "contracts/orders.yaml",
            "snapshot-file": "snapshots/orders.json",
            "verbose": True,
        }
        path = os.path.join(str(tmp_path), "config.yml")
        with open(path, "w") as f:
            yaml.dump(config_data, f)
        cfg = load_config(path)
        assert cfg["contract"] == "contracts/orders.yaml"
        assert cfg["verbose"] is True

    def test_loads_profile_config(self, tmp_path, monkeypatch):
        config_data = {
            "contract": "default.yaml",
            "profiles": {
                "dev": {
                    "contract": "dev.yaml",
                    "verbose": True,
                },
                "prod": {
                    "contract": "prod.yaml",
                    "verbose": False,
                }
            }
        }
        path = os.path.join(str(tmp_path), "config.yml")
        with open(path, "w") as f:
            yaml.dump(config_data, f)

        monkeypatch.setenv("SCHEMA_GUARD_PROFILE", "dev")
        cfg = load_config(path)
        assert cfg["contract"] == "dev.yaml"
        assert cfg["verbose"] is True

    def test_invalid_profile_raises(self, tmp_path, monkeypatch):
        config_data = {
            "profiles": {
                "dev": {"contract": "dev.yaml"},
            }
        }
        path = os.path.join(str(tmp_path), "config.yml")
        with open(path, "w") as f:
            yaml.dump(config_data, f)

        monkeypatch.setenv("SCHEMA_GUARD_PROFILE", "staging")
        with pytest.raises(ValueError, match="Profile 'staging' not found"):
            load_config(path)

    def test_returns_empty_when_no_file(self):
        cfg = load_config("/nonexistent/path/config.yml")
        assert cfg == {}

    def test_returns_empty_when_no_default(self, tmp_path, monkeypatch):
        monkeypatch.chdir(str(tmp_path))
        cfg = load_config(None)
        assert cfg == {}


class TestApplyEmailConfig:
    def test_sets_email_env_vars(self, monkeypatch):
        monkeypatch.delenv("EMAIL_HOST", raising=False)
        config = {
            "email": {
                "enabled": True,
                "host": "smtp.test.com",
                "port": 465,
            }
        }
        apply_email_config(config)
        assert os.getenv("EMAIL_HOST") == "smtp.test.com"
        assert os.getenv("EMAIL_PORT") == "465"

    def test_does_not_override_existing_env(self, monkeypatch):
        monkeypatch.setenv("EMAIL_HOST", "original.com")
        config = {
            "email": {
                "host": "override.com",
            }
        }
        apply_email_config(config)
        assert os.getenv("EMAIL_HOST") == "original.com"


# ─── Contract integrity tests ────────────────────────────────────────────────

class TestContractIntegrity:
    def test_hash_is_deterministic(self, tmp_path):
        path = os.path.join(str(tmp_path), "test.yaml")
        with open(path, "w") as f:
            f.write("source:\n  type: postgres\n")
        h1 = hash_contract(path)
        h2 = hash_contract(path)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_lock_creates_sidecar(self, tmp_path):
        path = os.path.join(str(tmp_path), "test.yaml")
        with open(path, "w") as f:
            f.write("source:\n  type: postgres\n")
        lock_path = lock_contract(path)
        assert os.path.exists(lock_path)
        assert lock_path == path + ".lock"

        with open(lock_path) as f:
            lock_data = json.load(f)
        assert "hash" in lock_data
        assert lock_data["contract"] == "test.yaml"

    def test_verify_passes_for_unmodified(self, tmp_path):
        path = os.path.join(str(tmp_path), "test.yaml")
        with open(path, "w") as f:
            f.write("source:\n  type: postgres\n")
        lock_contract(path)
        assert verify_contract_integrity(path) is True

    def test_verify_fails_for_modified(self, tmp_path):
        path = os.path.join(str(tmp_path), "test.yaml")
        with open(path, "w") as f:
            f.write("source:\n  type: postgres\n")
        lock_contract(path)

        # Modify the contract
        with open(path, "w") as f:
            f.write("source:\n  type: mysql\n")

        with pytest.raises(ValueError, match="Contract integrity check FAILED"):
            verify_contract_integrity(path)

    def test_verify_returns_false_when_no_lock(self, tmp_path):
        path = os.path.join(str(tmp_path), "test.yaml")
        with open(path, "w") as f:
            f.write("source:\n  type: postgres\n")
        assert verify_contract_integrity(path) is False


# ─── Logger tests ─────────────────────────────────────────────────────────────

class TestLogger:
    def test_setup_verbose_logger(self):
        import logging
        logger = setup_logger(verbose=True)
        assert logger.level == logging.DEBUG

    def test_setup_non_verbose_logger(self):
        import logging
        logger = setup_logger(verbose=False)
        assert logger.level == logging.WARNING

    def test_get_logger_returns_same_instance(self):
        setup_logger(verbose=True)
        logger = get_logger()
        assert logger.name == "schema_guard"


# ─── Contract generation tests ───────────────────────────────────────────────

class MockExtractor:
    def get_schema(self, connection_details, schema_name, table_name):
        # Return a mock schema structure
        return {
            "table": f"{schema_name}.{table_name}",
            "columns": [
                {"name": "id", "type": "INTEGER", "nullable": False},
                {"name": "name", "type": "VARCHAR(255)", "nullable": True}
            ]
        }


class TestContractGeneration:
    @patch("schema_guard.cli.get_extractor")
    def test_generate_creates_valid_yaml(self, mock_get_extractor, tmp_path):
        mock_get_extractor.return_value = MockExtractor()
        output_file = os.path.join(str(tmp_path), "generated.yaml")

        from click.testing import CliRunner
        from schema_guard.cli import generate

        runner = CliRunner()
        result = runner.invoke(generate, [
            "--type", "postgres",
            "--connection", "postgresql://localhost/db",
            "--schema", "public",
            "--table", "users",
            "--output", output_file
        ])

        assert result.exit_code == 0
        assert "Contract successfully generated" in result.output
        assert os.path.exists(output_file)

        # Load and verify contract content
        with open(output_file) as f:
            cfg = yaml.safe_load(f)

        assert cfg["source"]["type"] == "postgres"
        assert cfg["source"]["connection"] == "postgresql://localhost/db"
        assert cfg["source"]["schema"] == "public"
        assert cfg["source"]["table"] == "users"
        assert len(cfg["columns"]) == 2
        assert cfg["columns"][0] == {"name": "id", "type": "INTEGER", "nullable": False}
        assert cfg["columns"][1] == {"name": "name", "type": "VARCHAR(255)", "nullable": True}

    @patch("schema_guard.cli.get_extractor")
    def test_generate_resolves_env_reference(self, mock_get_extractor, tmp_path, monkeypatch):
        mock_get_extractor.return_value = MockExtractor()
        monkeypatch.setenv("TEST_GENERATOR_CONN", "postgresql://secret_user@localhost/db")

        output_file = os.path.join(str(tmp_path), "generated.yaml")

        from click.testing import CliRunner
        from schema_guard.cli import generate

        runner = CliRunner()
        result = runner.invoke(generate, [
            "--type", "postgres",
            "--connection", "env:TEST_GENERATOR_CONN",
            "--schema", "public",
            "--table", "users",
            "--output", output_file
        ])

        assert result.exit_code == 0
        assert os.path.exists(output_file)

        with open(output_file) as f:
            cfg = yaml.safe_load(f)

        # It must write the environment reference string, NOT the secret itself
        assert cfg["source"]["connection"] == "env:TEST_GENERATOR_CONN"

    @patch("schema_guard.cli.get_extractor")
    def test_generate_overwrite_protection(self, mock_get_extractor, tmp_path):
        mock_get_extractor.return_value = MockExtractor()
        output_file = os.path.join(str(tmp_path), "generated.yaml")

        # Create existing file
        with open(output_file, "w") as f:
            f.write("existing content")

        from click.testing import CliRunner
        from schema_guard.cli import generate

        runner = CliRunner()
        # Should refuse without --force
        result = runner.invoke(generate, [
            "--type", "postgres",
            "--connection", "postgresql://localhost/db",
            "--schema", "public",
            "--table", "users",
            "--output", output_file
        ])
        assert result.exit_code == 1
        assert "already exists" in result.output

        # Should overwrite with --force
        result_force = runner.invoke(generate, [
            "--type", "postgres",
            "--connection", "postgresql://localhost/db",
            "--schema", "public",
            "--table", "users",
            "--output", output_file,
            "--force"
        ])
        assert result_force.exit_code == 0
        assert "Contract successfully generated" in result_force.output

    @patch("schema_guard.cli.get_extractor")
    def test_generate_creates_parent_directories(self, mock_get_extractor, tmp_path):
        mock_get_extractor.return_value = MockExtractor()
        # Nested output path that does not exist
        output_file = os.path.join(str(tmp_path), "nested_dir", "sub_dir", "generated.yaml")

        from click.testing import CliRunner
        from schema_guard.cli import generate

        runner = CliRunner()
        result = runner.invoke(generate, [
            "--type", "postgres",
            "--connection", "postgresql://localhost/db",
            "--schema", "public",
            "--table", "users",
            "--output", output_file
        ])

        assert result.exit_code == 0
        assert os.path.exists(output_file)

    @patch("schema_guard.cli.get_extractor")
    def test_generate_interactive_prompts(self, mock_get_extractor, tmp_path):
        mock_get_extractor.return_value = MockExtractor()
        output_file = os.path.join(str(tmp_path), "interactive.yaml")

        from click.testing import CliRunner
        from schema_guard.cli import generate

        runner = CliRunner()
        # Feed inputs interactively:
        # 1. Type: postgres
        # 2. Connection: postgresql://localhost/db
        # 3. Schema: [default is public, so enter/empty]
        # 4. Table: customers
        # 5. Output: output_file
        inputs = f"postgres\npostgresql://localhost/db\n\ncustomers\n{output_file}\n"
        result = runner.invoke(generate, [], input=inputs)

        assert result.exit_code == 0
        assert "Contract successfully generated" in result.output
        assert os.path.exists(output_file)

        with open(output_file) as f:
            cfg = yaml.safe_load(f)

        assert cfg["source"]["type"] == "postgres"
        assert cfg["source"]["connection"] == "postgresql://localhost/db"
        assert cfg["source"]["schema"] == "public"
        assert cfg["source"]["table"] == "customers"

    @patch("schema_guard.cli.get_extractor")
    def test_generate_driver_missing_hint(self, mock_get_extractor, tmp_path):
        # Simulate driver module not installed
        mock_get_extractor.side_effect = ModuleNotFoundError("No module named 'snowflake'")
        output_file = os.path.join(str(tmp_path), "generated.yaml")

        from click.testing import CliRunner
        from schema_guard.cli import generate

        runner = CliRunner()
        result = runner.invoke(generate, [
            "--type", "snowflake",
            "--connection", "snowflake://account/db",
            "--schema", "PUBLIC",
            "--table", "orders",
            "--output", output_file
        ])

        assert result.exit_code == 2
        assert "Database driver missing" in result.output
        assert "pip install" in result.output
        assert "db-schema-guard[snowflake]" in result.output


