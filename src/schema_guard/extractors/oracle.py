from schema_guard.extractors.base import BaseExtractor
from sqlalchemy import create_engine, inspect
from urllib.parse import quote_plus


class OracleExtractor(BaseExtractor):
    def get_schema(self, connection_details: dict | str, schema_name: str, table_name: str) -> dict:
        """
        Extract schema metadata from an Oracle table.
        Uses oracledb driver via SQLAlchemy.

        Connection dict supports:
            user, password, host, port, service_name, sid
        """
        connection_string = self._build_oracle_url(connection_details)
        engine = create_engine(connection_string)
        try:
            inspector = inspect(engine)
            # Oracle schema names are typically uppercase
            effective_schema = schema_name.upper() if schema_name else None
            columns = inspector.get_columns(table_name.upper(), schema=effective_schema)

            # Get primary key info
            pk_info = inspector.get_pk_constraint(table_name.upper(), schema=effective_schema)
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

    def _build_oracle_url(self, connection_details: dict | str) -> str:
        """
        Build an Oracle SQLAlchemy connection URL.

        Supports:
            - Direct connection string
            - Dict with: user, password, host, port, service_name
            - Dict with: user, password, host, port, sid
        """
        if isinstance(connection_details, str):
            return connection_details

        if not isinstance(connection_details, dict):
            raise ValueError("Connection details must be a string URL or a dictionary of parameters.")

        user = connection_details.get("user") or connection_details.get("username") or ""
        password = connection_details.get("password") or ""
        host = connection_details.get("host") or "localhost"
        port = connection_details.get("port") or 1521
        service_name = connection_details.get("service_name")
        sid = connection_details.get("sid")

        user_escaped = quote_plus(str(user)) if user else ""
        password_escaped = quote_plus(str(password)) if password else ""

        userinfo = f"{user_escaped}:{password_escaped}" if password_escaped else user_escaped
        auth = f"{userinfo}@" if userinfo else ""

        if service_name:
            # Use service_name format
            return f"oracle+oracledb://{auth}{host}:{port}/?service_name={quote_plus(str(service_name))}"
        elif sid:
            # Use SID format
            return f"oracle+oracledb://{auth}{host}:{port}/{quote_plus(str(sid))}"
        else:
            raise ValueError("Oracle connection requires either 'service_name' or 'sid'.")
