import game_core as core

T = core.TILE
print("=== 盾卫剑击碎岩石 ===")
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
# 找一块岩石（火箭墙 col54/55 rows18+）
rocks = [(cx, cy) for (cx, cy), hp in e.rocks.items() if hp > 0]
print(" 岩石格数:", len(rocks), "例:", rocks[:4])
if rocks:
    cx, cy = rocks[0]
    p = e.players[1]      # 盾卫
    p["x"], p["y"] = (cx - 1) * T + 16, cy * T + T
    p["facing"] = 1
    hp0 = e.rocks.get((cx, cy), core.ROCK_HP)
    for f in range(60):
        e.step({1: {"sword": True}}, core.TICK_DT)
    hp1 = e.rocks.get((cx, cy), 0)
    print(" 岩石 hp %d -> %s（击碎=%s）" % (hp0, hp1 if (cx, cy) in e.rocks else "已碎",
          (cx, cy) not in e.rocks))

print("\n=== 箭依然能碎（回归）===")
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
rocks = [(cx, cy) for (cx, cy), hp in e.rocks.items() if hp > 0]
if rocks:
    cx, cy = rocks[0]
    p = e.players[0]
    p["x"], p["y"] = (cx - 4) * T, 19 * T
    for f in range(120):
        e.step({0: {"shoot": True, "mx": cx * T + 16, "my": cy * T + 16}}, core.TICK_DT)
    print(" 岩石已碎:", (cx, cy) not in e.rocks)
