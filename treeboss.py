# -*- coding: utf-8 -*-
"""独立演示：树精 Boss（**不修改项目任何文件**，纯预览）

v2：分辨率提到 240×300、色板 42 色，重点补三件事：
  · 树皮纤维（240 条深浅交错的竖笔触）
  · 苔藓分四层堆叠（暗底 -> 中绿 -> 亮绿 -> 高光点）
  · 轮廓加树瘤凸起 + 藤蔓 + 蘑菇 + 萤光点

运行：
    python tools/demo_treeboss.py
产物写到 shots/demo_*.png。
"""
import math
import os
import sys

import numpy as np
import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

W, H = 240, 300

PAL = {
    # 树皮 8 阶
    1: (30, 20, 14), 2: (50, 34, 22), 3: (72, 50, 30), 4: (96, 68, 40),
    5: (120, 88, 52), 6: (146, 110, 68), 7: (172, 136, 88), 8: (200, 166, 112),
    # 苔藓 8 阶
    9: (44, 62, 28), 10: (70, 98, 36), 11: (100, 134, 48),
    12: (132, 170, 62), 13: (166, 202, 80), 14: (196, 228, 100),
    15: (224, 246, 126), 16: (246, 255, 176),
    # 树洞 4 阶
    17: (14, 10, 10), 18: (30, 22, 20), 19: (48, 36, 30), 20: (68, 52, 42),
    # 骨 / 牙
    21: (216, 212, 186), 22: (244, 240, 218),
    # 白球 5 阶
    23: (150, 146, 126), 24: (186, 182, 158), 25: (218, 214, 190),
    26: (244, 242, 224), 27: (255, 255, 250),
    # 小兽 5 阶
    28: (128, 58, 26), 29: (176, 88, 40), 30: (216, 124, 58),
    31: (240, 164, 96), 32: (252, 206, 150),
    # 石头 4 阶
    33: (46, 46, 44), 34: (72, 72, 68), 35: (100, 100, 94), 36: (132, 132, 124),
    # 枯枝 3 阶
    37: (58, 44, 32), 38: (84, 66, 48), 39: (112, 92, 68),
    # 萤光
    40: (250, 240, 130), 41: (190, 250, 120),
    # 描边
    42: (12, 8, 8),
}


def blank(w=W, h=H):
    return np.zeros((h, w), dtype=np.int16)


def poly(g, pts, pid):
    h, w = g.shape
    ys = [p[1] for p in pts]
    y0 = max(0, min(h - 1, int(min(ys))))
    y1 = max(0, min(h - 1, int(max(ys))))
    n = len(pts)
    for y in range(y0, y1 + 1):
        xs = []
        for i in range(n):
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % n]
            if ay == by:
                continue
            if min(ay, by) <= y < max(ay, by):
                xs.append(ax + (bx - ax) * (y - ay) / float(by - ay))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            xa = max(0, min(w - 1, int(round(xs[i]))))
            xb = max(0, min(w - 1, int(round(xs[i + 1]))))
            if xb >= xa:
                g[y, xa:xb + 1] = pid


def rect(g, x0, y0, x1, y1, pid):
    h, w = g.shape
    x0, x1 = max(0, min(w - 1, int(x0))), max(0, min(w - 1, int(x1)))
    y0, y1 = max(0, min(h - 1, int(y0))), max(0, min(h - 1, int(y1)))
    if x1 >= x0 and y1 >= y0:
        g[y0:y1 + 1, x0:x1 + 1] = pid


def ell(g, cx, cy, rx, ry, pid):
    h, w = g.shape
    y0, y1 = max(0, int(cy - ry)), min(h - 1, int(cy + ry))
    x0, x1 = max(0, int(cx - rx)), min(w - 1, int(cx + rx))
    if y1 < y0 or x1 < x0:
        return
    yy, xx = np.ogrid[y0:y1 + 1, x0:x1 + 1]
    mask = (((xx - cx) / max(0.7, rx)) ** 2 +
            ((yy - cy) / max(0.7, ry)) ** 2) <= 1.0
    g[y0:y1 + 1, x0:x1 + 1][mask] = pid


def line(g, x0, y0, x1, y1, pid, wdt=1):
    n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    for i in range(n + 1):
        t = i / float(max(1, n))
        x = int(round(x0 + (x1 - x0) * t))
        y = int(round(y0 + (y1 - y0) * t))
        if wdt <= 1:
            if 0 <= y < g.shape[0] and 0 <= x < g.shape[1]:
                g[y, x] = pid
        else:
            rect(g, x - wdt // 2, y - wdt // 2, x + wdt // 2, y + wdt // 2, pid)


# --------------------------------------------------------------------------
def build_tree():
    g = blank()
    rng = np.random.RandomState(20261102)
    CX = 120
    Y_TOP, Y_BOT = 88, 258
    H_TOP, H_BOT = 38, 90

    def half_at(y):
        """双曲线式收窄：顶部细、往下平滑张开，中段不过分鼓。"""
        t = (y - Y_TOP) / float(Y_BOT - Y_TOP)
        t = max(0.0, min(1.0, t))
        return H_TOP + (H_BOT - H_TOP) * (t ** 1.08)

    # ============ 1. 树根（先画，被主体压住根部）============
    ROOTS = [
        # (x0, y0, x1, y1, w_top, w_tip, 弯曲量, 层)
        # 5 条主根：粗、短、向外张开，从"根盘"上长出来而不是从主体直插
        (78, 230, 22, 288, 34, 12, -11, 0),
        (162, 230, 218, 288, 34, 12, 11, 0),
        (100, 238, 62, 296, 30, 11, -6, 1),
        (140, 238, 178, 296, 30, 11, 6, 1),
        (120, 242, 116, 300, 36, 13, 0, 2),
    ]
    # 根盘：底部膨大一圈，让 5 条根连成一个整体（不是五条孤立的腿）
    for (ry_, rw_, rh_, cc) in ((250, 82, 15, 4), (258, 76, 12, 3),
                                (266, 64, 8, 2)):
        ell(g, CX, ry_, rw_, rh_, cc)
    for y in range(246, 276, 2):
        t = (y - 246) / 30.0
        w = 86 - 16 * t
        line(g, int(CX - w) + 3, y, int(CX - w) + 16, y, 5)
        line(g, int(CX + w) - 20, y, int(CX + w) - 8, y, 3)
        line(g, int(CX + w) - 7, y, int(CX + w) - 1, y, 2)

    # 先画后排（层 0），再画前排（层 1/2），形成盘绕叠压
    for layer in (0, 1, 2):
        for (x0, y0, x1, y1, wt, wp, cv, lay) in ROOTS:
            if lay != layer:
                continue
            pl, pr = [], []
            N = 12
            for i in range(N + 1):
                t = i / float(N)
                xx = x0 + (x1 - x0) * t + cv * math.sin(t * math.pi) * 0.55
                yy = y0 + (y1 - y0) * t
                w = wt + (wp - wt) * (t ** 0.8)
                pl.append((xx - w * 0.5, yy))
                pr.append((xx + w * 0.5, yy))
            poly(g, pl + pr[::-1], 3)
            for i in range(N):
                line(g, pl[i][0] + 1, pl[i][1], pl[i + 1][0] + 1, pl[i + 1][1], 5, 2)
                line(g, pl[i][0] + 3, pl[i][1], pl[i + 1][0] + 3, pl[i + 1][1], 4, 1)
                line(g, pr[i][0] - 2, pr[i][1], pr[i + 1][0] - 2, pr[i + 1][1], 2, 2)
            for k in (4, 8):
                t = k / float(N)
                bx = x0 + (x1 - x0) * t + cv * math.sin(t * math.pi) * 0.55
                by = y0 + (y1 - y0) * t
                sgn = 1 if cv <= 0 else -1
                line(g, bx, by, bx + sgn * 16, by + 8, 3, 7)
                line(g, bx + sgn * 16, by + 8, bx + sgn * 22, by + 15, 3, 4)

    # ============ 2. 主体：一条平滑的双曲线轮廓 ============
    pl, pr = [], []
    for y in range(Y_TOP, Y_BOT + 1, 2):
        h = half_at(y)
        # 轻微有机起伏（不是台阶，只是表皮不平）
        wob = 2.2 * math.sin(y * 0.17) + 1.3 * math.sin(y * 0.43 + 1.1)
        pl.append((CX - h + wob, y))
        pr.append((CX + h - wob, y))
    poly(g, pl + pr[::-1], 4)

    # 体积：左侧受光、右侧背光（宽色带）
    for y in range(Y_TOP, Y_BOT + 1, 2):
        h = half_at(y)
        line(g, int(CX - h) + 3, y, int(CX - h) + 17, y, 5)
        line(g, int(CX - h) + 18, y, int(CX - h) + 32, y, 4)
        line(g, int(CX + h) - 28, y, int(CX + h) - 13, y, 3)
        line(g, int(CX + h) - 12, y, int(CX + h) - 1, y, 2)

    # 树皮纤维
    for _ in range(300):
        y0 = Y_TOP + int(rng.rand() * (Y_BOT - Y_TOP))
        h0 = half_at(y0)
        x = int(CX + (rng.rand() * 2 - 1) * h0 * 0.94)
        ln = 4 + int(rng.rand() * 16)
        c = (1, 2, 2, 3, 5, 6)[int(rng.rand() * 6)]
        line(g, x, y0, x + rng.randint(-1, 1), min(Y_BOT, y0 + ln), c)

    # 不规则色块：打破"木板"的横平竖直
    for _ in range(60):
        y0 = Y_TOP + int(rng.rand() * (Y_BOT - Y_TOP))
        h0 = half_at(y0)
        x0 = int(CX + (rng.rand() * 2 - 1) * h0 * 0.85)
        rr = 3 + int(rng.rand() * 9)
        ell(g, x0, y0, rr, rr - 1,
            3 if rng.rand() < 0.45 else (2 if rng.rand() < 0.6 else 5))

    # 横向层缝：画在轮廓**内部**，用弧形凹槽表现层次，不往外凸台阶
    for yy in (118, 152, 186, 218, 244):
        h = half_at(yy)
        # 凹槽（深色）+ 下沿亮边，弧形跟随轮廓
        for xo in range(int(-h) + 4, int(h) - 3):
            xx = CX + xo
            sag = 2.0 * (1.0 - (abs(xo) / h) ** 2)      # 中间略下垂，像层叠
            line(g, xx, yy + sag, xx, yy + sag + 1, 1)
            line(g, xx, yy + sag + 2, xx, yy + sag + 3, 5)
        # 缝里的苔藓（只在轮廓内）
        for _ in range(9):
            mx = int(CX + (rng.rand() * 2 - 1) * h * 0.9)
            my = yy + int(2.0 * (1.0 - (abs(mx - CX) / h) ** 2)) - rng.randint(0, 2)
            if 0 <= my < H and 0 <= mx < W and g[my, mx] in (1, 2, 3, 4, 5, 6):
                ell(g, mx, my, rng.randint(3, 6), rng.randint(2, 3),
                    10 if rng.rand() < 0.5 else 9)

    # 树皮主裂纹
    CRACKS = [
        [(96, 100), (92, 118), (98, 134), (94, 150)],
        [(150, 104), (156, 122), (150, 140), (158, 156)],
        [(70, 168), (76, 188), (70, 208), (78, 228)],
        [(176, 172), (170, 194), (176, 214), (168, 236)],
        [(112, 226), (108, 242), (114, 256)],
        [(134, 200), (140, 218), (132, 236)],
    ]
    for path in CRACKS:
        for i in range(len(path) - 1):
            line(g, path[i][0], path[i][1], path[i + 1][0], path[i + 1][1], 1, 3)
            line(g, path[i][0], path[i][1], path[i + 1][0], path[i + 1][1], 2, 1)
        for i in range(1, len(path) - 1):
            bx, by = path[i]
            for sgn in (-1, 1):
                line(g, bx, by, bx + sgn * (6 + i * 2), by + 7 + i * 2, 1, 1)

    # ============ 3. 树洞（嘴）============
    poly(g, [(74, 172), (92, 158), (148, 157), (168, 172),
             (164, 206), (142, 220), (98, 219), (76, 202)], 17)
    poly(g, [(86, 171), (98, 162), (142, 161), (156, 171),
             (152, 196), (136, 206), (104, 205), (90, 192)], 18)
    poly(g, [(94, 176), (104, 170), (136, 170), (146, 176),
             (142, 194), (132, 200), (108, 199), (98, 190)], 19)
    poly(g, [(102, 180), (110, 175), (130, 175), (138, 180),
             (135, 192), (126, 196), (112, 195), (105, 188)], 18)
    poly(g, [(108, 182), (116, 179), (126, 179), (131, 183),
             (129, 190), (122, 192), (113, 191)], 17)
    for (tx, ty, tw, th) in ((96, 160, 7, 17), (112, 157, 8, 20),
                             (130, 158, 7, 18), (146, 161, 6, 15)):
        poly(g, [(tx, ty), (tx + tw, ty), (tx + tw // 2, ty + th)], 21)
        poly(g, [(tx + 1, ty), (tx + tw // 2, ty), (tx + tw // 2, ty + th - 5)], 22)
        line(g, tx, ty, tx + tw, ty, 18, 2)
    for (tx, ty, tw, th) in ((100, 212, 7, 15), (118, 214, 8, 17),
                             (138, 212, 7, 14)):
        poly(g, [(tx, ty), (tx + tw, ty), (tx + tw // 2, ty - th)], 21)

    # ============ 4. 眼睛 ============
    ell(g, 88, 140, 15, 13, 1)
    ell(g, 152, 140, 15, 13, 1)
    ell(g, 88, 142, 13, 11, 17)
    ell(g, 152, 142, 13, 11, 17)
    ell(g, 88, 143, 7, 6, 28)
    ell(g, 152, 143, 7, 6, 28)
    ell(g, 88, 143, 3, 3, 29)
    ell(g, 152, 143, 3, 3, 29)
    rect(g, 85, 140, 87, 141, 22)
    rect(g, 149, 140, 151, 141, 22)
    line(g, 76, 128, 104, 133, 2, 3)
    line(g, 136, 133, 164, 128, 2, 3)

    # ============ 5. 苔藓 ============
    BARK = (g > 0) & (g < 17)

    def in_bark(x, y):
        return 0 <= y < H and 0 <= x < W and BARK[y, x]

    def moss_patch(cx, cy, rw, rh, dens):
        before = g.copy()
        ell(g, cx, cy, rw * 0.82, rh * 0.82, 10)
        ell(g, cx - rw * 0.12, cy - rh * 0.22, rw * 0.62, rh * 0.55, 11)
        ell(g, cx - rw * 0.22, cy - rh * 0.30, rw * 0.34, rh * 0.30, 12)
        spill = (g != before) & ~BARK
        g[spill] = before[spill]
        for _ in range(dens):
            x = int(cx + rng.randn() * rw * 0.55)
            y = int(cy + rng.randn() * rh * 0.55)
            if not in_bark(x, y):
                continue
            ell(g, x, y, 1 + int(rng.rand() * 3), 1 + int(rng.rand() * 2), 10)
        for _ in range(dens // 2):
            x = int(cx + rng.randn() * rw * 0.5)
            y = int(cy + rng.randn() * rh * 0.5)
            if in_bark(x, y):
                ell(g, x, y, 1 + int(rng.rand() * 2), 1 + int(rng.rand() * 2), 12)
        for _ in range(dens // 4):
            x = int(cx + rng.randn() * rw * 0.42)
            y = int(cy + rng.randn() * rh * 0.42)
            if in_bark(x, y):
                rect(g, x, y, x, y, 14)

    # 顶部厚苔
    poly(g, [(56, 104), (70, 92), (120, 90), (166, 94), (180, 108),
             (150, 102), (120, 98), (80, 102), (60, 112)], 10)
    moss_patch(CX, 96, 34, 13, 70)
    # 两侧沿轮廓（x 由 half_at 动态算，保证落在轮廓内侧）
    for (yy, rw, rh, dens) in ((124, 13, 22, 26), (162, 13, 26, 28),
                               (200, 13, 26, 26), (234, 13, 20, 22)):
        hh = half_at(yy)
        moss_patch(CX - hh + 9, yy, rw, rh, dens)
        moss_patch(CX + hh - 9, yy, rw, rh, dens)
    # 眼/嘴周围留白后补一点边苔
    moss_patch(CX, 122, 24, 7, 14)

    # 苔藓亮斑
    for _ in range(120):
        x = 44 + int(rng.rand() * 152)
        y = 92 + int(rng.rand() * 160)
        if in_bark(x, y) and g[y, x] in (9, 10, 11, 12, 13):
            rect(g, x, y, x, y, 14 if rng.rand() < 0.6 else 15)

    # 眼/嘴周围清出干净树皮
    for (cx_, cy_, rx_, ry_) in ((88, 142, 26, 20), (152, 142, 26, 20),
                                 (120, 190, 54, 42)):
        for yy in range(cy_ - ry_, cy_ + ry_ + 1):
            for xx in range(cx_ - rx_, cx_ + rx_ + 1):
                if not (0 <= yy < H and 0 <= xx < W):
                    continue
                if ((xx - cx_) / rx_) ** 2 + ((yy - cy_) / ry_) ** 2 <= 1.0:
                    if g[yy, xx] in (9, 10, 11, 12, 13, 14, 15, 16):
                        g[yy, xx] = 3 if (xx + yy) % 7 else 4

    # ============ 6. 藤蔓 ============
    for (vx, vy, vlen) in ((74, 106, 62), (150, 102, 84), (196, 130, 52)):
        px = vx
        for i in range(vlen):
            py = vy + i
            if i % 5 == 0:
                px += rng.randint(-1, 2)
            rect(g, px, py, px + 1, py, 11 if i % 7 else 12)
            if i % 9 == 4:
                ell(g, px + 3, py, 3, 2, 12)

    # ============ 7. 左臂 + 鸟蛋 ============
    poly(g, [(70, 160), (44, 148), (26, 130), (32, 122), (52, 138),
             (76, 150)], 37)
    poly(g, [(30, 132), (16, 116), (22, 110), (36, 126)], 37)
    poly(g, [(32, 138), (16, 136), (16, 129), (32, 131)], 37)
    line(g, 24, 120, 30, 108, 38, 2)
    for (fx, fy) in ((18, 104), (26, 100), (34, 104)):
        line(g, fx, fy, fx - 2, fy - 8, 38, 2)
        line(g, fx, fy, fx + 1, fy - 9, 39, 1)

    # 鸟蛋：上窄下宽的蛋形（不是正圆）
    ECX, ECY = 26, 86
    egg = []
    N = 44
    for i in range(N):
        a = i * 2 * math.pi / N
        sa, ca = math.sin(a), math.cos(a)
        # 上半收窄 12%，下半略长
        kx = 1.0 - 0.14 * max(0.0, -sa)
        ry = 26 if sa > 0 else 22
        egg.append((ECX + ca * 20 * kx, ECY + sa * ry))
    poly(g, egg, 23)
    # 蛋壳分层：5 阶
    for i, (dx, dy, rx, ry, c) in enumerate((
            (0, 0, 18, 24, 24), (-2, -3, 15, 20, 25),
            (-4, -7, 11, 14, 26), (-6, -11, 6, 8, 27))):
        poly(g, [(ECX + dx + math.cos(a * 2 * math.pi / 32) * rx * (
            1.0 - 0.12 * max(0.0, -math.sin(a * 2 * math.pi / 32))),
            ECY + dy + math.sin(a * 2 * math.pi / 32) * ry) for a in range(32)], c)
    # 蛋壳斑点
    for _ in range(16):
        a = rng.rand() * 2 * math.pi
        rr = 0.55 + rng.rand() * 0.35
        px_ = int(ECX + math.cos(a) * 18 * rr)
        py_ = int(ECY + math.sin(a) * 22 * rr)
        if g[py_, px_] in (23, 24, 25):
            ell(g, px_, py_, 1 + int(rng.rand() * 2), 1, 26 if rng.rand() < 0.5 else 27)
    # 底部环境反射
    ell(g, 30, 102, 10, 4, 24)

    # ============ 8. 右臂 ============
    poly(g, [(172, 176), (198, 186), (216, 204), (206, 212),
             (188, 196), (168, 186)], 37)
    for (fx, fy, dx, dy) in ((214, 206, 12, 6), (212, 214, 10, 13),
                             (206, 220, 4, 15), (198, 224, -4, 13)):
        line(g, fx, fy, fx + dx, fy + dy, 38, 2)
        line(g, fx + dx, fy + dy, fx + dx + 2, fy + dy + 6, 39, 1)

    # ============ 9. 顶部断枝 ============
    for (bx, by, ex, ey, w) in ((78, 96, 52, 74, 4), (162, 98, 190, 76, 4),
                                (100, 92, 88, 66, 3), (140, 94, 154, 64, 3)):
        line(g, bx, by, ex, ey, 2, w)
        line(g, bx, by, ex, ey, 4, 1)
        mx, my = (bx + ex) // 2, (by + ey) // 2
        line(g, mx, my, mx + 8, my - 10, 3, 2)

    # ============ 10. 底部小石头 ============
    for (sx, sy, sr) in ((40, 292, 9), (74, 296, 8), (120, 297, 9),
                         (164, 296, 8), (198, 292, 8)):
        ell(g, sx, sy, sr, sr - 3, 34)
        ell(g, sx - 2, sy - 2, sr - 4, sr - 5, 35)

    # ============ 11. 蘑菇 ============
    for (mx, my, mw) in ((58, 272, 5), (168, 276, 4), (204, 268, 5)):
        rect(g, mx, my - 6, mx + 1, my, 25)
        ell(g, mx, my - 8, mw, 3, 30)
        ell(g, mx - 1, my - 9, mw - 2, 2, 31)

    # ============ 12. 萤光点 ============
    for _ in range(26):
        x = 50 + int(rng.rand() * 140)
        y = 100 + int(rng.rand() * 160)
        if in_bark(x, y) and g[y, x] in (9, 10, 11, 12, 13):
            rect(g, x, y, x, y, 41)

    # ============ 13. 顶部小兽 ============
    poly(g, [(150, 84), (166, 68), (172, 80), (156, 92)], 28)
    poly(g, [(152, 84), (164, 72), (168, 80), (156, 88)], 29)
    ell(g, 138, 78, 15, 12, 29)
    rect(g, 128, 74, 148, 88, 29)
    ell(g, 138, 74, 12, 9, 30)
    ell(g, 138, 62, 11, 11, 30)
    poly(g, [(130, 54), (126, 40), (136, 50)], 30)
    poly(g, [(146, 54), (150, 40), (140, 50)], 30)
    poly(g, [(132, 50), (129, 43), (135, 50)], 31)
    poly(g, [(144, 50), (147, 43), (141, 50)], 31)
    ell(g, 138, 84, 9, 6, 32)
    ell(g, 134, 61, 3, 3, 17)
    ell(g, 143, 61, 3, 3, 17)
    rect(g, 133, 60, 134, 60, 27)
    rect(g, 142, 60, 143, 60, 27)
    rect(g, 137, 66, 139, 67, 28)
    rect(g, 128, 88, 133, 90, 28)
    rect(g, 143, 88, 148, 90, 28)

    return g



def render(g, outline=True):
    h, w = g.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    solid = (g > 0)
    for pid, col in PAL.items():
        rgb[g == pid] = col
    edge = np.zeros_like(solid)
    if outline:
        adj = np.zeros_like(solid)
        adj[1:, :] |= solid[:-1, :]
        adj[:-1, :] |= solid[1:, :]
        adj[:, 1:] |= solid[:, :-1]
        adj[:, :-1] |= solid[:, 1:]
        edge = (~solid) & adj
        rgb[edge] = PAL[42]
    # 全局明暗：上方受光、下方沉入阴影，左侧亮右侧暗
    if solid.any():
        yy = np.arange(h, dtype=np.float32)[:, None] / float(h)
        xx = np.arange(w, dtype=np.float32)[None, :] / float(w)
        k = (1.26 - 0.52 * yy) * (1.12 - 0.22 * xx)
        lit = np.clip(rgb.astype(np.float32) * k[..., None], 0, 255).astype(np.uint8)
        rgb[solid] = lit[solid]
        if outline:
            rgb[edge] = PAL[42]        # 描边不参与明暗，保持轮廓清晰

    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(surf)[:] = np.transpose(rgb, (1, 0, 2))
    pygame.surfarray.pixels_alpha(surf)[:] = np.transpose(
        np.where(solid | edge, 255, 0).astype(np.uint8))
    return surf


# --------------------------------------------------------------------------
# 游戏内接入接口：把 240×300 的树精渲染后按比例缩放到游戏世界尺寸。
# 缓存，避免每帧重建（build_tree 有大量循环）。
# --------------------------------------------------------------------------
_SURF_CACHE = {}


def get_surface(scale=0.55):
    """返回按 scale 缩放的树精 Surface（最近邻，保持像素锐利）。"""
    key = round(float(scale), 4)
    s = _SURF_CACHE.get(key)
    if s is not None:
        return s
    base = render(build_tree(), outline=True)
    w, h = base.get_size()
    tw, th = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    s = pygame.transform.scale(base, (tw, th))
    _SURF_CACHE[key] = s
    return s


def egg_anchor(scale=0.55):
    """树精左手鸟蛋在精灵坐标系里的位置（相对精灵左上角），按 scale 缩放。

    鸟蛋在 240×300 画布里约在 (26, 86)（见 build_tree 的 ECX/ECY）。
    返回 (dx, dy)，单位是缩放后的像素，相对精灵左上角。
    """
    return (26 * scale, 86 * scale)


def main():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((320, 240))

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "shots")
    os.makedirs(out, exist_ok=True)

    tree = render(build_tree())
    pygame.image.save(tree, os.path.join(out, "demo_treeboss.png"))

    board = pygame.Surface((900, 340))
    board.fill((28, 28, 38))
    board.blit(tree, (16, 340 - 300 - 16))
    try:
        import sprites
        cur = sprites.get_char("archer", "idle0", 0)
        board.blit(cur, (290, 340 - 52 - 16))
        big = pygame.transform.scale(cur, (64, 96))
        board.blit(big, (360, 340 - 96 - 16))
        pygame.draw.rect(board, (70, 70, 90), (360, 340 - 96 - 16, 64, 96), 1)
    except Exception as e:
        print("跳过角色对比:", e)
    pygame.image.save(board, os.path.join(out, "demo_compare.png"))

    scene = pygame.Surface((760, 380))
    for i in range(380):
        k = i / 380.0
        scene.fill((int(34 + 24 * k), int(28 + 16 * k), int(44 + 18 * k)),
                   (0, i, 760, 1))
    pygame.draw.rect(scene, (56, 50, 42), (0, 320, 760, 60))
    pygame.draw.rect(scene, (86, 76, 62), (0, 320, 760, 3))
    for gx in range(0, 760, 32):
        pygame.draw.line(scene, (42, 38, 34), (gx, 323), (gx, 380), 1)
    scene.blit(tree, (260, 320 - 300 + 16))
    try:
        import sprites
        scene.blit(sprites.get_char("archer", "idle0", 0), (150, 320 - 52))
        scene.blit(sprites.get_char("guard", "idle0", 0), (560, 320 - 52))
    except Exception:
        pass
    pygame.image.save(scene, os.path.join(out, "demo_scene.png"))
    print("saved demo_treeboss / demo_compare / demo_scene")


if __name__ == "__main__":
    main()
