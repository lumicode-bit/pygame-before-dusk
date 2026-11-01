import game_core as core

T = core.TILE
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
p = e.players[0]
p["x"], p["y"] = 112 * T + 16, 19 * T
target = core.DUO_PLATE_COLS[1] * T + 16
hit = False
for f in range(400):
    inp = {"right": True, "mx": p["x"] + 100, "my": p["y"] - 20}
    # 前方有台阶就跳
    acx = int((p["x"] + 30) // T)
    foot = int((p["y"] - 2) // T)
    if p["on_ground"] and any(e._solid_at(acx, foot - u) for u in (1, 2)):
        inp["up"] = True
    p["hp"] = p["maxhp"]          # 关掉伤害干扰，只测走位
    e.step({0: inp}, core.TICK_DT)
    if abs(p["x"] - target) < 26 and p["on_ground"]:
        hit = True
        print("到达机关: f=%d x=%.0f y=%.0f" % (f, p["x"], p["y"]))
        break
print("能否走到 col118 机关:", hit, "末 x=%.0f(%.1fcol) y=%.0f" % (p["x"], p["x"] / T, p["y"]))

# 两人到位 -> 闸门开 -> 能否继续走到闸门右侧
e.players[1]["x"], e.players[1]["y"] = core.DUO_PLATE_COLS[0] * T + 16, 19 * T
for _ in range(40):
    e.step({}, core.TICK_DT)
print("闸门 open=%s 门格=%r" % (e.duo_gate_open, e.grid[16][core.DUO_GATE_COL]))
p["x"], p["y"] = 119 * T, 19 * T
for f in range(120):
    e.step({0: {"right": True, "mx": p["x"] + 100, "my": p["y"] - 20}}, core.TICK_DT)
print("过闸门后: x=%.0f(%.1fcol) y=%.0f" % (p["x"], p["x"] / T, p["y"]))
