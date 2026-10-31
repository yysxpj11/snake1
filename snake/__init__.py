# -*- coding: utf-8 -*-
"""贪吃蛇游戏包。

模块划分：
- config: 全局常量与配置（窗口/得分/难度/调色板/界面布局）
- utils: 网格工具、高分存储、计时器（常量已集中到 config，此处兼容再导出）
- snake: 蛇实体与移动/碰撞逻辑
- food:  食物实体与生成管理
- game:  状态机与核心逻辑
- effects: 粒子与视觉特效
- skin:   皮肤配色定义与切换管理
- highscore: 本地高分榜持久化
- settings: 音量/难度/皮肤设置持久化
- sound:  音效管理（内置波形合成，无外部素材）
- fps:    帧率控制（锁定 60FPS、步长裁剪、帧率统计）
- render: 战场增量渲染（只重绘变化的格子）
- logmanager: 日志管理（控制台 + game.log 双输出，分级记录）
- ui:    渲染与控件（依赖 pygame）
- main:  程序入口
"""

__version__ = "1.0.0"
__all__ = [
    "config", "utils", "snake", "food", "game", "effects",
    "skin", "highscore", "settings", "sound", "fps", "render",
    "logmanager", "ui", "main",
]
