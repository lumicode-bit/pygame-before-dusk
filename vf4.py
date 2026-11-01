import game_core as core

T = core.TILE

print("=== 熔炉段（col 100 -> 151）可通行性：逐段推进，记录卡点 ===")
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
# 先把双人闸门打开（模拟另一人已踩）
e._open_duo_gate()
p = e.players[0]
p["x"], p["y"] = 100 * T + 16, 19 * T
best = p["x"]
stall = 0
last = p["x"]
for f in range(60 * 90):
    inp = {"right": True, "mx": p["x"] + 120, "my": p["y"] - 30}
    acx = int((p["x"] + 30) // T)
    foot = int((p["y"] - 2) // T)
    if p["on_ground"] and any(e._solid_at(acx, foot - u) for u in (1, 2, 3)):
        inp["up"] = True
    if p["vine"] >= 0:
        e.step({0: {"down": True}}, core.TICK_DT)
        continue
    p["hp"] = p["maxhp"]
    e.step({0: inp}, core.TICK_DT)
    best = max(best, p["x"])
    if p["x"] > last + 8:
        last = p["x"]; stall = 0
    else:
        stall += 1
    if stall > 300:
        print(" 卡在 x=%.0f (col %.1f) y=%.0f" % (p["x"], p["x"] / T, p["y"]))
        break
print(" 最远 x=%.0f (col %.1f) 终点在 col 151 -> %s"
      % (best, best / T, "通过" if best > 149 * T else "未通过"))
