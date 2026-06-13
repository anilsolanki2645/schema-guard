import os
import yaml
from jinja2 import Environment, BaseLoader


# Default config file name
DEFAULT_CONFIG_FILE = "schema-guard-config.yml"


def _render_yaml_with_jinja(raw_content: str) -> str:
    """Render YAML content through Jinja2 for env_var support."""
    env = Environment(loader=BaseLoader())

    def env_var(name: str, default=None):
        val = os.getenv(name)
        if val is None:
            if default is None:
                raise ValueError(f"Environment variable '{name}' not set and no default provided.")
            return default
        return val

    env.globals['env_var'] = env_var
    return env.from_string(raw_content).render()


def load_config(config_path: str = None) -> dict:
    """
    Load a schema-guard YAML config file.

    Supports:
    - Flat key-value structure
    - Per-environment profiles (dev, staging, prod) with a top-level 'profile' key
    - Jinja2 templating with env_var() function

    Returns a flat dict of resolved configuration values.
    """
    if config_path is None:
        # Auto-detect default config file in cwd
        if os.path.exists(DEFAULT_CONFIG_FILE):
            config_path = DEFAULT_CONFIG_FILE
        else:
            return {}  # No config file found — return empty

    if not os.path.exists(config_path):
        return {}

    with open(config_path) as f:
        raw_content = f.read()

    # Render through Jinja2
    try:
        rendered_content = _render_yaml_with_jinja(raw_content)
    except Exception as e:
        raise ValueError(f"Failed to render config YAML via Jinja: {e}")

    cfg = yaml.safe_load(rendered_content)
    if cfg is None:
        return {}

    # Handle per-environment profiles
    active_profile = os.getenv("SCHEMA_GUARD_PROFILE") or cfg.get("profile")
    if active_profile and "profiles" in cfg:
        profiles = cfg.get("profiles", {})
        if active_profile not in profiles:
            raise ValueError(
                f"Profile '{active_profile}' not found in config. "
                f"Available profiles: {list(profiles.keys())}"
            )
        # Merge: base config + profile overrides
        profile_cfg = profiles[active_profile]
        # Remove profiles and profile key from base
        base = {k: v for k, v in cfg.items() if k not in ("profiles", "profile")}
        base.update(profile_cfg)
        return base

    # Flat config — remove profiles section if present but no profile selected
    return {k: v for k, v in cfg.items() if k != "profiles"}


def merge_config(cli_args: dict, config: dict) -> dict:
    """
    Merge CLI arguments with config file values.
    CLI arguments take priority over config file.

    Args:
        cli_args: Dict of CLI argument values (may contain None for unset args)
        config: Dict from load_config()

    Returns:
        Merged dict with CLI args overriding config values.
    """
    merged = dict(config)

    # Map CLI arg names to config file keys (handle naming differences)
    key_mapping = {
        "contract": "contract",
        "snapshot_file": "snapshot-file",
        "require_alert": "require-alert",
        "dry_run": "dry-run",
        "verbose": "verbose",
        "config": "config",
    }

    for cli_key, config_key in key_mapping.items():
        cli_value = cli_args.get(cli_key)
        if cli_value is not None and cli_value is not False:
            # CLI provided a value — it takes priority
            merged[config_key] = cli_value
        elif config_key not in merged:
            # Neither CLI nor config has this value
            if cli_value is not None:
                merged[config_key] = cli_value

    return merged


def apply_email_config(config: dict):
    """
    If the config file has an 'email' block, set the corresponding
    EMAIL_* environment variables (only if not already set).
    This allows config-file-based email settings without .env.
    """
    email_cfg = config.get("email", {})
    if not isinstance(email_cfg, dict):
        return

    mapping = {
        "enabled": "EMAIL_ENABLED",
        "host": "EMAIL_HOST",
        "port": "EMAIL_PORT",
        "user": "EMAIL_USER",
        "password": "EMAIL_PASSWORD",
        "from": "EMAIL_FROM",
        "to": "EMAIL_TO",
        "subject": "EMAIL_SUBJECT",
    }

    for yaml_key, env_key in mapping.items():
        value = email_cfg.get(yaml_key)
        if value is not None and not os.getenv(env_key):
            os.environ[env_key] = str(value)
