import asyncio
import os
import shlex
import sys

_cli = None


def _get_cli():
    global _cli
    if _cli is None:
        from app.cli.main import build_cli
        _cli = build_cli()
    return _cli


def _split_cli_line(line: str) -> list[str]:
    return shlex.split(line, posix=(os.name != "nt"))


def _run_cli_line(line: str) -> None:
    try:
        _get_cli().main(args=_split_cli_line(line), prog_name="pcb", standalone_mode=True)
    except SystemExit as exc:
        if exc.code not in (0, None):
            print(f"[exit {exc.code}]", file=sys.stderr)


async def _async_main() -> None:
    from app.cli.common import begin_session, end_session
    from app.runtime import ensure_scheduler, init_runtime, shutdown

    await init_runtime()
    await ensure_scheduler()
    loop = asyncio.get_running_loop()
    begin_session(loop)
    print("Pando CodeBase 交互模式 — 输入命令时可省略 pcb 前缀")
    print("  repo / search / migrate：交互与一次性命令均支持")
    print("  analyze：仅交互模式（本窗口）")
    print("示例：")
    print("  repo list")
    print("  search similar --path F:/myproject --code \"def foo\"")
    print("  analyze start --path F:/myproject")
    print("一次性用法：poetry run pcb repo list / pcb search similar ...")
    print("输入 help 查看命令，exit / quit 退出\n")
    try:
        while True:
            try:
                line = await asyncio.to_thread(input, "pcb> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            line = line.strip()
            if not line or line.lower() in ("exit", "quit"):
                break
            if line.lower() in ("help", "?"):
                _get_cli().main(args=["--help"], prog_name="pcb", standalone_mode=True)
                continue
            await asyncio.to_thread(_run_cli_line, line)
    finally:
        end_session()
        await shutdown()


def run_shell() -> None:
    asyncio.run(_async_main())
