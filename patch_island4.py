# -*- coding: utf-8 -*-
"""悬浮岛 v4：参考用户给的浮空岛概念图重写 _bake_island。

图的要点：厚实圆弧岩体（占岛高 60~70%）、岩石垂直分层、纵向裂纹、
底部圆润挂漂浮碎石、草沿外溢。pygame 无贝塞尔，底缘用"下半椭圆+噪声"
近似圆弧，分层用 set_clip 分段填充。
只替换 _bake_island 单个方法，避免上次区间替换误删方法的事故。
"""
import io

P = "renderer.py"
s = io.open(P, encoding="utf-8").read()
start = s.index("    def _bake_island(self, seg, grid):")
end = s.index("    def _draw_float_shells(self, surf, grid, cam_x, cam_y):")

NEW = '''    def _bake_island(self, seg, grid):
        """烘焙一个悬浮岛（v4，参考浮空岛概念图）。

        形状：薄草皮 + 厚实圆弧岩体（下半椭圆近似，占岛高 60%+），
        岩石垂直分三层（浅->深）、纵向裂纹、底部圆润挂漂浮碎石，
        部分岛有瀑布痕迹。碰撞仍是方块制。
        """
        c0, c1, gy = seg
        T = TILE
        px_w = (c1 - c0 + 1) * T
        thick = 1
        while thick < 3 and gy - thick >= 0 and grid[gy - thick][c0] not in (' ', 'O'):
            thick += 1
        # 岩体厚度：参考图里岩石占岛的 60~70%，比薄尾巴厚重得多
        depth = int(min(T * 4.4, px_w * 0.95 + T))
        fringe = 34
        pad = 20
        w = px_w + pad * 2
        h = thick * T + depth + fringe
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        c_top, c_mid, c_dark, c_hi = self._island_palette(c0)
        # 岩石主体比草皮略浅偏灰（参考图：鲜绿草皮 + 浅灰岩体），底部再压深
        c_rock = _island_mix(c_top, (168, 172, 182), 0.35)
        c_rock_hi = _island_mix(c_rock, (255, 255, 255), 0.18)
        c_rock_mid = _island_mix(c_rock, (30, 32, 40), 0.18)
        c_rock_deep = _island_mix(c_rock, (16, 16, 24), 0.48)
        rng = random.Random((c0 * 73856093) ^ (gy * 19349663))
        yb = thick * T
        x0, x1 = pad, pad + px_w
        cx = (x0 + x1) / 2.0
        rx = px_w * 0.5 + 10 + rng.randint(0, 6)     # 椭圆横轴（肩部略宽于平台）
        ry = depth                                    # 纵轴 = 岩体厚

        # ---- 轮廓：上边直线 + 下半椭圆（带噪声）+ 1~2 个底部凸块 ----
        body = [(x0 - 3, yb - 1), (x1 + 3, yb - 1)]
        n = 12
        for i in range(n + 1):
            f = i / float(n)                          # 0..1 右->左
            a = math.pi * f                           # 半圆参数
            ex = cx - math.cos(a) * rx
            ey = yb + math.sin(a) * ry
            # 噪声：边缘风化感（两端小，中段大）
            amp = 2 + 4 * math.sin(a)
            ey += rng.uniform(-amp, amp) * 0.6
            ex += rng.uniform(-2, 2)
            body.append((ex, ey))
        pygame.draw.polygon(surf, c_rock, body)

        # ---- 垂直分层（set_clip 分段填充同轮廓）----
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(0, yb, w, max(1, int(ry * 0.34))))
        pygame.draw.polygon(surf, c_rock_hi, body)
        surf.set_clip(pygame.Rect(0, yb + int(ry * 0.34), w, max(1, int(ry * 0.40))))
        pygame.draw.polygon(surf, c_rock_mid, body)
        surf.set_clip(pygame.Rect(0, yb + int(ry * 0.74), w, h - (yb + int(ry * 0.74))))
        pygame.draw.polygon(surf, c_rock_deep, body)
        surf.set_clip(clip)
        # 层间接缝（细暗线）
        for f in (0.34, 0.74):
            pygame.draw.line(surf, c_rock_deep,
                             (cx - rx * 0.92, yb + ry * f),
                             (cx + rx * 0.92, yb + ry * f), 1)

        # ---- 纵向裂纹（岩缝，微弯）----
        for k in range(4 + rng.randint(0, 2)):
            fx = rng.uniform(0.12, 0.88)
            sx2 = x0 + px_w * fx
            ln = depth * rng.uniform(0.45, 0.85)
            pts = []
            for i in range(4):
                t2 = i / 3.0
                pts.append((sx2 + rng.uniform(-2.5, 2.5) + math.sin(t2 * 4) * 2,
                            yb + 6 + t2 * ln))
            pygame.draw.lines(surf, c_rock_deep, False, pts, 1)

        # ---- 横向岩层纹理（少量短横线，避开裂纹感过重）----
        for k in range(3):
            yy = yb + depth * (0.30 + 0.22 * k)
            half = rx * (0.55 + 0.2 * k)
            pygame.draw.line(surf, c_rock_deep,
                             (cx - half, yy), (cx + half * 0.9, yy), 1)

        # ---- 草沿外溢：顶面上再勾一条 2px 草色沿（参考图草皮盖过岩石）----
        pygame.draw.line(surf, c_top, (x0 - 3, yb - 1), (x1 + 3, yb - 1), 2)

        # ---- 瀑布痕迹（30% 的岛，参考图点睛元素；静态淡蓝白条）----
        if rng.random() < 0.3 and px_w >= 96:
            wx2 = x0 + px_w * rng.uniform(0.18, 0.42)
            wy2 = yb + 4
            wl = depth * rng.uniform(0.62, 0.85)
            for seg_i, a in ((0, 120), (1, 70), (2, 32)):
                seg_len = wl * (0.45, 0.35, 0.2)[seg_i]
                y_a = wy2 + sum((wl * f for f in (0, 0.45, 0.8))[:seg_i])
                col = (205, 226, 255, a)
                pygame.draw.rect(surf, col,
                                 (wx2 - 2, y_a, 5 if seg_i == 0 else 3, seg_len))
            pygame.draw.rect(surf, (240, 248, 255, 150), (wx2 - 2, wy2, 5, 4))

        # ---- 底部漂浮碎石（参考图岛下的小浮石）----
        for k in range(3 + rng.randint(0, 2)):
            ang = rng.uniform(0.15, 0.85) * math.pi
            dx = cx + math.cos(math.pi - ang) * (rx + rng.randint(-6, 14)) * rng.choice((1, -1))
            dy = yb + ry * (0.72 + 0.3 * rng.random()) + rng.randint(4, fringe - 10)
            rr3 = rng.randint(2, 5)
            st = [(dx - rr3, dy), (dx + rr3, dy + 1), (dx + rr3 * 0.4, dy + rr3),
                  (dx - rr3 * 0.6, dy + rr3 - 1)]
            pygame.draw.polygon(surf, c_rock_mid, st)
            pygame.draw.polygon(surf, c_rock_deep, st, 1)
        # 烘焙返回世界坐标：面 y=0 对齐平台顶
        return surf, c0 * TILE - pad, (gy + 1 - thick) * TILE

'''
s = s[:start] + NEW + s[end:]
io.open(P, "w", encoding="utf-8").write(s)
print("bake v4 written")
