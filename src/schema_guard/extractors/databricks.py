from schema_guard.extractors.base import BaseExtractor
from sqlalchemy import create_engine, inspect, text
from urllib.parse import quote_plus


class DatabricksExtractor(BaseExtractor):
    def get_schema(self, connection_details: dict | str, schema_name: str, table_name: str) -> dict:
        """
        Extract schema metadata from a Databricks table.
        Uses databricks-sql-connector via SQLAlchemy.

        Connection dict supports:
            server_hostname, http_path, access_token
            OR OAuth: server_hostname, http_path, client_id, client_secret
            OR username/password: server_hostname, http_path, username, password
        """
        connection_string = self._build_databricks_url(connection_details)
        engine = create_engine(connection_string)
        try:
            inspector = inspect(engine)
            columns = inspector.get_columns(table_name, schema=schema_name)

            # Get primary key info (Databricks may not support PK constraints)
            try:
                pk_info = inspector.get_pk_constraint(table_name, schema=schema_name)
                pk_columns = pk_info.get('constrained_columns', [])
            except Exception:
                pk_columns = []

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

    def _build_databricks_url(self, connection_details: dict | str) -> str:
        """
        Build a Databricks SQLAlchemy connection URL.

        Supports multiple auth methods:
        1. Access token (PAT):
            server_hostname, http_path, access_token
        2. OAuth (M2M / service principal):
            server_hostname, http_path, client_id, client_secret
            (auth_type: "oauth")
        3. Username/password:
            server_hostname, http_path, username, password

        URL format: databricks://token:{access_token}@{server_hostname}?http_path={http_path}&catalog={catalog}&schema={schema}
        """
        if isinstance(connection_details, str):
            return connection_details

        if not isinstance(connection_details, dict):
            raise ValueError("Connection details must be a string URL or a dictionary of parameters.")

        server_hostname = connection_details.get("server_hostname", "")
        http_path = connection_details.get("http_path", "")
        catalog = connection_details.get("catalog")
        schema = connection_details.get("schema")
        auth_type = connection_details.get("auth_type", "").lower()

        if not server_hostname:
            raise ValueError("Databricks connection requires 'server_hostname'.")
        if not http_path:
            raise ValueError("Databricks connection requires 'http_path'.")

        # Build query parameters
        params = [f"http_path={quote_plus(str(http_path))}"]
        if catalog:
            params.append(f"catalog={quote_plus(str(catalog))}")
        if schema:
            params.append(f"schema={quote_plus(str(schema))}")

        # Determine auth method
        if auth_type == "oauth" or connection_details.get("client_id"):
            # OAuth / Service Principal (M2M)
            client_id = connection_details.get("client_id", "")
            client_secret = connection_details.get("client_secret", "")
            if not client_id or not client_secret:
                raise ValueError("OAuth auth requires 'client_id' and 'client_secret'.")

            params.append("auth_type=databricks-oauth")
            params.append(f"client_id={quote_plus(str(client_id))}")
            params.append(f"client_secret={quote_plus(str(client_secret))}")

            return f"databricks://token:oauth@{server_hostname}?{'&'.join(params)}"

        elif connection_details.get("access_token"):
            # Personal Access Token (PAT)
            access_token = connection_details["access_token"]
            return f"databricks://token:{quote_plus(str(access_token))}@{server_hostname}?{'&'.join(params)}"

        elif connection_details.get("username") and connection_details.get("password"):
            # Username/password auth
            username = quote_plus(str(connection_details["username"]))
            password = quote_plus(str(connection_details["password"]))
            return f"databricks://{username}:{password}@{server_hostname}?{'&'.join(params)}"

        else:
            raise ValueError(
                "Databricks connection requires one of: "
                "'access_token' (PAT), 'client_id'+'client_secret' (OAuth), "
                "or 'username'+'password'."
            )
