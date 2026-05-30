import click
from app.config.settings import APP_NAME, APP_VERSION
from app.cli.analyze import analyze
from app.cli.db import migrate
from app.cli.repo import repo
from app.cli.search import search
from app.cli.worker import worker


@click.group()
@click.version_option(APP_VERSION, prog_name=APP_NAME)
def cli() -> None:
    """Pando CodeBase 本地命令行工具（pcb）"""


cli.add_command(repo)
cli.add_command(analyze)
cli.add_command(search)
cli.add_command(worker)
cli.add_command(migrate)
