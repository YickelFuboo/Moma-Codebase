import asyncio
import logging
import signal
import click
from app.runtime import shutdown, startup


@click.command()
def worker() -> None:
    """前台运行文件分析调度器（Ctrl+C 退出）"""

    async def _run() -> None:
        await startup(start_scheduler=True)
        stop_event = asyncio.Event()

        def _handle_signal(*_args: object) -> None:
            stop_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_signal)
            except NotImplementedError:
                signal.signal(sig, lambda *_: stop_event.set())

        click.echo("分析调度器已启动，按 Ctrl+C 停止")
        await stop_event.wait()
        await shutdown()
        click.echo("已停止")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logging.info("收到中断信号，正在退出")
