# -*- coding: utf-8 -*-
"""Bug 修复回归测试。

覆盖两个已知小 bug 的修复效果：
1. 分数清零：游戏进行中 HUD（得分/最高分/长度/时间）从未接入渲染，
   玩家全程看不到分数；现在顶栏随战场一起渲染，
   分数变化会触发顶栏条带重绘。
2. 皮肤残留：游戏中按 S 或菜单 ←/→ 切换皮肤后不写 settings.json，
   重启后旧皮肤残留回来；现在任何通路的换肤都会即时持久化。

全部在临时目录中进行，不污染项目根目录的 settings.json / highscore.json。
"""

import json
import os
import sys

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.config import HUD_HEIGHT
from snake.main import Application
from snake.skin import SKIN_NEON
from snake.utils import Config


def _build_app(tmp_path, monkeypatch) -> Application:
    """在临时目录中创建 headless Application（数据文件均落在临时目录）。"""
    monkeypatch.chdir(tmp_path)
    pygame.init()
    return Application(Config(window_width=400, window_height=300))


class TestHudVisibleDuringPlay:
    """修复"游戏进行中看不到分数"：HUD 接入战场渲染。"""

    def test_hud_drawn_and_dirty_on_score_change(self, tmp_path, monkeypatch) -> None:
        """顶栏随战场渲染；分数变化时增量渲染的脏矩形覆盖顶栏条带。"""
        app = _build_app(tmp_path, monkeypatch)
        app._start_game()
        game = app.game

        # 第一帧：整屏重绘（含 HUD），顶栏区域不再是纯网格背景
        app.update(1 / 60)
        app.render()
        corner = app.screen.surface.get_at((app.screen.rect.width - 5, 5))[:3]
        assert corner != (18, 18, 24)  # 纯背景是 (18,18,24)，顶栏画了半透明遮罩

        # 两次移动之间的静止帧：没有变化就不提交
        assert app.play_renderer.render(game) == []

        # 分数变化（模拟吃到食物）：顶栏签名改变 → 产生脏矩形并覆盖顶栏
        game.score_manager.score = 55
        dirty = app.play_renderer.render(game)
        assert dirty, "分数变化后顶栏必须重绘"
        assert any(rect.top < HUD_HEIGHT for rect in dirty)

        # 再渲染一帧：签名已同步，回到"无变化不提交"
        assert app.play_renderer.render(game) == []

        # 整秒时间变化同样触发顶栏重绘
        game.stats.elapsed += 1.0
        dirty = app.play_renderer.render(game)
        assert dirty and any(rect.top < HUD_HEIGHT for rect in dirty)


class TestSkinPersistedOnChange:
    """修复"皮肤残留"：换肤后即时写入 settings.json，重启后不回退。"""

    def test_skin_change_persists_and_survives_restart(self, tmp_path, monkeypatch) -> None:
        """菜单换肤 → settings.json 立即更新 → 新实例恢复新皮肤。"""
        app = _build_app(tmp_path, monkeypatch)
        settings_path = os.path.join(str(tmp_path), "settings.json")

        # 菜单 ←/→ 换肤（走 set_skin -> on_skin_change 通路）
        app.menu_logic.set_skin(SKIN_NEON)
        assert app.skin_manager.current.name == SKIN_NEON
        with open(settings_path, encoding="utf-8") as fh:
            assert json.load(fh)["skin"] == SKIN_NEON

        # 游戏内按 S 换肤同样持久化（皮肤切换只有这一条回调通路）
        app._start_game()
        app.menu_logic.set_skin(app.skin_manager.next().name)
        with open(settings_path, encoding="utf-8") as fh:
            saved = json.load(fh)["skin"]
        assert saved == app.skin_manager.current.name

        # 重启：不再残留旧皮肤
        reloaded = _build_app(tmp_path, monkeypatch)
        assert reloaded.skin_manager.current.name == saved
        # 菜单标签同步显示新皮肤
        assert saved in reloaded.menu_logic.items[reloaded.menu_logic.skin_index][0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
