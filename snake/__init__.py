# -*- coding: utf-8 -*-
"""贪吃蛇游戏包。

模块划分：
- utils: 常量、配置、调色板、网格工具、高分存储
- snake: 蛇实体与移动/碰撞逻辑
- food:  食物实体与生成管理
- game:  状态机与核心逻辑
- effects: 粒子与视觉特效
- skin:   皮肤配色定义与切换管理
- highscore: 本地高分榜持久化
- sound:  音效管理（内置波形合成，无外部素材）
- ui:    渲染与控件（依赖 pygame）
- main:  程序入口
"""

__version__ = "1.0.0"
__all__ = [
    "utils", "snake", "food", "game", "effects",
    "skin", "highscore", "sound", "ui", "main",
]
