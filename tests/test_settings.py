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

    def test_panel_adjust_volume_difficulty_skin(self) -> None:
        """左右键调整音量/难度/皮肤暂存值：边界裁剪与循环切换。"""
        panel = SettingsPanel(
            volume=0.5,
            difficulty=Difficulty.NORMAL,
            skin="经典绿",
            skin_names=["经典绿", "霓虹蓝", "烈焰橙"],
        )

        # 音量项：右键 +10、左键 -10，到边界裁剪
        panel.handle_key("right")
        assert panel.volume == 60
        panel.handle_key("left")
        assert panel.volume == 50
        for _ in range(6):
            panel.handle_key("left")
        assert panel.volume == 0
        panel.handle_key("left")
        assert panel.volume == 0  # 不为负

        # 难度项：右键 普通 -> 困难 -> 简单（循环）
        panel.handle_key("down")
        assert panel.selected_action == "difficulty"
        panel.handle_key("right")
        assert panel.difficulty == Difficulty.HARD
        panel.handle_key("right")
        assert panel.difficulty == Difficulty.EASY
        panel.handle_key("left")
        assert panel.difficulty == Difficulty.HARD  # 左键从简单回退到困难
        panel.handle_key("left")
        assert panel.difficulty == Difficulty.NORMAL

        # 皮肤项：右键 经典绿 -> 霓虹蓝，左键回退
        panel.handle_key("down")
        assert panel.selected_action == "skin"
        panel.handle_key("right")
        assert panel.skin == "霓虹蓝"
        panel.handle_key("left")
        assert panel.skin == "经典绿"

        # 调整只是暂存：confirm 才把值交给回调
        saved: list = []
        panel.on_save = lambda v, d, s: saved.append((v, d, s))
        panel.handle_key("confirm")
        assert saved == [(panel.volume_ratio, Difficulty.NORMAL, "经典绿")]


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

    def test_settings_adjust_and_save_applies(self) -> None:
        """面板中调整音量/难度/皮肤后回车保存，设置真正生效；ESC 则放弃。"""
        pygame.init()
        from snake.main import Application, build_config, parse_args
        from snake.skin import SKIN_NEON

        app = Application(build_config(parse_args(["--width", "400", "--height", "400"])))
        settings_index = [a for _t, a in app.menu_logic.items].index("settings")
        app.menu_logic.selected_index = settings_index
        app.menu_logic.handle_key("confirm")
        panel = app.settings_panel

        # 调整：音量 70 -> 30，难度 -> 困难，皮肤 -> 霓虹蓝
        panel.handle_key("left")
        panel.handle_key("left")
        panel.handle_key("left")
        panel.handle_key("left")  # 音量 70 -> 30
        assert panel.volume == 30
        panel.handle_key("down")
        panel.handle_key("right")  # 普通 -> 困难
        panel.handle_key("down")
        panel.handle_key("right")  # 经典绿 -> 霓虹蓝

        # 保存前：设置未变
        assert app.config.sound_volume == pytest.approx(0.7)
        assert app.config.difficulty == Difficulty.NORMAL
        assert app.skin_manager.current.name != SKIN_NEON

        # 回车保存：音量/难度/皮肤全部生效并回到菜单
        panel.handle_key("confirm")
        assert app.game.state == GameState.MENU
        assert app.config.sound_volume == pytest.approx(0.3)
        assert app.sound.master_volume == pytest.approx(0.3)
        assert app.config.difficulty == Difficulty.HARD
        assert app.skin_manager.current.name == SKIN_NEON
        # 菜单标签同步刷新
        assert "困难" in app.menu_logic.items[app.menu_logic.difficulty_index][0]
        assert SKIN_NEON in app.menu_logic.items[app.menu_logic.skin_index][0]

        # 再次进入并调整后 ESC：修改被放弃，设置保持上次保存的值
        app.notice = ""
        app.menu_logic.selected_index = settings_index
        app.menu_logic.handle_key("confirm")
        app.settings_panel.handle_key("right")  # 音量 30 -> 40
        assert app.settings_panel.volume == 40
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        app.process_events()
        assert app.game.state == GameState.MENU
        assert app.config.sound_volume == pytest.approx(0.3)  # 未被 40 覆盖


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
