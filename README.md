
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

- **Multi-Database Support** — Supports schema drift detection for PostgreSQL, MySQL, Snowflake, SQL Server, Oracle, and Databricks.
- **Automatic Contract Generation** — Generate fully specified contract YAML files directly from live database tables using the new `generate` command.
- **YAML Configuration File** — Centralized configuration file support (`schema-guard-config.yml`) with per-environment profiles (dev, staging, prod) and Jinja2 templating.
- **Dry-Run Gate Mode** — Preview drift violations with `--dry-run` to test CI/CD pipelines without failing the build or sending email notifications.
- **Verbose Debug Logging** — Step-by-step logging with `--verbose` / `-v` detailing connection pooling, schema extraction, and comparison checks.
- **Change History & Audit Trail** — Persist gate execution results (timestamp, profile, violations, notices) in a dedicated database table for compliance.
- **Contract Integrity Verification** — Lock your YAML contract files by creating a `.lock` sidecar with a SHA-256 signature, preventing unauthorized contract edits.
- **Snapshot Integrity Check** — Baseline snapshots are SHA-256 hashed. Tampered or corrupted snapshot files are automatically blocked.
- **Overwrite Protection** — The `snap` command prevents accidentally overwriting your baseline snapshot unless `--force` is specified.
- **Case-Insensitive Comparison** — Treats type mismatches like `INTEGER` vs `integer` or whitespace shifts as identical to reduce false alarms.
- **Primary Key & Nullability Gate** — Tracks additions/deletions of PK constraints and nullability shifts as CRITICAL violations.
- **Allowed Drift Rules** — Map minor expected type changes (e.g. `numeric(10,2)` to `numeric(12,2)`) in the contract without breaking the pipeline.

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
Define a database connection string in `.env`:
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
schema-guard snap [--contract <contract.yaml>] [--snapshot-file <snapshot.json>] [--force] [--verbose] [--config <config.yml>]
```
| Flag / Option | Description |
|---|---|
| `--contract` | Path to the contract YAML file (required if not defined in config) |
| `--snapshot-file` | Where to save the snapshot (default: `schema_snapshot.json`) |
| `--force` | Overwrite an existing snapshot and display a diff of changes |
| `--verbose`, `-v` | Enable verbose step-by-step debug logging |
| `--config`, `-c` | Path to schema-guard configuration YAML file (auto-detects `schema-guard-config.yml` in cwd) |

- Connects to the source database and extracts columns, types, nullability, and primary key constraints.
- Saves the schema details with a SHA-256 integrity hash.
- Overwrite protection guarantees you do not accidentally overwrite a known good baseline without `--force`.

### `gate` – verify schema against snapshot
```bash
schema-guard gate [--contract <contract.yaml>] [--snapshot-file <snapshot.json>] [--require-alert] [--dry-run] [--verbose] [--config <config.yml>]
```
| Flag / Option | Description |
|---|---|
| `--contract` | Path to the contract YAML file (required if not defined in config) |
| `--snapshot-file` | Baseline snapshot to compare against (default: `schema_snapshot.json`) |
| `--require-alert` | Exit with code 2 if email alert fails to send |
| `--dry-run` | Preview drift results without failing CI or sending alerts (exit code is always 0) |
| `--verbose`, `-v` | Enable verbose step-by-step comparison logging |
| `--config`, `-c` | Path to schema-guard configuration YAML file (auto-detects `schema-guard-config.yml` in cwd) |

- Verifies snapshot file integrity.
- If a contract `.lock` sidecar exists, verifies that the contract hasn't been modified.
- Compares live schema metadata against the baseline snapshot using contract rules.
- If history connection parameters are configured, records the PASS/FAIL execution to the change history DB table.

### `lock` – lock a contract file
```bash
schema-guard lock --contract <contract.yaml> [--verbose]
```
- Computes a SHA-256 hash of the contract YAML file and writes a `<contract.yaml>.lock` sidecar.
- If the lock file exists, `gate` will verify that the contract has not been altered before checking drift, guaranteeing contract integrity.
- Re-run this command after making intentional edits to the contract to update the signature.

### `generate` – automatically generate a contract file
```bash
schema-guard generate [--type <database_type>] [--connection <conn>] [--schema <schema>] [--table <table>] [--output <output_path>] [--force] [--verbose]
```
| Flag / Option | Description |
|---|---|
| `--type`, `-t` | Database platform (e.g. `postgres`, `mysql`, `snowflake`, `sqlserver`, `oracle`, `databricks`). Optional; prompts interactively if omitted. |
| `--connection`, `--conn` | Connection URL, JSON connection dictionary, or env variable reference. Optional; prompts interactively if omitted. |
| `--schema`, `-s` | Target schema name. Optional; prompts with a database-specific smart default (e.g. `public`, `dbo`, `default`). |
| `--table`, `--tbl` | Target table name. Optional; prompts interactively if omitted. |
| `--output`, `-o` | Output file path for the contract YAML. Optional; defaults to `contracts/<table_name>.yaml`. |
| `--force`, `-f` | Overwrite the contract file if it already exists. |
| `--verbose`, `-v` | Enable verbose step-by-step debug logging. |

- **Interactive Mode**: Simply run `schema-guard generate` to launch an interactive terminal guide that asks for parameters with dropdown choices and smart defaults.
- Connects to the database and extracts column names, data types, and nullability.
- Formats the resulting metadata into a valid Schema Guard contract YAML.
- Overwrite protection checks if `--output` already exists. In interactive mode, it will prompt for confirmation; in scripts, it will refuse unless `--force` is provided.
- **Credential security**: If an env variable reference is passed (e.g. `--connection env:MY_CONN`), the resolver fetches the secret to extract the schema, but writes the original `"env:MY_CONN"` literal in the contract file.
- **Driver hints**: If a database driver is missing, the command catches the error and prints a friendly `pip install` hint with the correct package extra.

### `history` – view execution history
```bash
schema-guard history [--limit <count>] [--verbose] [--config <config.yml>]
```
- Connects to the database and fetches the recent gate check execution history logs.
- Displays timestamp, result status (PASS/FAIL), profile, contract path, and violations counts.
- Run with `--verbose` to view details on specific violations recorded in past failing runs.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Gate passed — no drift detected |
| `1` | Schema drift detected — violations found |
| `2` | Email alert failed (when `--require-alert` is set) or database/extractor error |
| `3` | Snapshot integrity check failed (file was tampered with or corrupted) |
| `4` | Contract integrity check failed (YAML modified since it was locked) |
---

## 🧱 Contract YAML Specification

A contract file defines the expected state of a data source. The contract is validated on load — missing or malformed fields produce clear error messages.

```yaml
source:
  name: friendly_name           # Used in logs (optional)
  type: postgres                # Source type (postgres, mysql, snowflake, sqlserver, oracle, databricks)
  connection: "env:DB_CONNECTION_STRING"  # Database URL or env:VARIABLE or Connection Dictionary
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

### Connection Dictionary (Optional)
Instead of a single URL string, the `connection` key under `source` can be defined as a mapping of parameters (ideal for config-managed DB setups like Snowflake and Databricks):
```yaml
source:
  type: snowflake
  schema: PUBLIC
  table: ORDERS
  connection:
    account: "{{ env_var('SNOWFLAKE_ACCOUNT') }}"
    user: "{{ env_var('SNOWFLAKE_USER') }}"
    password: "{{ env_var('SNOWFLAKE_PASSWORD') }}"
    database: PROD_DB
    warehouse: COMPUTE_WH
    role: DEV_ROLE
```
Databricks supports access tokens, username/password, and **OAuth 2.0 Client Credentials**:
```yaml
source:
  type: databricks
  schema: default
  table: customers
  connection:
    auth_type: oauth
    server_hostname: "{{ env_var('DATABRICKS_HOST') }}"
    http_path: "{{ env_var('DATABRICKS_PATH') }}"
    client_id: "{{ env_var('DATABRICKS_CLIENT_ID') }}"
    client_secret: "{{ env_var('DATABRICKS_CLIENT_SECRET') }}"
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

Schema Guard includes a comprehensive test suite with **61 unit tests** covering the core modules. No database connection is required to run the tests — they use in-memory fixtures and mock inspection suites.

### Running the test suite

```bash
# Install with dev dependencies (includes pytest)
pip install -e ".[dev]"

# Run all tests with verbose output
python -m pytest tests/ -v
```

### What the tests cover

| Test File | Module | What's Tested |
|-----------|--------|---------------|
| `test_diff_engine.py` | `diff_engine.py` | Column added/removed, type change detection, case-insensitive comparison, nullable change, primary key drift, allowed drift (with logging), contract-vs-snapshot validation, no-drift happy path |
| `test_contract.py` | `contract.py` | Valid YAML loading, env variable resolution, missing env var error, missing required keys (`source`, `type`, `connection`, etc.), unsupported source type, malformed `allowed_drift`, empty YAML |
| `test_snapshot.py` | `snapshot.py` | Save/load round-trip, SHA-256 hash determinism, parent directory auto-creation, tamper detection (modified schema, fake hash, missing hash field) |
| `test_new_features.py` | `config.py`, `logger.py`, `contract.py` (integrity) | YAML configuration file loading, per-environment profile loading & merging, default configuration merging, email environment injection, contract hashing/locking, and logging verbosity settings |

### Running specific tests
```bash
python -m pytest tests/test_new_features.py -v       # Only new features tests
python -m pytest tests/test_diff_engine.py -v        # Only diff engine tests
```

---

## 📁 Project Structure

```
schema-guard/
├── contracts/
│   └── orders.yaml                # Your data contracts
├── snapshots/                     # Baseline snapshots (auto‑created)
│   └── orders.json
├── src/schema_guard/
│   ├── __init__.py
│   ├── cli.py                     # Click CLI commands (snap, gate, lock, history)
│   ├── config.py                  # YAML config file loader and profile merger
│   ├── logger.py                  # Verbose structured logger configuration
│   ├── contract.py                # YAML parser, env resolver & integrity checks
│   ├── history.py                 # Change history audit trail DB recorder
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── base.py                # Base extractor interface & URL builder
│   │   ├── postgres.py            # PostgreSQL extractor
│   │   ├── mysql.py               # MySQL extractor
│   │   ├── snowflake.py           # Snowflake extractor
│   │   ├── sqlserver.py           # SQL Server extractor
│   │   ├── oracle.py              # Oracle extractor
│   │   └── databricks.py          # Databricks extractor
│   ├── snapshot.py                # Save/load snapshot JSON with integrity checks
│   ├── diff_engine.py             # Drift detection logic (type, nullable, PK)
│   └── alerter.py                 # SMTP email alerting
├── tests/
│   ├── test_diff_engine.py        # Drift engine tests
│   ├── test_contract.py           # Contract loader & validation tests
│   ├── test_snapshot.py           # Snapshot integrity tests
│   └── test_new_features.py       # Config, logging, and lock verification tests
├── pyproject.toml                 # Build config & DB extras definition
├── Dockerfile                     # Multi-stage lightweight CI Docker image
├── .dockerignore                  # Docker build context filters
├── schema-guard-config.example.yml # Template configuration file
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
| `Unsupported source type` | Typos in `source.type`. Supported types: `postgres`, `mysql`, `snowflake`, `sqlserver`, `oracle`, `databricks`. |
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
