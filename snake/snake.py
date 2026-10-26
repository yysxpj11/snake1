# -*- coding: utf-8 -*-
"""蛇模块。

定义方向枚举、蛇身节点与 Snake 类：
- 移动（穿墙 / 撞墙两种模式）
- 生长与吃食物后的长度变化
- 自撞与边界碰撞判定
- 方向输入缓冲（防止一帧内连续两次转向导致自杀）
- 序列化 / 反序列化，便于存档与测试
"""

from __future__ import annotations

import random
from collections import deque
from enum import Enum
from typing import Deque, Dict, Iterator, List, Optional, Tuple

from .utils import (
    DIRECTION_VECTORS,
    OPPOSITE_DIRECTIONS,
    add_vectors,
    clamp_position,
    direction_to_vector,
    is_opposite,
    wrap_position,
)


class Direction(Enum):
    """四个移动方向的枚举封装。"""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"

    @property
    def vector(self) -> Tuple[int, int]:
        """返回该方向对应的单位向量。"""
        return DIRECTION_VECTORS[self.value]

    @property
    def opposite(self) -> "Direction":
        """返回相反方向。"""
        return Direction(OPPOSITE_DIRECTIONS[self.value])

    @classmethod
    def from_name(cls, name: str) -> Optional["Direction"]:
        """根据名字构造方向，无效名字返回 None。"""
        try:
            return cls(name)
        except ValueError:
            return None

    @classmethod
    def random(cls, rng: Optional[random.Random] = None) -> "Direction":
        """随机返回一个方向。"""
        rng = rng or random
        return rng.choice(list(cls))


class WallMode(Enum):
    """边界处理模式。

    WRAP: 穿墙，从另一侧出现。
    SOLID: 撞墙即死亡。
    """

    WRAP = "wrap"
    SOLID = "solid"


class SnakeDeath(Exception):
    """蛇死亡时抛出的异常，携带死亡原因。"""

    def __init__(self, reason: str) -> None:
        """初始化异常并保存死亡原因。"""
        super().__init__(reason)
        self.reason = reason


class Segment:
    """蛇身单个节点，记录网格坐标与生长标记。"""

    __slots__ = ("position", "is_new")

    def __init__(self, position: Tuple[int, int]) -> None:
        """初始化节点位置，is_new 用于出生动画。"""
        self.position = position
        self.is_new = True

    def clear_new_flag(self) -> None:
        """清除出生标记（动画播放完毕后调用）。"""
        self.is_new = False

    def __eq__(self, other: object) -> bool:
        """按坐标判等，方便集合运算。"""
        if isinstance(other, Segment):
            return self.position == other.position
        if isinstance(other, tuple):
            return self.position == other
        return NotImplemented

    def __hash__(self) -> int:
        """哈希与坐标一致。"""
        return hash(self.position)

    def __repr__(self) -> str:
        """调试用表示。"""
        return f"Segment({self.position})"


class Snake:
    """贪吃蛇实体。

    内部使用 deque 存储 Segment，队头（索引 0）为蛇头。
    移动采用“头进尾出”的 O(1) 方式，吃食物时不弹出尾部即实现生长。
    """

    def __init__(
        self,
        start: Tuple[int, int] = (10, 10),
        length: int = 3,
        direction: str = "right",
        wall_mode: WallMode = WallMode.SOLID,
    ) -> None:
        """初始化蛇：从 start 向反方向铺出 length 节身体。"""
        self.wall_mode = wall_mode
        self.direction = Direction.from_name(direction) or Direction.RIGHT
        self.pending_directions: Deque[Direction] = deque()
        self.growth_pending = 0
        self.alive = True
        self.death_reason: str = ""
        self.move_count = 0
        self.body: Deque[Segment] = deque()
        dx, dy = self.direction.vector
        for i in range(max(1, length)):
            seg_x = start[0] - dx * i
            seg_y = start[1] - dy * i
            self.body.append(Segment((seg_x, seg_y)))

    # -- 基础属性 -----------------------------------------------------------

    @property
    def head(self) -> Segment:
        """返回蛇头节点。"""
        return self.body[0]

    @property
    def head_position(self) -> Tuple[int, int]:
        """返回蛇头坐标。"""
        return self.body[0].position

    @property
    def length(self) -> int:
        """返回蛇身长度。"""
        return len(self.body)

    @property
    def tail(self) -> Segment:
        """返回蛇尾节点。"""
        return self.body[-1]

    def positions(self) -> List[Tuple[int, int]]:
        """返回全部节点坐标列表（头在前）。"""
        return [seg.position for seg in self.body]

    def occupied_set(self) -> set:
        """返回被蛇身占用的坐标集合，加速碰撞查询。"""
        return {seg.position for seg in self.body}

    def __iter__(self) -> Iterator[Segment]:
        """迭代蛇身节点。"""
        return iter(self.body)

    def __len__(self) -> int:
        """len(snake) 返回长度。"""
        return len(self.body)

    # -- 输入与转向 ---------------------------------------------------------

    def queue_direction(self, direction: Direction) -> bool:
        """把转向请求放入缓冲队列，成功入队返回 True。

        规则：不允许与当前实际方向（或缓冲中的最后一个方向）相反，
        也不允许重复同方向；队列最多缓存 2 个转向保证手感。
        """
        last = self.pending_directions[-1] if self.pending_directions else self.direction
        if direction == last or direction == last.opposite:
            return False
        if len(self.pending_directions) >= 2:
            return False
        self.pending_directions.append(direction)
        return True

    def _consume_direction(self) -> None:
        """从缓冲队列取出下一个实际生效的方向。"""
        if self.pending_directions:
            self.direction = self.pending_directions.popleft()

    # -- 移动 ---------------------------------------------------------------

    def next_head_position(self) -> Tuple[int, int]:
        """计算按当前方向前进一格后蛇头的坐标（不真正移动）。"""
        self._consume_direction()
        return add_vectors(self.head_position, self.direction.vector)

    def _resolve_bounds(self, pos: Tuple[int, int], columns: int, rows: int) -> Tuple[int, int]:
        """按边界模式处理越界坐标：环绕或保持越界（由调用方判死）。"""
        if self.wall_mode == WallMode.WRAP:
            return wrap_position(pos, columns, rows)
        return pos

    def will_hit_wall(self, columns: int, rows: int) -> bool:
        """判断下一步是否会撞墙（仅 SOLID 模式有意义）。"""
        nxt = self.next_head_position()
        x, y = nxt
        return x < 0 or y < 0 or x >= columns or y >= rows

    def move(self, columns: int, rows: int) -> Tuple[int, int]:
        """前进一格并返回新蛇头坐标；穿墙模式自动环绕。"""
        new_head = self.next_head_position()
        new_head = self._resolve_bounds(new_head, columns, rows)
        self.body.appendleft(Segment(new_head))
        if self.growth_pending > 0:
            self.growth_pending -= 1
        else:
            self.body.pop()
        self.move_count += 1
        return new_head

    def grow(self, amount: int = 1) -> None:
        """登记待生长的节数，在后续移动中逐步兑现。"""
        self.growth_pending += max(0, amount)

    # -- 碰撞判定 -----------------------------------------------------------

    def hits_self(self, head: Optional[Tuple[int, int]] = None) -> bool:
        """判断蛇是否撞到自己。

        默认检查移动后的头（当前 self.body[0]）与身体其余部分；
        传入 head 则检查指定头坐标。注意：即将弹出尾巴时尾巴不算障碍，
        这里采用保守判定（包含尾巴），由 Game 层在移动后再调用。
        """
        if head is None:
            head = self.head_position
        segments = [seg.position for seg in self.body]
        return head in segments[1:]

    def hits_cell(self, cell: Tuple[int, int]) -> bool:
        """判断指定格子是否被蛇身占用。"""
        return cell in self.occupied_set()

    def check_death(self, columns: int, rows: int) -> Optional[str]:
        """移动后调用：综合判定死亡原因，返回原因字符串或 None。"""
        head = self.head_position
        x, y = head
        if self.wall_mode == WallMode.SOLID and (
            x < 0 or y < 0 or x >= columns or y >= rows
        ):
            self._die("撞墙")
            return self.death_reason
        if self.hits_self():
            self._die("咬到自己")
            return self.death_reason
        return None

    def _die(self, reason: str) -> None:
        """标记蛇死亡并记录原因。"""
        self.alive = False
        self.death_reason = reason

    def revive(self, start: Tuple[int, int], length: int = 3) -> None:
        """复活：重置到初始状态（练习模式使用）。"""
        dx, dy = self.direction.vector
        self.body.clear()
        for i in range(max(1, length)):
            self.body.append(Segment((start[0] - dx * i, start[1] - dy * i)))
        self.growth_pending = 0
        self.pending_directions.clear()
        self.alive = True
        self.death_reason = ""

    # -- 序列化 -------------------------------------------------------------

    def to_dict(self) -> Dict[str, object]:
        """序列化为字典，用于存档。"""
        return {
            "direction": self.direction.value,
            "wall_mode": self.wall_mode.value,
            "positions": [list(seg.position) for seg in self.body],
            "growth_pending": self.growth_pending,
            "alive": self.alive,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "Snake":
        """从字典恢复蛇对象，数据异常时抛 ValueError。"""
        positions = data.get("positions")
        if not positions or not isinstance(positions, list):
            raise ValueError("无效的蛇身数据")
        snake = cls(
            start=tuple(positions[0]),  # type: ignore[arg-type]
            length=1,
            direction=str(data.get("direction", "right")),
            wall_mode=WallMode(str(data.get("wall_mode", "solid"))),
        )
        snake.body.clear()
        for pos in positions:
            snake.body.append(Segment((int(pos[0]), int(pos[1]))))
        snake.growth_pending = int(data.get("growth_pending", 0))  # type: ignore[arg-type]
        snake.alive = bool(data.get("alive", True))
        return snake


def create_snake_for_level(level: int, columns: int, rows: int) -> Snake:
    """按关卡生成初始蛇：越往后初始长度越长、越居中。"""
    length = 3 + min(level, 7)
    start = (columns // 2, rows // 2)
    return Snake(start=start, length=length, direction="right")


def random_safe_direction(
    snake: Snake, columns: int, rows: int, rng: Optional[random.Random] = None
) -> Direction:
    """为 AI 演示模式挑选一个不立即死亡的方向；全部危险时保持原方向。"""
    rng = rng or random
    candidates = [d for d in Direction if d != snake.direction.opposite]
    rng.shuffle(candidates)
    original = snake.direction
    for cand in candidates:
        snake.direction = cand
        if not snake.hits_self(snake.next_head_position()):
            snake.direction = original
            return cand
    snake.direction = original
    return original
