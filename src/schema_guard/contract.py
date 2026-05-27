import yaml
import os

def load_contract(path):
    with open(path) as f:
        cfg = yaml.safe_load(f)

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

    return walk(cfg)