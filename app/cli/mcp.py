"""CLI：MCP Server 入口。"""
import click


@click.group()
def mcp() -> None:
    """MCP Server（stdio）查询接口"""


@mcp.command("serve")
@click.option(
    "--transport",
    default="stdio",
    show_default=True,
    type=click.Choice(["stdio"], case_sensitive=False),
    help="传输方式；Cursor 使用 stdio",
)
def mcp_serve(transport: str) -> None:
    """启动 MCP Server。Cursor 配置 command=mcb args=[mcp, serve]。"""
    from MCP.server import McpServer

    McpServer.run(transport=transport.lower())
