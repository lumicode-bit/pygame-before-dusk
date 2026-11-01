"""验证审计报告的玩法级断言 5-9。"""
import game_core as core

T = core.TILE
print("=== 5. 摆锤打不到地面玩家 ===")
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
h = next(iter(e._hammers.values())) if isinstance(e._hammers, dict) else e._hammers[0]
p = e.players[0]
p["x"], p["y"] = h["bx"], 19 * T
hp0 = p["hp"]
for f in range(60 * 12):
    p["hp"] = max(p["hp"], 1)  # 不让死，只看掉血
    e.step({}, core.TICK_DT)
print(" 地面 12s: hp %.0f -> %.0f %s" % (hp0, p["hp"], "打不到" if p["hp"] >= hp0 else "能打到"))
print(" 锤头 by=%.0f 地面玩家中心=%.0f 差=%.0f 阈值=r%.0f+24" %
      (h["by"], 19 * T - core.PLAYER_H / 2,
       abs(h["by"] - (19 * T - core.PLAYER_H / 2)), h["r"]))

print("\n=== 6. 双人闸门跳跃翻越 ===")
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
p = e.players[0]
gx = core.DUO_GATE_COL * T
p["x"], p["y"] = gx - 3 * T, 19 * T
p["hp"] = 9999
crossed = False
for f in range(60 * 6):
    i = {"right": True, "up": (f % 30 < 3), "mx": p["x"] + 120, "my": p["y"] - 30}
    e.step({0: i}, core.TICK_DT)
    if p["x"] > gx + core.TILE:
        crossed = True
        print(" 第%d帧越过闸门 x=%.0f y=%.0f 开门=%s" % (f, p["x"], p["y"], e.duo_gate_open))
        break
print(" 跳跃翻越:", "成立" if crossed else "不成立")

print("\n=== 7. 死在藤蔓上复活被拽回 ===")
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
p = e.players[0]
# 挂上藤蔓
vine_x = e.vines[0][0]
p["x"], p["y"] = vine_x, e.vines[0][1]
p["vine"] = 0
e.step({}, core.TICK_DT)
print(" 挂藤蔓后 vine=%d pos=(%.0f,%.0f)" % (p["vine"], p["x"], p["y"]))
# 死亡 -> 复活
p["hp"] = 0
p["vine"] = 0
e._respawn_all(0)
print(" 复活后 vine=%d pos=(%.0f,%.0f)" % (p["vine"], p["x"], p["y"]))
e.step({}, core.TICK_DT)
print(" 1 tick 后 vine=%d pos=(%.0f,%.0f) %s" % (p["vine"], p["x"], p["y"],
      "被拽回藤蔓!" if p["vine"] >= 0 else "正常"))

print("\n=== 8. AI 弓箭手对地面怪空射 ===")
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
g = core.Monster(1, "ground", 30 * T, 19 * T)
e.monsters.append(g)
e.players[0]["x"], e.players[0]["y"] = 20 * T, 19 * T
e.players[1]["x"], e.players[1]["y"] = 20 * T + 40, 19 * T
e.ai_pid = 1
arrows0 = len(e.arrows)
shoot_ticks = 0
for f in range(60 * 5):
    i1 = core.make_ai_input(1, e, 0, "follow")
    if i1.get("shoot"):
        shoot_ticks += 1
    e.step({1: i1}, core.TICK_DT)
print(" 5s: shoot按下=%d帧 发箭=%d %s" % (shoot_ticks, len(e.arrows) - arrows0,
      "空射" if len(e.arrows) == arrows0 else "有输出"))

print("\n=== 9. 守点 AI 被归队兜底传走 ===")
e = core.GameEngine()
e.monsters.clear(); e.wave1_spawned = True; e.rifts = []
p1 = e.players[1]
p1["x"], p1["y"] = 4 * T + 16, 19 * T   # 守在 col4 机关
e.players[0]["x"], e.players[0]["y"] = 46 * T, 19 * T
e.ai_order = ("guard", (4 * T + 16, 19 * T)) if hasattr(e, "ai_order") else None
x0 = p1["x"]
teleported = False
for f in range(60 * 8):
    e.step({0: {}}, core.TICK_DT)
    if abs(p1["x"] - x0) > 300:
        teleported = True
        print(" 第%d帧被传到 x=%.0f（原 x=%.0f）" % (f, p1["x"], x0))
        break
print(" 守点被传走:", "成立" if teleported else "不成立")
