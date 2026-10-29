# -*- coding: utf-8 -*-
"""暂停 / 继续功能测试。

验证：
1. P 键语义对应的 toggle_pause 能在 PLAYING / PAUSED 间切换；
2. 暂停期间蛇、食物、本局计时全部冻结；
3. 恢复后逻辑继续推进。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.game import Game, GameState
from snake.snake import Direction
from snake.utils import Config, Difficulty


def _make_game() -> Game:
    """构造一个已开始、走稳定随机的小网格游戏，便于断言位置变化。"""
    config = Config(window_width=400, window_height=400, cell_size=20,
                    difficulty=Difficulty.NORMAL)
    game = Game(config=config, seed=2024)
    game.new_game()
    return game


class TestPauseAndResume:
    """验证暂停状态切换与暂停期间的冻结行为。"""

    def test_pause_freezes_updates_and_resume_continues(self) -> None:
        """toggle_pause 切换状态；暂停时蛇/食物/计时冻结，恢复后继续推进。"""
        game = _make_game()
        assert game.state == GameState.PLAYING
        assert game.is_paused is False

        # 正常推进一帧：蛇头移动、用时累加
        accumulator = game.step(0.5, 0.0)
        assert game.stats.elapsed > 0
        assert game.stats.steps >= 1
        head_after_move = game.snake.head_position

        # 暂停：状态切换为 PAUSED
        assert game.toggle_pause() is True
        assert game.state == GameState.PAUSED
        assert game.is_paused is True

        # 暂停期间记录快照
        head_before = game.snake.head_position
        foods_before = [f.position for f in game.food_manager.foods]
        elapsed_before = game.stats.elapsed
        steps_before = game.stats.steps
        accumulator_before = accumulator

        # 连续推进 3 秒：不应有任何变化（蛇不动、食物不变、计时不走）
        for _ in range(5):
            accumulator = game.step(0.6, accumulator)
        assert game.snake.head_position == head_before == head_after_move
        assert [f.position for f in game.food_manager.foods] == foods_before
        assert game.stats.elapsed == elapsed_before
        assert game.stats.steps == steps_before
        assert accumulator == accumulator_before

        # 暂停时方向输入被忽略（转向缓冲队列长度不变）
        pending_before = len(game.snake.pending_directions)
        assert game.handle_direction(Direction.UP) is False
        assert len(game.snake.pending_directions) == pending_before

        # 再按 P 恢复：返回 False 表示已非暂停，逻辑继续推进
        assert game.toggle_pause() is False
        assert game.state == GameState.PLAYING
        assert game.is_paused is False

        game.step(0.6, accumulator)
        assert game.stats.elapsed > elapsed_before
        assert game.stats.steps > steps_before


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
