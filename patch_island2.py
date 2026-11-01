# -*- coding: utf-8 -*-
"""悬浮岛调参：更扁的岩根、更接近泥土的配色、两侧岩块更自然。"""
import io

P = "renderer.py"
s = io.open(P, encoding="utf-8").read()
log = []


def rep(old, new, tag):
    global s
    if old in s:
        s = s.replace(old, new, 1)
        log.append(tag)
    elif new in s:
        log.append(tag + "(already)")
    else:
        log.append(tag + "(SKIP)")


rep('''                # 深度按宽度走，最多 2.6 格，太窄的平台不至于变成尖钉
                depth = min(TILE * 2.6, w * 0.42)
                if c0 >= core.FORGE_LEFT:
                    c_dark, c_mid, c_hi = (36, 30, 36), (54, 46, 54), (82, 72, 80)
                elif c0 >= core.SCORCH_LEFT:
                    c_dark, c_mid, c_hi = (40, 33, 29), (60, 48, 40), (88, 72, 58)
                else:
                    c_dark, c_mid, c_hi = (34, 27, 21), (52, 41, 31), (80, 64, 46)''',
    '''                # 深度压扁一点：太深会变成钟乳石，岛底应该是"厚岩石被削了一刀"
                depth = min(TILE * 1.55, w * 0.26)
                if c0 >= core.FORGE_LEFT:
                    c_dark, c_mid, c_hi = (44, 38, 46), (66, 58, 68), (96, 86, 98)
                elif c0 >= core.SCORCH_LEFT:
                    c_dark, c_mid, c_hi = (48, 39, 33), (72, 58, 46), (102, 84, 66)
                else:
                    c_dark, c_mid, c_hi = (44, 34, 25), (66, 52, 37), (96, 78, 56)''',
    "depth_color")

rep('''                tip = x0 + w * (0.44 + ((seed >> 7) % 5) * 0.025)
                pts = [
                    (x0 - jl * 0.5, yb),
                    (x1 + jr * 0.5, yb),
                    (x1 - w * 0.09, yb + depth * 0.38),
                    (x1 - w * 0.24, yb + depth * 0.70),
                    (tip + w * 0.05, yb + depth),
                    (x0 + w * 0.31, yb + depth * 0.64),
                    (x0 + w * 0.11, yb + depth * 0.33),
                ]''',
    '''                tip = x0 + w * (0.50 + ((seed >> 7) % 5 - 2) * 0.018)
                pts = [
                    (x0 - jl * 0.5, yb),
                    (x1 + jr * 0.5, yb),
                    (x1 - w * 0.07, yb + depth * 0.42),
                    (x1 - w * 0.20, yb + depth * 0.76),
                    (tip + w * 0.06, yb + depth),
                    (x0 + w * 0.26, yb + depth * 0.72),
                    (x0 + w * 0.08, yb + depth * 0.40),
                ]''',
    "shape")

rep('''                # 两侧参差岩块：盖掉方块的直角边
                for side, xx in ((-1, x0), (1, x1)):
                    n = 2 + ((seed >> 9) % 3)
                    for k in range(n):
                        hh = 9 + ((seed >> (k * 3 + 1)) % 11)
                        yy = yb - 16 - k * (TILE - 10)
                        ww = 5 + ((seed >> (k * 2 + 4)) % 7)
                        rx = xx - ww if side < 0 else xx
                        pygame.draw.rect(surf, c_mid, (int(rx), int(yy), int(ww), int(hh)),
                                         border_radius=3)
                        pygame.draw.rect(surf, c_dark, (int(rx), int(yy), int(ww), int(hh)),
                                         1, border_radius=3)''',
    '''                # 两侧参差岩块：盖掉方块的直角边（做得更圆更像石头，不像钉子）
                for side, xx in ((-1, x0), (1, x1)):
                    n = 2 + ((seed >> 9) % 2)
                    for k in range(n):
                        hh = 16 + ((seed >> (k * 3 + 1)) % 12)
                        yy = yb - 10 - k * (TILE - 6)
                        ww = 8 + ((seed >> (k * 2 + 4)) % 7)
                        rx = xx - ww + 2 if side < 0 else xx - 2
                        pygame.draw.ellipse(surf, c_mid,
                                            (int(rx), int(yy), int(ww), int(hh)))
                        pygame.draw.ellipse(surf, c_dark,
                                            (int(rx), int(yy), int(ww), int(hh)), 1)''',
    "side_rocks")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_island2_log.txt", "w", encoding="utf-8").write(" | ".join(log))
print("done")
