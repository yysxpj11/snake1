# -*- coding: utf-8 -*-
"""游戏核心逻辑模块。

- ScoreManager: 得分与连击结算
- GameStats: 一局内的统计信息
- Game: 状态机 + 每帧 update，衔接 Snake / FoodManager / UI

本模块不直接创建窗口；渲染交给 ui 模块，入口在 main 模块。
"""

from __future__ import annotations

import random
import time
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .food import Food, FoodManager, FoodType
from .snake import Direction, Snake, WallMode
from .sound import SoundManager
from .utils import Config, HighScoreStore, Timer, clamp


class GameState(Enum):
    """游戏状态机：菜单 / 进行中 / 暂停 / 结束。"""

    MENU = "menu"
    PLAYING = "playing"
    PAUSED = "paused"
    GAME_OVER = "game_over"


class ScoreManager:
    """负责得分累加、连击奖励与分数上限保护。"""

    COMBO_WINDOW = 3.0  # 连击判定窗口（秒）
    COMBO_BONUS_RATIO = 0.5  # 连击加成比例

    def __init__(self, multiplier: float = 1.0) -> None:
        """初始化分数、连击状态与难度倍率。"""
        self.score = 0
        self.combo_count = 0
        self.combo_timer: Optional[Timer] = None
        self.multiplier = multiplier
        self.earned_history: List[int] = []

    def reset(self) -> None:
        """新一局重置得分。"""
        self.score = 0
        self.combo_count = 0
        self.combo_timer = None
        self.earned_history.clear()

    def register_eat(self, base_score: int) -> int:
        """结算一次吃食物，返回实际得分（含连击与难度加成）。"""
        now_bonus = 0
        if self.combo_timer is not None and not self.combo_timer.finished:
            self.combo_count += 1
            now_bonus = int(base_score * self.COMBO_BONUS_RATIO * min(self.combo_count, 5))
        else:
            self.combo_count = 1
        self.combo_timer = Timer(self.COMBO_WINDOW)
        gained = int((base_score + now_bonus) * self.multiplier)
        self.score += gained
        self.earned_history.append(gained)
        return gained

    def tick(self, dt: float) -> None:
        """推进连击窗口计时。"""
        if self.combo_timer is not None:
            self.combo_timer.tick(dt)
            if self.combo_timer.finished:
                self.combo_count = 0

    @property
    def combo_active(self) -> bool:
        """是否处于连击状态。"""
        return self.combo_count > 1 and self.combo_timer is not None and not self.combo_timer.finished

    def combo_label(self) -> str:
        """生成连击提示文本。"""
        if not self.combo_active:
            return ""
        return f"连击 x{self.combo_count}!"


class GameStats:
    """一局游戏的统计信息收集器。"""

    def __init__(self) -> None:
        """初始化各项统计计数。"""
        self.start_time = time.perf_counter()
        self.elapsed = 0.0
        self.foods_eaten = 0
        self.golden_eaten = 0
        self.speed_eaten = 0
        self.steps = 0
        self.death_reason = ""

    def reset(self) -> None:
        """重置全部统计。"""
        self.__init__()

    def register_eat(self, ftype: FoodType) -> None:
        """按食物类型登记一次进食。"""
        self.foods_eaten += 1
        if ftype == FoodType.GOLDEN:
            self.golden_eaten += 1
        elif ftype == FoodType.SPEED:
            self.speed_eaten += 1

    def tick(self, dt: float) -> None:
        """推进本局用时。"""
        self.elapsed += dt

    def summary(self) -> Dict[str, object]:
        """返回统计摘要字典，供结束画面与日志使用。"""
        return {
            "time": round(self.elapsed, 1),
            "foods": self.foods_eaten,
            "golden": self.golden_eaten,
            "speed": self.speed_eaten,
            "steps": self.steps,
            "reason": self.death_reason,
        }


class Game:
    """游戏主控制器：持有全部实体并驱动状态机。"""

    SPEED_BOOST_DIVISOR = 0.6  # 加速期间移动间隔缩短为 60%

    def __init__(
        self,
        config: Optional[Config] = None,
        seed: Optional[int] = None,
        store: Optional[object] = None,
        sound: Optional[SoundManager] = None,
    ) -> None:
        """初始化游戏：配置、实体容器、状态机、高分存储与音效管理器。"""
        self.config = config or Config()
        self.config.clamp_to_window()
        self.rng = random.Random(seed)
        self.store = store or HighScoreStore()
        self.sound = sound
        self.state = GameState.MENU
        self.score_manager = ScoreManager(self.config.difficulty_multiplier())
        self.stats = GameStats()
        self.snake: Optional[Snake] = None
        self.food_manager: Optional[FoodManager] = None
        self.speed_timer: Optional[Timer] = None
        self.wall_mode = WallMode.SOLID
        self.level = 1

    # -- 生命周期 -----------------------------------------------------------

    def new_game(self, level: int = 1, wall_mode: WallMode = WallMode.SOLID) -> None:
        """开始新一局：重置蛇、食物、分数与统计。"""
        self.level = level
        self.wall_mode = wall_mode
        self.snake = Snake(
            start=(self.config.grid_columns // 2, self.config.grid_rows // 2),
            length=3 + min(level - 1, 5),
            direction="right",
            wall_mode=wall_mode,
        )
        self.food_manager = FoodManager(
            self.config.grid_columns, self.config.grid_rows, seed=self.rng.randint(0, 2**30)
        )
        self.food_manager.spawn_normal(self.snake.positions())
        self.score_manager.reset()
        self.stats.reset()
        self.speed_timer = None
        self.state = GameState.PLAYING
        # 游戏开始：播放开场音效（未接入音效时安全跳过）
        if self.sound is not None:
            self.sound.play("start")

    def pause(self) -> bool:
        """进入暂停状态（仅进行中可暂停），返回是否成功暂停。"""
        if self.state == GameState.PLAYING:
            self.state = GameState.PAUSED
            return True
        return False

    def resume(self) -> bool:
        """从暂停恢复到进行中，返回是否成功恢复。"""
        if self.state == GameState.PAUSED:
            self.state = GameState.PLAYING
            return True
        return False

    def toggle_pause(self) -> bool:
        """切换暂停/继续。

        Returns:
            切换后是否处于暂停状态（非进行中/暂停状态调用返回 False）。
        """
        if self.state == GameState.PAUSED:
            self.resume()
            return False
        if self.state == GameState.PLAYING:
            self.pause()
            return True
        return False

    @property
    def is_paused(self) -> bool:
        """当前是否处于暂停状态。"""
        return self.state == GameState.PAUSED

    def back_to_menu(self) -> None:
        """返回主菜单。"""
        self.state = GameState.MENU

    @property
    def score(self) -> int:
        """当前得分快捷属性。"""
        return self.score_manager.score

    @property
    def best_score(self) -> int:
        """历史最高分。"""
        return self.store.best_score()

    # -- 输入 ---------------------------------------------------------------

    def handle_direction(self, direction: Direction) -> bool:
        """转发方向输入给蛇，返回是否被接受。"""
        if self.snake is None or self.state != GameState.PLAYING:
            return False
        return self.snake.queue_direction(direction)

    # -- 核心更新 -----------------------------------------------------------

    def current_move_interval(self) -> float:
        """计算当前实际移动间隔。

        速度参数完全来自设置层：难度决定基础间隔（秒/格），
        关卡提升会让蛇略微加速，加速道具再按倍率缩短。
        """
        # 从难度设置读取基础移动间隔，不再使用硬编码倍率
        interval = self.config.move_interval_for_difficulty
        interval = max(0.05, interval - (self.level - 1) * 0.005)
        if self.speed_timer is not None and not self.speed_timer.finished:
            interval *= self.SPEED_BOOST_DIVISOR
        return interval

    def _move_accumulator(self) -> float:
        """内部使用的移动累加器占位（主循环由外部驱动，见 step）。"""
        return self.current_move_interval()

    def step(self, dt: float, move_accumulator: float) -> float:
        """推进一帧逻辑，返回更新后的移动累加器。

        move_accumulator 达到当前移动间隔时蛇前进一格。
        暂停（PAUSED）状态下直接返回，不做任何推进：
        蛇不移动、食物不计时、本局用时也停止累加。
        """
        if self.state != GameState.PLAYING or self.snake is None or self.food_manager is None:
            return move_accumulator
        self.stats.tick(dt)
        self.score_manager.tick(dt)
        if self.speed_timer is not None:
            self.speed_timer.tick(dt)
        expired = self.food_manager.tick(dt)
        if expired:
            self._ensure_normal_food()
        self.food_manager.maybe_spawn_special(self.snake.positions(), dt)
        move_accumulator += dt
        interval = self.current_move_interval()
        while move_accumulator >= interval:
            move_accumulator -= interval
            self._advance_snake()
            if self.state != GameState.PLAYING:
                break
        return move_accumulator

    def _ensure_normal_food(self) -> None:
        """保证场上始终存在普通食物。"""
        assert self.food_manager is not None and self.snake is not None
        if not self.food_manager.has_normal_food:
            self.food_manager.spawn_normal(self.snake.positions())

    def _advance_snake(self) -> None:
        """蛇前进一格并处理吃食物与死亡判定。"""
        assert self.snake is not None and self.food_manager is not None
        columns, rows = self.config.grid_columns, self.config.grid_rows
        nxt = self.snake.next_head_position()
        x, y = nxt
        if self.wall_mode == WallMode.SOLID and (x < 0 or y < 0 or x >= columns or y >= rows):
            self._game_over("撞墙")
            return
        self.snake.move(columns, rows)
        self.stats.steps += 1
        if self.snake.hits_self():
            self._game_over("咬到自己")
            return
        eaten = self.food_manager.remove_at(self.snake.head_position)
        if eaten is not None:
            self._apply_food_effect(eaten)
        self._ensure_normal_food()

    def _apply_food_effect(self, food: Food) -> None:
        """结算吃到的食物：得分、生长、加速。"""
        assert self.snake is not None
        effect = food.effect()
        gained = self.score_manager.register_eat(effect.score_delta)
        self.snake.grow(effect.growth)
        self.stats.register_eat(food.ftype)
        # 吃到食物：播放进食音效
        if self.sound is not None:
            self.sound.play("eat")
        if effect.speed_boost > 0:
            self.speed_timer = Timer(effect.speed_boost)
        label = self.score_manager.combo_label()
        self.stats.death_reason = ""  # 保持字段干净
        self.last_gain_message = effect.message if not label else f"{effect.message} {label}"

    def _game_over(self, reason: str) -> None:
        """结束本局：登记成绩、记录原因并切换状态。"""
        self.stats.death_reason = reason
        if self.snake is not None:
            self.snake.alive = False
            self.snake.death_reason = reason
        # 撞墙 / 咬到自己：播放游戏结束音效
        if self.sound is not None:
            self.sound.play("game_over")
        self.is_new_record = self.store.is_new_record(self.score)
        if self.score > 0:
            self.store.add_score(self.score)
        self.state = GameState.GAME_OVER

    # -- 查询 ---------------------------------------------------------------

    def speed_effect_ratio(self) -> float:
        """返回加速效果剩余比例，用于渲染光晕。"""
        if self.speed_timer is None or self.speed_timer.finished:
            return 0.0
        return 1.0 - self.speed_timer.ratio()

    def is_running(self) -> bool:
        """游戏是否处于可交互状态（进行中或暂停）。"""
        return self.state in (GameState.PLAYING, GameState.PAUSED)

    def game_over_info(self) -> Dict[str, object]:
        """返回结束画面所需信息字典。"""
        return {
            "score": self.score,
            "best": self.best_score,
            "reason": self.stats.death_reason,
            "record": getattr(self, "is_new_record", False),
            "summary": self.stats.summary(),
        }
