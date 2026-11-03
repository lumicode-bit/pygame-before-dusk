# -*- coding: utf-8 -*-
"""主动找 bug：随机操作压测 + 几何扫描 + 全图渲染扫描

比单元测试更"脏"：
  * 用随机输入连跑上万帧，检查不变量（角色是否卡进地形、血量溢出、集合泄漏、NaN）
  * 扫描整张地图，找出"一格高的夹缝"这类会把角色卡住的地形
  * 把相机扫过整张地图逐帧渲染，找渲染分支里的异常
  * 顺带检查引擎内部被吞掉的异常（core.log）
"""
import math
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

import game_core as core

T = core.TILE
FAIL = []
LOG = "core.log"


def check(name, cond, detail=""):
    print(("  [PASS] " if cond else "  [FAIL] ") + name + ("  " + detail if detail else ""))
    if not cond:
        FAIL.append(name)


def clear_log():
    try:
        open(LOG, "w", encoding="utf-8").close()
    except Exception:
        pass


def log_errors():
    try:
        with open(LOG, "r", encoding="utf-8", errors="ignore") as f:
            lines = [l.strip() for l in f if "异常" in l or "Traceback" in l]
        return lines
    except Exception:
        return []


# --------------------------------------------------------------------------
print("== 1. 几何扫描：找出会把角色卡住的一格高夹缝 ==")
g = core.build_static_grid()


def solid(x, y):
    if x < 0 or x >= core.MAP_W or y >= core.MAP_H:
        return True
    if y < 0:
        return False
    return g[y][x] in ("G", "R", "Q", "S", "s")


notches = []
for y in range(1, core.MAP_H - 1):
    for x in range(core.MAP_W):
        if solid(x, y):
            continue
        # 上方是实体、下方也是实体 -> 只有一格高的横向空腔，角色下半身可能钻进被夹住
        if solid(x, y - 1) and solid(x, y + 1):
            # 只有能横向走进去（左右至少一侧是空的）才算隐患
            if not solid(x - 1, y) or not solid(x + 1, y):
                notches.append((x, y))
check("不存在一格高夹缝", not notches, "发现 %d 处：%s" % (len(notches), notches[:8]))

# 出生点/交互物不能嵌在墙里
for pid, (sx, sy) in core.PLAYER_START.items():
    cx, cy = int(sx // T), int((sy - core.PLAYER_H / 2) // T)
    check("玩家%d出生点在空腔" % pid, not solid(cx, cy), "(%d,%d)" % (cx, cy))
for cp in core.CHECKPOINT_COLS:
    # 检查点必须站在某一层地表上，且身体所在格是空的
    surf = next((y for y in range(core.MAP_H) if solid(cp, y)), None)
    check("检查点%d落点合法" % cp, surf is not None and not solid(cp, surf - 1),
          "surface row=%s" % surf)
for ch in core.CHEST_CFG:
    # 箱子按自身层 cy 落在地表上，身体所在格（上一行）必须是空
    row = ch.get("cy", 19)
    check("补给箱%s落点为空" % ch["id"], solid(ch["cx"], row) and not solid(ch["cx"], row - 1),
          "row=%d" % row)

# --------------------------------------------------------------------------
print("== 2. 随机操作压测 12000 帧 ==")
clear_log()
random.seed(20261021)
eng = core.GameEngine()
eng.ai_pid = None
maxx = 0
bad = []


def rnd_input():
    r = random.random()
    d = {
        "left": r < 0.35,
        "right": 0.35 <= r < 0.75,
        "up": random.random() < 0.18,
        "dash": random.random() < 0.03,
        "shoot": random.random() < 0.45,
        "sword": random.random() < 0.4,
        "block": random.random() < 0.15,
        "interact": random.random() < 0.05,
        "mx": random.uniform(0, core.WORLD_W),
        "my": random.uniform(0, core.WORLD_H),
    }
    return d


for i in range(12000):
    # 这一段测的是"地形/移动/异常"，不是生命系统：随机乱按会频繁阵亡，
    # 命耗尽会触发失败冻结，就测不到远处的推进了。这里给无限命。
    eng.lives = 999
    eng.fail = False
    eng.step({0: rnd_input(), 1: rnd_input()}, core.TICK_DT)
    for pid, p in eng.players.items():
        x, y = p["x"], p["y"]
        maxx = max(maxx, x)
        if not (math.isfinite(x) and math.isfinite(y)):
            bad.append(("nan", i, pid, x, y))
        if p["hp"] > p["maxhp"] + 0.01 or p["hp"] < -0.01:
            bad.append(("hp", i, pid, p["hp"]))
        if y < -400 or y > core.WORLD_H + 400:
            bad.append(("y", i, pid, y))
        # 身体中心不能留在实体格里（挂藤蔓时允许贴到岩石，松手会做脱困）
        cx, cy = int(x // T), int((y - core.PLAYER_H / 2) // T)
        if eng._solid_at(cx, cy) and p.get("vine", -1) < 0:
            bad.append(("inside", i, pid, round(x), round(y)))
    if len(eng.arrows) > 200 or len(eng.fireballs) > 120 or len(eng.monsters) > 60:
        bad.append(("leak", i, len(eng.arrows), len(eng.fireballs), len(eng.monsters)))
    if bad:
        break

check("12000 帧无异常", not bad, str(bad[:2]))
check("引擎内部无异常日志", not log_errors(), str(log_errors()[:2]))
# 地图加了断桥/藤蔓/塔楼后随机游走更绕，阈值设为能证明"离开出生点并推进了相当距离"
check("随机操作也能推进一段距离", maxx > 700, "最远 x=%.0f" % maxx)
check("怪物数量合理", len(eng.monsters) <= 60, str(len(eng.monsters)))
check("火球不会泄漏", len(eng.fireballs) <= 120, str(len(eng.fireballs)))
check("尸体不会无限增长", len(eng.corpses) <= 10, str(len(eng.corpses)))

# --------------------------------------------------------------------------
print("== 3. 全地图渲染扫描 ==")
clear_log()
import main as M

app = M.App()
app.dt = 1 / 60.0
app.start_single(0)
app._apply_scene("GAME")
app.post.fade = 0.0
eng = M.engine
eng.monsters.clear()
err = None
fx_pos = 0
frames = 0
for wx in range(0, core.WORLD_W, 160):
    try:
        app.cam.snap(wx + 400, 560, (core.WORLD_W, core.WORLD_H))
        app.scene_game([], type("K", (), {"__getitem__": lambda self, k: False})(), (640, 360))
        frames += 1
    except Exception as e:
        err = (wx, repr(e))
        break
check("相机扫过全图不崩", err is None, str(err))
check("渲染了足够多的位置", frames >= 28, str(frames))
check("渲染分支无异常日志", not log_errors(), str(log_errors()[:2]))

# --------------------------------------------------------------------------
print("== 4. 关键流程不变量 ==")
e = core.GameEngine()
e.portal_active = True
e.players[0]["x"] = core.PORTAL_RECT[0] + 60
e.players[0]["y"] = 15 * T
e.players[1]["x"] = core.PORTAL_RECT[0] + 100
e.players[1]["y"] = 15 * T
for _ in range(60):
    e.step({}, core.TICK_DT)
check("两人进门即通关", e.win)

e = core.GameEngine()
e.monsters.clear()
e.wave = 2
e.wave2_spawned = True
e.wave1_spawned = True          # 模拟第一波已过
e.players[0]["x"] = core.BOSS_TRIGGER_X + 30
e.players[0]["y"] = 19 * T
e.players[1]["x"] = core.BOSS_TRIGGER_X - 70
e.players[1]["y"] = 19 * T
for _ in range(4):
    e.step({}, core.TICK_DT)
# Boss 现在走裂隙出场，先把计时推满
for _r in e.rifts:
    _r["t"] = _r["delay"]
e.step({}, core.TICK_DT)
for _m in e.monsters:
    if getattr(_m, "state", "") == "spawn":
        _m.state_t = 0.0
e.step({}, core.TICK_DT)
boss = next((m for m in e.monsters if m.kind in ("boss", "tree")), None)
check("Boss 存在时传送门保持封印", boss is not None and not e.portal_active)
if boss:
    # 玩家阵亡 -> 检查点复活，Boss 血量不能被重置
    # （团灭惩罚会让 Boss 回 8%，所以只要求"没被清空/回满"，不要求分毫不差）
    boss.hp = 20
    e.players[0]["hp"] = 0
    e.step({}, core.TICK_DT)
    e.step({}, core.TICK_DT)
    boss2 = next((m for m in e.monsters if m.kind in ("boss", "tree")), None)
    _cap = 20 + boss.maxhp * core.BOSS_WIPE_HEAL + 0.01
    check("复活不清空 Boss 进度", boss2 is not None and 20 <= boss2.hp <= _cap,
          "hp=%s" % (boss2.hp if boss2 else "None"))
    check("复活时清空残留火球", len(e.fireballs) == 0, str(len(e.fireballs)))

# 怪物掉坑自救：否则这一波永远清不完（软锁）
e = core.GameEngine()
e.monsters.clear()
mm = core.Monster(77, "ground", 37 * T, 19 * T - core.MONSTER_H)
e.monsters.append(mm)
e.players[0]["x"] = 20 * T
e.players[0]["y"] = 19 * T
for _ in range(150):
    e.step({}, core.TICK_DT)
check("掉坑的怪会被拉回地面", mm.y <= 19 * T + 1 and mm.x < 37 * T,
      "x=%.0f y=%.0f" % (mm.x, mm.y))

# 重开一局必须把 Boss/火球/波次全部复位
e.reset("重开")
check("重开后回到第一波", e.wave == 1 and not e.boss_spawned)
check("重开后火球清空", len(e.fireballs) == 0)
check("重开后传送门关闭", not e.portal_active)

# --------------------------------------------------------------------------
print()
if FAIL:
    print("失败项：", FAIL)
    sys.exit(1)
print("自检通过。")
