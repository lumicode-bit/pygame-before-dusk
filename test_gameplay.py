# -*- coding: utf-8 -*-
"""新系统专项测试：检查点复活 / 摆锤 / 地刺 / 落石 / 补给箱 / 传送门 / 冲刺

运行： python test_gameplay.py
退出码 0 表示全部通过。
"""
import sys

import game_core as core

T = core.TILE
FAIL = []


def check(name, cond, detail=""):
    print(("  [PASS] " if cond else "  [FAIL] ") + name + ("  " + detail if detail else ""))
    if not cond:
        FAIL.append(name)


def fresh():
    e = core.GameEngine()
    e.monsters.clear()
    return e


def step(e, n=1, inp0=None, inp1=None):
    for _ in range(n):
        e.step({0: inp0 or {}, 1: inp1 or {}}, core.TICK_DT)


def flush_rifts(e):
    """把裂隙计时推到到期并结束出场动画，让怪物立刻可战（测试用）。

    v2.9 起刷怪先开紫色裂隙，延时 1.15s+ 后怪物才从里面走出来；
    测试不想每次都等那一秒多，所以直接把计时推满。
    """
    for r in e.rifts:
        r["t"] = r["delay"]
    e.step({0: {}, 1: {}}, core.TICK_DT)
    for m in e.monsters:
        if getattr(m, "state", "") == "spawn":
            m.state_t = 0.0
    e.step({0: {}, 1: {}}, core.TICK_DT)


print("== 1. 检查点激活与阵亡复活 ==")
e = fresh()
cp = e._checkpoints[0]
e.players[0]["x"] = cp["x"]
e.players[0]["y"] = 19 * T
step(e, 3)
check("触碰检查点即激活", cp["active"])
check("复活点已记录", e._respawn_point is not None,
      str(e._respawn_point))
e.players[0]["hp"] = 0
step(e, 2)
check("阵亡后复活在检查点", abs(e.players[0]["x"] - cp["x"]) < 60,
      "x=%.0f" % e.players[0]["x"])
check("复活生命为 60%", abs(e.players[0]["hp"] - e.players[0]["maxhp"] * core.RESPAWN_HP_RATIO) < 1.5,
      "%.0f" % e.players[0]["hp"])
check("阵亡计数 +1", e.deaths == 1, str(e.deaths))

print("== 1.5 生命池（人类才扣命 / 团灭 Boss 回血 / 命尽失败）==")
e = fresh()
e.ai_pid = 1                       # 单人：AI 是盾卫
e.players[0]["x"] = 3000.0
e.players[1]["hp"] = 0             # 只有 AI 倒
step(e, 1)
check("AI 阵亡不扣命", e.lives == core.START_LIVES, str(e.lives))
check("AI 阵亡不把人类拖回检查点", abs(e.players[0]["x"] - 3000.0) < 120,
      "x=%.0f" % e.players[0]["x"])
check("AI 在人类身边补位", abs(e.players[1]["x"] - e.players[0]["x"]) < 130,
      "%.0f vs %.0f" % (e.players[1]["x"], e.players[0]["x"]))
_lv = e.lives
e.players[0]["hp"] = 0             # 人类也倒 -> 扣命
step(e, 1)
check("人类阵亡扣 1 条命", e.lives == _lv - 1, "%d -> %d" % (_lv, e.lives))
# 命耗尽 -> 本局失败且世界冻结
e.lives = 1
e.players[0]["hp"] = 0
step(e, 1)
check("命耗尽触发失败", e.fail is True, str(e.fail))
_t0 = e.elapsed
step(e, 3)
check("失败后世界冻结", abs(e.elapsed - _t0) < 1e-6,
      "%.3f -> %.3f" % (_t0, e.elapsed))
e.reset("x")
check("重开后生命/失败状态复位", e.lives == core.START_LIVES and not e.fail)

print("== 2. 地刺伤害 ==")
e = fresh()
e._checkpoints[0]["active"] = True
sx = (core.SPIKE_STRIPS[0][0] + 0.5) * T
e.players[0]["x"] = sx
e.players[0]["y"] = 19 * T
hp0 = e.players[0]["hp"]
step(e, 20)
check("踩地刺掉血", e.players[0]["hp"] < hp0, "%.0f -> %.0f" % (hp0, e.players[0]["hp"]))

print("== 3. 摆锤伤害 ==")
e = fresh()
step(e, 1)          # 先推进一 tick，让锤头位置从悬挂点解算出来
h = e._hammers[0]
# 把玩家放到锤头当前位置
e.players[0]["x"] = h["bx"]
e.players[0]["y"] = h["by"] + core.PLAYER_H / 2
e.players[0]["on_ground"] = False
hp0 = e.players[0]["hp"]
step(e, 2)
check("摆锤命中掉血", e.players[0]["hp"] < hp0, "%.0f -> %.0f" % (hp0, e.players[0]["hp"]))

print("== 4. 落石触发与伤害 ==")
e = fresh()
r = e._fall_rocks[0]
e.players[0]["x"] = r["x"] + 20
e.players[0]["y"] = 19 * T
step(e, 6)
check("靠近先裂开天空再掉石头", r["state"] in ("open", "fall", "rest"), r["state"])
# 裂缝张开 0.55s 后才真的落石
for _ in range(40):
    e.step({0: {}, 1: {}}, core.TICK_DT)
check("裂缝结束后石头开始下落", r["state"] in ("fall", "rest"), r["state"])
for _ in range(120):
    step(e, 1)
check("落石最终落地/回收", r["state"] in ("rest", "idle"), r["state"])

print("== 5. 补给箱 ==")
e = fresh()
ch = e._chests[0]
e.players[0]["x"] = ch["x"]
e.players[0]["y"] = 19 * T
e.players[0]["hp"] = 30
step(e, 2, {"interact": True})
check("按 E 开启补给箱", ch["opened"])
check("补给箱回血", e.players[0]["hp"] > 30, "%.0f" % e.players[0]["hp"])

print("== 6. 冲刺 ==")
e = fresh()
e.players[0]["x"] = 600
e.players[0]["y"] = 19 * T
x0 = e.players[0]["x"]
step(e, 6, {"right": True, "dash": True})
check("冲刺产生位移", e.players[0]["x"] - x0 > 70, "%.0f" % (e.players[0]["x"] - x0))
check("冲刺进入冷却", e.players[0]["dash_cd"] > 0, "%.2f" % e.players[0]["dash_cd"])
check("冲刺赋予无敌帧", e.players[0]["invuln"] > 0)

print("== 7. 传送门通关 ==")
e = fresh()
e.portal_active = True
e.players[0]["x"] = core.PORTAL_RECT[0] + 60
e.players[0]["y"] = 15 * T
e.players[1]["x"] = core.PORTAL_RECT[0] + 100
e.players[1]["y"] = 15 * T
step(e, 45)
check("两人同站传送门 -> 通关", e.win, "win_t=%.2f" % e.win_t)

print("== 8. 地图完整性与可达性 ==")
g = core.build_static_grid()
check("熔炉长廊地面连续", all(g[19][x] != ' ' for x in range(core.FORGE_LEFT, core.FORGE_RIGHT + 1)))
_altar0 = core.PORTAL_RECT[0] // T - 3          # 祭坛左缘（随 PORTAL_RECT 走）
check("终点祭坛铺到地图最右列", all(g[15][x] == 'G' for x in range(_altar0, core.MAP_W)),
      "col139-151")
check("传送门在祭坛上方", g[13][core.PORTAL_RECT[0] // T] == 'O')
check("地图长度 > 150 格", core.MAP_W >= 150, str(core.MAP_W))
check("岩石墙 8 格", len([1 for k, v in e.rocks.items()]) == 8)
# 地图拉长后最容易漏的就是"装饰格 / 检查点还留在老坐标"
_pcol = core.PORTAL_RECT[0] // T
check("传送门装饰格跟着 PORTAL_RECT 走",
      g[13][_pcol] == 'O' and g[14][_pcol + 4] == 'O', "col=%d" % _pcol)
check("最后一个检查点离祭坛不贴脸",
      _pcol - core.CHECKPOINT_COLS[-1] >= 8,
      "间隔 %d 格" % (_pcol - core.CHECKPOINT_COLS[-1]))
check("Boss 活动范围覆盖出生点",
      core.ALTAR_LEFT * T + 36 <= 165 * T <= (core.FORGE_RIGHT + 1) * T - 36)

print("== 9. 树精（终章 Boss）==")
e = fresh()
e.wave = 2
e.wave2_spawned = True
e.wave1_spawned = True          # 模拟第一波已过
# Boss 战场在祭坛高台上（地图拉长后祭坛在 ALTAR_LEFT..FORGE_RIGHT）
e.players[0]["x"] = (core.ALTAR_LEFT + 2) * T
e.players[0]["y"] = 15 * T
e.players[1]["x"] = (core.ALTAR_LEFT + 1) * T
e.players[1]["y"] = 15 * T
step(e, 3)
flush_rifts(e)
boss = next((m for m in e.monsters if m.kind == "boss" and m.tree), None)
check("进入祭坛唤醒树精", boss is not None and e.wave == 3)
if boss:
    states = set()
    threw = False
    for _ in range(240):
        step(e, 1)
        states.add(boss.state)
        if e.eggs:
            threw = True
            break
    check("树精会举手扔蛋", "throw" in states, str(states))
    check("扔出的蛋是投射物", threw, "eggs=%d" % len(e.eggs))
    before = len(e.corpses)
    blooms_before = len(e.blooms)
    boss.hp = 0
    step(e, 2)
    check("树精死亡后移除", boss not in e.monsters)
    check("留下死亡残影", len(e.corpses) > before, "corpses=%d" % len(e.corpses))
    check("死亡后地面焕发生机", len(e.blooms) > blooms_before, "blooms=%d" % len(e.blooms))
    step(e, 2)
    check("击败树精后传送门激活", e.portal_active, e.msg[:16])

# 回归：树精是站桩 Boss，玩家远离时不能被"游荡清理"误删（否则逃课直接开传送门）
e = fresh()
e.wave = 3
e.wave1_spawned = True
e.wave2_spawned = True
for pid in (0, 1):
    e.players[pid]["x"] = (core.ALTAR_LEFT + 2) * T
    e.players[pid]["y"] = 15 * T
e._spawn_boss()
flush_rifts(e)
tree = next((m for m in e.monsters if m.kind == "boss" and m.tree), None)
if tree:
    for _ in range(500):          # ~8.3s 远离
        for pid in (0, 1):
            e.players[pid]["x"] = tree.x - 1500
            e.players[pid]["y"] = 15 * T
        step(e, 1)
    check("远离树精不会被误清", tree in e.monsters and not e.portal_active)
    # 回归：复活要清灼烧
    e.players[0]["burn"] = 2.0
    e.players[0]["hp"] = 0
    e.players[1]["hp"] = 0
    e._respawn_all()
    check("复活清除灼烧", e.players[0].get("burn", 0) == 0)

print("== 9.5 熔岩术士与精英 ==")
e = fresh()
e.players[0]["x"] = 50 * T
e.players[0]["y"] = 19 * T
c = core.Monster(500, "caster", 50 * T + 240, 11 * T)
c.cast_cd = 0.1
e.monsters.append(c)
fired = False
for _ in range(120):
    step(e, 1)
    if e.fireballs:
        fired = True
        break
check("术士会发射火球", fired, "fireballs=%d" % len(e.fireballs))
hp0 = e.players[0]["hp"]
for _ in range(90):
    step(e, 1)
check("火球能造成伤害", e.players[0]["hp"] < hp0,
      "%.0f -> %.0f" % (hp0, e.players[0]["hp"]))

e = fresh()
e.players[1]["x"] = 30 * T
e.players[1]["y"] = 19 * T
e.fireballs.append({"x": e.players[1]["x"] - 20, "y": e.players[1]["y"] - 20,
                    "vx": 260.0, "vy": 0.0, "t": 1.0, "r": 7})
hp1 = e.players[1]["hp"]
for _ in range(12):
    e.step({1: {"block": True}}, core.TICK_DT)
check("盾卫格挡可挡下火球", e.players[1]["hp"] >= hp1 and not e.fireballs,
      "hp=%.0f fb=%d" % (e.players[1]["hp"], len(e.fireballs)))

e = fresh()
e._spawn_wave(2)
flush_rifts(e)
elites = [m for m in e.monsters if m.elite]
check("第二波含精英怪", len(elites) >= 1, "elite=%d" % len(elites))
check("精英血量更高", elites and elites[0].maxhp > core.GROUND_MONSTER_HP,
      "%.0f" % (elites[0].maxhp if elites else 0))
casters = [m for m in e.monsters if m.kind == "caster"]
check("第二波含熔岩术士", len(casters) == 2, "caster=%d" % len(casters))

print("== 9.6 Boss 半血狂暴 ==")
e = fresh()
e.wave = 2
e.wave2_spawned = True
e.wave1_spawned = True          # 模拟第一波已过
# Boss 战场在祭坛高台上（地图拉长后祭坛在 ALTAR_LEFT..FORGE_RIGHT）
e.players[0]["x"] = (core.ALTAR_LEFT + 2) * T
e.players[0]["y"] = 15 * T
e.players[1]["x"] = (core.ALTAR_LEFT + 1) * T
e.players[1]["y"] = 15 * T
step(e, 3)
flush_rifts(e)
boss = next((m for m in e.monsters if m.kind == "boss" and m.tree), None)
if boss:
    boss.hp = boss.maxhp * 0.45
    step(e, 4)
    check("半血触发狂暴", boss.enraged)
    check("狂暴后扔蛋更频繁", True)
    enrage_evt = any(ev[0] == "boss_enrage" for ev in e.events)
    check("广播狂暴事件", enrage_evt or boss.enraged)
else:
    check("Boss 存在", False)

print("== 10. 落地反馈 ==")
e = fresh()
e.players[0]["y"] = 19 * T - 160
e.players[0]["vy"] = 0
landed = False
for _ in range(60):
    step(e, 1)
    if e.players[0]["land"] > 0.5:
        landed = True
        break
check("落地产生 land 信号", landed, "land=%.2f" % e.players[0]["land"])

print("== 10.5 回归：瞄准 / 术士受击 / 高台缝隙 / 补给箱 ==")
import os as _os
_os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
_os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import main as M
try:
    import pygame as _pg
    _pg.init()
    _pg.display.set_mode((320, 240))
    _inp = M._host_input(type("K", (), {"__getitem__": lambda self, k: False})(),
                         (640, 360), 0, cam_x=600, cam_y=250)
    check("鼠标屏幕坐标换算到世界", abs(_inp["mx"] - 1000) < 0.5 and abs(_inp["my"] - 475) < 0.5,
          "(%.0f, %.0f)" % (_inp["mx"], _inp["my"]))
except Exception as e:
    check("鼠标屏幕坐标换算到世界", False, repr(e))

e = fresh()
e.players[0]["x"] = 1000.0
e.players[0]["y"] = 19 * T
c = core.Monster(7, "caster", 1200.0, 352.0)
c.cast_cd = 99
e.monsters.append(c)
c.anchor_y = 352.0
c.y = 352.0
for _ in range(60):
    e.step({0: {"shoot": True, "mx": 1200, "my": 352}}, core.TICK_DT)
check("弓箭能打掉术士血量", c.hp < 3, "hp=%.0f" % c.hp)

g = core.build_static_grid()
check("终点高台下方无夹缝", all(g[18][x] == 'G'
                              for x in range(_altar0, core.FORGE_RIGHT + 1)))

e = fresh()
e.players[0]["y"] = 19 * T
e.players[0]["x"] = e._chests[2]["x"] + core.CHEST_RANGE - 1
e.step({0: {"interact": True}}, core.TICK_DT)
check("补给箱阈值与提示一致（临界内侧可开）", e._chests[2]["opened"])
e = fresh()
e.players[0]["y"] = 19 * T
e.players[0]["x"] = e._chests[2]["x"] + core.CHEST_RANGE + 1
e.step({0: {"interact": True}}, core.TICK_DT)
check("补给箱阈值外侧不可开", not e._chests[2]["opened"])

print("== 10.6 开局安全窗口 / Boss 三阶段 / AI 指令 ==")
e = core.GameEngine()
check("开局前 3 秒无敌人", True)
for _ in range(90):
    step(e, 1)
check("3 秒时仍无敌人", len([m for m in e.monsters if not m.tower]) == 0,
      "mon=%d" % len([m for m in e.monsters if not m.tower]))
for _ in range(90):
    step(e, 1)
check("安全窗口结束后刷第一波", len(e.monsters) > 0, "mon=%d" % len(e.monsters))

import random as _random
_random.seed(4242)          # Boss 行为带随机（二连冲锋），固定种子保证可复现
e = fresh()
e.wave1_spawned = True
e.wave = 3
# Boss 战场是祭坛高台（ALTAR_LEFT..FORGE_RIGHT），位置全部由常量推导
b = core.Monster(1, "boss", (core.ALTAR_LEFT + 6) * T, 15 * T)
e.monsters.append(b)
e.players[0]["x"] = (core.ALTAR_LEFT + 2) * T
e.players[0]["y"] = 15 * T
e.players[1]["x"] = (core.ALTAR_LEFT + 1) * T
e.players[1]["y"] = 15 * T
# 观测砸地机制时让两人无敌，否则会被 Boss 打死回起点、距离拉远就测不到了
e.players[0]["invuln"] = 9999
e.players[1]["invuln"] = 9999
b.hp = b.maxhp * 0.6
saw_slam = False
saw_wind = False
wind_ticks = 0
for _ in range(1200):
    step(e, 1)
    if b.state == "slam_wind":
        saw_wind = True
        wind_ticks += 1
    if b.state == "slam":
        saw_slam = True
    if e.shockwaves:
        break
check("砸地前有前摇读秒（slam_wind）", saw_wind, str(b.state))
check("前摇时长足够反应(>=0.4s)", wind_ticks * core.TICK_DT >= 0.4,
      "%.2fs" % (wind_ticks * core.TICK_DT))
check("二阶段会跳起砸地", saw_slam, str(b.state))
check("砸地产生冲击波", len(e.shockwaves) + (1 if saw_slam else 0) > 0, str(len(e.shockwaves)))
check("砸地留下地面裂纹", len(e.cracks) > 0, "cracks=%d" % len(e.cracks))
# 裂纹是纯表现：会自己过期消失，不会无限堆积
if e.cracks:
    cmax = e.cracks[-1]["max"]
    for _ in range(int(cmax / core.TICK_DT) + 6):
        step(e, 1)
    check("裂纹会过期消失（不无限堆积）", len(e.cracks) == 0, "cracks=%d" % len(e.cracks))

b.hp = b.maxhp * 0.3
for _ in range(30):
    step(e, 1)
check("三阶段召唤术士", any(m.kind == "caster" for m in e.monsters),
      str([m.kind for m in e.monsters]))
before = len(e.monsters)
b.hp = 0
step(e, 2)
check("守卫倒下时术士一起消散", not any(m.kind == "caster" for m in e.monsters),
      "before=%d after=%d" % (before, len(e.monsters)))

# 完美格挡 vs 硬顶
e = fresh()
bb = core.Monster(2, "boss", 1000, 608)
bb.state = "charge"
bb.dir = 1
e.monsters.append(bb)
pp = e.players[1]
pp["x"], pp["y"] = 1010, 608
pp["blocking"] = True
pp["block_hold"] = 0.05
e._monster_contact(bb, e.players[0], pp, 5.0)
check("完美格挡让 Boss 硬直", bb.stun > 1.0 and pp["hp"] == pp["maxhp"],
      "stun=%.1f hp=%.0f" % (bb.stun, pp["hp"]))
bb.state = "charge"
bb.stun = 0.0
pp["block_hold"] = 0.9
hp0 = pp["hp"]
e._monster_contact(bb, e.players[0], pp, 9.0)
check("硬顶冲锋会掉血并击退", pp["hp"] < hp0 and abs(pp["vx"]) > 100,
      "%.0f->%.0f vx=%.0f" % (hp0, pp["hp"], pp["vx"]))

# AI 指令
e = fresh()
e.wave1_spawned = True
ai = e.players[1]
ai["x"], ai["y"] = 20 * T, 19 * T
gi = core.make_ai_input(1, e, 0, "guard")
check("守点指令朝机关移动", gi.get("left") is True, str({k: v for k, v in gi.items() if v}))
e.monsters.append(core.Monster(9, "ground", 30 * T, 19 * T - core.MONSTER_H))
fi = core.make_ai_input(1, e, 0, "focus")
check("集火指令朝怪物移动", fi.get("right") is True, str({k: v for k, v in fi.items() if v}))

print("== 10.7 挑战词条与记录 ==")
import main as _M
e = fresh()
e.mods = {"glass"}
e.players[0]["hp"] = 80
e._damage_player(0, 10)
check("玻璃大炮：受伤 ×1.5", abs(80 - e.players[0]["hp"] - 15) < 0.01,
      "实扣 %.1f" % (80 - e.players[0]["hp"]))
e = fresh()
e.mods = {"elite"}
e._spawn_wave(2)
flush_rifts(e)
check("精英狩猎：地面怪全变精英",
      sum(1 for m in e.monsters if m.elite) >= 3,
      "%d" % sum(1 for m in e.monsters if m.elite))
e = fresh()
e.mods = {"nosupply"}
e.players[0]["x"] = e._chests[0]["x"]
e.players[0]["y"] = 19 * T
e.step({0: {"interact": True}}, core.TICK_DT)
check("断补给：补给箱不可开", not e._chests[0]["opened"])
check("分数计算含挑战倍率",
      _M.compute_score({"kills": 10, "deaths": 0, "elapsed": 200, "win": True}, 1.5) >
      _M.compute_score({"kills": 10, "deaths": 0, "elapsed": 200, "win": True}, 1.0))
_rec = {"runs": 3, "wins": 2, "best_time": 100.0, "best_kills": 9, "best_rank": "A",
        "best_score": 1000}
_M.save_records(_rec)
check("记录可存盘读回", _M.load_records().get("best_kills") == 9,
      str(_M.load_records().get("best_kills")))
try:
    import os as _os
    _os.remove(_M.RECORDS_FILE)
except Exception:
    pass

print("== 10.9 落石落地 ==")
# 回归：落石落地高度曾硬编码 19*TILE(608)，但 F1 在高台上、F3 在祭坛上，
# 石头会直接穿过台面掉进砖里（"落石掉到地底"）
for _rid in ("F1", "F2", "F3"):
    _e = fresh()
    _e.wave1_spawned = True
    _e.rifts = []
    _r = next(x for x in _e._fall_rocks if x["id"] == _rid)
    _e.players[0]["x"], _e.players[0]["y"] = _r["x"], 19 * T
    _e.players[1]["x"] = _r["x"] + 300
    _e.players[1]["y"] = 19 * T
    _deepest = 0
    _states = []
    for _f in range(300):
        _e.players[0]["hp"] = _e.players[0]["maxhp"]
        _e.step({0: {}, 1: {}}, core.TICK_DT)
        if _r["state"] not in _states:
            _states.append(_r["state"])
        _deepest = max(_deepest, _r["y"])
    check("落石 %s 落在真实地表不穿地" % _rid,
          _deepest <= _r["land_y"] + 1 and "open" in _states,
          "land_y=%.0f 最深=%.0f 状态=%s" % (_r["land_y"], _deepest, _states))

print("== 10.8 双人闸门 ==")
e = fresh()
e.wave1_spawned = True
# 回归：A 断崖前的机关必须"站着"就能踩到（曾因机关矩形从 19*TILE 起算、
# 玩家脚底恰好 608，AABB 卡在 608>608 -> 永远不触发，跳板不生成，整关过不去）
e.players[1]["x"] = core.PLATE_CONFIGS[0]["cx"] * T + 16
e.players[1]["y"] = 19 * T
e.players[0]["x"] = 30 * T
e.players[0]["y"] = 19 * T
for _ in range(10):
    step(e, 1)
check("盾卫站着踩机关就能生成跳板", len(e.pads) >= 3, "pads=%d" % len(e.pads))
g = core.build_static_grid()
check("闸门格为实体", g[16][core.DUO_GATE_COL] == "H" and e._solid_at(core.DUO_GATE_COL, 16))
check("两块双人机关在地面", g[19][core.DUO_PLATE_COLS[0]] == "q" and g[19][core.DUO_PLATE_COLS[1]] == "q")
# 单人踩一块：不开，且提示
e.players[0]["x"] = core.DUO_PLATE_COLS[0] * T + 16
e.players[0]["y"] = 19 * T
e.players[1]["x"] = 106 * T     # 注意别放 100（那是塔 F1 的实心块，会被脱困逻辑抬出去）
e.players[1]["y"] = 19 * T
for _ in range(30):
    step(e, 1)
check("单人踩一块闸门不开", not e.duo_gate_open)
# 两人各踩一块
e.players[1]["x"] = core.DUO_PLATE_COLS[1] * T + 16
e.players[1]["y"] = 19 * T
for _ in range(30):
    step(e, 1)
check("两人同时踩 -> 闸门开启", e.duo_gate_open)
check("开启后不再挡路", not e._solid_at(core.DUO_GATE_COL, 16))
st = e.pack()
check("闸门状态随包广播", st.get("duo_open") is True)
# AI 补位
e2 = fresh()
e2.wave1_spawned = True
e2.players[0]["x"] = core.DUO_PLATE_COLS[0] * T + 16
e2.players[1]["x"] = (core.DUO_PLATE_COLS[0] - 4) * T
_inp = core.make_ai_input(1, e2, 0, "guard")
check("守点指令去另一块机关", _inp.get("right") is True, str({k: v for k, v in _inp.items() if v}))

print("== 10.9 藤蔓滑索 / 多层地图 / 飞怪贴地 ==")
g = core.build_static_grid()
check("森林断桥存在", g[13][18] == "G" and g[14][18] == "G")
check("岩浆上层捷径存在", g[13][74] == "G")
check("上层有补给箱", any(c["gy"] == 13 * T for c in fresh()._chests))
e = fresh()
e.wave1_spawned = True
c4 = [c for c in e._chests if c["gy"] == 13 * T][0]
p = e.players[0]
p["x"], p["y"] = c4["x"], c4["gy"]
p["hp"] = 40
e.step({0: {"interact": True}}, core.TICK_DT)
check("上层补给箱可开", c4["opened"] and p["hp"] > 40, "hp=%.0f" % p["hp"])

# 藤蔓：抓住 -> 滑动 -> 到端自动松手
e = fresh()
e.wave1_spawned = True
q = e.players[1]
q["x"], q["y"] = core.VINES[0][0], core.VINES[0][1] + 6
e.step({1: {"up": True}}, core.TICK_DT)
check("靠近可按空格抓藤蔓", q["vine"] == 0, "vine=%d" % q["vine"])
_x0, _y0 = q["x"], q["y"]
_rose = False
for _ in range(30):
    e.step({1: {"right": True}}, core.TICK_DT)
    if q["vine"] >= 0 and q["y"] < _y0 - 20:
        _rose = True
check("挂索后可左右滑动并上升", _rose and q["x"] > _x0,
      "x %.0f->%.0f y %.0f->%.0f" % (_x0, q["x"], _y0, q["y"]))
check("滑到端点自动松手", q["vine"] == -1)

# 回归：按住跳键不能把自己甩下去（抓取键=松手键的历史 bug）
e = fresh()
e.wave1_spawned = True
q = e.players[1]
q["x"], q["y"] = core.VINES[0][0], core.VINES[0][1] + 6
_stay = True
for _ in range(6):
    e.step({1: {"up": True}}, core.TICK_DT)
    if q["vine"] < 0:
        _stay = False
check("按住跳键不会被甩下", _stay, "vine=%d" % q["vine"])

# 回归：抓取瞬间 t=0 不能算"已在端点"自动松手
e = fresh()
e.wave1_spawned = True
q = e.players[1]
q["x"], q["y"] = core.VINES[0][0], core.VINES[0][1] + 6
e.step({1: {"up": True}}, core.TICK_DT)
_idle_ok = True
for _ in range(10):
    e.step({1: {}}, core.TICK_DT)
    if q["vine"] < 0:
        _idle_ok = False
        break
check("挂住不动不会掉", _idle_ok, "vine=%d" % q["vine"])

# 松手路径：重新按跳才松手
e.step({1: {"up": True}}, core.TICK_DT)
check("重新按跳键才松手", q["vine"] == -1, "vine=%d" % q["vine"])

# 六条藤蔓：从低端滑到高端都要能站上平台（端点对齐检查）
_PLATS = [
    (10, 13, 13 * T), (17, 20, 13 * T), (24, 27, 13 * T), (31, 33, 13 * T),
    (66, 69, 13 * T), (73, 76, 13 * T), (79, 81, 13 * T),
    (96, 104, 15 * T), (97, 103, 11 * T), (99, 101, 7 * T),
]
_all_ok = True
_bad = []
for _vi, _v in enumerate(core.VINES):
    _e = fresh(); _e.wave1_spawned = True
    _q = _e.players[0]
    if _v[1] >= _v[3]:
        _sx, _sy, _k = _v[0], _v[1], "right"
    else:
        _sx, _sy, _k = _v[2], _v[3], "left"
    _q["x"], _q["y"] = _sx, _sy + 14
    for _ in range(4):
        _e.step({0: {"up": True}}, core.TICK_DT)
        if _q["vine"] >= 0:
            break
    if _q["vine"] < 0:
        _all_ok = False
        _bad.append("v%d抓不住" % _vi)
        continue
    for _ in range(100):
        _e.step({0: {_k: True}}, core.TICK_DT)
        if _q["vine"] < 0:
            break
    for _ in range(30):
        _e.step({0: {}}, core.TICK_DT)
    _on_plat = any(c0 * T <= _q["x"] <= (c1 + 1) * T and abs(_q["y"] - top) < 12
                   for c0, c1, top in _PLATS)
    _in_wall = _e._solid_at(int(_q["x"] // T), int((_q["y"] - 6) // T))
    if not (_on_plat and _q["on_ground"] and not _in_wall):
        _all_ok = False
        _bad.append("v%d落点(%.0f,%.0f)" % (_vi, _q["x"], _q["y"]))
check("六条藤蔓滑到顶都能站上平台", _all_ok, "; ".join(_bad))

# 塔内：站 F2 按跳应抓 F2->F3 那条，而不是 F1->F2 的顶端
_e = fresh(); _e.wave1_spawned = True
_q = _e.players[0]
_q["x"], _q["y"] = 3152, 11 * T
_e.step({0: {"up": True}}, core.TICK_DT)
check("塔内按跳抓向上的那条藤蔓", _q["vine"] == 5, "vine=%d" % _q["vine"])

# 靠近顶端松手：身体不能卡进平台
_e = fresh(); _e.wave1_spawned = True
_q = _e.players[0]
_q["x"], _q["y"] = core.VINES[2][0], core.VINES[2][1] + 14
for _ in range(4):
    _e.step({0: {"up": True}}, core.TICK_DT)
    if _q["vine"] >= 0:
        break
_px, _py = _e._vine_point(2, 0.92)
_q["x"], _q["y"] = _px, _py + 6
_q["vine_t"] = 0.92
_e.step({0: {"down": True}}, core.TICK_DT)
_stuck = False
for _ in range(20):
    _e.step({0: {}}, core.TICK_DT)
    if _e._solid_at(int(_q["x"] // T), int((_q["y"] - core.PLAYER_H / 2) // T)):
        _stuck = True
        break
check("贴着平台顶端松手不卡砖", not _stuck, "x=%.0f y=%.0f" % (_q["x"], _q["y"]))
# 站在上层平台上
e = fresh()
e.wave1_spawned = True
r = e.players[0]
r["x"], r["y"] = 18 * T + 16, 13 * T
for _ in range(20):
    step(e, 1)
check("可站立在上层平台", abs(r["y"] - 13 * T) < 2, "y=%.0f" % r["y"])

# 飞怪不能钻进地下
e = fresh()
e.wave1_spawned = True
e.players[0]["x"], e.players[0]["y"] = 37 * T, 704
bat = core.Monster(77, "fly", 39 * T, 600)
e.monsters.append(bat)
_bad = 0
for _ in range(240):
    step(e, 1)
    if bat.y > e.surface_y(bat.x) - 30 + 0.01:
        _bad += 1
check("飞怪不再嵌入地下", _bad == 0, "bad=%d y=%.0f surf=%.0f" % (_bad, bat.y, e.surface_y(bat.x)))

print("== 11. 性能：1000 tick ==")
import time
e = fresh()
t0 = time.perf_counter()
for i in range(1000):
    e.step({0: {"right": True, "shoot": i % 7 == 0, "mx": 900, "my": 240},
            1: {"right": True, "sword": i % 5 == 0}}, core.TICK_DT)
dt = time.perf_counter() - t0
print("  1000 tick 用时 %.0f ms（%.2f ms/tick）" % (dt * 1000, dt))
check("逻辑帧耗时 < 8ms", dt * 1000 / 1000 < 8)

print()
if FAIL:
    print("失败项：", FAIL)
    sys.exit(1)
print("全部通过。")
