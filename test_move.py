# -*- coding: utf-8 -*-
"""测试角色移动逻辑"""
import game_core as core

eng = core.GameEngine()
print("初始位置:", eng.players[0]["x"], eng.players[0]["y"])

# 让弓箭手一直按右键 1 秒（30 tick）
for i in range(30):
    eng.step({0: {"left": False, "right": True, "up": False, "down": False,
                  "shoot": False, "sword": False, "block": False,
                  "mx": 100.0, "my": 100.0}}, core.TICK_DT)

x0 = eng.players[0]["x"]
print("按右1秒后位置:", x0, eng.players[0]["y"])
print("移动距离:", x0 - 3 * core.TILE - 12)
assert x0 > 3 * core.TILE + 12, "角色没有向右移动！"

# 测试移动 + 跳跃
eng2 = core.GameEngine()
x_start = eng2.players[1]["x"]
for i in range(30):
    eng2.step({1: {"left": False, "right": True, "up": (i < 5), "down": False,
                   "shoot": False, "sword": False, "block": False,
                   "mx": 0.0, "my": 0.0}}, core.TICK_DT)
x1 = eng2.players[1]["x"]
print("盾卫按右+跳1秒后位置:", x1, eng2.players[1]["y"])
print("盾卫移动距离:", x1 - x_start)
assert x1 > x_start, "盾卫没有向右移动！"

# 测试是否被卡住（物理碰撞问题）
eng3 = core.GameEngine()
xs = []
for i in range(60):
    eng3.step({0: {"left": False, "right": True, "up": False, "down": False,
                   "shoot": False, "sword": False, "block": False,
                   "mx": 100.0, "my": 100.0}}, core.TICK_DT)
    xs.append(eng3.players[0]["x"])
print("2秒内x序列(前10/后10):", [round(v,1) for v in xs[:10]], [round(v,1) for v in xs[-10:]])
assert xs[-1] > xs[0], "角色卡住未移动！"

print("=== 所有移动测试通过 ===")