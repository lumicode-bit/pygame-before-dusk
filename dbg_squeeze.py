import game_core as core

T = core.TILE
print("=== 场景：玩家站在祭坛左壁旁（台阶上），Boss 从左边冲锋撞过来 ===")
for px in (4400, 4420, 4435, 4440):
    e = core.GameEngine()
    e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
    p = e.players[0]
    p["x"], p["y"] = float(px), 17 * T      # 台阶顶 544
    e.players[1]["x"], e.players[1]["y"] = float(px - 60), 17 * T
    b = core.Monster(1, "boss", float(px - 160), float(15 * T))
    b.state = "charge"
    b.state_t = 0.0
    b.dir = 1
    b.vx = core.BOSS_CHARGE_SPEED
    e.monsters.append(b)
    worst_y, min_x, max_x = p["y"], p["x"], p["x"]
    buried_frames = 0
    for f in range(40):
        e.step({}, core.TICK_DT)
        worst_y = max(worst_y, p["y"])
        min_x = min(min_x, p["x"])
        max_x = max(max_x, p["x"])
        if e._solid_at(int(p["x"] // T), int((p["y"] - 6) // T)):
            buried_frames += 1
    foot = e._solid_at(int(p["x"] // T), int((p["y"] - 6) // T))
    print(" 起点 x=%d -> 末 x=%.0f y=%.0f 范围x[%.0f,%.0f] 最深y=%.0f 埋地帧=%d 末脚在实体=%s hp=%.0f"
          % (px, p["x"], p["y"], min_x, max_x, worst_y, buried_frames, foot, p["hp"]))

print("\n=== 场景：玩家站在祭坛上，Boss 从右往左撞（推向地图右端）===")
for px in (4750, 4800, 4820):
    e = core.GameEngine()
    e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
    p = e.players[0]
    p["x"], p["y"] = float(px), 15 * T
    b = core.Monster(1, "boss", float(px + 150), float(15 * T))
    b.state = "charge"
    b.state_t = 0.0
    b.dir = -1
    b.vx = -core.BOSS_CHARGE_SPEED
    e.monsters.append(b)
    worst_y = p["y"]
    buried = 0
    for f in range(40):
        e.step({}, core.TICK_DT)
        worst_y = max(worst_y, p["y"])
        if e._solid_at(int(p["x"] // T), int((p["y"] - 6) // T)):
            buried += 1
    print(" 起点 x=%d -> 末 x=%.0f y=%.0f 最深y=%.0f 埋地帧=%d hp=%.0f"
          % (px, p["x"], p["y"], worst_y, buried, p["hp"]))
