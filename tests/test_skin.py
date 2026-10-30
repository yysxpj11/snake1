# -*- coding: utf-8 -*-
"""皮肤管理功能测试。

验证 SkinManager 的初始化、三套内置皮肤、循环切换与名称查找；
以及菜单"选择皮肤"项的左右键切换与实时预览状态。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.skin import (
    SKIN_CLASSIC,
    SKIN_FLAME,
    SKIN_NEON,
    Skin,
    SkinManager,
    build_builtin_skins,
)


class TestSkinManager:
    """验证 SkinManager 的皮肤切换逻辑。"""

    def test_builtin_skins_and_cycle_switch(self) -> None:
        """内置三套皮肤可循环切换，颜色配置完整且互不相同。"""
        manager = SkinManager()

        # 内置皮肤：经典绿 / 霓虹蓝 / 烈焰橙，默认选中第一套
        assert manager.names() == [SKIN_CLASSIC, SKIN_NEON, SKIN_FLAME]
        assert manager.current.name == SKIN_CLASSIC

        # 每套皮肤都定义了 蛇头/蛇身/蛇尾/食物/背景 配色
        for skin in manager.skins:
            head, body, tail = skin.snake_colors
            normal, golden, speed = skin.food_colors
            assert head and body and tail and normal and golden and speed
            assert skin.background and skin.grid_line

        # 三套皮肤的蛇头颜色互不相同（确实存在视觉差异）
        heads = {skin.snake_head for skin in manager.skins}
        assert len(heads) == 3

        # 右键循环切换：经典绿 -> 霓虹蓝 -> 烈焰橙 -> 经典绿
        assert manager.next().name == SKIN_NEON
        assert manager.next().name == SKIN_FLAME
        assert manager.next().name == SKIN_CLASSIC

        # 左键回退：经典绿 -> 烈焰橙
        assert manager.previous().name == SKIN_FLAME
        manager.next()  # 回到经典绿

        # cycle 的正向/负向大步长同样正确取模循环
        assert manager.cycle(4).name == SKIN_NEON
        assert manager.cycle(-4).name == SKIN_CLASSIC

        # 按名称切换与容错
        assert manager.set_current(SKIN_FLAME) is True
        assert manager.current.name == SKIN_FLAME
        assert manager.set_current("不存在的皮肤") is False
        assert manager.current.name == SKIN_FLAME

        # find 查找与非法皮肤校验
        assert manager.find(SKIN_NEON) is not None
        assert manager.find("无") is None
        with pytest.raises(ValueError):
            Skin(
                name="坏皮肤", snake_head=(300, 0, 0), snake_body=(0, 0, 0),
                snake_tail=(0, 0, 0), food_normal=(0, 0, 0), food_golden=(0, 0, 0),
                food_speed=(0, 0, 0), background=(0, 0, 0), grid_line=(0, 0, 0),
            )

        # 自定义皮肤列表也能正常管理
        custom = Skin(
            name="测试皮", snake_head=(1, 2, 3), snake_body=(4, 5, 6),
            snake_tail=(7, 8, 9), food_normal=(10, 11, 12), food_golden=(13, 14, 15),
            food_speed=(16, 17, 18), background=(19, 20, 21), grid_line=(22, 23, 24),
        )
        custom_manager = SkinManager(skins=[custom])
        assert custom_manager.names() == ["测试皮"]
        assert build_builtin_skins()[0].name == SKIN_CLASSIC


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
