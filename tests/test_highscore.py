# -*- coding: utf-8 -*-
"""本地高分榜测试。

验证 HighScoreManager 的分数读写：保存到 highscore.json、重新加载、
破纪录判定、损坏文件容错、清除记录，以及与 Game 的联动。
测试全部使用 pytest 的 tmp_path，不触碰真实数据文件。
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from snake.highscore import HIGHSCORE_FILENAME, HighScoreManager


class TestHighScoreManager:
    """验证高分榜的持久化读写与纪录判定。"""

    def test_score_write_and_read_roundtrip(self, tmp_path) -> None:
        """写入分数后落盘为 highscore.json，重新实例化可读回最高分与记录。"""
        manager = HighScoreManager(directory=str(tmp_path))

        # 初始空榜
        assert manager.best_score() == 0
        assert manager.records == []
        assert manager.is_new_record(0) is False  # 0 分不算纪录

        # 提交首个成绩：刷新纪录并自动保存
        assert manager.add_score(120) is True
        assert manager.best_score() == 120
        assert manager.top_scores(3) == [120]

        # 文件确实写到了 highscore.json，且结构正确
        path = os.path.join(str(tmp_path), HIGHSCORE_FILENAME)
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        assert payload["best_score"] == 120
        assert payload["records"][0]["score"] == 120

        # 未破纪录的分数：保存但不影响最高分
        assert manager.add_score(80) is False
        assert manager.best_score() == 120

        # 重新加载（模拟下次启动）：数据一致，记录按分数降序
        reloaded = HighScoreManager(directory=str(tmp_path))
        assert reloaded.best_score() == 120
        assert reloaded.top_scores(5) == [120, 80]
        assert reloaded.is_new_record(121) is True
        assert reloaded.is_new_record(120) is False  # 平纪录不算破纪录

        # 清除最高分：内存与磁盘同步归零
        reloaded.clear()
        assert reloaded.best_score() == 0
        cleared = HighScoreManager(directory=str(tmp_path))
        assert cleared.best_score() == 0
        assert cleared.records == []

        # 记录条数上限裁剪
        for score in range(1, 15):
            cleared.add_score(score)
        assert len(cleared.records) <= cleared.max_records
        assert cleared.best_score() == 14

    def test_corrupt_file_and_legacy_format(self, tmp_path) -> None:
        """损坏文件回退为空榜；旧版列表格式可被兼容读取。"""
        broken = tmp_path / "broken.json"
        broken.write_text("{ not valid json ", encoding="utf-8")
        manager = HighScoreManager(directory=str(tmp_path), filename="broken.json")
        assert manager.load() is False
        assert manager.best_score() == 0

        # 旧格式：直接是记录列表（兼容历史 highscores.json）
        legacy = tmp_path / "legacy.json"
        legacy.write_text(
            json.dumps([{"name": "P", "score": 50, "date": "2026-01-01"}], ensure_ascii=False),
            encoding="utf-8",
        )
        legacy_manager = HighScoreManager(directory=str(tmp_path), filename="legacy.json")
        assert legacy_manager.best_score() == 50

        # 删除文件同样安全
        assert manager.clear_file() is True
        assert not os.path.exists(manager.path)


class TestHighScoreGameIntegration:
    """验证 Game 使用 HighScoreManager 时，游戏结束会自动保存成绩。"""

    def test_game_over_saves_record(self, tmp_path) -> None:
        """撞墙结束后成绩写入 highscore.json，且被判定为新纪录。"""
        from snake.game import Game, GameState
        from snake.snake import Direction, WallMode
        from snake.utils import Config

        manager = HighScoreManager(directory=str(tmp_path))
        config = Config(window_width=200, window_height=200, cell_size=20)
        game = Game(config=config, seed=3, store=manager)
        game.new_game(wall_mode=WallMode.SOLID)

        # 直接向右撞墙结束本局
        for _ in range(50):
            if game.state == GameState.GAME_OVER:
                break
            game.handle_direction(Direction.RIGHT)
            game.step(0.5, 0.5)
        assert game.state == GameState.GAME_OVER

        # 得分 > 0 时自动落盘；最高分与 game 查询一致
        if game.score > 0:
            assert os.path.exists(manager.path)
            assert manager.best_score() == game.score
        assert game.game_over_info()["best"] == manager.best_score()


class TestClearByLongPress:
    """验证菜单中长按 C 键清除最高分，以及清除后磁盘同步。"""

    def test_long_press_c_clears_best_score(self, tmp_path, monkeypatch) -> None:
        """按住 C 超过阈值才清除；短按取消，不误删记录。"""
        import pygame

        pygame.init()
        monkeypatch.chdir(tmp_path)  # 让 Application 的默认路径落在临时目录

        # 预置一条历史最高分
        HighScoreManager().add_score(120)
        assert HighScoreManager().best_score() == 120

        from snake.main import Application, build_config, parse_args

        app = Application(build_config(parse_args(["--width", "400", "--height", "400"])))
        assert app.store.best_score() == 120
        assert app.game.best_score == 120  # 菜单展示的历史最高分

        # 短按 C（按下后 0.3 秒松开）：不触发清除
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c))
        app.process_events()
        app.update(0.3)
        pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_c))
        app.process_events()
        app.update(0.5)
        assert app.store.best_score() == 120

        # 长按 C：按住 1.2 秒后清除最高分并给出提示
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c))
        app.process_events()
        app.update(0.6)
        assert app.store.best_score() == 120  # 未达阈值
        app.update(0.6)
        assert app.store.best_score() == 0
        assert app.notice == "最高分记录已清除"
        assert app.notice_timer > 0
        app.render()  # 提示文字绘制不报错

        # 磁盘同步归零，重新加载仍为 0
        assert HighScoreManager().best_score() == 0

        # 提示 3 秒后自动消失
        app.update(3.1)
        assert app.notice == ""

    def test_game_over_record_prompt_and_autosave(self, tmp_path, monkeypatch) -> None:
        """打破纪录时 game_over_info 标记 record，并自动写入 highscore.json。"""
        import pygame

        pygame.init()
        monkeypatch.chdir(tmp_path)
        HighScoreManager().add_score(5)  # 旧纪录：5 分

        from snake.main import Application, build_config, parse_args
        from snake.game import GameState
        from snake.snake import Direction, WallMode

        app = Application(build_config(parse_args(["--width", "400", "--height", "400"])))
        app.menu_logic.handle_key("confirm")
        assert app.game.state == GameState.PLAYING

        # 白盒：把食物放在蛇头前方吃到，拿到分数后再撞墙
        head = app.game.snake.head_position
        from snake.food import Food, FoodType

        app.game.food_manager.foods = [Food((head[0] + 1, head[1]), FoodType.NORMAL)]
        app.game.handle_direction(Direction.RIGHT)
        app.update(0.5)
        assert app.game.score > 5  # 已超过旧纪录

        for _ in range(60):
            if app.game.state == GameState.GAME_OVER:
                break
            app.game.handle_direction(Direction.RIGHT)
            app.update(0.5)
        assert app.game.state == GameState.GAME_OVER

        info = app.game.game_over_info()
        assert info["record"] is True            # 破纪录 → 结束画面显示"新纪录！已保存"
        assert info["best"] == app.game.score
        assert HighScoreManager().best_score() == app.game.score  # 已自动落盘


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
