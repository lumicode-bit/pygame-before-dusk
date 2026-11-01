import game_core as core

T = core.TILE
e = core.GameEngine()
g = core.build_static_grid()

print("=== 扫描：每一列从 row 19 往上的第一块实体顶面（地面高度）===")
prev = None
gaps = []
for c in range(core.MAP_W):
    top = None
    for r in range(19, 28):
        if g[r][c] != ' ':
            top = r
            break
    if top is None:
        gaps.append((c, "无地面"))
        continue
    if prev is not None and top != prev:
        gaps.append((c, "地面高度突变 row %d -> %d" % (prev, top)))
    prev = top

print("异常列:", gaps if gaps else "无（地面 row 19 连续）")

print("\n=== 已知设计上的空洞（断崖/深坑）===")
print(" A断崖 col 36-43:", [g[19][c] for c in range(36, 44)])
print(" 深坑 col 90-93:", [g[19][c] for c in range(90, 94)])

print("\n=== 每列最高可站立面（玩家可能需要跳上去的平台）===")
prof = []
for c in range(core.MAP_W):
    top = None
    for r in range(5, 28):
        if g[r][c] != ' ':
            top = r
            break
    prof.append((c, top))
# 找"孤立高台"：某列比左右两列都高很多，且顶部没有连通
odd = []
for i in range(1, len(prof) - 1):
    c, t = prof[i]
    if t is None:
        continue
    l, r = prof[i - 1][1], prof[i + 1][1]
    if l is not None and r is not None and t < l - 2 and t < r - 2:
        odd.append((c, t, l, r))
print("孤立尖峰列:", odd[:10] if odd else "无")

print("\n=== 检查所有补给箱是否站在实心面上 ===")
for ch in e._chests:
    cx = int(ch["x"] // T)
    row = int(ch["gy"] // T)
    ok = e._solid_at(cx, row)
    print(" %s col=%3d gy=%4.0f -> row %d 实体=%s %s"
          % (ch["id"], cx, ch["gy"], row, ok, "OK" if ok else "!! 悬空"))
