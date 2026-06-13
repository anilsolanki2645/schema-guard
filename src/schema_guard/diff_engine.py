def normalize_type(t: str) -> str:
    """
    Normalize a SQL type string for case-insensitive, whitespace-insensitive comparison.
    e.g. 'NUMERIC(10, 2)' → 'numeric(10,2)'
    """
    return t.lower().replace(" ", "")


def compare_schemas(live_schema: dict, snapshot_schema: dict, contract_columns: list):
    """
    Compare live schema against snapshot and contract.
    
    Returns a tuple of (violations, notices):
      - violations: list of CRITICAL/WARNING strings that should fail the gate
      - notices: list of INFO strings for visibility (e.g. allowed drift that matched)
    """
    live_cols = {c['name']: c for c in live_schema['columns']}
    snap_cols = {c['name']: c for c in snapshot_schema['columns']}

    violations = []
    notices = []

    # --- Fix #5: Validate contract expectations against snapshot ---
    for contract_col in contract_columns:
        col_name = contract_col['name']
        if col_name in snap_cols:
            snap = snap_cols[col_name]
            # Check if snapshot matches contract expectation
            if normalize_type(str(contract_col['type'])) != normalize_type(str(snap['type'])):
                notices.append(
                    f"WARNING: Snapshot type for '{col_name}' is '{snap['type']}' "
                    f"but contract expects '{contract_col['type']}'. "
                    "The baseline snapshot may have been captured at a bad time."
                )
            if contract_col.get('nullable') is not None and contract_col['nullable'] != snap.get('nullable'):
                notices.append(
                    f"WARNING: Snapshot nullable for '{col_name}' is {snap.get('nullable')} "
                    f"but contract expects {contract_col['nullable']}. "
                    "The baseline snapshot may have been captured at a bad time."
                )

    # Check for removed columns
    for name in snap_cols:
        if name not in live_cols:
            violations.append(f"CRITICAL: Column '{name}' removed from table.")

    # Check for added columns and compare existing ones
    for name in live_cols:
        if name not in snap_cols:
            violations.append(f"WARNING: New column '{name}' added (type {live_cols[name]['type']}).")
            continue

        live = live_cols[name]
        snap = snap_cols[name]

        # Nullability change
        if live['nullable'] != snap['nullable']:
            violations.append(
                f"CRITICAL: Column '{name}' nullable changed from {snap['nullable']} to {live['nullable']}."
            )

        # --- Fix #6: Primary key change detection ---
        live_pk = live.get('primary_key', False)
        snap_pk = snap.get('primary_key', False)
        if live_pk != snap_pk:
            if snap_pk and not live_pk:
                violations.append(
                    f"CRITICAL: Column '{name}' primary key constraint DROPPED."
                )
            else:
                violations.append(
                    f"CRITICAL: Column '{name}' primary key constraint ADDED."
                )

        # --- Fix #4: Case-insensitive type comparison ---
        if normalize_type(live['type']) != normalize_type(snap['type']):
            # Check contract allowed_drift
            contract_col = next((c for c in contract_columns if c['name'] == name), None)
            if contract_col and 'allowed_drift' in contract_col:
                drift_allowed = False
                for rule in contract_col['allowed_drift']:
                    if (normalize_type(rule['from']) == normalize_type(snap['type']) and
                            normalize_type(rule['to']) == normalize_type(live['type'])):
                        drift_allowed = True
                        # --- Fix #7: Log allowed drift instead of silencing ---
                        notices.append(
                            f"INFO: Allowed drift applied — Column '{name}' type changed "
                            f"from '{snap['type']}' to '{live['type']}' (per contract rule)."
                        )
                        break
                if not drift_allowed:
                    violations.append(
                        f"CRITICAL: Column '{name}' type changed from '{snap['type']}' to '{live['type']}' (not in allowed_drift)."
                    )
            else:
                violations.append(
                    f"CRITICAL: Column '{name}' type changed from '{snap['type']}' to '{live['type']}'."
                )

    return violations, notices