import yaml
import os
import hashlib
import json
from jinja2 import Environment, BaseLoader

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

    supported_types = ["postgres", "mysql", "snowflake", "sqlserver", "oracle", "databricks"]
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


def jinja_env_var(name: str, default=None):
    """
    Jinja function to access environment variables.
    If default is not provided and the variable is missing, raises ValueError.
    """
    val = os.getenv(name)
    if val is None:
        if default is None:
            raise ValueError(f"Environment variable '{name}' not set and no default provided.")
        return default
    return val


def load_contract(path: str) -> dict:
    """
    Load and validate a contract YAML file.
    Renders the YAML text using Jinja2 (providing env_var function).
    Also supports env: prefixed values for backwards compatibility.
    """
    with open(path) as f:
        raw_content = f.read()

    # Render through Jinja2 first
    env = Environment(loader=BaseLoader())
    env.globals['env_var'] = jinja_env_var
    try:
        rendered_content = env.from_string(raw_content).render()
    except Exception as e:
        raise ValueError(f"Failed to render contract YAML via Jinja: {e}")

    cfg = yaml.safe_load(rendered_content)

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

    # Validate structure after resolving env vars
    validate_contract(resolved)

    return resolved


def hash_contract(path: str) -> str:
    """Compute a SHA-256 hash of the raw contract file bytes."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def lock_contract(path: str) -> str:
    """
    Create a .lock sidecar file for the contract.
    The lock file contains the SHA-256 hash and metadata.

    Returns the path to the lock file.
    """
    contract_hash = hash_contract(path)
    lock_path = path + ".lock"

    lock_data = {
        "contract": os.path.basename(path),
        "hash": contract_hash,
        "locked_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }

    with open(lock_path, "w") as f:
        json.dump(lock_data, f, indent=2)

    return lock_path


def verify_contract_integrity(path: str) -> bool:
    """
    Verify a contract file against its .lock sidecar.

    Returns True if the contract matches its lock.
    Raises ValueError if the lock exists and the contract has been modified.
    Returns False if no lock file exists (no verification possible).
    """
    lock_path = path + ".lock"
    if not os.path.exists(lock_path):
        return False  # No lock file — can't verify

    with open(lock_path) as f:
        lock_data = json.load(f)

    stored_hash = lock_data.get("hash")
    if not stored_hash:
        raise ValueError(f"Lock file '{lock_path}' is missing the 'hash' field.")

    current_hash = hash_contract(path)
    if current_hash != stored_hash:
        raise ValueError(
            f"Contract integrity check FAILED for '{path}'.\n"
            f"  Locked hash:  {stored_hash}\n"
            f"  Current hash: {current_hash}\n"
            "The contract file has been modified since it was locked.\n"
            "If this change is intentional, re-lock with: schema-guard lock --contract " + path
        )

    return True