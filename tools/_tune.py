# -*- coding: utf-8 -*-
"""数值调参模拟：测树精 Boss 的击杀耗时(TTK)与站桩承伤，用于调血/伤害。"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import game_core as core

T = core.TILE
DT = core.TICK_DT


def spawn_tree(hp_override=None):
    e = core.GameEngine()
    e.monsters.clear()
    e.wave = 3
    e.wave1_spawned = True
    e.wave2_spawned = True
    for pid in (0, 1):
        e.players[pid]["x"] = (core.ALTAR_LEFT + 2) * T
        e.players[pid]["y"] = 15 * T
    e._spawn_boss()
    for r in e.rifts:
        r["t"] = r["delay"]
    e.step({0: {}, 1: {}}, DT)
    for m in e.monsters:
        if getattr(m, "state", "") == "spawn":
            m.state_t = 0.0
    e.step({0: {}, 1: {}}, DT)
    tree = next((m for m in e.monsters if m.kind == "boss" and m.tree), None)
    if tree is not None and hp_override:
        tree.hp = tree.maxhp = hp_override
    return e, tree


def ttk(godmode=True):
    e, tree = spawn_tree()
    if tree is None:
        return None, 0
    t = 0.0
    max_t = 150.0
    while tree in e.monsters and t < max_t:
        p0 = e.players[0]
        p1 = e.players[1]
        # 固定站位：弓手在远处射，盾卫贴身砍
        p0["x"] = tree.x - 220
        p0["y"] = 15 * T
        p1["x"] = tree.x - 70
        p1["y"] = 15 * T
        if godmode:
            p0["hp"] = p0["maxhp"]
            p1["hp"] = p1["maxhp"]
            p0["invuln"] = 0.5
            p1["invuln"] = 0.5
        inp0 = {"shoot": True, "mx": tree.x, "my": tree.y - 60}
        inp1 = {"sword": True}
        e.step({0: inp0, 1: inp1}, DT)
        t += DT
    return t, tree.hp


def incoming(duration=30.0):
    """站桩不躲，测单位时间受到的伤害（评估是否过于致命）。"""
    e, tree = spawn_tree()
    if tree is None:
        return None
    e.players[0]["maxhp"] = 1000
    e.players[1]["maxhp"] = 1000
    e.players[0]["hp"] = 1000
    e.players[1]["hp"] = 1000
    dmg = {0: 0.0, 1: 0.0}
    t = 0.0
    while t < duration:
        p0, p1 = e.players[0], e.players[1]
        p0["x"] = tree.x - 220
        p0["y"] = 15 * T
        p1["x"] = tree.x - 70
        p1["y"] = 15 * T
        before = {0: p0["hp"], 1: p1["hp"]}
        inp0 = {"shoot": True, "mx": tree.x, "my": tree.y - 60}
        inp1 = {"sword": True}
        e.step({0: inp0, 1: inp1}, DT)
        t += DT
        for pid in (0, 1):
            if e.players[pid]["hp"] < before[pid]:
                dmg[pid] += before[pid] - e.players[pid]["hp"]
    return dmg, duration


print("== 树精 TTK（无敌模式，纯输出）==")
t, hp = ttk(True)
print("  击杀耗时: %.1f 秒（剩余 hp=%.0f）" % (t, hp))
print("== 树精站桩承伤（30 秒不躲）==")
r = incoming(30.0)
if r:
    dmg, dur = r
    print("  弓手受伤 %.0f / %.0f 秒 = %.1f dps" % (dmg[0], dur, dmg[0] / dur))
    print("  盾卫受伤 %.0f / %.0f 秒 = %.1f dps" % (dmg[1], dur, dmg[1] / dur))
