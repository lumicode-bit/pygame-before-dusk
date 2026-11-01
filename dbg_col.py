import game_core as core

T = core.TILE
for col in (87, 88, 95):
    e = core.GameEngine()
    e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
    p = e.players[0]
    p["x"], p["y"] = col * T + 16, 5 * T
    for _ in range(20):
        e.step({}, core.TICK_DT)
    print("\ncol %d 落地: x=%.0f y=%.0f hp=%.0f on_ground=%s"
          % (col, p["x"], p["y"], p["hp"], p["on_ground"]))
    last_hp = p["hp"]
    for f in range(14):
        e.step({0: {"right": True, "mx": p["x"] + 100, "my": p["y"] - 20}}, core.TICK_DT)
        if p["hp"] != last_hp or f % 4 == 0:
            evs = [ev[0] for ev in e.events]
            print("  f%02d x=%.0f y=%.0f hp=%.0f vine=%d events=%s"
                  % (f, p["x"], p["y"], p["hp"], p["vine"], evs))
            last_hp = p["hp"]
