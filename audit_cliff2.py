import game_core as core

T = core.TILE
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True
p0, p1 = e.players[0], e.players[1]

# 1) 盾卫站上 A 断崖前的机关（col 4）
p1["x"], p1["y"] = 4 * T + 16, 19 * T
p0["x"], p0["y"] = 30 * T, 19 * T
for _ in range(30):
    e.step({}, core.TICK_DT)
print("盾卫踩机关后跳板数:", len(e.pads),
      [(round(p[0]), round(p[1])) for p in e.pads])

# 2) 弓箭手向右跑，跳到跳板上
p0["x"], p0["y"] = 34 * T, 19 * T
best = p0["x"]
fired = False
for f in range(240):
    inp = {"right": True, "up": (f < 2 or (35.5 * T < p0["x"] < 38 * T and p0["on_ground"])),
           "mx": p0["x"] + 100, "my": p0["y"] - 20}
    e.step({0: inp}, core.TICK_DT)
    best = max(best, p0["x"])
    if p0["y"] < 19 * T - 40 and not fired:
        fired = True
        print("  f%03d 跳板弹起 x=%.0f y=%.0f vy=%.0f" % (f, p0["x"], p0["y"], p0["vy"]))
    if p0["x"] > 44 * T:
        print("  越过断崖！f%03d x=%.0f y=%.0f" % (f, p0["x"], p0["y"]))
        break
print("最远 x=%.0f (col %.1f) hp=%.0f 落崖=%s"
      % (best, best / T, p0["hp"], p0["hp"] <= 0))

# 3) 顺便看第二次能不能再生成（机关是否可重复）
p1["x"], p1["y"] = 4 * T + 16, 19 * T
for _ in range(20):
    e.step({}, core.TICK_DT)
print("12 秒内再踩机关，跳板数:", len(e.pads))
