
# 🛡️ Schema Guard

**Stop silent schema drift before it breaks your production data pipelines.**

Schema Guard is a lightweight CLI tool that captures database schema snapshots and acts as a CI/CD gate, blocking deployments when unauthorized schema changes are detected. It's the missing guardrail for data engineers who've been burned by unexpected column drops, type changes, or nullability shifts.

---

## Why Schema Guard?

Every data engineer knows the 2 AM nightmare:
- A source team adds a column, changes a type, or drops a `NOT NULL` without notice.
- Your ETL pipeline doesn't fail—it silently writes `NULL`s or corrupts downstream data.
- Executive dashboards break, and you spend hours tracing the issue back to a trivial schema change.

Schema Guard stops this at the CI gate. You define a **data contract** (YAML), capture a trusted **schema snapshot**, and then in your deployment pipeline, `schema-guard gate` compares the live source against the snapshot and contract. Any drift fails the build *before* it hits production.

---

## 🧠 Architecture Overview

``` 

┌─────────────────┐        ┌──────────────┐        ┌─────────────────┐
│  Contract       │──────▶ │  CLI (snap)  │──────▶│  Snapshot JSON  │
│  (orders.yaml)  │        └──────────────┘        └─────────────────┘
│                 │               │
│  Live Database  │               │
└─────────────────┘               │
                                  │
                      ┌───────────▼───────────┐
                      │  CLI (gate)            │
                      │  Compares live schema  │
                      │  vs snapshot + contract│
                      └───────────┬───────────┘
                                  │
                      ┌───────────▼───────────┐
                      │  Diff Engine          │
                      │  Detects violations   │
                      └───────────┬───────────┘
                                  │
                      ┌───────────▼───────────┐
                      │  Alerter (email)      │
                      │  Sends notifications  │
                      └───────────────────────┘
```

1. **Contract** – Describes the expected schema (columns, types, nullability, allowed drifts).  
2. **Snapshot** – A frozen, integrity-verified JSON representation of the real schema at a trusted point in time.  
3. **Gate** – Compares live schema to snapshot + contract. If drift is detected, it logs violations, sends an email, and exits with code 1 to fail the CI pipeline.

---

## ✨ Key Features

- **Snapshot integrity verification** — Every snapshot is SHA-256 hashed. Tampered or corrupted snapshot files are detected and rejected on load.
- **Overwrite protection** — The `snap` command refuses to overwrite an existing baseline unless `--force` is passed, preventing accidental baseline drift.
- **Case-insensitive type comparison** — `INTEGER` vs `integer` and `NUMERIC(10, 2)` vs `numeric(10,2)` are treated as equal. No more false positives.
- **Primary key drift detection** — Dropped or added primary key constraints are flagged as CRITICAL violations.
- **Contract validation** — Malformed YAML contracts fail fast with clear error messages instead of cryptic `KeyError` crashes.
- **Contract-vs-snapshot warnings** — If the snapshot itself doesn't match the contract expectations, you'll see a WARNING notice so you know the baseline may have been captured at a bad time.
- **Allowed drift visibility** — When an `allowed_drift` rule matches, it's logged as an INFO notice instead of being silently swallowed.
- **Reliable alerting** — Email alert failures are reported to stderr. Use `--require-alert` to fail the gate if email delivery fails.

---

## 🚀 Installation

### From source (for development)
```bash
git clone https://github.com/anilsolanki2645/schema-guard/
cd schema-guard
pip install -e ".[dev]"
```

### From PyPI (once published)
```bash
pip install db-schema-guard
```

Requires Python ≥ 3.8. Dependencies are installed automatically.

---

## ⚡ Quick Start

### 1. Create the database table
```sql
CREATE TABLE public.orders (
    order_id INT PRIMARY KEY,
    amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) NOT NULL
);

INSERT INTO orders VALUES (1, 99.99, 'shipped');
```

### 2. Define a contract – `contracts/orders.yaml`
```yaml
source:
  name: prod_orders
  type: postgres
  connection: "env:DB_CONNECTION_STRING"   # see Configuration
  schema: public
  table: orders
columns:
  - name: order_id
    type: integer
    nullable: false
  - name: amount
    type: numeric(10,2)
    nullable: false
    allowed_drift:
      - from: "numeric(10,2)"
        to: "numeric(12,2)"
  - name: status
    type: character varying(20)
    nullable: false
```

### 3. Set up environment variables

Copy the example file and fill in your values:
```bash
cp .env.example .env
```

Edit `.env`:
```env
DB_CONNECTION_STRING=postgresql://postgres:yourpassword@localhost:5432/schema_guard
```
> **Note:** Special characters must be URL‑encoded, e.g., `@` → `%40`

> **⚠️ Security:** Never commit `.env` to version control. The `.gitignore` is already configured to exclude it. Use `.env.example` as a template reference.

### 4. Capture a snapshot of the current schema
```bash
schema-guard snap --contract contracts/orders.yaml --snapshot-file snapshots/orders.json
```
✅ Snapshot saved to `snapshots/orders.json`

### 5. Verify the gate passes
```bash
schema-guard gate --contract contracts/orders.yaml --snapshot-file snapshots/orders.json
```
✅ Schema matches snapshot. No drift.

### 6. Simulate a drift
```sql
ALTER TABLE public.orders ALTER COLUMN amount DROP NOT NULL;
```

### 7. Run the gate again (should fail)
```bash
schema-guard gate --contract contracts/orders.yaml --snapshot-file snapshots/orders.json
```
```text
❌ Schema drift detected:
  - CRITICAL: Column 'amount' nullable changed from False to True.
```
Command exits with code 1, and an email alert is sent (if configured).

### 8. Revert to clean state
```sql
ALTER TABLE public.orders ALTER COLUMN amount SET NOT NULL;
```
Now the gate passes again.

---

## 📋 Configuration

### Database connection
Define a PostgreSQL connection string in `.env`:
```env
DB_CONNECTION_STRING=postgresql://user:password@host:5432/dbname
```
In the contract, reference it with `"env:DB_CONNECTION_STRING"`.  
The tool's `contract.py` resolves any value beginning with `env:` to the corresponding environment variable.

### Email alerting (optional)
Add these to `.env` to receive drift alerts via SMTP:
```env
EMAIL_ENABLED=true
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password    # Use an App Password, not your real password
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=oncall@example.com
EMAIL_SUBJECT=Schema Drift Detected
```
If `EMAIL_ENABLED` is not `true`, alerts are silently skipped—the gate still works, but no email is sent.

---

## 📖 Command Reference

### `snap` – capture a schema snapshot
```bash
schema-guard snap --contract <contract.yaml> --snapshot-file <snapshot.json> [--force]
```
| Flag | Description |
|------|-------------|
| `--contract` | **(required)** Path to the contract YAML file |
| `--snapshot-file` | Where to save the snapshot (default: `schema_snapshot.json`) |
| `--force` | Overwrite an existing snapshot. Without this flag, the command will refuse to overwrite and show a diff of detected changes |

- Connects to the source defined in the contract.
- Inspects the table and saves column metadata (name, type, nullable, primary key) along with a SHA-256 hash and timestamp.
- **Overwrite protection:** If a snapshot already exists, you must pass `--force` to replace it. This prevents accidentally re-baselining against a drifted schema.

### `gate` – check for drift
```bash
schema-guard gate --contract <contract.yaml> --snapshot-file <snapshot.json> [--require-alert]
```
| Flag | Description |
|------|-------------|
| `--contract` | **(required)** Path to the contract YAML file |
| `--snapshot-file` | Baseline snapshot to compare against (default: `schema_snapshot.json`) |
| `--require-alert` | Exit with code 2 if email alert fails to send |

- Verifies snapshot integrity (SHA-256 hash check) before comparing.
- Extracts the current live schema.
- Validates contract expectations against the snapshot (emits warnings if mismatched).
- Compares live schema against the snapshot using the contract rules.
- **Violation types:**

| Violation | Severity |
|-----------|----------|
| Column removed | CRITICAL |
| Type changed (not in `allowed_drift`) | CRITICAL |
| Nullable changed | CRITICAL |
| Primary key constraint dropped | CRITICAL |
| Primary key constraint added | CRITICAL |
| New column added | WARNING |
| Allowed drift matched | INFO (notice, non-blocking) |

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Gate passed — no drift detected |
| `1` | Schema drift detected — violations found |
| `2` | Email alert failed (when `--require-alert` is set) or unsupported source type |
| `3` | Snapshot integrity check failed (file was tampered with or corrupted) |

---

## 🧱 Contract YAML Specification

A contract file defines the expected state of a data source. The contract is validated on load — missing or malformed fields produce clear error messages.

```yaml
source:
  name: friendly_name           # Used in logs (optional)
  type: postgres                # Source type (currently only postgres supported)
  connection: "env:DB_CONNECTION_STRING"  # Database URL or env:VARIABLE
  schema: public                # Database schema (required)
  table: orders                 # Table name (required)

columns:                          # Optional section
  - name: order_id                # Column name (required)
    type: integer                 # Expected type (required, case-insensitive matching)
    nullable: false               # Expected nullability (required)
    allowed_drift:                # Optional — type changes allowed without alert
      - from: "numeric(10,2)"
        to: "numeric(12,2)"
```

### Required fields

| Section | Required Keys |
|---------|---------------|
| `source` | `type`, `connection`, `schema`, `table` |
| Each column in `columns` | `name`, `type`, `nullable` |
| Each rule in `allowed_drift` | `from`, `to` |

### Matching behavior
- **`type`** comparison is **case-insensitive** and **whitespace-insensitive**. `INTEGER` matches `integer`, and `NUMERIC(10, 2)` matches `numeric(10,2)`.
- **`nullable`** must be `true` or `false`.
- **`allowed_drift`** rules are also matched case-insensitively. When a rule matches, an INFO notice is logged for visibility.

---

## 🔔 Alerting (Email)

The `alerter.py` module sends an email with the list of violations. Uses Python's `smtplib` and `email` libraries (no extra deps).

- Alert errors are printed to **stderr** as `[alerter] Failed to send email: ...`
- The gate still fails with exit code 1 regardless of email success/failure.
- To **require** successful email delivery, use `--require-alert`. If the email fails, the gate exits with code 2.

---

## ⚙️ CI/CD Integration

### GitHub Actions example – `.github/workflows/schema-check.yml`
```yaml
name: Schema Drift Gate

on: [push, pull_request]

jobs:
  schema-drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install schema-guard
        run: pip install -e .            # or pip install db-schema-guard
      - name: Run schema gate
        run: schema-guard gate --contract contracts/orders.yaml --snapshot-file snapshots/orders.json --require-alert
        env:
          DB_CONNECTION_STRING: ${{ secrets.DB_CONNECTION_STRING }}
          EMAIL_ENABLED: true
          EMAIL_HOST: ${{ secrets.EMAIL_HOST }}
          EMAIL_PORT: ${{ secrets.EMAIL_PORT }}
          EMAIL_USER: ${{ secrets.EMAIL_USER }}
          EMAIL_PASSWORD: ${{ secrets.EMAIL_PASSWORD }}
          EMAIL_FROM: ${{ secrets.EMAIL_FROM }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}
```

Store these values as [GitHub Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets).  
Now every push and pull request will be checked for schema drift automatically.

---

## 🧪 Testing

Schema Guard includes a comprehensive test suite with **39 unit tests** covering the core modules. No database connection is required to run the tests — they use in-memory fixtures.

### Running the test suite

```bash
# Install with dev dependencies (includes pytest)
pip install -e ".[dev]"

# Run all tests with verbose output
python -m pytest tests/ -v
```

Expected output:
```text
tests/test_contract.py::TestValidContract::test_loads_valid_contract PASSED
tests/test_contract.py::TestValidContract::test_contract_without_columns_section PASSED
tests/test_contract.py::TestEnvResolution::test_resolves_env_variable PASSED
tests/test_contract.py::TestEnvResolution::test_missing_env_variable_raises PASSED
tests/test_contract.py::TestContractValidation::test_missing_source_section PASSED
tests/test_contract.py::TestContractValidation::test_missing_source_type PASSED
tests/test_contract.py::TestContractValidation::test_missing_source_connection PASSED
tests/test_contract.py::TestContractValidation::test_unsupported_source_type PASSED
tests/test_contract.py::TestContractValidation::test_column_missing_name PASSED
tests/test_contract.py::TestContractValidation::test_column_missing_type PASSED
tests/test_contract.py::TestContractValidation::test_malformed_allowed_drift PASSED
tests/test_contract.py::TestContractValidation::test_empty_yaml_raises PASSED
tests/test_diff_engine.py::TestNormalizeType::test_lowercase PASSED
tests/test_diff_engine.py::TestNormalizeType::test_strip_spaces PASSED
tests/test_diff_engine.py::TestNormalizeType::test_already_normalized PASSED
tests/test_diff_engine.py::TestColumnRemoved::test_detects_removed_column PASSED
tests/test_diff_engine.py::TestColumnAdded::test_detects_added_column PASSED
tests/test_diff_engine.py::TestNullableChange::test_detects_nullable_change PASSED
tests/test_diff_engine.py::TestNullableChange::test_no_violation_when_nullable_matches PASSED
tests/test_diff_engine.py::TestTypeChange::test_detects_type_change PASSED
tests/test_diff_engine.py::TestTypeChange::test_case_insensitive_no_false_positive PASSED
tests/test_diff_engine.py::TestTypeChange::test_whitespace_insensitive PASSED
tests/test_diff_engine.py::TestAllowedDrift::test_allowed_drift_passes PASSED
tests/test_diff_engine.py::TestAllowedDrift::test_disallowed_drift_fails PASSED
tests/test_diff_engine.py::TestAllowedDrift::test_allowed_drift_case_insensitive PASSED
tests/test_diff_engine.py::TestPrimaryKeyChange::test_detects_pk_dropped PASSED
tests/test_diff_engine.py::TestPrimaryKeyChange::test_detects_pk_added PASSED
tests/test_diff_engine.py::TestPrimaryKeyChange::test_no_violation_when_pk_matches PASSED
tests/test_diff_engine.py::TestContractVsSnapshot::test_warns_type_mismatch PASSED
tests/test_diff_engine.py::TestContractVsSnapshot::test_warns_nullable_mismatch PASSED
tests/test_diff_engine.py::TestContractVsSnapshot::test_no_warning_when_contract_matches PASSED
tests/test_diff_engine.py::TestNoDrift::test_identical_schemas_pass PASSED
tests/test_snapshot.py::TestRoundTrip::test_save_and_load PASSED
tests/test_snapshot.py::TestRoundTrip::test_hash_is_deterministic PASSED
tests/test_snapshot.py::TestRoundTrip::test_creates_parent_directories PASSED
tests/test_snapshot.py::TestIntegrityVerification::test_tampered_schema_raises PASSED
tests/test_snapshot.py::TestIntegrityVerification::test_tampered_hash_raises PASSED
tests/test_snapshot.py::TestIntegrityVerification::test_missing_hash_raises PASSED
tests/test_snapshot.py::TestIntegrityVerification::test_valid_snapshot_passes PASSED

============================= 39 passed ==============================
```

### What the tests cover

| Test File | Module | What's Tested |
|-----------|--------|---------------|
| `test_diff_engine.py` | `diff_engine.py` | Column added/removed, type change detection, case-insensitive comparison, nullable change, primary key drift, allowed drift (with logging), contract-vs-snapshot validation, no-drift happy path |
| `test_contract.py` | `contract.py` | Valid YAML loading, env variable resolution, missing env var error, missing required keys (`source`, `type`, `connection`, etc.), unsupported source type, malformed `allowed_drift`, empty YAML |
| `test_snapshot.py` | `snapshot.py` | Save/load round-trip, SHA-256 hash determinism, parent directory auto-creation, tamper detection (modified schema, fake hash, missing hash field) |

### Running a specific test file
```bash
python -m pytest tests/test_diff_engine.py -v      # Only diff engine tests
python -m pytest tests/test_contract.py -v          # Only contract tests
python -m pytest tests/test_snapshot.py -v           # Only snapshot tests
```

### Running a specific test class or method
```bash
python -m pytest tests/test_diff_engine.py::TestPrimaryKeyChange -v           # One class
python -m pytest tests/test_snapshot.py::TestIntegrityVerification::test_tampered_schema_raises -v  # One test
```

---

## 📁 Project Structure

```
schema-guard/
├── .github/workflows/
│   └── schema-check.yml           # CI/CD pipeline config
├── contracts/
│   └── orders.yaml                # Your data contracts
├── snapshots/                     # Baseline snapshots (auto‑created)
│   └── orders.json
├── src/schema_guard/
│   ├── __init__.py
│   ├── cli.py                     # Click CLI (snap & gate commands)
│   ├── contract.py                # YAML parser, env resolver & validator
│   ├── extractors/
│   │   ├── __init__.py
│   │   └── postgres.py            # PostgreSQL schema inspector
│   ├── snapshot.py                # Save/load snapshot JSON with integrity checks
│   ├── diff_engine.py             # Drift detection logic (type, nullable, PK)
│   └── alerter.py                 # SMTP email alerting
├── tests/
│   ├── test_diff_engine.py        # 20 tests — drift detection logic
│   ├── test_contract.py           # 12 tests — YAML loading & validation
│   └── test_snapshot.py           # 7 tests — save/load & integrity
├── pyproject.toml                 # Build & packaging config
├── .env.example                   # Template for environment variables
├── .gitignore
└── README.md
```

---

## 🔌 Extending with New Extractors

To support another data source (Snowflake, BigQuery, S3 Parquet, etc.):

1. Create a new file in `src/schema_guard/extractors/` (e.g., `snowflake.py`).
2. Implement a function `get_schema(connection_string, schema_name, table_name)` returning:
```python
{
    "table": "schema.table",
    "columns": [
        {
            "name": "col1",
            "type": "varchar",
            "nullable": True,
            "primary_key": False
        },
        ...
    ]
}
```
3. In `cli.py`, add an `elif` branch for the new source type.
4. Add any required packages to `pyproject.toml`.

Pull requests are welcome!

---

## 🧩 Troubleshooting

| Problem | Solution |
|--------|----------|
| `FileNotFoundError: snapshots/orders.json` | Run `schema-guard snap` first to create the baseline snapshot. The `snapshots/` directory is auto‑created. |
| `Snapshot integrity check FAILED` | The snapshot file was manually edited or corrupted. Re‑capture a trusted snapshot with `schema-guard snap --force`. |
| `Contract 'source' is missing required key` | Your contract YAML is missing a required field. Check the [Contract YAML Specification](#-contract-yaml-specification). |
| `Unsupported source type` | Only `postgres` is currently supported. Check for typos in `source.type`. |
| `Could not parse SQLAlchemy URL` | The connection string is invalid. Check `.env` and contract; ensure `env:` placeholders resolve correctly. |
| `FATAL: password authentication failed` | Wrong credentials or special characters not URL‑encoded. Encode `@` as `%40`, `%` as `%25`, etc. Test with `psql`. |
| Email not sent | Set `EMAIL_ENABLED=true`. Use an App Password for Gmail. Look for `[alerter]` messages in **stderr**. |
| Gate passes when it shouldn't | Ensure the snapshot file is the correct baseline and hasn't been tampered with. The hash check should catch this. |
| `ModuleNotFoundError` when running CLI | Run `pip install -e .` from the project root. |
| Snapshot overwrite refused | Pass `--force` to `schema-guard snap` to overwrite an existing snapshot. |

---

## 🔒 Security Best Practices

- **Never commit `.env`** — Use `.env.example` as a template. The `.gitignore` excludes `.env` by default.
- **Use GitHub Secrets** for CI/CD — Store `DB_CONNECTION_STRING`, email credentials, etc. as encrypted secrets.
- **Rotate credentials** if they were ever exposed in version control history.
- **Snapshot integrity** — Every snapshot includes a SHA-256 hash. If the file is tampered with, the `gate` command will reject it immediately.

---

## 📜 License

Schema Guard is open‑source under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

**Built with frustration turned into code by a data engineer who just wants to sleep through the night.** ✨
