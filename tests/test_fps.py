# -*- coding: utf-8 -*-
"""帧率控制测试。

用注入的假 clock 验证限帧逻辑，不依赖真实计时器与显示器：
- tick() 把毫秒换算成秒，并按 MAX_DT 裁剪；
- 每次 tick 都把帧率上限（60）交给底层 clock；
- 超限帧率被压回 60，非法帧率被压回下限；
- 平均 FPS 与 --fps 参数的裁剪规则。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.fps import MAX_DT, MAX_FPS, FrameRateController


class FakeClock:
    """假的 pygame.time.Clock：按预设毫秒数返回，并记录收到的 limit。"""

    def __init__(self, intervals_ms) -> None:
        """记录预设的每帧耗时序列。"""
        self._intervals = list(intervals_ms)
        self.limits = []

    def tick(self, limit: int) -> int:
        """返回下一帧耗时（毫秒），同时记录被要求的帧率上限。"""
        self.limits.append(limit)
        if not self._intervals:
            return 16
        return self._intervals.pop(0)


def test_frame_rate_control_logic() -> None:
    """限帧 60：dt 换算正确、卡顿被裁剪、上限不可突破、平均 FPS 可统计。"""
    clock = FakeClock([16, 33, 500, 0])
    controller = FrameRateController(limit=60, clock=clock)

    # 毫秒 -> 秒，正常帧与半帧
    assert controller.tick() == pytest.approx(0.016)
    assert controller.tick() == pytest.approx(0.033)
    # 500ms 的卡顿被裁剪到 MAX_DT，避免蛇一帧连走多格
    assert controller.tick() == pytest.approx(MAX_DT)
    assert MAX_DT == pytest.approx(0.25)
    # 0ms 不允许产生负步长
    assert controller.tick() == pytest.approx(0.0)
    # 每次都把 60 这个上限交给底层 clock 去限帧
    assert clock.limits == [60, 60, 60, 60]
    assert controller.frame_count == 4

    # 帧率上限：超过 60 压回 60，低于 1 压回 1
    assert controller.set_limit(240) == MAX_FPS
    assert controller.set_limit(0) == 1
    assert controller.set_limit(45) == 45  # 调低是允许的

    # 平均 FPS：60 帧匀速 16ms -> 62.5 FPS
    steady = FrameRateController(clock=FakeClock([16] * 60))
    for _ in range(60):
        steady.tick()
    assert steady.average_fps() == pytest.approx(1000 / 16, rel=1e-6)

    # reset 清空统计但保留帧率上限
    steady.reset()
    assert steady.frame_count == 0
    assert steady.average_fps() == pytest.approx(0.0)
    assert steady.limit == 60

    # 命令行 --fps 120 也会被 build_config 压到 60
    from snake.main import build_config, parse_args

    config = build_config(parse_args(["--fps", "120"]))
    assert config.fps == MAX_FPS
    # 调低则尊重传入值
    assert build_config(parse_args(["--fps", "30"])).fps == 30

    # 主循环用的控制器与配置对齐
    pygame = pytest.importorskip("pygame")
    pygame.init()
    from snake.main import Application

    app = Application(build_config(parse_args(["--width", "320", "--height", "240"])))
    assert app.frame_controller.limit == 60


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
