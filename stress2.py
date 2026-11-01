"""压力测试 v2：卡住判定加 on_ground，埋地要求连续 8 帧（排除过渡帧）。"""
import random
import game_core as core

T = core.TILE
random.seed(20261027)

buried = []
frozen = []
for trial in range(8):
    e = core.GameEngine()
    e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
    seg = trial % 5
    base = [10, 50, 70, 95, 140][seg] * T
    for pid in (0, 1):
        p = e.players[pid]
        p["x"] = float(base + pid * 40)
        p["y"] = 6 * T                      # 从高空落下，别直接塞进平台里
    last_x = [e.players[0]["x"], e.players[1]["x"]]
    still = [0, 0]
    bury_run = [0, 0]
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
        for pid in (0, 1):
            p = e.players[pid]
            if p["hp"] <= 0:
                still[pid] = 0; bury_run[pid] = 0
                last_x[pid] = p["x"]
                continue
            if p.get("vine", -1) < 0 and e._rect_solid(p["x"], p["y"], core.PLAYER_W, core.PLAYER_H):
                bury_run[pid] += 1
                if bury_run[pid] == 8:        # 连续 8 帧都埋 = 真问题
                    buried.append((trial, pid, f, round(p["x"]), round(p["y"])))
            else:
                bury_run[pid] = 0
            if abs(p["x"] - last_x[pid]) < 0.4 and p["on_ground"]:
                still[pid] += 1
                if still[pid] == 120:          # 站着 2 秒不动
                    frozen.append((trial, pid, f, round(p["x"]), round(p["y"]), round(p["hp"])))
            else:
                still[pid] = 0
            last_x[pid] = p["x"]

print("真埋地（连续8帧）:", len(buried), buried[:6])
print("真卡住（站着2秒不动）:", len(frozen))
for x in frozen[:8]:
    print("  trial=%d pid=%d f=%d x=%d y=%d hp=%d" % x)
print("\n结论: 埋地=%s 卡死=%s" % ("无" if not buried else "有", "无" if not frozen else "有"))
