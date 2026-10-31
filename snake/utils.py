# -*- coding: utf-8 -*-
"""贪吃蛇游戏工具模块。

本模块提供整个游戏共用的基础能力：
- 常量与默认配置
- 配置数据类 Config
- 调色板 Palette
- 网格坐标与向量运算
- 高分记录的持久化存取
- 简易日志与计时器工具

所有其他模块都依赖本模块，但本模块不依赖任何游戏逻辑模块，
以保证依赖方向单一、便于单元测试。
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# 常量定义
# ---------------------------------------------------------------------------

# 默认窗口尺寸（像素）
DEFAULT_WINDOW_WIDTH: int = 800
DEFAULT_WINDOW_HEIGHT: int = 600

# 单个网格单元的边长（像素）
DEFAULT_CELL_SIZE: int = 20

# 网格列数与行数（根据窗口与单元尺寸推算）
GRID_COLUMNS: int = DEFAULT_WINDOW_WIDTH // DEFAULT_CELL_SIZE
GRID_ROWS: int = DEFAULT_WINDOW_HEIGHT // DEFAULT_CELL_SIZE

# 目标帧率
TARGET_FPS: int = 60

# 蛇每几帧移动一格（数值越大蛇越慢）
DEFAULT_MOVE_INTERVAL: float = 0.12  # 秒

# 分数规则
SCORE_PER_FOOD: int = 10
SCORE_PER_GOLDEN_FOOD: int = 50
SCORE_PER_SPEED_FOOD: int = 20

# 特殊食物存在时间（秒）
SPECIAL_FOOD_LIFETIME: float = 8.0

# 高分文件名
HIGHSCORE_FILENAME: str = "highscores.json"

# 方向向量：(dx, dy)，屏幕坐标 y 向下
DIRECTION_VECTORS: Dict[str, Tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}

# 方向之间的对立关系，用于禁止 180 度掉头
OPPOSITE_DIRECTIONS: Dict[str, str] = {
    "up": "down",
    "down": "up",
    "left": "right",
    "right": "left",
}


# ---------------------------------------------------------------------------
# 难度枚举与配置数据类
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
    FOOD_NORMAL = (230, 80, 80)
    FOOD_GOLDEN = (240, 200, 60)
    FOOD_SPEED = (80, 160, 240)
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
# 网格与向量工具
# ---------------------------------------------------------------------------


def wrap_position(pos: Tuple[int, int], columns: int, rows: int) -> Tuple[int, int]:
    """把网格坐标环绕到有效范围内（穿墙模式）。"""
    x, y = pos
    return (x % columns, y % rows)


def clamp_position(pos: Tuple[int, int], columns: int, rows: int) -> Tuple[int, int]:
    """把网格坐标钳制在有效范围内（撞墙模式）。"""
    x, y = pos
    return (max(0, min(columns - 1, x)), max(0, min(rows - 1, y)))


def manhattan_distance(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    """计算两个网格坐标之间的曼哈顿距离。"""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def add_vectors(a: Tuple[int, int], b: Tuple[int, int]) -> Tuple[int, int]:
    """两个整数向量相加。"""
    return (a[0] + b[0], a[1] + b[1])


def scale_vector(v: Tuple[int, int], factor: int) -> Tuple[int, int]:
    """向量按整数倍缩放。"""
    return (v[0] * factor, v[1] * factor)


def direction_to_vector(direction: str) -> Tuple[int, int]:
    """把方向名字符串转换为方向向量，未知方向默认向右。"""
    return DIRECTION_VECTORS.get(direction, (1, 0))


def vector_to_direction(vector: Tuple[int, int]) -> str:
    """把方向向量转换为方向名，未知向量返回空字符串。"""
    for name, vec in DIRECTION_VECTORS.items():
        if vec == vector:
            return name
    return ""


def is_opposite(dir_a: str, dir_b: str) -> bool:
    """判断两个方向是否相反（用于禁止原地掉头）。"""
    return OPPOSITE_DIRECTIONS.get(dir_a) == dir_b


def cell_to_pixel(cell: Tuple[int, int], cell_size: int) -> Tuple[int, int]:
    """把网格坐标转换为左上角像素坐标。"""
    return (cell[0] * cell_size, cell[1] * cell_size)


def pixel_to_cell(pixel: Tuple[int, int], cell_size: int) -> Tuple[int, int]:
    """把像素坐标转换为网格坐标。"""
    return (pixel[0] // cell_size, pixel[1] // cell_size)


# ---------------------------------------------------------------------------
# 随机与采样工具
# ---------------------------------------------------------------------------


def random_empty_cell(
    occupied: Sequence[Tuple[int, int]],
    columns: int,
    rows: int,
    rng: Optional[random.Random] = None,
) -> Optional[Tuple[int, int]]:
    """从不在 occupied 中的格子中随机取一个，若无空格返回 None。"""
    rng = rng or random
    occupied_set = set(occupied)
    empty_cells = [
        (x, y)
        for x in range(columns)
        for y in range(rows)
        if (x, y) not in occupied_set
    ]
    if not empty_cells:
        return None
    return rng.choice(empty_cells)


def random_choice_weighted(
    choices: Sequence[Tuple[str, float]],
    rng: Optional[random.Random] = None,
) -> str:
    """按权重随机选择一个键，choices 形如 [(key, weight), ...]。"""
    rng = rng or random
    total = sum(weight for _, weight in choices)
    if total <= 0:
        return choices[0][0] if choices else ""
    roll = rng.uniform(0, total)
    acc = 0.0
    for key, weight in choices:
        acc += weight
        if roll <= acc:
            return key
    return choices[-1][0]


def clamp(value: float, low: float, high: float) -> float:
    """把数值钳制在 [low, high] 区间内。"""
    return max(low, min(high, value))


def lerp(a: float, b: float, t: float) -> float:
    """线性插值，t 通常在 0~1 之间。"""
    return a + (b - a) * clamp(t, 0.0, 1.0)


def ease_out_cubic(t: float) -> float:
    """三次缓出函数，用于动画渐变。"""
    t = clamp(t, 0.0, 1.0)
    return 1 - (1 - t) ** 3


# ---------------------------------------------------------------------------
# 高分榜持久化
# ---------------------------------------------------------------------------


class HighScoreStore:
    """负责高分记录的读取、写入与排名计算。"""

    def __init__(self, directory: str = ".") -> None:
        """初始化存储路径并加载已有记录。"""
        self._directory = directory
        self._path = os.path.join(directory, HIGHSCORE_FILENAME)
        self._records: List[Dict[str, object]] = []
        self.load()

    @property
    def records(self) -> List[Dict[str, object]]:
        """只读访问高分记录列表。"""
        return list(self._records)

    def load(self) -> None:
        """从磁盘加载高分记录，文件不存在或损坏则使用空列表。"""
        if not os.path.exists(self._path):
            self._records = []
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                self._records = [rec for rec in data if isinstance(rec, dict)]
            else:
                self._records = []
        except (OSError, json.JSONDecodeError):
            self._records = []

    def save(self) -> None:
        """把当前记录写回磁盘，写入失败仅记录日志不抛异常。"""
        try:
            os.makedirs(self._directory, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as fh:
                json.dump(self._records, fh, ensure_ascii=False, indent=2)
        except OSError as exc:
            logging.getLogger(__name__).warning("保存高分记录失败: %s", exc)

    def add_score(self, score: int, name: str = "Player", date: Optional[str] = None) -> int:
        """新增一条成绩并返回其排名（从 1 开始）。"""
        if date is None:
            date = time.strftime("%Y-%m-%d %H:%M")
        self._records.append({"name": name, "score": score, "date": date})
        self._records.sort(key=lambda rec: int(rec.get("score", 0)), reverse=True)
        self._records = self._records[:10]
        rank = 1
        for rec in self._records:
            if rec is self._records[-1] or int(rec.get("score", 0)) >= score:
                rank = self._records.index(rec) + 1
                break
        self.save()
        return rank

    def best_score(self) -> int:
        """返回历史最高分，无记录时返回 0。"""
        if not self._records:
            return 0
        return int(self._records[0].get("score", 0))

    def is_new_record(self, score: int) -> bool:
        """判断给定分数是否刷新了历史纪录（需大于 0）。"""
        return score > 0 and score > self.best_score()

    def clear(self) -> None:
        """清空全部高分记录并立即保存。"""
        self._records = []
        self.save()


# ---------------------------------------------------------------------------
# 日志与计时器
# ---------------------------------------------------------------------------


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """初始化游戏日志（控制台 + game.log 双输出）并返回游戏专用 logger。

    具体配置交给 LogManager：包级 logger "snake" 会接住 snake.* 各模块的日志，
    这里只做兼容转发，并保证整个进程复用同一个实例（重复调用不会重复挂 handler）。
    """
    from .logmanager import LogManager

    return LogManager.get_default(console_level=level).logger


class Timer:
    """简易倒计时器，用于特殊食物存在时间、加速效果等。"""

    def __init__(self, duration: float) -> None:
        """初始化计时器并立即启动。"""
        self.duration = duration
        self.elapsed = 0.0
        self.running = True

    def tick(self, dt: float) -> None:
        """推进计时器，dt 为自上帧以来的秒数。"""
        if not self.running:
            return
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self.elapsed = self.duration
            self.running = False

    @property
    def finished(self) -> bool:
        """计时是否结束。"""
        return not self.running and self.elapsed >= self.duration

    @property
    def remaining(self) -> float:
        """剩余时间（秒）。"""
        return max(0.0, self.duration - self.elapsed)

    def ratio(self) -> float:
        """返回已过去时间的比例（0~1），便于绘制进度条。"""
        if self.duration <= 0:
            return 1.0
        return clamp(self.elapsed / self.duration, 0.0, 1.0)

    def reset(self, duration: Optional[float] = None) -> None:
        """重置计时器，可同时调整总时长。"""
        if duration is not None:
            self.duration = duration
        self.elapsed = 0.0
        self.running = True

    def stop(self) -> None:
        """手动停止计时器。"""
        self.running = False


class FrameClock:
    """帧率控制器封装，记录帧间隔供逻辑层使用。"""

    def __init__(self, fps: int) -> None:
        """按目标帧率初始化（实际 tick 依赖 pygame.time.Clock）。"""
        self.target_fps = fps
        self.last_tick = time.perf_counter()
        self.dt = 0.0

    def tick_with(self, clock: "object" = None) -> float:
        """与 pygame Clock 联动推进一帧并返回帧间隔秒数。"""
        if clock is not None:
            self.dt = clock.tick(self.target_fps) / 1000.0
        else:
            now = time.perf_counter()
            self.dt = now - self.last_tick
            self.last_tick = now
        return self.dt


def format_time(seconds: float) -> str:
    """把秒数格式化为 mm:ss 字符串。"""
    total = int(max(0, seconds))
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}:{secs:02d}"


def format_score(score: int, width: int = 6) -> str:
    """把分数格式化为固定位宽字符串，便于对齐显示。"""
    return str(max(0, score)).zfill(width)
