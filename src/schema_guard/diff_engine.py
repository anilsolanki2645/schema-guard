from deepdiff import DeepDiff

def compare_schemas(live_schema: dict, snapshot_schema: dict, contract_columns: list):
    # Extract column lists for comparison (ignoring metadata)
    live_cols = {c['name']: c for c in live_schema['columns']}
    snap_cols = {c['name']: c for c in snapshot_schema['columns']}

    violations = []
    # Check for removed columns
    for name in snap_cols:
        if name not in live_cols:
            violations.append(f"CRITICAL: Column '{name}' removed from table.")
    # Check for added columns (warning unless contract says otherwise)
    for name in live_cols:
        if name not in snap_cols:
            violations.append(f"WARNING: New column '{name}' added (type {live_cols[name]['type']}).")
            continue
        # Compare type & nullability for existing columns
        live = live_cols[name]
        snap = snap_cols[name]
        # Nullability change
        if live['nullable'] != snap['nullable']:
            violations.append(
                f"CRITICAL: Column '{name}' nullable changed from {snap['nullable']} to {live['nullable']}."
            )
        # Type change
        if live['type'] != snap['type']:
            # Check contract allowed_drift
            contract_col = next((c for c in contract_columns if c['name'] == name), None)
            if contract_col and 'allowed_drift' in contract_col:
                drift_allowed = False
                for rule in contract_col['allowed_drift']:
                    if rule['from'] == snap['type'] and rule['to'] == live['type']:
                        drift_allowed = True
                        break
                if not drift_allowed:
                    violations.append(
                        f"CRITICAL: Column '{name}' type changed from {snap['type']} to {live['type']} (not allowed)."
                    )
            else:
                violations.append(
                    f"CRITICAL: Column '{name}' type changed from {snap['type']} to {live['type']}."
                )
    return violations