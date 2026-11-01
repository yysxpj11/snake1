# -*- coding: utf-8 -*-
"""核心逻辑测试（一）：蛇的移动方向控制、食物生成范围与三档难度速度差异。

覆盖场景：
1. 上下左右四个方向的单位向量与实际移动结果
2. 方向输入缓冲（拒绝 180 度掉头、按顺序消费转向请求）
3. 食物生成位置必须落在网格有效范围内且避开蛇身
4. 三档难度的移动间隔排序与实际步进速度差异

本测试不依赖 pygame 显示层，纯逻辑可 headless 运行。
"""

import os
import sys

import pytest

# 保证从项目根目录可导入 snake 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.config import DIFFICULTY_MOVE_INTERVALS
from snake.food import FoodManager, FoodType
from snake.game import Game
from snake.snake import Direction, Snake, WallMode
from snake.utils import Config, Difficulty


# ---------------------------------------------------------------------------
# 测试 1：蛇的移动方向控制（上下左右）
# ---------------------------------------------------------------------------


class TestDirectionControl:
    """验证四个方向的控制：向量、移动结果、转向缓冲。"""

    @pytest.mark.parametrize(
        "name, vector",
        [
            ("up", (0, -1)),
            ("down", (0, 1)),
            ("left", (-1, 0)),
            ("right", (1, 0)),
        ],
    )
    def test_direction_vectors(self, name: str, vector: tuple) -> None:
        """每个方向的单位向量必须与网格坐标约定一致（y 向下为正）。"""
        assert Direction(name).vector == vector

    @pytest.mark.parametrize(
        "name, expected_head",
        [
            ("up", (5, 4)),
            ("down", (5, 6)),
            ("left", (4, 5)),
            ("right", (6, 5)),
        ],
    )
    def test_move_in_each_direction(self, name: str, expected_head: tuple) -> None:
        """蛇按指定方向前进一格后，蛇头必须落在正确的相邻格子。"""
        snake = Snake(start=(5, 5), length=3, direction=name)
        assert snake.head_position == (5, 5)
        new_head = snake.move(40, 30)
        assert new_head == expected_head
        assert snake.head_position == expected_head
        assert snake.length == 3  # 未生长时长度不变

    def test_queue_all_four_directions_in_sequence(self) -> None:
        """连续输入的合法转向按先进先出顺序逐次生效。"""
        snake = Snake(start=(5, 5), length=3, direction="right")
        # 右 -> 上 -> 左：两次合法转向全部入队
        assert snake.queue_direction(Direction.UP) is True
        assert snake.queue_direction(Direction.LEFT) is True
        # 第一次移动消费 UP：头 (5,4)
        assert snake.move(40, 30) == (5, 4)
        assert snake.direction is Direction.UP
        # 第二次移动消费 LEFT：头 (4,4)
        assert snake.move(40, 30) == (4, 4)
        assert snake.direction is Direction.LEFT

    @pytest.mark.parametrize("name", ["up", "down", "left", "right"])
    def test_opposite_turn_rejected_for_every_direction(self, name: str) -> None:
        """任意方向下，180 度掉头请求都必须被拒绝。"""
        snake = Snake(start=(5, 5), length=3, direction=name)
        assert snake.queue_direction(snake.direction.opposite) is False
        assert snake.direction is Direction(name)  # 方向未被篡改

    def test_game_handle_direction_forwards_to_snake(self) -> None:
        """Game 层的方向输入转发给蛇：合法转向被接受，掉头被拒绝。"""
        game = Game(config=Config(window_width=200, window_height=200, cell_size=20), seed=11)
        game.new_game()
        assert game.handle_direction(Direction.UP) is True
        assert game.handle_direction(Direction.DOWN) is False  # UP 的反向被拒绝
        # 消费掉 UP 后当前方向就是 UP，DOWN 仍是反向、LEFT 可正常入队
        game.snake.move(game.config.grid_columns, game.config.grid_rows)
        assert game.snake.direction is Direction.UP
        assert game.handle_direction(Direction.DOWN) is False
        assert game.handle_direction(Direction.LEFT) is True


# ---------------------------------------------------------------------------
# 测试 2：食物生成位置在有效范围内
# ---------------------------------------------------------------------------


class TestFoodSpawnRange:
    """验证食物生成始终落在网格内、避开蛇身且不重叠。"""

    def test_spawn_positions_always_within_grid(self) -> None:
        """多次生成食物，坐标必须始终满足 0 <= x < 列数、0 <= y < 行数。"""
        columns, rows = 24, 18
        manager = FoodManager(columns, rows, seed=123)
        for _ in range(60):
            food = manager.spawn_normal([])
            assert food is not None
            x, y = food.position
            assert 0 <= x < columns
            assert 0 <= y < rows
            manager.remove_at(food.position)

    def test_spawn_avoids_blocked_cells(self) -> None:
        """连续生成的多个食物彼此不重叠，且全部避开蛇身（blocked）格子。"""
        columns, rows = 15, 12
        blocked = [(0, 0), (1, 0), (2, 0), (0, 1)]
        manager = FoodManager(columns, rows, seed=7)
        foods = []
        for _ in range(20):
            food = manager.spawn_normal(blocked)
            assert food is not None
            assert food.position not in blocked
            # 与场上已存在的其他食物不重叠
            assert all(food.position != other.position for other in foods)
            foods.append(food)

    def test_game_food_stays_inside_playfield(self) -> None:
        """Game 一局内反复补充的食物都应在战场范围内。"""
        config = Config(window_width=240, window_height=200, cell_size=20)
        game = Game(config=config, seed=5)
        game.new_game()
        columns, rows = game.config.grid_columns, game.config.grid_rows
        for _ in range(30):
            game.food_manager.clear()
            game.food_manager.spawn_normal(game.snake.positions())
            food = game.food_manager.normal_food
            assert food is not None
            assert food.ftype == FoodType.NORMAL
            x, y = food.position
            assert 0 <= x < columns
            assert 0 <= y < rows
            # 且不与蛇身重叠
            assert food.position not in game.snake.occupied_set()

    def test_spawn_returns_none_when_grid_full(self) -> None:
        """网格被完全占满时，spawn_normal 应返回 None 而非死循环或越界。"""
        columns, rows = 4, 3
        manager = FoodManager(columns, rows, seed=2)
        blocked = [(x, y) for x in range(columns) for y in range(rows)]
        assert manager.spawn_normal(blocked) is None


# ---------------------------------------------------------------------------
# 测试 3：三档难度的速度差异
# ---------------------------------------------------------------------------


class TestDifficultySpeedDifference:
    """验证三档难度的移动间隔单调递减，且实际体现在步进速度上。"""

    def test_move_intervals_strictly_ordered(self) -> None:
        """配置表中三档间隔必须严格递减：简单 > 普通 > 困难。"""
        easy = DIFFICULTY_MOVE_INTERVALS[Difficulty.EASY.value]
        normal = DIFFICULTY_MOVE_INTERVALS[Difficulty.NORMAL.value]
        hard = DIFFICULTY_MOVE_INTERVALS[Difficulty.HARD.value]
        assert easy > normal > hard > 0
        # 枚举属性与配置表一致
        assert Difficulty.EASY.move_interval == easy
        assert Difficulty.NORMAL.move_interval == normal
        assert Difficulty.HARD.move_interval == hard

    def test_game_reads_interval_from_difficulty(self) -> None:
        """Game 的当前移动间隔应直接来自所选难度，无额外偏移。"""
        for difficulty in Difficulty:
            game = Game(config=Config(difficulty=difficulty), seed=1)
            game.new_game()
            assert game.current_move_interval() == difficulty.move_interval

    def test_hard_snake_travels_farther_than_easy_in_same_time(self) -> None:
        """同样的模拟时长内，困难档蛇走的步数必须显著多于简单档。"""

        def simulate_steps(difficulty: Difficulty, seconds: float) -> int:
            game = Game(config=Config(difficulty=difficulty), seed=1)
            # 穿墙模式，避免蛇撞墙死亡导致步数被封顶
            game.new_game(wall_mode=WallMode.WRAP)
            accumulator = 0.0
            frame_dt = 1 / 60
            for _ in range(int(seconds / frame_dt)):
                accumulator = game.step(frame_dt, accumulator)
            return game.snake.move_count

        easy_steps = simulate_steps(Difficulty.EASY, 10.0)
        normal_steps = simulate_steps(Difficulty.NORMAL, 10.0)
        hard_steps = simulate_steps(Difficulty.HARD, 10.0)
        # 10 秒内：简单约 62 格、普通约 83 格、困难约 117 格
        assert easy_steps < normal_steps < hard_steps
        # 步数应与间隔换算结果接近（允许 ±2 格误差）
        assert abs(easy_steps - 10.0 / Difficulty.EASY.move_interval) <= 2
        assert abs(hard_steps - 10.0 / Difficulty.HARD.move_interval) <= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
