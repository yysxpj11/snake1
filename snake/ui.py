# -*- coding: utf-8 -*-
"""界面模块。

负责一切与渲染、输入界面相关的工作：
- Screen 封装窗口与网格绘制
- HUD 顶部信息栏
- Button / Panel 可复用控件
- MenuRenderer 主菜单 / 暂停 / 结束画面
- GameRenderer 游戏进行时的场景渲染

注意：pygame 初始化由 main 模块负责，本模块不做 import pygame 的副作用，
顶层直接 import pygame 仅供类型提示（运行环境保证已安装）。
"""

from __future__ import annotations

import math
import sys
from typing import Dict, List, Optional, Sequence, Tuple

import pygame

from .food import Food, FoodType
from .snake import Snake, WallMode
from .utils import Config, Palette, format_score, format_time


class FontBank:
    """集中管理各字号字体对象，避免每帧重复创建字体。"""

    def __init__(self) -> None:
        """按需创建常用字号的字体。"""
        self._cache: Dict[str, pygame.font.Font] = {}
        base = pygame.font.get_default_font()
        for size in (12, 14, 16, 20, 24, 32, 48, 64):
            self._cache[str(size)] = pygame.font.SysFont(
                "microsoftyahei, simhei, arial", size
            ) if False else pygame.font.Font(base, size)

    def get(self, size: int) -> pygame.font.Font:
        """获取指定字号字体，未缓存则现场创建。"""
        key = str(size)
        if key not in self._cache:
            base = pygame.font.get_default_font()
            self._cache[key] = pygame.font.Font(base, size)
        return self._cache[key]

    def render(self, text: str, size: int, color: Tuple[int, int, int]) -> pygame.Surface:
        """便捷方法：直接渲染文本并返回 Surface。"""
        return self.get(size).render(text, True, color)


class Screen:
    """主窗口与网格背景的封装。"""

    def __init__(self, config: Config) -> None:
        """按配置创建窗口并预计算网格线。"""
        self.config = config
        flags = pygame.FULLSCREEN if config.fullscreen else 0
        self.surface = pygame.display.set_mode(
            (config.window_width, config.window_height), flags
        )
        pygame.display.set_caption("贪吃蛇 Pygame 版")
        self.fonts = FontBank()
        self._grid_surface = self._build_grid_surface()

    def _build_grid_surface(self) -> pygame.Surface:
        """预绘制网格线到离屏 Surface，每帧直接贴图以提高性能。"""
        surf = pygame.Surface((self.config.window_width, self.config.window_height))
        surf.fill(Palette.BACKGROUND)
        cs = self.config.cell_size
        for x in range(0, self.config.window_width, cs):
            pygame.draw.line(surf, Palette.GRID_LINE, (x, 0), (x, self.config.window_height))
        for y in range(0, self.config.window_height, cs):
            pygame.draw.line(surf, Palette.GRID_LINE, (0, y), (self.config.window_width, y))
        return surf

    def draw_background(self) -> None:
        """绘制背景与网格。"""
        self.surface.blit(self._grid_surface, (0, 0))

    def draw_text(
        self,
        text: str,
        pos: Tuple[int, int],
        size: int = 20,
        color: Tuple[int, int, int] = Palette.TEXT_PRIMARY,
        center: bool = False,
    ) -> pygame.Rect:
        """在窗口上绘制文本，返回文本矩形（center=True 时按中心定位）。"""
        rendered = self.fonts.render(text, size, color)
        rect = rendered.get_rect()
        if center:
            rect.center = pos
        else:
            rect.topleft = pos
        self.surface.blit(rendered, rect)
        return rect

    def cell_rect(self, cell: Tuple[int, int]) -> pygame.Rect:
        """把网格坐标转换为像素矩形（留 1px 间隙形成格子感）。"""
        cs = self.config.cell_size
        x, y = cell
        return pygame.Rect(x * cs + 1, y * cs + 1, cs - 2, cs - 2)

    def flip(self) -> None:
        """交换前后缓冲，呈现本帧画面。"""
        pygame.display.flip()


class Panel:
    """带边框的半透明面板，用于弹窗、菜单容器。"""

    def __init__(self, rect: pygame.Rect) -> None:
        """初始化面板矩形。"""
        self.rect = rect

    def draw(self, surface: pygame.Surface) -> None:
        """绘制面板背景与边框。"""
        overlay = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        overlay.fill(Palette.OVERLAY)
        surface.blit(overlay, self.rect.topleft)
        pygame.draw.rect(surface, Palette.PANEL_BORDER, self.rect, 2, border_radius=8)

    @property
    def center(self) -> Tuple[int, int]:
        """面板中心点。"""
        return self.rect.center


class Button:
    """简单按钮控件，支持悬停高亮与回调。"""

    def __init__(
        self,
        text: str,
        rect: pygame.Rect,
        on_click=None,
        font_size: int = 24,
    ) -> None:
        """初始化按钮文本、区域与点击回调。"""
        self.text = text
        self.rect = rect
        self.on_click = on_click
        self.font_size = font_size
        self.hovered = False
        self.enabled = True

    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理点击事件，命中返回 True。"""
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.on_click:
                    self.on_click()
                return True
        return False

    def update_hover(self, mouse_pos: Tuple[int, int]) -> None:
        """根据鼠标位置更新悬停状态。"""
        self.hovered = self.enabled and self.rect.collidepoint(mouse_pos)

    def draw(self, surface: pygame.Surface, fonts: FontBank) -> None:
        """绘制按钮本体与文字。"""
        color = Palette.BUTTON_HOVER if self.hovered else Palette.BUTTON_BG
        pygame.draw.rect(surface, color, self.rect, border_radius=6)
        pygame.draw.rect(surface, Palette.PANEL_BORDER, self.rect, 1, border_radius=6)
        rendered = fonts.render(self.text, self.font_size, Palette.TEXT_PRIMARY)
        text_rect = rendered.get_rect(center=self.rect.center)
        surface.blit(rendered, text_rect)


class HUD:
    """顶部信息栏：分数、最高分、长度、时间。"""

    HEIGHT = 40

    def __init__(self, screen: Screen, best_score: int) -> None:
        """初始化并记录最高分。"""
        self.screen = screen
        self.best_score = best_score
        self.message: str = ""
        self.message_timer = 0.0

    def show_message(self, text: str, duration: float = 2.0) -> None:
        """显示一条限时提示（如“加速！”）。"""
        self.message = text
        self.message_timer = duration

    def tick_message(self, dt: float) -> None:
        """推进提示消息的显示时间。"""
        if self.message_timer > 0:
            self.message_timer = max(0.0, self.message_timer - dt)
            if self.message_timer == 0:
                self.message = ""

    def draw(self, score: int, length: int, elapsed: float) -> None:
        """绘制整条 HUD。"""
        surf = self.screen.surface
        bar = pygame.Rect(0, 0, self.screen.config.window_width, HUD.HEIGHT)
        pygame.draw.rect(surf, Palette.PANEL_BG, bar)
        pygame.draw.line(surf, Palette.PANEL_BORDER, (0, HUD.HEIGHT), (bar.width, HUD.HEIGHT))
        self.screen.draw_text(
            f"得分: {format_score(score)}", (10, 8), 20, Palette.TEXT_PRIMARY
        )
        self.screen.draw_text(
            f"最高: {format_score(self.best_score)}", (200, 8), 20, Palette.TEXT_DIM
        )
        self.screen.draw_text(
            f"长度: {length}", (400, 8), 20, Palette.TEXT_PRIMARY
        )
        self.screen.draw_text(
            f"时间: {format_time(elapsed)}", (560, 8), 20, Palette.TEXT_PRIMARY
        )
        if self.message:
            self.screen.draw_text(
                self.message, (bar.width - 120, 8), 20, Palette.SUCCESS
            )


class GameRenderer:
    """游戏进行中的场景渲染器。"""

    def __init__(self, screen: Screen) -> None:
        """记录屏幕引用。"""
        self.screen = screen

    # -- 蛇 -----------------------------------------------------------------

    def draw_snake(self, snake: Snake) -> None:
        """绘制整条蛇：头、身、尾使用不同颜色。"""
        n = snake.length
        for index, seg in enumerate(snake):
            rect = self.screen.cell_rect(seg.position)
            if index == 0:
                color = Palette.SNAKE_HEAD
            elif index == n - 1:
                color = Palette.SNAKE_TAIL
            else:
                color = Palette.SNAKE_BODY
            if seg.is_new:
                color = Palette.lighten(color, 0.35)
            pygame.draw.rect(self.screen.surface, color, rect, border_radius=4)
        self._draw_eyes(snake)

    def _draw_eyes(self, snake: Snake) -> None:
        """在蛇头上绘制两只眼睛，指示朝向。"""
        cs = self.screen.config.cell_size
        hx, hy = snake.head_position
        cx = hx * cs + cs // 2
        cy = hy * cs + cs // 2
        dx, dy = snake.direction.vector
        offset = cs // 4
        perp = (-dy, dx)
        eye1 = (cx + dx * offset + perp[0] * offset, cy + dy * offset + perp[1] * offset)
        eye2 = (cx + dx * offset - perp[0] * offset, cy + dy * offset - perp[1] * offset)
        radius = max(2, cs // 10)
        for pos in (eye1, eye2):
            pygame.draw.circle(self.screen.surface, (20, 20, 20), pos, radius)

    # -- 食物 ---------------------------------------------------------------

    def draw_food(self, food: Food) -> None:
        """按类型绘制食物，特殊食物附带剩余时间指示环。"""
        rect = self.screen.cell_rect(food.position)
        color_map = {
            FoodType.NORMAL: Palette.FOOD_NORMAL,
            FoodType.GOLDEN: Palette.FOOD_GOLDEN,
            FoodType.SPEED: Palette.FOOD_SPEED,
        }
        color = color_map.get(food.ftype, Palette.FOOD_NORMAL)
        pygame.draw.circle(self.screen.surface, color, rect.center, rect.width // 2 - 1)
        if food.is_special:
            ratio = food.remaining_ratio()
            if ratio < 0.35:
                # 快过期时闪烁提醒
                if int(ratio * 20) % 2 == 0:
                    pygame.draw.circle(
                        self.screen.surface,
                        Palette.TEXT_PRIMARY,
                        rect.center,
                        rect.width // 2 + 1,
                        1,
                    )

    def draw_foods(self, foods: Sequence[Food]) -> None:
        """绘制场上所有食物。"""
        for food in foods:
            self.draw_food(food)

    # -- 覆盖层 -------------------------------------------------------------

    def draw_pause_overlay(self) -> None:
        """绘制暂停遮罩与提示文字。"""
        self._dim_overlay()
        size = self.screen.config.window_width, self.screen.config.window_height
        cx, cy = size[0] // 2, size[1] // 2
        self.screen.draw_text("已暂停", (cx, cy - 30), 48, Palette.TEXT_PRIMARY, center=True)
        self.screen.draw_text(
            "按 P 或 空格 继续", (cx, cy + 30), 20, Palette.TEXT_DIM, center=True
        )

    def _dim_overlay(self, alpha: int = 160) -> None:
        """在全屏上叠加半透明黑色遮罩。"""
        w, h = self.screen.config.window_width, self.screen.config.window_height
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, alpha))
        self.screen.surface.blit(overlay, (0, 0))

    def draw_speed_effect(self, active: bool, ratio: float) -> None:
        """加速效果激活时在屏幕边缘绘制蓝色光晕。"""
        if not active:
            return
        w, h = self.screen.config.window_width, self.screen.config.window_height
        border = pygame.Surface((w, h), pygame.SRCALPHA)
        thickness = max(2, int(6 * ratio))
        alpha = int(120 * ratio)
        pygame.draw.rect(border, (80, 160, 240, alpha), border.get_rect(), thickness)
        self.screen.surface.blit(border, (0, 0))


class MenuRenderer:
    """主菜单、结束画面等静态界面的渲染与按钮管理。"""

    def __init__(self, screen: Screen) -> None:
        """初始化并创建菜单按钮组。"""
        self.screen = screen
        self.buttons: List[Button] = []
        self._build_main_menu()

    def _make_button(self, text: str, index: int, on_click) -> Button:
        """在屏幕中央纵向排列生成一个按钮。"""
        w, h = self.screen.config.window_width, self.screen.config.window_height
        rect = pygame.Rect(0, 0, 220, 48)
        rect.center = (w // 2, h // 2 - 20 + index * 64)
        return Button(text, rect, on_click)

    def _build_main_menu(self) -> None:
        """构建主菜单按钮：开始游戏、难度切换、退出。"""
        self.buttons.clear()
        self.buttons.append(self._make_button("开始游戏", 0, None))
        self.buttons.append(self._make_button("难度: 普通", 1, None))
        self.buttons.append(self._make_button("退出", 2, None))

    def draw_main_menu(self, best_score: int) -> None:
        """绘制主菜单界面。"""
        self.screen.draw_background()
        w, h = self.screen.config.window_width, self.screen.config.window_height
        self.screen.draw_text("贪吃蛇", (w // 2, h // 3 - 40), 64, Palette.SNAKE_HEAD, center=True)
        self.screen.draw_text(
            f"历史最高分: {best_score}", (w // 2, h // 3 + 20), 24, Palette.TEXT_DIM, center=True
        )
        fonts = self.screen.fonts
        for button in self.buttons:
            button.update_hover(pygame.mouse.get_pos())
            button.draw(self.screen.surface, fonts)
        self.screen.draw_text(
            "方向键 / WASD 移动 · P 暂停 · ESC 退出",
            (w // 2, h - 40),
            16,
            Palette.TEXT_DIM,
            center=True,
        )

    def draw_game_over(
        self, score: int, best: int, reason: str, is_record: bool
    ) -> None:
        """绘制结束画面。"""
        self.screen.draw_background()
        self._dim_overlay()
        w, h = self.screen.config.window_width, self.screen.config.window_height
        cx, cy = w // 2, h // 2
        self.screen.draw_text("游戏结束", (cx, cy - 120), 56, Palette.DANGER, center=True)
        self.screen.draw_text(f"原因: {reason}", (cx, cy - 60), 24, Palette.TEXT_DIM, center=True)
        self.screen.draw_text(f"本局得分: {score}", (cx, cy), 32, Palette.TEXT_PRIMARY, center=True)
        if is_record:
            self.screen.draw_text("新纪录！", (cx, cy + 44), 28, Palette.FOOD_GOLDEN, center=True)
        else:
            self.screen.draw_text(f"最高分: {best}", (cx, cy + 44), 24, Palette.TEXT_DIM, center=True)
        self.screen.draw_text(
            "按 R 重新开始 · 按 M 返回菜单",
            (cx, cy + 110),
            20,
            Palette.TEXT_PRIMARY,
            center=True,
        )

    def handle_events(self, events: Sequence[pygame.event.Event]) -> int:
        """转发事件给按钮，返回被点击按钮的索引（无点击返回 -1）。"""
        for event in events:
            for index, button in enumerate(self.buttons):
                if button.handle_event(event):
                    return index
        return -1
