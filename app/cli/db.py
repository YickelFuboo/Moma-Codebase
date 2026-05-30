import subprocess
import click


@click.command("migrate")
def migrate() -> None:
    """执行数据库迁移（alembic upgrade head）"""
    try:
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        click.echo("数据库迁移完成")
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"迁移失败: {e}") from e
    except FileNotFoundError as e:
        raise click.ClickException("未找到 alembic，请先 poetry install") from e
