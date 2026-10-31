# -*- coding: utf-8 -*-
"""帧率控制模块。

主循环用 pygame.time.Clock 把帧率锁在上限之内（默认 60FPS），
避免不锁帧时 CPU 空转、物理步长忽大忽小导致的抖动。

除了限帧，这里还做两件容易被忽略但很关键的事：

1. **步长裁剪**：拖动窗口、切换全屏或系统卡顿会让某一帧的 dt 变得很大，
   若直接拿去累加，蛇会在一帧内连走好几格（俗称"瞬移"）。因此单帧
   dt 被裁剪到 MAX_DT（0.25s）以内。
2. **帧率统计**：保留最近若干帧的步长，算出平均 FPS，退出时写日志，
   也方便测试与性能排查。

clock 对象可注入（默认 pygame.time.Clock），因此本模块的限帧逻辑
可以在没有真实显示器/计时器的环境里做单元测试。
"""

from __future__ import annotations

import logging
from typing import List, Optional

import pygame

logger = logging.getLogger(__name__)

# 帧率上限：需求要求锁在 60FPS，任何更高的请求都会被压回这个值
MAX_FPS: int = 60
# 帧率下限：至少 1FPS，避免 tick(0) 变成"不限帧"导致 CPU 跑满
MIN_FPS: int = 1
# 单帧最大步长（秒）：低于 4FPS 的卡顿按 0.25s 推进，防止逻辑一次跳太多
MAX_DT: float = 0.25
# 平均帧率的采样窗口（帧）
SAMPLE_FRAMES: int = 120


class FrameRateController:
    """主循环的帧率控制器：限帧 + 步长裁剪 + 帧率统计。

    Attributes:
        limit: 当前生效的帧率上限（1-60）。
        frame_count: 已经过的总帧数。
        last_dt: 最近一帧的步长（秒）。
    """

    def __init__(self, limit: int = MAX_FPS, clock: Optional[object] = None) -> None:
        """初始化控制器。

        Args:
            limit: 期望的帧率上限，会被裁剪到 MIN_FPS-MAX_FPS。
            clock: 可注入的计时器（需提供 tick(limit) -> 毫秒），
                默认新建 pygame.time.Clock；测试时可传入假对象。
        """
        self._clock = clock if clock is not None else pygame.time.Clock()
        self.limit: int = self.clamp_limit(limit)
        self.frame_count: int = 0
        self.last_dt: float = 0.0
        self._samples: List[float] = []

    @staticmethod
    def clamp_limit(fps: int) -> int:
        """把帧率限制裁剪到 [MIN_FPS, MAX_FPS] 区间。"""
        try:
            value = int(fps)
        except (TypeError, ValueError):
            return MAX_FPS
        return max(MIN_FPS, min(MAX_FPS, value))

    def set_limit(self, fps: int) -> int:
        """调整帧率上限，返回真正生效的值（超过 60 会被压回 60）。"""
        self.limit = self.clamp_limit(fps)
        return self.limit

    def tick(self) -> float:
        """阻塞到下一帧，返回这一帧的步长（秒，已裁剪到 MAX_DT）。

        这是主循环每帧唯一需要调用的方法：内部先让 clock 限帧，
        再把毫秒换算成秒并裁剪，最后记录样本供 average_fps 使用。
        """
        elapsed_ms = self._clock.tick(self.limit)
        dt = max(0.0, min(MAX_DT, float(elapsed_ms) / 1000.0))
        self.last_dt = dt
        self.frame_count += 1
        self._samples.append(dt)
        if len(self._samples) > SAMPLE_FRAMES:
            # 只保留最近 SAMPLE_FRAMES 帧，窗口滑动而非无限累积
            del self._samples[0]
        return dt

    def average_fps(self) -> float:
        """最近 SAMPLE_FRAMES 帧的平均帧率；没有样本时返回 0.0。"""
        if not self._samples:
            return 0.0
        total = sum(self._samples)
        if total <= 0:
            return 0.0
        return len(self._samples) / total

    def reset(self) -> None:
        """清空统计（帧数、样本、最近步长），不影响帧率上限。"""
        self.frame_count = 0
        self.last_dt = 0.0
        self._samples.clear()
