"""启动入口。

功能：
1. 单实例检测：已有实例运行时直接打开浏览器，不重复启动；
2. 自动探测可用端口（默认 8080，被占用则依次尝试 8081~8089）；
3. 服务启动后自动唤起默认浏览器打开页面；
4. windowed 模式下日志写入文件，无控制台黑窗；
5. 支持通过 /api/shutdown 优雅关闭服务；
6. 兼容 PyInstaller 打包运行。
"""
import logging
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from config import HOST, DEFAULT_PORT, DATA_DIR
from src.app import app

# ============================================================
# 日志配置：windowed 模式下写文件，控制台模式同时输出到屏幕
# ============================================================
LOG_FILE = DATA_DIR / "app.log"

_log_handlers = [logging.FileHandler(LOG_FILE, encoding="utf-8")]
if not getattr(sys, "frozen", False):
    _log_handlers.append(logging.StreamHandler())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_log_handlers,
)

UVICORN_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(asctime)s [%(levelname)s] %(message)s",
            "use_colors": False,
        },
    },
    "handlers": {
        "file": {
            "formatter": "default",
            "class": "logging.FileHandler",
            "filename": str(LOG_FILE),
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["file"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["file"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["file"], "level": "INFO", "propagate": False},
    },
}


def is_our_service_running(host: str, port: int) -> bool:
    """检测指定端口是否已有本服务在运行（发HTTP请求确认）。"""
    try:
        req = urllib.request.Request(f"http://{host}:{port}/", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def find_available_port(host: str, start_port: int, max_tries: int = 10) -> int:
    """从 start_port 开始依次探测可用端口，最多尝试 max_tries 个。"""
    for i in range(max_tries):
        port = start_port + i
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((host, port))
            s.close()
            return port
        except OSError:
            continue
    raise RuntimeError(
        f"端口 {start_port}~{start_port + max_tries - 1} 均被占用，"
        f"请关闭占用程序后重试，或设置环境变量 DESENSITIZE_PORT 指定其他端口。"
    )


def _open_browser_later(port: int, delay: float = 1.5):
    """延迟打开浏览器，确保 uvicorn 已开始监听。"""
    time.sleep(delay)
    try:
        webbrowser.open(f"http://127.0.0.1:{port}/")
    except Exception:
        pass


if __name__ == "__main__":
    # ── 单实例检测：默认端口已有本服务在跑 → 直接开浏览器，不启动新实例 ──
    if is_our_service_running(HOST, DEFAULT_PORT):
        logging.info(f"检测到已有实例在运行，直接打开浏览器 → http://127.0.0.1:{DEFAULT_PORT}/")
        webbrowser.open(f"http://127.0.0.1:{DEFAULT_PORT}/")
        sys.exit(0)

    port = find_available_port(HOST, DEFAULT_PORT, max_tries=10)

    # 打包后自动开浏览器
    if getattr(sys, "frozen", False):
        threading.Thread(target=_open_browser_later, args=(port,), daemon=True).start()

    logging.info(f"政务工单脱敏系统启动 → http://127.0.0.1:{port}/")
    print(f"[启动] 政务工单脱敏系统 → http://127.0.0.1:{port}/")

    config = uvicorn.Config(
        app,
        host=HOST,
        port=port,
        reload=False,
        log_config=UVICORN_LOG_CONFIG,
    )
    server = uvicorn.Server(config)
    app.state.server = server
    server.run()
