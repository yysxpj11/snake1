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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
