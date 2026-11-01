"""全图扫描：找"卡进地底"和"卡住不能动"的点。

判定：
- 穿地 = 角色脚所在格是实心（身体嵌进砖里）
- 卡死 = 连续给方向输入 45 帧，x 位移 < 1px，且没有在下落
"""
import game_core as core

T = core.TILE
STEP = 8


def scan(x, y_start, direction):
    e = core.GameEngine()
    e.monsters.clear()
    e.wave1_spawned = True
    e.rifts = []
    p = e.players[0]
    p["x"], p["y"] = float(x), float(y_start)
    # 先稳定（重力落到位）
    for _ in range(20):
        e.step({}, core.TICK_DT)
    inside0 = e._solid_at(int(p["x"] // T), int((p["y"] - 4) // T))
    x0, y0 = p["x"], p["y"]
    inp = {"right": direction > 0, "left": direction < 0,
           "mx": p["x"] + 100 * direction, "my": p["y"] - 20}
    for _ in range(45):
        e.step({0: inp}, core.TICK_DT)
    moved = abs(p["x"] - x0)
    inside1 = e._solid_at(int(p["x"] // T), int((p["y"] - 4) // T))
    fell = p["y"] - y0 > 30
    stuck = (moved < 1.0) and not fell and p["on_ground"]
    buried = inside1 and not inside0
    return stuck, buried, p, e


print("=== 扫描每列（地面上方落位），左右各给一次输入 ===")
print("列   卡住(右) 卡住(左) 穿地  末y   血量")
problems = []
for c in range(2, core.MAP_W - 1):
    x = c * T + 16
    row = []
    for d in (1, -1):
        st, bu, p, e = scan(x, 6 * T, d)     # 从高空落下，模拟正常落地
        row.append((st, bu, p, e))
    stuck = row[0][0] or row[1][0]
    buried = row[0][1] or row[1][1]
    hp = min(row[0][2]["hp"], row[1][2]["hp"])
    y = row[0][2]["y"]
    if stuck or buried or hp <= 0:
        problems.append((c, stuck, buried, y, hp))
        print(" %3d   %-6s %-6s %-5s %5.0f %5.0f  <-- 异常"
              % (c, row[0][0], row[1][0], buried, y, hp))
print("\n异常点:", [(c, s, b, round(y), hp) for c, s, b, y, hp in problems] or "无")
