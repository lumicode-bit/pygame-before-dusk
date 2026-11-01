# -*- coding: utf-8 -*-
"""test_edges.py —— 边界与异常路径测试

覆盖现有 test_* 没有触及的地方：
  * 渲染函数的异常处理分支本身是否健壮（这里曾有三个 NameError）
  * 死亡 / 通关 / Boss 状态机的极端时序
  * 物理越界、极端 dt
  * 存档文件被写坏后的行为
  * 畸形网络封包

运行： python test_edges.py
退出码 0 表示全部通过。
"""
import io
import json
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

pygame.init()
pygame.display.set_mode((1280, 720))

import game_core as core
import main as M
import ui
import theme

# --- 测试隔离：绝不碰玩家的真实存档 -------------------------------------
# 之前跑测试会把 records.json 的 runs/wins 直接 +1，best_time 还会被
# 写成测试里那个 0.5 秒的假成绩（"历史最佳 0:00"就是这么来的）。
import tempfile as _tf
_TMPDIR = _tf.mkdtemp(prefix="dusk_test_")
M.RECORDS_FILE = os.path.join(_TMPDIR, "records.json")
M.SETTINGS_FILE = os.path.join(_TMPDIR, "settings.json")
import renderer as R

FAIL = []


def check(name, cond, detail=""):
    print(("  [PASS] " if cond else "  [FAIL] ") + name + ("  " + detail if detail else ""))
    if not cond:
        FAIL.append(name)


def fresh():
    e = core.GameEngine()
    e.reset()
    return e


def run(e, n, inputs=None):
    for _ in range(n):
        e.step(inputs or {0: {}, 1: {}}, core.TICK_DT)


def _tmp_json(name, obj):
    p = os.path.join(os.getcwd(), name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return p


# ---------------------------------------------------------------- 渲染异常路径
def test_render_guards():
    print("== 1. 渲染异常处理分支 ==")
    w = R.WorldRenderer(pygame.display.get_surface())
    surf = pygame.Surface((800, 450))

    # 坏数据触发 _draw_tower 内部异常：必须被吞掉，不能反过来抛 NameError
    try:
        w._draw_tower(surf, 0, 0, 0.0, {"vents": [{"x": "坏", "y": 0, "on": True}]})
        ok_tower = True
        err = ""
    except Exception as e:
        ok_tower = False
        err = "%s: %s" % (type(e).__name__, e)
    check("塔楼绘制异常被吞掉", ok_tower, err)

    try:
        w._draw_vines(surf, 0, 0, 0.0, {"players": {0: {"vine": "坏"}}})
        ok_vines = True
        err = ""
    except Exception as e:
        ok_vines = False
        err = "%s: %s" % (type(e).__name__, e)
    check("藤蔓绘制异常被吞掉", ok_vines, err)

    try:
        w._draw_rifts(surf, 0, 0, 0.0, {"rifts": [{"x": "坏", "y": 0, "t": 0}]})
        ok_rifts = True
        err = ""
    except Exception as e:
        ok_rifts = False
        err = "%s: %s" % (type(e).__name__, e)
    check("裂隙绘制异常被吞掉", ok_rifts, err)

    # 警告只打一次：第二次不应再改变标志
    check("异常只告警一次", getattr(w, "_tower_warned", False) is True)


# ---------------------------------------------------------------- 死亡 / 通关
def test_death():
    print("== 2. 死亡与复活 ==")
    e = fresh()
    e.players[0]["hp"] = 0
    e.players[1]["hp"] = 0
    run(e, 1)
    hp = [e.players[i]["hp"] for i in (0, 1)]
    check("两人同帧死亡都能复活", all(h > 0 for h in hp), "血量 %s" % hp)
    check("复活后血量约为上限的 60%",
          abs(hp[0] - core.ROLES[0]["maxhp"] * core.RESPAWN_HP_RATIO) < 12, "%.0f" % hp[0])

    e = fresh()
    e.portal_active = True
    for pid in (0, 1):
        e.players[pid]["x"] = core.PORTAL_RECT[0] + 40
        e.players[pid]["y"] = core.PORTAL_RECT[1] + 40
    run(e, 45)
    check("两人同时站在传送门内 1 秒即通关", e.win, "win_t=%.2f" % e.win_t)

    e = fresh()
    e.portal_active = True
    e.players[0]["x"] = core.PORTAL_RECT[0] + 40
    e.players[0]["y"] = core.PORTAL_RECT[1] + 40
    run(e, 60)
    check("只有一人进门不通关", not e.win)


# ---------------------------------------------------------------- Boss
def test_boss():
    print("== 3. Boss 状态机 ==")
    e = fresh()
    e._spawn_boss()
    run(e, 70)
    bosses = [m for m in e.monsters if m.kind == "boss"]
    check("裂隙倒计时结束后 Boss 出场", len(bosses) == 1)

    if not bosses:
        return
    b = bosses[0]
    check("Boss 初始血量 = BOSS_HP", abs(b.hp - core.BOSS_HP) < 0.01, "%.1f" % b.hp)

    phases = []
    for frac in (0.70, 0.60, 0.40, 0.30, 0.10):
        b.hp = b.maxhp * frac
        run(e, 20)
        phases.append((frac, b.phase))
    check("66% 进二阶段", phases[1][1] == 2, str(phases[:2]))
    check("33% 进三阶段", phases[3][1] == 3, str(phases[3:4]))

    # 冲锋有距离条件（<430px，三阶段 520px），必须先把玩家挪到 Boss 身边
    for pid in (0, 1):
        e.players[pid]["x"] = b.x - 260
        e.players[pid]["y"] = b.y
        e.players[pid]["hp"] = e.players[pid]["maxhp"]
    states = set()
    for _ in range(300):
        for pid in (0, 1):
            e.players[pid]["x"] = b.x - 260
            e.players[pid]["y"] = b.y
            e.players[pid]["hp"] = e.players[pid]["maxhp"]
        e.step({0: {}, 1: {}}, core.TICK_DT)
        states.add(b.state)
    check("Boss 会进入冲锋状态", "charge" in states, str(sorted(states)))


# ---------------------------------------------------------------- 单人协作
def test_solo_coop():
    print("== 4. 单人模式的 AI 协作 ==")
    T = core.TILE
    c0 = core.DUO_PLATE_COLS[0]

    # 真实流程：主角走到双人机关 -> 按 F 切"守点" -> AI 应该补位并开门。
    # 曾经这里必挂：guard 分支只接管左右键，原始 AI 一直按跳，
    # 而闸门要求连续踩住 0.45s，跳一下就清零 -> AI 在机关上原地弹跳、门永远不开。
    e = core.GameEngine()
    e.reset()
    e.ai_pid = 1
    for pid in (0, 1):
        e.players[pid]["x"] = 108 * T + 16
        e.players[pid]["y"] = e.surface_y(108 * T + 16)
    target = c0 * T + 16
    cmd = "follow"
    opened = False
    for i in range(1800):
        pin = {"right": True} if e.players[0]["x"] < target - 6 else {}
        if e.players[0]["x"] >= target - 6 and cmd == "follow":
            cmd = "guard"
        e.step({0: pin, 1: core.make_ai_input(1, e, 0, cmd)}, core.TICK_DT)
        if e.duo_gate_open:
            opened = True
            break
    check("单人模式：守点指令能开启双人闸门", opened,
          "AI 列 %.1f 用时 %.1fs" % (e.players[1]["x"] / T, i * core.TICK_DT))

    # 守门符文：AI 站上符文，门必须开
    e = core.GameEngine()
    e.reset()
    e.ai_pid = 1
    for pid, col in ((0, 101), (1, 96)):
        e.players[pid]["x"] = col * T + 16
        e.players[pid]["y"] = 11 * T
    rune_ok = False
    for i in range(300):
        e.step({0: {}, 1: core.make_ai_input(1, e, 0, "guard")}, core.TICK_DT)
        if e.rune_open:
            rune_ok = True
            break
    check("单人模式：守点指令能开启共鸣门", rune_ok, "AI 列 %.1f" % (e.players[1]["x"] / T))

    # 两人已经各自站在机关上时，必须在 0.6s 内开门。
    # 如果 AI 原地跳，hold 会被反复清零，这个时间就永远到不了。
    e = core.GameEngine()
    e.reset()
    e.ai_pid = 1
    for pid, col in ((0, c0), (1, core.DUO_PLATE_COLS[1])):
        e.players[pid]["x"] = col * T + 16
        e.players[pid]["y"] = e.surface_y(col * T + 16)
    t_open = None
    for i in range(60):
        e.step({0: {}, 1: core.make_ai_input(1, e, 0, "guard")}, core.TICK_DT)
        if e.duo_gate_open:
            t_open = i * core.TICK_DT
            break
    check("两人已在机关上时 0.6s 内开门（说明 AI 没有原地跳）",
          t_open is not None and t_open <= 0.6,
          "开门用时 %s" % ("%.2fs" % t_open if t_open is not None else "未开"))

    # 瞭望塔是垂直结构，AI 爬不上去（会在井道里弹跳、被喷火烧死）。
    # 人类过塔后必须把同伴带过去，否则单人模式就卡在塔后面了。
    e = core.GameEngine()
    e.reset()
    e.ai_pid = 1
    for pid, col in ((0, 110), (1, 99)):
        e.players[pid]["x"] = col * T + 16
        e.players[pid]["y"] = e.surface_y(col * T + 16)
    rescued = False
    for i in range(600):
        e.step({0: {}, 1: core.make_ai_input(1, e, 0, "follow")}, core.TICK_DT)
        if abs(e.players[1]["x"] - e.players[0]["x"]) < 3 * T:
            rescued = True
            break
    # 导航图缓存必须能反复取：缓存属性一旦和方法同名，第一次调用后
    # 实例属性就把方法覆盖了，第二次 eng._nav_graph() 变成"调用 NavGraph 对象"
    # -> TypeError 被 _nav_follow 吞成 False，导航图从第二帧起彻底失效。
    e = core.GameEngine()
    e.reset()
    g1 = e._nav_graph()
    g2 = e._nav_graph()
    check("导航图可重复获取", g1 is g2 and g1 is not None,
          "同一对象=%s" % (g1 is g2))

    # 跟着玩家爬藤上平台：曾经因为挂索方向按"下一节点"判断而原地卡死
    e = core.GameEngine()
    e.reset()
    e.ai_pid = 1
    e.players[1]["x"] = 20 * T + 16
    e.players[1]["y"] = 13 * T
    e.players[0]["x"] = 26 * T + 16
    e.players[0]["y"] = e.surface_y(26 * T + 16)
    for _ in range(400):
        e.step({0: {}, 1: core.make_ai_input(1, e, 0, "follow")}, core.TICK_DT)
    _a, _p = e.players[1], e.players[0]
    check("AI 能跟着玩家上到平台", abs(_a["x"] - _p["x"]) < 3 * T and abs(_a["y"] - _p["y"]) < 3 * T,
          "AI(%.1f,%.1f) 玩家(%.1f,%.1f)" % (_a["x"] / T, _a["y"] / T, _p["x"] / T, _p["y"] / T))

    check("AI 卡在塔里会被带回人类身边", rescued,
          "AI 列 %.1f 用时 %.1fs 死亡 %d" % (e.players[1]["x"] / T, i * core.TICK_DT, e.deaths))

    # 导航图强化：关掉传送兜底，AI 也要能自己翻过塔（跳 F1 -> 走塔顶 -> 落下）
    old_rescue = core.GameEngine._update_ai_rescue
    core.GameEngine._update_ai_rescue = lambda self, dt: None
    try:
        e = core.GameEngine()
        e.reset()
        e.ai_pid = 1
        e.players[0]["x"] = 110 * T + 16
        e.players[0]["y"] = 19 * T
        e.players[1]["x"] = 94 * T + 16
        e.players[1]["y"] = 19 * T          # 塔前地面
        crossed = False
        for i in range(1500):
            e.step({0: {}, 1: core.make_ai_input(1, e, 0, "follow")}, core.TICK_DT)
            if e.players[1]["x"] > 107 * T:
                crossed = True
                break
        check("纯导航图翻塔（不靠传送）", crossed,
              "用时 %.1fs 死亡 %d" % (i * core.TICK_DT, e.deaths))
    finally:
        core.GameEngine._update_ai_rescue = old_rescue

    # 站在平台上、怪在正下方时，旧逻辑会因为"横向距离 0"而僵住：
    # 既不挥剑（剑判定盒只有 56px 高）也不跟随玩家。
    e = core.GameEngine()
    e.reset()
    e.ai_pid = 1
    e.players[1]["x"] = 20 * T + 16
    e.players[1]["y"] = 13 * T                      # 站在平台上
    e.players[0]["x"] = 26 * T + 16
    e.players[0]["y"] = e.surface_y(26 * T + 16)
    below = core.Monster(97, "ground", 20 * T, 19 * T - 40)   # 怪在脚下
    e.monsters.append(below)
    for i in range(400):
        e.step({0: {}, 1: core.make_ai_input(1, e, 0, "follow")}, core.TICK_DT)
    check("AI 不会对着脚下的怪僵住（会继续跟随）",
          abs(e.players[1]["x"] - e.players[0]["x"]) < 5 * T,
          "AI 列 %.1f 玩家列 %.1f" % (e.players[1]["x"] / T, e.players[0]["x"] / T))

    # 同一层的怪必须能打死（剑真的挥得出去）
    e = core.GameEngine()
    e.reset()
    e.ai_pid = 1
    for pid in (0, 1):
        e.players[pid]["x"] = 20 * T + 16
        e.players[pid]["y"] = 19 * T
    m = core.Monster(96, "ground", 22 * T, 19 * T - 40)
    e.monsters.append(m)
    killed = False
    for i in range(300):
        e.step({0: {}, 1: core.make_ai_input(1, e, 0, "follow")}, core.TICK_DT)
        if m.hp <= 0:
            killed = True
            break
    check("AI 盾卫能斩杀同层地面怪", killed, "hp=%.1f 用时 %.1fs" % (m.hp, i * core.TICK_DT))


# ---------------------------------------------------------------- 暮色倒计时
def test_dusk():
    print("== 5. 暮色倒计时 ==")
    # 进度与夜幕标志
    e = core.GameEngine()
    e.reset()
    e.elapsed = 900.0                     # 夜幕(840)之后、完全入夜(1140)之前
    st = e.pack()
    check("暮色进度随时间推进", 0.78 < st["dusk"] < 0.80, "dusk=%.2f" % st["dusk"])
    check("夜幕标志正确", st["night"] is True and st["night_in"] == 0.0)
    e.elapsed = 100.0
    st = e.pack()
    check("黄昏阶段无夜幕", st["night"] is False and st["dusk"] < 0.1)

    # 难度越高天黑越早
    e.difficulty = 1.4
    nf_hard = e.nightfall_at()
    e.difficulty = 0.7
    nf_easy = e.nightfall_at()
    check("困难难度夜幕更早", nf_hard < 840.0 < nf_easy,
          "hard=%.0fs easy=%.0fs" % (nf_hard, nf_easy))
    e.difficulty = 1.0

    # 夜幕增援：裂隙事件随时间出现
    e2 = core.GameEngine()
    e2.reset()
    e2.elapsed = core.DUSK_NIGHTFALL + 1.0
    e2._night_next = e2.elapsed
    e2._night_announced = True
    rift_open = 0
    for i in range(900):                  # 30 秒 → 至少一次增援
        e2.step({0: {}, 1: {}}, core.TICK_DT)
        rift_open += sum(1 for ev in e2.events if ev[0] == "rift_open")
    check("夜幕增援会开出裂隙", rift_open >= 1, "30 秒内 %d 次" % rift_open)

    # 残阳加成：赶在夜幕前通关 +500 分
    st = {"kills": 10, "deaths": 0, "elapsed": 500.0, "win": True}
    s0 = M.compute_score(st, 1.0)
    st["beat_night"] = True
    s1 = M.compute_score(st, 1.0)
    check("残阳加成 +500", s1 - s0 == 500, "%d -> %d" % (s0, s1))

    # 渲染：完全入夜不崩溃
    e3 = core.GameEngine()
    e3.reset()
    e3.elapsed = core.DUSK_FULLNIGHT
    st = e3.pack()
    try:
        app = M.App()
        app.start_single(0)
        app._apply_scene("GAME")
        M.engine.elapsed = core.DUSK_FULLNIGHT
        app.dt = core.TICK_DT
        for _ in range(10):
            app.scene_game([], pygame.key.get_pressed(), (640, 360))
        ok = True
    except Exception as ex:
        ok = False
        print("   ", ex)
    check("完全入夜渲染不崩溃", ok)


# ---------------------------------------------------------------- 藤蔓与荆棘
def test_vine_bramble():
    print("== 6. 藤蔓与荆棘 ==")
    T = core.TILE

    # 藤蔓：按住跳松手后不能被"秒抓回去"（旧版会原地循环卡在藤蔓上）
    e = core.GameEngine()
    e.reset()
    e.ai_pid = 1
    e.players[0]["x"] = 33 * T
    e.players[0]["y"] = 15 * T
    e.players[0]["vine"] = 1
    e.players[0]["vine_t"] = 0.5
    # 模拟"抓取时跳键正按着"（闩锁=True）：此时松手必须先松键再按，
    # 松手瞬间起跳坠离藤蔓的过程中，按着跳也不允许被吸回去
    e.players[0]["_vine_up_latch"] = False
    e.players[1]["x"] = 40 * T
    e.players[1]["y"] = 19 * T
    regrab = 0
    for i in range(60):                       # 按住跳 2 秒
        e.step({0: {"up": True}, 1: {}}, core.TICK_DT)
        if e.players[0]["vine"] >= 0:
            regrab += 1
    check("按住跳松手后不再被抓回藤蔓", regrab == 0, "被抓回 %d/60 帧" % regrab)

    # 用"下键"松手（不按跳）→ 0.2s 后按跳应能重新抓取
    # （先把人吸附到藤蔓点上，位置和挂索参数一致；不一致会触发
    #   松手时的"嵌墙校正"，把人弹到平台上——那是另一条合理行为）
    e.players[0]["vine"] = 1
    e.players[0]["vine_t"] = 0.5
    _gx, _gy = e._vine_point(1, 0.5)
    e.players[0]["x"] = _gx
    e.players[0]["y"] = _gy + 6
    e.players[0]["_vine_up_latch"] = False
    e.step({0: {"down": True}, 1: {}}, core.TICK_DT)
    regrabbed = False
    for i in range(40):
        e.step({0: {"up": True} if i >= 6 else {}, 1: {}}, core.TICK_DT)
        if e.players[0]["vine"] == 1:
            regrabbed = True
            break
    check("下键松手后按跳可重新抓取", regrabbed)

    # 红黑荆棘：路过（不踩上去）也会被抓住
    e = core.GameEngine()
    e.reset()
    e.ai_pid = 1
    e.players[0]["x"] = 124 * T
    e.players[0]["y"] = 19 * T
    e.players[1]["x"] = 140 * T
    e.players[1]["y"] = 19 * T
    hp0 = e.players[0]["hp"]
    for i in range(120):
        e.step({0: {"right": True}, 1: {}}, core.TICK_DT)
    check("路过荆棘会被抓伤", e.players[0]["hp"] < hp0 - 20,
          "血量 %.0f -> %.0f" % (hp0, e.players[0]["hp"]))

    # 金属刺：踩上去仍是"弹开"行为
    e = core.GameEngine()
    e.reset()
    e.ai_pid = 1
    e.players[0]["x"] = 108 * T
    e.players[0]["y"] = 19 * T
    e.players[1]["x"] = 140 * T
    e.players[1]["y"] = 19 * T
    bounced = False
    for i in range(60):
        e.step({0: {"right": True}, 1: {}}, core.TICK_DT)
        if e.players[0].get("on_ground") is False and e.players[0].get("vy", 0) < -200:
            bounced = True
            break
    check("金属刺仍是弹开行为", bounced)

    # 摆锤渲染（已去掉轨迹弧）不崩溃
    app = M.App()
    app.start_single(0)
    app._apply_scene("GAME")
    app.dt = core.TICK_DT
    ok = True
    try:
        for _ in range(30):
            app.scene_game([], pygame.key.get_pressed(), (640, 360))
    except Exception as ex:
        ok = False
        print("   ", ex)
    check("摆锤渲染（无轨迹弧）", ok)


# ---------------------------------------------------------------- 行程统计
def test_stats():
    print("== 6. 行程统计（结算页故事数据） ==")
    T = core.TILE
    e = core.GameEngine()
    e.reset()
    # 推进到岩浆段 -> 受伤 -> 折返回森林
    for pid in (0, 1):
        e.players[pid]["x"] = 70 * T + 16
        e.players[pid]["y"] = e.surface_y(70 * T + 16)
    for i in range(10):
        e.step({0: {}, 1: {}}, core.TICK_DT)
    e._track_dmg(0, 12)
    for pid in (0, 1):
        e.players[pid]["x"] = 40 * T + 16
        e.players[pid]["y"] = e.surface_y(40 * T + 16)
    for i in range(10):
        e.step({0: {}, 1: {}}, core.TICK_DT)
    st = e.pack()["stats"]
    check("折返被计数", st["reversals"] >= 1, "reversals=%d" % st["reversals"])
    check("区域伤害按段累计", st["dmg"][1] >= 12, "dmg=%s" % st["dmg"])
    check("最远区域被记录", st["max_region"] >= 1, "max_region=%d" % st["max_region"])
    check("状态包带行程统计", all(k in st for k in
          ("blocks", "chests", "weapon")), str(sorted(st)))


# ---------------------------------------------------------------- 物理边界
def test_physics():
    print("== 4. 物理边界 ==")
    e = fresh()
    for dt in (0.0, 1e-9, 5.0, -1.0):
        e.step({0: {}, 1: {}}, dt)
    check("极端 dt 不崩溃", True, "tick=%d" % e.tick)

    e = fresh()
    e.players[0]["x"] = -500
    run(e, 1)
    left = e.players[0]["x"]
    e.players[0]["x"] = core.WORLD_W + 500
    run(e, 1)
    right = e.players[0]["x"]
    check("玩家不会跑出世界左右边界",
          -64 <= left <= core.WORLD_W + 64 and -64 <= right <= core.WORLD_W + 64,
          "%.0f / %.0f" % (left, right))

    e = fresh()
    e.players[0]["x"] = 46 * core.TILE
    e.players[0]["y"] = 18 * core.TILE
    run(e, 30)
    p = e.players[0]
    inside = e._rect_solid(p["x"], p["y"], core.PLAYER_W, core.PLAYER_H)
    check("塞进实体方块会被脱困逻辑抬出", not inside, "x=%.0f y=%.0f" % (p["x"], p["y"]))


# ---------------------------------------------------------------- 存档
def test_files():
    print("== 5. 存档容错 ==")
    p = _tmp_json("_t_records.json", {"runs": "很多", "wins": None, "best_time": "abc",
                                      "best_kills": [], "best_rank": 99, "best_score": {}})
    old = M.RECORDS_FILE
    M.RECORDS_FILE = p
    try:
        rec = M.load_records()
        clean = (isinstance(rec["runs"], int) and isinstance(rec["best_kills"], int)
                 and (rec["best_time"] is None or isinstance(rec["best_time"], float))
                 and rec["best_rank"] in ("", "S", "A", "B", "C"))
        check("损坏的记录字段被清洗成合法值", clean, str(rec))

        app = M.App()
        app.records = rec
        app._update_records({"kills": 9, "deaths": 0, "elapsed": 50.0, "win": True})
        check("损坏记录下结算仍能写入新纪录",
              app.records.get("best_kills") == 9 and app.records.get("best_score", 0) > 0,
              str({k: app.records[k] for k in ("runs", "best_kills", "best_score")}))
    finally:
        M.RECORDS_FILE = old
        os.remove(p)

    # 自定义键位必须能重启读回（之前 _commit_settings 不写 keys，
    # load_settings 又按白名单把它丢掉，改键重启就回默认）
    p = os.path.join(os.getcwd(), "_t_keys.json")
    old_s = M.SETTINGS_FILE
    M.SETTINGS_FILE = p
    old_map = {k: list(v) for k, v in M.KEYMAP.items()}
    try:
        app = M.App()
        app._assign_key("up", pygame.K_j)
        app._assign_key("dash", pygame.K_k)
        app._commit_settings()
        M.KEYMAP = {k: list(v) for k, v in M.DEFAULT_KEYMAP.items()}
        M.App()
        ok = (M.KEYMAP["up"] == [pygame.K_j] and M.KEYMAP["dash"] == [pygame.K_k])
        check("自定义键位重启后仍生效", ok, "up=%s dash=%s" % (M.KEYMAP["up"], M.KEYMAP["dash"]))
    finally:
        M.SETTINGS_FILE = old_s
        M.KEYMAP = old_map
        if os.path.exists(p):
            os.remove(p)

    p = _tmp_json("_t_settings.json", {"master": "loud", "music": -5, "sfx": 99,
                                       "fullscreen": "yes", "quality": "高"})
    old = M.SETTINGS_FILE
    M.SETTINGS_FILE = p
    try:
        s = M.load_settings()
        bad = [k for k, v in s.items() if isinstance(v, float) and not (0 <= v <= 1)]
        check("损坏的设置被收敛到合法范围", not bad, str(bad))
    finally:
        M.SETTINGS_FILE = old
        os.remove(p)


# ---------------------------------------------------------------- 网络
def test_net():
    print("== 6. 网络封包 ==")
    # 数据没到齐 / 长度合法但内容坏：安静返回，不能抛
    soft = [b"\x00\x00", b"\x00\x00\x00\x05" + b"\xff\xfe\xfd\xfc\xfb",
            b"\x00\x00\x00\x04null", b"\x00\x00\x00\x08{}"]
    ok = True
    for c in soft:
        try:
            core.decode_pkt(c)
        except Exception:
            ok = False
    check("可恢复的坏包不抛异常", ok, "%d 种" % len(soft))

    # 长度非法：必须抛 PacketError，否则流会错位
    fatal = [b"\x00\x00\x00\x00", b"\xff\xff\xff\xff" + b"x" * 10,
             b"\x00\x00\x00\x00extra"]
    raised = 0
    for c in fatal:
        try:
            core.decode_pkt(c)
        except core.PacketError:
            raised += 1
        except Exception:
            pass
    check("非法长度抛 PacketError", raised == len(fatal), "%d/%d" % (raised, len(fatal)))

    out = core.sanitize_input({"left": "yes", "right": 10 ** 9, "mx": float("nan"),
                               "hack": 1, "shoot": [1, 2]})
    import math
    check("非法输入被过滤/夹紧",
          all(not (isinstance(v, float) and not math.isfinite(v)) for v in out.values()),
          str(out))

    e = fresh()
    e._spawn_boss()
    run(e, 60)
    b = core.encode_pkt(e.pack())
    obj, _ = core.decode_pkt(b)
    check("状态包可 JSON 往返", bool(obj) and obj.get("type") == "state", "%d 字节" % len(b))
    check("玩家 key 解码后仍是 int", all(isinstance(k, int) for k in obj["players"]))


# ---------------------------------------------------------------- UI / 场景
def test_ui():
    print("== 7. 场景与 UI ==")
    app = M.App()
    for _ in range(10):
        app.start_single(0)
        for _ in range(3):
            app.scene_game([], pygame.key.get_pressed(), (700, 360))
        app.leave_game()
    check("连续进出游戏 10 次不崩溃", True, "scene=%s" % app.scene)

    old = dict(M.KEYMAP)
    try:
        app._assign_key("jump", pygame.K_a)
        app._assign_key("dash", pygame.K_a)
        ok = True
    except Exception as e:
        ok = False
        print("   ", e)
    finally:
        M.KEYMAP.clear()
        M.KEYMAP.update(old)
    check("键位冲突不崩溃", ok)


# ---------------------------------------------------------------- 本轮回归
def test_regress_round14():
    print("== 8. 塔楼入口 / 折返统计 / 缩放持久化 ==")
    T = core.TILE

    # 塔楼入口：地面 94 列连跳上 F1。曾经在 95 列加过一格"护沿"，
    # 结果玩家被卡进护沿与塔基之间那条一格宽的缝里，永远上不去。
    e = core.GameEngine()
    e.reset()
    e.ai_pid = 1
    e.players[0]["x"] = 94 * T + 16
    e.players[0]["y"] = 19 * T
    e.players[1]["x"] = 110 * T + 16
    e.players[1]["y"] = 19 * T
    climbed = False
    for i in range(300):
        inp = {"right": True}
        if i % 18 < 9:
            inp["up"] = True
        e.step({0: inp, 1: {}}, core.TICK_DT)
        a = e.players[0]
        # 必须"真的站在台面上"（落地 + 脚在 480），不能是跳跃途中路过。
        # 旧写法只判 y <= 481，跳到半空就能过，等于没测。
        if abs(a["y"] - 15 * T) < 2 and a.get("on_ground") and a["x"] > 96 * T:
            climbed = True
            break
    check("能从地面登上塔一层（入口未被堵）", climbed,
          "列 %.1f 行 %.1f" % (e.players[0]["x"] / T, e.players[0]["y"] / T))

    # 阵亡传送回检查点不该被记成"主动折返"（结算页会写"折返 N 次"）
    e = core.GameEngine()
    e.reset()
    e.ai_pid = 1
    e._respawn_point = (108 * T, 19 * T)
    for pid in (0, 1):
        e.players[pid]["x"] = 120 * T + 16
        e.players[pid]["y"] = 19 * T
    for _ in range(10):
        e.step({0: {}, 1: {}}, core.TICK_DT)
    e.players[0]["hp"] = 0
    for _ in range(60):
        e.step({0: {}, 1: {}}, core.TICK_DT)
    check("阵亡复活不计为折返", e.stats["reversals"] == 0,
          "reversals=%d" % e.stats["reversals"])
    # 但主动回头仍要计
    for pid in (0, 1):
        e.players[pid]["x"] = 100 * T + 16
    for _ in range(10):
        e.step({0: {}, 1: {}}, core.TICK_DT)
    check("主动后退仍计为折返", e.stats["reversals"] == 1,
          "reversals=%d" % e.stats["reversals"])

    # 界面缩放 >100% 必须能重启后读回（旧版统一按 0~1 夹，1.2 会变 1.0）
    import json as _json
    import tempfile as _tf
    old_s = M.SETTINGS_FILE
    tmp = _tf.mkdtemp(prefix="dusk_scale_")
    M.SETTINGS_FILE = os.path.join(tmp, "settings.json")
    try:
        with open(M.SETTINGS_FILE, "w", encoding="utf-8") as f:
            _json.dump({"ui_scale": 1.2}, f)
        loaded = M.load_settings()
        check("界面缩放 120% 重启后仍生效", abs(loaded["ui_scale"] - 1.2) < 1e-6,
              "读出 %.2f" % loaded["ui_scale"])
        with open(M.SETTINGS_FILE, "w", encoding="utf-8") as f:
            _json.dump({"ui_scale": 1.4}, f)
        check("界面缩放 140% 重启后仍生效", abs(M.load_settings()["ui_scale"] - 1.4) < 1e-6)
        with open(M.SETTINGS_FILE, "w", encoding="utf-8") as f:
            _json.dump({"ui_scale": 9.9}, f)
        check("越界缩放被夹到 140%", abs(M.load_settings()["ui_scale"] - 1.4) < 1e-6)
    finally:
        M.SETTINGS_FILE = old_s

    # 滑块值域：越界值不能画到轨道外
    sl = ui.Slider((0, 0, 260, 8), 1.667, "界面缩放")
    check("滑块越界值被夹到 1.0", sl.value == 1.0, "value=%.3f" % sl.value)

    # 挑战词条卡：说明文字（rect.y+36，tiny 16px）要离底边至少 4px。
    # 曾经 56 高只剩 2px，看着像被裁掉。
    app = M.App()
    app._apply_scene("CHAR_SELECT")
    app.scene_char_select([], pygame.key.get_pressed(), (0, 0))
    bad = [cid for cid, rr in app.challenge_rects.items()
           if rr.y + 36 + 16 > rr.bottom - 4]
    check("词条卡说明不贴底边", not bad, "越界 %s" % bad)

    # Boss 血条不能压住角色卡（卡片 12..72）
    app._draw_boss_bar(app.screen, {"hp": 21, "maxhp": 42, "state": "charge",
                                    "enraged": True, "flash": 1.0})
    br = getattr(app, "_boss_bar_rect", None)
    check("Boss 血条在角色卡下方", br is not None and br.top >= 74,
          "top=%s" % (br.top if br else "无"))
    check("Boss 血条不压消息横幅", br is not None and br.bottom <= 114,
          "bottom=%s" % (br.bottom if br else "无"))

    # 底部提示是三层叠放的（键位行 / 塔引导 / 教程 / 交互提示），
    # 任何两层相交都会出现"字压在字上"。这里把 rounded_panel 的调用录下来，
    # 检查底部区域的框两两不相交。
    app = M.App()
    app.start_single(0)
    app._apply_scene("GAME")
    app.dt = core.TICK_DT
    eng = M.engine
    eng.monsters.clear()
    eng.wave1_spawned = True
    # 站到塔一层的补给箱旁：交互提示 + 教程 + 塔引导 同时出现
    for pid in (0, 1):
        eng.players[pid]["x"] = 101 * T + 16
        eng.players[pid]["y"] = 15 * T
    rects = []
    _orig = theme.rounded_panel
    def _spy(surf, r, *a, **kw):
        rects.append(pygame.Rect(r))
        return _orig(surf, r, *a, **kw)
    theme.rounded_panel = _spy
    try:
        for _ in range(3):
            app.scene_game([], pygame.key.get_pressed(), (640, 360))
    finally:
        theme.rounded_panel = _orig
    # 同一帧会被重复绘制，先按几何去重，否则"自己和自己相交"会误报
    seen = set()
    low = []
    for r in rects:
        if r.y > 540 and r.w < 700 and tuple(r) not in seen:
            seen.add(tuple(r))
            low.append(r)
    clash = []
    for i in range(len(low)):
        for j in range(i + 1, len(low)):
            if low[i].colliderect(low[j]):
                clash.append((tuple(low[i]), tuple(low[j])))
    check("底部提示层不互相重叠", not clash,
          "%d 个框，冲突 %d 组" % (len(low), len(clash)))

    # 结算页：文字不能互相压住（100% 与 120% 各查一次）。
    # 面板原来 470 高、偏移写死，加了两行后评语被按钮切掉；
    # 120% 下"击杀 12"又会和"得分"标签叠住。
    def _result_overlaps(scale):
        theme.ui_scale = scale
        ap = M.App()
        ap.settings["ui_scale"] = scale
        ap.start_single(0)
        en = M.engine
        en.kills, en.deaths, en.elapsed, en.win = 12, 1, 500.0, True
        en.beat_night = True
        en.stats["reversals"] = 2
        en.stats["blocks"] = 6
        en.stats["max_region"] = 2
        st = en.pack()
        ap.last_st = st
        ap.final_state = st
        ap._update_records(st)
        ap._apply_scene("RESULT")
        calls = []
        _o = theme.text
        def _sp(surf, txt, pos, *a, **kw):
            rr = _o(surf, txt, pos, *a, **kw)
            calls.append((str(txt), pygame.Rect(rr)))
            return rr
        theme.text = _sp
        try:
            ap.scene_result([], pygame.key.get_pressed(), (640, 400))
        finally:
            theme.text = _o
        seen, boxes = set(), []
        for txt, rr in calls:
            if rr.w <= 0 or rr.h <= 0 or rr.h > 60:   # 跳过 96px 的评级大字（字形框天然压到下一行）
                continue
            kk = (txt, tuple(rr))
            if kk in seen:
                continue
            seen.add(kk)
            boxes.append((txt, rr))
        bad = []
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                t1, r1 = boxes[i]
                t2, r2 = boxes[j]
                it = r1.clip(r2)
                if it.w > 0 and it.h > 0 and it.w * it.h > 0.30 * min(r1.w * r1.h, r2.w * r2.h):
                    bad.append("%s×%s" % (t1[:8], t2[:8]))
        bottom_ok = ap.result_panel.bottom <= 720
        btn_ok = ap.result_buttons[0].rect.top >= ap.result_panel.y + 8
        theme.ui_scale = 1.0
        return bad, bottom_ok, btn_ok

    bad1, bot1, btn1 = _result_overlaps(1.0)
    check("结算页文字不重叠(100%)", not bad1, "冲突 %s" % bad1)
    check("结算面板不超出屏幕(100%)", bot1)
    bad2, bot2, _ = _result_overlaps(1.2)
    check("结算页文字不重叠(120%)", not bad2, "冲突 %s" % bad2)
    check("结算面板不超出屏幕(120%)", bot2)


# ---------------------------------------------------------------- 事件反馈
def test_event_feedback():
    print("== 9. 事件反馈与键位完整性 ==")
    import re as _re
    src = io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "game_core.py"), encoding="utf-8").read()
    kinds = sorted(set(_re.findall(r'events\.append\(\(\s*"([a-z_]+)"', src)))
    # 明确"故意静默"的事件：
    #   monster_return = AI 内部状态（怪撤回守卫点），不需要玩家感知
    #   reset = 世界重置，由上层自己给提示
    silent_ok = {"monster_return", "reset"}
    app = M.App()
    app.start_single(0)
    missing = []
    for k in kinds:
        if k in silent_ok:
            continue
        fired = []
        o_sfx = M.audio.sfx
        o_float = app.floats.add
        o_burst = app.particles.burst
        o_trauma = app.cam.add_trauma
        o_flash = app.post.hit_flash
        o_chat = M.add_chat
        M.audio.sfx = lambda *a, **kw: fired.append("sfx")
        app.floats.add = lambda *a, **kw: fired.append("float")
        app.particles.burst = lambda *a, **kw: fired.append("particles")
        app.cam.add_trauma = lambda *a, **kw: fired.append("shake")
        app.post.hit_flash = lambda *a, **kw: fired.append("flash")
        M.add_chat = lambda *a, **kw: fired.append("chat")
        try:
            app.handle_events([(k, 400, 300)], 0)
        except Exception as ex:
            fired.append("CRASH:%s" % type(ex).__name__)
        finally:
            M.audio.sfx = o_sfx
            app.floats.add = o_float
            app.particles.burst = o_burst
            app.cam.add_trauma = o_trauma
            app.post.hit_flash = o_flash
            M.add_chat = o_chat
        if not fired:
            missing.append(k)
    check("引擎的每个事件都有反馈", not missing,
          "共 %d 种，无反馈：%s" % (len(kinds), missing))

    # 客机首帧：还没收到状态包时必须能正常画"同步世界状态…"。
    # 曾经这行少传了画布，theme.text 内部抛 ValueError，
    # 而它的兜底分支自己也会崩 -> 客机刚进游戏每帧抛异常。
    import queue as _q
    old_g, old_s, old_c, old_q, old_ls = M.guest, M.single_mode, M.client, M.net_out, M.last_state
    try:
        M.guest, M.single_mode = True, False
        M.client = None
        M.net_out = _q.Queue()
        M.last_state = None
        ap = M.App()
        ap._apply_scene("GAME")
        ap.dt = core.TICK_DT
        crashed = None
        for _ in range(5):
            try:
                ap.scene_game([], pygame.key.get_pressed(), (640, 360))
            except Exception as ex:
                crashed = "%s: %s" % (type(ex).__name__, ex)
                break
        check("客机首帧（无状态包）不崩", crashed is None, crashed or "")
    finally:
        M.guest, M.single_mode, M.client, M.net_out, M.last_state = \
            old_g, old_s, old_c, old_q, old_ls

    # 结算页的数值字段来自网络时可能是字符串/None，必须强制转型而不是崩
    _bad_results = [
        {"kills": "abc", "elapsed": 100, "win": True},
        {"kills": 3, "elapsed": None, "win": True},
        {"kills": None, "deaths": None, "elapsed": None, "win": True},
        {"kills": 3, "deaths": -5, "elapsed": 100, "win": True},
    ]
    _crash = None
    for _br in _bad_results:
        ap3 = M.App()
        ap3.last_st = _br
        ap3.final_state = _br
        try:
            ap3._update_records(_br)
            ap3._apply_scene("RESULT")
            ap3.scene_result([], pygame.key.get_pressed(), (640, 400))
        except Exception as ex:
            _crash = "%r -> %s: %s" % (_br, type(ex).__name__, ex)
            break
    check("结算页畸形数值不崩", _crash is None, _crash or "")

    # 客机收到畸形状态包（网络上的半截包/版本不一致）必须丢弃而不是崩
    try:
        import time as _t
        M.guest, M.single_mode = True, False
        M.client = None
        M.net_out = _q.Queue()
        M.last_state = None
        ap2 = M.App()
        ap2._apply_scene("GAME")
        ap2.dt = core.TICK_DT
        bad_states = [{}, {"players": {}}, {"players": {0: {}, 1: {}}},
                      {"players": []},
                      {"players": {0: {"x": "a", "y": None}, 1: {}}}]
        crashed = None
        for bs in bad_states:
            M.net_out.put_nowait(("state", bs, _t.time()))
            try:
                for _ in range(2):
                    ap2.scene_game([], pygame.key.get_pressed(), (640, 360))
            except Exception as ex:
                crashed = "%s: %s" % (type(ex).__name__, ex)
                break
        check("客机丢弃畸形状态包且不崩", crashed is None, crashed or "")
        check("畸形包没有污染 last_state", M.last_state is None)
        # 合法包仍要能收下
        _h = core.GameEngine()
        _h.reset()
        _h.step({0: {}, 1: {}}, core.TICK_DT)
        M.net_out.put_nowait(("state", _h.pack(), _t.time()))
        ap2.scene_game([], pygame.key.get_pressed(), (640, 360))
        check("合法状态包仍被接受", M.last_state is not None)
    finally:
        M.guest, M.single_mode, M.client, M.net_out, M.last_state = \
            old_g, old_s, old_c, old_q, old_ls

    # theme.text 参数传错时也不能把异常抛给调用方
    bad = None
    try:
        theme.text("这不是画布", (1, 2), "title", (255, 255, 255))
    except Exception as ex:
        bad = "%s: %s" % (type(ex).__name__, ex)
    check("theme.text 参数错误不抛异常", bad is None, bad or "")

    # 下蹲/穿板必须可重映射（原来硬编码 S/↓，改键后不跟随）
    check("下蹲动作在键位表里", "down" in M.KEYMAP, str(sorted(M.KEYMAP)))
    check("下蹲在可重映射列表里", "down" in M.REBIND_ORDER, str(M.REBIND_ORDER))

    # 键位里出现越界/负数/布尔值时必须回退默认，不能"接受但用不了"
    _def_up = list(M.DEFAULT_KEYMAP["up"])
    _bad_maps = [{"up": [-5]}, {"up": [10 ** 12]}, {"up": [True]}, {"up": [106, -1]}]
    _kept = []
    for _bm in _bad_maps:
        M.apply_keymap(_bm)
        if M.KEYMAP["up"] != _def_up:
            _kept.append(_bm)
    M.apply_keymap(None)
    check("越界键位回退默认", not _kept, "仍被接受：%s" % _kept)
    M.apply_keymap({"up": [106]})
    check("合法键位仍生效", M.KEYMAP["up"] == [106], str(M.KEYMAP["up"]))
    M.apply_keymap(None)

    # 滑块标签不能压住滑轨（22 时标签底边正好落在轨道上，像被划掉）
    ui.Slider((0, 100, 260, 8), 0.5, "测试")   # 仅构造，检查标签偏移
    lab_h = theme.render_text("测试", "label").get_height()
    lab_bottom = 100 - int(28 * max(1.0, theme.ui_scale)) + lab_h
    check("滑块标签不压滑轨", lab_bottom <= 100, "标签底边 %d vs 轨道顶 100" % lab_bottom)

    # 设置页已拆成三页：任何一页在任何缩放下都不能出现"字压字"。
    # （分页之前单页塞不下，1.3 就开始互相挤）
    for _sc in (1.0, 1.4):
        for _tab in (0, 1, 2):
            theme.ui_scale = _sc
            ap = M.App()
            ap.settings["ui_scale"] = _sc
            ap._build_settings()
            ap._apply_scene("SETTINGS")
            ap.set_tab = _tab
            calls = []
            _o = theme.text
            def _sp(surf, txt, pos, *a, **kw):
                rr = _o(surf, txt, pos, *a, **kw)
                calls.append((str(txt), pygame.Rect(rr)))
                return rr
            theme.text = _sp
            try:
                ap.scene_settings([], pygame.key.get_pressed(), (640, 360))
            finally:
                theme.text = _o
            seen, boxes = set(), []
            for txt, rr in calls:
                if rr.w <= 0 or rr.h <= 0:
                    continue
                kk = (txt, tuple(rr))
                if kk in seen:
                    continue
                seen.add(kk)
                boxes.append((txt, rr))
            bad = []
            for i in range(len(boxes)):
                for j in range(i + 1, len(boxes)):
                    t1, r1 = boxes[i]
                    t2, r2 = boxes[j]
                    it = r1.clip(r2)
                    if (it.w > 0 and it.h > 0
                            and it.w * it.h > 0.30 * min(r1.w * r1.h, r2.w * r2.h)):
                        bad.append("%s×%s" % (t1[:8], t2[:8]))
            check("设置页第 %d 页不重叠(%.0f%%)" % (_tab + 1, _sc * 100), not bad,
                  "冲突 %s" % bad[:3])
        theme.ui_scale = 1.0


def main():
    test_render_guards()
    test_death()
    test_boss()
    test_solo_coop()
    test_physics()
    test_dusk()
    test_vine_bramble()
    test_stats()
    test_files()
    test_regress_round14()
    test_event_feedback()
    test_net()
    test_ui()
    print("-" * 56)
    if FAIL:
        print("失败 %d 项：%s" % (len(FAIL), "、".join(FAIL)))
        return 1
    print("边界测试全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
