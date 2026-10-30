# -*- coding: utf-8 -*-
"""音效管理模块。

- SoundManager: 集中管理所有音效的注册、音量与播放

所有音效均由本模块内置的波形合成器实时生成（正弦波 / 方波 / 噪声），
不依赖任何外部音频素材文件；合成结果封装为 pygame.mixer.Sound 对象。

若运行环境没有可用的音频设备（如无头 CI 环境），SoundManager 会自动
降级为"静音模式"：所有播放调用变成无副作用的安全空操作。
"""

from __future__ import annotations

import array
import logging
import math
from typing import Dict, Optional, Tuple

from .utils import Config, clamp

logger = logging.getLogger(__name__)

# 内部合成使用的采样率（Hz）：22.05kHz 对短音效足够清晰且内存占用小
SAMPLE_RATE = 22050

# 16 位有符号整数的振幅上限
MAX_AMPLITUDE = 32767

# 支持的波形类型
WAVE_SINE = "sine"
WAVE_SQUARE = "square"
WAVE_SAWTOOTH = "sawtooth"
WAVE_NOISE = "noise"

_VALID_WAVES = (WAVE_SINE, WAVE_SQUARE, WAVE_SAWTOOTH, WAVE_NOISE)


class SoundManager:
    """音效管理器：统一负责音效的合成、注册、音量控制与播放。

    Attributes:
        master_volume: 主音量（0.0 - 1.0），来自设置并支持运行时调节。
        enabled: 是否启用音效；关闭时 play() 直接跳过。
        available: 混音器是否初始化成功（决定能否真正发声）。
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        sample_rate: int = SAMPLE_RATE,
        init_mixer: bool = True,
    ) -> None:
        """初始化音效管理器。

        Args:
            config: 游戏配置；读取 sound_enabled 与 sound_volume 字段。
            sample_rate: 波形合成的采样率。
            init_mixer: 是否尝试初始化 pygame.mixer（测试时可关闭）。
        """
        self.sample_rate = sample_rate
        self.config = config
        self.sounds: Dict[str, "object"] = {}
        self.enabled: bool = True if config is None else config.sound_enabled
        self.master_volume: float = 0.7 if config is None else config.sound_volume
        self.available: bool = False
        if init_mixer:
            self.available = self._try_init_mixer()
        if self.available:
            self.apply_volume()
            logger.info("音频混音器初始化成功，采样率=%d", self.sample_rate)
        else:
            logger.info("无可用音频设备，SoundManager 进入静音降级模式")

    # -- 混音器与音量 -------------------------------------------------------

    def _try_init_mixer(self) -> bool:
        """尝试初始化 pygame.mixer，失败时返回 False（不抛异常）。"""
        try:
            import pygame

            if not pygame.get_init():
                pygame.init()
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=1, buffer=512)
            return pygame.mixer.get_init() is not None
        except Exception as exc:  # 无声卡 / 虚拟环境等场景
            logger.debug("pygame.mixer 初始化失败: %s", exc)
            return False

    def set_volume(self, volume: float) -> None:
        """设置主音量（自动裁剪到 0.0 - 1.0 区间）并即时生效。"""
        self.master_volume = clamp(float(volume), 0.0, 1.0)
        self.apply_volume()

    def apply_volume(self) -> None:
        """把主音量应用到所有已注册音效上。"""
        if not self.available:
            return
        for sound in self.sounds.values():
            try:
                sound.set_volume(self.master_volume)
            except Exception:
                pass

    def enable(self) -> None:
        """启用音效播放。"""
        self.enabled = True

    def disable(self) -> None:
        """禁用音效播放（play 调用将被忽略）。"""
        self.enabled = False

    # -- 波形合成 -----------------------------------------------------------

    def synthesize(
        self,
        duration: float,
        start_freq: float,
        end_freq: Optional[float] = None,
        wave: str = WAVE_SINE,
        volume: float = 1.0,
        fade_out: bool = True,
    ) -> Optional["object"]:
        """合成一段音效并返回 pygame.mixer.Sound 对象。

        Args:
            duration: 音效时长（秒）。
            start_freq: 起始频率（Hz）。
            end_freq: 结束频率（Hz）；None 表示恒定音高，否则在起止间线性滑音。
            wave: 波形类型（sine / square / sawtooth / noise）。
            volume: 本段音效的相对音量（0.0 - 1.0），最终再乘以主音量。
            fade_out: 末尾 10% 是否做淡出，避免爆音。

        Returns:
            合成好的 Sound 对象；混音器不可用时返回 None。
        """
        if not self.available:
            return None
        import pygame

        wave = wave if wave in _VALID_WAVES else WAVE_SINE
        end_freq = start_freq if end_freq is None else end_freq
        total = max(1, int(self.sample_rate * duration))
        amp = MAX_AMPLITUDE * clamp(volume, 0.0, 1.0)
        fade_len = max(1, int(total * 0.1)) if fade_out else 0
        buf = array.array("h", bytes(2 * total))
        phase = 0.0
        for i in range(total):
            progress = i / total
            freq = start_freq + (end_freq - start_freq) * progress
            phase += freq / self.sample_rate
            if wave == WAVE_SINE:
                sample = math.sin(2.0 * math.pi * phase)
            elif wave == WAVE_SQUARE:
                sample = 1.0 if (phase % 1.0) < 0.5 else -1.0
            elif wave == WAVE_SAWTOOTH:
                sample = 2.0 * (phase % 1.0) - 1.0
            else:  # noise：用相位哈希模拟白噪声，保证确定性
                sample = ((int(phase * self.sample_rate) * 1103515245 + 12345) % 65536) / 32768.0 - 1.0
            if fade_len and i > total - fade_len:
                sample *= (total - i) / fade_len
            buf[i] = int(sample * amp)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    # -- 注册与播放 ---------------------------------------------------------

    def register(self, name: str, sound: Optional["object"]) -> None:
        """注册一个命名音效；sound 为 None 时忽略（静音降级场景）。"""
        if sound is None:
            return
        self.sounds[name] = sound
        try:
            sound.set_volume(self.master_volume)
        except Exception:
            pass

    def play(self, name: str) -> bool:
        """按名称播放音效，返回是否真正触发了播放。

        以下情况均为安全空操作并返回 False：
        - 音效被禁用（enabled=False）
        - 混音器不可用（静音降级模式）
        - 名称未注册
        """
        if not self.enabled or not self.available:
            return False
        sound = self.sounds.get(name)
        if sound is None:
            logger.debug("播放请求被忽略：音效 '%s' 未注册", name)
            return False
        try:
            sound.play()
            return True
        except Exception as exc:
            logger.debug("播放音效 '%s' 失败: %s", name, exc)
            return False

    def has_sound(self, name: str) -> bool:
        """查询某名称的音效是否已注册。"""
        return name in self.sounds

    def stop_all(self) -> None:
        """停止当前正在播放的所有音效。"""
        if not self.available:
            return
        import pygame

        try:
            pygame.mixer.stop()
        except Exception:
            pass

    # -- 调试辅助 -----------------------------------------------------------

    def describe(self) -> Tuple[int, float, bool]:
        """返回（已注册音效数, 主音量, 是否可用）元组，便于日志与调试。"""
        return len(self.sounds), self.master_volume, self.available
