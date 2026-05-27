Here is a comprehensive **reference documentation** for your Schema Guard project. You can save it as `README.md` or `DOCS.md` in your repository. It covers everything from what the tool does to how to extend it.

---

```markdown
# Schema Guard 🛡️

**Catch silent schema drift before it breaks your production data pipelines.**

Schema Guard is a lightweight CLI tool that captures database schema snapshots and then acts as a CI/CD gate to block deployments when unauthorized schema changes are detected. It’s the missing guardrail for data engineers who’ve been burned by unexpected column drops, type changes, or nullability shifts.

---

## Table of Contents
- [Why Schema Guard?](#why-schema-guard)
- [Architecture Overview](#architecture-overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Command Reference](#command-reference)
- [Contract YAML Specification](#contract-yaml-specification)
- [Alerting (Email)](#alerting-email)
- [CI/CD Integration](#cicd-integration)
- [Extending with New Extractors](#extending-with-new-extractors)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Why Schema Guard?

Every data engineer knows the 2 AM incident:
- The source team adds a column, changes a type, or drops `NOT NULL` without warning.
- Your ETL pipeline doesn’t fail—it silently writes `NULL`s or corrupts downstream data.
- An executive dashboard breaks, and it takes hours to trace back to a trivial schema change.

**Schema Guard stops this at the CI gate.** You define a data contract (YAML), capture a snapshot of the real schema, and then in your deployment pipeline run `schema-guard gate`. Any drift from the contract or snapshot fails the build—*before* the change hits production.

---

## Architecture Overview

```
┌─────────────┐      ┌──────────────┐      ┌─────────────────┐
│  Contract   │──────▶│  CLI (snap)  │──────▶│  Snapshot JSON  │
│  (orders.yaml)     └──────────────┘      └─────────────────┘
│                              │
│   Live DB Schema             │
└──────────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │  CLI (gate)           │
                    │  Compares live schema  │
                    │  vs. snapshot + contract
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Diff Engine          │
                    │  Detects violations   │
                    └───────────┬───────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Alerter (email)      │
                    │  Sends notification   │
                    └───────────────────────┘
```

1. **Contract** – Describes what the source *must* look like (which columns, types, nullability, allowed drifts).
2. **Snapshot** – A frozen JSON representation of the actual schema at a trusted moment.
3. **Gate** – Compares live schema against the snapshot and contract. On drift, it logs violations, sends an email, and exits with code 1 (fails CI).

---

## Installation

From source (for development):
```bash
git clone <your-repo-url>
cd schema-guard
pip install -e .
```

Or install from PyPI (once published):
```bash
pip install schema-guard
```

### Dependencies
- Python ≥ 3.8
- `click`, `pyyaml`, `sqlalchemy`, `psycopg2-binary` (PostgreSQL), `deepdiff`, `python-dotenv`

All dependencies are installed automatically with pip.

---

## Quick Start

1. **Create a contract** for your source table (e.g., `contracts/orders.yaml`):
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

2. **Snap the current schema** (creates a baseline):
```bash
schema-guard snap --contract contracts/orders.yaml --snapshot-file snapshots/orders.json
```
Output: `✅ Snapshot saved to snapshots/orders.json`

3. **Simulate a drift** (e.g., in psql):
```sql
ALTER TABLE orders ALTER COLUMN amount DROP NOT NULL;
```

4. **Run the gate**:
```bash
schema-guard gate --contract contracts/orders.yaml --snapshot-file snapshots/orders.json
```
Output:
```
❌ Schema drift detected:
  - CRITICAL: Column 'amount' nullable changed from False to True.
```
The command exits with code 1.

---

## Configuration

Schema Guard uses environment variables (via a `.env` file) for all sensitive or environment‑specific settings.

### Database Connection
Define a PostgreSQL connection string in `.env`:
```env
DB_CONNECTION_STRING=postgresql://user:password@host:5432/dbname
```
Special characters in the password must be URL‑encoded (e.g., `@` → `%40`).

In the contract YAML, reference it with `"env:DB_CONNECTION_STRING"`. The tool’s `contract.py` automatically resolves `env:...` values.

### Email Alerting
To receive email alerts on drift, set these variables in `.env`:
```env
EMAIL_ENABLED=true
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password    # Gmail: use an App Password
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=oncall@example.com
EMAIL_SUBJECT=Schema Drift Detected
```
If `EMAIL_ENABLED` is not `true`, alerts are silently skipped. No email means the gate still works—only the notification is omitted.

For Gmail, you must enable 2‑FA and generate an **App Password**. Other SMTP providers work similarly (sendgrid, Mailgun, etc.).

---

## Command Reference

### `schema-guard snap`
Captures the current schema of the source and writes a snapshot file.

**Usage:**
```bash
schema-guard snap --contract <contract.yaml> --snapshot-file <snapshot.json>
```

**Options:**
- `--contract` (required) – Path to the contract YAML.
- `--snapshot-file` – Path for the output snapshot (default: `schema_snapshot.json`).

**Behavior:**
- Connects to the database defined in the contract.
- Inspects the table and saves column names, types, nullability, and primary key info.
- Also stores a hash and timestamp in the snapshot.

---

### `schema-guard gate`
Compares the live source schema against the snapshot and contract rules. Exits with code 1 on any violation.

**Usage:**
```bash
schema-guard gate --contract <contract.yaml> --snapshot-file <snapshot.json>
```

**Options:**
- `--contract` (required) – Path to the contract YAML.
- `--snapshot-file` – Path to the baseline snapshot (default: `schema_snapshot.json`).

**Violation types:**
- **Column removed** – CRITICAL
- **New column added** – WARNING (doesn't fail by default; can be configured)
- **Type changed** (not in allowed_drift) – CRITICAL
- **Nullable changed** – CRITICAL (unless explicitly allowed)
- **Allowed drift** – passes if the exact `from` and `to` match a rule

If violations are found, the command prints them and triggers an email alert (if configured).

---

## Contract YAML Specification

A contract file defines the expected state of a data source.

**Structure:**
```yaml
source:
  name: friendly_name           # Used in logs (optional)
  type: postgres                # Source type (currently only postgres supported)
  connection: "env:DB_CONNECTION_STRING"  # Database URL or env:VARIABLE
  schema: public                # Database schema name
  table: orders                 # Table name
  freshness_hours: 24           # (future use) max allowed snapshot age

columns:
  - name: order_id
    type: integer               # SQLAlchemy type name (e.g., "integer", "numeric(10,2)")
    nullable: false
    checks:                     # Optional: additional logical checks
      - unique_in_table         # (future: could integrate Great Expectations)
    allowed_drift:              # Optional: list of type changes that are acceptable
      - from: "numeric(10,2)"
        to: "numeric(12,2)"
```

**Column rules:**
- `name` and `type` must match exactly (case‑sensitive).
- `nullable` must match (`true`/`false`).
- If a column has `allowed_drift`, a type change is permitted only if it matches one of the listed `from`/`to` pairs. Otherwise, any type change is forbidden.

---

## Alerting (Email)

The alerting module (`alerter.py`) sends an email listing all violations. It uses environment variables for SMTP configuration. No alerting means the gate still functions; the notification is optional.

The email body looks like:
```
The following schema drift violations were detected:

• CRITICAL: Column 'amount' nullable changed from False to True.
• CRITICAL: Column 'status' type changed from character varying(20) to text.
```

If email fails to send (wrong password, network issue), a message is printed to stderr: `[alerter] Failed to send email: <reason>`. The gate still fails as expected.

---

## CI/CD Integration

### GitHub Actions Example
Place this workflow in `.github/workflows/schema-check.yml`:

```yaml
name: Schema Drift Gate
on: [push, pull_request]

jobs:
  drift-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install Schema Guard
        run: pip install schema-guard  # or pip install -e .
      - name: Run Schema Gate
        run: schema-guard gate --contract contracts/orders.yaml --snapshot-file snapshots/orders.json
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

**How it works:**
- The pipeline runs on every push and pull request.
- If the gate fails, the build turns red, preventing merge.
- Email alerts are sent to the on‑call address (if configured).

---

## Extending with New Extractors

To support a new source (e.g., Snowflake, BigQuery, S3 Parquet):

1. Create a new file in `src/schema_guard/extractors/` (e.g., `snowflake.py`).
2. Implement a function `get_schema(connection_string, schema_name, table_name)` that returns a dictionary in this format:
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
3. In `cli.py`, add an `elif` branch in the `snap` and `gate` commands to call your new extractor based on `source.type`.
4. Add any required Python package dependencies to `pyproject.toml`.

---

## Project Structure

```
schema-guard/
├── .github/workflows/
│   └── schema-check.yml          # CI pipeline example
├── contracts/                    # Store your data contract YAML files here
│   └── orders.yaml
├── snapshots/                    # Baseline snapshots (automatically created)
│   └── orders.json
├── src/schema_guard/
│   ├── __init__.py
│   ├── cli.py                    # Click CLI definition
│   ├── config.py                 # .env loader (if needed)
│   ├── contract.py               # YAML contract parser & env resolver
│   ├── extractors/
│   │   ├── __init__.py
│   │   └── postgres.py           # PostgreSQL schema inspector
│   ├── snapshot.py               # Save/load snapshot JSON
│   ├── diff_engine.py            # Drift detection logic
│   └── alerter.py                # Email alerting (SMTP)
├── pyproject.toml                # Package metadata & build config
├── .env                          # Secrets (not committed to git)
└── README.md
```

---

## Troubleshooting

| Problem | Solution |
|--------|----------|
| `FileNotFoundError: snapshots/orders.json` | Create the `snapshots/` directory or update `snapshot.py` to auto‑create it (already recommended). |
| `Could not parse SQLAlchemy URL` | The connection string is invalid. Check your `.env`/contract; ensure `env:...` is resolved. |
| `FATAL: password authentication failed` | Wrong credentials or special characters not URL‑encoded. Encode `@` as `%40`, `%` as `%25`, etc. Use `psql` to verify. |
| Email not sent | Set `EMAIL_ENABLED=true` in `.env`. Check SMTP settings and that you’re using an App Password for Gmail. Look for `[alerter]` messages in the terminal. |
| Gate passes when it shouldn’t | Ensure the snapshot file is the correct baseline. Run `snap` again after an intentional schema change. |
| `ModuleNotFoundError` when running CLI | Make sure you installed with `pip install -e .` from the project root. |

---

## License

*(Choose your license – e.g., MIT, Apache 2.0)*

---

**Built with frustration turned into code by a data engineer who just wants to sleep through the night.**
```