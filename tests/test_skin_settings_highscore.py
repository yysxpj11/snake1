# -*- coding: utf-8 -*-
"""状态与界面测试（二）：皮肤颜色应用、settings.json 读写、高分榜存取。

补充既有测试未覆盖的分支：
1. 换肤后 Screen 网格背景与渲染器取到的颜色真正变为新皮肤配色；
2. 三套内置皮肤的配色与文档值逐一相符；
3. settings.json 只写部分字段时的容错加载与补全保存；
4. 高分榜记录结构（score/date 字段）、降序排列与 0 分忽略规则。

测试在临时目录中运行，不触碰真实数据文件。
"""

import json
import os
import sys

import pytest

# 保证从项目根目录可导入 snake 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.highscore import HIGHSCORE_FILENAME, HighScoreManager
from snake.settings import (
    DEFAULT_DIFFICULTY,
    DEFAULT_SOUND_VOLUME,
    SETTINGS_FILENAME,
    SettingsManager,
)
from snake.skin import SKIN_CLASSIC, SKIN_FLAME, SKIN_NEON, SkinManager, build_builtin_skins


# ---------------------------------------------------------------------------
# 测试 1：皮肤切换后颜色正确应用
# ---------------------------------------------------------------------------


class TestSkinColorApplication:
    """验证换肤后屏幕背景、网格线与渲染器取色全部切换为新皮肤。"""

    def test_builtin_skin_colors_match_documented_values(self) -> None:
        """三套内置皮肤的关键颜色与约定值一致，且互不相同。"""
        skins = {skin.name: skin for skin in build_builtin_skins()}
        assert set(skins) == {SKIN_CLASSIC, SKIN_NEON, SKIN_FLAME}

        # 经典绿：绿头、深灰蓝背景
        assert skins[SKIN_CLASSIC].snake_head == (80, 220, 120)
        assert skins[SKIN_CLASSIC].background == (18, 18, 24)
        # 霓虹蓝：青蓝头、深蓝背景
        assert skins[SKIN_NEON].snake_head == (0, 229, 255)
        assert skins[SKIN_NEON].background == (8, 12, 30)
        # 烈焰橙：橙头、暗棕背景
        assert skins[SKIN_FLAME].snake_head == (255, 140, 0)
        assert skins[SKIN_FLAME].background == (30, 15, 8)

        heads = {skin.snake_head for skin in skins.values()}
        backgrounds = {skin.background for skin in skins.values()}
        assert len(heads) == 3 and len(backgrounds) == 3

    def test_skin_switch_recolors_screen_and_renderer(self, tmp_path, monkeypatch) -> None:
        """Application 中切换皮肤：网格背景像素、渲染器取色、落盘配置同步变化。"""
        import pygame

        pygame.init()  # Application 需要字体子系统
        monkeypatch.chdir(tmp_path)  # 换肤会写 settings.json，隔离到临时目录
        from snake.main import Application, build_config, parse_args

        app = Application(build_config(parse_args(["--width", "400", "--height", "400"])))
        assert app.skin_manager.current.name == SKIN_CLASSIC

        def grid_background_pixel(app):
            """采样网格背景 Surface 内部一点（避开 x=0/y=0 的网格线）。"""
            pixel = app.screen._grid_surface.get_at((19, 19))
            return (pixel.r, pixel.g, pixel.b)

        # 初始：经典绿的深灰蓝背景
        assert grid_background_pixel(app) == (18, 18, 24)
        assert app.play_renderer.skin_manager.current.snake_head == (80, 220, 120)

        # 切换到霓虹蓝：背景、渲染器取色、菜单标签全部跟随
        app._on_skin_change(SKIN_NEON)
        assert app.skin_manager.current.name == SKIN_NEON
        assert grid_background_pixel(app) == (8, 12, 30)
        assert app.play_renderer.skin_manager.current.snake_head == (0, 229, 255)
        # 菜单标签同步由菜单/S 键通路的 set_skin 负责（见 test_skin.py），
        # _on_skin_change 本身只管 SkinManager、屏幕配色与落盘

        # 换肤立即持久化：settings.json 中已写入新皮肤名
        settings_path = os.path.join(str(tmp_path), SETTINGS_FILENAME)
        assert os.path.exists(settings_path)
        with open(settings_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["skin"] == SKIN_NEON

        # 用新皮肤完整渲染一帧不报错（颜色真正参与绘制）
        app.render()

        # 再切到烈焰橙，同样立即生效
        app._on_skin_change(SKIN_FLAME)
        assert grid_background_pixel(app) == (30, 15, 8)
        assert app.play_renderer.skin_manager.current.snake_head == (255, 140, 0)

    def test_skin_manager_invalid_name_keeps_current(self) -> None:
        """切换到不存在的皮肤名时保持原皮肤，颜色不受污染。"""
        manager = SkinManager(current=SKIN_NEON)
        assert manager.set_current("不存在的皮肤") is False
        assert manager.current.name == SKIN_NEON
        assert manager.current.snake_head == (0, 229, 255)


# ---------------------------------------------------------------------------
# 测试 2：设置面板读写 settings.json
# ---------------------------------------------------------------------------


class TestSettingsJsonReadWrite:
    """验证 settings.json 的部分字段容错与补全保存。"""

    def test_partial_file_fills_missing_keys_with_defaults(self, tmp_path) -> None:
        """文件只含部分字段：已有项恢复，缺失项回退默认；保存后补全全部字段。"""
        path = tmp_path / SETTINGS_FILENAME
        path.write_text(json.dumps({"sound_volume": 0.4}), encoding="utf-8")

        manager = SettingsManager(directory=str(tmp_path))
        assert manager.loaded is True
        assert manager.sound_volume == pytest.approx(0.4)        # 已有项恢复
        assert manager.difficulty == DEFAULT_DIFFICULTY           # 缺失项回退
        assert manager.skin == ""

        # 保存后三个字段全部写齐
        manager.update(volume=0.4, difficulty=DEFAULT_DIFFICULTY, skin=SKIN_CLASSIC)
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["sound_volume"] == pytest.approx(0.4)
        assert data["difficulty"] == DEFAULT_DIFFICULTY
        assert data["skin"] == SKIN_CLASSIC
        assert data["updated"]

        # 新实例读回：三项完整
        reloaded = SettingsManager(directory=str(tmp_path))
        assert reloaded.sound_volume == pytest.approx(0.4)
        assert reloaded.skin == SKIN_CLASSIC

    def test_default_values_when_no_file(self, tmp_path) -> None:
        """无配置文件时全部取默认值（音量/难度/皮肤）。"""
        manager = SettingsManager(directory=str(tmp_path))
        assert manager.loaded is False
        assert manager.sound_volume == pytest.approx(DEFAULT_SOUND_VOLUME)
        assert manager.difficulty == DEFAULT_DIFFICULTY
        assert manager.skin == ""


# ---------------------------------------------------------------------------
# 测试 3：高分榜保存与读取
# ---------------------------------------------------------------------------


class TestHighScoreSaveLoad:
    """验证高分榜记录结构、排序与边界写入规则。"""

    def test_records_sorted_desc_with_dates(self, tmp_path) -> None:
        """多条记录按分数降序排列，score/date 字段完整，重启后顺序保持。"""
        manager = HighScoreManager(directory=str(tmp_path))
        manager.add_score(50, date="2026-01-01 10:00")
        manager.add_score(120, date="2026-01-02 11:30")
        manager.add_score(80, date="2026-01-03 09:15")

        records = manager.records
        assert [rec["score"] for rec in records] == [120, 80, 50]
        assert records[0]["date"] == "2026-01-02 11:30"
        assert records[1]["date"] == "2026-01-03 09:15"
        assert records[2]["date"] == "2026-01-01 10:00"

        # top_scores 按降序截取；count 超过记录数时返回全部
        assert manager.top_scores(2) == [120, 80]
        assert manager.top_scores(99) == [120, 80, 50]
        assert manager.top_scores(0) == []

        # 重新实例化（模拟重启）：顺序与字段一致
        reloaded = HighScoreManager(directory=str(tmp_path))
        assert [rec["score"] for rec in reloaded.records] == [120, 80, 50]
        assert reloaded.records[1]["date"] == "2026-01-03 09:15"

        # 文件落盘位置与结构正确
        file_path = os.path.join(str(tmp_path), HIGHSCORE_FILENAME)
        assert os.path.exists(file_path)
        with open(file_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        assert payload["best_score"] == 120
        assert len(payload["records"]) == 3

    def test_zero_and_negative_scores_ignored(self, tmp_path) -> None:
        """0 分与负分不进入榜单，但保存动作本身不报错。"""
        manager = HighScoreManager(directory=str(tmp_path))
        assert manager.add_score(0) is False
        assert manager.add_score(-5) is False
        assert manager.records == []
        assert manager.best_score() == 0
        # 之后正常成绩不受影响
        assert manager.add_score(30) is True
        assert manager.top_scores(3) == [30]

    def test_load_drops_malformed_record_entries(self, tmp_path) -> None:
        """文件里混入非法记录（score 非数字）时剔除，合法记录保留。"""
        path = tmp_path / HIGHSCORE_FILENAME
        path.write_text(
            json.dumps(
                {
                    "best_score": 66,
                    "records": [
                        {"score": 66, "date": "2026-02-01 08:00"},
                        {"score": "not-a-number", "date": "bad"},
                        {"date": "missing-score"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        manager = HighScoreManager(directory=str(tmp_path))
        # score 非数字的记录被剔除；缺 score 的记录按 0 分保留（当前容错行为）
        assert [rec["score"] for rec in manager.records] == [66, 0]
        assert manager.best_score() == 66


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
