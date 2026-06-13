import click
import sys
import os
import json
from schema_guard.extractors import get_extractor
from schema_guard.contract import load_contract, verify_contract_integrity, lock_contract as do_lock_contract, validate_contract
from schema_guard.snapshot import capture_snapshot, load_snapshot
from schema_guard.diff_engine import compare_schemas
from schema_guard.alerter import send_email_alert
from schema_guard.masking import mask_secrets
from schema_guard.logger import setup_logger, get_logger
from schema_guard.config import load_config, merge_config, apply_email_config
from schema_guard.history import ChangeHistory

from dotenv import load_dotenv
load_dotenv()


def _try_record_history(config, contract_path, snapshot_path, result,
                        violations, notices, dry_run, source_type, source_table, logger):
    """Record gate result to change history table if configured."""
    history_conn = os.getenv("HISTORY_CONNECTION_STRING") or config.get("history-connection")
    if not history_conn:
        logger.debug("No HISTORY_CONNECTION_STRING set — skipping history recording.")
        return

    try:
        history_schema = os.getenv("HISTORY_SCHEMA") or config.get("history-schema", "public")
        history_table = os.getenv("HISTORY_TABLE") or config.get("history-table", "schema_guard_history")
        profile = os.getenv("SCHEMA_GUARD_PROFILE") or config.get("profile")

        logger.debug(f"Recording gate result to {history_schema}.{history_table}...")
        history = ChangeHistory(history_conn, schema=history_schema, table=history_table)
        history.ensure_table_exists()
        history.record(
            contract_path=contract_path,
            snapshot_path=snapshot_path,
            result=result,
            violations=violations,
            notices=notices,
            dry_run=dry_run,
            profile=profile,
            source_type=source_type,
            source_table=source_table,
        )
        history.dispose()
        logger.debug("Gate result recorded to history table.")
    except Exception as e:
        logger.debug(f"Failed to record history: {e}")
        click.echo(f"[history] Warning: Failed to record gate result: {e}", err=True)


def _resolve_option(cli_value, config, key, default=None):
    """Resolve an option value: CLI arg > config file > default."""
    if cli_value is not None and cli_value is not False and cli_value != default:
        return cli_value
    return config.get(key, default)


@click.group()
def cli():
    """Schema Guard - protect your data pipelines from silent schema drift."""


@cli.command()
@click.option('--contract', required=False, help='Path to contract YAML file')
@click.option('--snapshot-file', default=None, help='Where to save the snapshot')
@click.option('--force', is_flag=True, default=False, help='Overwrite existing snapshot without confirmation')
@click.option('--verbose', '-v', is_flag=True, default=False, help='Enable verbose debug output')
@click.option('--config', '-c', 'config_file', default=None, help='Path to schema-guard config YAML file')
def snap(contract, snapshot_file, force, verbose, config_file):
    """Capture a schema snapshot from the source defined in the contract."""
    # Load config file and merge with CLI args
    file_config = load_config(config_file)
    apply_email_config(file_config)

    contract = _resolve_option(contract, file_config, 'contract')
    snapshot_file = _resolve_option(snapshot_file, file_config, 'snapshot-file', 'schema_snapshot.json')
    verbose = verbose or file_config.get('verbose', False)

    if not contract:
        click.echo("Error: --contract is required (or set 'contract' in config file).", err=True)
        sys.exit(1)

    logger = setup_logger(verbose)
    logger.debug(f"Loading contract from: {contract}")
    cfg = load_contract(contract)
    logger.debug(f"Contract loaded — source type: {cfg['source']['type']}, "
                 f"table: {cfg['source'].get('schema', '')}.{cfg['source'].get('table', '')}")

    # --- Protect against silent overwrites ---
    if os.path.exists(snapshot_file) and not force:
        click.echo(f"⚠️  Snapshot already exists: {snapshot_file}")
        click.echo("   Use --force to overwrite the existing baseline.")
        click.echo("   This is a safety measure to prevent accidental baseline drift.")

        # Show a quick summary of what would change
        try:
            old_snapshot = load_snapshot(snapshot_file)
            old_cols = {c['name'] for c in old_snapshot['schema']['columns']}

            # Fetch live schema to show diff
            extractor = get_extractor(cfg['source']['type'])
            live = extractor.get_schema(
                cfg['source']['connection'],
                cfg['source']['schema'],
                cfg['source']['table']
            )
            live_cols = {c['name'] for c in live['columns']}
            added = live_cols - old_cols
            removed = old_cols - live_cols
            if added or removed:
                click.echo("\n   Changes detected:")
                for c in added:
                    click.echo(f"     + Column '{c}' (new)")
                for c in removed:
                    click.echo(f"     - Column '{c}' (removed)")
            else:
                click.echo("\n   No structural column changes detected (types/nullable may differ).")
        except Exception:
            pass  # If we can't show a diff, that's fine — the safety gate still holds

        sys.exit(1)

    logger.debug(f"Creating extractor for source type: {cfg['source']['type']}")
    try:
        extractor = get_extractor(cfg['source']['type'])
        logger.debug("Connecting to database and fetching schema...")
        schema = extractor.get_schema(
            cfg['source']['connection'],
            cfg['source']['schema'],
            cfg['source']['table']
        )
        logger.debug(f"Schema fetched — {len(schema.get('columns', []))} columns found")
        for col in schema.get('columns', []):
            logger.debug(f"  Column: {col['name']} | type: {col['type']} | "
                         f"nullable: {col.get('nullable')} | pk: {col.get('primary_key')}")
    except Exception as e:
        click.echo(f"Error fetching schema: {mask_secrets(str(e))}", err=True)
        sys.exit(1)

    logger.debug(f"Saving snapshot to: {snapshot_file}")
    capture_snapshot(schema, snapshot_file)
    click.echo(f"✅ Snapshot saved to {snapshot_file}")


@cli.command()
@click.option('--contract', required=False, help='Path to contract YAML file')
@click.option('--snapshot-file', default=None, help='Baseline snapshot to compare against')
@click.option('--require-alert', is_flag=True, default=False, help='Exit with code 2 if email alert fails to send')
@click.option('--dry-run', is_flag=True, default=False, help='Preview drift results without failing CI or sending alerts')
@click.option('--verbose', '-v', is_flag=True, default=False, help='Enable verbose debug output')
@click.option('--config', '-c', 'config_file', default=None, help='Path to schema-guard config YAML file')
def gate(contract, snapshot_file, require_alert, dry_run, verbose, config_file):
    """Check current schema against snapshot and contract. Exit non-zero on violations."""
    # Load config file and merge with CLI args
    file_config = load_config(config_file)
    apply_email_config(file_config)

    contract = _resolve_option(contract, file_config, 'contract')
    snapshot_file = _resolve_option(snapshot_file, file_config, 'snapshot-file', 'schema_snapshot.json')
    verbose = verbose or file_config.get('verbose', False)
    dry_run = dry_run or file_config.get('dry-run', False)
    require_alert = require_alert or file_config.get('require-alert', False)

    if not contract:
        click.echo("Error: --contract is required (or set 'contract' in config file).", err=True)
        sys.exit(1)

    logger = setup_logger(verbose)

    # Verify contract integrity if a .lock file exists
    try:
        if verify_contract_integrity(contract):
            logger.debug(f"Contract integrity verified against lock file.")
    except ValueError as e:
        click.echo(f"❌ {e}", err=True)
        if not dry_run:
            sys.exit(4)
        click.echo("[DRY RUN] Contract integrity failure would block gate in normal mode.")
    logger.debug(f"Loading contract from: {contract}")
    cfg = load_contract(contract)
    logger.debug(f"Contract loaded — source type: {cfg['source']['type']}, "
                 f"table: {cfg['source'].get('schema', '')}.{cfg['source'].get('table', '')}")
    if cfg.get('columns'):
        logger.debug(f"Contract defines {len(cfg['columns'])} expected column(s)")
        for col in cfg['columns']:
            drift_info = f", allowed_drift: {len(col.get('allowed_drift', []))} rule(s)" if 'allowed_drift' in col else ""
            logger.debug(f"  Expected: {col['name']} | type: {col['type']} | nullable: {col['nullable']}{drift_info}")

    if dry_run:
        click.echo("[DRY RUN] Running schema gate in preview mode (will not fail CI or send alerts).")

    logger.debug(f"Creating extractor for source type: {cfg['source']['type']}")
    try:
        extractor = get_extractor(cfg['source']['type'])
        logger.debug("Connecting to database and fetching live schema...")
        live_schema = extractor.get_schema(
            cfg['source']['connection'],
            cfg['source']['schema'],
            cfg['source']['table']
        )
        logger.debug(f"Live schema fetched — {len(live_schema.get('columns', []))} columns found")
        for col in live_schema.get('columns', []):
            logger.debug(f"  Live: {col['name']} | type: {col['type']} | "
                         f"nullable: {col.get('nullable')} | pk: {col.get('primary_key')}")
    except Exception as e:
        click.echo(f"Error fetching live schema: {mask_secrets(str(e))}", err=True)
        if dry_run:
            sys.exit(0)
        sys.exit(2)

    logger.debug(f"Loading baseline snapshot from: {snapshot_file}")
    try:
        snapshot = load_snapshot(snapshot_file)
        logger.debug(f"Snapshot loaded — captured at: {snapshot.get('captured_at', 'unknown')}, "
                     f"hash: {snapshot.get('hash', 'n/a')[:16]}...")
        logger.debug(f"Snapshot contains {len(snapshot['schema'].get('columns', []))} column(s)")
    except ValueError as e:
        click.echo(f"❌ {e}", err=True)
        if dry_run:
            sys.exit(0)
        sys.exit(3)

    logger.debug("Comparing live schema against snapshot + contract...")
    violations, notices = compare_schemas(live_schema, snapshot['schema'], cfg.get('columns', []))
    logger.debug(f"Comparison complete — {len(violations)} violation(s), {len(notices)} notice(s)")

    # Print notices (non-blocking) for visibility
    if notices:
        prefix = "[DRY RUN] " if dry_run else ""
        click.echo(f"{prefix}ℹ️  Notices:")
        for n in notices:
            click.echo(f"  - {n}")

    # Determine result and source info for history
    source_type = cfg['source']['type']
    source_table = f"{cfg['source'].get('schema', '')}.{cfg['source'].get('table', '')}"

    if violations:
        prefix = "[DRY RUN] " if dry_run else ""
        click.echo(f"{prefix}❌ Schema drift detected:")
        for v in violations:
            click.echo(f"  - {v}")

        # Record to history
        _try_record_history(file_config, contract, snapshot_file, "FAIL",
                            violations, notices, dry_run, source_type, source_table, logger)

        if dry_run:
            click.echo(f"\n[DRY RUN] {len(violations)} violation(s) found. In normal mode, this would fail CI with exit code 1.")
            sys.exit(0)

        # Send alert (only in non-dry-run mode)
        logger.debug("Sending email alert...")
        alert_sent = send_email_alert(violations)
        if require_alert and not alert_sent:
            click.echo("❌ Email alert failed to send (--require-alert is set).", err=True)
            sys.exit(2)
        logger.debug(f"Email alert {'sent successfully' if alert_sent else 'skipped or failed'}")

        sys.exit(1)  # fails CI
    else:
        prefix = "[DRY RUN] " if dry_run else ""
        click.echo(f"{prefix}✅ Schema matches snapshot. No drift.")

        # Record to history
        _try_record_history(file_config, contract, snapshot_file, "PASS",
                            [], notices, dry_run, source_type, source_table, logger)


@cli.command()
@click.option('--limit', '-n', default=10, help='Number of recent records to show')
@click.option('--verbose', '-v', is_flag=True, default=False, help='Enable verbose debug output')
@click.option('--config', '-c', 'config_file', default=None, help='Path to schema-guard config YAML file')
def history(limit, verbose, config_file):
    """View recent gate run history from the audit trail."""
    logger = setup_logger(verbose)
    file_config = load_config(config_file)

    history_conn = os.getenv("HISTORY_CONNECTION_STRING") or file_config.get("history-connection")
    if not history_conn:
        click.echo("Error: HISTORY_CONNECTION_STRING not set. Set it in .env or config file (history-connection).", err=True)
        sys.exit(1)

    history_schema = os.getenv("HISTORY_SCHEMA") or file_config.get("history-schema", "public")
    history_table = os.getenv("HISTORY_TABLE") or file_config.get("history-table", "schema_guard_history")

    try:
        hist = ChangeHistory(history_conn, schema=history_schema, table=history_table)
        records = hist.get_recent(n=limit)
        hist.dispose()
    except Exception as e:
        click.echo(f"Error reading history: {mask_secrets(str(e))}", err=True)
        sys.exit(1)

    if not records:
        click.echo("No gate history records found.")
        return

    click.echo(f"📋 Last {len(records)} gate run(s):\n")
    for r in records:
        ts = r.get('run_timestamp', 'unknown')
        result = r.get('result', '?')
        icon = "✅" if result == "PASS" else "❌"
        dry = " [DRY RUN]" if r.get('dry_run') else ""
        profile = f" [{r['profile']}]" if r.get('profile') else ""
        violations_n = r.get('violations_count', 0)
        click.echo(f"  {icon} {ts} | {result}{dry}{profile} | "
                   f"contract: {r.get('contract_path', '?')} | "
                   f"violations: {violations_n}")
        if verbose and violations_n > 0 and r.get('violations'):
            for v in r['violations']:
                click.echo(f"       - {v}")


@cli.command()
@click.option('--contract', required=True, help='Path to contract YAML file to lock')
@click.option('--verbose', '-v', is_flag=True, default=False, help='Enable verbose debug output')
def lock(contract, verbose):
    """Lock a contract file by creating a .lock sidecar with SHA-256 hash."""
    logger = setup_logger(verbose)

    if not os.path.exists(contract):
        click.echo(f"Error: Contract file not found: {contract}", err=True)
        sys.exit(1)

    logger.debug(f"Computing SHA-256 hash for: {contract}")
    lock_path = do_lock_contract(contract)
    click.echo(f"🔒 Contract locked: {lock_path}")
    click.echo(f"   The gate command will now verify this contract has not been modified.")
    click.echo(f"   To update the lock after intentional changes, run this command again.")


@cli.command()
@click.option('--type', '-t', default=None, help='Database source type (postgres, mysql, snowflake, sqlserver, oracle, databricks)')
@click.option('--connection', '--conn', default=None, help='Connection string, JSON string, or env:VAR reference')
@click.option('--schema', '-s', default=None, help='Database schema name')
@click.option('--table', '--tbl', default=None, help='Database table name')
@click.option('--output', '-o', default=None, help='Path to output contract YAML file')
@click.option('--force', '-f', is_flag=True, default=False, help='Overwrite output file if it exists')
@click.option('--verbose', '-v', is_flag=True, default=False, help='Enable verbose debug output')
def generate(type, connection, schema, table, output, force, verbose):
    """Automatically generate a contract YAML file from a live database table."""
    # Interactive prompting for missing options
    if not type:
        type = click.prompt(
            "Select database type",
            type=click.Choice(['postgres', 'mysql', 'snowflake', 'sqlserver', 'oracle', 'databricks'], case_sensitive=False)
        )

    if not connection:
        connection = click.prompt("Enter connection details (string, JSON dict, or env:VAR)")

    if not schema:
        default_schemas = {
            "postgres": "public",
            "mysql": "public",
            "snowflake": "PUBLIC",
            "sqlserver": "dbo",
            "oracle": "public",
            "databricks": "default"
        }
        default_sch = default_schemas.get(type.lower(), "public")
        schema = click.prompt("Enter schema name", default=default_sch)

    if not table:
        table = click.prompt("Enter table name")

    if not output:
        default_out = f"contracts/{table}.yaml"
        output = click.prompt("Enter output contract file path", default=default_out)

    logger = setup_logger(verbose)

    # Check if output file exists and handle force flag / interactive confirmation
    if os.path.exists(output) and not force:
        if click.confirm(f"Output file '{output}' already exists. Overwrite?", default=False):
            force = True
        else:
            click.echo("Aborted.", err=True)
            sys.exit(1)

    logger.debug("Resolving connection details...")

    # Resolve env reference
    resolved_conn = connection
    if connection.startswith("env:"):
        env_name = connection[4:]
        resolved_conn = os.getenv(env_name)
        if resolved_conn is None:
            click.echo(f"Error: Environment variable '{env_name}' not set.", err=True)
            sys.exit(1)
        logger.debug(f"Resolved connection from env:{env_name}")

    # Check if connection is JSON dict
    try:
        if resolved_conn.strip().startswith("{") and resolved_conn.strip().endswith("}"):
            connection_details = json.loads(resolved_conn)
            logger.debug("Parsed connection details as JSON dictionary.")
        else:
            connection_details = resolved_conn
    except Exception:
        connection_details = resolved_conn

    # Get extractor and fetch schema
    logger.debug(f"Instantiating extractor for type: '{type}'")
    try:
        extractor = get_extractor(type)
        logger.debug(f"Fetching live schema for {schema}.{table}...")
        live_schema = extractor.get_schema(connection_details, schema, table)
    except ModuleNotFoundError as e:
        driver_install_cmds = {
            "snowflake": 'pip install "db-schema-guard[snowflake]"',
            "sqlserver": 'pip install "db-schema-guard[sqlserver]"',
            "oracle": 'pip install "db-schema-guard[oracle]"',
            "databricks": 'pip install "db-schema-guard[databricks]"'
        }
        cmd_hint = driver_install_cmds.get(type.lower())
        click.echo(f"Error: Database driver missing. {e}", err=True)
        if cmd_hint:
            click.echo(f"💡 Hint: Install the required driver using:\n   {cmd_hint}", err=True)
        sys.exit(2)
    except Exception as e:
        click.echo(f"Error fetching live schema: {mask_secrets(str(e))}", err=True)
        sys.exit(2)

    # Format as contract structure
    contract_data = {
        "source": {
            "type": type.lower(),
            "connection": connection,  # Write the original connection reference (e.g. 'env:DB_CONN')
            "schema": schema,
            "table": table
        },
        "columns": []
    }

    for col in live_schema.get("columns", []):
        contract_data["columns"].append({
            "name": col["name"],
            "type": col["type"],
            "nullable": col.get("nullable", True)
        })

    # Validate the generated structure as a sanity check
    try:
        validate_contract(contract_data)
    except Exception as e:
        click.echo(f"Warning: Generated contract did not pass validation: {e}", err=True)

    logger.debug(f"Generated contract with {len(contract_data['columns'])} columns.")

    # Write output file
    try:
        out_dir = os.path.dirname(output)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
            logger.debug(f"Created directory: {out_dir}")

        import yaml
        with open(output, "w") as f:
            yaml.dump(contract_data, f, sort_keys=False)

        click.echo(f"✨ Contract successfully generated and saved to: {output}")
    except Exception as e:
        click.echo(f"Error writing contract file: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()