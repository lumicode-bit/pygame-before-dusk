import game_core as core
T = core.TILE
e = core.GameEngine()
e.monsters.clear()
e.wave = 2
e.wave2_spawned = True
e.wave1_spawned = True
e.players[0]["x"] = core.BOSS_TRIGGER_X + 30
e.players[0]["y"] = 19 * T
e.players[1]["x"] = core.BOSS_TRIGGER_X - 70
e.players[1]["y"] = 19 * T
print("BOSS_TRIGGER_X =", core.BOSS_TRIGGER_X, "col", core.BOSS_TRIGGER_X / T)
for _ in range(3):
    e.step({}, core.TICK_DT)
print("rifts:", e.rifts)
for r in e.rifts:
    r["t"] = r["delay"]
e.step({}, core.TICK_DT)
print("monsters:", [(m.kind, round(m.x), round(m.y), m.state, round(m.state_t, 2), round(m.atk_cd, 2)) for m in e.monsters])
for m in e.monsters:
    if m.state == "spawn":
        m.state_t = 0.0
states = []
for f in range(200):
    e.step({}, core.TICK_DT)
    b = next((m for m in e.monsters if m.kind == "boss"), None)
    if b:
        if f % 20 == 0:
            print(" f%03d state=%s atk_cd=%.2f dx=%.0f dy=%.0f y=%.0f" %
                  (f, b.state, b.atk_cd, e.players[0]["x"] - b.x, e.players[0]["y"] - b.y, b.y))
        if b.state not in states:
            states.append(b.state)
print("状态序列:", states)
