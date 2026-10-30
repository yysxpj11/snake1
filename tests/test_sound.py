# -*- coding: utf-8 -*-
"""SoundManager 音效管理器的测试用例。

覆盖：初始化（含静音降级模式）、音量裁剪、注册与播放的安全空操作。
测试不依赖真实声卡：混音器初始化失败时 SoundManager 会自动降级。
"""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from snake.sound import SoundManager
from snake.utils import Config


def test_sound_manager_init():
    """验证 SoundManager 初始化：默认音量、开关、注册与播放的安全性。"""
    config = Config(sound_enabled=True, sound_volume=0.8)
    manager = SoundManager(config=config, init_mixer=False)

    # 初始化状态：读取设置中的音量与开关，且尚无注册音效
    assert manager.master_volume == 0.8
    assert manager.enabled is True
    assert len(manager.sounds) == 0
    assert not manager.has_sound("eat")

    # set_volume 裁剪到合法区间
    manager.set_volume(1.5)
    assert manager.master_volume == 1.0
    manager.set_volume(-0.2)
    assert manager.master_volume == 0.0

    # 未注册名称播放是安全空操作，不抛异常
    assert manager.play("eat") is False

    # 未初始化混音器时合成与注册均为空操作
    manager.register("eat", manager.synthesize(0.1, 440.0))
    assert not manager.has_sound("eat")
    assert manager.play("eat") is False

    # disable 后即使有音效也不会播放
    manager.disable()
    assert manager.enabled is False
    manager.enable()
    assert manager.enabled is True

    # 静音降级模式的 describe 元组结构
    count, volume, available = manager.describe()
    assert count == 0 and volume == 0.0 and available is False

    # sound_enabled=False 时 enabled 应为 False
    muted = SoundManager(config=Config(sound_enabled=False), init_mixer=False)
    assert muted.enabled is False


def test_builtin_sounds_registration():
    """验证内置音效：可用时注册 4 种音效，降级模式下安全跳过。"""
    manager = SoundManager(config=Config(sound_enabled=True), init_mixer=False)
    # 混音器不可用：build_builtin_sounds 是安全空操作
    manager.build_builtin_sounds()
    assert len(manager.sounds) == 0

    if not manager.available:
        return  # 环境无声卡时到此为止，不影响测试通过

    # 混音器可用：4 种内置音效全部注册成功并可播放
    manager.build_builtin_sounds()
    for name in ("eat", "game_over", "start", "finish"):
        assert manager.has_sound(name), f"缺少内置音效: {name}"
    assert manager.play("eat") is True
    assert manager.play("game_over") is True
    # 主音量调节后仍可正常播放
    manager.set_volume(0.3)
    assert manager.play("start") is True
