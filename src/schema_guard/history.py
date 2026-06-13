import json
from datetime import datetime, timezone
from sqlalchemy import create_engine, text, MetaData, Table, Column, String, Integer, DateTime, Text


# DDL for the change history table
CHANGE_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS {schema}.{table} (
    id              SERIAL PRIMARY KEY,
    run_timestamp   TIMESTAMP NOT NULL,
    contract_path   VARCHAR(500) NOT NULL,
    snapshot_path   VARCHAR(500) NOT NULL,
    result          VARCHAR(20) NOT NULL,
    violations_count INTEGER NOT NULL DEFAULT 0,
    notices_count   INTEGER NOT NULL DEFAULT 0,
    violations      TEXT,
    notices         TEXT,
    dry_run         BOOLEAN NOT NULL DEFAULT FALSE,
    profile         VARCHAR(100),
    source_type     VARCHAR(50),
    source_table    VARCHAR(500)
);
"""


class ChangeHistory:
    """
    Records gate results to a database table for audit/compliance purposes.

    Usage:
        history = ChangeHistory(connection_string, schema='public', table='schema_guard_history')
        history.ensure_table_exists()
        history.record(contract_path, snapshot_path, result, violations, notices, ...)
        recent = history.get_recent(n=10)
    """

    def __init__(self, connection_string: str, schema: str = "public",
                 table: str = "schema_guard_history"):
        self.connection_string = connection_string
        self.schema = schema
        self.table = table
        self.engine = create_engine(connection_string)

    def ensure_table_exists(self):
        """Create the change history table if it does not exist."""
        ddl = CHANGE_HISTORY_DDL.format(schema=self.schema, table=self.table)
        with self.engine.connect() as conn:
            conn.execute(text(ddl))
            conn.commit()

    def record(self, contract_path: str, snapshot_path: str, result: str,
               violations: list = None, notices: list = None,
               dry_run: bool = False, profile: str = None,
               source_type: str = None, source_table: str = None):
        """
        Record a gate run result.

        Args:
            contract_path: Path to the contract YAML file used
            snapshot_path: Path to the snapshot file used
            result: 'PASS' or 'FAIL'
            violations: List of violation strings
            notices: List of notice strings
            dry_run: Whether this was a dry run
            profile: Active config profile name
            source_type: Database source type (postgres, mysql, etc.)
            source_table: Full table name (schema.table)
        """
        violations = violations or []
        notices = notices or []

        insert_sql = text(f"""
            INSERT INTO {self.schema}.{self.table}
                (run_timestamp, contract_path, snapshot_path, result,
                 violations_count, notices_count, violations, notices,
                 dry_run, profile, source_type, source_table)
            VALUES
                (:run_timestamp, :contract_path, :snapshot_path, :result,
                 :violations_count, :notices_count, :violations, :notices,
                 :dry_run, :profile, :source_type, :source_table)
        """)

        with self.engine.connect() as conn:
            conn.execute(insert_sql, {
                "run_timestamp": datetime.now(timezone.utc),
                "contract_path": contract_path,
                "snapshot_path": snapshot_path,
                "result": result,
                "violations_count": len(violations),
                "notices_count": len(notices),
                "violations": json.dumps(violations) if violations else None,
                "notices": json.dumps(notices) if notices else None,
                "dry_run": dry_run,
                "profile": profile,
                "source_type": source_type,
                "source_table": source_table,
            })
            conn.commit()

    def get_recent(self, n: int = 10) -> list:
        """
        Retrieve the most recent N gate run records.

        Returns a list of dicts with run details.
        """
        query = text(f"""
            SELECT id, run_timestamp, contract_path, snapshot_path, result,
                   violations_count, notices_count, violations, notices,
                   dry_run, profile, source_type, source_table
            FROM {self.schema}.{self.table}
            ORDER BY run_timestamp DESC
            LIMIT :limit
        """)

        with self.engine.connect() as conn:
            result = conn.execute(query, {"limit": n})
            rows = []
            for row in result:
                row_dict = dict(row._mapping)
                # Parse JSON fields back to lists
                if row_dict.get("violations"):
                    row_dict["violations"] = json.loads(row_dict["violations"])
                if row_dict.get("notices"):
                    row_dict["notices"] = json.loads(row_dict["notices"])
                rows.append(row_dict)
            return rows

    def dispose(self):
        """Dispose the database engine connection pool."""
        self.engine.dispose()
