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
        _get_cli().main(args=_split_cli_line(line), prog_name="mcb", standalone_mode=True)
    except SystemExit as exc:
        if exc.code not in (0, None):
            print(f"[exit {exc.code}]", file=sys.stderr)


async def _async_main() -> None:
    from app.cli.common import begin_session, end_session
    from app.repo_analysis.services.codegraph.gateway import CodeGraphGateway
    from app.runtime import ensure_scheduler, init_runtime, shutdown

    await init_runtime()
    try:
        CodeGraphGateway.ensure_ready()
    except Exception as exc:
        print(f"[CodeGraph] 就绪检查失败: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    await ensure_scheduler()
    loop = asyncio.get_running_loop()
    begin_session(loop)
    print("MomaCodeBase 交互模式 — 输入命令时可省略 mcb 前缀")
    print("  repo / analyze / experience / search / inspect / migrate：交互与一次性命令均支持")
    print("示例：")
    print("  repo add --path F:/myproject --kind code")
    print("  analyze --path F:/myproject")
    print("  experience analyze --path F:/myproject --limit 20")
    print("  search similar --path F:/myproject --code \"def foo\"")
    print("  search related --path F:/myproject --keywords \"告警,触发\"")
    print("  search chunks --path F:/myproject --query \"告警触发\"")
    print("  search symbols --path F:/myproject --query \"TriggerAlarm\"")
    print("  search pattern --path F:/myproject --query \"改告警\"")
    print("  inspect chunks --path F:/myproject --target app/cli --limit 20")
    print("  inspect apis --path F:/mylib --file pkg/api.py")
    print("一次性用法：poetry run mcb repo list / mcb search similar ...")
    print("输入 help 查看命令，exit / quit 退出\n")
    try:
        while True:
            try:
                line = await asyncio.to_thread(input, "mcb> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            line = line.strip()
            if not line or line.lower() in ("exit", "quit"):
                break
            if line.lower() in ("help", "?"):
                _get_cli().main(args=["--help"], prog_name="mcb", standalone_mode=True)
                continue
            await asyncio.to_thread(_run_cli_line, line)
    finally:
        end_session()
        await shutdown()


def run_shell() -> None:
    asyncio.run(_async_main())
