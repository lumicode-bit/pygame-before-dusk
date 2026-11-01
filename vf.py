import game_core as c
g = c.build_static_grid()
print("col151 rows15-19:", [g[r][151] for r in range(15, 20)])
e = c.GameEngine()
e.monsters.clear(); e.wave1_spawned = True
q = e.players[0]
q["x"], q["y"] = 4851, 480
for _ in range(60):
    e.step({}, c.TICK_DT)
print("x=4851 -> y=%.0f on_ground=%s" % (q["y"], q["on_ground"]))

# 被 Boss 一路推到最右，看会不会掉下去
e2 = c.GameEngine()
e2.monsters.clear(); e2.wave1_spawned = True
q = e2.players[0]
q["x"], q["y"] = 144 * c.TILE, 480
worst = q["y"]
for f in range(240):
    e2.step({0: {"right": True, "mx": q["x"] + 200, "my": q["y"] - 20}}, c.TICK_DT)
    worst = max(worst, q["y"])
print("一路向右 4 秒: 末 x=%.0f y=%.0f 最低 y=%.0f (都不该超过 480)" % (q["x"], q["y"], worst))
