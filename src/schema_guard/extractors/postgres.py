from sqlalchemy import create_engine, inspect
import logging


def get_schema(connection_string: str, schema_name: str, table_name: str) -> dict:
    """
    Extract schema metadata from a PostgreSQL table.
    Returns a dict with table name and column details.
    """
    engine = create_engine(connection_string)
    try:
        inspector = inspect(engine)
        columns = inspector.get_columns(table_name, schema=schema_name)
        # Also get primary key info
        pk_info = inspector.get_pk_constraint(table_name, schema=schema_name)
        pk_columns = pk_info.get('constrained_columns', [])

        schema = {
            "table": f"{schema_name}.{table_name}",
            "columns": []
        }
        for col in columns:
            schema["columns"].append({
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
                "primary_key": col["name"] in pk_columns
            })
        return schema
    finally:
        # --- Fix #9: Always dispose engine to prevent connection leaks ---
        engine.dispose()