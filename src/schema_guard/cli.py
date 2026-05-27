import click
import sys
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
def snap(contract, snapshot_file):
    """Capture a schema snapshot from the source defined in the contract."""
    cfg = load_contract(contract)
    if cfg['source']['type'] == 'postgres':
        schema = get_schema(
            cfg['source']['connection'],
            cfg['source']['schema'],
            cfg['source']['table']
        )
    else:
        click.echo("Unsupported source type.", err=True)
        sys.exit(1)

    capture_snapshot(schema, snapshot_file)
    click.echo(f"✅ Snapshot saved to {snapshot_file}")

@cli.command()
@click.option('--contract', required=True, help='Path to contract YAML file')
@click.option('--snapshot-file', default='schema_snapshot.json', help='Baseline snapshot to compare against')
def gate(contract, snapshot_file):
    """Check current schema against snapshot and contract. Exit non-zero on violations."""
    cfg = load_contract(contract)
    if cfg['source']['type'] == 'postgres':
        live_schema = get_schema(
            cfg['source']['connection'],
            cfg['source']['schema'],
            cfg['source']['table']
        )
    else:
        click.echo("Unsupported source type.", err=True)
        sys.exit(2)

    snapshot = load_snapshot(snapshot_file)
    violations = compare_schemas(live_schema, snapshot['schema'], cfg.get('columns', []))

    if violations:
        click.echo("❌ Schema drift detected:")
        for v in violations:
            click.echo(f"  - {v}")
        # Send Slack alert (optional)
        send_email_alert(violations)
        sys.exit(1)  # fails CI
    else:
        click.echo("✅ Schema matches snapshot. No drift.")

if __name__ == '__main__':
    cli()