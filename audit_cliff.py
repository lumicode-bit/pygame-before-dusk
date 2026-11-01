import game_core as core

T = core.TILE
print("跳板配置:", getattr(core, "PAD_CONFIGS", "?"))
for cfg in getattr(core, "PAD_CONFIGS", []):
    print("  pad:", cfg)

# 从各种起跳点试弹射，看能否越过断崖
for sx in (1100, 1120, 1140, 1160, 1180):
    best_x = sx
    e = core.GameEngine()
    e.monsters.clear(); e.wave1_spawned = True
    p = e.players[0]
    p["x"], p["y"] = sx, 19 * T
    for f in range(150):
        inp = {"right": True, "up": (f < 3),
               "mx": p["x"] + 100, "my": p["y"] - 20}
        e.step({0: inp}, core.TICK_DT)
        best_x = max(best_x, p["x"])
        if p["hp"] <= 0:
            break
    print("起跳 x=%d -> 最远 x=%.0f (col %.1f) hp=%.0f" % (sx, best_x, best_x / T, p["hp"]))

# 断崖范围
print("\n=== 断崖区域地形 ===")
g = core.build_static_grid()
for c in range(34, 46):
    col = "".join(g[r][c] for r in range(17, 22))
    print(" col %2d: %s" % (c, col))
