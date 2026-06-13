from schema_guard.extractors.base import BaseExtractor
from sqlalchemy import create_engine, inspect
from urllib.parse import quote_plus


class SnowflakeExtractor(BaseExtractor):
    def get_schema(self, connection_details: dict | str, schema_name: str, table_name: str) -> dict:
        """
        Extract schema metadata from a Snowflake table.
        Supports both connection string and dict-based connection details.
        """
        connection_string = self._build_snowflake_url(connection_details)
        engine = create_engine(connection_string)
        try:
            inspector = inspect(engine)
            columns = inspector.get_columns(table_name, schema=schema_name)

            # Get primary key info
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
            engine.dispose()

    def _build_snowflake_url(self, connection_details: dict | str) -> str:
        """
        Build a Snowflake SQLAlchemy connection URL.

        String format: snowflake://{user}:{password}@{account}/{database}/{schema}?warehouse={warehouse}&role={role}
        Dict keys: account, user, password, database, schema, warehouse, role
        """
        if isinstance(connection_details, str):
            return connection_details

        if not isinstance(connection_details, dict):
            raise ValueError("Connection details must be a string URL or a dictionary of parameters.")

        account = connection_details.get("account", "")
        user = connection_details.get("user") or connection_details.get("username") or ""
        password = connection_details.get("password") or ""
        database = connection_details.get("database") or ""
        schema = connection_details.get("schema") or ""
        warehouse = connection_details.get("warehouse") or ""
        role = connection_details.get("role") or ""

        user_escaped = quote_plus(str(user)) if user else ""
        password_escaped = quote_plus(str(password)) if password else ""

        userinfo = f"{user_escaped}:{password_escaped}" if password_escaped else user_escaped
        auth = f"{userinfo}@" if userinfo else ""

        url = f"snowflake://{auth}{account}/{database}/{schema}"

        # Add query parameters for warehouse and role
        params = []
        if warehouse:
            params.append(f"warehouse={quote_plus(str(warehouse))}")
        if role:
            params.append(f"role={quote_plus(str(role))}")
        if params:
            url += "?" + "&".join(params)

        return url
