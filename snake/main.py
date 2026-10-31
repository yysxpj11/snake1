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
from typing import List, Optional, Tuple

import pygame

from .food import FoodType
from .game import Game, GameState
from .highscore import HighScoreManager
from .settings import SettingsManager
from .skin import SkinManager
from .snake import Direction, WallMode
from .sound import SoundManager
from .utils import Config, Difficulty, setup_logging
from .ui import GameRenderer, Menu, MenuRenderer, Screen, SettingsPanel


# 长按 C 键清除最高分所需的按住时长（秒）
CLEAR_HOLD_SECONDS = 1.0


# 方向键映射表：pygame 键码 -> Direction
# 注意：S 键已让位给"游戏内切换皮肤"，向下移动使用 ↓ 键
KEY_DIRECTION_MAP = {
    pygame.K_UP: Direction.UP,
    pygame.K_w: Direction.UP,
    pygame.K_DOWN: Direction.DOWN,
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
        # 设置持久化：启动时自动加载上次保存的音量/难度/皮肤，
        # 必须在创建 SoundManager / Game / Menu 之前应用，
        # 这样音量、得分倍率与菜单标签都能直接取到恢复后的值。
        self.settings = SettingsManager()
        self._apply_saved_settings()
        self.screen = Screen(config)
        # 本地高分榜：独立 highscore.json，成绩自动落盘
        self.store = HighScoreManager()
        # 皮肤管理：默认经典绿；有上次保存的皮肤时恢复（名称无效则保持默认）
        self.skin_manager = SkinManager()
        if self.settings.loaded and self.settings.skin:
            self.skin_manager.set_current(self.settings.skin)
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
        # 长按 C 清除最高分的输入状态
        self._clear_armed = False   # C 键是否处于按下状态
        self._clear_hold = 0.0      # 已按住时长（秒）
        self._clear_done = False    # 本次按住是否已执行清除
        self.notice = ""            # 菜单底部临时提示
        self.notice_timer = 0.0
        # 设置面板：进入设置状态时创建，保存/返回后置空
        self.settings_panel: Optional[SettingsPanel] = None
        # 打开面板时的设置快照：实时预览改了也要能 ESC 一键回滚
        self._settings_snapshot: Optional[Tuple[float, Difficulty, str]] = None
        # 音量滑条是否处于按住拖动状态
        self._dragging_volume = False

    def _apply_saved_settings(self) -> None:
        """把上次保存的设置写回 Config（未保存过或单项非法时保持默认）。

        音量与难度写入 config 后，SoundManager / Game 构造时即可取到；
        皮肤在 SkinManager 创建后单独恢复（见 __init__）。
        """
        if not self.settings.loaded:
            return
        self.config.sound_volume = self.settings.sound_volume
        self.config.difficulty = Difficulty.from_name(self.settings.difficulty)

    def _on_menu_select(self, action: str) -> None:
        """菜单确认回调：根据动作名执行开始游戏 / 退出。

        难度项由 Menu.cycle_difficulty 处理并通过 _on_difficulty_change 同步，
        这里无需重复切换。
        """
        if action == "start":
            self._start_game()
        elif action == "settings":
            # 打开设置面板：暂存值取当前生效设置
            self._open_settings()
        elif action == "quit":
            self.running = False

    def _open_settings(self) -> None:
        """进入设置面板，并以当前生效设置为初值创建面板。

        菜单中确认"设置"与游戏内按 V 走同一条入口；
        关闭时由 Game.exit_settings 恢复到打开前的状态
        （菜单回到菜单，游戏内回到进行中/暂停，本局不中断）。
        """
        if self.game.enter_settings():
            # 记录快照：面板里的改动会实时生效，ESC 时据此回滚
            self._settings_snapshot = (
                self.config.sound_volume,
                self.config.difficulty,
                self.skin_manager.current.name,
            )
            self._dragging_volume = False
            self.settings_panel = SettingsPanel(
                volume=self.config.sound_volume,
                difficulty=self.config.difficulty,
                skin=self.skin_manager.current.name,
                skin_names=self.skin_manager.names(),
                on_save=self._on_settings_save,
                on_cancel=self._on_settings_cancel,
                on_change=self._on_settings_change,
            )

    def _on_settings_change(self, volume: float, difficulty: Difficulty, skin_name: str) -> None:
        """面板调整回调：音量 / 难度 / 皮肤一改就生效，不必等回车保存。

        - 音量：直接写 SoundManager 主音量，正在播放/下次播放都按新音量走；
        - 难度：写入 config，Game.current_move_interval 每帧读取它，
          所以下一格起蛇的移动间隔立刻变化，得分倍率同步刷新；
        - 皮肤：立即重绘背景配色，菜单标签一并同步。
        此时不落盘，持久化仍由回车保存负责（ESC 可整体回滚）。
        """
        self.sound.set_volume(volume)
        self.config.sound_volume = volume
        if difficulty != self.config.difficulty:
            self.menu_logic.set_difficulty(difficulty, notify=True)
        if skin_name and skin_name != self.skin_manager.current.name:
            self.menu_logic.set_skin(skin_name, notify=True)

    def _on_settings_save(self, volume: float, difficulty: Difficulty, skin_name: str) -> None:
        """回车保存：把面板暂存值应用到各组件并持久化到 settings.json。"""
        self.sound.set_volume(volume)
        self.config.sound_volume = volume
        self.menu_logic.set_difficulty(difficulty, notify=True)
        self.menu_logic.set_skin(skin_name, notify=True)
        # 持久化：下次启动自动恢复这三项设置
        self.settings.update(volume=volume, difficulty=difficulty.value, skin=skin_name)
        self._settings_snapshot = None
        self._close_settings("设置已保存")

    def _on_settings_cancel(self) -> None:
        """ESC 返回：把实时预览过的改动回滚到打开面板前的值。"""
        self._restore_settings_snapshot()
        self._close_settings("")

    def _restore_settings_snapshot(self) -> None:
        """把音量/难度/皮肤恢复到打开设置面板时的快照（未保存的预览作废）。"""
        if self._settings_snapshot is None:
            return
        volume, difficulty, skin_name = self._settings_snapshot
        self._settings_snapshot = None
        self.sound.set_volume(volume)
        self.config.sound_volume = volume
        if difficulty != self.config.difficulty:
            self.menu_logic.set_difficulty(difficulty, notify=True)
        if skin_name and skin_name != self.skin_manager.current.name:
            self.menu_logic.set_skin(skin_name, notify=True)

    def _close_settings(self, notice: str) -> None:
        """关闭设置面板，notice 为空时不显示提示。

        根据打开来源决定去向：游戏内打开时回到进行中/暂停并复位移动累加器
        （否则调设置花掉的时间会一次性攒起来，关掉瞬间连跳好几格）；
        菜单中打开时回到菜单。
        """
        from_game = self.game.settings_from_game
        self.settings_panel = None
        self._dragging_volume = False
        self._settings_snapshot = None
        if from_game:
            self.game.exit_settings()
            self.move_accumulator = 0.0
        else:
            self.game.back_to_menu()
        if notice:
            self.notice = notice
            self.notice_timer = 3.0

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
        elif self.game.state == GameState.SETTINGS:
            # 设置面板中的 ESC：放弃修改并返回菜单
            if self.settings_panel is not None:
                self.settings_panel.cancel()
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
        """处理菜单状态事件：↑↓ 选择、←→ 切难度/皮肤、回车确认、鼠标点击、长按 C 清榜。"""
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_c:
                    # 开始计时"长按 C"，达到阈值后在 update 中清除最高分
                    self._clear_armed = True
                    self._clear_hold = 0.0
                    self._clear_done = False
                    continue
                menu_key = KEY_MENU_MAP.get(event.key)
                if menu_key is not None:
                    self.menu_logic.handle_key(menu_key)
            elif event.type == pygame.KEYUP and event.key == pygame.K_c:
                # 松开 C 键：时长未达阈值即取消
                self._clear_armed = False
                self._clear_hold = 0.0
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                rects = self.menu.item_rects(self.menu_logic)
                self.menu_logic.handle_click_at(event.pos, rects)

    def _update_clear_hold(self, dt: float) -> None:
        """累计 C 键按住时长，达到阈值时清除最高分记录（每次按住只清一次）。"""
        if not self._clear_armed or self._clear_done:
            return
        self._clear_hold += dt
        if self._clear_hold >= CLEAR_HOLD_SECONDS:
            self._clear_done = True
            self.store.clear()
            self.notice = "最高分记录已清除"
            self.notice_timer = 3.0
            logger = setup_logging()
            logger.info("最高分记录已清除")

    def _handle_settings_events(self, events: List[pygame.event.Event]) -> None:
        """处理设置面板事件：↑↓ 选项、←→ 调值、鼠标拖动音量滑条、回车保存。

        ESC 由全局按键处理（回滚并返回），这里不重复处理。
        """
        panel = self.settings_panel
        if panel is None:
            return
        for event in events:
            if event.type == pygame.KEYDOWN:
                menu_key = KEY_MENU_MAP.get(event.key)
                if menu_key is not None:
                    panel.handle_key(menu_key)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self._volume_hit(event.pos):
                    # 按下即定位到音量项并跳到点击位置，随后拖动持续跟随
                    self._dragging_volume = True
                    self._select_volume_item()
                    self._drag_volume_to(event.pos[0])
            elif event.type == pygame.MOUSEMOTION and self._dragging_volume:
                self._drag_volume_to(event.pos[0])
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._dragging_volume = False

    def _volume_hit(self, pos: Tuple[int, int]) -> bool:
        """判断鼠标位置是否落在音量滑条的命中区域内。"""
        panel = self.settings_panel
        if panel is None:
            return False
        return self.menu.volume_hit_rect(panel).collidepoint(pos)

    def _select_volume_item(self) -> None:
        """把面板选中项切到"音量"，让随后的左右键继续调整音量。"""
        panel = self.settings_panel
        if panel is None:
            return
        actions = [action for _label, action in panel.items]
        if "volume" in actions:
            panel.selected_index = actions.index("volume")

    def _drag_volume_to(self, mouse_x: int) -> None:
        """把鼠标横坐标换算成音量百分比并写入面板（拖动时实时生效）。"""
        panel = self.settings_panel
        if panel is None:
            return
        panel.set_volume_percent(self.menu.volume_percent_at(panel, mouse_x))

    def _start_game(self) -> None:
        """开始新一局。"""
        self.move_accumulator = 0.0
        self.game.new_game()

    def _handle_playing_events(self, events: List[pygame.event.Event]) -> None:
        """处理游戏进行中/暂停的事件：方向键移动、P 暂停、V 设置、S 切皮肤、M 回菜单。"""
        for event in events:
            if event.type == pygame.KEYDOWN:
                direction = KEY_DIRECTION_MAP.get(event.key)
                if direction is not None:
                    self.game.handle_direction(direction)
                elif event.key == pygame.K_p:
                    # P 键切换暂停 / 继续（暂停期间蛇与食物都不更新）
                    self.game.toggle_pause()
                elif event.key == pygame.K_v:
                    # V 键就地打开设置面板：调整即时生效，关掉后继续这一局
                    self._open_settings()
                elif event.key == pygame.K_s:
                    # S 键循环切换皮肤：换肤立即生效并同步菜单标签
                    self.menu_logic.set_skin(self.skin_manager.next().name)
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
        elif state == GameState.SETTINGS:
            self._handle_settings_events(events)
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
        """推进一帧游戏逻辑（含菜单中的长按清榜与提示计时）。"""
        # 临时提示倒计时（菜单底部"已清除"文字）
        if self.notice_timer > 0:
            self.notice_timer = max(0.0, self.notice_timer - dt)
            if self.notice_timer == 0:
                self.notice = ""
        if self.game.state in (GameState.MENU, GameState.SETTINGS):
            self._update_clear_hold(dt)
            return
        if self.game.state == GameState.PLAYING:
            self.move_accumulator = self.game.step(dt, self.move_accumulator)

    def render(self) -> None:
        """按状态渲染当前画面。"""
        state = self.game.state
        if state == GameState.MENU:
            self.menu.draw_main_menu(
                self.game.best_score, self.menu_logic, self.skin_manager, self.notice
            )
        elif state == GameState.SETTINGS:
            if self.settings_panel is not None:
                # 游戏内打开：先画冻结的战场，再压暗叠加面板，保留局势参照
                from_game = self.game.settings_from_game
                if from_game:
                    self._render_playfield()
                self.menu.draw_settings_panel(
                    self.settings_panel, self.skin_manager, translucent=from_game
                )
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
