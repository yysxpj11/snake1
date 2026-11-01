# -*- coding: utf-8 -*-
"""状态流转测试（一）：菜单状态切换与暂停/继续状态切换。

补充既有测试未覆盖的分支：
1. 菜单五项动作的完整清单与"设置"项确认回调；
2. Game 状态机的完整流转：菜单 <-> 设置、菜单 -> 游戏 -> 菜单、
   结束状态下拒绝进入设置；
3. 暂停/继续在各非法状态下的拒绝行为（菜单中、结束后、重复暂停）。

本测试不依赖 pygame 显示层，纯逻辑可 headless 运行。
"""

import os
import sys
import tempfile

import pytest

# 保证从项目根目录可导入 snake 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.game import Game, GameState
from snake.ui import Menu
from snake.utils import Config, HighScoreStore


# ---------------------------------------------------------------------------
# 测试 1：菜单状态切换（开始 / 设置 / 退出）
# ---------------------------------------------------------------------------


class TestMenuStateSwitching:
    """验证菜单项动作与 Game 状态机的完整流转。"""

    def test_menu_contains_five_actions_in_order(self) -> None:
        """菜单包含 开始/难度/皮肤/设置/退出 五项，动作名与顺序固定。"""
        menu = Menu()
        actions = [action for _text, action in menu.items]
        assert actions == ["start", "difficulty", "skin", "settings", "quit"]

    def test_confirm_settings_action_fires_callback(self) -> None:
        """确认"设置"项：返回 "settings"，回调按序收到动作。"""
        actions: list = []
        menu = Menu(on_select=actions.append)
        menu.selected_index = [a for _t, a in menu.items].index("settings")
        assert menu.selected_action == "settings"
        assert menu.handle_key("confirm") == "settings"
        assert actions == ["settings"]

    def test_game_state_machine_menu_settings_roundtrip(self) -> None:
        """菜单 <-> 设置：从菜单进入设置后返回菜单；从游戏内进入则回到游戏。"""
        game = Game(config=Config(window_width=200, window_height=200, cell_size=20), seed=1)

        # 菜单 -> 设置 -> 菜单
        assert game.state == GameState.MENU
        assert game.enter_settings() is True
        assert game.state == GameState.SETTINGS
        assert game.settings_from_game is False  # 从菜单进入，不是游戏内
        assert game.exit_settings() == GameState.MENU
        assert game.state == GameState.MENU

        # 游戏 -> 设置 -> 游戏（本局继续）
        game.new_game()
        assert game.state == GameState.PLAYING
        assert game.enter_settings() is True
        assert game.state == GameState.SETTINGS
        assert game.exit_settings() == GameState.PLAYING
        assert game.snake is not None  # 局面未被丢弃

        # 游戏 -> 菜单：结束本局回主菜单
        game.back_to_menu()
        assert game.state == GameState.MENU

    def test_settings_rejected_from_game_over(self) -> None:
        """结束状态下不允许进入设置面板，状态保持 GAME_OVER。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = HighScoreStore(directory=tmpdir)
            game = Game(config=Config(window_width=200, window_height=200, cell_size=20),
                        seed=1, store=store)
            game.new_game()
            game._game_over("测试结束")
            assert game.state == GameState.GAME_OVER
            assert game.enter_settings() is False
            assert game.state == GameState.GAME_OVER

    def test_quit_action_terminates_application_flow(self) -> None:
        """确认"退出"动作后回调收到 quit，可用于结束主循环。"""
        actions: list = []
        menu = Menu(on_select=actions.append)
        menu.selected_index = [a for _t, a in menu.items].index("quit")
        assert menu.handle_key("confirm") == "quit"
        assert actions == ["quit"]


# ---------------------------------------------------------------------------
# 测试 2：暂停与继续状态切换
# ---------------------------------------------------------------------------


class TestPauseStateEdgeCases:
    """验证暂停/继续在各状态下的接受与拒绝行为。"""

    def _make_game(self) -> Game:
        """构造一个已开始的小网格游戏。"""
        game = Game(config=Config(window_width=200, window_height=200, cell_size=20), seed=2)
        game.new_game()
        return game

    def test_pause_rejected_in_menu_state(self) -> None:
        """菜单状态下不可暂停：pause/toggle 均失败，状态不变。"""
        game = Game(config=Config(window_width=200, window_height=200, cell_size=20), seed=2)
        assert game.state == GameState.MENU
        assert game.pause() is False
        assert game.state == GameState.MENU
        assert game.toggle_pause() is False
        assert game.state == GameState.MENU

    def test_resume_rejected_when_not_paused(self) -> None:
        """进行中调用 resume 无效；只有先暂停后 resume 才成功。"""
        game = self._make_game()
        assert game.state == GameState.PLAYING
        assert game.resume() is False
        assert game.state == GameState.PLAYING

        assert game.pause() is True
        assert game.state == GameState.PAUSED
        assert game.resume() is True
        assert game.state == GameState.PLAYING

    def test_double_pause_fails_second_time(self) -> None:
        """重复暂停：第一次成功，第二次失败且状态保持 PAUSED。"""
        game = self._make_game()
        assert game.pause() is True
        assert game.state == GameState.PAUSED
        assert game.pause() is False
        assert game.state == GameState.PAUSED

    def test_toggle_pause_in_game_over_state(self) -> None:
        """结束后 toggle_pause 无效：状态保持 GAME_OVER，也不复活本局。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = HighScoreStore(directory=tmpdir)
            game = Game(config=Config(window_width=200, window_height=200, cell_size=20),
                        seed=2, store=store)
            game.new_game()
            game._game_over("测试结束")
            assert game.toggle_pause() is False
            assert game.state == GameState.GAME_OVER
            assert game.is_paused is False

    def test_pause_resume_alternates_via_toggle(self) -> None:
        """toggle_pause 连续切换：暂停(True) -> 继续(False) -> 暂停(True)。"""
        game = self._make_game()
        assert game.toggle_pause() is True   # 进入暂停
        assert game.toggle_pause() is False  # 恢复进行
        assert game.toggle_pause() is True   # 再次暂停
        assert game.is_paused is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
