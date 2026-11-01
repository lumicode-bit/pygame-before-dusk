import game_core as core
T = core.TILE
e = core.GameEngine()
for frame in range(60 * 70):
    i0 = core.make_ai_input(0, e, 1, "follow")
    i1 = core.make_ai_input(1, e, 0, "follow")
    e.step({0: i0, 1: i1}, core.TICK_DT)
    if frame % 300 == 0:
        p0, p1 = e.players[0], e.players[1]
        print("f%04d 弓 x=%.0f(%.1fcol) y=%.0f hp=%.0f vine=%d | 盾 x=%.0f y=%.0f hp=%.0f vine=%d | 怪=%d 波=%d 门=%s kills=%d"
              % (frame, p0["x"], p0["x"] / T, p0["y"], p0["hp"], p0["vine"],
                 p1["x"], p1["y"], p1["hp"], p1["vine"],
                 len(e.monsters), e.wave, e.portal_active, e.kills))
print("\n=== 最后 3 秒逐帧（弓）===")
for frame in range(180):
    i0 = core.make_ai_input(0, e, 1, "follow")
    i1 = core.make_ai_input(1, e, 0, "follow")
    e.step({0: i0, 1: i1}, core.TICK_DT)
    if frame % 20 == 0:
        p0 = e.players[0]
        print(" x=%.0f y=%.0f vy=%.1f on_ground=%s vine=%d inp L=%s R=%s U=%s"
              % (p0["x"], p0["y"], p0["vy"], p0["on_ground"], p0["vine"],
                 i0.get("left"), i0.get("right"), i0.get("up")))
print("\n怪物列表:", [(m.kind, round(m.x / T, 1), round(m.y), round(m.hp, 1)) for m in e.monsters])
print("wave1_spawned=%s _wave1_timer=%.1f" % (e.wave1_spawned, getattr(e, "_wave1_timer", -1)))
