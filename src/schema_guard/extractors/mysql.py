from schema_guard.extractors.base import BaseExtractor
from sqlalchemy import create_engine, inspect

class MySQLExtractor(BaseExtractor):
    def get_schema(self, connection_details: dict | str, schema_name: str, table_name: str) -> dict:
        """
        Extract schema metadata from a MySQL table.
        Note: In MySQL, schema_name is usually the database/schema.
        """
        # If it is a dictionary connection, default to mysql+pymysql (commonly used pure-python driver)
        # or fallback to default mysql driver if prefix is already present.
        connection_string = self.make_sqlalchemy_url(connection_details, "mysql+pymysql")
        engine = create_engine(connection_string)
        try:
            inspector = inspect(engine)
            columns = inspector.get_columns(table_name, schema=schema_name)
            
            # Get primary key info
            pk_info = inspector.get_pk_constraint(table_name, schema=schema_name)
            pk_columns = pk_info.get('constrained_columns', [])

            schema = {
                "table": f"{schema_name}.{table_name}" if schema_name else table_name,
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
