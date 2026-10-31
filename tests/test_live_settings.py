# -*- coding: utf-8 -*-
"""设置实时生效测试。

覆盖"游戏中按 V 打开设置 -> 调整 -> 立即生效"的主链路：
音量写入 SoundManager、难度改变蛇的移动间隔、ESC 取消回滚实时预览。
"""

import os
import sys

import pygame
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.game import GameState
from snake.utils import Difficulty


def test_in_game_settings_take_effect_immediately(tmp_path, monkeypatch) -> None:
    """游戏内调整设置后立即生效，ESC 取消时回滚到打开前的值。

    断言四条链路：
    1. V 键在 PLAYING 状态直接打开设置面板（本局不中断）；
    2. 音量：左右键与鼠标拖动滑条都立刻改变 SoundManager 主音量与 config；
    3. 难度：切到困难后当前移动间隔立刻缩短，得分倍率同步为 1.5；
    4. ESC：回到进行中，音量与难度回滚到打开面板时的快照。
    """
    monkeypatch.chdir(tmp_path)  # 隔离：本测试不写 settings.json 到项目根目录
    pygame.init()
    from snake.main import Application, build_config, parse_args

    app = Application(build_config(parse_args(["--width", "600", "--height", "480"])))
    app.game.new_game()
    assert app.game.state == GameState.PLAYING
    interval_normal = app.game.current_move_interval()

    # 1. V 键就地打开设置：状态切到 SETTINGS，本局仍在（蛇没被丢弃）
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_v))
    app.process_events()
    assert app.game.state == GameState.SETTINGS
    assert app.game.settings_from_game is True
    panel = app.settings_panel
    assert panel is not None

    # 2a. 音量：左键 70% -> 60%，主音量与 config 立即同步（无需回车）
    panel.handle_key("left")
    assert panel.volume == 60
    assert app.sound.master_volume == pytest.approx(0.6)
    assert app.config.sound_volume == pytest.approx(0.6)

    # 2b. 音量：拖动滑条到轨道最右端，音量立刻升到 100%
    track = app.menu.volume_track_rect(panel)
    drag_pos = (track.right, track.centery)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=drag_pos))
    pygame.event.post(
        pygame.event.Event(pygame.MOUSEMOTION, pos=drag_pos, buttons=(1, 0, 0))
    )
    app.process_events()
    assert panel.volume == 100
    assert app.sound.master_volume == pytest.approx(1.0)
    assert app.config.sound_volume == pytest.approx(1.0)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=drag_pos))
    app.process_events()

    # 3. 难度：普通 -> 困难，移动间隔立刻缩短，得分倍率同步
    panel.handle_key("down")  # 选中"难度"
    assert panel.selected_action == "difficulty"
    panel.handle_key("right")
    assert app.config.difficulty == Difficulty.HARD
    assert app.game.current_move_interval() == pytest.approx(Difficulty.HARD.move_interval)
    assert app.game.current_move_interval() < interval_normal
    assert app.game.score_manager.multiplier == pytest.approx(Difficulty.HARD.score_multiplier)

    # 4. ESC 取消：回到进行中，实时预览的音量与难度全部回滚
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    app.process_events()
    assert app.game.state == GameState.PLAYING
    assert app.settings_panel is None
    assert app.sound.master_volume == pytest.approx(0.7)
    assert app.config.sound_volume == pytest.approx(0.7)
    assert app.config.difficulty == Difficulty.NORMAL
    assert app.game.current_move_interval() == pytest.approx(interval_normal)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
