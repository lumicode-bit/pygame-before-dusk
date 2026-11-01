# -*- coding: utf-8 -*-
"""把悬浮平台画成空中岛屿：方块底部加倒锥岩根 + 两侧参差岩块。"""
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


# ---------- 1) 在 tile 绘制之后补岛体 ----------
rep("        self._draw_terrain(surf, grid, cam_x, cam_y, st, rocks_state)",
    "        self._draw_terrain(surf, grid, cam_x, cam_y, st, rocks_state)\n"
    "        self._draw_float_shells(surf, grid, cam_x, cam_y)",
    "call")

# ---------- 2) 岛体绘制 ----------
rep("    def _draw_ground_spikes(self, surf, cam_x, cam_y, t):",
    '''    def _float_bottom_segments(self, grid):
        """找出所有"悬空底面"：某段实心格的正下方是空的。

        返回 [(c0, c1, gy)]，gy 是这段的底边所在行。
        地面 / 塔基（下面接着实心）不会被算进来。
        """
        solid_ch = ('G', 'R', 'Q', 'S', 's')
        segs = []
        try:
            for gy in range(core.MAP_H - 1):
                gx = 0
                while gx < core.MAP_W:
                    if grid[gy][gx] in solid_ch and grid[gy + 1][gx] in (' ', 'O'):
                        c0 = gx
                        while (gx + 1 < core.MAP_W and grid[gy][gx + 1] in solid_ch
                               and grid[gy + 1][gx + 1] in (' ', 'O')):
                            gx += 1
                        segs.append((c0, gx, gy))
                    gx += 1
        except Exception:
            pass
        return segs

    def _draw_float_shells(self, surf, grid, cam_x, cam_y):
        """给悬浮平台补"岛体"：底部倒锥岩根 + 两侧参差岩块。

        碰撞仍然是方块制的，这里只改轮廓观感——把被切平的方块底边
        变成向下收窄的岩根，避免一排"空中草方块"的塑料感。
        """
        vw = surf.get_width()
        for (c0, c1, gy) in self._float_bottom_segments(grid):
            try:
                x0 = c0 * TILE - cam_x
                x1 = (c1 + 1) * TILE - cam_x
                yb = (gy + 1) * TILE - cam_y
                w = x1 - x0
                if w < 20 or x1 < -80 or x0 > vw + 80:
                    continue
                # 深度按宽度走，最多 2.6 格，太窄的平台不至于变成尖钉
                depth = min(TILE * 2.6, w * 0.42)
                if c0 >= core.FORGE_LEFT:
                    c_dark, c_mid, c_hi = (36, 30, 36), (54, 46, 54), (82, 72, 80)
                elif c0 >= core.SCORCH_LEFT:
                    c_dark, c_mid, c_hi = (40, 33, 29), (60, 48, 40), (88, 72, 58)
                else:
                    c_dark, c_mid, c_hi = (34, 27, 21), (52, 41, 31), (80, 64, 46)
                seed = (c0 * 41 + gy * 29) & 0xffff
                # 左右不对称，免得每块岛都长得一样
                jl = 5 + (seed % 6)
                jr = 4 + ((seed >> 3) % 7)
                tip = x0 + w * (0.44 + ((seed >> 7) % 5) * 0.025)
                pts = [
                    (x0 - jl * 0.5, yb),
                    (x1 + jr * 0.5, yb),
                    (x1 - w * 0.09, yb + depth * 0.38),
                    (x1 - w * 0.24, yb + depth * 0.70),
                    (tip + w * 0.05, yb + depth),
                    (x0 + w * 0.31, yb + depth * 0.64),
                    (x0 + w * 0.11, yb + depth * 0.33),
                ]
                pygame.draw.polygon(surf, c_mid, pts)
                pygame.draw.polygon(surf, c_dark, pts, 2)
                # 岩层横纹
                for k in (1, 2):
                    yy = yb + depth * k / 3.0
                    half = w * (0.33 - k * 0.085)
                    pygame.draw.line(surf, c_dark,
                                     (int(tip - half), int(yy)), (int(tip + half), int(yy)), 1)
                # 受环境光的一侧高光
                pygame.draw.line(surf, c_hi,
                                 (int(tip - w * 0.10), int(yb + depth * 0.42)),
                                 (int(tip + w * 0.02), int(yb + depth * 0.92)), 1)
                # 两侧参差岩块：盖掉方块的直角边
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
                                         1, border_radius=3)
                # 底部挂着的碎屑
                for k in range(2 + (seed >> 11) % 3):
                    dx = tip + ((seed >> (k * 4)) % 21 - 10) * 2.2
                    dy = yb + depth + 3 + ((seed >> (k * 3)) % 9)
                    rr = 2 + ((seed >> (k * 2)) % 3)
                    pygame.draw.circle(surf, c_dark, (int(dx), int(dy)), int(rr))
            except Exception as e:
                if not getattr(_draw_float_shells, "_warned", False):
                    _draw_float_shells._warned = True
                    print("[悬浮岛绘制异常] %r" % (e,))

    def _draw_ground_spikes(self, surf, cam_x, cam_y, t):''', "shells")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_island_log.txt", "w", encoding="utf-8").write(" | ".join(log))
print("done")
