# -*- coding: utf-8 -*-
"""设置面板功能测试。

验证设置面板的界面状态流转（菜单 -> 设置 -> 菜单）、
面板内部导航与保存/返回回调，不依赖真实显示窗口。
"""

import os
import sys

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.game import GameState
from snake.ui import Menu, SettingsPanel
from snake.utils import Config, Difficulty


class TestSettingsPanel:
    """验证 SettingsPanel 的导航与回调逻辑。"""

    def test_panel_navigation_and_callbacks(self) -> None:
        """上/下键在三个设置项间循环切换，确认/返回触发对应回调。"""
        saved: list = []
        cancelled: list = []
        panel = SettingsPanel(
            volume=0.5,
            difficulty=Difficulty.NORMAL,
            skin="经典绿",
            on_save=lambda v, d, s: saved.append((v, d, s)),
            on_cancel=lambda: cancelled.append(True),
        )

        # 初始状态：选中第一项"音量"，音量换算正确
        assert panel.selected_action == "volume"
        assert panel.volume == 50
        assert panel.volume_ratio == pytest.approx(0.5)

        # 向下循环：音量 -> 难度 -> 皮肤 -> 音量
        panel.handle_key("down")
        assert panel.selected_action == "difficulty"
        panel.handle_key("down")
        assert panel.selected_action == "skin"
        panel.handle_key("down")
        assert panel.selected_action == "volume"

        # 向上循环回到皮肤项
        panel.handle_key("up")
        assert panel.selected_action == "skin"

        # 回车保存：回调收到暂存值，返回 "save"
        assert panel.handle_key("confirm") == "save"
        assert saved == [(0.5, Difficulty.NORMAL, "经典绿")]

        # ESC 返回：触发取消回调，返回 "back"
        assert panel.cancel() == "back"
        assert cancelled == [True]

        # 音量越界保护：构造时裁剪到 0-100
        low = SettingsPanel(volume=-0.5)
        high = SettingsPanel(volume=1.8)
        assert low.volume == 0
        assert high.volume == 100


class TestSettingsStateFlow:
    """验证菜单 -> 设置面板 -> 菜单 的界面状态流转。"""

    def test_open_settings_from_menu_and_esc_back(self) -> None:
        """菜单确认"设置"进入 SETTINGS 状态，ESC 返回 MENU 且面板关闭。"""
        pygame.init()  # Application 需要字体子系统
        from snake.main import Application, build_config, parse_args

        app = Application(build_config(parse_args(["--width", "400", "--height", "400"])))
        assert app.game.state == GameState.MENU

        # 选中"设置"项并确认：状态切换为 SETTINGS，面板以当前设置创建
        settings_index = [a for _t, a in app.menu_logic.items].index("settings")
        app.menu_logic.selected_index = settings_index
        app.menu_logic.handle_key("confirm")
        assert app.game.state == GameState.SETTINGS
        assert app.settings_panel is not None
        assert app.settings_panel.difficulty == app.config.difficulty
        assert app.settings_panel.skin == app.skin_manager.current.name

        # 面板导航不影响游戏状态
        app.settings_panel.handle_key("down")
        assert app.game.state == GameState.SETTINGS

        # ESC 返回菜单：面板被关闭，游戏状态回到 MENU
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        app.process_events()
        assert app.game.state == GameState.MENU
        assert app.settings_panel is None

        # 游戏进行中无法进入设置（enter_settings 仅在菜单态有效）
        app.menu_logic.selected_index = 0
        app.menu_logic.handle_key("confirm")  # 开始游戏
        assert app.game.state == GameState.PLAYING
        assert app.game.enter_settings() is False
        assert app.game.state == GameState.PLAYING


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
