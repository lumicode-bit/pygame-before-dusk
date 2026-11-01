"""精确扫描：短输入，只看"卡住"和"埋进地里"，不让人跑远。"""
import game_core as core

T = core.TILE


def probe(x, y_start, direction, frames=14):
    e = core.GameEngine()
    e.monsters.clear()
    e.wave1_spawned = True
    e.rifts = []
    p = e.players[0]
    p["x"], p["y"] = float(x), float(y_start)
    for _ in range(20):
        e.step({}, core.TICK_DT)          # 落到实地
    if p["hp"] <= 0:
        return ("died_falling", p, e)
    x0, y0 = p["x"], p["y"]
    inp = {"right": direction > 0, "left": direction < 0,
           "mx": p["x"] + 100 * direction, "my": p["y"] - 20}
    for _ in range(frames):
        e.step({0: inp}, core.TICK_DT)
    moved = abs(p["x"] - x0)
    # 埋进地形：脚上方 4px 那格是实心
    foot_cell = e._solid_at(int(p["x"] // T), int((p["y"] - 4) // T))
    # 落得更深（掉下去了）
    deeper = p["y"] - y0
    return ("moved" if moved > 3 else "stuck", p, e, moved, foot_cell, deeper)


print("列   右移  左移  埋地  位移  深降  血量  末y")
bad = []
for c in range(2, core.MAP_W - 1):
    x = c * T + 16
    results = []
    for d in (1, -1):
        r = probe(x, 5 * T, d)
        if r[0] == "died_falling":
            results.append(None)
            continue
        _, p, e, moved, foot, deeper = r
        results.append((moved, foot, deeper, p["hp"], p["y"], p["on_ground"]))
    if None in results:
        continue
    r0, r1 = results
    stuck_r = r0[0] <= 3
    stuck_l = r1[0] <= 3
    buried = r0[1] or r1[1]
    hp = min(r0[3], r1[3])
    # 只有"卡住"或"埋地"才算问题；掉坑被扎死是设计
    if buried or (stuck_r and stuck_l) or hp <= 0:
        bad.append((c, stuck_r, stuck_l, buried, round(r0[0]), round(r1[0]), round(r0[2]), hp, round(r0[4])))
        print(" %3d  %-5s %-5s %-5s %4.0f %4.0f %5.0f %5.0f %5.0f  <--"
              % (c, stuck_r, stuck_l, buried, r0[0], r1[0], r0[2], hp, r0[4]))
print("\n合计异常列:", len(bad))
print("明细:", bad)
