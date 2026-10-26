# -*- coding: utf-8 -*-
"""贪吃蛇游戏 pytest 测试套件。

覆盖三大核心场景：
1. 蛇的移动与转向
2. 食物生成与吃食物结算
3. 碰撞判定与游戏结束流程

本测试不依赖 pygame 显示层，纯逻辑可 headless 运行。
"""

import os
import sys
import tempfile

import pytest

# 保证从项目根目录可导入 snake 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.food import Food, FoodManager, FoodType
from snake.game import Game, GameState, ScoreManager
from snake.snake import Direction, Snake, WallMode
from snake.utils import Config, HighScoreStore


# ---------------------------------------------------------------------------
# 测试 1：蛇移动与转向
# ---------------------------------------------------------------------------


class TestSnakeMovement:
    """验证蛇的移动、转向缓冲与生长行为。"""

    def test_snake_moves_right_and_turns(self) -> None:
        """蛇默认向右移动一格；转向缓冲允许合法转向、拒绝 180 度掉头。"""
        snake = Snake(start=(10, 10), length=3, direction="right")
        assert snake.head_position == (10, 10)

        # 向右前进一格
        new_head = snake.move(40, 30)
        assert new_head == (11, 10)
        assert snake.length == 3  # 未生长时长度不变

        # 合法转向：向上
        assert snake.queue_direction(Direction.UP) is True
        new_head = snake.move(40, 30)
        assert new_head == (11, 9)

        # 180 度掉头被拒绝
        assert snake.queue_direction(snake.direction.opposite) is False

    def test_snake_grows_after_grow_call(self) -> None:
        """调用 grow 后，蛇在后续移动中逐步增长。"""
        snake = Snake(start=(5, 5), length=3, direction="right")
        snake.grow(2)
        snake.move(40, 30)
        assert snake.length == 4  # 第一次移动长 1
        snake.move(40, 30)
        assert snake.length == 5  # 第二次移动再长 1
        snake.move(40, 30)
        assert snake.length == 5  # 生长完毕后长度稳定

    def test_snake_wrap_mode_teleports_across_wall(self) -> None:
        """穿墙模式下，越界坐标应环绕到另一侧。"""
        snake = Snake(start=(39, 15), length=2, direction="right", wall_mode=WallMode.WRAP)
        new_head = snake.move(40, 30)
        assert new_head == (0, 15)  # 从右边穿到左边


# ---------------------------------------------------------------------------
# 测试 2：食物生成与进食结算
# ---------------------------------------------------------------------------


class TestFoodAndScoring:
    """验证食物生成规则与得分结算。"""

    def test_food_manager_spawns_on_empty_cell(self) -> None:
        """普通食物必须生成在空闲格子且不与蛇身重叠。"""
        manager = FoodManager(20, 15, seed=42)
        blocked = [(0, 0), (1, 0), (2, 0)]
        food = manager.spawn_normal(blocked)
        assert food is not None
        assert food.ftype == FoodType.NORMAL
        assert food.position not in blocked
        assert 0 <= food.position[0] < 20
        assert 0 <= food.position[1] < 15

    def test_remove_at_returns_food_and_clears_cell(self) -> None:
        """remove_at 移除指定格子的食物；重复移除返回 None。"""
        manager = FoodManager(10, 10, seed=1)
        food = manager.spawn_normal([])
        assert food is not None
        cell = food.position
        picked = manager.remove_at(cell)
        assert picked is food
        assert manager.food_at(cell) is None
        assert manager.remove_at(cell) is None

    def test_score_manager_combo_bonus_increases_score(self) -> None:
        """连击窗口内连续进食应获得更高得分。"""
        sm = ScoreManager(multiplier=1.0)
        first = sm.register_eat(10)
        sm.tick(0.1)  # 不超出连击窗口
        second = sm.register_eat(10)
        assert first == 10
        assert second > 10  # 连击加成生效
        assert sm.combo_active

    def test_game_eating_food_increases_score_and_length(self) -> None:
        """端到端：Game 中蛇吃到食物后分数增加、蛇变长。"""
        config = Config(window_width=200, window_height=200, cell_size=20)
        game = Game(config=config, seed=7)
        game.new_game()
        assert game.state == GameState.PLAYING
        assert game.score == 0

        # 白盒方式：清空食物，把普通食物直接放在蛇头前进方向上，
        # 专注验证“吃食物 -> 加分 -> 变长”的完整链路
        from snake.food import Food as FoodEntity

        head = game.snake.head_position
        target = (head[0] + 1, head[1])
        game.food_manager.clear()
        game.food_manager.foods.append(FoodEntity(position=target, ftype=FoodType.NORMAL))
        game.snake.growth_pending = 0
        game.handle_direction(Direction.RIGHT) if game.snake.direction.value != "right" else None
        old_length = game.snake.length
        game.step(1.0, 0.0)  # 大步长确保本帧至少移动一格

        assert game.score > 0
        assert game.stats.foods_eaten == 1
        assert game.snake.length == old_length + 1


# ---------------------------------------------------------------------------
# 测试 3：碰撞判定与游戏结束
# ---------------------------------------------------------------------------


class TestCollisionAndGameOver:
    """验证撞墙、自撞与游戏结束流程。"""

    def test_solid_wall_death(self) -> None:
        """SOLID 模式下蛇撞墙应死亡并标记原因。"""
        snake = Snake(start=(0, 0), length=2, direction="left", wall_mode=WallMode.SOLID)
        nxt = snake.next_head_position()
        assert nxt == (-1, 0)  # 越界
        snake.move(40, 30)
        reason = snake.check_death(40, 30)
        assert reason == "撞墙"
        assert snake.alive is False

    def test_self_collision_death(self) -> None:
        """蛇咬到自己身体时判定死亡。"""
        # 构造一条 U 形蛇：头在 (3,1)，身体回折
        snake = Snake(start=(0, 0), length=1, direction="right")
        snake.body.clear()
        for pos in [(3, 1), (2, 1), (1, 1), (1, 2), (2, 2), (3, 2)]:
            from snake.snake import Segment

            snake.body.appendleft(Segment(pos))
        # 让蛇向右走，新头 (4,1)；先手动把头摆到将撞的位置验证 hits_self
        assert snake.hits_self((2, 1)) is True   # (2,1) 在身体上
        assert snake.hits_self((9, 9)) is False  # 空格子

    def test_game_over_flow_records_score(self) -> None:
        """游戏结束流程：状态切换、统计原因、成绩写入高分榜。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = HighScoreStore(directory=tmpdir)
            config = Config(window_width=200, window_height=200, cell_size=20)
            game = Game(config=config, seed=3, store=store)
            game.new_game()
            # 人为给一点分数再触发死亡
            game.score_manager.score = 55
            game._game_over("测试死亡")
            assert game.state == GameState.GAME_OVER
            assert game.stats.death_reason == "测试死亡"
            info = game.game_over_info()
            assert info["reason"] == "测试死亡"
            assert store.best_score() == 55
            # R 键重开的逻辑由 main 层处理，这里验证 new_game 可恢复
            game.new_game()
            assert game.state == GameState.PLAYING


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
