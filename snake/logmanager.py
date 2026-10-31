# -*- coding: utf-8 -*-
"""日志管理模块。

- LogManager: 统一配置"控制台 + 本地 game.log"双输出，支持 DEBUG/INFO/ERROR 分级

设计要点：

1. **挂在包级 logger 上**：日志器名为 ``snake``，包里各模块的
   ``logging.getLogger(__name__)``（snake.game / snake.settings / snake.sound ...）
   会沿父子关系向上冒泡到这里，因此任何模块写日志都能同时进控制台和文件，
   不需要逐个函数传 logger 参数。
2. **重复创建不叠加 handler**：测试里会反复构造 Application / LogManager，
   若每次都 addHandler，日志就会重复输出、文件句柄也会泄漏。这里在挂新
   handler 前先把"自己人"（带 ``_log_manager_owned`` 标记的）摘除并关闭。
3. **落盘失败要降级**：日志目录只读或磁盘满时，只保留控制台输出，
   绝不因为写日志把游戏搞崩。

典型用法::

    logs = LogManager()                 # 默认 ./game.log，文件 DEBUG，控制台 INFO
    logs.info("游戏开始，难度=%s", "normal")
    logs.debug("蛇长度=%d", 3)
    logs.error("保存设置失败: %s", exc)
"""

from __future__ import annotations

import logging
import os
import sys
from typing import List, Optional

# 默认日志文件名
DEFAULT_LOG_FILENAME = "game.log"
# 包级 logger 名称：包内模块的日志都会冒泡到这里
PACKAGE_LOGGER_NAME = "snake"
# 统一的日志格式与时间格式
LOG_FORMAT = "[%(asctime)s] %(levelname)-5s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class LogManager:
    """日志管理器：控制台 + 文件双输出，按等级过滤。

    Attributes:
        logger: 底层 logging.Logger（包级，名为 "snake"）。
        path: 日志文件的完整路径。
        directory: 日志文件所在目录。
        console_level: 控制台输出的最低等级。
    """

    # 进程内共享实例（见 get_default）
    _default: Optional["LogManager"] = None

    def __init__(
        self,
        directory: str = ".",
        filename: str = DEFAULT_LOG_FILENAME,
        level: int = logging.DEBUG,
        console_level: int = logging.INFO,
        console: bool = True,
    ) -> None:
        """初始化日志系统并挂上控制台与文件两个 handler。

        Args:
            directory: 日志文件所在目录，默认当前工作目录。
            filename: 日志文件名，默认 game.log。
            level: 写入文件的最低等级（默认 DEBUG，细节也留档）。
            console_level: 输出到控制台的最低等级（默认 INFO，避免刷屏）。
            console: 是否启用控制台输出（关闭后只写文件）。
        """
        self.directory = directory
        self.filename = filename
        self.path = os.path.join(directory, filename)
        self.console_level = self.parse_level(console_level)
        self.file_level = self.parse_level(level)

        self.logger = logging.getLogger(PACKAGE_LOGGER_NAME)
        # 先摘掉上一次（可能是别的实例）挂上的 handler，避免重复输出
        self._detach_owned_handlers()
        self.logger.setLevel(min(self.file_level, self.console_level if console else self.file_level))
        # 不向 root 冒泡：否则 pytest / 其他库配置过 root 时会再输出一遍
        self.logger.propagate = False

        self._console_handler: Optional[logging.Handler] = None
        self._file_handler: Optional[logging.Handler] = None
        if console:
            self._attach_console()
        self._attach_file()

    # -- 构造辅助 -----------------------------------------------------------

    @staticmethod
    def parse_level(level) -> int:
        """把 int 或 "debug"/"info"/"error" 这类字符串转成 logging 级别。"""
        if isinstance(level, str):
            return getattr(logging, level.strip().upper(), logging.INFO)
        try:
            return int(level)
        except (TypeError, ValueError):
            return logging.INFO

    @staticmethod
    def _formatter() -> logging.Formatter:
        """构造统一的日志格式（时间 + 等级 + 来源模块 + 内容）。"""
        return logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    def _owned_handlers(self) -> List[logging.Handler]:
        """返回本类挂上去的 handler（用于安全清理，不影响外部 handler）。"""
        return [
            handler
            for handler in self.logger.handlers
            if getattr(handler, "_log_manager_owned", False)
        ]

    def _detach_owned_handlers(self) -> None:
        """摘除并关闭之前挂上的 handler，保证同一时刻只有一套输出。"""
        for handler in self._owned_handlers():
            self.logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:  # 关闭失败不影响后续初始化
                pass

    def _attach_console(self) -> None:
        """挂上控制台 handler（写 stdout）。"""
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(self.console_level)
        handler.setFormatter(self._formatter())
        handler._log_manager_owned = True  # type: ignore[attr-defined]
        self.logger.addHandler(handler)
        self._console_handler = handler

    def _attach_file(self) -> None:
        """挂上文件 handler；目录/文件不可写时降级为仅控制台。"""
        try:
            if self.directory and not os.path.isdir(self.directory):
                os.makedirs(self.directory, exist_ok=True)
            # 追加模式：多次启动的日志连续留档，不覆盖上一次
            handler = logging.FileHandler(self.path, mode="a", encoding="utf-8")
        except OSError as exc:
            self._file_handler = None
            self.logger.warning("日志文件不可用，已降级为仅控制台输出: %s (%s)", self.path, exc)
            return
        handler.setLevel(self.file_level)
        handler.setFormatter(self._formatter())
        handler._log_manager_owned = True  # type: ignore[attr-defined]
        self.logger.addHandler(handler)
        self._file_handler = handler

    # -- 共享实例 -----------------------------------------------------------

    @classmethod
    def get_default(cls, **kwargs) -> "LogManager":
        """获取进程内共享的 LogManager（首次调用按参数创建，之后复用）。

        游戏里各模块统一从这里取，避免反复创建导致的 handler 叠加。
        单元测试需要隔离时直接构造 ``LogManager(directory=tmp_path)``。
        """
        if cls._default is None:
            cls._default = cls(**kwargs)
        return cls._default

    @classmethod
    def reset_default(cls) -> None:
        """关闭并丢弃共享实例（进程退出或测试收尾时调用）。"""
        if cls._default is not None:
            cls._default.close()
            cls._default = None

    # -- 分级输出 -----------------------------------------------------------

    def debug(self, message: str, *args) -> None:
        """输出 DEBUG 级日志（细节排查，默认只进文件）。"""
        self.logger.debug(message, *args)

    def info(self, message: str, *args) -> None:
        """输出 INFO 级日志（正常事件：开始、暂停、吃到食物等）。"""
        self.logger.info(message, *args)

    def warning(self, message: str, *args) -> None:
        """输出 WARNING 级日志（可恢复的异常：文件读写失败等）。"""
        self.logger.warning(message, *args)

    def error(self, message: str, *args) -> None:
        """输出 ERROR 级日志（功能受损但游戏仍能继续）。"""
        self.logger.error(message, *args)

    def critical(self, message: str, *args) -> None:
        """输出 CRITICAL 级日志（严重错误，通常紧随其后就退出）。"""
        self.logger.critical(message, *args)

    def exception(self, message: str, *args) -> None:
        """在 except 块里输出 ERROR 日志并附带堆栈。"""
        self.logger.exception(message, *args)

    # -- 运行期调整 ---------------------------------------------------------

    def set_level(self, level) -> int:
        """调整写文件的日志等级，返回生效后的等级值。"""
        self.file_level = self.parse_level(level)
        self.logger.setLevel(self.file_level)
        if self._file_handler is not None:
            self._file_handler.setLevel(self.file_level)
        return self.file_level

    def set_console_level(self, level) -> int:
        """调整控制台日志等级，返回生效后的等级值。"""
        self.console_level = self.parse_level(level)
        if self._console_handler is not None:
            self._console_handler.setLevel(self.console_level)
        return self.console_level

    def flush(self) -> None:
        """把缓冲区里的日志立刻刷到文件（测试与崩溃排查时用）。"""
        for handler in self._owned_handlers():
            try:
                handler.flush()
            except Exception:
                pass

    def close(self) -> None:
        """摘除并关闭自己挂的所有 handler（可重复调用）。"""
        self.flush()
        self._detach_owned_handlers()
        self._console_handler = None
        self._file_handler = None

    # -- 上下文管理 ---------------------------------------------------------

    def __enter__(self) -> "LogManager":
        """支持 with LogManager() as logs 用法。"""
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """离开 with 块时关闭 handler。"""
        self.close()

    @property
    def file_handler(self) -> Optional[logging.Handler]:
        """当前的文件 handler（未成功挂上时为 None）。"""
        return self._file_handler

    @property
    def console_handler(self) -> Optional[logging.Handler]:
        """当前的控制台 handler（console=False 时为 None）。"""
        return self._console_handler


def get_logger(name: str = PACKAGE_LOGGER_NAME) -> logging.Logger:
    """便捷函数：按名称取 logger（包内模块可直接用它代替 logging.getLogger）。"""
    return logging.getLogger(name)
