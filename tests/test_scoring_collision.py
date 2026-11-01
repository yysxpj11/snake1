# -*- coding: utf-8 -*-
"""核心逻辑测试（二）：计分逻辑与碰撞判定。

覆盖场景：
1. 吃到普通食物：得分增加（基础分 SCORE_PER_FOOD）、蛇身长度 +1
2. 难度加成：同一食物在不同难度倍率下结算得分不同（简单 0.8 / 普通 1.0 / 困难 1.5）
3. 碰撞判定：四边撞墙、咬到自己，以及 Game 层的死亡流程

本测试不依赖 pygame 显示层，纯逻辑可 headless 运行。
"""

import os
import sys
import tempfile

import pytest

# 保证从项目根目录可导入 snake 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.config import SCORE_PER_FOOD
from snake.food import Food, FoodType
from snake.game import Game, GameState, ScoreManager
from snake.snake import Direction, Segment, Snake, WallMode
from snake.utils import Config, Difficulty, HighScoreStore


# ---------------------------------------------------------------------------
# 测试 1：计分逻辑
# ---------------------------------------------------------------------------


class TestScoringLogic:
    """验证吃食物得分与难度倍率加成。"""

    def test_eating_food_adds_base_score_and_one_length(self) -> None:
        """端到端：蛇吃到普通食物后得分 +SCORE_PER_FOOD、长度 +1。"""
        config = Config(window_width=200, window_height=200, cell_size=20)
        game = Game(config=config, seed=7)
        game.new_game()
        assert game.score == 0

        # 白盒方式：把普通食物直接放在蛇头前进方向上，专注验证吃食物结算
        head = game.snake.head_position
        target = (head[0] + 1, head[1])
        game.food_manager.clear()
        game.food_manager.foods.append(Food(position=target, ftype=FoodType.NORMAL))
        game.snake.growth_pending = 0
        old_length = game.snake.length

        game.step(1.0, 0.0)  # 大步长确保本帧至少移动一格并吃到食物

        assert game.score == SCORE_PER_FOOD
        assert game.snake.length == old_length + 1
        assert game.stats.foods_eaten == 1

    def test_score_manager_scales_by_multiplier(self) -> None:
        """ScoreManager 按倍率缩放基础分：0.8 / 1.0 / 1.5。"""
        assert ScoreManager(multiplier=1.0).register_eat(10) == 10
        assert ScoreManager(multiplier=0.8).register_eat(10) == 8
        assert ScoreManager(multiplier=1.5).register_eat(10) == 15

    @pytest.mark.parametrize(
        "difficulty, expected_gain",
        [
            (Difficulty.EASY, int(SCORE_PER_FOOD * 0.8)),
            (Difficulty.NORMAL, SCORE_PER_FOOD),
            (Difficulty.HARD, int(SCORE_PER_FOOD * 1.5)),
        ],
    )
    def test_difficulty_score_bonus(
        self, difficulty: Difficulty, expected_gain: int
    ) -> None:
        """同一颗普通食物，难度越高得分越高：简单 < 普通 < 困难。"""
        config = Config(difficulty=difficulty, window_width=200, window_height=200, cell_size=20)
        game = Game(config=config, seed=7)
        game.new_game()
        head = game.snake.head_position
        game.food_manager.clear()
        game.food_manager.foods.append(
            Food(position=(head[0] + 1, head[1]), ftype=FoodType.NORMAL)
        )
        game.step(1.0, 0.0)
        assert game.score == expected_gain

    def test_hard_earns_more_than_easy_for_same_food(self) -> None:
        """直接对比：吃同样的食物，困难档的得分必须高于简单档。"""
        scores = {}
        for difficulty in (Difficulty.EASY, Difficulty.HARD):
            config = Config(
                difficulty=difficulty, window_width=200, window_height=200, cell_size=20
            )
            game = Game(config=config, seed=7)
            game.new_game()
            head = game.snake.head_position
            game.food_manager.clear()
            game.food_manager.foods.append(
                Food(position=(head[0] + 1, head[1]), ftype=FoodType.NORMAL)
            )
            game.step(1.0, 0.0)
            scores[difficulty] = game.score
        assert scores[Difficulty.HARD] > scores[Difficulty.EASY]


# ---------------------------------------------------------------------------
# 测试 2：碰撞判定
# ---------------------------------------------------------------------------


class TestCollisionDetection:
    """验证撞墙与撞自己的判定，以及 Game 层的死亡流程。"""

    @pytest.mark.parametrize(
        "direction, start, expected_next",
        [
            ("left", (0, 5), (-1, 5)),   # 左墙
            ("right", (39, 5), (40, 5)),  # 右墙（40 列网格）
            ("up", (5, 0), (5, -1)),      # 上墙
            ("down", (5, 29), (5, 30)),   # 下墙（30 行网格）
        ],
    )
    def test_wall_death_on_all_four_sides(
        self, direction: str, start: tuple, expected_next: tuple
    ) -> None:
        """四条边任意一边撞墙都判死，死亡原因为"撞墙"。"""
        snake = Snake(start=start, length=2, direction=direction, wall_mode=WallMode.SOLID)
        assert snake.next_head_position() == expected_next  # 下一步越界
        snake.move(40, 30)
        assert snake.check_death(40, 30) == "撞墙"
        assert snake.alive is False
        assert snake.death_reason == "撞墙"

    def test_wrap_mode_never_dies_on_wall(self) -> None:
        """穿墙模式下越过边界应环绕而非死亡。"""
        snake = Snake(start=(0, 5), length=2, direction="left", wall_mode=WallMode.WRAP)
        snake.move(40, 30)
        assert snake.head_position == (39, 5)
        assert snake.check_death(40, 30) is None
        assert snake.alive is True

    def test_hits_self_detects_body_cells(self) -> None:
        """hits_self 对身体格子返回 True、空格子返回 False。"""
        snake = Snake(start=(0, 0), length=1, direction="right")
        snake.body.clear()
        for pos in [(3, 1), (2, 1), (1, 1), (1, 2), (2, 2)]:
            snake.body.append(Segment(pos))
        assert snake.hits_self((2, 1)) is True   # 身体格子
        assert snake.hits_self((3, 1)) is False  # 头部自身不算障碍（只检查 segments[1:]）
        assert snake.hits_self((9, 9)) is False  # 空格子

    def test_self_bite_death_reason(self) -> None:
        """蛇头走进身体时判死，死亡原因为"咬到自己"。"""
        # 构造一条蛇：头 (4,5) 向右走，新头 (5,5) 正好是身体第 2 节
        snake = Snake(start=(0, 0), length=1, direction="right")
        snake.body.clear()
        for pos in [(4, 5), (5, 5), (5, 4), (4, 4)]:
            snake.body.append(Segment(pos))
        snake.move(40, 30)  # 新头 (5,5)
        assert snake.check_death(40, 30) == "咬到自己"
        assert snake.alive is False

    def test_game_over_on_wall_hit(self) -> None:
        """Game 层：蛇一路向右撞上右墙后进入 GAME_OVER，原因"撞墙"。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = HighScoreStore(directory=tmpdir)
            config = Config(window_width=200, window_height=200, cell_size=20)
            game = Game(config=config, seed=3, store=store)
            game.new_game()  # 10x10 网格，蛇头居中 (5,5) 向右
            accumulator = 0.0
            for _ in range(20):
                accumulator = game.step(0.5, accumulator)
                if game.state == GameState.GAME_OVER:
                    break
            assert game.state == GameState.GAME_OVER
            assert game.stats.death_reason == "撞墙"
            assert game.snake.alive is False

    def test_game_over_on_self_bite(self) -> None:
        """Game 层：蛇头撞进自己身体后进入 GAME_OVER，原因"咬到自己"。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = HighScoreStore(directory=tmpdir)
            config = Config(window_width=200, window_height=200, cell_size=20)
            game = Game(config=config, seed=3, store=store)
            game.new_game()
            # 白盒构造：头 (4,5) 向右走，新头 (5,5) 是身体第 2 节
            game.snake.body.clear()
            for pos in [(4, 5), (5, 5), (5, 4), (4, 4)]:
                game.snake.body.append(Segment(pos))
            game.step(1.0, 0.0)
            assert game.state == GameState.GAME_OVER
            assert game.stats.death_reason == "咬到自己"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
