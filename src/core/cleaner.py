"""文件过期清理模块。

在每次上传/脱敏任务执行时调用，清理 uploads/ 和 output/ 中超过保留时长的文件。
简单可靠，不需要额外守护进程。
"""
import time
from pathlib import Path
from config import UPLOAD_DIR, OUTPUT_DIR, FILE_EXPIRE_SECONDS


def clean_expired_files(directory: Path = None, expire_seconds: int = None) -> int:
    """清理指定目录中超过保留时长的文件。

    Args:
        directory: 要清理的目录，默认同时清理 uploads 和 output
        expire_seconds: 文件保留时长（秒），默认读取配置

    Returns:
        被删除的文件数量
    """
    if expire_seconds is None:
        expire_seconds = FILE_EXPIRE_SECONDS

    deleted = 0
    now = time.time()

    dirs = [directory] if directory else [UPLOAD_DIR, OUTPUT_DIR]

    for d in dirs:
        if not d.exists():
            continue
        for f in d.iterdir():
            if not f.is_file():
                continue
            try:
                mtime = f.stat().st_mtime
                if now - mtime > expire_seconds:
                    f.unlink()
                    deleted += 1
            except OSError:
                # 文件可能被占用，跳过即可
                continue

    return deleted


def clean_on_task() -> int:
    """任务执行时调用的便捷清理函数。

    由 AUTO_CLEAN_ON_TASK 配置控制是否启用。
    """
    from config import AUTO_CLEAN_ON_TASK
    if not AUTO_CLEAN_ON_TASK:
        return 0
    return clean_expired_files()
