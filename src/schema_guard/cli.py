import click
import sys
import os
import json
from schema_guard.extractors.postgres import get_schema
from schema_guard.contract import load_contract
from schema_guard.snapshot import capture_snapshot, load_snapshot
from schema_guard.diff_engine import compare_schemas
from schema_guard.alerter import send_email_alert

from dotenv import load_dotenv
load_dotenv()


@click.group()
def cli():
    """Schema Guard - protect your data pipelines from silent schema drift."""


@cli.command()
@click.option('--contract', required=True, help='Path to contract YAML file')
@click.option('--snapshot-file', default='schema_snapshot.json', help='Where to save the snapshot')
@click.option('--force', is_flag=True, default=False, help='Overwrite existing snapshot without confirmation')
def snap(contract, snapshot_file, force):
    """Capture a schema snapshot from the source defined in the contract."""
    cfg = load_contract(contract)

    # --- Fix #3: Protect against silent overwrites ---
    if os.path.exists(snapshot_file) and not force:
        click.echo(f"⚠️  Snapshot already exists: {snapshot_file}")
        click.echo("   Use --force to overwrite the existing baseline.")
        click.echo("   This is a safety measure to prevent accidental baseline drift.")

        # Show a quick summary of what would change
        try:
            old_snapshot = load_snapshot(snapshot_file)
            old_cols = {c['name'] for c in old_snapshot['schema']['columns']}

            # Fetch live schema to show diff
            if cfg['source']['type'] == 'postgres':
                live = get_schema(
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

    if cfg['source']['type'] == 'postgres':
        schema = get_schema(
            cfg['source']['connection'],
            cfg['source']['schema'],
            cfg['source']['table']
        )
    else:
        click.echo(f"Unsupported source type: {cfg['source']['type']}", err=True)
        sys.exit(1)

    capture_snapshot(schema, snapshot_file)
    click.echo(f"✅ Snapshot saved to {snapshot_file}")


@cli.command()
@click.option('--contract', required=True, help='Path to contract YAML file')
@click.option('--snapshot-file', default='schema_snapshot.json', help='Baseline snapshot to compare against')
@click.option('--require-alert', is_flag=True, default=False, help='Exit with code 2 if email alert fails to send')
def gate(contract, snapshot_file, require_alert):
    """Check current schema against snapshot and contract. Exit non-zero on violations."""
    cfg = load_contract(contract)
    if cfg['source']['type'] == 'postgres':
        live_schema = get_schema(
            cfg['source']['connection'],
            cfg['source']['schema'],
            cfg['source']['table']
        )
    else:
        click.echo(f"Unsupported source type: {cfg['source']['type']}", err=True)
        sys.exit(2)

    try:
        snapshot = load_snapshot(snapshot_file)
    except ValueError as e:
        click.echo(f"❌ {e}", err=True)
        sys.exit(3)

    violations, notices = compare_schemas(live_schema, snapshot['schema'], cfg.get('columns', []))

    # --- Fix #7: Print notices (non-blocking) for visibility ---
    if notices:
        click.echo("ℹ️  Notices:")
        for n in notices:
            click.echo(f"  - {n}")

    if violations:
        click.echo("❌ Schema drift detected:")
        for v in violations:
            click.echo(f"  - {v}")

        # --- Fix #11: Handle --require-alert ---
        alert_sent = send_email_alert(violations)
        if require_alert and not alert_sent:
            click.echo("❌ Email alert failed to send (--require-alert is set).", err=True)
            sys.exit(2)

        sys.exit(1)  # fails CI
    else:
        click.echo("✅ Schema matches snapshot. No drift.")


if __name__ == '__main__':
    cli()