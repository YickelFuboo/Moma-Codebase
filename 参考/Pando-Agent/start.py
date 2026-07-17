#!/usr/bin/env python3
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PID_FILE = ROOT / ".pando-dev.pids"
BACKEND_LOG = ROOT / "backend.log"
FRONTEND_LOG = ROOT / "frontend.log"
WEBSITE_DIR = ROOT / "website"
FRONTEND_HOST = "0.0.0.0"
FRONTEND_PORT = 5173


def _env_flag(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _resolve_cmd(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        print(f"[error] 未找到 {name}，请先安装并配置 PATH")
        sys.exit(1)
    return path


def _require_cmd(name: str) -> None:
    _resolve_cmd(name)


def _kill_pid(pid: int) -> None:
    if pid <= 0:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except ProcessLookupError:
                os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, OSError, PermissionError):
        pass


def _read_pids() -> tuple[int, int]:
    if not PID_FILE.is_file():
        return 0, 0
    text = PID_FILE.read_text(encoding="utf-8").strip()
    if not text:
        return 0, 0
    parts = text.split()
    if len(parts) < 2:
        return 0, 0
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return 0, 0


def _stop_old_pids() -> None:
    old_back, old_web = _read_pids()
    _kill_pid(old_back)
    _kill_pid(old_web)
    PID_FILE.unlink(missing_ok=True)


def _spawn_background(cmd: list[str], *, cwd: Path, log_file: Path) -> int:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as log_handle:
        kwargs: dict = {
            "cwd": str(cwd),
            "stdout": log_handle,
            "stderr": subprocess.STDOUT,
            "env": os.environ.copy(),
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **kwargs)
    return proc.pid


def main() -> None:
    os.chdir(ROOT)

    if not (ROOT / "pyproject.toml").is_file():
        print("[error] 请在项目根目录运行 start.py")
        sys.exit(1)

    _require_cmd("poetry")
    _require_cmd("npm")

    if not (ROOT / "env").is_file() and not (ROOT / ".env").is_file():
        print("[warn] 未找到 env 或 .env，建议执行：cp env.example env")

    if not (WEBSITE_DIR / "node_modules").is_dir():
        print("[info] 安装前端依赖...")
        subprocess.run([_resolve_cmd("npm"), "install"], cwd=WEBSITE_DIR, check=True)

    _stop_old_pids()

    service_port = os.environ.get("SERVICE_PORT", "9001")
    reload_enabled = _env_flag("UVICORN_RELOAD", default=True)
    poetry = _resolve_cmd("poetry")
    npm = _resolve_cmd("npm")

    backend_cmd = [
        poetry,
        "run",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        service_port,
    ]
    if reload_enabled:
        backend_cmd.append("--reload")

    print("")
    print(f"[start] 启动后端  http://127.0.0.1:{service_port}")
    pid_back = _spawn_background(backend_cmd, cwd=ROOT, log_file=BACKEND_LOG)
    print(f"后端进程 PID: {pid_back}")

    frontend_cmd = [
        npm,
        "run",
        "dev",
        "--",
        "--host",
        FRONTEND_HOST,
        "--port",
        str(FRONTEND_PORT),
    ]
    print(f"[start] 启动前端  http://{FRONTEND_HOST}:{FRONTEND_PORT}")
    pid_web = _spawn_background(frontend_cmd, cwd=WEBSITE_DIR, log_file=FRONTEND_LOG)
    print(f"前端进程 PID: {pid_web}")

    PID_FILE.write_text(f"{pid_back} {pid_web}\n", encoding="utf-8")

    print("")
    print("=============================================")
    print(f"后端日志：{BACKEND_LOG}")
    print(f"前端日志：{FRONTEND_LOG}")
    print(f"PID 文件：{PID_FILE}")
    if sys.platform == "win32":
        print(f"停止服务：taskkill /F /PID {pid_back} & taskkill /F /PID {pid_web}")
    else:
        print(f"停止服务：kill $(cat {PID_FILE})")
    print("禁用热重载：UVICORN_RELOAD=0 python start.py")
    print("=============================================")
    print("")

    print("[info] 主进程进入阻塞等待，服务持续运行...")

    def _shutdown(signum: int, _frame) -> None:
        print(f"[info] 收到终止信号 ({signum})，清理子进程")
        _stop_old_pids()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, _shutdown)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("[info] 收到终止信号，清理子进程")
        _stop_old_pids()


if __name__ == "__main__":
    main()
