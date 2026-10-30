# 贪吃蛇 Pygame 版

基于 Python + Pygame 的模块化贪吃蛇游戏。

## 运行

```bash
pip install pygame pytest
cd snake_game
python -m snake.main            # 默认 800x600
python -m snake.main --difficulty hard --cell 24
python -m snake.main --width 960 --height 640
```

## 操作

| 按键 | 功能 |
|------|------|
| 方向键 / W A D | 移动（S 键在游戏内用于切换皮肤） |
| P | 暂停 / 继续 |
| S | 游戏中切换皮肤（经典绿 / 霓虹蓝 / 烈焰橙） |
| M | 返回菜单 |
| R | 结束后重开 |
| ESC | 菜单中退出程序，游戏中返回开始菜单 |
| 菜单 ↑/↓ + 回车 | 选择并确认菜单项 |
| 菜单 ←/→ | 切换难度 / 皮肤（需选中对应菜单项） |
| 菜单长按 C | 清除最高分记录 |

## 模块结构

```
snake_game/
├── snake/
│   ├── __init__.py   # 包声明与版本
│   ├── utils.py      # 常量、Config、调色板、网格工具
│   ├── snake.py      # Direction / Segment / Snake：移动、生长、碰撞
│   ├── food.py       # FoodType / Food / FoodManager：食物生成与生命周期
│   ├── game.py       # ScoreManager / GameStats / Game：状态机与核心逻辑
│   ├── effects.py    # 粒子特效、浮动文字、屏幕震动
│   ├── skin.py       # Skin / SkinManager：三套皮肤配色与切换
│   ├── sound.py      # SoundManager：内置波形合成音效
│   ├── highscore.py  # HighScoreManager：highscore.json 持久化
│   ├── ui.py         # Screen / HUD / Menu / 渲染器（依赖 pygame）
│   └── main.py       # 命令行参数、事件分发、主循环入口
├── tests/            # pytest 用例（核心玩法 / 菜单 / 难度 / 暂停 / 音效 / 皮肤 / 高分）
├── TODO.md           # 待做功能清单
└── README.md
```

## 玩法特性

- 三种食物：普通（+10）、金色（+50，限时）、加速（+20，限时加速）
- 连击系统：3 秒内连续进食获得递增加成
- 三档难度（easy/normal/hard），影响速度与得分倍率
- 穿墙 / 撞墙两种边界模式（`--wrap` 开启穿墙）
- 开始菜单 + 暂停遮罩 + 结束画面完整状态机
- 三套皮肤（经典绿 / 霓虹蓝 / 烈焰橙），菜单与游戏内均可切换
- 音效全部由代码合成（无外部素材），支持 `--no-sound` 关闭
- 本地高分榜：成绩自动保存到 `highscore.json`，破纪录显示"新纪录！已保存"

## 测试

```bash
pytest tests/ -v
```
