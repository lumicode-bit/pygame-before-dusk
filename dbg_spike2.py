import game_core as core

T = core.TILE
print("=== 站在刀刺上：能否被弹开、会不会卡住/扎死 ===")
for hp0 in (80, 20, 10):
    e = core.GameEngine()
    e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
    p = e.players[0]
    p["x"], p["y"] = 110 * T + 16, 19 * T
    p["hp"] = hp0
    stuck = 0
    last = p["x"]
    minhp = hp0
    for f in range(240):
        e.step({}, core.TICK_DT)     # 完全不动，看被扎几次
        minhp = min(minhp, p["hp"])
    print(" 起始hp=%d -> 末 hp=%.0f x=%.0f 位移=%.0f 死亡=%s"
          % (hp0, p["hp"], p["x"], abs(p["x"] - (110 * T + 16)), p["hp"] <= 0))

print("\n=== 跑过刀刺带（正常通过）===")
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
p = e.players[0]
p["x"], p["y"] = 108 * T + 16, 19 * T
for f in range(120):
    e.step({0: {"right": True, "mx": p["x"] + 100, "my": p["y"] - 20}}, core.TICK_DT)
print(" 跑过 110-111 后: x=%.0f(%.1fcol) hp=%.0f 位移=%.0f" % (p["x"], p["x"] / T, p["hp"], p["x"] - (108 * T + 16)))

print("\n=== 残血 5 站在刀刺上是否会死 ===")
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
p = e.players[0]
p["x"], p["y"] = 110 * T + 16, 19 * T
p["hp"] = 5
for f in range(300):
    e.step({}, core.TICK_DT)
print(" hp=%.1f 死亡=%s" % (p["hp"], p["hp"] <= 0))
