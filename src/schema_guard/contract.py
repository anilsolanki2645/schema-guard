import yaml
import os


# --- Fix #8: Required contract schema structure ---
REQUIRED_SOURCE_KEYS = ["type", "connection", "schema", "table"]
REQUIRED_COLUMN_KEYS = ["name", "type", "nullable"]


def validate_contract(cfg: dict):
    """
    Validate the contract YAML structure.
    Raises ValueError with a clear message for missing or malformed fields.
    """
    if "source" not in cfg:
        raise ValueError("Contract is missing the required 'source' section.")

    source = cfg["source"]
    if not isinstance(source, dict):
        raise ValueError("Contract 'source' must be a mapping (dict), got: " + type(source).__name__)

    for key in REQUIRED_SOURCE_KEYS:
        if key not in source:
            raise ValueError(f"Contract 'source' is missing required key: '{key}'")

    supported_types = ["postgres"]
    if source["type"] not in supported_types:
        raise ValueError(
            f"Unsupported source type: '{source['type']}'. "
            f"Supported types: {supported_types}"
        )

    # Validate columns (optional section, but if present, each entry must be well-formed)
    if "columns" in cfg:
        if not isinstance(cfg["columns"], list):
            raise ValueError("Contract 'columns' must be a list.")

        for i, col in enumerate(cfg["columns"]):
            if not isinstance(col, dict):
                raise ValueError(f"Contract column #{i+1} must be a mapping (dict).")
            for key in REQUIRED_COLUMN_KEYS:
                if key not in col:
                    raise ValueError(
                        f"Contract column #{i+1} is missing required key: '{key}'. "
                        f"Column so far: {col}"
                    )

            # Validate allowed_drift structure if present
            if "allowed_drift" in col:
                if not isinstance(col["allowed_drift"], list):
                    raise ValueError(
                        f"Contract column '{col['name']}': 'allowed_drift' must be a list."
                    )
                for j, rule in enumerate(col["allowed_drift"]):
                    if not isinstance(rule, dict) or "from" not in rule or "to" not in rule:
                        raise ValueError(
                            f"Contract column '{col['name']}': allowed_drift rule #{j+1} "
                            "must have 'from' and 'to' keys."
                        )


def load_contract(path: str) -> dict:
    """
    Load and validate a contract YAML file.
    Resolves env: prefixed values to environment variables.
    """
    with open(path) as f:
        cfg = yaml.safe_load(f)

    if cfg is None:
        raise ValueError(f"Contract file '{path}' is empty or invalid YAML.")

    def resolve_env(value):
        if isinstance(value, str) and value.startswith("env:"):
            env_var = value[4:]
            val = os.getenv(env_var)
            if val is None:
                raise ValueError(f"Environment variable '{env_var}' not set.")
            return val
        return value

    def walk(obj):
        if isinstance(obj, dict):
            return {k: walk(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [walk(item) for item in obj]
        else:
            return resolve_env(obj)

    resolved = walk(cfg)

    # --- Fix #8: Validate structure after resolving env vars ---
    validate_contract(resolved)

    return resolved