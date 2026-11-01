import random
import game_core as core

T = core.TILE
random.seed(20261027)

# 复现 trial=5 pid=0 在 x=4851 悬空卡住
for trial in range(6):
    e = core.GameEngine()
    e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
    seg = trial % 5
    base = [10, 50, 70, 95, 140][seg] * T
    for pid in (0, 1):
        p = e.players[pid]
        p["x"] = float(base + pid * 40)
        p["y"] = 15 * T
    for f in range(4000):
        inp = {}
        for pid in (0, 1):
            inp[pid] = {
                "left": random.random() < 0.12, "right": random.random() < 0.45,
                "up": random.random() < 0.10, "down": random.random() < 0.03,
                "dash": random.random() < 0.05, "shoot": random.random() < 0.2,
                "sword": random.random() < 0.2, "block": random.random() < 0.1,
                "interact": random.random() < 0.05,
                "mx": e.players[pid]["x"] + random.uniform(-200, 400),
                "my": e.players[pid]["y"] - random.uniform(0, 160),
            }
        e.step(inp, core.TICK_DT)
        if trial == 5 and f in (1690, 1697, 1700):
            p = e.players[0]
            print("trial5 f%d: x=%.2f y=%.2f vy=%.1f on_ground=%s vine=%d solid=%s hp=%.0f"
                  % (f, p["x"], p["y"], p["vy"], p["on_ground"], p["vine"],
                     e._rect_solid(p["x"], p["y"], core.PLAYER_W, core.PLAYER_H), p["hp"]))
            print("       上方格子:", [(r, e._solid_at(int(p["x"] // T), r)) for r in range(8, 16)])
            print("       脚格:", int(p["y"] // T), "solid=", e._solid_at(int(p["x"] // T), int(p["y"] // T)))
