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

    def test_menu_skin_switch_with_preview_state(self) -> None:
        """菜单"选择皮肤"项：左右键循环切换、标签实时刷新、回调按序触发。"""
        from snake.ui import Menu

        names = [SKIN_CLASSIC, SKIN_NEON, SKIN_FLAME]
        changes: list = []
        menu = Menu(skin=SKIN_CLASSIC, skin_names=names, on_skin_change=changes.append)

        # 默认菜单含皮肤项，位于难度项之后
        assert menu.skin_index == 2
        assert menu.items[2][0] == f"选择皮肤: {SKIN_CLASSIC}"

        # 未选中皮肤项时，左右键不切换皮肤
        menu.handle_key("right")
        assert menu.skin == SKIN_CLASSIC
        assert changes == []

        # 选中皮肤项后，右键：经典绿 -> 霓虹蓝（标签实时刷新）
        menu.handle_key("down")
        menu.handle_key("down")
        assert menu.selected_action == "skin"
        menu.handle_key("right")
        assert menu.skin == SKIN_NEON
        assert menu.items[2][0] == f"选择皮肤: {SKIN_NEON}"

        # 继续右键循环：霓虹蓝 -> 烈焰橙 -> 经典绿（首尾循环）
        menu.handle_key("right")
        assert menu.skin == SKIN_FLAME
        menu.handle_key("right")
        assert menu.skin == SKIN_CLASSIC

        # 左键回退：经典绿 -> 烈焰橙
        menu.handle_key("left")
        assert menu.skin == SKIN_FLAME

        # 回调按切换顺序记录（不含未选中时的无效按键）
        assert changes == [SKIN_NEON, SKIN_FLAME, SKIN_CLASSIC, SKIN_FLAME]

        # 确认皮肤项同样切到下一套
        menu.handle_key("confirm")
        assert menu.skin == SKIN_CLASSIC

        # SkinManager 与菜单状态一致：set_current 后标签含义不变
        manager = SkinManager()
        manager.set_current(menu.skin)
        assert manager.current.name == menu.skin

    def test_skin_switch_by_s_key_in_game(self) -> None:
        """游戏内按 S 键循环切换皮肤，且 S 不再触发"向下移动"。"""
        import pygame

        pygame.init()  # 初始化字体等子系统（Application 会创建窗口与 FontBank）
        from snake.main import Application, build_config, parse_args
        from snake.snake import Direction

        app = Application(build_config(parse_args(["--width", "400", "--height", "400"])))
        app.menu_logic.handle_key("confirm")  # 进入游戏
        assert app.game.state.value == "playing"

        initial_skin = app.skin_manager.current.name
        initial_direction = app.game.snake.direction
        initial_head = app.game.snake.head_position

        # 模拟按下 S 键：皮肤切换到下一套，蛇的方向与位置不受影响
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_s))
        app.process_events()
        assert app.skin_manager.current.name != initial_skin
        assert app.menu_logic.skin == app.skin_manager.current.name  # 菜单标签同步
        assert app.game.snake.direction == initial_direction
        assert app.game.snake.head_position == initial_head

        # 连按三次回到初始皮肤（三套皮肤循环）
        for _ in range(2):
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_s))
            app.process_events()
        assert app.skin_manager.current.name == initial_skin

        # S 键不再映射为"向下"：方向输入应被忽略（未注册在方向表中）
        assert pygame.K_s not in __import__("snake.main", fromlist=["KEY_DIRECTION_MAP"]).KEY_DIRECTION_MAP

        # 方向键移动仍正常：按 W 依然向上（进入待应用方向队列）
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_w))
        app.process_events()
        assert Direction.UP in app.game.snake.pending_directions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
