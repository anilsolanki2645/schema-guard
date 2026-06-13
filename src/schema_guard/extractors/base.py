from abc import ABC, abstractmethod
from urllib.parse import quote_plus

class BaseExtractor(ABC):
    @abstractmethod
    def get_schema(self, connection_details: dict | str, schema_name: str, table_name: str) -> dict:
        """
        Extract schema metadata from a database table.
        Returns a dict:
        {
            "table": "schema.table",
            "columns": [
                {
                    "name": "col_name",
                    "type": "col_type",
                    "nullable": True/False,
                    "primary_key": True/False
                },
                ...
            ]
        }
        """
        pass

    def make_sqlalchemy_url(self, connection_details: dict | str, default_driver: str) -> str:
        """
        Construct a SQLAlchemy connection string from connection details.
        """
        if isinstance(connection_details, str):
            return connection_details
            
        if not isinstance(connection_details, dict):
            raise ValueError("Connection details must be a string URL or a dictionary of parameters.")

        # Standard keys from db-schemachange / connections-config.yml
        user = connection_details.get("user") or connection_details.get("username") or ""
        password = connection_details.get("password") or ""
        host = connection_details.get("host") or "localhost"
        port = connection_details.get("port")
        dbname = connection_details.get("dbname") or connection_details.get("database") or ""

        user_escaped = quote_plus(str(user)) if user else ""
        password_escaped = quote_plus(str(password)) if password else ""

        userinfo = f"{user_escaped}:{password_escaped}" if password_escaped else user_escaped
        auth = f"{userinfo}@" if userinfo else ""
        port_suffix = f":{port}" if port else ""

        # Some drivers need specific schemas/queries appended, but we keep it simple for base URL
        return f"{default_driver}://{auth}{host}{port_suffix}/{dbname}"
