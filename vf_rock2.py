import game_core as core
import fx

T = core.TILE
print("=== 受击震屏强度对比（连续被打 3 次）===")
c = fx.Camera(800, 450)
for i in range(3):
    c.add_trauma(0.15)          # 新的 hurt 值
    mag = c.trauma ** 2
    print(" 第%d次受击 trauma=%.3f 最大偏移=%.1fx%.1f px" % (i + 1, c.trauma, 12.5 * mag, 9.5 * mag))
print("（旧版：每次 +0.3 线性叠加，第3次 trauma=0.9 -> 偏移 10.1x7.7）")

print("\n=== 落石：三条都落在真实地表，不穿地 ===")
for rid in ("F1", "F2", "F3"):
    e = core.GameEngine()
    e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
    r = next(x for x in e._fall_rocks if x["id"] == rid)
    p = e.players[0]
    p["x"], p["y"] = r["x"], 19 * T
    seen = []
    deepest = 0
    for f in range(360):
        p["hp"] = p["maxhp"]
        e.step({}, core.TICK_DT)
        if r["state"] not in seen:
            seen.append(r["state"])
        deepest = max(deepest, r["y"])
    ok = deepest <= r["land_y"] + 1
    print(" %s 状态链=%s land_y=%.0f 最深=%.0f %s"
          % (rid, seen, r["land_y"], deepest, "OK" if ok else "穿地!"))
