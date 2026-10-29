import typer

from raid_log import __version__

app = typer.Typer(
    help="Validate, report on and diff a RAID register kept as YAML.",
    no_args_is_help=True,
    add_completion=False,
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"raid-log {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_print_version, is_eager=True, help="Show the version."
    ),
) -> None:
    """Validate, report on and diff a RAID register kept as YAML."""
