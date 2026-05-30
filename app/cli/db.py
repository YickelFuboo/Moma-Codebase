import click
from app.infrastructure.database.migrate import upgrade_head


@click.command("migrate")
def migrate() -> None:
    """执行数据库迁移（alembic upgrade head）"""
    try:
        upgrade_head()
        click.echo("数据库迁移完成")
    except Exception as e:
        raise click.ClickException(f"迁移失败: {e}") from e
