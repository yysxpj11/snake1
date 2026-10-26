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
| 方向键 / WASD | 移动 |
| P / 空格 | 暂停 / 继续 |
| M | 返回菜单 |
| R | 结束后重开 |
| ESC | 退出 |

## 模块结构

```
snake_game/
├── snake/
│   ├── __init__.py   # 包声明与版本
│   ├── utils.py      # 常量、Config、调色板、网格工具、高分存储
│   ├── snake.py      # Direction / Segment / Snake：移动、生长、碰撞
│   ├── food.py       # FoodType / Food / FoodManager：食物生成与生命周期
│   ├── game.py       # ScoreManager / GameStats / Game：状态机与核心逻辑
│   ├── ui.py         # Screen / HUD / Button / 渲染器（依赖 pygame）
│   └── main.py       # 命令行参数、事件分发、主循环入口
├── tests/
│   └── test_snake_game.py  # pytest 测试（移动/食物/碰撞三大场景）
├── TODO.md           # 待做功能清单
└── README.md
```

## 玩法特性

- 三种食物：普通（+10）、金色（+50，限时）、加速（+20，限时加速）
- 连击系统：3 秒内连续进食获得递增加成
- 三档难度（easy/normal/hard），影响速度与得分倍率
- 穿墙 / 撞墙两种边界模式（`--wrap` 开启穿墙）
- 高分榜持久化到 `highscores.json`

## 测试

```bash
pytest tests/ -v
```
