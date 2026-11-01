# -*- coding: utf-8 -*-
"""深坑刀刺阶板专项测试

T1 AI 借助刀刺阶板跨越深坑（从左岸到右岸，不掉坑、不阵亡；卡住时允许归队兜底）
T2 AI 在坑口等待时不会被刀刺扎死
T3 玩家掉坑被刀刺扎死 -> 血迹标记 + 提示语
T4 无阶板时掉坑跳不出来（被困坑底）
T5 玩家站上阶板被携带上下 -> 可撤回左岸
"""
import sys

import game_core as core

T = core.TILE
PIT_L = core.PIT_COLS[0] * T
PIT_R = (core.PIT_COLS[1] + 1) * T
PIT_FLOOR_Y = core.PIT_FLOOR_Y
FAIL = []


def check(name, cond, detail=""):
    print(("  [PASS] " if cond else "  [FAIL] ") + name + ("  " + detail if detail else ""))
    if not cond:
        FAIL.append(name)


def sentinel(eng):
    """一只远处的哨兵怪：阻止波次推进，也不干扰坑边测试。"""
    eng.monsters.clear()
    eng.wave1_spawned = True          # 关掉开局安全窗口的自动刷怪
    eng.monsters.append(core.Monster(9999, "ground", 2 * T + 16, 19 * T - core.MONSTER_H))


print("T1 AI 借板跨越深坑（左 -> 右，含归队兜底）...")
eng = core.GameEngine()
eng.ai_pid = 0
sentinel(eng)
eng.players[0]["x"] = PIT_L - 140
eng.players[0]["y"] = 19 * T
eng.players[1]["x"] = PIT_R + 160
eng.players[1]["y"] = 19 * T
crossed = False
i = 0
for i in range(60 * 45):
    eng.step({0: core.make_ai_input(0, eng, 1), 1: {}}, core.TICK_DT)
    p = eng.players[0]
    if p["x"] > PIT_R + 30 and p["y"] <= 19 * T + 2:
        crossed = True
        break
check("AI 成功跨越", crossed, "t=%.1fs x=%.0f y=%.0f" % (i / 30.0, eng.players[0]["x"], eng.players[0]["y"]))
check("跨越过程未阵亡", eng.deaths == 0, "deaths=%d" % eng.deaths)

print("T2 AI 在坑口等待不被扎死...")
eng = core.GameEngine()
sentinel(eng)
eng.players[0]["x"] = PIT_L - 30
eng.players[0]["y"] = 19 * T
eng.players[1]["x"] = PIT_R + 200
eng.players[1]["y"] = 19 * T
hp0 = eng.players[0]["hp"]
for _ in range(60 * 12):
    eng.step({0: {}, 1: {}}, core.TICK_DT)
check("静立坑口安全", eng.players[0]["hp"] >= hp0 - 1,
      "hp %.0f -> %.0f" % (hp0, eng.players[0]["hp"]))

print("T3 掉坑被刀刺扎死 & 血迹...")
eng = core.GameEngine()
sentinel(eng)
eng._spike_kill_msg = ""
p0 = eng.players[0]
p0["x"] = eng._spike_platform["x"] + core.SPIKE_PAD_W / 2
p0["y"] = PIT_FLOOR_Y
p0["vx"] = p0["vy"] = 0.0
died = False
for _ in range(int(5.0 / core.TICK_DT)):
    eng.step({0: {}, 1: {}}, core.TICK_DT)
    if p0["hp"] <= 0:
        died = True
        break
bloody = bool(eng._spike_platform["bloody"])
msg = eng._spike_kill_msg
check("刀刺扎死", died, "hp=%.0f" % p0["hp"])
check("血迹标记", bloody)
check("提示语含'扎死'", "扎死" in msg, msg)

print("T4 无阶板时掉坑跳不出来...")
eng = core.GameEngine()
sentinel(eng)
eng._spike_platform["x"] = -9999.0
p1 = eng.players[1]
p1["x"] = PIT_L + 20
p1["y"] = PIT_FLOOR_Y
p1["vx"] = p1["vy"] = 0.0
for _ in range(120):
    eng.step({1: {"up": True}}, core.TICK_DT)
trapped = p1["y"] > core.PIT_TOP_Y + 10
check("坑底跳不出", trapped, "y=%.0f" % p1["y"])

print("T5 玩家骑板上下并撤回左岸...")
eng = core.GameEngine()
sentinel(eng)
p0 = eng.players[0]
sp = eng._spike_platform
p0["x"] = sp["x"] + core.SPIKE_PAD_W / 2
p0["y"] = sp["y"]
p0["vx"] = p0["vy"] = 0.0
bottom = False
for _ in range(int(3.0 / core.TICK_DT)):
    eng.step({0: {}, 1: {}}, core.TICK_DT)
    if eng._spike_platform["y"] >= core.SPIKE_CFG["y_bot"] - 1:
        bottom = True
for _ in range(int(3.0 / core.TICK_DT)):
    eng.step({0: {"left": True}, 1: {}}, core.TICK_DT)
for _ in range(int(3.0 / core.TICK_DT)):
    eng.step({0: {}, 1: {}}, core.TICK_DT)
ok = (p0["hp"] > 0 and bottom and p0["x"] < PIT_L - 10 and abs(p0["y"] - 19 * T) < 12)
check("骑板到底", bottom)
check("安全撤回左岸", ok, "x=%.0f y=%.0f hp=%.0f" % (p0["x"], p0["y"], p0["hp"]))

print()
if FAIL:
    print("失败项：", FAIL)
    sys.exit(1)
print("深坑专项全部通过。")
