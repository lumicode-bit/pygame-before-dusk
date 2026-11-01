import game_core as core

T = core.TILE
g = core.build_static_grid()
print("=== 机关上方是否还有遮挡 ===")
bad = []
for r in range(core.MAP_H):
    for c in range(core.MAP_W):
        if g[r][c] in ('q', 'Q'):
            above = "".join(g[rr][c] for rr in range(max(0, r - 3), r))
            if any(ch != ' ' for ch in above):
                bad.append((c, r, above))
print("被压住:", bad if bad else "无")

print("\n=== 真实走位：从 col 112 走到 col 118 机关，能不能站上去 ===")
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
p = e.players[0]
p["x"], p["y"] = 112 * T + 16, 19 * T
for f in range(90):
    e.step({0: {"right": True, "mx": p["x"] + 100, "my": p["y"] - 20}}, core.TICK_DT)
print(" 走到 x=%.0f(%.1fcol) y=%.0f on_ground=%s" % (p["x"], p["x"] / T, p["y"], p["on_ground"]))

# 直接站上去
e.players[0]["x"], e.players[0]["y"] = core.DUO_PLATE_COLS[0] * T + 16, 19 * T
e.players[1]["x"], e.players[1]["y"] = core.DUO_PLATE_COLS[1] * T + 16, 19 * T
for _ in range(40):
    e.step({}, core.TICK_DT)
print("两人踩机关: hold=%.2f open=%s p1=(%.0f,%.0f)" % (e._duo_hold, e.duo_gate_open,
                                                       e.players[1]["x"], e.players[1]["y"]))
