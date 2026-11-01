import game_core as core
T = core.TILE
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True
p1 = e.players[1]
p1["x"], p1["y"] = 4 * T + 16, 19 * T
for i in range(10):
    e.step({}, core.TICK_DT)
print("盾卫 x=%.2f y=%.2f on_ground=%s" % (p1["x"], p1["y"], p1["on_ground"]))
print("盾卫矩形 y: %.2f ~ %.2f" % (p1["y"] - core.PLAYER_H, p1["y"]))
print("机关矩形 y: %d ~ %d" % (19 * T, 19 * T + T))
print("机关 active:", [p["active"] for p in e.plates], "pads:", len(e.pads))

# 双人闸门
e2 = core.GameEngine()
e2.monsters.clear(); e2.wave1_spawned = True
c0, c1 = core.DUO_PLATE_COLS
e2.players[0]["x"], e2.players[0]["y"] = c0 * T + 16, 19 * T
e2.players[1]["x"], e2.players[1]["y"] = c1 * T + 16, 19 * T
for i in range(30):
    e2.step({}, core.TICK_DT)
print("\n双人闸门: hold=%.2f open=%s 门格=%r"
      % (getattr(e2, "_duo_hold", -1), e2.duo_gate_open, e2.grid[15][core.DUO_GATE_COL]))

# 把玩家 y 抬高 2px 再试
e3 = core.GameEngine()
e3.monsters.clear(); e3.wave1_spawned = True
e3.players[1]["x"], e3.players[1]["y"] = 4 * T + 16, 19 * T + 2
for i in range(10):
    e3.step({}, core.TICK_DT)
print("\n抬高 2px: y=%.2f 机关 active=%s pads=%d"
      % (e3.players[1]["y"], [p["active"] for p in e3.plates], len(e3.pads)))
