# -*- coding: utf-8 -*-
"""设置持久化功能测试。

验证 SettingsManager 的读写往返、损坏容错与非法值回退，
全部在临时目录中进行，不触碰真实工作目录的 settings.json。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.settings import (
    DEFAULT_DIFFICULTY,
    DEFAULT_SOUND_VOLUME,
    SETTINGS_FILENAME,
    SettingsManager,
)


class TestSettingsManager:
    """验证 SettingsManager 的持久化逻辑。"""

    def test_settings_read_write_roundtrip(self, tmp_path) -> None:
        """保存的音量/难度/皮肤三项写入 settings.json，重新加载后完整恢复。"""
        manager = SettingsManager(directory=str(tmp_path))

        # 无文件时：loaded=False，各项为默认值
        assert manager.loaded is False
        assert manager.sound_volume == pytest.approx(DEFAULT_SOUND_VOLUME)
        assert manager.difficulty == DEFAULT_DIFFICULTY
        assert manager.skin == ""

        # 更新三项并保存：文件生成，内容完整
        assert manager.update(volume=0.35, difficulty="hard", skin="霓虹蓝") is True
        assert os.path.exists(manager.path)
        with open(manager.path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["sound_volume"] == pytest.approx(0.35)
        assert data["difficulty"] == "hard"
        assert data["skin"] == "霓虹蓝"
        assert data["updated"]  # 保存时间已记录

        # 新实例重新加载：三项全部恢复
        reloaded = SettingsManager(directory=str(tmp_path))
        assert reloaded.loaded is True
        assert reloaded.sound_volume == pytest.approx(0.35)
        assert reloaded.difficulty == "hard"
        assert reloaded.skin == "霓虹蓝"

        # 单项更新：只改音量，难度与皮肤保持不变
        assert reloaded.update(volume=0.9) is True
        again = SettingsManager(directory=str(tmp_path))
        assert again.sound_volume == pytest.approx(0.9)
        assert again.difficulty == "hard"
        assert again.skin == "霓虹蓝"

    def test_settings_corrupted_and_invalid_values(self, tmp_path) -> None:
        """损坏文件与非法值容错：不抛异常，逐项回退默认值。"""
        # 损坏的 JSON
        bad = tmp_path / SETTINGS_FILENAME
        bad.write_text("{不是合法的JSON", encoding="utf-8")
        manager = SettingsManager(directory=str(tmp_path))
        assert manager.loaded is False
        assert manager.sound_volume == pytest.approx(DEFAULT_SOUND_VOLUME)

        # JSON 合法但各项值非法：音量越界、难度不存在、皮肤非字符串
        bad.write_text(
            json.dumps({"sound_volume": 7.5, "difficulty": "extreme", "skin": 123}),
            encoding="utf-8",
        )
        manager = SettingsManager(directory=str(tmp_path))
        assert manager.loaded is True  # 文件本身可解析
        assert manager.sound_volume == pytest.approx(DEFAULT_SOUND_VOLUME)  # 越界回退
        assert manager.difficulty == DEFAULT_DIFFICULTY  # 未知难度回退
        assert manager.skin == ""  # 非字符串回退

        # update 传入非法值同样被裁剪/回退
        assert manager.update(volume=2.0, difficulty="lunatic") is True
        assert manager.sound_volume == pytest.approx(1.0)  # 裁剪到上界
        assert manager.difficulty == DEFAULT_DIFFICULTY  # 非法难度回退


class TestStartupAutoLoad:
    """验证游戏启动时自动加载上次保存的设置，以及面板保存后的落盘。"""

    def test_startup_loads_saved_settings_and_save_persists(
        self, tmp_path, monkeypatch
    ) -> None:
        """预置 settings.json 启动游戏：音量/难度/皮肤三项自动恢复；
        设置面板保存后新值写回文件，下次启动可再次恢复。"""
        import pygame

        pygame.init()  # Application 需要字体子系统
        from snake.main import Application, build_config, parse_args
        from snake.skin import SKIN_FLAME
        from snake.utils import Difficulty

        # 预置上次保存的设置：音量 25%、困难、烈焰橙
        (tmp_path / SETTINGS_FILENAME).write_text(
            json.dumps(
                {"sound_volume": 0.25, "difficulty": "hard", "skin": SKIN_FLAME}
            ),
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)  # Application 从工作目录读写 settings.json

        app = Application(build_config(parse_args(["--width", "400", "--height", "400"])))

        # 三项设置全部自动恢复
        assert app.config.sound_volume == pytest.approx(0.25)
        assert app.sound.master_volume == pytest.approx(0.25)
        assert app.config.difficulty == Difficulty.HARD
        assert app.skin_manager.current.name == SKIN_FLAME
        # 菜单与设置面板的初值同步为恢复后的设置
        assert app.settings_panel is None  # 尚未打开
        assert app.menu_logic.difficulty == Difficulty.HARD

        # 打开设置面板，把音量调到 35% 并保存：文件同步更新
        settings_index = [a for _t, a in app.menu_logic.items].index("settings")
        app.menu_logic.selected_index = settings_index
        app.menu_logic.handle_key("confirm")
        panel = app.settings_panel
        assert panel.volume == 25
        panel.handle_key("right")  # 25 -> 35
        panel.handle_key("confirm")
        with open(app.settings.path, "r", encoding="utf-8") as fh:
            saved = json.load(fh)
        assert saved["sound_volume"] == pytest.approx(0.35)
        assert saved["difficulty"] == "hard"
        assert saved["skin"] == SKIN_FLAME

        # 再启动一个实例：恢复的是保存后的 35%
        app2 = Application(build_config(parse_args(["--width", "400", "--height", "400"])))
        assert app2.config.sound_volume == pytest.approx(0.35)

    def test_startup_without_file_uses_defaults(self, tmp_path, monkeypatch) -> None:
        """没有 settings.json 时正常启动，各项为默认值。"""
        import pygame

        pygame.init()
        from snake.main import Application, build_config, parse_args
        from snake.skin import SKIN_CLASSIC
        from snake.utils import Difficulty

        monkeypatch.chdir(tmp_path)
        app = Application(build_config(parse_args(["--width", "400", "--height", "400"])))
        assert app.settings.loaded is False
        assert app.config.sound_volume == pytest.approx(0.7)
        assert app.config.difficulty == Difficulty.NORMAL
        assert app.skin_manager.current.name == SKIN_CLASSIC


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
