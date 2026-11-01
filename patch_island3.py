# -*- coding: utf-8 -*-
"""悬浮岛 v3：预烘焙整岛轮廓（参考 WAYFARER tilerender.py 的做法）。

痛点：此前"平台方块 + 底部斗篷"是两截，侧边是硬直角。
参考 https://git.bytes.zone/RayenMalouche/Classic-Pygame-Platformer game/tilerender.py：
- 邻居感知（up/dn/lf/rt）在裸边画帽/暗边/根须
- 静态地形烘焙进一张 surface，运行时零成本 blit
移植：每个悬空平台段启动时烘焙一张"参差侧边 + 倒山丘岩根 + 底部根须碎石"
的 SRCALPHA surface，画在 tile 之上，把直角吃掉、和岩根连成整体。
"""
import io

P = "renderer.py"
s = io.open(P, encoding="utf-8").read()
a = s.index("    def _float_bottom_segments(self, grid):")
b = s.index("    def _island_rock_poly(self, cx, cy, seed, scale=1.0):")

NEW = '''    def _float_bottom_segments(self, grid):
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

    def _island_palette(self, c0):
        """配色采样自地形 tile 实际像素（v2.14 的结论：凭感觉给色必然跑偏）。"""
        if c0 >= core.FORGE_LEFT:
            return (70, 58, 51), (60, 51, 45), (44, 38, 34), (88, 74, 62)
        if c0 >= core.SCORCH_LEFT:
            return (54, 47, 43), (48, 42, 38), (34, 30, 28), (72, 62, 53)
        return (76, 72, 70), (66, 63, 61), (52, 50, 48), (88, 84, 80)

    def _bake_island(self, seg, grid):
        """把一个悬浮岛的"轮廓层"烘焙成 SRCALPHA surface。

        只画 tile 之外/之上的部分：参差侧边（吃掉方块的直角）、
        倒山丘形岩根、底部根须与碎石。碰撞仍是方块制，不受影响。
        返回 (surface, 世界像素偏移 x, y)。
        """
        import math as _m
        import random as _rnd
        c0, c1, gy = seg
        T = TILE
        px_w = (c1 - c0 + 1) * T
        # 平台厚度：从底边行往上数到第一块空（最多 3 行）
        thick = 1
        while thick < 3 and gy - thick >= 0 and grid[gy - thick][c0] not in (' ', 'O'):
            thick += 1
        depth = int(min(T * 2.3, px_w * 0.5))
        fringe = 26                                    # 底部根须/碎石空间
        pad = 14                                       # 左右外扩
        w = px_w + pad * 2
        h = thick * T + depth + fringe
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        c_top, c_mid, c_dark, c_hi = self._island_palette(c0)
        rng = _rnd((c0 * 73856093) ^ (gy * 19349663))
        yb = thick * T                                 # 平台底边（局部坐标）
        x0, x1 = pad, pad + px_w

        # ---- 左右侧边：参差折线，覆盖 tile 的直角边 ----
        # WAYFARER 的做法是 1-2px 暗边；这里再进一步：整条侧边外扩 1~3px、
        # 逐 8px 段抖动，像被风化的岩壁而不是刀切的砖
        for side, xe in ((-1, x0), (1, x1)):
            pts = []
            rows = thick * T // 8
            for r in range(rows + 1):
                yy = yb - thick * T + r * 8
                jitter = rng.randint(-2, 3) * side
                # 越靠上越贴近 tile（顶部要和草面对齐），越往下越参差
                amp = 1 + int(2 * (r / max(1, rows)))
                pts.append((xe + jitter * amp if side > 0 else xe + jitter * amp, yy))
            # 闭合回岩根肩部
            pts.append((xe + side * 6, yb + depth * 0.22))
            pygame.draw.lines(surf, c_dark, False, pts, 2)

        # ---- 岩根：倒山丘（肩部比平台略宽，再收到偏侧的底尖）----
        tip_x = x0 + px_w * (0.42 + rng.random() * 0.16)
        sh_l = x0 - 8 - rng.randint(0, 6)
        sh_r = x1 + 8 + rng.randint(0, 6)
        left_pts = [
            (x0 - 2, yb + 2),
            (sh_l, yb + depth * 0.30),
            (sh_l + (tip_x - sh_l) * 0.45, yb + depth * 0.66),
            (tip_x - px_w * 0.03, yb + depth),
        ]
        right_pts = [
            (x1 + 2, yb + 2),
            (sh_r, yb + depth * 0.26),
            (sh_r - (sh_r - tip_x) * 0.5, yb + depth * 0.62),
            (tip_x + px_w * 0.03, yb + depth),
        ]
        body = left_pts + right_pts[::-1]
        pygame.draw.polygon(surf, c_mid, body)
        # 顶部过渡带：与平台侧面同色，接缝消失
        band = max(6, depth // 5)
        pygame.draw.polygon(surf, c_top, [
            (x0 - 2, yb - 2), (x1 + 2, yb - 2),
            (sh_r - 2, yb + band), (sh_l + 2, yb + band),
        ])
        # 岩层横纹（WAYFARER 的 strata 思路）
        for k in range(1, 4):
            yy = yb + depth * (0.28 + 0.22 * k)
            f = 1.0 - (0.28 + 0.22 * k) * 0.75
            half = px_w * 0.5 * f
            cx = (tip_x + (x0 + x1) / 2) / 2
            pygame.draw.line(surf, c_dark, (cx - half, yy), (cx + half, yy), 1)
        # 左右暗边（仅岩根部分）
        pygame.draw.lines(surf, c_dark, False, left_pts, 2)
        pygame.draw.lines(surf, c_dark, False, right_pts, 2)
        # 受环境光一侧的高光
        pygame.draw.line(surf, c_hi,
                         (tip_x - px_w * 0.08, yb + depth * 0.42),
                         (tip_x + px_w * 0.01, yb + depth * 0.9), 1)

        # ---- 底部根须 + 钟乳石 + 碎石（WAYFARER _ceiling_deco 思路）----
        for k in range(3):
            bx = x0 + px_w * (0.25 + 0.25 * k) + rng.randint(-6, 6)
            by = yb + depth * (0.55 + 0.12 * k)
            ln = rng.randint(8, 18)
            pygame.draw.line(surf, c_dark, (bx, by), (bx + rng.randint(-3, 3), by + ln), 1)
        for k in range(2 + rng.randint(0, 2)):
            px2 = x0 + rng.randint(8, max(9, px_w - 8))
            py2 = yb + depth * (0.35 + 0.3 * rng.random())
            pygame.draw.polygon(surf, c_dark,
                                [(px2 - 2, py2), (px2 + 2, py2), (px2, py2 + rng.randint(4, 9))])
        for k in range(2 + rng.randint(0, 2)):
            dx = tip_x + rng.uniform(-0.35, 0.35) * px_w
            dy = yb + depth + rng.randint(2, fringe - 8)
            rr = rng.randint(1, 3)
            pygame.draw.circle(surf, c_dark, (int(dx), int(dy)), rr)
        return surf, x0 - pad, 0

    def _draw_float_shells(self, surf, grid, cam_x, cam_y):
        """把烘焙好的岛体按视口 blit（缓存于 self._island_cache）。"""
        if not hasattr(self, "_island_cache"):
            self._island_cache = {}
        vw = surf.get_width()
        for seg in self._float_bottom_segments(grid):
            try:
                if seg not in self._island_cache:
                    self._island_cache[seg] = self._bake_island(seg, grid)
                isurf, ox, oy = self._island_cache[seg]
                c0, c1, gy = seg
                sx = c0 * TILE - 14 - cam_x
                sy = (gy + 1 - (isurf.get_height() // TILE if False else 0)) * TILE - cam_y
                # sy：岛面顶对齐"平台底边行 - 平台厚度"，烘焙时 y=0 就是那一条
                sy = (gy + 1) * TILE - isurf.get_height() - cam_y
                if sx > vw + 80 or sx + isurf.get_width() < -80:
                    continue
                surf.blit(isurf, (sx, sy))
            except Exception as e:
                if not getattr(self._draw_float_shells, "_warned", False):
                    self._draw_float_shells._warned = True
                    print("[悬浮岛绘制异常] %r" % (e,))

'''
s = s[:a] + NEW + s[b:]
io.open(P, "w", encoding="utf-8").write(s)
print("island v3 written")
