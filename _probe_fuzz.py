# -*- coding: utf-8 -*-
"""_probe_fuzz.py —— 随机输入压力测试 + 不变量检查（临时探测，不留在仓库）

检查的不变量：
  1. 玩家/怪物坐标必须是有限值，且不能被甩出世界
  2. 玩家不能长时间嵌在实心方块里
  3. 血量必须在 [0, maxhp]
  4. tick 单调、事件列表不能无限增长
  5. 全程不能抛异常
"""
import math
import os
import random
import sys
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

pygame.init()
pygame.display.set_mode((1, 1))

import game_core as core

T = core.TILE
KEYS = ("left", "right", "up", "down", "dash", "shoot", "sword", "block", "interact")


def rand_input(rng, mx=800, my=300):
    d = {}
    for k in KEYS:
        if rng.random() < 0.28:
            d[k] = True
    if rng.random() < 0.5:
        d["mx"] = rng.uniform(0, mx)
        d["my"] = rng.uniform(0, my)
    return d


def check_invariants(e, tag, issues):
    for pid, p in e.players.items():
        x, y = p["x"], p["y"]
        if not (math.isfinite(x) and math.isfinite(y)):
            issues.append("%s: 玩家%d 坐标非有限值 (%r,%r)" % (tag, pid, x, y))
        if not (-2 * T <= x <= core.WORLD_W + 2 * T):
            issues.append("%s: 玩家%d 被甩出世界 x=%.0f" % (tag, pid, x))
        if not (-4 * T <= y <= core.WORLD_H + 8 * T):
            issues.append("%s: 玩家%d y 异常 %.0f" % (tag, pid, y))
        hp = p["hp"]
        if not (math.isfinite(hp) and -0.01 <= hp <= p["maxhp"] + 0.01):
            issues.append("%s: 玩家%d 血量越界 %.2f/%.0f" % (tag, pid, hp, p["maxhp"]))
    for m in e.monsters:
        if not (math.isfinite(m.x) and math.isfinite(m.y)):
            issues.append("%s: 怪物%d 坐标非有限值" % (tag, m.mid))
            continue
        if not (-8 * T <= m.x <= core.WORLD_W + 8 * T):
            issues.append("%s: 怪物%d 跑出世界 x=%.0f" % (tag, m.mid, m.x))
    if len(e.events) > 400:
        issues.append("%s: 单帧事件数异常 %d" % (tag, len(e.events)))
    if len(e.arrows) > 300:
        issues.append("%s: 箭矢数量异常 %d" % (tag, len(e.arrows)))
    if len(e.monsters) > 80:
        issues.append("%s: 怪物数量异常 %d" % (tag, len(e.monsters)))


def run_fuzz(seed, ticks=4000):
    rng = random.Random(seed)
    e = core.GameEngine()
    e.reset()
    # 一半的种子直接跳到中段，覆盖不同地形
    if seed % 3 == 1:
        for pid in (0, 1):
            e.players[pid]["x"] = rng.uniform(60, 95) * T
            e.players[pid]["y"] = 18 * T
    elif seed % 3 == 2:
        for pid in (0, 1):
            e.players[pid]["x"] = rng.uniform(105, 140) * T
            e.players[pid]["y"] = 18 * T
    issues = []
    stuck = {0: 0, 1: 0}
    last_pos = {pid: (e.players[pid]["x"], e.players[pid]["y"]) for pid in (0, 1)}
    for i in range(ticks):
        inp = {0: rand_input(rng), 1: rand_input(rng)}
        e.step(inp, core.TICK_DT)
        check_invariants(e, "seed%d tick%d" % (seed, i), issues)
        if len(issues) > 12:
            break
        # 长时间不动且按着方向键 -> 可能卡死
        for pid in (0, 1):
            p = e.players[pid]
            dx = abs(p["x"] - last_pos[pid][0]) + abs(p["y"] - last_pos[pid][1])
            pressing = inp[pid].get("left") or inp[pid].get("right")
            if dx < 0.2 and pressing and p["hp"] > 0:
                stuck[pid] += 1
            else:
                stuck[pid] = 0
            last_pos[pid] = (p["x"], p["y"])
            if stuck[pid] == 150:      # 5 秒按着方向键却纹丝不动
                issues.append("seed%d tick%d: 玩家%d 疑似卡死 (%0.f,%.0f)"
                              % (seed, i, pid, p["x"], p["y"]))
    return issues


def main():
    all_issues = []
    for seed in range(1, 13):
        try:
            issues = run_fuzz(seed, 3000)
        except Exception:
            issues = ["seed%d 抛异常:\n%s" % (seed, traceback.format_exc())]
        if issues:
            all_issues.extend(issues)
            print("seed %2d  ->  %d 个问题" % (seed, len(issues)))
        else:
            print("seed %2d  ->  OK" % seed)
    print("=" * 60)
    for s in all_issues[:30]:
        print(" *", s)
    print("总计 %d 个问题" % len(all_issues))
    return 1 if all_issues else 0


if __name__ == "__main__":
    sys.exit(main())
