import game_core as c

T = c.TILE
e = c.GameEngine()
print("=== 每个补给箱：台面 y / 箱子底 y / 差值 ===")
for ch in e._chests:
    cx = int(ch["x"] // T)
    surf = e.surface_y(ch["x"])
    gy = ch["gy"]
    diff = gy - surf
    flag = "OK" if abs(diff) < 1 else ("悬空 %.0fpx" % -diff if diff < surf else "陷进 %.0fpx" % diff)
    print(" %s cx=%3d x=%4d 地表y=%4.0f 箱底y=%4.0f 差值=%+5.1f  %s"
          % (ch["id"], cx, ch["x"], surf, gy, diff, flag))

print("\n=== 地表采样（确认 surface_y 对不对）===")
for x in (34 * T + 16, 18 * T + 16, 74 * T + 16, 100 * T + 16, 101 * T + 16, 104 * T + 16, 129 * T + 16, 82 * T + 16):
    print(" x=%4d (col %5.1f) -> surface_y=%.0f  solid_below=%s"
          % (x, x / T, e.surface_y(x), e._solid_at(int(x // T), int(e.surface_y(x) // T))))
