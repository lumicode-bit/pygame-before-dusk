import game_core as core

T = core.TILE
print("=== 祭坛区地形（col 134-150, row 14-21）===")
g = core.build_static_grid()
for c in range(134, 151):
    col = "".join(g[r][c] for r in range(14, 22))
    print(" col %3d (x=%d): %s" % (c, c * T, col))
print(" 图例: 行14..21 从上到下, 空格=空, G=石")

print("\n=== 从台阶走向祭坛，逐帧看是否穿地 ===")
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True
p = e.players[0]
for start_x, label in ((135 * T, "台阶前"), (137 * T, "台阶上"), (138 * T + 8, "台阶边缘")):
    p["x"], p["y"] = start_x, 17 * T
    p["vy"] = 0
    worst = 0
    for f in range(90):
        inp = {"right": True, "up": (f % 24 < 2),
               "mx": p["x"] + 100, "my": p["y"] - 20}
        e.step({0: inp}, core.TICK_DT)
        worst = max(worst, p["y"])
    print(" %s 起点x=%d -> 末 x=%.0f y=%.0f on_ground=%s 最深 y=%.0f (地面608)"
          % (label, start_x, p["x"], p["y"], p["on_ground"], worst))

print("\n=== 直接站在祭坛里的各个 x，看是否被卡/穿 ===")
for x in (137 * T, 138 * T, 139 * T, 139 * T + 16, 140 * T, 145 * T, 149 * T):
    e2 = core.GameEngine()
    e2.monsters.clear(); e2.wave1_spawned = True
    q = e2.players[0]
    q["x"], q["y"] = x, 15 * T - 60
    for _ in range(40):
        e2.step({}, core.TICK_DT)
    inside = e2._solid_at(int(q["x"] // T), int((q["y"] - 6) // T))
    print(" 放到 x=%4d(%.1fcol) y=%d -> 落底 y=%.0f on_ground=%s 脚在实体里=%s"
          % (x, x / T, 15 * T - 60, q["y"], q["on_ground"], inside))
