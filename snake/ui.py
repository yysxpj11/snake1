# -*- coding: utf-8 -*-
"""界面模块。

负责一切与渲染、输入界面相关的工作：
- Screen 封装窗口、离屏后缓冲（双缓冲）与网格绘制
- Renderer 渲染器基类（沉淀各渲染器共用的绘制原语）
- HUD 顶部信息栏
- MenuRenderer 主菜单 / 暂停 / 结束画面
- GameRenderer 游戏进行时的场景渲染

布局尺寸、字号、颜色等常量集中在 snake.config，本模块不写魔法数字。

注意：pygame 初始化由 main 模块负责，本模块不做 import pygame 的副作用，
顶层直接 import pygame 仅供类型提示（运行环境保证已安装）。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import pygame

from .config import (
    CELL_RECT_INSET,
    CHIP_EDGE_OFFSET,
    CHIP_GAP,
    CHIP_HEIGHT,
    Config,
    DIFFICULTY_CHIP_WIDTH,
    Difficulty,
    DIM_OVERLAY_ALPHA,
    FOOD_BLINK_RATIO,
    FOOD_BLINK_STEPS,
    FONT_SIZE_GAME_OVER_REASON,
    FONT_SIZE_GAME_OVER_TITLE,
    FONT_SIZE_HINT,
    FONT_SIZE_ITEM,
    FONT_SIZE_MENU_TITLE,
    FONT_SIZE_NOTICE,
    FONT_SIZE_PANEL_TITLE,
    FONT_SIZE_SMALL,
    FONT_SIZE_SUBTITLE,
    FOOTER_BOTTOM_OFFSET,
    HUD_HEIGHT,
    HUD_TEXT_OFFSET_X,
    HUD_TEXT_OFFSET_Y,
    MENU_ITEM_GAP,
    MENU_ITEM_HEIGHT,
    MENU_ITEM_WIDTH,
    MENU_NOTICE_OFFSET,
    MENU_START_Y_RATIO,
    MENU_SUBTITLE_OFFSET,
    MENU_TITLE_Y_RATIO,
    NEW_SEGMENT_BRIGHTEN,
    Palette,
    ROW_LABEL_INSET,
    SELECTED_PREFIX,
    SETTINGS_DIM_OVERLAY_ALPHA,
    SETTINGS_ROW_GAP,
    SETTINGS_ROW_HEIGHT,
    SETTINGS_ROW_WIDTH,
    SETTINGS_START_Y_RATIO,
    SETTINGS_TITLE_Y_RATIO,
    SKIN_CHIP_DOT_SIZE,
    SKIN_CHIP_WIDTH,
    VOLUME_HIT_INFLATE_X,
    VOLUME_HIT_INFLATE_Y,
    VOLUME_KNOB_RADIUS,
    VOLUME_TRACK_HEIGHT,
    VOLUME_TRACK_OFFSET_X,
    VOLUME_TRACK_WIDTH,
)
from .food import Food, FoodType
from .snake import Snake
from .utils import format_score, format_time


class FontBank:
    """集中管理各字号字体对象，避免每帧重复创建字体。"""

    def __init__(self) -> None:
        """按需创建常用字号的字体。"""
        self._cache: Dict[str, pygame.font.Font] = {}
        base = pygame.font.get_default_font()
        for size in (12, 14, 16, 20, 24, 32, 48, 64):
            self._cache[str(size)] = pygame.font.Font(base, size)

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
        """把网格坐标转换为像素矩形（向内收缩留出格子缝隙感）。"""
        cs = self.config.cell_size
        x, y = cell
        return pygame.Rect(
            x * cs + CELL_RECT_INSET,
            y * cs + CELL_RECT_INSET,
            cs - 2 * CELL_RECT_INSET,
            cs - 2 * CELL_RECT_INSET,
        )


class Renderer:
    """渲染器基类：沉淀各渲染器共用的绘制原语。

    子类（HUD / GameRenderer / MenuRenderer）通过它拿到 screen 的
    常用引用，并复用圆角矩形、文字标签、标题 / 底部提示、
    选中行、档位条等重复出现的绘制代码，避免各画各的。
    """

    def __init__(self, screen: Screen) -> None:
        """记录屏幕引用；皮肤管理器由子类按需注入。"""
        self.screen = screen
        self.skin_manager = None

    # -- 常用引用 -----------------------------------------------------------

    @property
    def surface(self) -> pygame.Surface:
        """后缓冲 Surface（所有绘制都写在这里）。"""
        return self.screen.surface

    @property
    def fonts(self) -> FontBank:
        """字体库。"""
        return self.screen.fonts

    @property
    def config(self) -> Config:
        """窗口配置。"""
        return self.screen.config

    @property
    def size(self) -> Tuple[int, int]:
        """窗口尺寸 (宽, 高)。"""
        return self.config.window_width, self.config.window_height

    def _skin(self):
        """返回当前皮肤；未接入皮肤管理时返回 None（回退默认配色）。"""
        return self.skin_manager.current if self.skin_manager is not None else None

    # -- 通用绘制原语 -------------------------------------------------------

    def draw_round_rect(
        self,
        rect: pygame.Rect,
        fill=None,
        border=None,
        border_width: int = 1,
        radius: int = 6,
    ) -> None:
        """绘制圆角矩形：可只填色、只描边或两者都画。"""
        if fill is not None:
            pygame.draw.rect(self.surface, fill, rect, border_radius=radius)
        if border is not None:
            pygame.draw.rect(
                self.surface, border, rect, border_width, border_radius=radius
            )

    def blit_text(
        self,
        text: str,
        size: int,
        color: Tuple[int, int, int],
        rect: pygame.Rect,
        align: str = "center",
    ) -> pygame.Rect:
        """渲染文字并对齐到 rect（center / midleft / topleft），返回文字矩形。"""
        rendered = self.fonts.render(text, size, color)
        text_rect = rendered.get_rect()
        if align == "center":
            text_rect.center = rect.center
        elif align == "midleft":
            text_rect.midleft = (rect.left + ROW_LABEL_INSET, rect.centery)
        else:
            text_rect.topleft = rect.topleft
        self.surface.blit(rendered, text_rect)
        return text_rect

    def draw_title(
        self,
        text: str,
        y_ratio: float,
        size: int,
        color: Tuple[int, int, int],
    ) -> None:
        """在窗口上部绘制居中大标题（y_ratio 为中心所在的高度比例）。"""
        w, h = self.size
        rendered = self.fonts.render(text, size, color)
        title_rect = rendered.get_rect(center=(w // 2, int(h * y_ratio)))
        self.surface.blit(rendered, title_rect)

    def draw_footer(self, text: str) -> None:
        """在窗口底部绘制居中操作提示。"""
        w, h = self.size
        self.screen.draw_text(
            text, (w // 2, h - FOOTER_BOTTOM_OFFSET), FONT_SIZE_NOTICE,
            Palette.TEXT_DIM, center=True,
        )

    def selected_border_color(self, selected: bool) -> Tuple[int, int, int]:
        """选中行的描边颜色：取当前皮肤蛇头色，未换肤时回退默认强调色。"""
        skin = self._skin()
        if selected:
            return skin.snake_head if skin is not None else Palette.SNAKE_HEAD
        return Palette.PANEL_BORDER

    def draw_selectable_row(
        self,
        rect: pygame.Rect,
        label: str,
        selected: bool,
        text_align: str = "center",
    ) -> None:
        """绘制一行可选中条目：底色 + 描边 + 前缀与文字。

        主菜单项与设置面板行共用这一份绘制代码；
        text_align="center" 用于菜单项（文字居中），
        "midleft" 用于设置行（左侧固定标签）。
        """
        skin = self._skin()
        bg = Palette.BUTTON_HOVER if selected else Palette.BUTTON_BG
        self.draw_round_rect(
            rect, fill=bg, border=self.selected_border_color(selected),
            border_width=2, radius=8,
        )
        color = Palette.TEXT_PRIMARY if selected else Palette.TEXT_DIM
        prefix = SELECTED_PREFIX if selected else ""
        self.blit_text(f"{prefix}{label}", FONT_SIZE_ITEM, color, rect, align=text_align)

    def chip_rects(
        self,
        item_rect: pygame.Rect,
        count: int,
        chip_width: int,
    ) -> List[pygame.Rect]:
        """计算一排档位条（chips）的矩形，贴着条目右侧排列、不超出窗口。

        难度档位条与皮肤预览条共用同一套几何。
        """
        _, h = self.size
        total_w = count * chip_width + (count - 1) * CHIP_GAP
        x = item_rect.right + ROW_LABEL_INSET
        y = item_rect.centery - CHIP_HEIGHT // 2
        max_x = self.config.window_width - total_w - CHIP_EDGE_OFFSET
        x = min(x, max_x)
        return [
            pygame.Rect(x + index * (chip_width + CHIP_GAP), y, chip_width, CHIP_HEIGHT)
            for index in range(count)
        ]


class HUD(Renderer):
    """顶部信息栏：得分、最高分、长度、时间。

    过去这个类写好了却从未接入渲染循环，游戏进行中看不到任何分数；
    现在作为渲染器家族的一员由战场渲染负责绘制，
    并提供 signature() 供增量渲染判断顶栏内容是否变化。
    """

    HEIGHT = HUD_HEIGHT

    def __init__(self, screen: Screen, best_score: int) -> None:
        """初始化并记录最高分。"""
        super().__init__(screen)
        self.best_score = best_score
        self.message: str = ""
        self.message_timer = 0.0

    @property
    def rect(self) -> pygame.Rect:
        """顶栏矩形。"""
        return pygame.Rect(0, 0, self.config.window_width, HUD_HEIGHT)

    def signature(self, score: int, length: int, elapsed: float) -> tuple:
        """返回当前顶栏内容签名（分数/最高分/长度/整秒时间/提示文字）。"""
        return (score, self.best_score, length, int(elapsed), self.message)

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
        bar = self.rect
        width = bar.width
        pygame.draw.rect(self.surface, Palette.PANEL_BG, bar)
        pygame.draw.line(
            self.surface, Palette.PANEL_BORDER,
            (0, HUD_HEIGHT), (width, HUD_HEIGHT),
        )
        y = HUD_TEXT_OFFSET_Y
        self.screen.draw_text(
            f"得分: {format_score(score)}", (HUD_TEXT_OFFSET_X, y),
            FONT_SIZE_ITEM, Palette.TEXT_PRIMARY,
        )
        self.screen.draw_text(
            f"最高: {format_score(self.best_score)}", (width // 4, y),
            FONT_SIZE_ITEM, Palette.TEXT_DIM,
        )
        self.screen.draw_text(
            f"长度: {length}", (width // 2, y), FONT_SIZE_ITEM, Palette.TEXT_PRIMARY
        )
        self.screen.draw_text(
            f"时间: {format_time(elapsed)}", (int(width * 0.7), y),
            FONT_SIZE_ITEM, Palette.TEXT_PRIMARY,
        )
        if self.message:
            self.screen.draw_text(
                self.message, (width - 120, y), FONT_SIZE_ITEM, Palette.SUCCESS
            )


class GameRenderer(Renderer):
    """游戏进行中的场景渲染器。

    传入 skin_manager 时蛇/食物颜色取自当前皮肤，实现游戏内换肤；
    未传入时回退到默认调色板（兼容旧调用）。
    """

    # 加速光晕的边缘厚度与透明度上限
    HALO_MAX_THICKNESS = 6
    HALO_MAX_ALPHA = 120

    def __init__(self, screen: Screen, skin_manager=None) -> None:
        """记录屏幕与皮肤管理器引用。"""
        super().__init__(screen)
        self.skin_manager = skin_manager

    # -- 蛇 -----------------------------------------------------------------

    def segment_color(self, index: int, length: int, segment) -> Tuple[int, int, int]:
        """返回第 index 节蛇身的颜色（头/身/尾不同，新生节更亮）。

        单独抽出来是为了让增量渲染能"只算颜色、比差异"，
        而不必先画一遍才知道这一格长什么样。
        """
        skin = self._skin()
        head_color = skin.snake_head if skin is not None else Palette.SNAKE_HEAD
        body_color = skin.snake_body if skin is not None else Palette.SNAKE_BODY
        tail_color = skin.snake_tail if skin is not None else Palette.SNAKE_TAIL
        if index == 0:
            color = head_color
        elif index == length - 1:
            color = tail_color
        else:
            color = body_color
        if segment.is_new:
            color = Palette.lighten(color, NEW_SEGMENT_BRIGHTEN)
        return color

    def draw_segment(self, index: int, length: int, segment) -> None:
        """绘制一节蛇身（整条绘制与增量绘制共用同一份绘制代码）。"""
        rect = self.screen.cell_rect(segment.position)
        color = self.segment_color(index, length, segment)
        pygame.draw.rect(self.surface, color, rect, border_radius=4)

    def draw_snake(self, snake: Snake) -> None:
        """绘制整条蛇：头、身、尾使用不同颜色（优先取当前皮肤配色）。"""
        length = snake.length
        for index, seg in enumerate(snake):
            self.draw_segment(index, length, seg)
        self.draw_eyes(snake)

    def draw_eyes(self, snake: Snake) -> None:
        """在蛇头上绘制两只眼睛，指示朝向。"""
        cs = self.config.cell_size
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
            pygame.draw.circle(self.surface, Palette.SNAKE_EYE, pos, radius)

    # -- 食物 ---------------------------------------------------------------

    def food_color(self, food: Food) -> Tuple[int, int, int]:
        """返回食物颜色（优先取当前皮肤配色），供绘制与增量比对共用。"""
        skin = self._skin()
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
        return color_map.get(food.ftype, Palette.FOOD_NORMAL)

    def draw_food(self, food: Food) -> None:
        """按类型绘制食物（优先取当前皮肤配色），特殊食物附带剩余时间指示环。"""
        rect = self.screen.cell_rect(food.position)
        color = self.food_color(food)
        pygame.draw.circle(self.surface, color, rect.center, rect.width // 2 - CELL_RECT_INSET)
        if food.is_special:
            ratio = food.remaining_ratio()
            if ratio < FOOD_BLINK_RATIO:
                # 快过期时闪烁提醒
                if int(ratio * FOOD_BLINK_STEPS) % 2 == 0:
                    pygame.draw.circle(
                        self.surface,
                        Palette.TEXT_PRIMARY,
                        rect.center,
                        rect.width // 2 + CELL_RECT_INSET,
                        1,
                    )

    def draw_foods(self, foods: Sequence[Food]) -> None:
        """绘制场上所有食物。"""
        for food in foods:
            self.draw_food(food)

    # -- 整个战场 -----------------------------------------------------------

    def draw_playfield(self, game, speed_ratio: float = 0.0) -> None:
        """绘制完整战场：食物 + 蛇 +（可选）加速光晕。

        整屏重绘（暂停 / 结束 / 换肤后的第一帧）与增量渲染器的
        _draw_full 共用这一份代码，避免两处各画一遍。
        """
        food_manager = getattr(game, "food_manager", None)
        if food_manager is not None:
            self.draw_foods(food_manager.foods)
        if game.snake is not None:
            self.draw_snake(game.snake)
        if speed_ratio > 0:
            self.draw_speed_effect(True, speed_ratio)

    # -- 覆盖层 -------------------------------------------------------------

    def draw_pause_overlay(self) -> None:
        """绘制暂停遮罩：半透明黑底 + "已暂停，按 P 继续" 居中提示。"""
        self._dim_overlay()
        w, h = self.size
        cx, cy = w // 2, h // 2
        self.screen.draw_text(
            "已暂停，按 P 继续", (cx, cy - 10), 40, Palette.TEXT_PRIMARY, center=True
        )
        self.screen.draw_text(
            "按 ESC 返回开始菜单", (cx, cy + 44), 20, Palette.TEXT_DIM, center=True
        )

    def _dim_overlay(self, alpha: int = DIM_OVERLAY_ALPHA) -> None:
        """在全屏上叠加半透明黑色遮罩。"""
        draw_dim_overlay(self.surface, alpha)

    def draw_speed_effect(self, active: bool, ratio: float) -> None:
        """加速效果激活时在屏幕边缘绘制光晕（颜色随当前皮肤）。"""
        if not active:
            return
        w, h = self.size
        border = pygame.Surface((w, h), pygame.SRCALPHA)
        thickness = max(2, int(self.HALO_MAX_THICKNESS * ratio))
        alpha = int(self.HALO_MAX_ALPHA * ratio)
        skin = self._skin()
        base = skin.food_speed if skin is not None else Palette.SPEED_HALO
        pygame.draw.rect(border, (*base, alpha), border.get_rect(), thickness)
        self.surface.blit(border, (0, 0))


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


class MenuRenderer(Renderer):
    """主菜单、设置面板、结束画面等静态界面的渲染。

    可选中行、档位条、标题 / 底部提示等重复出现的绘制代码
    全部复用基类 Renderer 的原语；布局尺寸取自 snake.config。
    """

    # 渐变背景的明暗端比例（按皮肤背景色推算）
    GRADIENT_LIGHTEN = 0.5
    GRADIENT_DARKEN = 0.35

    def __init__(self, screen: Screen) -> None:
        """初始化渐变背景缓存。"""
        super().__init__(screen)
        self._gradients: Dict[str, pygame.Surface] = {}

    def blit_gradient(self, skin=None) -> None:
        """把菜单/面板用的深色渐变背景铺满后缓冲。

        skin 为 None 时使用默认深色渐变；传入皮肤时以皮肤背景色
        生成专属渐变并缓存（键为皮肤名），实现菜单实时换肤。
        """
        self.surface.blit(self._ensure_gradient(skin), (0, 0))

    def _ensure_gradient(self, skin=None) -> pygame.Surface:
        """获取（或按皮肤首次生成）渐变背景 Surface。"""
        from .skin import Skin

        key = skin.name if isinstance(skin, Skin) else "default"
        if key not in self._gradients:
            w, h = self.size
            if isinstance(skin, Skin):
                bg = skin.background
                top = Palette.lighten(bg, self.GRADIENT_LIGHTEN)
                bottom = tuple(int(c * self.GRADIENT_DARKEN) for c in bg)
                self._gradients[key] = build_vertical_gradient(w, h, top, bottom)
            else:
                self._gradients[key] = build_vertical_gradient(w, h)
        return self._gradients[key]

    def item_rects(self, menu: "Menu") -> List[pygame.Rect]:
        """计算各菜单项的屏幕矩形，与绘制位置保持一致（供点击命中使用）。"""
        w, h = self.size
        start_y = int(h * MENU_START_Y_RATIO)
        rects: List[pygame.Rect] = []
        for index in range(len(menu.items)):
            rect = pygame.Rect(0, 0, MENU_ITEM_WIDTH, MENU_ITEM_HEIGHT)
            rect.center = (w // 2, start_y + index * (MENU_ITEM_HEIGHT + MENU_ITEM_GAP))
            rects.append(rect)
        return rects

    # -- 设置面板 ----------------------------------------------------------

    def settings_item_rects(self, panel: "SettingsPanel") -> List[pygame.Rect]:
        """计算设置面板各行的屏幕矩形，与绘制位置保持一致。"""
        w, h = self.size
        start_y = int(h * SETTINGS_START_Y_RATIO)
        rects: List[pygame.Rect] = []
        for index in range(len(panel.items)):
            rect = pygame.Rect(0, 0, SETTINGS_ROW_WIDTH, SETTINGS_ROW_HEIGHT)
            rect.center = (
                w // 2,
                start_y + index * (SETTINGS_ROW_HEIGHT + SETTINGS_ROW_GAP),
            )
            rects.append(rect)
        return rects

    @staticmethod
    def _volume_track_for_row(row_rect: pygame.Rect) -> pygame.Rect:
        """给定设置行矩形，返回音量滑条轨道矩形（绘制/命中/坐标换算共用）。"""
        return pygame.Rect(
            row_rect.centerx - VOLUME_TRACK_OFFSET_X,
            row_rect.centery - VOLUME_TRACK_HEIGHT // 2,
            VOLUME_TRACK_WIDTH,
            VOLUME_TRACK_HEIGHT,
        )

    def volume_track_rect(self, panel: "SettingsPanel") -> pygame.Rect:
        """返回音量滑条轨道的屏幕矩形（用于把鼠标 x 坐标换算成音量）。"""
        rects = self.settings_item_rects(panel)
        actions = [action for _label, action in panel.items]
        index = actions.index("volume") if "volume" in actions else 0
        return self._volume_track_for_row(rects[index])

    def volume_hit_rect(self, panel: "SettingsPanel") -> pygame.Rect:
        """返回音量滑条的鼠标命中区域。

        轨道本身只有 10px 高，直接点中太苛刻，命中区向外扩展一圈，
        让"按住拖动"更容易触发。
        """
        return self.volume_track_rect(panel).inflate(
            VOLUME_HIT_INFLATE_X, VOLUME_HIT_INFLATE_Y
        )

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
        self.skin_manager = skin_manager
        if translucent:
            # 压暗冻结的战场，面板本身仍是实心底色，保证文字可读
            draw_dim_overlay(self.surface, SETTINGS_DIM_OVERLAY_ALPHA)
        else:
            self.blit_gradient(skin)

        # 标题（与主菜单同一风格，取皮肤强调色实现实时预览）
        self.draw_title(
            "设置", SETTINGS_TITLE_Y_RATIO, FONT_SIZE_PANEL_TITLE,
            skin.accent if skin is not None else Palette.SNAKE_HEAD,
        )

        # 三个设置行：音量滑条 / 难度档位条 / 皮肤预览条
        rects = self.settings_item_rects(panel)
        for index, (label, action) in enumerate(panel.items):
            rect = rects[index]
            selected = index == panel.selected_index
            self.draw_selectable_row(rect, label, selected, text_align="midleft")
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
            (self.size[0] // 2, hint_y),
            FONT_SIZE_NOTICE,
            Palette.TEXT_DIM,
            center=True,
        )
        footer = (
            "←/→ 调整数值 · 拖动滑条调音量 · 回车 保存 · ESC 返回游戏"
            if translucent
            else "←/→ 调整数值 · 拖动滑条调音量 · 回车 保存 · ESC 返回"
        )
        self.draw_footer(footer)

    def _draw_volume_slider(self, row_rect: pygame.Rect, volume: int, active: bool) -> None:
        """在设置行右侧绘制音量滑条：轨道 + 已填充部分 + 百分比文字。

        轨道矩形由 _volume_track_for_row 统一计算，与鼠标拖动时的
        坐标换算（volume_percent_at）共用同一套几何，保证"看到哪就能拖到哪"。
        """
        track = self._volume_track_for_row(row_rect)
        radius = track.height // 2
        # 轨道（未选中时更暗）
        self.draw_round_rect(
            track,
            fill=Palette.PANEL_BG if not active else Palette.BUTTON_BG,
            border=Palette.PANEL_BORDER,
            radius=radius,
        )
        # 已填充部分
        fill_w = int(track.width * volume / 100)
        if fill_w > 0:
            fill = pygame.Rect(track.left, track.top, fill_w, track.height)
            pygame.draw.rect(self.surface, Palette.SUCCESS, fill, border_radius=radius)
        # 滑块
        knob_x = track.left + fill_w
        knob_y = track.centery
        pygame.draw.circle(self.surface, Palette.TEXT_PRIMARY, (knob_x, knob_y), VOLUME_KNOB_RADIUS)
        pygame.draw.circle(
            self.surface, Palette.PANEL_BORDER, (knob_x, knob_y), VOLUME_KNOB_RADIUS, 2
        )
        # 百分比
        self.screen.draw_text(
            f"{volume}%", (knob_x + VOLUME_TRACK_OFFSET_X, knob_y - 10),
            FONT_SIZE_NOTICE, Palette.TEXT_PRIMARY,
        )

    def draw_main_menu(
        self, best_score: int, menu: "Menu", skin_manager=None, notice: Optional[str] = None
    ) -> None:
        """绘制开始菜单：深色渐变背景 + 居中标题 + 键盘选中高亮。

        skin_manager 传入时按当前皮肤实时换肤：渐变背景、标题颜色、
        选中边框与皮肤预览条全部取自当前皮肤配色。
        notice 为底部临时提示（如"最高分记录已清除"）。
        """
        skin = skin_manager.current if skin_manager is not None else None
        self.skin_manager = skin_manager
        self.blit_gradient(skin)
        w, h = self.size

        # 标题与最高分（标题取皮肤强调色，实现菜单级实时预览）
        title_color = skin.accent if skin is not None else Palette.SNAKE_HEAD
        self.draw_title("贪吃蛇", MENU_TITLE_Y_RATIO, FONT_SIZE_MENU_TITLE, title_color)
        sub_y = int(h * MENU_TITLE_Y_RATIO) + MENU_SUBTITLE_OFFSET
        self.screen.draw_text(
            f"历史最高分: {best_score}", (w // 2, sub_y),
            FONT_SIZE_SUBTITLE, Palette.TEXT_DIM, center=True,
        )
        # 临时提示（清除最高分后的反馈），显示在最高分下方
        if notice:
            self.screen.draw_text(
                notice, (w // 2, int(h * MENU_TITLE_Y_RATIO) + MENU_NOTICE_OFFSET),
                FONT_SIZE_NOTICE, Palette.DANGER, center=True,
            )

        # 菜单项：选中项高亮加边框，未选中项半透明暗色
        rects = self.item_rects(menu)
        for index, (label, action) in enumerate(menu.items):
            rect = rects[index]
            selected = index == menu.selected_index
            self.draw_selectable_row(rect, label, selected, text_align="center")
            # 难度项右侧绘制三档档位条，高亮当前档位
            if action == "difficulty":
                self._draw_difficulty_chips(rect, menu.difficulty, selected)
            # 皮肤项右侧绘制皮肤预览条（各皮肤蛇头色样 + 名称）
            elif action == "skin" and skin_manager is not None:
                self._draw_skin_chips(rect, menu.skin, skin_manager, selected)

        self.draw_footer(
            "↑/↓ 选择 · ←/→ 切换难度/皮肤 · 回车 确认 · 长按 C 清除最高分 · ESC 退出"
        )

    def _draw_skin_chips(
        self, item_rect: pygame.Rect, current_skin: str, skin_manager, active: bool
    ) -> None:
        """在菜单项右侧绘制各皮肤预览条：色块 + 皮肤名，高亮当前皮肤。

        每个预览条左侧画该皮肤的蛇头颜色方块（实时预览主色调），
        当前皮肤条使用该皮肤的蛇头色描边并提亮。
        """
        chips = skin_manager.skins
        rects = self.chip_rects(item_rect, len(chips), SKIN_CHIP_WIDTH)
        for chip, chip_skin in zip(rects, chips):
            is_current = chip_skin.name == current_skin
            bg_color = Palette.BUTTON_HOVER if is_current else (
                Palette.BUTTON_BG if active else Palette.PANEL_BG
            )
            self.draw_round_rect(
                chip,
                fill=bg_color,
                border=chip_skin.snake_head if is_current else Palette.PANEL_BORDER,
                border_width=2 if is_current else 1,
            )
            # 皮肤主色方块（预览）
            dot = pygame.Rect(0, 0, SKIN_CHIP_DOT_SIZE, SKIN_CHIP_DOT_SIZE)
            dot.center = (chip.x + 13, chip.centery)
            pygame.draw.rect(self.surface, chip_skin.snake_head, dot, border_radius=2)
            self.blit_text(
                chip_skin.name, FONT_SIZE_SMALL,
                Palette.TEXT_PRIMARY if is_current else Palette.TEXT_DIM,
                pygame.Rect(chip.x + 24, chip.top, chip.width, chip.height),
                align="midleft",
            )

    def _draw_difficulty_chips(self, item_rect: pygame.Rect, current: Difficulty, active: bool) -> None:
        """在菜单项右侧绘制 简单/普通/困难 三个档位标签，高亮当前档位。

        active 表示难度项当前是否被选中，选中时档位条整体更亮以突出可操作。
        """
        levels = Difficulty.levels()
        rects = self.chip_rects(item_rect, len(levels), DIFFICULTY_CHIP_WIDTH)
        for chip, level in zip(rects, levels):
            is_current = level == current
            if is_current:
                bg_color = self.selected_border_color(True)
                text_color = Palette.BACKGROUND
            else:
                bg_color = Palette.BUTTON_BG if active else Palette.PANEL_BG
                text_color = Palette.TEXT_DIM if active else Palette.PANEL_BORDER
            self.draw_round_rect(
                chip, fill=bg_color, border=Palette.PANEL_BORDER,
                border_width=1,
            )
            self.blit_text(level.label, FONT_SIZE_HINT, text_color, chip, align="center")

    def draw_game_over(
        self, score: int, best: int, reason: str, is_record: bool
    ) -> None:
        """绘制结束画面。"""
        self.screen.draw_background()
        # 结束画面遮罩：半透明黑底（与暂停遮罩同一实现）
        draw_dim_overlay(self.surface)
        w, h = self.size
        cx, cy = w // 2, h // 2
        self.screen.draw_text(
            "游戏结束", (cx, cy - 120), FONT_SIZE_GAME_OVER_TITLE, Palette.DANGER, center=True
        )
        self.screen.draw_text(
            f"原因: {reason}", (cx, cy - 60), FONT_SIZE_GAME_OVER_REASON, Palette.TEXT_DIM, center=True
        )
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
