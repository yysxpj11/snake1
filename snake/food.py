# -*- coding: utf-8 -*-
"""食物模块。

定义游戏中的食物实体与食物管理器：
- FoodType 枚举：普通 / 金色 / 加速 三种食物
- Food 数据类：位置、类型、存在时间
- FoodManager：负责食物生成、过期清理与效果结算

食物模块只依赖 utils，不依赖蛇与界面模块。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from .utils import (
    SPECIAL_FOOD_LIFETIME,
    SCORE_PER_FOOD,
    SCORE_PER_GOLDEN_FOOD,
    SCORE_PER_SPEED_FOOD,
    Timer,
    manhattan_distance,
    random_choice_weighted,
    random_empty_cell,
)


class FoodType(Enum):
    """食物类型枚举。

    NORMAL: 普通红苹果，固定出现。
    GOLDEN: 金色苹果，稀有、高分、限时存在。
    SPEED:  蓝色能量果，短暂提升蛇速。
    """

    NORMAL = "normal"
    GOLDEN = "golden"
    SPEED = "speed"


@dataclass
class FoodEffect:
    """吃下食物后产生的效果描述。

    Attributes:
        score_delta: 得分变化。
        growth: 蛇身增长格数。
        speed_boost: 速度提升持续秒数（0 表示无）。
        message: 展示给玩家的提示文本。
    """

    score_delta: int = 0
    growth: int = 1
    speed_boost: float = 0.0
    message: str = ""

    def merge(self, other: "FoodEffect") -> None:
        """把另一个效果合并进当前效果（用于叠加结算）。"""
        self.score_delta += other.score_delta
        self.growth += other.growth
        self.speed_boost = max(self.speed_boost, other.speed_boost)
        if other.message:
            self.message = other.message


@dataclass
class Food:
    """单个食物实体。

    Attributes:
        position: 网格坐标 (x, y)。
        ftype: 食物类型。
        lifetime: 限时食物的存在计时器，普通食物为 None。
        birth_frame: 生成时的帧计数，用于出生动画。
        value: 该食物的基础分值。
    """

    position: Tuple[int, int]
    ftype: FoodType = FoodType.NORMAL
    lifetime: Optional[Timer] = None
    birth_frame: int = 0
    value: int = SCORE_PER_FOOD

    def __post_init__(self) -> None:
        """根据类型补齐默认分值与限时计时器。"""
        default_scores = {
            FoodType.NORMAL: SCORE_PER_FOOD,
            FoodType.GOLDEN: SCORE_PER_GOLDEN_FOOD,
            FoodType.SPEED: SCORE_PER_SPEED_FOOD,
        }
        if self.value == SCORE_PER_FOOD and self.ftype in default_scores:
            self.value = default_scores[self.ftype]
        if self.ftype != FoodType.NORMAL and self.lifetime is None:
            self.lifetime = Timer(SPECIAL_FOOD_LIFETIME)

    @property
    def is_special(self) -> bool:
        """是否为限时特殊食物。"""
        return self.ftype != FoodType.NORMAL

    @property
    def expired(self) -> bool:
        """限时食物是否已过期。"""
        return self.lifetime is not None and self.lifetime.finished

    def tick(self, dt: float) -> None:
        """推进限时计时器。"""
        if self.lifetime is not None:
            self.lifetime.tick(dt)

    def remaining_ratio(self) -> float:
        """返回限时食物剩余时间比例（普通食物恒为 1）。"""
        if self.lifetime is None:
            return 1.0
        return 1.0 - self.lifetime.ratio()

    def effect(self, multiplier: float = 1.0) -> FoodEffect:
        """结算该食物被吃掉后的效果。"""
        effect_map = {
            FoodType.NORMAL: FoodEffect(
                score_delta=int(self.value * multiplier),
                growth=1,
                message="好吃！",
            ),
            FoodType.GOLDEN: FoodEffect(
                score_delta=int(self.value * multiplier),
                growth=2,
                message="金色大奖！",
            ),
            FoodType.SPEED: FoodEffect(
                score_delta=int(self.value * multiplier),
                growth=1,
                speed_boost=5.0,
                message="加速！",
            ),
        }
        return effect_map.get(self.ftype, FoodEffect())


class FoodManager:
    """管理场上所有食物的生成与生命周期。

    职责：
    1. 保证场上始终有一个普通食物；
    2. 按概率生成限时特殊食物；
    3. 每帧推进食物计时并清理过期食物；
    4. 提供查询接口供碰撞判定使用。
    """

    # 特殊食物生成概率（每秒尝试一次的基准概率）
    GOLDEN_SPAWN_CHANCE = 0.25
    SPEED_SPAWN_CHANCE = 0.30
    MAX_SPECIAL_FOODS = 2

    def __init__(self, columns: int, rows: int, seed: Optional[int] = None) -> None:
        """初始化管理器，columns/rows 为网格尺寸。"""
        self.columns = columns
        self.rows = rows
        self.rng = random.Random(seed)
        self.foods: List[Food] = []
        self.spawn_cooldown = 0.0
        self.total_spawned = 0

    # -- 生成 ---------------------------------------------------------------

    def _occupied_cells(self, extra: Sequence[Tuple[int, int]] = ()) -> List[Tuple[int, int]]:
        """收集所有被食物占用的格子（可附加额外占用）。"""
        cells = [food.position for food in self.foods]
        cells.extend(extra)
        return cells

    def spawn_normal(self, blocked: Sequence[Tuple[int, int]]) -> Optional[Food]:
        """生成一个普通食物，位置避开 blocked（通常是蛇身）。"""
        occupied = self._occupied_cells(blocked)
        cell = random_empty_cell(occupied, self.columns, self.rows, self.rng)
        if cell is None:
            return None
        food = Food(position=cell, ftype=FoodType.NORMAL)
        self.foods.append(food)
        self.total_spawned += 1
        return food

    def _spawn_special(self, blocked: Sequence[Tuple[int, int]], ftype: FoodType) -> Optional[Food]:
        """生成一个指定类型的特殊食物。"""
        occupied = self._occupied_cells(blocked)
        cell = random_empty_cell(occupied, self.columns, self.rows, self.rng)
        if cell is None:
            return None
        food = Food(position=cell, ftype=ftype)
        self.foods.append(food)
        self.total_spawned += 1
        return food

    def maybe_spawn_special(self, blocked: Sequence[Tuple[int, int]], dt: float) -> Optional[Food]:
        """每秒按权重尝试生成一个特殊食物，受数量上限约束。"""
        self.spawn_cooldown += dt
        if self.spawn_cooldown < 1.0:
            return None
        self.spawn_cooldown = 0.0
        specials = [f for f in self.foods if f.is_special]
        if len(specials) >= self.MAX_SPECIAL_FOODS:
            return None
        choice = random_choice_weighted(
            [("golden", self.GOLDEN_SPAWN_CHANCE), ("speed", self.SPEED_SPAWN_CHANCE)],
            self.rng,
        )
        ftype = FoodType.GOLDEN if choice == "golden" else FoodType.SPEED
        return self._spawn_special(blocked, ftype)

    # -- 生命周期 -----------------------------------------------------------

    def tick(self, dt: float) -> List[Food]:
        """推进所有食物计时，返回本帧因过期被移除的食物列表。"""
        expired: List[Food] = []
        for food in self.foods:
            food.tick(dt)
            if food.expired:
                expired.append(food)
        for food in expired:
            self.foods.remove(food)
        return expired

    def remove_at(self, cell: Tuple[int, int]) -> Optional[Food]:
        """移除并返回位于指定格子的食物，找不到返回 None。"""
        for food in self.foods:
            if food.position == cell:
                self.foods.remove(food)
                return food
        return None

    def clear(self) -> None:
        """清空所有食物（新一局开始时调用）。"""
        self.foods.clear()
        self.spawn_cooldown = 0.0

    # -- 查询 ---------------------------------------------------------------

    def food_at(self, cell: Tuple[int, int]) -> Optional[Food]:
        """查询指定格子上的食物。"""
        for food in self.foods:
            if food.position == cell:
                return food
        return None

    @property
    def normal_food(self) -> Optional[Food]:
        """返回场上普通食物，若无则返回 None。"""
        for food in self.foods:
            if food.ftype == FoodType.NORMAL:
                return food
        return None

    @property
    def has_normal_food(self) -> bool:
        """场上是否存在普通食物。"""
        return self.normal_food is not None

    def count_by_type(self, ftype: FoodType) -> int:
        """统计指定类型的食物数量。"""
        return sum(1 for food in self.foods if food.ftype == ftype)

    def nearest_food_distance(self, head: Tuple[int, int]) -> Optional[int]:
        """计算蛇头到最近食物的曼哈顿距离，场上无食物返回 None。"""
        if not self.foods:
            return None
        return min(manhattan_distance(head, food.position) for food in self.foods)

    def food_type_ratios(self) -> Dict[str, float]:
        """返回各类型食物占比字典，便于统计与调试。"""
        total = len(self.foods)
        if total == 0:
            return {"normal": 0.0, "golden": 0.0, "speed": 0.0}
        result: Dict[str, float] = {}
        for ftype in FoodType:
            result[ftype.value] = self.count_by_type(ftype) / total
        return result


def default_spawn_weights() -> Dict[str, float]:
    """返回默认的特殊食物生成权重表（供配置界面复用）。"""
    return {
        "golden": FoodManager.GOLDEN_SPAWN_CHANCE,
        "speed": FoodManager.SPEED_SPAWN_CHANCE,
    }


def score_value_of(ftype: FoodType) -> int:
    """返回指定食物类型的基础分值。"""
    mapping = {
        FoodType.NORMAL: SCORE_PER_FOOD,
        FoodType.GOLDEN: SCORE_PER_GOLDEN_FOOD,
        FoodType.SPEED: SCORE_PER_SPEED_FOOD,
    }
    return mapping.get(ftype, SCORE_PER_FOOD)
