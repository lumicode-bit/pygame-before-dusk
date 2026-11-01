# -*- coding: utf-8 -*-
"""机器人玩家：两个角色都由 AI 托管，跑完整关，用来验证"AI 能不能真的通关"。

做法：给两个 AI 一个共同的**汇合点**（waypoint），而不是互相跟随。
互相跟随会在两人站到一起后各自判定"已到达"而双双僵死 —— 真实对局里
人类玩家会自己往前走，所以这个问题只在"全 AI"时暴露。

用法：
    python -B tools/bot_run.py            # 跑 120 秒
    python -B tools/bot_run.py 300        # 跑 300 秒
    python -B tools/bot_run.py 300 --god  # 锁血，只验证地形通行能力
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import game_core as core  # noqa: E402

TILE = core.TILE

# 关卡路标（列, 站立行）。队伍两人都越过才切下一个。
WAYPOINTS = [
    (10, 19),    # 出生地
    (33, 19),    # 压力机关触发带（盾卫会回去踩）
    (44, 19),    # A 断崖（踩跳板）
    (50, 19),
    (58, 19),    # 岩壁之后
    (82, 19),    # 跨过岩浆坑（AI 只在目标在 78 列以东时才骑板过坑）
    (86, 19),    # 岩浆右岸
    (94, 19),    # 深坑右岸
    (100, 15),   # 瞭望塔
    (110, 19),
    (114, 19),   # 双人闸门
    (122, 19),
    (132, 19),   # Boss 区
    (142, 15),   # 传送门
]


def describe(eng):
    p0, p1 = eng.players[0], eng.players[1]
    return ("[%5.1fs t=%4d] 弓(%5.1f,%4.1f hp%3d) 盾(%5.1f,%4.1f hp%3d) "
            "波次=%s 闸门=%s 符文=%s 怪=%d 死=%d %s" % (
                eng.tick * core.TICK_DT, eng.tick,
                p0["x"] / TILE, p0["y"] / TILE, p0["hp"],
                p1["x"] / TILE, p1["y"] / TILE, p1["hp"],
                eng.wave, eng.duo_gate_open, eng.rune_open,
                len(eng.monsters), eng.deaths, eng.msg))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    god = "--god" in sys.argv          # 锁血，只测"能不能走过去"
    seconds = float(args[0]) if args else 120.0
    eng = core.GameEngine()
    eng.ai_pid = None          # 关掉"归队传送"兜底，才能看到真实的 AI 能力
    dt = core.TICK_DT
    steps = int(seconds / dt)
    wp = 0
    best_x = 0.0
    stuck_t = 0.0
    t0 = time.time()

    for i in range(steps):
        wx, wy = WAYPOINTS[wp]
        lead = (wx * TILE + TILE / 2, wy * TILE)
        # 只有"领队"（弓箭手）看路标；盾卫照旧跟随领队 —— 这样两人不会走散，
        # 也复现真实单人局里"人类在前、AI 在后"的关系。
        inputs = {}
        for pid, other in ((0, 1), (1, 0)):
            try:
                inputs[pid] = core.make_ai_input(pid, eng, other,
                                                 lead=lead if pid == 0 else None)
            except Exception as e:
                print("AI 生成输入异常 pid=%d: %r" % (pid, e))
                inputs[pid] = {}
        eng.step(inputs, dt)
        if god:
            for p in eng.players.values():
                p["hp"] = p["maxhp"]

        # 领队到路标就推进（留 1 格容差）。盾卫自己会跟上来 ——
        # 要求"两人都到"会让领队在机关带上原地等，和跑回去踩机关的盾卫互相僵住。
        if wp < len(WAYPOINTS) - 1:
            reached = eng.players[0]["x"] >= wx * TILE - TILE
            if reached:
                wp += 1
                print("   -> 路标 %d/%d  x=%d 列  t=%.1fs" %
                      (wp, len(WAYPOINTS) - 1, WAYPOINTS[wp][0], eng.tick * dt))

        if eng.win:
            print(describe(eng))
            print("*** 通关！用时 %.1fs，死亡 %d 次 ***" % (eng.tick * dt, eng.deaths))
            return 0

        if eng.tick % int(2.0 / dt) == 0:
            print(describe(eng))

        cur = eng.players[0]["x"]
        if cur > best_x + TILE * 0.5:
            best_x = cur
            stuck_t = 0.0
        else:
            stuck_t += dt
            if stuck_t > 10.0:
                print("!! 10 秒无推进：弓(%.1f,%.1f) 盾(%.1f,%.1f) 路标=%d(%d 列)" % (
                    eng.players[0]["x"] / TILE, eng.players[0]["y"] / TILE,
                    eng.players[1]["x"] / TILE, eng.players[1]["y"] / TILE,
                    wp, wx))
                print("   墙体剩余: %s" % sorted(eng.rocks.items()))
                return 2

    print(describe(eng))
    print("超时 %.0fs 未通关。路标 %d/%d，队伍最靠后 x=%.1f 格" %
          (seconds, wp, len(WAYPOINTS) - 1, best_x / TILE))
    print("墙体剩余: %s" % sorted(eng.rocks.items()))
    return 1


if __name__ == "__main__":
    sys.exit(main())
