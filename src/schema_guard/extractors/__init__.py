from schema_guard.extractors.postgres import PostgresExtractor
from schema_guard.extractors.mysql import MySQLExtractor
from schema_guard.extractors.snowflake import SnowflakeExtractor
from schema_guard.extractors.sqlserver import SQLServerExtractor
from schema_guard.extractors.oracle import OracleExtractor
from schema_guard.extractors.databricks import DatabricksExtractor

EXTRACTORS = {
    "postgres": PostgresExtractor,
    "mysql": MySQLExtractor,
    "snowflake": SnowflakeExtractor,
    "sqlserver": SQLServerExtractor,
    "oracle": OracleExtractor,
    "databricks": DatabricksExtractor,
}

def get_extractor(source_type: str):
    extractor_class = EXTRACTORS.get(source_type.lower())
    if not extractor_class:
        raise ValueError(f"Unsupported extractor source type: '{source_type}'")
    return extractor_class()
