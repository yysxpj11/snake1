# -*- coding: utf-8 -*-
"""粒子与特效模块。

提供轻量级视觉反馈系统：
- Particle: 单个粒子（位置、速度、寿命、颜色）
- ParticleSystem: 粒子池管理（发射、更新、绘制）
- FloatingText: 漂浮文字（如 "+10"、"连击 x3!"）
- EffectManager: 统一管理粒子与漂浮文字

特效模块只依赖 utils 与 food 类型，保持与逻辑层解耦：
Game 层调用 EffectManager 的接口，渲染由 ui 层透传完成。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .config import Palette
from .utils import clamp, ease_out_cubic, lerp

Vector = Tuple[float, float]


# ---------------------------------------------------------------------------
# 粒子
# ---------------------------------------------------------------------------


@dataclass
class Particle:
    """单个粒子实体。

    Attributes:
        x, y: 像素坐标。
        vx, vy: 速度分量（像素/秒）。
        life: 总寿命（秒）。
        age: 已存活时间（秒）。
        color: RGB 颜色。
        size: 初始半径（像素）。
        gravity: 每秒垂直加速度（正值向下）。
        fade: 是否随寿命淡出。
    """

    x: float
    y: float
    vx: float
    vy: float
    life: float
    color: Tuple[int, int, int]
    size: float = 3.0
    gravity: float = 0.0
    fade: bool = True
    age: float = field(default=0.0, init=False)

    def update(self, dt: float) -> None:
        """推进粒子运动与寿命。"""
        self.age += dt
        self.vy += self.gravity * dt
        self.x += self.vx * dt
        self.y += self.vy * dt

    @property
    def dead(self) -> bool:
        """粒子是否已消亡。"""
        return self.age >= self.life

    def alpha_ratio(self) -> float:
        """返回剩余寿命比例（0~1），用于淡出。"""
        if self.life <= 0:
            return 0.0
        return clamp(1.0 - self.age / self.life, 0.0, 1.0)

    def current_size(self) -> float:
        """返回当前半径：随寿命线性收缩。"""
        return max(0.5, self.size * self.alpha_ratio())

    def scale_velocity(self, factor: float) -> None:
        """按比例缩放速度（用于扩散强弱调节）。"""
        self.vx *= factor
        self.vy *= factor


class ParticleSystem:
    """粒子池：批量发射、更新与清理。"""

    MAX_PARTICLES = 400  # 粒子上限，防止性能劣化

    def __init__(self, seed: Optional[int] = None) -> None:
        """初始化空粒子池与随机源。"""
        self.particles: List[Particle] = []
        self.rng = random.Random(seed)
        self.total_emitted = 0

    def emit_burst(
        self,
        center: Tuple[float, float],
        color: Tuple[int, int, int],
        count: int = 14,
        speed: float = 90.0,
        life: float = 0.6,
        gravity: float = 60.0,
        size: float = 3.0,
    ) -> None:
        """在指定像素坐标发射一圈爆裂粒子（吃食物时调用）。"""
        count = min(count, self.MAX_PARTICLES - len(self.particles))
        for _ in range(max(0, count)):
            angle = self.rng.uniform(0, math.tau)
            spd = speed * self.rng.uniform(0.5, 1.3)
            particle = Particle(
                x=center[0],
                y=center[1],
                vx=math.cos(angle) * spd,
                vy=math.sin(angle) * spd,
                life=life * self.rng.uniform(0.7, 1.3),
                color=color,
                size=size * self.rng.uniform(0.7, 1.4),
                gravity=gravity,
            )
            self.particles.append(particle)
            self.total_emitted += 1

    def emit_trail(
        self,
        position: Tuple[float, float],
        color: Tuple[int, int, int],
        speed: float = 20.0,
    ) -> None:
        """发射单个尾迹粒子（蛇头移动时低频调用）。"""
        if len(self.particles) >= self.MAX_PARTICLES:
            return
        jitter = self.rng.uniform(-speed, speed)
        self.particles.append(
            Particle(
                x=position[0],
                y=position[1],
                vx=jitter,
                vy=jitter,
                life=0.35,
                color=color,
                size=2.0,
                gravity=0.0,
            )
        )
        self.total_emitted += 1

    def update(self, dt: float) -> int:
        """推进所有粒子并清理消亡者，返回本帧消亡数量。"""
        alive: List[Particle] = []
        dead_count = 0
        for particle in self.particles:
            particle.update(dt)
            if particle.dead:
                dead_count += 1
            else:
                alive.append(particle)
        self.particles = alive
        return dead_count

    def clear(self) -> None:
        """清空全部粒子。"""
        self.particles.clear()

    @property
    def count(self) -> int:
        """当前存活粒子数量。"""
        return len(self.particles)

    def average_age_ratio(self) -> float:
        """所有粒子剩余寿命比例的均值（调试用）。"""
        if not self.particles:
            return 0.0
        return sum(p.alpha_ratio() for p in self.particles) / len(self.particles)


# ---------------------------------------------------------------------------
# 漂浮文字
# ---------------------------------------------------------------------------


class FloatingText:
    """向上漂移并淡出的文字特效。"""

    def __init__(
        self,
        text: str,
        position: Tuple[float, float],
        color: Tuple[int, int, int] = Palette.TEXT_PRIMARY,
        duration: float = 1.0,
        rise_speed: float = 40.0,
        font_size: int = 18,
    ) -> None:
        """初始化文本内容、起点与动画参数。"""
        self.text = text
        self.start_x, self.start_y = position
        self.color = color
        self.duration = duration
        self.rise_speed = rise_speed
        self.font_size = font_size
        self.age = 0.0

    def update(self, dt: float) -> None:
        """推进漂浮动画。"""
        self.age += dt

    @property
    def dead(self) -> bool:
        """动画是否结束。"""
        return self.age >= self.duration

    def progress(self) -> float:
        """返回动画进度（0~1）。"""
        if self.duration <= 0:
            return 1.0
        return clamp(self.age / self.duration, 0.0, 1.0)

    def current_position(self) -> Tuple[float, float]:
        """返回当前渲染坐标（带缓出上升曲线）。"""
        t = ease_out_cubic(self.progress())
        return (self.start_x, self.start_y - self.rise_speed * t)

    def alpha(self) -> int:
        """返回当前透明度（0~255），后半段淡出。"""
        p = self.progress()
        if p < 0.5:
            return 255
        return int(255 * clamp(1.0 - (p - 0.5) / 0.5, 0.0, 1.0))


# ---------------------------------------------------------------------------
# 特效总管
# ---------------------------------------------------------------------------


class EffectManager:
    """统一管理粒子系统与漂浮文字，供 Game 层调用。"""

    # 事件 -> 颜色映射
    EVENT_COLORS: Dict[str, Tuple[int, int, int]] = {
        "normal": Palette.FOOD_NORMAL,
        "golden": Palette.FOOD_GOLDEN,
        "speed": Palette.FOOD_SPEED,
        "death": Palette.DANGER,
        "levelup": Palette.SUCCESS,
    }

    def __init__(self, seed: Optional[int] = None) -> None:
        """初始化粒子系统与漂浮文字列表。"""
        self.particles = ParticleSystem(seed=seed)
        self.texts: List[FloatingText] = []
        self.screen_shake_time = 0.0
        self.screen_shake_duration = 0.0

    def on_eat(
        self,
        pixel_center: Tuple[float, float],
        food_kind: str = "normal",
        bonus_text: str = "",
    ) -> None:
        """吃食物特效：爆裂粒子 + 得分漂浮文字。"""
        color = self.EVENT_COLORS.get(food_kind, Palette.FOOD_NORMAL)
        count = 22 if food_kind == "golden" else 12
        self.particles.emit_burst(pixel_center, color, count=count)
        if bonus_text:
            self.texts.append(
                FloatingText(bonus_text, pixel_center, color, duration=1.0)
            )

    def on_death(self, pixel_center: Tuple[float, float]) -> None:
        """死亡特效：红色大爆裂 + 屏幕震动。"""
        self.particles.emit_burst(
            pixel_center, Palette.DANGER, count=40, speed=140.0, life=0.9
        )
        self.shake(0.35)

    def on_level_up(self, pixel_center: Tuple[float, float], text: str) -> None:
        """升级特效：绿色粒子环 + 提示文字。"""
        self.particles.emit_burst(
            pixel_center, Palette.SUCCESS, count=18, speed=60.0, gravity=0.0
        )
        self.texts.append(FloatingText(text, pixel_center, Palette.SUCCESS, duration=1.4))

    def shake(self, duration: float) -> None:
        """触发一次屏幕震动。"""
        self.screen_shake_time = duration
        self.screen_shake_duration = duration

    def update(self, dt: float) -> None:
        """推进所有特效。"""
        self.particles.update(dt)
        for text in self.texts:
            text.update(dt)
        self.texts = [t for t in self.texts if not t.dead]
        if self.screen_shake_time > 0:
            self.screen_shake_time = max(0.0, self.screen_shake_time - dt)

    def shake_offset(self, rng: Optional[random.Random] = None) -> Tuple[int, int]:
        """返回当前帧的屏幕震动偏移量（震动结束后为 (0, 0)）。"""
        if self.screen_shake_time <= 0 or self.screen_shake_duration <= 0:
            return (0, 0)
        rng = rng or random
        intensity = self.screen_shake_time / self.screen_shake_duration
        magnitude = 6 * intensity
        return (
            int(rng.uniform(-magnitude, magnitude)),
            int(rng.uniform(-magnitude, magnitude)),
        )

    @property
    def shaking(self) -> bool:
        """当前是否处于震动中。"""
        return self.screen_shake_time > 0

    def clear(self) -> None:
        """清空全部特效（新一局时调用）。"""
        self.particles.clear()
        self.texts.clear()
        self.screen_shake_time = 0.0
        self.screen_shake_duration = 0.0

    def stats(self) -> Dict[str, float]:
        """返回特效系统统计信息（粒子数、文字数）。"""
        return {
            "particles": float(self.particles.count),
            "texts": float(len(self.texts)),
            "emitted_total": float(self.particles.total_emitted),
        }


def lerp_color(
    a: Tuple[int, int, int], b: Tuple[int, int, int], t: float
) -> Tuple[int, int, int]:
    """在两种颜色之间线性插值，t 为 0~1。"""
    t = clamp(t, 0.0, 1.0)
    return (
        int(lerp(a[0], b[0], t)),
        int(lerp(a[1], b[1], t)),
        int(lerp(a[2], b[2], t)),
    )
