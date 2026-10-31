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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
