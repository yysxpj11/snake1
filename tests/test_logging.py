# -*- coding: utf-8 -*-
"""日志系统测试。

验证 LogManager 的核心承诺：
- DEBUG / INFO / ERROR 三级日志按等级分别写进 game.log 与控制台；
- 重复创建不会叠加 handler（日志不重复、文件不重复写）；
- set_level 能收紧输出等级；
- close() 之后不再占用 handler。
"""

import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.logmanager import LogManager


def test_log_manager_writes_to_console_and_file(tmp_path, capsys, monkeypatch) -> None:
    """三级日志分别落到 game.log 与控制台，且重复初始化不会重复输出。"""
    monkeypatch.chdir(tmp_path)  # setup_logging 的默认 game.log 落到临时目录
    LogManager.reset_default()   # 其他测试可能已创建过共享实例，先清掉保证隔离
    log_path = tmp_path / "game.log"
    manager = LogManager(
        directory=str(tmp_path),
        filename="game.log",
        level=logging.DEBUG,      # 文件留全部细节
        console_level=logging.INFO,  # 控制台只看 INFO 以上
    )
    assert manager.path == str(log_path)
    assert manager.file_handler is not None
    assert manager.console_handler is not None

    # 三级日志各写一条（含占位符参数，验证格式化正常）
    manager.debug("调试细节：蛇长度=%d", 3)
    manager.info("游戏开始，难度=%s", "normal")
    manager.error("写盘失败：%s", "disk full")
    manager.flush()

    content = log_path.read_text(encoding="utf-8")
    assert "DEBUG" in content and "调试细节：蛇长度=3" in content
    assert "INFO" in content and "游戏开始，难度=normal" in content
    assert "ERROR" in content and "写盘失败：disk full" in content
    # 三条日志按调用顺序落盘
    assert content.index("DEBUG") < content.index("INFO") < content.index("ERROR")
    # 每条都带模块来源，便于定位
    assert "snake:" in content

    # 控制台：INFO/ERROR 有，DEBUG 被 console_level 过滤掉
    out = capsys.readouterr().out
    assert "游戏开始，难度=normal" in out
    assert "写盘失败：disk full" in out
    assert "调试细节" not in out

    # 重复创建（模拟测试里反复 new Application）不会叠加 handler、不会重复写
    second = LogManager(directory=str(tmp_path), filename="game.log")
    owned = [h for h in second.logger.handlers if getattr(h, "_log_manager_owned", False)]
    assert len(owned) == 2, "应只有一套 控制台 + 文件 handler"
    second.info("第二次初始化")
    second.flush()
    assert log_path.read_text(encoding="utf-8").count("第二次初始化") == 1

    # set_level 收紧后，低等级日志不再落盘
    assert second.set_level(logging.ERROR) == logging.ERROR
    second.info("这条不该出现")
    second.error("只留错误")
    second.flush()
    content = log_path.read_text(encoding="utf-8")
    assert "这条不该出现" not in content
    assert "只留错误" in content

    # 等级字符串解析
    assert LogManager.parse_level("debug") == logging.DEBUG
    assert LogManager.parse_level("ERROR") == logging.ERROR
    assert LogManager.parse_level(15) == 15

    # setup_logging 复用共享实例，日志落在当前目录的 game.log
    from snake.utils import setup_logging

    shared_logger = setup_logging()
    assert shared_logger.name == "snake"
    LogManager.get_default().info("启动日志")
    LogManager.get_default().flush()
    assert (tmp_path / "game.log").read_text(encoding="utf-8").count("启动日志") == 1

    # close 之后不再持有自己的 handler
    second.close()
    assert [h for h in second.logger.handlers if getattr(h, "_log_manager_owned", False)] == []
    LogManager.reset_default()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
