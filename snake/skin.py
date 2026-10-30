# -*- coding: utf-8 -*-
"""皮肤管理模块。

- Skin: 单套皮肤的配色定义（蛇头 / 蛇身 / 蛇尾 / 食物 / 背景）
- SkinManager: 内置皮肤注册表，负责当前皮肤的选择与切换

皮肤是纯数据对象，不依赖 pygame；渲染层（ui 模块）读取当前皮肤的
颜色字段进行绘制，实现整套配色的一键切换。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# RGB 颜色类型别名
RGB = Tuple[int, int, int]

# 内置皮肤名称常量（集中定义，避免魔法字符串）
SKIN_CLASSIC = "经典绿"
SKIN_NEON = "霓虹蓝"
SKIN_FLAME = "烈焰橙"


def _valid_rgb(color: RGB) -> bool:
    """校验一个 RGB 三元组是否合法（0-255 整数）。"""
    return (
        isinstance(color, tuple)
        and len(color) == 3
        and all(isinstance(c, int) and 0 <= c <= 255 for c in color)
    )


@dataclass(frozen=True)
class Skin:
    """单套皮肤的完整配色定义。

    Attributes:
        name: 皮肤显示名称。
        snake_head: 蛇头颜色。
        snake_body: 蛇身颜色。
        snake_tail: 蛇尾颜色。
        food_normal: 普通食物颜色。
        food_golden: 金色食物颜色。
        food_speed: 加速食物颜色。
        background: 游戏背景底色。
        grid_line: 网格线颜色。
        accent: 界面强调色（标题、选中边框等）。
    """

    name: str
    snake_head: RGB
    snake_body: RGB
    snake_tail: RGB
    food_normal: RGB
    food_golden: RGB
    food_speed: RGB
    background: RGB
    grid_line: RGB
    accent: RGB = field(default=(235, 235, 235))

    def __post_init__(self) -> None:
        """初始化后校验全部颜色字段合法性，尽早暴露配置错误。"""
        for attr in (
            "snake_head", "snake_body", "snake_tail",
            "food_normal", "food_golden", "food_speed",
            "background", "grid_line", "accent",
        ):
            value = getattr(self, attr)
            if not _valid_rgb(value):
                raise ValueError(f"皮肤 '{self.name}' 的字段 {attr} 不是合法 RGB: {value!r}")

    @property
    def snake_colors(self) -> Tuple[RGB, RGB, RGB]:
        """返回（头, 身, 尾）三元组，便于渲染蛇时按段取色。"""
        return self.snake_head, self.snake_body, self.snake_tail

    @property
    def food_colors(self) -> Tuple[RGB, RGB, RGB]:
        """返回（普通, 金色, 加速）三种食物颜色。"""
        return self.food_normal, self.food_golden, self.food_speed


def build_builtin_skins() -> List[Skin]:
    """构建三套内置皮肤（经典绿 / 霓虹蓝 / 烈焰橙）。"""
    return [
        Skin(
            name=SKIN_CLASSIC,
            snake_head=(80, 220, 120),
            snake_body=(60, 180, 100),
            snake_tail=(40, 140, 80),
            food_normal=(230, 80, 80),
            food_golden=(240, 200, 60),
            food_speed=(80, 160, 240),
            background=(18, 18, 24),
            grid_line=(30, 30, 40),
            accent=(80, 220, 120),
        ),
        Skin(
            name=SKIN_NEON,
            snake_head=(0, 229, 255),
            snake_body=(0, 160, 233),
            snake_tail=(0, 105, 180),
            food_normal=(255, 64, 129),
            food_golden=(255, 213, 79),
            food_speed=(140, 255, 120),
            background=(8, 12, 30),
            grid_line=(25, 35, 70),
            accent=(0, 229, 255),
        ),
        Skin(
            name=SKIN_FLAME,
            snake_head=(255, 140, 0),
            snake_body=(230, 100, 20),
            snake_tail=(180, 60, 10),
            food_normal=(90, 200, 120),
            food_golden=(255, 220, 90),
            food_speed=(160, 90, 255),
            background=(30, 15, 8),
            grid_line=(64, 34, 20),
            accent=(255, 140, 0),
        ),
    ]


class SkinManager:
    """皮肤管理器：注册全部皮肤并维护当前选中的皮肤。

    Attributes:
        skins: 全部可用皮肤列表（顺序即切换顺序）。
        current_index: 当前皮肤在列表中的下标。
    """

    def __init__(self, current: Optional[str] = None, skins: Optional[List[Skin]] = None) -> None:
        """初始化皮肤列表与默认皮肤。

        Args:
            current: 初始皮肤名称；None 或找不到时使用第一套。
            skins: 自定义皮肤列表；None 时使用三套内置皮肤。
        """
        self.skins: List[Skin] = skins if skins is not None else build_builtin_skins()
        self.current_index = 0
        if current is not None:
            self.set_current(current)

    @property
    def current(self) -> Skin:
        """当前选中的皮肤。"""
        return self.skins[self.current_index]

    def names(self) -> List[str]:
        """返回全部皮肤名称（按切换顺序）。"""
        return [skin.name for skin in self.skins]

    def find(self, name: str) -> Optional[Skin]:
        """按名称查找皮肤，找不到返回 None。"""
        for skin in self.skins:
            if skin.name == name:
                return skin
        return None

    def set_current(self, name: str) -> bool:
        """按名称切换当前皮肤，成功返回 True，名称不存在返回 False（保持原状）。"""
        index = next((i for i, s in enumerate(self.skins) if s.name == name), None)
        if index is None:
            return False
        self.current_index = index
        return True

    def cycle(self, step: int) -> Skin:
        """按 step 方向循环切换皮肤（正数下一套，负数上一套），返回新皮肤。"""
        self.current_index = (self.current_index + step) % len(self.skins)
        return self.current

    def next(self) -> Skin:
        """切换到下一套皮肤。"""
        return self.cycle(1)

    def previous(self) -> Skin:
        """切换到上一套皮肤。"""
        return self.cycle(-1)
