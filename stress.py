"""随机压力测试：重点验证"嵌进实心格"和"长时间动不了"绝迹。

- 每帧检测：角色矩形是否与实心格重叠（=卡进地底）
- 连续 90 帧 x 几乎不变且 on_ground（=卡住动不了）
- 用固定种子，可复现
"""
import random
import game_core as core

T = core.TILE
random.seed(20261027)

buried = []
frozen = []
for trial in range(8):
    e = core.GameEngine()
    e.monsters.clear()
    e.wave1_spawned = True
    e.rifts = []
    # 把两个角色丢到地图不同区段
    seg = trial % 5
    base = [10, 50, 70, 95, 140][seg] * T
    for pid in (0, 1):
        p = e.players[pid]
        p["x"] = float(base + pid * 40)
        p["y"] = 15 * T

    last_x = [e.players[0]["x"], e.players[1]["x"]]
    still = [0, 0]
    for f in range(4000):
        inp = {}
        for pid in (0, 1):
            inp[pid] = {
                "left": random.random() < 0.12,
                "right": random.random() < 0.45,
                "up": random.random() < 0.10,
                "down": random.random() < 0.03,
                "dash": random.random() < 0.05,
                "shoot": random.random() < 0.2,
                "sword": random.random() < 0.2,
                "block": random.random() < 0.1,
                "interact": random.random() < 0.05,
                "mx": e.players[pid]["x"] + random.uniform(-200, 400),
                "my": e.players[pid]["y"] - random.uniform(0, 160),
            }
        e.step(inp, core.TICK_DT)

        for pid in (0, 1):
            p = e.players[pid]
            if p["hp"] <= 0:
                still[pid] = 0
                last_x[pid] = p["x"]
                continue
            # 卡进实心格（排除挂藤蔓，挂索时允许贴岩石）
            if p.get("vine", -1) < 0 and e._rect_solid(p["x"], p["y"], core.PLAYER_W, core.PLAYER_H):
                buried.append((trial, pid, f, round(p["x"]), round(p["y"])))
            if abs(p["x"] - last_x[pid]) < 0.4:
                still[pid] += 1
                if still[pid] == 90:
                    frozen.append((trial, pid, f, round(p["x"]), round(p["y"]),
                                   p["on_ground"], round(p["hp"])))
            else:
                still[pid] = 0
            last_x[pid] = p["x"]

print("嵌进实心格次数:", len(buried), buried[:6])
print("连续 90 帧不动次数:", len(frozen))
for x in frozen[:8]:
    print("  trial=%d pid=%d f=%d x=%d y=%d on_ground=%s hp=%d" % x)
print("\n最终: 埋地=%s 卡死=%s" % ("无" if not buried else "有", "无" if not frozen else "有"))
