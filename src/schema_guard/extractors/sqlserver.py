from schema_guard.extractors.base import BaseExtractor
from sqlalchemy import create_engine, inspect


class SQLServerExtractor(BaseExtractor):
    def get_schema(self, connection_details: dict | str, schema_name: str, table_name: str) -> dict:
        """
        Extract schema metadata from a SQL Server table.
        Uses pymssql driver via SQLAlchemy.
        """
        connection_string = self.make_sqlalchemy_url(connection_details, "mssql+pymssql")
        engine = create_engine(connection_string)
        try:
            inspector = inspect(engine)
            # SQL Server uses 'dbo' as default schema
            effective_schema = schema_name or "dbo"
            columns = inspector.get_columns(table_name, schema=effective_schema)

            # Get primary key info
            pk_info = inspector.get_pk_constraint(table_name, schema=effective_schema)
            pk_columns = pk_info.get('constrained_columns', [])

            schema = {
                "table": f"{effective_schema}.{table_name}",
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
            engine.dispose()
