# -*- coding: utf-8 -*-
"""落石渲染：天空裂缝 + 石头从缝里掉出 + 预警圈用真实落点。"""
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


OLD = '''    def _draw_fall_rocks(self, surf, cam_x, cam_y, t, st):
        for r in st.get("fall_rocks", []):
            try:
                if r["state"] == "idle":
                    continue
                rx = r["x"] - cam_x
                ry = r["y"] - cam_y
                if r["state"] == "fall":
                    # 地面投影预警圈
                    gy = 19 * TILE - cam_y
                    k = max(0.0, 1.0 - abs(r["y"] - (19 * TILE)) / 500.0)
                    sh = pygame.Surface((40, 12), pygame.SRCALPHA)
                    pygame.draw.ellipse(sh, (0, 0, 0, int(110 * (0.4 + k))), (0, 0, 40, 12))
                    surf.blit(sh, (rx - 20, gy - 6))
                    pygame.draw.ellipse(surf, (255, 90, 70), (rx - 14, gy - 4, 28, 6), 2)
                # 石块
                rnd = random.Random(int(r["x"]))
                pts = []
                for i in range(9):
                    a = i * math.pi * 2 / 9
                    rr = 14 + rnd.uniform(-3, 3)
                    pts.append((rx + math.cos(a) * rr, ry + math.sin(a) * rr))
                pygame.draw.polygon(surf, (96, 88, 86), pts)
                pygame.draw.polygon(surf, (54, 50, 52), pts, 2)
                pygame.draw.circle(surf, (132, 122, 118), (int(rx - 4), int(ry - 5)), 5)
                if r["state"] == "fall":
                    pygame.draw.line(surf, (255, 220, 160), (rx, ry - 20), (rx, ry - 34), 2)'''

NEW = '''    def _draw_sky_crack(self, surf, cx, cy, t, ratio):
        """天空裂缝：中间宽两头尖的裂口 + 锯齿边 + 内部暗紫透光 + 掉落碎屑。

        ratio 0->1 是张开程度。刻意做得"不干净"：边缘随机抖动、
        内部有断续微光，才像被撕开的空间，而不是一个黑色椭圆。
        """
        w = 26.0 + 52.0 * ratio
        h = 5.0 + 21.0 * ratio
        n = 9
        top, bot = [], []
        for i in range(n + 1):
            f = i / float(n)
            x = cx - w * 0.5 + w * f
            taper = math.sin(f * math.pi) ** 0.65
            jt = math.sin(f * 9.3 + t * 3.1) * (1.2 + 1.8 * ratio)
            top.append((x, cy - h * taper * 0.5 + jt))
            bot.append((x, cy + h * taper * 0.5 - jt))
        poly = top + bot[::-1]
        pygame.draw.polygon(surf, (9, 5, 11), poly)
        pygame.draw.lines(surf, (78, 36, 90), False, top, 2)
        pygame.draw.lines(surf, (78, 36, 90), False, bot, 2)
        pygame.draw.lines(surf, (140, 92, 168), False,
                          [(p[0], p[1] + 1) for p in top], 1)
        # 内部透出的光（越张开越明显）
        if ratio > 0.3:
            a = int(110 * (ratio - 0.3) / 0.7)
            for i in range(1, n):
                f = i / float(n)
                tp = math.sin(f * math.pi)
                if tp < 0.22:
                    continue
                yy = cy + (h * tp * 0.22) * (1 if i % 2 else -1)
                pygame.draw.line(surf, theme.alpha_color((158, 92, 190), a),
                                 (top[i][0], yy), (top[i][0] + 4, yy), 1)
        # 沿裂缝掉下的碎屑
        rnd = random.Random(int(cx) * 13 + 7)
        for i in range(4):
            ph = (t * 0.9 + i * 0.25) % 1.0
            xx = cx + rnd.uniform(-0.5, 0.5) * w
            yy = cy + h * 0.5 + ph * 46
            pygame.draw.circle(surf, theme.alpha_color((132, 112, 120),
                                                       int(170 * (1.0 - ph))),
                               (int(xx), int(yy)), 1 if ph > 0.5 else 2)

    def _island_rock_poly(self, cx, cy, seed, scale=1.0):
        rnd = random.Random(seed)
        pts = []
        for i in range(9):
            a = i * math.pi * 2 / 9
            rr = (14 + rnd.uniform(-3.2, 3.2)) * scale
            pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
        return pts

    def _draw_fall_rocks(self, surf, cam_x, cam_y, t, st):
        for r in st.get("fall_rocks", []):
            try:
                state = r["state"]
                if state == "idle":
                    continue
                rx = r["x"] - cam_x
                ry = r["y"] - cam_y
                land_y = float(r.get("land_y", 19 * TILE)) - cam_y
                # 裂缝固定在"天空"：至少贴在屏幕顶部，别跑到视口上方看不见
                crack_y = max(float(r.get("y0", 5 * TILE)) - cam_y, 24)

                if state == "open":
                    ratio = 1.0 - max(0.0, float(r.get("open_t", 0.0))) / 0.55
                    ratio = max(0.0, min(1.0, ratio))
                    self._draw_sky_crack(surf, rx, crack_y, t, ratio)
                    # 石头从裂缝里探出下半截
                    drop = 6 + 10 * ratio
                    pts = self._island_rock_poly(rx, crack_y + drop, int(r["x"]), 0.92)
                    pygame.draw.polygon(surf, (96, 88, 86), pts)
                    pygame.draw.polygon(surf, (54, 50, 52), pts, 2)
                    pygame.draw.circle(surf, (132, 122, 118),
                                       (int(rx - 3), int(crack_y + drop - 4)), 4)
                    # 落点预警
                    shade = pygame.Surface((42, 13), pygame.SRCALPHA)
                    pygame.draw.ellipse(shade, (0, 0, 0, 70), (0, 0, 42, 13))
                    surf.blit(shade, (rx - 21, land_y - 7))
                    pygame.draw.ellipse(surf, theme.alpha_color((255, 90, 70), 150),
                                        (rx - 15, land_y - 5, 30, 7), 2)
                elif state == "fall":
                    self._draw_sky_crack(surf, rx, crack_y, t, 1.0)
                    k = max(0.0, 1.0 - abs(ry - land_y) / 500.0)
                    shade = pygame.Surface((42, 13), pygame.SRCALPHA)
                    pygame.draw.ellipse(shade, (0, 0, 0, int(110 * (0.4 + k))), (0, 0, 42, 13))
                    surf.blit(shade, (rx - 21, land_y - 7))
                    pygame.draw.ellipse(surf, (255, 90, 70), (rx - 15, land_y - 5, 30, 7), 2)

                # 石块本体
                pts = self._island_rock_poly(rx, ry, int(r["x"]), 1.0)
                pygame.draw.polygon(surf, (96, 88, 86), pts)
                pygame.draw.polygon(surf, (54, 50, 52), pts, 2)
                pygame.draw.circle(surf, (132, 122, 118), (int(rx - 4), int(ry - 5)), 5)
                if state == "fall":
                    # 拖尾
                    for k in range(1, 4):
                        g = pygame.Surface((28, 28), pygame.SRCALPHA)
                        pygame.draw.ellipse(g, (170, 158, 150, 46 - k * 12), (4, 4, 20, 20))
                        surf.blit(g, (rx - 14, ry - 14 - k * 13))
                    pygame.draw.line(surf, (255, 220, 160), (rx, ry - 20), (rx, ry - 34), 2)'''

rep(OLD, NEW, "rock_render")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_rockr_log.txt", "w", encoding="utf-8").write(" | ".join(log))
print("done")
