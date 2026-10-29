# -*- coding: utf-8 -*-
"""难度选择功能测试。

验证菜单中"选择难度"的三档切换、标签刷新、回调同步，
以及难度参数确实驱动蛇的移动速度。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.game import Game
from snake.ui import Menu
from snake.utils import Config, Difficulty


class TestDifficultySelection:
    """验证三档难度的切换与速度参数化。"""

    def test_difficulty_switch_by_left_right_keys(self) -> None:
        """左右键在"选择难度"项上循环切换三档，并同步标签、回调与蛇速。"""
        changes = []
        menu = Menu(difficulty=Difficulty.NORMAL, on_difficulty_change=changes.append)

        # 菜单默认项顺序：开始游戏 / 选择难度 / 退出
        assert menu.difficulty_index == 1
        assert menu.items[1][0] == "选择难度: 普通"

        # 未选中难度项时，左右键不改变难度
        menu.handle_key("right")
        assert menu.difficulty is Difficulty.NORMAL

        # 选中难度项后，右键：普通 -> 困难
        menu.handle_key("down")
        assert menu.selected_action == "difficulty"
        menu.handle_key("right")
        assert menu.difficulty is Difficulty.HARD
        assert menu.items[1][0] == "选择难度: 困难"

        # 继续右键循环：困难 -> 简单
        menu.handle_key("right")
        assert menu.difficulty is Difficulty.EASY

        # 左键回退：简单 -> 困难
        menu.handle_key("left")
        assert menu.difficulty is Difficulty.HARD

        # 回调按切换顺序记录
        assert changes == [Difficulty.HARD, Difficulty.EASY, Difficulty.HARD]

        # 难度参数驱动速度：档位越快，移动间隔越小
        assert Difficulty.EASY.move_interval > Difficulty.NORMAL.move_interval
        assert Difficulty.NORMAL.move_interval > Difficulty.HARD.move_interval

        # 游戏从设置读取速度：难度的间隔应直接反映到实际移动间隔
        easy_game = Game(config=Config(difficulty=Difficulty.EASY), seed=1)
        hard_game = Game(config=Config(difficulty=Difficulty.HARD), seed=1)
        assert easy_game.current_move_interval() == Difficulty.EASY.move_interval
        assert hard_game.current_move_interval() == Difficulty.HARD.move_interval
        assert easy_game.current_move_interval() > hard_game.current_move_interval()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
