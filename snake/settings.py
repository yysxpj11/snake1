# -*- coding: utf-8 -*-
"""本地设置持久化模块。

- SettingsManager: 音量 / 难度 / 皮肤三项设置的加载与保存

数据文件默认为工作目录下的 settings.json，结构：
{
  "sound_volume": 0.7,
  "difficulty": "normal",
  "skin": "经典绿",
  "updated": "2026-10-31 13:30"
}

写入采用"临时文件 + 原子替换"，避免中途崩溃导致文件损坏；
读取时对损坏/非法值做容错：文件缺失或无法解析视为未保存过，
单项值非法时回退到该项默认值，均不抛异常。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 默认数据文件名
SETTINGS_FILENAME = "settings.json"

# 各设置项的默认值（与 Config / SkinManager 的默认保持一致）
DEFAULT_SOUND_VOLUME = 0.7
DEFAULT_DIFFICULTY = "normal"
DEFAULT_SKIN = ""  # 空字符串表示"未保存过皮肤"，由调用方用当前默认皮肤兜底


class SettingsManager:
    """本地设置管理器：音量、难度、皮肤的持久化。

    Attributes:
        path: 数据文件完整路径。
        loaded: 构造时是否成功加载了已有设置文件。
    """

    def __init__(self, directory: str = ".", filename: str = SETTINGS_FILENAME) -> None:
        """初始化数据路径并加载已有设置。

        Args:
            directory: 数据文件所在目录，默认当前工作目录。
            filename: 数据文件名，默认 settings.json。
        """
        self.directory = directory
        self.filename = filename
        self.path = os.path.join(directory, filename)
        self.loaded: bool = False
        self._sound_volume: float = DEFAULT_SOUND_VOLUME
        self._difficulty: str = DEFAULT_DIFFICULTY
        self._skin: str = DEFAULT_SKIN
        self._updated: str = ""
        self.load()

    # -- 读取 ---------------------------------------------------------------

    def load(self) -> bool:
        """从磁盘加载设置，成功返回 True。

        文件不存在或内容损坏时保持默认值并返回 False，不抛出异常；
        单项值非法时该项回退默认值（其余项照常生效）。
        """
        self.loaded = False
        self._sound_volume = DEFAULT_SOUND_VOLUME
        self._difficulty = DEFAULT_DIFFICULTY
        self._skin = DEFAULT_SKIN
        self._updated = ""
        if not os.path.exists(self.path):
            logger.debug("设置文件不存在，使用默认设置: %s", self.path)
            return False
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取设置文件失败，使用默认设置: %s", exc)
            return False
        if not isinstance(data, dict):
            logger.warning("设置文件格式未知，使用默认设置: %s", self.path)
            return False
        self._sound_volume = self._sanitize_volume(data.get("sound_volume"))
        self._difficulty = self._sanitize_difficulty(data.get("difficulty"))
        self._skin = self._sanitize_skin(data.get("skin"))
        self._updated = str(data.get("updated", ""))
        self.loaded = True
        return True

    @staticmethod
    def _sanitize_volume(value: object) -> float:
        """校验音量值：必须是 0.0-1.0 的数字，非法回退默认值。"""
        if isinstance(value, (int, float)) and 0.0 <= float(value) <= 1.0:
            return float(value)
        logger.debug("音量值非法(%r)，回退默认 %.2f", value, DEFAULT_SOUND_VOLUME)
        return DEFAULT_SOUND_VOLUME

    @staticmethod
    def _sanitize_difficulty(value: object) -> str:
        """校验难度值：必须是 easy/normal/hard 之一，非法回退默认值。"""
        if isinstance(value, str) and value.strip().lower() in ("easy", "normal", "hard"):
            return value.strip().lower()
        logger.debug("难度值非法(%r)，回退默认 %s", value, DEFAULT_DIFFICULTY)
        return DEFAULT_DIFFICULTY

    @staticmethod
    def _sanitize_skin(value: object) -> str:
        """校验皮肤名：必须是非空字符串，非法回退为空（由调用方兜底）。"""
        if isinstance(value, str) and value.strip():
            return value.strip()
        return DEFAULT_SKIN

    # -- 写入 ---------------------------------------------------------------

    def save(self) -> bool:
        """把当前设置原子写入磁盘，成功返回 True。

        先写入同目录临时文件再 os.replace，保证不会留下半截文件；
        写入失败仅记录日志并返回 False（游戏不因存储问题崩溃）。
        """
        payload = {
            "sound_volume": self._sound_volume,
            "difficulty": self._difficulty,
            "skin": self._skin,
            "updated": time.strftime("%Y-%m-%d %H:%M"),
        }
        try:
            if self.directory and not os.path.isdir(self.directory):
                os.makedirs(self.directory, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                prefix=".settings_", suffix=".tmp", dir=self.directory or "."
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
            self._updated = payload["updated"]
            return True
        except OSError as exc:
            logger.warning("保存设置文件失败: %s", exc)
            return False

    def update(
        self,
        volume: Optional[float] = None,
        difficulty: Optional[str] = None,
        skin: Optional[str] = None,
    ) -> bool:
        """更新一或多项设置并立即写盘。

        Args:
            volume: 音量（0.0-1.0），None 表示不修改。
            difficulty: 难度名（easy/normal/hard），None 表示不修改。
            skin: 皮肤名称，None 表示不修改。

        Returns:
            save() 的结果（是否成功落盘）。
        """
        if volume is not None:
            # 写入时裁剪到 0.0-1.0（读取时非法值才回退默认）
            self._sound_volume = max(0.0, min(1.0, float(volume)))
        if difficulty is not None:
            self._difficulty = self._sanitize_difficulty(str(difficulty))
        if skin is not None:
            self._skin = self._sanitize_skin(skin)
        return self.save()

    # -- 查询 ---------------------------------------------------------------

    @property
    def sound_volume(self) -> float:
        """已保存的音量（0.0-1.0）。"""
        return self._sound_volume

    @property
    def difficulty(self) -> str:
        """已保存的难度名（easy/normal/hard）。"""
        return self._difficulty

    @property
    def skin(self) -> str:
        """已保存的皮肤名（空字符串表示未保存过）。"""
        return self._skin
