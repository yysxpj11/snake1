# -*- coding: utf-8 -*-
"""全局常量与配置模块。

整个游戏的"数字"都集中在这里，其他模块只引用名字、不写魔法数字：

- 窗口 / 网格 / 帧率等默认参数
- 得分与食物规则
- 难度枚举 Difficulty 及其参数表
- 配置数据类 Config
- 调色板 Palette（全部 RGB 颜色）
- 界面布局常量（菜单 / 设置面板 / HUD / 遮罩等）

本模块只依赖标准库，不依赖任何游戏逻辑模块，
保证依赖方向单一：所有模块 -> config。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# 窗口与网格
# ---------------------------------------------------------------------------

# 默认窗口尺寸（像素）
DEFAULT_WINDOW_WIDTH: int = 800
DEFAULT_WINDOW_HEIGHT: int = 600

# 单个网格单元的边长（像素）
DEFAULT_CELL_SIZE: int = 20

# 网格列数与行数（根据窗口与单元尺寸推算）
GRID_COLUMNS: int = DEFAULT_WINDOW_WIDTH // DEFAULT_CELL_SIZE
GRID_ROWS: int = DEFAULT_WINDOW_HEIGHT // DEFAULT_CELL_SIZE

# 绘制格子时向内收缩的像素数，形成格子之间的缝隙感
CELL_RECT_INSET: int = 1

# ---------------------------------------------------------------------------
# 帧率与速度
# ---------------------------------------------------------------------------

# 目标帧率
TARGET_FPS: int = 60

# 蛇基础移动间隔（秒/格，数值越大蛇越慢；难度会覆盖此值）
DEFAULT_MOVE_INTERVAL: float = 0.12

# 移动间隔下限：关卡加成再快也不能低于它
MIN_MOVE_INTERVAL: float = 0.05

# 每提升一级，移动间隔缩短的秒数
LEVEL_SPEEDUP_STEP: float = 0.005

# 蛇的初始长度与关卡长度加成上限
SNAKE_START_LENGTH: int = 3
MAX_LEVEL_LENGTH_BONUS: int = 5

# ---------------------------------------------------------------------------
# 得分与食物
# ---------------------------------------------------------------------------

# 分数规则
SCORE_PER_FOOD: int = 10
SCORE_PER_GOLDEN_FOOD: int = 50
SCORE_PER_SPEED_FOOD: int = 20

# 特殊食物存在时间（秒）
SPECIAL_FOOD_LIFETIME: float = 8.0

# 旧版高分文件名（HighScoreStore 使用；新版见 highscore.HIGHSCORE_FILENAME）
HIGHSCORE_FILENAME: str = "highscores.json"

# 连击判定窗口（秒）与连击加成比例
COMBO_WINDOW: float = 3.0
COMBO_BONUS_RATIO: float = 0.5

# 连击加成的最大倍数（防止无限叠连击）
COMBO_MAX_COUNT: int = 5

# 加速期间移动间隔的缩短比例（0.6 = 间隔变为 60%）
SPEED_BOOST_DIVISOR: float = 0.6

# ---------------------------------------------------------------------------
# 难度参数表
# ---------------------------------------------------------------------------

# 各难度档位的参数表（集中存放，便于统一调整；
# 注意不能写在 Enum 类体内，否则会被当作枚举成员）
DIFFICULTY_MOVE_INTERVALS: Dict[str, float] = {
    "easy": 0.16,    # 慢速：每格 0.16 秒
    "normal": 0.12,  # 中速
    "hard": 0.085,   # 快速
}

DIFFICULTY_SCORE_MULTIPLIERS: Dict[str, float] = {
    "easy": 0.8,
    "normal": 1.0,
    "hard": 1.5,
}

DIFFICULTY_LABELS: Dict[str, str] = {
    "easy": "简单",
    "normal": "普通",
    "hard": "困难",
}


class Difficulty(Enum):
    """难度档位枚举。

    每个档位自带速度与得分参数，游戏逻辑只读枚举属性，
    不再硬编码任何数值：
    - EASY:   慢速（0.16 秒/格），得分倍率 0.8
    - NORMAL: 中速（0.12 秒/格），得分倍率 1.0
    - HARD:   快速（0.085 秒/格），得分倍率 1.5
    """

    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"

    @property
    def label(self) -> str:
        """返回中文显示名（简单 / 普通 / 困难）。"""
        return DIFFICULTY_LABELS[self.value]

    @property
    def move_interval(self) -> float:
        """蛇每移动一格所需的秒数，数值越小蛇越快。"""
        return DIFFICULTY_MOVE_INTERVALS[self.value]

    @property
    def score_multiplier(self) -> float:
        """该难度下的得分倍率。"""
        return DIFFICULTY_SCORE_MULTIPLIERS[self.value]

    @property
    def speed_factor(self) -> float:
        """相对普通档的速度倍率（1.0 为基准，小于 1 表示更快）。"""
        return self.move_interval / DIFFICULTY_MOVE_INTERVALS[Difficulty.NORMAL.value]

    def next(self) -> "Difficulty":
        """返回下一档难度（困难之后回到简单）。"""
        order = Difficulty.levels()
        return order[(order.index(self) + 1) % len(order)]

    def previous(self) -> "Difficulty":
        """返回上一档难度（简单之前回到困难）。"""
        order = Difficulty.levels()
        return order[(order.index(self) - 1) % len(order)]

    @classmethod
    def levels(cls) -> List["Difficulty"]:
        """按由慢到快返回全部难度档位。"""
        return [cls.EASY, cls.NORMAL, cls.HARD]

    @classmethod
    def from_name(cls, name: str) -> "Difficulty":
        """根据名称（不区分大小写）构造难度，无效名称回退到普通。"""
        try:
            return cls(str(name).strip().lower())
        except (ValueError, AttributeError):
            return cls.NORMAL


# ---------------------------------------------------------------------------
# 配置数据类
# ---------------------------------------------------------------------------


@dataclass
class Config:
    """游戏全局配置。

    Attributes:
        window_width: 窗口宽度（像素）。
        window_height: 窗口高度（像素）。
        cell_size: 单个网格单元的边长（像素）。
        fps: 目标帧率。
        move_interval: 基础移动间隔秒数（难度会覆盖此值）。
        score_per_food: 普通食物得分。
        sound_enabled: 是否开启音效。
        sound_volume: 音效主音量（0.0 - 1.0），供设置界面预留。
        fullscreen: 是否全屏运行。
        difficulty: 难度档位枚举（easy / normal / hard）。
        max_score_history: 高分榜最多保存条数。
    """

    window_width: int = DEFAULT_WINDOW_WIDTH
    window_height: int = DEFAULT_WINDOW_HEIGHT
    cell_size: int = DEFAULT_CELL_SIZE
    fps: int = TARGET_FPS
    move_interval: float = DEFAULT_MOVE_INTERVAL
    score_per_food: int = SCORE_PER_FOOD
    sound_enabled: bool = True
    sound_volume: float = 0.7
    fullscreen: bool = False
    difficulty: Difficulty = Difficulty.NORMAL
    max_score_history: int = 10

    @property
    def grid_columns(self) -> int:
        """返回网格列数。"""
        return self.window_width // self.cell_size

    @property
    def grid_rows(self) -> int:
        """返回网格行数。"""
        return self.window_height // self.cell_size

    def difficulty_multiplier(self) -> float:
        """返回当前难度对应的得分倍率。"""
        return self.difficulty.score_multiplier

    def speed_factor(self) -> float:
        """返回当前难度相对普通档的速度倍率（小于 1 表示更快）。"""
        return self.difficulty.speed_factor

    @property
    def move_interval_for_difficulty(self) -> float:
        """返回当前难度对应的移动间隔（秒/格），供游戏逻辑直接读取。"""
        return self.difficulty.move_interval

    def clamp_to_window(self) -> None:
        """保证窗口尺寸是单元尺寸的整数倍，避免网格溢出。"""
        self.window_width = max(
            self.cell_size * 10,
            (self.window_width // self.cell_size) * self.cell_size,
        )
        self.window_height = max(
            self.cell_size * 10,
            (self.window_height // self.cell_size) * self.cell_size,
        )


# ---------------------------------------------------------------------------
# 调色板
# ---------------------------------------------------------------------------


class Palette:
    """游戏配色方案，集中管理所有 RGB 颜色。"""

    BACKGROUND = (18, 18, 24)
    GRID_LINE = (30, 30, 40)
    SNAKE_HEAD = (80, 220, 120)
    SNAKE_BODY = (60, 180, 100)
    SNAKE_TAIL = (40, 140, 80)
    SNAKE_EYE = (20, 20, 20)
    FOOD_NORMAL = (230, 80, 80)
    FOOD_GOLDEN = (240, 200, 60)
    FOOD_SPEED = (80, 160, 240)
    SPEED_HALO = (80, 160, 240)
    TEXT_PRIMARY = (235, 235, 235)
    TEXT_DIM = (150, 150, 160)
    PANEL_BG = (28, 28, 38)
    PANEL_BORDER = (70, 70, 90)
    BUTTON_BG = (60, 60, 80)
    BUTTON_HOVER = (90, 90, 120)
    OVERLAY = (0, 0, 0, 160)
    DANGER = (220, 60, 60)
    SUCCESS = (90, 200, 90)

    @classmethod
    def all_colors(cls) -> Dict[str, Tuple[int, int, int]]:
        """返回类属性中定义的全部颜色字典，便于调试与主题切换。"""
        result: Dict[str, Tuple[int, int, int]] = {}
        for name in dir(cls):
            if name.startswith("_"):
                continue
            value = getattr(cls, name)
            if isinstance(value, tuple) and len(value) in (3, 4):
                result[name] = value
        return result

    @classmethod
    def lighten(cls, color: Tuple[int, int, int], amount: float = 0.2) -> Tuple[int, int, int]:
        """把颜色变亮 amount（0~1）。"""
        r, g, b = color[:3]
        r = min(255, int(r + (255 - r) * amount))
        g = min(255, int(g + (255 - g) * amount))
        b = min(255, int(b + (255 - b) * amount))
        return (r, g, b)

    @classmethod
    def darken(cls, color: Tuple[int, int, int], amount: float = 0.2) -> Tuple[int, int, int]:
        """把颜色变暗 amount（0~1）。"""
        r, g, b = color[:3]
        r = max(0, int(r * (1 - amount)))
        g = max(0, int(g * (1 - amount)))
        b = max(0, int(b * (1 - amount)))
        return (r, g, b)


# ---------------------------------------------------------------------------
# 界面布局常量（菜单 / 设置面板 / HUD / 遮罩）
# ---------------------------------------------------------------------------

# 菜单项在界面中的纵向排布
MENU_ITEM_WIDTH: int = 260
MENU_ITEM_HEIGHT: int = 52
MENU_ITEM_GAP: int = 18
MENU_START_Y_RATIO: float = 0.52       # 第一项中心所在的窗口高度比例
MENU_TITLE_Y_RATIO: float = 0.26       # 主菜单标题中心高度比例
MENU_SUBTITLE_OFFSET: int = 58         # 副标题（最高分）相对标题的纵向偏移
MENU_NOTICE_OFFSET: int = 92           # 临时提示相对标题的纵向偏移

# 设置面板各行
SETTINGS_ROW_WIDTH: int = 420
SETTINGS_ROW_HEIGHT: int = 56
SETTINGS_ROW_GAP: int = 16
SETTINGS_START_Y_RATIO: float = 0.42   # 第一行中心所在的窗口高度比例
SETTINGS_TITLE_Y_RATIO: float = 0.2    # 面板标题中心高度比例

# 音量滑条（绘制与鼠标命中共用同一套几何）
VOLUME_TRACK_WIDTH: int = 200
VOLUME_TRACK_HEIGHT: int = 10
VOLUME_TRACK_OFFSET_X: int = 20        # 轨道相对行中心的左偏移
VOLUME_HIT_INFLATE_X: int = 20         # 命中区横向外扩像素
VOLUME_HIT_INFLATE_Y: int = 28         # 命中区纵向外扩像素
VOLUME_KNOB_RADIUS: int = 9

# 档位条（难度 / 皮肤 chips）
CHIP_HEIGHT: int = 28
CHIP_GAP: int = 8
CHIP_EDGE_OFFSET: int = 10             # chips 距窗口右缘的最小间距
DIFFICULTY_CHIP_WIDTH: int = 56
SKIN_CHIP_WIDTH: int = 76
SKIN_CHIP_DOT_SIZE: int = 10           # 皮肤主色小方块边长

# 行内标签
ROW_LABEL_INSET: int = 18              # 行内左侧标签距行左缘的像素
SELECTED_PREFIX: str = "▶ "

# 字号
FONT_SIZE_SMALL: int = 13
FONT_SIZE_HINT: int = 14
FONT_SIZE_NOTICE: int = 16
FONT_SIZE_ITEM: int = 24
FONT_SIZE_SUBTITLE: int = 24
FONT_SIZE_GAME_OVER_REASON: int = 24
FONT_SIZE_PANEL_TITLE: int = 48
FONT_SIZE_MENU_TITLE: int = 64
FONT_SIZE_GAME_OVER_TITLE: int = 56

# HUD 顶栏高度（像素）
HUD_HEIGHT: int = 40
HUD_TEXT_OFFSET_X: int = 12
HUD_TEXT_OFFSET_Y: int = 8

# 遮罩透明度：暂停 / 结束用默认值，游戏内设置面板用更深的值
DIM_OVERLAY_ALPHA: int = 160
SETTINGS_DIM_OVERLAY_ALPHA: int = 190

# 新生蛇节的提亮比例（比相邻身体更亮，指示刚长出来的一节）
NEW_SEGMENT_BRIGHTEN: float = 0.35

# 特殊食物快过期时闪烁的判定阈值与闪烁频率倍率
FOOD_BLINK_RATIO: float = 0.35
FOOD_BLINK_STEPS: int = 20

# 底部提示文字距窗口下缘的像素
FOOTER_BOTTOM_OFFSET: int = 36

# 菜单底部临时提示的显示时长（秒）
NOTICE_DURATION: float = 3.0

# 长按 C 键清除最高分所需的按住时长（秒）
CLEAR_HOLD_SECONDS: float = 1.0
