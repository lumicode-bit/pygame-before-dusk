import game_core as core

T = core.TILE
print("=== AI（盾卫）从台阶跟着玩家上祭坛 ===")
for player_x in (142 * T, 146 * T, 150 * T):
    e = core.GameEngine()
    e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
    p0, p1 = e.players[0], e.players[1]
    p0["x"], p0["y"] = float(player_x), 15 * T
    p1["x"], p1["y"] = 137 * T + 16, 17 * T      # AI 在台阶上
    stuck = 0
    last = p1["x"]
    for f in range(60 * 12):
        i1 = core.make_ai_input(1, e, 0, "follow")
        e.step({0: {}, 1: i1}, core.TICK_DT)
        if abs(p1["x"] - last) < 0.5 and p1["on_ground"]:
            stuck += 1
        else:
            stuck = 0
        last = p1["x"]
        if stuck > 240:
            break
    foot_bad = e._solid_at(int(p1["x"] // T), int((p1["y"] - 6) // T))
    print(" 玩家x=%4d -> AI x=%4.0f y=%3.0f on_ground=%s 埋地=%s 卡住帧=%d hp=%.0f"
          % (player_x, p1["x"], p1["y"], p1["on_ground"], foot_bad, stuck, p1["hp"]))

print("\n=== AI 从祭坛往左回台阶（下坡）===")
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
p0, p1 = e.players[0], e.players[1]
p0["x"], p0["y"] = 135 * T, 17 * T
p1["x"], p1["y"] = 145 * T, 15 * T
for f in range(60 * 10):
    i1 = core.make_ai_input(1, e, 0, "follow")
    e.step({0: {}, 1: i1}, core.TICK_DT)
print(" AI x=%.0f y=%.0f on_ground=%s hp=%.0f" % (p1["x"], p1["y"], p1["on_ground"], p1["hp"]))
