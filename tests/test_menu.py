# -*- coding: utf-8 -*-
"""开始菜单功能测试。

验证 Menu 类的状态切换与"菜单 -> 游戏"的状态流转，
不依赖 pygame 显示窗口（Menu 为纯逻辑类）。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.game import Game, GameState
from snake.ui import Menu
from snake.utils import Config


class TestMenuStateSwitching:
    """验证菜单选择切换与确认后的状态流转。"""

    def test_menu_selection_and_start_game(self) -> None:
        """上/下键切换选中项（含循环），回车确认"开始游戏"后进入 PLAYING。"""
        actions: list = []
        menu = Menu(on_select=actions.append)

        # 初始状态：默认选中第一项"开始游戏"
        assert menu.selected_index == 0
        assert menu.selected_action == "start"

        # 向下四次：开始游戏 -> 难度 -> 皮肤 -> 设置 -> 退出
        menu.handle_key("down")
        assert menu.selected_action == "difficulty"
        menu.handle_key("down")
        assert menu.selected_action == "skin"
        menu.handle_key("down")
        assert menu.selected_action == "settings"
        menu.handle_key("down")
        assert menu.selected_action == "quit"

        # 向下一次：从最后一项循环回第一项
        menu.handle_key("down")
        assert menu.selected_action == "start"

        # 向上一次：从第一项循环回最后一项
        menu.handle_key("up")
        assert menu.selected_action == "quit"

        # 再向上四次：退出 -> 设置 -> 皮肤 -> 难度 -> 开始游戏
        menu.handle_key("up")
        assert menu.selected_action == "settings"
        menu.handle_key("up")
        assert menu.selected_action == "skin"
        menu.handle_key("up")
        assert menu.selected_action == "difficulty"
        menu.handle_key("up")
        assert menu.selected_action == "start"

        # 确认"开始游戏"，回调收到 start 动作
        result = menu.handle_key("confirm")
        assert result == "start"
        assert actions == ["start"]

        # 确认动作驱动 Game 状态：MENU -> PLAYING
        config = Config(window_width=200, window_height=200, cell_size=20)
        game = Game(config=config, seed=1)
        assert game.state == GameState.MENU
        game.new_game()  # 与 main._on_menu_select("start") 的行为一致
        assert game.state == GameState.PLAYING

    def test_menu_confirm_quit_and_difficulty_label(self) -> None:
        """确认"退出"动作正确返回；难度标签可动态刷新。"""
        actions: list = []
        menu = Menu(on_select=actions.append)

        # 选中难度项并确认
        menu.handle_key("down")
        assert menu.selected_action == "difficulty"
        assert menu.handle_key("confirm") == "difficulty"

        # 难度切换后刷新菜单标签
        menu.set_item_text(1, "难度: 困难")
        assert menu.selected_text == "难度: 困难"
        # 动作名不受文本刷新影响
        assert menu.selected_action == "difficulty"

        # 选中退出项并确认（中间跳过皮肤与设置项）
        menu.handle_key("down")
        assert menu.selected_action == "skin"
        menu.handle_key("down")
        assert menu.selected_action == "settings"
        menu.handle_key("down")
        assert menu.handle_key("confirm") == "quit"
        assert actions == ["difficulty", "quit"]

        # 未知按键不改变状态
        before = menu.selected_index
        assert menu.handle_key("unknown") is None
        assert menu.selected_index == before


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
