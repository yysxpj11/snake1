# -*- coding: utf-8 -*-
"""界面模块。

负责一切与渲染、输入界面相关的工作：
- Screen 封装窗口、离屏后缓冲（双缓冲）与网格绘制
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
    """主窗口、离屏后缓冲与网格背景的封装。

    双缓冲策略：
    - ``surface`` 是离屏后缓冲，菜单、面板、蛇、食物等一切绘制都写在这里；
    - 一帧画完后由 ``present()`` 把后缓冲提交到真正的窗口 ``display``。

    这样显示器上永远不会出现"画了一半"的中间状态（撕裂 / 闪烁），
    同时把绘制与提交解耦，为后面的按脏区提交留好接口。
    本模块其余代码照旧写 ``screen.surface``，不需要关心缓冲细节。
    """

    def __init__(self, config: Config) -> None:
        """按配置创建窗口与后缓冲，并预计算网格线。"""
        self.config = config
        flags = pygame.FULLSCREEN if config.fullscreen else 0
        # DOUBLEBUF：要求 SDL 用双缓冲的显示模式；即使驱动忽略该标志，
        # 下面的离屏后缓冲也能保证同样的"先画完再提交"效果。
        self.display = pygame.display.set_mode(
            (config.window_width, config.window_height), flags | pygame.DOUBLEBUF
        )
        # 后缓冲：与窗口同尺寸的独立 Surface，所有绘制都发生在这里
        self.surface = pygame.Surface(
            (config.window_width, config.window_height)
        ).convert()
        pygame.display.set_caption("贪吃蛇 Pygame 版")
        self.fonts = FontBank()
        self._grid_surface = self._build_grid_surface()

    @property
    def rect(self) -> pygame.Rect:
        """整屏矩形（窗口尺寸）。"""
        return pygame.Rect(0, 0, self.config.window_width, self.config.window_height)

    def present(self, rects: Optional[Sequence[pygame.Rect]] = None) -> None:
        """把后缓冲提交到窗口，完成一次双缓冲交换。

        Args:
            rects: None 表示整屏提交（菜单、结束画面等整屏重绘的场合）；
                传入矩形列表时只把这些区域从后缓冲拷到窗口并局部刷新，
                配合 display.update 实现"只重绘变化区域"。
        """
        if rects is None:
            self.display.blit(self.surface, (0, 0))
            pygame.display.flip()
            return
        clipped: List[pygame.Rect] = []
        for rect in rects:
            area = pygame.Rect(rect).clip(self.rect)
            if area.width <= 0 or area.height <= 0:
                continue  # 完全在窗口外的矩形直接丢弃
            self.display.blit(self.surface, area.topleft, area)
            clipped.append(area)
        if clipped:
            pygame.display.update(clipped)

    def flip(self) -> None:
        """整屏提交并交换缓冲区（python 语义延续，等价于 present(None)）。"""
        self.present()

    def restore_background(self, rect: pygame.Rect) -> None:
        """按矩形把网格背景贴回后缓冲（增量渲染时擦掉上一帧的旧内容）。"""
        area = pygame.Rect(rect).clip(self.rect)
        if area.width > 0 and area.height > 0:
            self.surface.blit(self._grid_surface, area.topleft, area)

    def _build_grid_surface(self, background=None, grid_line=None) -> pygame.Surface:
        """预绘制网格线到离屏 Surface，每帧直接贴图以提高性能。

        background / grid_line 缺省时使用默认调色板；
        传入皮肤配色时按皮肤颜色绘制（供换肤调用）。
        """
        bg = background if background is not None else Palette.BACKGROUND
        line = grid_line if grid_line is not None else Palette.GRID_LINE
        surf = pygame.Surface((self.config.window_width, self.config.window_height))
        surf.fill(bg)
        cs = self.config.cell_size
        for x in range(0, self.config.window_width, cs):
            pygame.draw.line(surf, line, (x, 0), (x, self.config.window_height))
        for y in range(0, self.config.window_height, cs):
            pygame.draw.line(surf, line, (0, y), (self.config.window_width, y))
        return surf

    def apply_skin(self, skin) -> None:
        """应用皮肤配色：重建网格背景 Surface（背景色 + 网格线色）。"""
        self._grid_surface = self._build_grid_surface(skin.background, skin.grid_line)

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
    """游戏进行中的场景渲染器。

    传入 skin_manager 时蛇/食物颜色取自当前皮肤，实现游戏内换肤；
    未传入时回退到默认调色板（兼容旧调用）。
    """

    def __init__(self, screen: Screen, skin_manager=None) -> None:
        """记录屏幕与皮肤管理器引用。"""
        self.screen = screen
        self.skin_manager = skin_manager

    def _skin(self):
        """返回当前皮肤；未接入皮肤管理时返回 None（回退默认配色）。"""
        return self.skin_manager.current if self.skin_manager is not None else None

    # -- 蛇 -----------------------------------------------------------------

    def draw_snake(self, snake: Snake) -> None:
        """绘制整条蛇：头、身、尾使用不同颜色（优先取当前皮肤配色）。"""
        skin = self._skin()
        head_color = skin.snake_head if skin is not None else Palette.SNAKE_HEAD
        body_color = skin.snake_body if skin is not None else Palette.SNAKE_BODY
        tail_color = skin.snake_tail if skin is not None else Palette.SNAKE_TAIL
        n = snake.length
        for index, seg in enumerate(snake):
            rect = self.screen.cell_rect(seg.position)
            if index == 0:
                color = head_color
            elif index == n - 1:
                color = tail_color
            else:
                color = body_color
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
        """按类型绘制食物（优先取当前皮肤配色），特殊食物附带剩余时间指示环。"""
        skin = self._skin()
        rect = self.screen.cell_rect(food.position)
        if skin is not None:
            color_map = {
                FoodType.NORMAL: skin.food_normal,
                FoodType.GOLDEN: skin.food_golden,
                FoodType.SPEED: skin.food_speed,
            }
        else:
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
        """绘制暂停遮罩：半透明黑底 + "已暂停，按 P 继续" 居中提示。"""
        self._dim_overlay()
        w, h = self.screen.config.window_width, self.screen.config.window_height
        cx, cy = w // 2, h // 2
        self.screen.draw_text(
            "已暂停，按 P 继续", (cx, cy - 10), 40, Palette.TEXT_PRIMARY, center=True
        )
        self.screen.draw_text(
            "按 ESC 返回开始菜单", (cx, cy + 44), 20, Palette.TEXT_DIM, center=True
        )

    def _dim_overlay(self, alpha: int = 160) -> None:
        """在全屏上叠加半透明黑色遮罩。"""
        draw_dim_overlay(self.screen.surface, alpha)

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
        skin: Optional[str] = None,
        skin_names: Optional[List[str]] = None,
        on_skin_change=None,
    ) -> None:
        """初始化菜单项、选中状态与难度/皮肤档位。

        Args:
            items: 菜单项列表 [(文本, 动作名)]，默认 开始/难度/皮肤/退出。
            on_select: 确认菜单项时的回调，参数为动作名。
            difficulty: 初始难度档位，默认 NORMAL。
            on_difficulty_change: 难度切换时的回调，参数为新的 Difficulty。
            skin: 初始皮肤名称，默认 None（由渲染层填充文本）。
            skin_names: 全部可选皮肤名称列表（供左右键循环切换）。
            on_skin_change: 皮肤切换时的回调，参数为新皮肤名称。
        """
        self.difficulty: Difficulty = difficulty or Difficulty.NORMAL
        self.on_difficulty_change = on_difficulty_change
        self.skin: str = skin or ""
        self.skin_names: List[str] = list(skin_names) if skin_names else []
        self.on_skin_change = on_skin_change
        if items is None:
            items = [
                ("开始游戏", "start"),
                (f"选择难度: {self.difficulty.label}", "difficulty"),
                (f"选择皮肤: {self.skin}" if self.skin else "选择皮肤", "skin"),
                ("设置", "settings"),
                ("退出", "quit"),
            ]
        self.items: List[Tuple[str, str]] = list(items)
        self.selected_index = 0
        self.on_select = on_select

    @property
    def skin_index(self) -> int:
        """返回皮肤项在菜单中的下标，找不到返回 -1。"""
        for index, (_text, action) in enumerate(self.items):
            if action == "skin":
                return index
        return -1

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

    def set_skin(self, skin_name: str, notify: bool = True) -> None:
        """设置当前皮肤并刷新菜单标签，notify=True 时触发切换回调。"""
        self.skin = skin_name
        index = self.skin_index
        if index >= 0:
            self.set_item_text(index, f"选择皮肤: {skin_name}")
        if notify and self.on_skin_change is not None:
            self.on_skin_change(skin_name)

    def cycle_skin(self, step: int) -> str:
        """在 skin_names 列表中按 step 方向循环切换皮肤，返回新皮肤名。

        列表为空或当前皮肤不在列表中时，从第一套开始。
        """
        if not self.skin_names:
            return self.skin
        try:
            index = self.skin_names.index(self.skin)
        except ValueError:
            index = 0
        new_skin = self.skin_names[(index + step) % len(self.skin_names)]
        self.set_skin(new_skin)
        return new_skin

    def confirm(self) -> Optional[str]:
        """确认当前选中项，触发回调并返回动作名（无回调时仅返回动作名）。"""
        action = self.selected_action
        # 难度项上的确认等价于切到下一档
        if action == "difficulty":
            self.cycle_difficulty(1)
        # 皮肤项上的确认等价于切到下一套皮肤
        if action == "skin":
            self.cycle_skin(1)
        if self.on_select is not None:
            self.on_select(action)
        return action

    def handle_key(self, key: str) -> Optional[str]:
        """处理一个抽象按键，key 可为 up / down / left / right / confirm。

        左右键仅在选中"选择难度"或"选择皮肤"时生效，用于切换档位/皮肤；
        返回 confirm 产生的动作名，其余操作返回 None。
        """
        if key == "up":
            self.move_up()
            return None
        if key == "down":
            self.move_down()
            return None
        if key in ("left", "right"):
            if self.selected_action == "difficulty":
                self.cycle_difficulty(-1 if key == "left" else 1)
                return None
            if self.selected_action == "skin":
                self.cycle_skin(-1 if key == "left" else 1)
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


class SettingsPanel:
    """设置面板的逻辑状态：设置项导航与暂存值。

    与 Menu 同样的设计思路——只管状态与键盘逻辑、不直接绘制，
    绘制由 MenuRenderer.draw_settings_panel 完成，便于脱离窗口做单元测试。

    面板包含三个设置项：音量滑条、难度选择、皮肤选择；
    另外固定显示"暂停键说明"文字（无需导航）。

    Attributes:
        items: 设置项列表，形如 [(显示名, 动作名), ...]。
        selected_index: 当前选中的设置项下标。
        volume: 暂存的音量值（0-100 整数，保存时换算为 0.0-1.0）。
        difficulty: 暂存的难度档位。
        skin: 暂存的皮肤名称。
    """

    def __init__(
        self,
        volume: float = 0.7,
        difficulty: Optional[Difficulty] = None,
        skin: str = "",
        skin_names: Optional[List[str]] = None,
        on_save=None,
        on_cancel=None,
        on_change=None,
    ) -> None:
        """初始化设置项与暂存值（默认取当前生效的设置）。

        Args:
            volume: 当前音量（0.0-1.0），面板内部换算为 0-100 整数。
            difficulty: 当前难度档位，默认 NORMAL。
            skin: 当前皮肤名称。
            skin_names: 全部可选皮肤名称（保存/预览用）。
            on_save: 回车保存时的回调，参数为 (volume, difficulty, skin_name)。
            on_cancel: ESC 返回时的回调（用于放弃未保存的修改）。
            on_change: 数值每次变化时的回调，参数同 on_save；
                用于"调整即生效"——每按一次左右键、每拖动一次滑条都会触发，
                因此正式落盘（写 settings.json）仍只发生在保存时。
        """
        self.items: List[Tuple[str, str]] = [
            ("音量", "volume"),
            ("难度", "difficulty"),
            ("皮肤", "skin"),
        ]
        self.selected_index = 0
        self.volume: int = max(0, min(100, int(round(volume * 100))))
        self.difficulty: Difficulty = difficulty or Difficulty.NORMAL
        self.skin: str = skin
        self.skin_names: List[str] = list(skin_names) if skin_names else []
        self.on_save = on_save
        self.on_cancel = on_cancel
        self.on_change = on_change

    @property
    def volume_ratio(self) -> float:
        """音量的 0.0-1.0 表示（供 SoundManager 使用）。"""
        return self.volume / 100.0

    @property
    def selected_action(self) -> str:
        """当前选中设置项的动作名。"""
        return self.items[self.selected_index][1]

    @property
    def selected_text(self) -> str:
        """当前选中设置项的显示名。"""
        return self.items[self.selected_index][0]

    def move_up(self) -> None:
        """向上切换选中项，到顶循环回最后一项。"""
        self.selected_index = (self.selected_index - 1) % len(self.items)

    def move_down(self) -> None:
        """向下切换选中项，到底循环回第一项。"""
        self.selected_index = (self.selected_index + 1) % len(self.items)

    # 音量滑条每次左右键调整的步长（百分比）
    VOLUME_STEP = 10

    def adjust(self, step: int) -> None:
        """按 step 方向调整当前选中设置项的暂存值（正数增大，负数减小）。

        - 音量：步长 VOLUME_STEP，裁剪到 0-100；
        - 难度：在三档之间循环切换；
        - 皮肤：在 skin_names 中循环切换。
        调整后立即通过 on_change 推给应用层，实现"改完即生效"；
        写盘持久化仍只发生在回车保存时。
        """
        action = self.selected_action
        if action == "volume":
            self.volume = max(0, min(100, self.volume + step * SettingsPanel.VOLUME_STEP))
        elif action == "difficulty":
            self.difficulty = self.difficulty.next() if step > 0 else self.difficulty.previous()
        elif action == "skin" and self.skin_names:
            try:
                index = self.skin_names.index(self.skin)
            except ValueError:
                index = 0
            self.skin = self.skin_names[(index + step) % len(self.skin_names)]
        self._notify_change()

    def set_volume_percent(self, percent: float) -> None:
        """按百分比设置音量（鼠标拖动滑条时调用），并立即生效。

        百分比会先裁剪到 0-100 再四舍五入成整数；与当前值相同时不回调，
        避免拖动过程中每帧都向应用层重复推送同一个音量。
        """
        value = int(round(max(0.0, min(100.0, float(percent)))))
        if value == self.volume:
            return
        self.volume = value
        self._notify_change()

    def _notify_change(self) -> None:
        """把当前暂存值经校验后推给 on_change 回调，实现"调整即生效"。"""
        if self.on_change is not None:
            self.on_change(*self.apply())

    def apply(self) -> Tuple[float, Difficulty, str]:
        """把暂存值校验后返回 (音量比例, 难度, 皮肤名)。

        实时生效与回车保存共用这一份取值逻辑，避免越界/非法值流入
        SoundManager 与 Config：
        - 音量按 0-100 裁剪后换算为 0.0-1.0（外部直接改字段也不会越界）；
        - 难度必须是 Difficulty 枚举，否则回退普通档；
        - 皮肤不在可选列表中时回退第一套（列表为空则原样返回）。
        """
        volume = max(0.0, min(1.0, float(self.volume) / 100.0))
        difficulty = (
            self.difficulty if isinstance(self.difficulty, Difficulty) else Difficulty.NORMAL
        )
        skin = self.skin
        if self.skin_names and skin not in self.skin_names:
            skin = self.skin_names[0]
        return volume, difficulty, skin

    def confirm(self) -> str:
        """回车保存：触发 on_save 回调并返回动作名 "save"（取值经 apply 校验）。"""
        if self.on_save is not None:
            self.on_save(*self.apply())
        return "save"

    def cancel(self) -> str:
        """ESC 返回：触发 on_cancel 回调并返回动作名 "back"（未保存的修改被放弃）。"""
        if self.on_cancel is not None:
            self.on_cancel()
        return "back"

    def handle_key(self, key: str) -> Optional[str]:
        """处理一个抽象按键，key 可为 up / down / left / right / confirm。

        左右键调整当前选中设置项的数值；返回 confirm 产生的 "save"，
        其余操作返回 None。
        """
        if key == "up":
            self.move_up()
            return None
        if key == "down":
            self.move_down()
            return None
        if key in ("left", "right"):
            self.adjust(-1 if key == "left" else 1)
            return None
        if key == "confirm":
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


def draw_dim_overlay(surface: pygame.Surface, alpha: int = 160) -> None:
    """在给定 Surface 上叠加半透明黑色遮罩（暂停/结束画面共用）。"""
    w, h = surface.get_size()
    overlay = pygame.Surface((w, h), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, alpha))
    surface.blit(overlay, (0, 0))


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
        self._gradients: Dict[str, pygame.Surface] = {}
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

    def _ensure_gradient(self, skin=None) -> pygame.Surface:
        """获取（或按皮肤首次生成）菜单用的深色渐变背景。

        skin 为 None 时使用默认深色渐变；传入皮肤时以皮肤背景色
        生成专属渐变并缓存（键为皮肤名），实现菜单实时换肤。
        """
        from .skin import Skin

        key = skin.name if isinstance(skin, Skin) else "default"
        if key not in self._gradients:
            w, h = self.screen.config.window_width, self.screen.config.window_height
            if isinstance(skin, Skin):
                bg = skin.background
                top = Palette.lighten(bg, 0.5)
                bottom = tuple(int(c * 0.35) for c in bg)
                self._gradients[key] = build_vertical_gradient(w, h, top, bottom)
            else:
                self._gradients[key] = build_vertical_gradient(w, h)
        return self._gradients[key]

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

    # -- 设置面板 ----------------------------------------------------------

    # 设置面板的排布参数（行高更大，容纳滑条与档位条）
    SETTING_ROW_WIDTH = 420
    SETTING_ROW_HEIGHT = 56
    SETTING_ROW_GAP = 16
    # 音量滑条轨道尺寸（绘制与鼠标命中判断共用）
    VOLUME_TRACK_WIDTH = 200
    VOLUME_TRACK_HEIGHT = 10

    def settings_item_rects(self, panel: "SettingsPanel") -> List[pygame.Rect]:
        """计算设置面板各行的屏幕矩形，与绘制位置保持一致。"""
        w, h = self.screen.config.window_width, self.screen.config.window_height
        start_y = int(h * 0.42)
        rects: List[pygame.Rect] = []
        for index in range(len(panel.items)):
            rect = pygame.Rect(
                0, 0, MenuRenderer.SETTING_ROW_WIDTH, MenuRenderer.SETTING_ROW_HEIGHT
            )
            rect.center = (
                w // 2,
                start_y + index * (MenuRenderer.SETTING_ROW_HEIGHT + MenuRenderer.SETTING_ROW_GAP),
            )
            rects.append(rect)
        return rects

    @staticmethod
    def _volume_track_for_row(row_rect: pygame.Rect) -> pygame.Rect:
        """给定设置行矩形，返回音量滑条轨道矩形（绘制/命中/坐标换算共用）。"""
        track_h = MenuRenderer.VOLUME_TRACK_HEIGHT
        return pygame.Rect(
            row_rect.centerx - 20,
            row_rect.centery - track_h // 2,
            MenuRenderer.VOLUME_TRACK_WIDTH,
            track_h,
        )

    def volume_track_rect(self, panel: "SettingsPanel") -> pygame.Rect:
        """返回音量滑条轨道的屏幕矩形（用于把鼠标 x 坐标换算成音量）。"""
        rects = self.settings_item_rects(panel)
        actions = [action for _label, action in panel.items]
        index = actions.index("volume") if "volume" in actions else 0
        return self._volume_track_for_row(rects[index])

    def volume_hit_rect(self, panel: "SettingsPanel") -> pygame.Rect:
        """返回音量滑条的鼠标命中区域。

        轨道本身只有 10px 高，直接点中太苛刻，命中区上下各外扩 14px、
        左右各外扩 10px，让"按住拖动"更容易触发。
        """
        return self.volume_track_rect(panel).inflate(20, 28)

    def volume_percent_at(self, panel: "SettingsPanel", x: int) -> float:
        """把屏幕横坐标换算成音量百分比（0-100，超出轨道两端自动裁剪）。"""
        track = self.volume_track_rect(panel)
        if track.width <= 0:
            return 0.0
        ratio = (x - track.left) / float(track.width)
        return max(0.0, min(100.0, ratio * 100.0))

    def draw_settings_panel(
        self, panel: "SettingsPanel", skin_manager=None, translucent: bool = False
    ) -> None:
        """绘制设置面板：音量滑条、难度选择、皮肤选择与暂停键说明。

        skin_manager 传入时按当前皮肤实时换肤（背景渐变与标题配色）。
        translucent=True 用于"游戏中按 V 打开设置"：不再覆盖整屏渐变，
        而是把面板压在压暗后的战场之上，让玩家仍能看见当前局面。
        """
        skin = skin_manager.current if skin_manager is not None else None
        if translucent:
            # 压暗冻结的战场，面板本身仍是实心底色，保证文字可读
            draw_dim_overlay(self.screen.surface, 190)
        else:
            self.screen.surface.blit(self._ensure_gradient(skin), (0, 0))
        w, h = self.screen.config.window_width, self.screen.config.window_height
        fonts = self.screen.fonts

        # 标题（与主菜单同一风格）
        title_color = skin.accent if skin is not None else Palette.SNAKE_HEAD
        title = fonts.render("设置", 48, title_color)
        title_rect = title.get_rect(center=(w // 2, int(h * 0.2)))
        self.screen.surface.blit(title, title_rect)

        # 三个设置行：音量滑条 / 难度档位条 / 皮肤预览条
        rects = self.settings_item_rects(panel)
        for index, (label, action) in enumerate(panel.items):
            rect = rects[index]
            selected = index == panel.selected_index
            bg = Palette.BUTTON_HOVER if selected else Palette.BUTTON_BG
            border = (
                (skin.snake_head if skin is not None else Palette.SNAKE_HEAD)
                if selected
                else Palette.PANEL_BORDER
            )
            pygame.draw.rect(self.screen.surface, bg, rect, border_radius=8)
            pygame.draw.rect(self.screen.surface, border, rect, 2, border_radius=8)
            # 左侧固定标签
            prefix = "▶ " if selected else ""
            name = fonts.render(f"{prefix}{label}", 24, Palette.TEXT_PRIMARY if selected else Palette.TEXT_DIM)
            self.screen.surface.blit(name, name.get_rect(midleft=(rect.left + 18, rect.centery)))
            # 右侧控件
            if action == "volume":
                self._draw_volume_slider(rect, panel.volume, selected)
            elif action == "difficulty":
                self._draw_difficulty_chips(rect, panel.difficulty, selected)
            elif action == "skin" and skin_manager is not None:
                self._draw_skin_chips(rect, panel.skin, skin_manager, selected)

        # 暂停键说明（固定文字，无需导航）
        hint_y = rects[-1].bottom + 34
        self.screen.draw_text(
            "暂停键说明: P 暂停 / 继续 · V 打开设置 · 调整立即生效",
            (w // 2, hint_y),
            18,
            Palette.TEXT_DIM,
            center=True,
        )
        footer = (
            "←/→ 调整数值 · 拖动滑条调音量 · 回车 保存 · ESC 返回游戏"
            if translucent
            else "←/→ 调整数值 · 拖动滑条调音量 · 回车 保存 · ESC 返回"
        )
        self.screen.draw_text(
            footer,
            (w // 2, h - 36),
            16,
            Palette.TEXT_DIM,
            center=True,
        )

    def _draw_volume_slider(self, row_rect: pygame.Rect, volume: int, active: bool) -> None:
        """在设置行右侧绘制音量滑条：轨道 + 已填充部分 + 百分比文字。

        轨道矩形由 _volume_track_for_row 统一计算，与鼠标拖动时的
        坐标换算（volume_percent_at）共用同一套几何，保证"看到哪就能拖到哪"。
        """
        track = self._volume_track_for_row(row_rect)
        x, y = track.left, track.centery
        track_w = track.width
        # 轨道（未选中时更暗）
        pygame.draw.rect(
            self.screen.surface,
            Palette.PANEL_BG if not active else Palette.BUTTON_BG,
            track,
            border_radius=track.height // 2,
        )
        pygame.draw.rect(
            self.screen.surface, Palette.PANEL_BORDER, track, 1, border_radius=track.height // 2
        )
        # 已填充部分
        fill_w = int(track_w * volume / 100)
        if fill_w > 0:
            fill = pygame.Rect(x, track.top, fill_w, track.height)
            pygame.draw.rect(self.screen.surface, Palette.SUCCESS, fill, border_radius=track.height // 2)
        # 滑块
        knob_x = x + fill_w
        pygame.draw.circle(self.screen.surface, Palette.TEXT_PRIMARY, (knob_x, y), 9)
        pygame.draw.circle(self.screen.surface, Palette.PANEL_BORDER, (knob_x, y), 9, 2)
        # 百分比
        self.screen.draw_text(f"{volume}%", (knob_x + 20, y - 10), 18, Palette.TEXT_PRIMARY)

    def draw_main_menu(
        self, best_score: int, menu: "Menu", skin_manager=None, notice: Optional[str] = None
    ) -> None:
        """绘制开始菜单：深色渐变背景 + 居中标题 + 键盘选中高亮。

        skin_manager 传入时按当前皮肤实时换肤：渐变背景、标题颜色、
        选中边框与皮肤预览条全部取自当前皮肤配色。
        notice 为底部临时提示（如"最高分记录已清除"）。
        """
        skin = skin_manager.current if skin_manager is not None else None
        self.screen.surface.blit(self._ensure_gradient(skin), (0, 0))
        w, h = self.screen.config.window_width, self.screen.config.window_height
        fonts = self.screen.fonts

        # 标题与最高分（标题取皮肤强调色，实现菜单级实时预览）
        title_color = skin.accent if skin is not None else Palette.SNAKE_HEAD
        title = fonts.render("贪吃蛇", 64, title_color)
        title_rect = title.get_rect(center=(w // 2, int(h * 0.26)))
        self.screen.surface.blit(title, title_rect)
        sub = fonts.render(f"历史最高分: {best_score}", 24, Palette.TEXT_DIM)
        sub_rect = sub.get_rect(center=(w // 2, int(h * 0.26) + 58))
        self.screen.surface.blit(sub, sub_rect)
        # 临时提示（清除最高分后的反馈），显示在最高分下方
        if notice:
            self.screen.draw_text(
                notice, (w // 2, int(h * 0.26) + 92), 18, Palette.DANGER, center=True
            )

        # 菜单项：选中项高亮加边框，未选中项半透明暗色
        rects = self.item_rects(menu)
        for index, (label, action) in enumerate(menu.items):
            rect = rects[index]
            selected = index == menu.selected_index
            bg = Palette.BUTTON_HOVER if selected else Palette.BUTTON_BG
            border = (
                (skin.snake_head if skin is not None else Palette.SNAKE_HEAD)
                if selected
                else Palette.PANEL_BORDER
            )
            pygame.draw.rect(self.screen.surface, bg, rect, border_radius=8)
            pygame.draw.rect(self.screen.surface, border, rect, 2, border_radius=8)
            text_color = Palette.TEXT_PRIMARY if selected else Palette.TEXT_DIM
            prefix = "▶ " if selected else ""
            rendered = fonts.render(f"{prefix}{label}", 24, text_color)
            text_rect = rendered.get_rect(center=rect.center)
            self.screen.surface.blit(rendered, text_rect)
            # 难度项右侧绘制三档档位条，高亮当前档位
            if action == "difficulty":
                self._draw_difficulty_chips(rect, menu.difficulty, selected)
            # 皮肤项右侧绘制皮肤预览条（各皮肤蛇头色样 + 名称）
            elif action == "skin" and skin_manager is not None:
                self._draw_skin_chips(rect, menu.skin, skin_manager, selected)

        self.screen.draw_text(
            "↑/↓ 选择 · ←/→ 切换难度/皮肤 · 回车 确认 · 长按 C 清除最高分 · ESC 退出",
            (w // 2, h - 36),
            16,
            Palette.TEXT_DIM,
            center=True,
        )

    def _draw_skin_chips(
        self, item_rect: pygame.Rect, current_skin: str, skin_manager, active: bool
    ) -> None:
        """在菜单项右侧绘制各皮肤预览条：色块 + 皮肤名，高亮当前皮肤。

        每个预览条左侧画该皮肤的蛇头颜色方块（实时预览主色调），
        当前皮肤条使用该皮肤的蛇头色描边并提亮。
        """
        fonts = self.screen.fonts
        chip_w, chip_h, gap = 76, 28, 8
        chips = skin_manager.skins
        total_w = len(chips) * chip_w + (len(chips) - 1) * gap
        x = item_rect.right + 16
        y = item_rect.centery - chip_h // 2
        max_x = self.screen.config.window_width - total_w - 10
        x = min(x, max_x)
        for index, chip_skin in enumerate(chips):
            chip = pygame.Rect(x + index * (chip_w + gap), y, chip_w, chip_h)
            is_current = chip_skin.name == current_skin
            bg_color = Palette.BUTTON_HOVER if is_current else (
                Palette.BUTTON_BG if active else Palette.PANEL_BG
            )
            pygame.draw.rect(self.screen.surface, bg_color, chip, border_radius=6)
            border_color = chip_skin.snake_head if is_current else Palette.PANEL_BORDER
            pygame.draw.rect(self.screen.surface, border_color, chip, 2 if is_current else 1, border_radius=6)
            # 皮肤主色方块（预览）
            dot = pygame.Rect(0, 0, 10, 10)
            dot.center = (chip.x + 13, chip.centery)
            pygame.draw.rect(self.screen.surface, chip_skin.snake_head, dot, border_radius=2)
            label = fonts.render(chip_skin.name, 13, Palette.TEXT_PRIMARY if is_current else Palette.TEXT_DIM)
            label_rect = label.get_rect(midleft=(chip.x + 24, chip.centery))
            self.screen.surface.blit(label, label_rect)

    def _draw_difficulty_chips(self, item_rect: pygame.Rect, current: Difficulty, active: bool) -> None:
        """在菜单项右侧绘制 简单/普通/困难 三个档位标签，高亮当前档位。

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
            is_current = level == current
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
        # 结束画面遮罩：半透明黑底（与暂停遮罩同一实现）
        draw_dim_overlay(self.screen.surface)
        w, h = self.screen.config.window_width, self.screen.config.window_height
        cx, cy = w // 2, h // 2
        self.screen.draw_text("游戏结束", (cx, cy - 120), 56, Palette.DANGER, center=True)
        self.screen.draw_text(f"原因: {reason}", (cx, cy - 60), 24, Palette.TEXT_DIM, center=True)
        self.screen.draw_text(f"本局得分: {score}", (cx, cy), 32, Palette.TEXT_PRIMARY, center=True)
        if is_record:
            # 破纪录：成绩已由 HighScoreManager 自动写入 highscore.json
            self.screen.draw_text("新纪录！已保存", (cx, cy + 44), 28, Palette.FOOD_GOLDEN, center=True)
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
