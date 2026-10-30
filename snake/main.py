# -*- coding: utf-8 -*-
"""程序入口模块。

职责：
1. 解析命令行参数（窗口尺寸、难度、音效、seed 等）
2. 初始化 pygame 与各组件
3. 运行主循环：事件分发 -> 逻辑更新 -> 渲染

用法示例:
    python main.py --difficulty hard --width 960 --height 640
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

import pygame

from .food import FoodType
from .game import Game, GameState
from .skin import SkinManager
from .snake import Direction, WallMode
from .sound import SoundManager
from .utils import Config, Difficulty, HighScoreStore, setup_logging
from .ui import GameRenderer, Menu, MenuRenderer, Screen


# 方向键映射表：pygame 键码 -> Direction
KEY_DIRECTION_MAP = {
    pygame.K_UP: Direction.UP,
    pygame.K_w: Direction.UP,
    pygame.K_DOWN: Direction.DOWN,
    pygame.K_s: Direction.DOWN,
    pygame.K_LEFT: Direction.LEFT,
    pygame.K_a: Direction.LEFT,
    pygame.K_RIGHT: Direction.RIGHT,
    pygame.K_d: Direction.RIGHT,
}

# 菜单导航键映射：pygame 键码 -> 菜单抽象按键
KEY_MENU_MAP = {
    pygame.K_UP: "up",
    pygame.K_w: "up",
    pygame.K_DOWN: "down",
    pygame.K_s: "down",
    pygame.K_LEFT: "left",
    pygame.K_a: "left",
    pygame.K_RIGHT: "right",
    pygame.K_d: "right",
    pygame.K_RETURN: "confirm",
    pygame.K_SPACE: "confirm",
}


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """解析命令行参数并返回 Namespace。"""
    parser = argparse.ArgumentParser(description="贪吃蛇 Pygame 版")
    parser.add_argument("--width", type=int, default=800, help="窗口宽度（像素）")
    parser.add_argument("--height", type=int, default=600, help="窗口高度（像素）")
    parser.add_argument("--cell", type=int, default=20, help="网格单元边长")
    parser.add_argument("--difficulty", choices=["easy", "normal", "hard"], default="normal")
    parser.add_argument("--wrap", action="store_true", help="开启穿墙模式")
    parser.add_argument("--no-sound", action="store_true", help="关闭音效")
    parser.add_argument("--fullscreen", action="store_true", help="全屏运行")
    parser.add_argument("--fps", type=int, default=60, help="目标帧率")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（调试用）")
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace) -> Config:
    """把命令行参数转换为 Config 对象（难度字符串转为 Difficulty 枚举）。"""
    config = Config(
        window_width=args.width,
        window_height=args.height,
        cell_size=args.cell,
        fps=args.fps,
        difficulty=Difficulty.from_name(args.difficulty),
        sound_enabled=not args.no_sound,
        fullscreen=args.fullscreen,
    )
    config.clamp_to_window()
    return config


class Application:
    """应用层：组合 Screen / MenuRenderer / Game 并驱动主循环。"""

    def __init__(self, config: Config, seed: Optional[int] = None) -> None:
        """初始化窗口、菜单与游戏对象；启动后先显示开始菜单。"""
        self.config = config
        self.screen = Screen(config)
        self.store = HighScoreStore()
        # 皮肤管理：默认经典绿，同步到窗口背景
        self.skin_manager = SkinManager()
        self.screen.apply_skin(self.skin_manager.current)
        # 音效管理：读取设置中的开关与音量，合成全部内置音效
        self.sound = SoundManager(config=config)
        self.sound.build_builtin_sounds()
        self.game = Game(config=config, seed=seed, store=self.store, sound=self.sound)
        # 菜单逻辑：确认开始游戏、左右键切换难度/皮肤、退出程序
        self.menu_logic = Menu(
            on_select=self._on_menu_select,
            difficulty=self.config.difficulty,
            on_difficulty_change=self._on_difficulty_change,
            skin=self.skin_manager.current.name,
            skin_names=self.skin_manager.names(),
            on_skin_change=self._on_skin_change,
        )
        self.menu = MenuRenderer(self.screen)
        # 预创建一局数据后立即回到菜单状态，保证启动第一屏是开始菜单
        self.game.new_game(wall_mode=WallMode.WRAP if config.fullscreen else WallMode.SOLID)
        self.game.back_to_menu()
        self.hud_message = ""
        self.move_accumulator = 0.0
        self.running = True

    def _on_menu_select(self, action: str) -> None:
        """菜单确认回调：根据动作名执行开始游戏 / 退出。

        难度项由 Menu.cycle_difficulty 处理并通过 _on_difficulty_change 同步，
        这里无需重复切换。
        """
        if action == "start":
            self._start_game()
        elif action == "quit":
            self.running = False

    def _on_difficulty_change(self, difficulty: Difficulty) -> None:
        """难度切换回调：写入设置并同步得分倍率（速度在每帧读取设置）。"""
        self.config.difficulty = difficulty
        self.game.score_manager.multiplier = difficulty.score_multiplier

    def _on_skin_change(self, skin_name: str) -> None:
        """皮肤切换回调：更新 SkinManager 并重建窗口背景配色。"""
        self.skin_manager.set_current(skin_name)
        self.screen.apply_skin(self.skin_manager.current)

    # -- 事件 ---------------------------------------------------------------

    def _handle_global_keys(self, event: pygame.event.Event) -> None:
        """处理全局按键：ESC 在菜单中退出程序，在游戏/结束画面中返回开始菜单。"""
        if event.type != pygame.KEYDOWN or event.key != pygame.K_ESCAPE:
            return
        if self.game.state == GameState.MENU:
            self.running = False
        else:
            self._return_to_menu()

    def _return_to_menu(self) -> None:
        """返回开始菜单，并把菜单选中项复位到第一项。

        从结束画面返回时视为"本局结束"，播放收尾音效。
        """
        was_game_over = self.game.state == GameState.GAME_OVER
        self.game.back_to_menu()
        if was_game_over and self.sound is not None:
            self.sound.play("finish")
        self.menu_logic.selected_index = 0

    def _handle_menu_events(self, events: List[pygame.event.Event]) -> None:
        """处理菜单状态事件：↑↓ 选择、←→ 切难度、回车确认、鼠标点击。"""
        for event in events:
            if event.type == pygame.KEYDOWN:
                menu_key = KEY_MENU_MAP.get(event.key)
                if menu_key is not None:
                    self.menu_logic.handle_key(menu_key)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                rects = self.menu.item_rects(self.menu_logic)
                self.menu_logic.handle_click_at(event.pos, rects)

    def _start_game(self) -> None:
        """开始新一局。"""
        self.move_accumulator = 0.0
        self.game.new_game()

    def _handle_playing_events(self, events: List[pygame.event.Event]) -> None:
        """处理游戏进行中/暂停的事件：方向键移动、P 暂停/继续、M 回菜单。"""
        for event in events:
            if event.type == pygame.KEYDOWN:
                direction = KEY_DIRECTION_MAP.get(event.key)
                if direction is not None:
                    self.game.handle_direction(direction)
                elif event.key == pygame.K_p:
                    # P 键切换暂停 / 继续（暂停期间蛇与食物都不更新）
                    self.game.toggle_pause()
                elif event.key == pygame.K_m:
                    self.game.back_to_menu()

    def _handle_game_over_events(self, events: List[pygame.event.Event]) -> None:
        """处理结束画面事件：R 重开，M 回菜单。"""
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    self._start_game()
                elif event.key == pygame.K_m:
                    self.game.back_to_menu()

    def process_events(self) -> List[pygame.event.Event]:
        """收集并按状态分发一帧的事件，返回本帧事件列表。"""
        events = list(pygame.event.get())
        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
        self._handle_global_keys_all(events)
        state = self.game.state
        if state == GameState.MENU:
            self._handle_menu_events(events)
        elif state in (GameState.PLAYING, GameState.PAUSED):
            self._handle_playing_events(events)
        elif state == GameState.GAME_OVER:
            self._handle_game_over_events(events)
        return events

    def _handle_global_keys_all(self, events: List[pygame.event.Event]) -> None:
        """对所有事件执行全局按键处理。"""
        for event in events:
            self._handle_global_keys(event)

    # -- 更新与渲染 ---------------------------------------------------------

    def update(self, dt: float) -> None:
        """推进一帧游戏逻辑。"""
        if self.game.state == GameState.PLAYING:
            self.move_accumulator = self.game.step(dt, self.move_accumulator)

    def render(self) -> None:
        """按状态渲染当前画面。"""
        state = self.game.state
        if state == GameState.MENU:
            self.menu.draw_main_menu(self.game.best_score, self.menu_logic, self.skin_manager)
        elif state in (GameState.PLAYING, GameState.PAUSED):
            self._render_playfield()
            if state == GameState.PAUSED:
                self.play_renderer.draw_pause_overlay()
        elif state == GameState.GAME_OVER:
            self._render_playfield()
            info = self.game.game_over_info()
            self.menu.draw_game_over(
                int(info["score"]), int(info["best"]),
                str(info["reason"]), bool(info["record"]),
            )
        self.screen.flip()

    def _render_playfield(self) -> None:
        """渲染进行中的场景：背景、食物、蛇与加速特效。"""
        self.screen.draw_background()
        game = self.game
        if game.snake is None or game.food_manager is None:
            return
        # 直接使用 GameRenderer 绘制实体与特效（读取当前皮肤配色）
        if not hasattr(self, "play_renderer"):
            self.play_renderer = GameRenderer(self.screen, self.skin_manager)
        self.play_renderer.draw_foods(game.food_manager.foods)
        self.play_renderer.draw_snake(game.snake)
        ratio = game.speed_effect_ratio()
        if ratio > 0:
            self.play_renderer.draw_speed_effect(True, ratio)

    def run(self) -> int:
        """运行主循环直至退出，返回进程退出码。"""
        clock = pygame.time.Clock()
        logger = setup_logging()
        logger.info("游戏启动，难度=%s", self.config.difficulty)
        while self.running:
            dt = clock.tick(self.config.fps) / 1000.0
            self.process_events()
            self.update(dt)
            self.render()
        pygame.quit()
        logger.info("游戏退出")
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    """程序主入口：初始化 pygame 并启动应用。"""
    args = parse_args(argv)
    pygame.init()
    config = build_config(args)
    app = Application(config, seed=args.seed)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
