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
from .utils import Config, Difficulty, Palette, format_score, format_time


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


class Menu:
    """开始菜单的逻辑状态：菜单项、选中索引与确认动作。

    本类只负责菜单的状态与键盘交互逻辑，不直接绘制，
    绘制由 MenuRenderer 完成；这样菜单逻辑可以脱离窗口做单元测试。

    Attributes:
        items: 菜单项列表，形如 [(显示文本, 动作名), ...]。
        selected_index: 当前选中的菜单项下标。
        on_select: 确认选中项时的回调，参数为动作名字符串。
    """

    def __init__(
        self,
        items: Optional[List[Tuple[str, str]]] = None,
        on_select=None,
        difficulty: Optional[Difficulty] = None,
        on_difficulty_change=None,
    ) -> None:
        """初始化菜单项、选中状态与难度档位。

        Args:
            items: 菜单项列表 [(文本, 动作名)]，默认 开始游戏/选择难度/退出。
            on_select: 确认菜单项时的回调，参数为动作名。
            difficulty: 初始难度档位，默认 NORMAL。
            on_difficulty_change: 难度切换时的回调，参数为新的 Difficulty。
        """
        self.difficulty: Difficulty = difficulty or Difficulty.NORMAL
        self.on_difficulty_change = on_difficulty_change
        if items is None:
            items = [
                ("开始游戏", "start"),
                (f"选择难度: {self.difficulty.label}", "difficulty"),
                ("退出", "quit"),
            ]
        self.items: List[Tuple[str, str]] = list(items)
        self.selected_index = 0
        self.on_select = on_select

    @property
    def difficulty_index(self) -> int:
        """返回难度项在菜单中的下标，找不到返回 -1。"""
        for index, (_text, action) in enumerate(self.items):
            if action == "difficulty":
                return index
        return -1

    @property
    def selected_text(self) -> str:
        """当前选中项的显示文本。"""
        return self.items[self.selected_index][0]

    @property
    def selected_action(self) -> str:
        """当前选中项的动作名。"""
        return self.items[self.selected_index][1]

    def move_up(self) -> None:
        """向上移动选中项，到顶后循环回最后一项。"""
        self.selected_index = (self.selected_index - 1) % len(self.items)

    def move_down(self) -> None:
        """向下移动选中项，到底后循环回第一项。"""
        self.selected_index = (self.selected_index + 1) % len(self.items)

    def set_item_text(self, index: int, text: str) -> None:
        """更新指定菜单项的显示文本（如难度切换后刷新标签）。"""
        if 0 <= index < len(self.items):
            label, action = self.items[index]
            self.items[index] = (text, action)

    def set_difficulty(self, difficulty: Difficulty, notify: bool = True) -> None:
        """设置当前难度并刷新菜单标签，notify=True 时触发切换回调。"""
        self.difficulty = difficulty
        index = self.difficulty_index
        if index >= 0:
            self.set_item_text(index, f"选择难度: {difficulty.label}")
        if notify and self.on_difficulty_change is not None:
            self.on_difficulty_change(difficulty)

    def cycle_difficulty(self, step: int) -> Difficulty:
        """按 step 方向在三档难度间循环切换（正数下一档，负数上一档）。"""
        new_difficulty = self.difficulty.next() if step > 0 else self.difficulty.previous()
        self.set_difficulty(new_difficulty)
        return new_difficulty

    def confirm(self) -> Optional[str]:
        """确认当前选中项，触发回调并返回动作名（无回调时仅返回动作名）。"""
        action = self.selected_action
        # 难度项上的确认等价于切到下一档
        if action == "difficulty":
            self.cycle_difficulty(1)
        if self.on_select is not None:
            self.on_select(action)
        return action

    def handle_key(self, key: str) -> Optional[str]:
        """处理一个抽象按键，key 可为 up / down / left / right / confirm。

        左右键仅在选中"选择难度"时生效，用于切换三档难度；
        返回 confirm 产生的动作名，其余操作返回 None。
        """
        if key == "up":
            self.move_up()
            return None
        if key == "down":
            self.move_down()
            return None
        if key in ("left", "right") and self.selected_action == "difficulty":
            self.cycle_difficulty(-1 if key == "left" else 1)
            return None
        if key == "confirm":
            return self.confirm()
        return None

    def handle_click_at(self, pos: Tuple[int, int], item_rects: Sequence[pygame.Rect]) -> Optional[str]:
        """处理鼠标点击：点中某个菜单项则选中并确认，返回动作名。"""
        for index, rect in enumerate(item_rects):
            if rect.collidepoint(pos):
                self.selected_index = index
                return self.confirm()
        return None


def build_vertical_gradient(
    width: int,
    height: int,
    top_color: Tuple[int, int, int] = (30, 30, 46),
    bottom_color: Tuple[int, int, int] = (8, 8, 14),
) -> pygame.Surface:
    """生成一张深色纵向渐变背景 Surface（顶亮底暗）。"""
    surface = pygame.Surface((width, height))
    span = max(1, height - 1)
    for y in range(height):
        t = y / span
        color = (
            int(top_color[0] + (bottom_color[0] - top_color[0]) * t),
            int(top_color[1] + (bottom_color[1] - top_color[1]) * t),
            int(top_color[2] + (bottom_color[2] - top_color[2]) * t),
        )
        pygame.draw.line(surface, color, (0, y), (width, y))
    return surface


class MenuRenderer:
    """主菜单、结束画面等静态界面的渲染与按钮管理。"""

    # 菜单项在界面中的纵向排布参数
    ITEM_WIDTH = 260
    ITEM_HEIGHT = 52
    ITEM_GAP = 18

    def __init__(self, screen: Screen) -> None:
        """初始化并创建菜单按钮组与渐变背景缓存。"""
        self.screen = screen
        self.buttons: List[Button] = []
        self._gradient: Optional[pygame.Surface] = None
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

    def _ensure_gradient(self) -> pygame.Surface:
        """获取（或首次生成）菜单用的深色渐变背景。"""
        if self._gradient is None:
            w, h = self.screen.config.window_width, self.screen.config.window_height
            self._gradient = build_vertical_gradient(w, h)
        return self._gradient

    def item_rects(self, menu: "Menu") -> List[pygame.Rect]:
        """计算各菜单项的屏幕矩形，与绘制位置保持一致（供点击命中使用）。"""
        w, h = self.screen.config.window_width, self.screen.config.window_height
        start_y = int(h * 0.52)
        rects: List[pygame.Rect] = []
        for index in range(len(menu.items)):
            rect = pygame.Rect(0, 0, MenuRenderer.ITEM_WIDTH, MenuRenderer.ITEM_HEIGHT)
            rect.center = (w // 2, start_y + index * (MenuRenderer.ITEM_HEIGHT + MenuRenderer.ITEM_GAP))
            rects.append(rect)
        return rects

    def draw_main_menu(self, best_score: int, menu: "Menu") -> None:
        """绘制开始菜单：深色渐变背景 + 居中标题 + 键盘选中高亮。"""
        self.screen.surface.blit(self._ensure_gradient(), (0, 0))
        w, h = self.screen.config.window_width, self.screen.config.window_height
        fonts = self.screen.fonts

        # 标题与最高分
        title = fonts.render("贪吃蛇", 64, Palette.SNAKE_HEAD)
        title_rect = title.get_rect(center=(w // 2, int(h * 0.26)))
        self.screen.surface.blit(title, title_rect)
        sub = fonts.render(f"历史最高分: {best_score}", 24, Palette.TEXT_DIM)
        sub_rect = sub.get_rect(center=(w // 2, int(h * 0.26) + 58))
        self.screen.surface.blit(sub, sub_rect)

        # 菜单项：选中项高亮加边框，未选中项半透明暗色
        rects = self.item_rects(menu)
        for index, (label, action) in enumerate(menu.items):
            rect = rects[index]
            selected = index == menu.selected_index
            bg = Palette.BUTTON_HOVER if selected else Palette.BUTTON_BG
            border = Palette.SNAKE_HEAD if selected else Palette.PANEL_BORDER
            pygame.draw.rect(self.screen.surface, bg, rect, border_radius=8)
            pygame.draw.rect(self.screen.surface, border, rect, 2, border_radius=8)
            text_color = Palette.TEXT_PRIMARY if selected else Palette.TEXT_DIM
            prefix = "▶ " if selected else ""
            rendered = fonts.render(f"{prefix}{label}", 24, text_color)
            text_rect = rendered.get_rect(center=rect.center)
            self.screen.surface.blit(rendered, text_rect)
            # 难度项右侧绘制三档档位条，高亮当前档位
            if action == "difficulty":
                self._draw_difficulty_chips(rect, menu, selected)

        self.screen.draw_text(
            "↑/↓ 选择 · ←/→ 切换难度 · 回车 确认 · ESC 退出",
            (w // 2, h - 36),
            16,
            Palette.TEXT_DIM,
            center=True,
        )

    def _draw_difficulty_chips(self, item_rect: pygame.Rect, menu: "Menu", active: bool) -> None:
        """在难度菜单项右侧绘制 简单/普通/困难 三个档位标签，高亮当前档位。

        active 表示难度项当前是否被选中，选中时档位条整体更亮以突出可操作。
        """
        fonts = self.screen.fonts
        levels = Difficulty.levels()
        chip_w, chip_h, gap = 56, 28, 8
        total_w = len(levels) * chip_w + (len(levels) - 1) * gap
        x = item_rect.right + 16
        y = item_rect.centery - chip_h // 2
        # 右侧空间不足时改为贴右边缘排列，避免超出窗口
        max_x = self.screen.config.window_width - total_w - 10
        x = min(x, max_x)
        for index, level in enumerate(levels):
            chip = pygame.Rect(x + index * (chip_w + gap), y, chip_w, chip_h)
            is_current = level == menu.difficulty
            if is_current:
                bg_color = Palette.SNAKE_HEAD
                text_color = Palette.BACKGROUND
            else:
                bg_color = Palette.BUTTON_BG if active else Palette.PANEL_BG
                text_color = Palette.TEXT_DIM if active else Palette.PANEL_BORDER
            pygame.draw.rect(self.screen.surface, bg_color, chip, border_radius=6)
            pygame.draw.rect(self.screen.surface, Palette.PANEL_BORDER, chip, 1, border_radius=6)
            label = fonts.render(level.label, 14, text_color)
            self.screen.surface.blit(label, label.get_rect(center=chip.center))

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
