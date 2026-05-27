```markdown
# 🛡️ Schema Guard

**Stop silent schema drift before it breaks your production data pipelines.**

Schema Guard is a lightweight CLI tool that captures database schema snapshots and acts as a CI/CD gate, blocking deployments when unauthorized schema changes are detected. It’s the missing guardrail for data engineers who’ve been burned by unexpected column drops, type changes, or nullability shifts.

---

## Why Schema Guard?

Every data engineer knows the 2 AM nightmare:
- A source team adds a column, changes a type, or drops a `NOT NULL` without notice.
- Your ETL pipeline doesn’t fail—it silently writes `NULL`s or corrupts downstream data.
- Executive dashboards break, and you spend hours tracing the issue back to a trivial schema change.

Schema Guard stops this at the CI gate. You define a **data contract** (YAML), capture a trusted **schema snapshot**, and then in your deployment pipeline, `schema-guard gate` compares the live source against the snapshot and contract. Any drift fails the build *before* it hits production.

---

## 🧠 Architecture Overview

```
┌─────────────────┐      ┌──────────────┐      ┌─────────────────┐
│  Contract       │──────▶│  CLI (snap)  │──────▶│  Snapshot JSON  │
│  (orders.yaml)  │      └──────────────┘      └─────────────────┘
│                 │                │
│  Live Database  │                │
└─────────────────┘                │
                                  │
                      ┌───────────▼───────────┐
                      │  CLI (gate)           │
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
2. **Snapshot** – A frozen JSON representation of the real schema at a trusted point in time.  
3. **Gate** – Compares live schema to snapshot + contract. If drift is detected, it logs violations, sends an email, and exits with code 1 to fail the CI pipeline.

---

## 🚀 Installation

### From source (for development)
```bash
git clone https://github.com/your-username/schema-guard.git
cd schema-guard
pip install -e .
```

### From PyPI (once published)
```bash
pip install schema-guard
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

### 3. Set up environment variables – `.env`
```env
DB_CONNECTION_STRING=postgresql://postgres:Abc%402645@localhost:5432/schema_guard
```
(Note: special characters must be URL‑encoded, e.g., `@` → `%40`)

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
The tool’s `contract.py` resolves any value beginning with `env:` to the corresponding environment variable.

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
schema-guard snap --contract <contract.yaml> --snapshot-file <snapshot.json>
```
- Connects to the source defined in the contract.
- Inspects the table and saves column metadata (name, type, nullable, primary key) along with a hash and timestamp.

### `gate` – check for drift
```bash
schema-guard gate --contract <contract.yaml> --snapshot-file <snapshot.json>
```
- Extracts the current live schema.
- Loads the snapshot and compares against the contract rules.
- Returns exit code 0 if all is well, 1 if any violation is found.
- **Violation types:** column removed (CRITICAL), new column added (WARNING), type changed (CRITICAL, unless allowed_drift), nullable change (CRITICAL).
- On violation, prints the diff and triggers email alert (if enabled).

---

## 🧱 Contract YAML Specification

A contract file defines the expected state of a data source.

```yaml
source:
  name: friendly_name           # Used in logs (optional)
  type: postgres                # Source type (currently only postgres supported)
  connection: "env:DB_CONNECTION_STRING"  # Database URL or env:VARIABLE
  schema: public                # Database schema
  table: orders                 # Table name
  freshness_hours: 24           # (future use)

columns:
  - name: order_id
    type: integer               # Use the exact SQLAlchemy type string
    nullable: false
    checks:                     # Optional
      - unique_in_table
    allowed_drift:              # Optional type changes allowed without alert
      - from: "numeric(10,2)"
        to: "numeric(12,2)"
```

- **`name`** and **`type`** must match the live schema exactly (case‑sensitive).  
- **`nullable`** must be `true` or `false`.  
- If a column has **`allowed_drift`**, a type change passes only if it matches one of the listed `from`/`to` pairs.

---

## 🔔 Alerting (Email)

The `alerter.py` module sends an email with the list of violations. Uses Python’s `smtplib` and `email` libraries (no extra deps).  
If the email fails (wrong password, network issue), the error is printed to stderr as `[alerter] Failed to send email: ...`, but the gate still fails as expected.

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
        run: pip install -e .            # or pip install schema-guard
      - name: Run schema gate
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

Store these values as [GitHub Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets).  
Now every push and pull request will be checked for schema drift automatically.

---

## 📁 Project Structure

```
schema-guard/
├── .github/workflows/
│   └── schema-check.yml
├── contracts/
│   └── orders.yaml                # Your data contracts
├── snapshots/                     # Baseline snapshots (auto‑created)
│   └── orders.json
├── src/schema_guard/
│   ├── __init__.py
│   ├── cli.py                     # Click CLI (snap & gate)
│   ├── config.py                  # (optional) connection helpers
│   ├── contract.py                # YAML parser & env resolver
│   ├── extractors/
│   │   ├── __init__.py
│   │   └── postgres.py            # PostgreSQL schema inspector
│   ├── snapshot.py                # Save/load snapshot JSON
│   ├── diff_engine.py             # Drift detection logic
│   └── alerter.py                 # SMTP email alerting
├── pyproject.toml                 # Build & packaging config
├── .gitignore
├── .env                           # Secrets (never commit)
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

## 🧪 Troubleshooting

| Problem | Solution |
|--------|----------|
| `FileNotFoundError: snapshots/orders.json` | Create the `snapshots/` directory or update `snapshot.py` to auto‑create it (already done in recent versions). |
| `Could not parse SQLAlchemy URL` | The connection string is invalid. Check `.env` and contract; ensure `env:` placeholders resolve correctly. |
| `FATAL: password authentication failed` | Wrong credentials or special characters not URL‑encoded. Encode `@` as `%40`, `%` as `%25`, etc. Test with `psql`. |
| Email not sent | Set `EMAIL_ENABLED=true`. Use an App Password for Gmail. Look for `[alerter]` messages in terminal. |
| Gate passes when it shouldn’t | Ensure the snapshot file is the correct baseline. Re‑run `snap` after any intentional schema change. |
| `ModuleNotFoundError` when running CLI | Run `pip install -e .` from the project root. |

---

## 📜 License

Schema Guard is open‑source under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

**Built with frustration turned into code by a data engineer who just wants to sleep through the night.** ✨
```

That README is ready to drop into your repository. It explains the problem, provides a full walkthrough, includes a working example, and covers every part of your tool—from configuration to CI/CD. Let me know when you want the next piece.
