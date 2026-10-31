# -*- coding: utf-8 -*-
"""增量（脏矩形）渲染模块。

游戏画面里真正每帧都在变的只有蛇身和食物，背景网格、其余空白格子
完全没变。整屏重绘等于每帧把 800x600 全部重画一遍，纯属浪费。
本模块的做法：

1. 每帧构建一份 ``{格子坐标: 内容签名}`` 快照（蛇节颜色、食物颜色、
   闪烁相位），与上一帧比对，得到内容真的变了的格子集合；
2. 只用缓存的网格背景擦除这些格子，再按格子集合重画对应的蛇节 / 食物；
3. 把脏矩形合并后交给 ``Screen.present()`` 局部提交到窗口。

于是两次移动之间的那些帧（60FPS 下占绝大多数）几乎不画东西，
提交的脏矩形数量也能压到个位数。

特殊处理：
- 加速光晕是整屏边缘渐变，无法用格子表达，激活期间退化为整屏重绘；
- 切换皮肤/暂停/结束时调用 ``invalidate()``，下一帧强制整屏重绘，
  避免脏区判断基于上一屏的残留内容。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set, Tuple

import pygame

from .ui import GameRenderer

# 格子坐标
Cell = Tuple[int, int]
# 一格的内容签名：("snake", 颜色) 或 ("food", 颜色, 闪烁相位)
Signature = tuple


def merge_rects(rects: Sequence[pygame.Rect], limit: int = 64) -> List[pygame.Rect]:
    """把重叠或相邻的脏矩形合并，减少 display.update 的提交次数。

    Args:
        rects: 待合并的矩形序列（通常是一批相邻格子）。
        limit: 合并结果的数量上限；仍然超出时退化为一个外接矩形，
            因为提交几百个小矩形的开销可能比画一块大区域还高。

    Returns:
        合并后的矩形列表（已丢弃空矩形）。
    """
    merged: List[pygame.Rect] = []
    for rect in rects:
        if rect.width <= 0 or rect.height <= 0:
            continue
        merged.append(pygame.Rect(rect))

    # 反复合并，直到没有新的相邻关系（矩形数量很少，代价可忽略）
    changed = True
    while changed and len(merged) > 1:
        changed = False
        result: List[pygame.Rect] = []
        for rect in merged:
            for index, other in enumerate(result):
                # inflate(2, 2) 让"紧挨着"的格子也算相邻，避免大量 1px 缝隙
                if other.colliderect(rect.inflate(2, 2)):
                    result[index] = other.union(rect)
                    changed = True
                    break
            else:
                result.append(rect)
        merged = result

    if len(merged) > limit:
        box = merged[0].unionall(merged[1:])
        return [box]
    return merged


class PlayfieldRenderer:
    """游戏战场的增量渲染器：只重绘上一帧与这一帧不同的格子。

    Attributes:
        game_renderer: 复用的 GameRenderer（负责具体绘制与配色）。
        last_dirty: 最近一帧提交的脏矩形（整屏重绘时是整屏矩形），调试用。
    """

    def __init__(self, screen, skin_manager=None) -> None:
        """记录屏幕与皮肤管理器，并初始化空的帧快照。"""
        self.screen = screen
        self.skin_manager = skin_manager
        self.game_renderer = GameRenderer(screen, skin_manager)
        self._snapshot: Dict[Cell, Signature] = {}
        self._speed_active = False
        self.last_dirty: List[pygame.Rect] = []

    def invalidate(self) -> None:
        """丢弃帧快照，下一帧强制整屏重绘（换皮肤、状态切换、窗口重建时用）。"""
        self._snapshot.clear()
        self._speed_active = False
        self.last_dirty = []

    # -- 对外入口 -----------------------------------------------------------

    def render(self, game, force_full: bool = False) -> Optional[List[pygame.Rect]]:
        """渲染一帧战场。

        Args:
            game: 当前 Game 对象（提供 snake / food_manager / 加速状态）。
            force_full: True 时无条件整屏重绘（暂停、结束、设置叠加界面用）。

        Returns:
            None 表示已整屏重绘（调用方整屏提交）；否则返回需要局部提交的
            脏矩形列表，空列表表示这一帧什么都没变，不需要刷新显示器。
        """
        snapshot = self._build_snapshot(game)
        speed_active = game.speed_effect_ratio() > 0
        need_full = force_full or not self._snapshot or speed_active or self._speed_active

        if need_full:
            self._draw_full(game, speed_active)
            self._snapshot = snapshot
            self._speed_active = speed_active
            self.last_dirty = [self.screen.rect]
            return None

        cells = self._diff_cells(snapshot)
        self._snapshot = snapshot
        if not cells:
            # 这一帧内容与上一帧完全一致：不画、不提交
            self.last_dirty = []
            return []

        for cell in cells:
            self.screen.restore_background(self.screen.cell_rect(cell))
        self._draw_cells(game, cells)

        dirty = merge_rects([self.screen.cell_rect(cell) for cell in cells])
        self.last_dirty = dirty
        return dirty

    # -- 快照与差异 ---------------------------------------------------------

    def _build_snapshot(self, game) -> Dict[Cell, Signature]:
        """构建这一帧每个有内容格子的签名（颜色 + 闪烁相位）。"""
        snapshot: Dict[Cell, Signature] = {}
        snake = game.snake
        if snake is not None:
            length = snake.length
            for index, segment in enumerate(snake):
                color = self.game_renderer.segment_color(index, length, segment)
                snapshot[segment.position] = ("snake", color)
        food_manager = getattr(game, "food_manager", None)
        if food_manager is not None:
            for food in food_manager.foods:
                color = self.game_renderer.food_color(food)
                snapshot[food.position] = ("food", color, self._blink_phase(food))
        return snapshot

    @staticmethod
    def _blink_phase(food) -> int:
        """特殊食物快过期时会闪烁，把相位纳入签名，该亮/该灭时格子自动变脏。"""
        if not food.is_special:
            return 0
        ratio = food.remaining_ratio()
        if ratio >= 0.35:
            return 0
        return int(ratio * 20) % 2

    def _diff_cells(self, snapshot: Dict[Cell, Signature]) -> Set[Cell]:
        """返回内容发生变化的格子集合（新增、消失、颜色改变都算）。"""
        previous = self._snapshot
        changed: Set[Cell] = set()
        for cell, signature in snapshot.items():
            if previous.get(cell) != signature:
                changed.add(cell)
        for cell in previous:
            if cell not in snapshot:
                changed.add(cell)  # 上一帧有、这一帧没有了：需要擦掉
        return changed

    # -- 绘制 ---------------------------------------------------------------

    def _draw_full(self, game, speed_active: bool) -> None:
        """整屏重绘：背景 + 食物 + 蛇 +（可选）加速光晕。"""
        self.screen.draw_background()
        food_manager = getattr(game, "food_manager", None)
        if food_manager is not None:
            self.game_renderer.draw_foods(food_manager.foods)
        if game.snake is not None:
            self.game_renderer.draw_snake(game.snake)
        if speed_active:
            self.game_renderer.draw_speed_effect(True, game.speed_effect_ratio())

    def _draw_cells(self, game, cells: Set[Cell]) -> None:
        """只绘制落在脏格子里的蛇节与食物（其余格子沿用后缓冲内容）。"""
        snake = game.snake
        if snake is not None:
            length = snake.length
            for index, segment in enumerate(snake):
                if segment.position in cells:
                    self.game_renderer.draw_segment(index, length, segment)
            if snake.head_position in cells:
                # 眼睛画在蛇头格内，蛇头变脏时一并重画
                self.game_renderer.draw_eyes(snake)
        food_manager = getattr(game, "food_manager", None)
        if food_manager is not None:
            for food in food_manager.foods:
                if food.position in cells:
                    self.game_renderer.draw_food(food)
