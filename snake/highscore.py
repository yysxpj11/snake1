# -*- coding: utf-8 -*-
"""本地高分榜模块。

- HighScoreManager: 最高分的加载 / 保存 / 破纪录判定 / 清除

数据文件默认为项目根目录下的 highscore.json，结构：
{
  "best_score": 120,
  "records": [{"score": 120, "date": "2026-10-30 18:20"}, ...],
  "updated": "2026-10-30 18:20"
}

写入采用"临时文件 + 原子替换"，避免中途崩溃导致文件损坏；
读取时对损坏/旧格式文件做容错，无法解析则视为空榜（不抛异常）。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认数据文件名
HIGHSCORE_FILENAME = "highscore.json"

# 默认保留的记录条数
DEFAULT_MAX_RECORDS = 10


class HighScoreManager:
    """本地高分榜管理器：负责最高分持久化与破纪录判断。

    Attributes:
        path: 数据文件完整路径。
        max_records: 榜单最多保留的记录条数。
    """

    def __init__(
        self,
        directory: str = ".",
        filename: str = HIGHSCORE_FILENAME,
        max_records: int = DEFAULT_MAX_RECORDS,
    ) -> None:
        """初始化数据路径并加载已有记录。

        Args:
            directory: 数据文件所在目录，默认当前工作目录。
            filename: 数据文件名，默认 highscore.json。
            max_records: 榜单保留的最大条数。
        """
        self.directory = directory
        self.filename = filename
        self.path = os.path.join(directory, filename)
        self.max_records = max(1, int(max_records))
        self._best_score: int = 0
        self._records: List[Dict[str, object]] = []
        self._updated: str = ""
        self.load()

    # -- 读写 ---------------------------------------------------------------

    def load(self) -> bool:
        """从磁盘加载高分数据，成功返回 True。

        文件不存在、内容损坏或格式不符时回退为空榜（best=0），
        并返回 False，不抛出异常。
        """
        self._best_score = 0
        self._records = []
        self._updated = ""
        if not os.path.exists(self.path):
            logger.debug("高分文件不存在，使用空榜: %s", self.path)
            return False
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取高分文件失败，使用空榜: %s", exc)
            return False
        # 新格式：字典；旧格式：记录列表（兼容并迁移）
        if isinstance(data, dict):
            records = data.get("records", [])
            if not isinstance(records, list):
                records = []
            self._records = [rec for rec in records if isinstance(rec, dict)]
            best = data.get("best_score", 0)
            self._best_score = int(best) if isinstance(best, (int, float)) else 0
            self._updated = str(data.get("updated", ""))
        elif isinstance(data, list):
            # 兼容旧版 highscores.json 的列表格式
            self._records = [rec for rec in data if isinstance(rec, dict)]
        else:
            logger.warning("高分文件格式未知，使用空榜: %s", self.path)
            return False
        self._normalize()
        return True

    def save(self) -> bool:
        """把当前榜单原子写入磁盘，成功返回 True。

        先写入同目录临时文件再 os.replace，保证不会留下半截文件；
        写入失败仅记录日志并返回 False（游戏不因存储问题崩溃）。
        """
        payload = {
            "best_score": self._best_score,
            "records": self._records,
            "updated": self._updated or time.strftime("%Y-%m-%d %H:%M"),
        }
        try:
            if self.directory and not os.path.isdir(self.directory):
                os.makedirs(self.directory, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                prefix=".highscore_", suffix=".tmp", dir=self.directory or "."
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
            return True
        except OSError as exc:
            logger.warning("保存高分文件失败: %s", exc)
            return False

    def _normalize(self) -> None:
        """整理记录：按分数降序、裁剪条数、重算最高分。"""
        cleaned: List[Dict[str, object]] = []
        for rec in self._records:
            try:
                score = int(rec.get("score", 0))
            except (TypeError, ValueError):
                continue
            cleaned.append(
                {"score": score, "date": str(rec.get("date", ""))}
            )
        cleaned.sort(key=lambda item: int(item["score"]), reverse=True)
        self._records = cleaned[: self.max_records]
        top = int(self._records[0]["score"]) if self._records else 0
        # 文件中的 best_score 与记录表取较大者，避免数据不一致导致显示回退
        self._best_score = max(self._best_score, top)

    # -- 查询 ---------------------------------------------------------------

    @property
    def best(self) -> int:
        """历史最高分（无记录为 0）。"""
        return self._best_score

    @property
    def records(self) -> List[Dict[str, object]]:
        """只读的记录列表（已按分数降序）。"""
        return [dict(rec) for rec in self._records]

    def best_score(self) -> int:
        """历史最高分（与 Game 期望的 store 接口保持一致）。"""
        return self._best_score

    def top_scores(self, count: int = 5) -> List[int]:
        """返回前 count 名的分数列表。"""
        return [int(rec["score"]) for rec in self._records[: max(0, count)]]

    def is_new_record(self, score: int) -> bool:
        """判断给定分数是否打破历史纪录（需大于 0 且严格大于当前最高分）。"""
        return score > 0 and score > self._best_score

    # -- 写入 ---------------------------------------------------------------

    def add_score(self, score: int, date: Optional[str] = None) -> bool:
        """登记一局成绩并立即保存，返回是否刷新了纪录。

        Args:
            score: 本局得分。
            date: 记录时间字符串，默认取当前时间。
        """
        score = int(score)
        record_broken = self.is_new_record(score)
        if score > 0:
            self._records.append(
                {"score": score, "date": date or time.strftime("%Y-%m-%d %H:%M")}
            )
            self._best_score = max(self._best_score, score)
            self._updated = time.strftime("%Y-%m-%d %H:%M")
            self._normalize()
        self.save()
        return record_broken

    def submit(self, score: int, date: Optional[str] = None) -> bool:
        """add_score 的语义化别名：提交一局成绩并保存。"""
        return self.add_score(score, date)

    def clear(self) -> None:
        """清空全部记录（含最高分）并立即写盘。"""
        self._best_score = 0
        self._records = []
        self._updated = time.strftime("%Y-%m-%d %H:%M")
        self.save()
        logger.info("最高分记录已清除")

    def clear_file(self) -> bool:
        """删除数据文件并清空内存状态，成功返回 True。"""
        self._best_score = 0
        self._records = []
        self._updated = ""
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
            return True
        except OSError as exc:
            logger.warning("删除高分文件失败: %s", exc)
            return False
