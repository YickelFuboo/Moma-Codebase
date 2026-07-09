import importlib
from typing import Optional

import click

from app.config.settings import APP_NAME, APP_VERSION

_LAZY_COMMANDS: dict[str, str] = {
    "repo": "app.cli.repo",
    "analyze": "app.cli.analyze",
    "search": "app.cli.search",
    "migrate": "app.cli.db",
}


class LazyCLI(click.Group):
    """按需加载子命令，避免 repo list 等轻量命令拉取分析/向量检索重依赖。"""

    def list_commands(self, ctx: click.Context) -> list[str]:
        return sorted(_LAZY_COMMANDS.keys())

    def get_command(self, ctx: click.Context, cmd_name: str) -> Optional[click.Command]:
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None:
            return cmd
        module_path = _LAZY_COMMANDS.get(cmd_name)
        if module_path is None:
            return None
        module = importlib.import_module(module_path)
        cmd = getattr(module, cmd_name if cmd_name != "migrate" else "migrate")
        self.add_command(cmd, name=cmd_name)
        return cmd


def build_cli() -> click.Group:
    @click.group(cls=LazyCLI, invoke_without_command=True)
    @click.pass_context
    @click.version_option(APP_VERSION, prog_name=APP_NAME)
    def cli(ctx: click.Context) -> None:
        """MOMA RepoBase 代码仓分析工具"""
        if ctx.invoked_subcommand is None:
            from app.cli.shell import run_shell
            run_shell()

    return cli


cli = build_cli()


if __name__ == "__main__":
    cli()
