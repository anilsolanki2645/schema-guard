"""
Tests for schema_guard.diff_engine — the core drift detection logic.
"""
import pytest
from schema_guard.diff_engine import compare_schemas, normalize_type


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_schema(columns):
    return {"table": "public.test", "columns": columns}


def _col(name, type_str, nullable=False, primary_key=False):
    return {"name": name, "type": type_str, "nullable": nullable, "primary_key": primary_key}


# ─── normalize_type ──────────────────────────────────────────────────────────

class TestNormalizeType:
    def test_lowercase(self):
        assert normalize_type("INTEGER") == "integer"

    def test_strip_spaces(self):
        assert normalize_type("NUMERIC(10, 2)") == "numeric(10,2)"

    def test_already_normalized(self):
        assert normalize_type("varchar(20)") == "varchar(20)"


# ─── Column removed ─────────────────────────────────────────────────────────

class TestColumnRemoved:
    def test_detects_removed_column(self):
        snap = _make_schema([_col("id", "INTEGER"), _col("amount", "NUMERIC(10,2)")])
        live = _make_schema([_col("id", "INTEGER")])  # amount removed
        violations, _ = compare_schemas(live, snap, [])
        assert len(violations) == 1
        assert "CRITICAL" in violations[0]
        assert "'amount' removed" in violations[0]


# ─── Column added ────────────────────────────────────────────────────────────

class TestColumnAdded:
    def test_detects_added_column(self):
        snap = _make_schema([_col("id", "INTEGER")])
        live = _make_schema([_col("id", "INTEGER"), _col("new_col", "TEXT")])
        violations, _ = compare_schemas(live, snap, [])
        assert len(violations) == 1
        assert "WARNING" in violations[0]
        assert "'new_col' added" in violations[0]


# ─── Nullable change ────────────────────────────────────────────────────────

class TestNullableChange:
    def test_detects_nullable_change(self):
        snap = _make_schema([_col("amount", "NUMERIC", nullable=False)])
        live = _make_schema([_col("amount", "NUMERIC", nullable=True)])
        violations, _ = compare_schemas(live, snap, [])
        assert len(violations) == 1
        assert "CRITICAL" in violations[0]
        assert "nullable changed" in violations[0]

    def test_no_violation_when_nullable_matches(self):
        snap = _make_schema([_col("amount", "NUMERIC", nullable=False)])
        live = _make_schema([_col("amount", "NUMERIC", nullable=False)])
        violations, _ = compare_schemas(live, snap, [])
        assert len(violations) == 0


# ─── Type change ─────────────────────────────────────────────────────────────

class TestTypeChange:
    def test_detects_type_change(self):
        snap = _make_schema([_col("amount", "NUMERIC(10,2)")])
        live = _make_schema([_col("amount", "TEXT")])
        violations, _ = compare_schemas(live, snap, [])
        assert any("type changed" in v for v in violations)

    def test_case_insensitive_no_false_positive(self):
        """Fix #4: 'INTEGER' vs 'integer' should NOT trigger a violation."""
        snap = _make_schema([_col("id", "INTEGER")])
        live = _make_schema([_col("id", "integer")])
        violations, _ = compare_schemas(live, snap, [])
        type_violations = [v for v in violations if "type changed" in v]
        assert len(type_violations) == 0

    def test_whitespace_insensitive(self):
        """Fix #4: 'NUMERIC(10, 2)' vs 'numeric(10,2)' should NOT trigger."""
        snap = _make_schema([_col("amount", "NUMERIC(10, 2)")])
        live = _make_schema([_col("amount", "numeric(10,2)")])
        violations, _ = compare_schemas(live, snap, [])
        type_violations = [v for v in violations if "type changed" in v]
        assert len(type_violations) == 0


# ─── Allowed drift ───────────────────────────────────────────────────────────

class TestAllowedDrift:
    def test_allowed_drift_passes(self):
        snap = _make_schema([_col("amount", "NUMERIC(10,2)")])
        live = _make_schema([_col("amount", "NUMERIC(12,2)")])
        contract_cols = [{
            "name": "amount",
            "type": "numeric(10,2)",
            "nullable": False,
            "allowed_drift": [{"from": "NUMERIC(10,2)", "to": "NUMERIC(12,2)"}]
        }]
        violations, notices = compare_schemas(live, snap, contract_cols)
        type_violations = [v for v in violations if "type changed" in v]
        assert len(type_violations) == 0
        # Fix #7: Should produce an INFO notice
        assert any("Allowed drift" in n for n in notices)

    def test_disallowed_drift_fails(self):
        snap = _make_schema([_col("amount", "NUMERIC(10,2)")])
        live = _make_schema([_col("amount", "TEXT")])
        contract_cols = [{
            "name": "amount",
            "type": "numeric(10,2)",
            "nullable": False,
            "allowed_drift": [{"from": "NUMERIC(10,2)", "to": "NUMERIC(12,2)"}]
        }]
        violations, _ = compare_schemas(live, snap, contract_cols)
        assert any("not in allowed_drift" in v for v in violations)

    def test_allowed_drift_case_insensitive(self):
        """Fix #4: allowed_drift rules should also be case-insensitive."""
        snap = _make_schema([_col("amount", "NUMERIC(10, 2)")])
        live = _make_schema([_col("amount", "numeric(12,2)")])
        contract_cols = [{
            "name": "amount",
            "type": "numeric(10,2)",
            "nullable": False,
            "allowed_drift": [{"from": "numeric(10,2)", "to": "Numeric(12,2)"}]
        }]
        violations, notices = compare_schemas(live, snap, contract_cols)
        type_violations = [v for v in violations if "type changed" in v]
        assert len(type_violations) == 0
        assert any("Allowed drift" in n for n in notices)


# ─── Primary key changes (Fix #6) ───────────────────────────────────────────

class TestPrimaryKeyChange:
    def test_detects_pk_dropped(self):
        snap = _make_schema([_col("id", "INTEGER", primary_key=True)])
        live = _make_schema([_col("id", "INTEGER", primary_key=False)])
        violations, _ = compare_schemas(live, snap, [])
        assert any("primary key constraint DROPPED" in v for v in violations)

    def test_detects_pk_added(self):
        snap = _make_schema([_col("id", "INTEGER", primary_key=False)])
        live = _make_schema([_col("id", "INTEGER", primary_key=True)])
        violations, _ = compare_schemas(live, snap, [])
        assert any("primary key constraint ADDED" in v for v in violations)

    def test_no_violation_when_pk_matches(self):
        snap = _make_schema([_col("id", "INTEGER", primary_key=True)])
        live = _make_schema([_col("id", "INTEGER", primary_key=True)])
        violations, _ = compare_schemas(live, snap, [])
        pk_violations = [v for v in violations if "primary key" in v]
        assert len(pk_violations) == 0


# ─── Contract vs snapshot validation (Fix #5) ───────────────────────────────

class TestContractVsSnapshot:
    def test_warns_type_mismatch(self):
        snap = _make_schema([_col("amount", "TEXT")])
        live = _make_schema([_col("amount", "TEXT")])  # no live drift
        contract_cols = [{"name": "amount", "type": "numeric(10,2)", "nullable": False}]
        _, notices = compare_schemas(live, snap, contract_cols)
        assert any("Snapshot type" in n and "contract expects" in n for n in notices)

    def test_warns_nullable_mismatch(self):
        snap = _make_schema([_col("amount", "NUMERIC(10,2)", nullable=True)])
        live = _make_schema([_col("amount", "NUMERIC(10,2)", nullable=True)])
        contract_cols = [{"name": "amount", "type": "numeric(10,2)", "nullable": False}]
        _, notices = compare_schemas(live, snap, contract_cols)
        assert any("Snapshot nullable" in n and "contract expects" in n for n in notices)

    def test_no_warning_when_contract_matches(self):
        snap = _make_schema([_col("id", "INTEGER", nullable=False)])
        live = _make_schema([_col("id", "INTEGER", nullable=False)])
        contract_cols = [{"name": "id", "type": "integer", "nullable": False}]
        _, notices = compare_schemas(live, snap, contract_cols)
        contract_warnings = [n for n in notices if "contract expects" in n]
        assert len(contract_warnings) == 0


# ─── No drift (happy path) ──────────────────────────────────────────────────

class TestNoDrift:
    def test_identical_schemas_pass(self):
        schema = _make_schema([
            _col("id", "INTEGER", nullable=False, primary_key=True),
            _col("amount", "NUMERIC(10,2)", nullable=False),
            _col("status", "VARCHAR(20)", nullable=False),
        ])
        violations, notices = compare_schemas(schema, schema, [])
        assert len(violations) == 0
