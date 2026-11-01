import game_core as core

T = core.TILE
print("=== 落石落地高度是否与真实地形一致 ===")
e = core.GameEngine()
for r in e._fall_rocks:
    cx = int(r["x"] // T)
    print(" %s x=%4d(col %3d) y0=%3.0f land_y=%.0f 该列地表=%s"
          % (r["id"], r["x"], cx, r["y0"], r["land_y"],
             [yy * T for yy in range(core.MAP_H) if e._solid_at(cx, yy)][:3]))

print("\n=== 实际触发一次：石头会不会穿地 ===")
for rid in ("F1", "F2", "F3"):
    e = core.GameEngine()
    e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
    r = next(x for x in e._fall_rocks if x["id"] == rid)
    p = e.players[0]
    p["x"], p["y"] = r["x"], 19 * T
    worst = 0
    states = []
    for f in range(400):
        e.step({}, core.TICK_DT)
        if r["state"] not in states:
            states.append(r["state"])
        if r["state"] in ("fall", "rest"):
            worst = max(worst, r["y"])
    print(" %s 状态=%s 最深 y=%.0f land_y=%.0f 末 y=%.0f 穿地=%s"
          % (rid, states, worst, r["land_y"], r["y"], worst > r["land_y"] + 2))
