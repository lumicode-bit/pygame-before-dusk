import game_core as core

T = core.TILE
bad = []
for trial in range(6):
    e = core.GameEngine()
    e.monsters.clear()
    e.wave = 2
    e.wave2_spawned = True
    e.wave1_spawned = True
    e.players[0]["x"], e.players[0]["y"] = core.BOSS_TRIGGER_X + 30, 19 * T
    e.players[1]["x"], e.players[1]["y"] = core.BOSS_TRIGGER_X - 70, 19 * T
    for _ in range(3):
        e.step({}, core.TICK_DT)
    for r in e.rifts:
        r["t"] = r["delay"]
    e.step({}, core.TICK_DT)
    for m in e.monsters:
        if m.state == "spawn":
            m.state_t = 0.0
    e.step({}, core.TICK_DT)

    deepest = 0
    for f in range(60 * 25):          # 25 秒
        # 玩家不停往右挤（模拟被冲锋一路推）
        i0 = {"right": True, "mx": e.players[0]["x"] + 150, "my": e.players[0]["y"] - 30}
        i1 = {"right": True, "mx": e.players[1]["x"] + 150, "my": e.players[1]["y"] - 30}
        if f % 20 < 2:
            i0["up"] = i1["up"] = True
        e.step({0: i0, 1: i1}, core.TICK_DT)
        for pid, p in e.players.items():
            if p["y"] > 19 * T + 2:      # 比地面还深 = 穿地
                bad.append((trial, pid, f, round(p["x"]), round(p["y"])))
            deepest = max(deepest, p["y"])
        if e.win:
            break
    print("trial %d: win=%s 末 x0=%.0f y0=%.0f x1=%.0f y1=%.0f 最深y=%.0f 死亡=%d"
          % (trial, e.win, e.players[0]["x"], e.players[0]["y"],
             e.players[1]["x"], e.players[1]["y"], deepest, e.deaths))
print("\n穿地记录:", bad[:5] if bad else "无")
