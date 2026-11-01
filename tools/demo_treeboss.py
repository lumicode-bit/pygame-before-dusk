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
    1: (26, 18, 14), 2: (42, 30, 22), 3: (60, 44, 30), 4: (80, 60, 40),
    5: (102, 78, 52), 6: (126, 100, 68), 7: (152, 124, 86), 8: (182, 154, 110),
    # 苔藓 8 阶
    9: (34, 46, 24), 10: (54, 74, 30), 11: (78, 104, 40),
    12: (106, 138, 52), 13: (138, 172, 66), 14: (172, 206, 84),
    15: (206, 232, 104), 16: (236, 250, 150),
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

    # ============ 底部石堆 ============
    poly(g, [(20, 288), (34, 268), (62, 274), (84, 264), (106, 278),
             (128, 266), (152, 274), (176, 264), (198, 272), (220, 288)], 33)
    poly(g, [(32, 288), (40, 276), (62, 280), (82, 272), (104, 284),
             (126, 274), (150, 280), (174, 272), (196, 280), (212, 288)], 34)
    for (sx, sy, sr) in ((48, 278, 11), (84, 280, 10), (120, 277, 12),
                         (158, 280, 10), (192, 278, 9)):
        ell(g, sx, sy, sr, sr - 3, 35)
        ell(g, sx - 3, sy - 3, sr - 5, sr - 6, 36)

    # ============ 树桩：六层"裙边"堆叠（不是一根直筒）============
    # 参考图的树精是**一层层树皮往外翻**堆起来的，每层下缘比上缘宽，
    # 层与层错位叠压 —— 这是它不像水桶的关键。
    LAYERS = [
        # (y_top, y_bot, half_top, half_bot, x_off, 树皮色)
        # 只有 4 层，每层 50~60px 高；下缘比上缘宽 22px -> 明显的"盘沿"台阶
        (228, 292, 66, 96, 0, 4),
        (176, 234, 54, 80, -5, 3),
        (128, 182, 44, 66, 4, 5),
        (88, 134, 34, 52, -2, 3),
    ]

    def layer_pts(yt, yb, ht, hb, xo, step=4):
        pl, pr = [], []
        for y in range(yt, yb + 1, step):
            t = (y - yt) / float(max(1, yb - yt))
            h = ht + (hb - ht) * t
            jag = (7, -5, 8, -4, 6, -8, 4, -6)[(y // step) % 8]
            pl.append((CX + xo - h + jag, y))
            pr.append((CX + xo + h - jag, y))
        return pl, pr

    # 从下往上画，上层压住下层，形成层叠
    for (yt, yb, ht, hb, xo, col) in LAYERS:
        pl, pr = layer_pts(yt, yb, ht, hb, xo)
        poly(g, pl + pr[::-1], col)
        # 边缘树瘤：在两侧随机鼓出 3~5 个小半圆，打破"梯形直边"
        for side in (-1, 1):
            for _ in range(3 + int(rng.rand() * 3)):
                by = int(yt + rng.rand() * (yb - yt))
                t = (by - yt) / float(max(1, yb - yt))
                bh = ht + (hb - ht) * t
                bx = int(CX + xo + side * (bh - 3))
                br = 4 + int(rng.rand() * 7)
                ell(g, bx, by, br, br - 1, col)
                ell(g, bx, by - 1, max(1, br - 2), max(1, br - 3),
                    col + 1 if col < 6 else col)
        # 下缘往外翻的"裙边"阴影：沿底部再描 4px 深色
        for k in range(4):
            yy = yb - k
            t = (yy - yt) / float(max(1, yb - yt))
            h = ht + (hb - ht) * t
            line(g, int(CX + xo - h) + 1, yy, int(CX + xo + h) - 1, yy,
                 1 if k < 2 else 2, 1)
        # 上缘亮边
        for k in range(2):
            yy = yt + k
            t = (yy - yt) / float(max(1, yb - yt))
            h = ht + (hb - ht) * t
            line(g, int(CX + xo - h) + 2, yy, int(CX + xo + h) - 2, yy,
                 6 if k == 0 else 5, 1)

    # ============ 体积感：每层左侧受光、右侧背光 ============
    for (yt, yb, ht, hb, xo, col) in LAYERS:
        for y in range(yt, yb + 1, 2):
            t = (y - yt) / float(max(1, yb - yt))
            h = ht + (hb - ht) * t
            xl, xr = int(CX + xo - h), int(CX + xo + h)
            line(g, xl + 3, y, xl + 14, y, 5)
            line(g, xr - 22, y, xr - 10, y, 3)
            line(g, xr - 9, y, xr - 1, y, 2)

    # ============ 树皮纤维（每层 44 条）============
    for (yt, yb, ht, hb, xo, col) in LAYERS:
        for _ in range(44):
            t0 = rng.rand()
            y0 = int(yt + t0 * (yb - yt) * 0.7)
            h0 = ht + (hb - ht) * t0
            x = int(CX + xo + (rng.rand() * 2 - 1) * h0 * 0.9)
            ln = 4 + int(rng.rand() * 14)
            c = (1, 2, 2, 3, 5, 6)[int(rng.rand() * 6)]
            line(g, x, y0, x + rng.randint(-1, 1), min(yb, y0 + ln), c)

    BARK = (g > 0) & (g < 17)

    def in_bark(x, y):
        return 0 <= y < H and 0 <= x < W and BARK[y, x]

    # ============ 层缝苔藓：连续多边形带（不是碎椭圆堆）============
    for li, (yt, yb, ht, hb, xo, col) in enumerate(LAYERS):
        span = hb * 2 - 16
        x0 = CX + xo - hb + 8
        N = 26
        top_pts, bot_pts = [], []
        for i in range(N + 1):
            t = i / float(N)
            xx = x0 + span * t
            top_pts.append((xx, yb - 7 + math.sin(i * 1.9 + li) * 2.2))
            drop = 7 + math.sin(i * 1.13 + li * 2.1) * 4 + (i % 3) * 2
            bot_pts.append((xx, yb + drop))
        poly(g, top_pts + bot_pts[::-1], 9)
        # 亮面：整条带的上半部分
        mid = [(x, (a1 + b1) * 0.5 - 1)
               for (x, a1), (_, b1) in zip(top_pts, bot_pts)]
        poly(g, top_pts + mid[::-1], 11)
        # 顶部高光点
        for i in range(0, N + 1, 2):
            x, y = top_pts[i]
            rect(g, int(x), int(y), int(x) + 1, int(y) + 1, 13)
        # 垂下来的一两缕
        for i in range(2, N, 5):
            x, y = bot_pts[i]
            ell(g, int(x), int(y) + 3, 2, 3, 9)
            ell(g, int(x), int(y) + 8, 1, 2, 10)

    for (yt, yb, ht, hb, xo, col) in LAYERS:
        # 等距成排（步长 13px）—— 随机会变成"绿色噪声"，等距才有设计感
        span = hb * 2 - 20
        n = max(4, int(span / 13))
        for i in range(n + 1):
            mx = int(CX + xo - hb + 10 + span * (i / float(n)))
            if not in_bark(mx, yb - 2):
                continue
            r0 = 5 if i % 2 == 0 else 4
            ell(g, mx, yb - 2, r0, r0 - 2, 10)
            ell(g, mx - 1, yb - 3, r0 - 2, r0 - 3, 11)
            drop = 2 + (i % 3)
            dy = 0
            for k in range(drop):
                dy += 5 + (i + k) % 3
                r = max(1, r0 - 1 - k)
                ell(g, mx, yb + dy, r, max(1, r - 1), 10 if k == 0 else 9)
                if k == 0:
                    ell(g, mx, yb + dy - 1, max(1, r - 2), 1, 12)

    # ============ 顶部伸出的断枝（打破平顶）============
    for (bx, by, ex, ey, w) in ((78, 96, 52, 74, 4), (162, 98, 190, 76, 4),
                                (100, 92, 88, 66, 3), (140, 94, 154, 64, 3)):
        line(g, bx, by, ex, ey, 2, w)
        line(g, bx, by, ex, ey, 4, 1)
        mx, my = (bx + ex) // 2, (by + ey) // 2
        line(g, mx, my, mx + 8, my - 10, 3, 2)

    # ============ 底部散开的根须 ============
    for (rx, ry, ex, ey) in ((58, 276, 22, 292), (86, 282, 66, 296),
                             (150, 282, 178, 296), (176, 276, 214, 290),
                             (120, 286, 120, 298)):
        line(g, rx, ry, ex, ey, 2, 3)
        line(g, (rx + ex) // 2, (ry + ey) // 2,
             (rx + ex) // 2 + 6, ey + 2, 3, 2)


    # ============ 树洞（嘴）============
    poly(g, [(74, 172), (92, 158), (148, 157), (168, 172),
             (164, 206), (142, 220), (98, 219), (76, 202)], 17)
    poly(g, [(86, 171), (98, 162), (142, 161), (156, 171),
             (152, 196), (136, 206), (104, 205), (90, 192)], 18)
    poly(g, [(94, 176), (104, 170), (136, 170), (146, 176),
             (142, 194), (132, 200), (108, 199), (98, 190)], 19)
    # 上排獠牙
    for (tx, ty, tw, th) in ((96, 160, 7, 17), (112, 157, 8, 20),
                             (130, 158, 7, 18), (146, 161, 6, 15)):
        poly(g, [(tx, ty), (tx + tw, ty), (tx + tw // 2, ty + th)], 21)
        poly(g, [(tx + 1, ty), (tx + tw // 2, ty), (tx + tw // 2, ty + th - 5)], 22)
    # 下排獠牙
    for (tx, ty, tw, th) in ((100, 212, 7, 15), (118, 214, 8, 17),
                             (138, 212, 7, 14)):
        poly(g, [(tx, ty), (tx + tw, ty), (tx + tw // 2, ty - th)], 21)

    # ============ 眼/嘴周围清出干净树皮（视觉焦点）============
    for (cx_, cy_, rx_, ry_) in ((88, 142, 26, 20), (152, 142, 26, 20),
                                 (120, 190, 54, 42)):
        for yy in range(cy_ - ry_, cy_ + ry_ + 1):
            for xx in range(cx_ - rx_, cx_ + rx_ + 1):
                if not (0 <= yy < H and 0 <= xx < W):
                    continue
                if ((xx - cx_) / rx_) ** 2 + ((yy - cy_) / ry_) ** 2 <= 1.0:
                    if g[yy, xx] in (9, 10, 11, 12, 13, 14, 15, 16):
                        g[yy, xx] = 3 if (xx + yy) % 7 else 4

    # ============ 眼睛 ============
    ell(g, 88, 142, 13, 11, 17)
    ell(g, 152, 142, 13, 11, 17)
    ell(g, 88, 143, 7, 6, 28)          # 暗红瞳
    ell(g, 152, 143, 7, 6, 28)
    ell(g, 88, 143, 3, 3, 29)
    ell(g, 152, 143, 3, 3, 29)
    rect(g, 85, 140, 87, 141, 22)      # 高光
    rect(g, 149, 140, 151, 141, 22)
    line(g, 76, 128, 104, 133, 2, 3)        # 眉压
    line(g, 136, 133, 164, 128, 2, 3)

    # ============ 苔藓：四层堆叠 ============
    # 树皮遮罩：苔藓只能长在树皮表面，否则会飘成一团绿色噪声
    def moss_patch(cx, cy, rw, rh, dens):
        # 先铺连续基底：参考图的苔藓是"整块"的，不是一堆碎点
        before = g.copy()
        ell(g, cx, cy, rw * 0.82, rh * 0.82, 10)
        ell(g, cx - rw * 0.12, cy - rh * 0.22, rw * 0.62, rh * 0.55, 11)
        ell(g, cx - rw * 0.22, cy - rh * 0.30, rw * 0.34, rh * 0.30, 12)
        # 基底超出树皮的部分还原（苔藓要贴着树皮长）
        spill = (g != before) & ~BARK
        g[spill] = before[spill]
        for _ in range(dens):
            x = int(cx + rng.randn() * rw * 0.55)
            y = int(cy + rng.randn() * rh * 0.55)
            if not in_bark(x, y):
                continue
            r = 1 + int(rng.rand() * 3)
            ell(g, x, y, r, max(1, r - 1), 10)
        for _ in range(dens // 2):
            x = int(cx + rng.randn() * rw * 0.5)
            y = int(cy + rng.randn() * rh * 0.5)
            if not in_bark(x, y):
                continue
            r = 1 + int(rng.rand() * 2)
            ell(g, x, y, r, max(1, r - 1), 12)
        for _ in range(dens // 4):
            x = int(cx + rng.randn() * rw * 0.42)
            y = int(cy + rng.randn() * rh * 0.42)
            if in_bark(x, y):
                ell(g, x, y, 1, 1, 14)
        for _ in range(dens // 5):
            x = int(cx + rng.randn() * rw * 0.36)
            y = int(cy + rng.randn() * rh * 0.36)
            if in_bark(x, y):
                rect(g, x, y, x, y, 15)

    # 顶部：厚厚一层
    poly(g, [(54, 106), (70, 94), (120, 92), (168, 96), (182, 110),
             (150, 104), (120, 100), (80, 104), (60, 114)], 10)
    moss_patch(CX, 96, 74, 16, 90)
    # 两侧沿边缘垂落（中间留出树皮，不然全糊成绿噪声）
    moss_patch(56, 132, 20, 30, 44)
    moss_patch(50, 186, 18, 38, 44)
    moss_patch(58, 242, 20, 36, 40)
    moss_patch(186, 128, 18, 32, 40)
    moss_patch(192, 186, 18, 40, 44)
    moss_patch(184, 244, 18, 34, 38)
    # 层缝横向苔带（细一点，只压在缝上）
    moss_patch(CX, 180, 52, 7, 20)
    moss_patch(CX, 232, 58, 7, 22)
    # 树瘤、分缝上的苔簇
    moss_patch(CX + 66, 186, 13, 13, 26)
    moss_patch(CX - 66, 140, 12, 14, 24)
    moss_patch(CX, 262, 40, 10, 30)
    # 嘴上方与眼睛周围
    moss_patch(CX, 126, 30, 8, 22)

    # ============ 藤蔓 ============
    for (vx, vy, vlen) in ((74, 106, 62), (150, 102, 84), (196, 130, 52)):
        px = vx
        for i in range(vlen):
            py = vy + i
            if i % 5 == 0:
                px += rng.randint(-1, 2)
            rect(g, px, py, px + 1, py, 11 if i % 7 else 12)
            if i % 9 == 4:
                ell(g, px + 3, py, 3, 2, 12)

    # ============ 左臂（枯枝托白球）============
    poly(g, [(70, 160), (44, 148), (26, 130), (32, 122), (52, 138),
             (76, 150)], 37)
    poly(g, [(30, 132), (16, 116), (22, 110), (36, 126)], 37)
    poly(g, [(32, 138), (16, 136), (16, 129), (32, 131)], 37)
    line(g, 24, 120, 30, 108, 38, 2)
    for (fx, fy) in ((18, 104), (26, 100), (34, 104)):
        line(g, fx, fy, fx - 2, fy - 8, 38, 2)
        line(g, fx, fy, fx + 1, fy - 9, 39, 1)

    # 白球
    ell(g, 26, 88, 24, 23, 23)
    ell(g, 25, 87, 22, 21, 24)
    ell(g, 23, 84, 19, 18, 25)
    ell(g, 20, 80, 14, 13, 26)
    ell(g, 16, 75, 7, 6, 27)
    ell(g, 30, 98, 9, 5, 24)
    for i in range(3):
        ell(g, 33 + i * 3, 92 + i * 4, 2, 1, 26)

    # ============ 右臂（枯枝张开）============
    poly(g, [(172, 176), (198, 186), (216, 204), (206, 212),
             (188, 196), (168, 186)], 37)
    for (fx, fy, dx, dy) in ((214, 206, 12, 6), (212, 214, 10, 13),
                             (206, 220, 4, 15), (198, 224, -4, 13)):
        line(g, fx, fy, fx + dx, fy + dy, 38, 2)
        line(g, fx + dx, fy + dy, fx + dx + 2, fy + dy + 6, 39, 1)

    # ============ 背上的小枯枝 ============
    for (bx, by, ex, ey) in ((60, 128, 42, 110), (186, 134, 206, 116),
                             (86, 100, 76, 82), (156, 100, 170, 84)):
        line(g, bx, by, ex, ey, 38, 2)
        mx, my = (bx + ex) // 2, (by + ey) // 2
        line(g, mx, my, mx + 6, my - 8, 39, 1)

    # ============ 底部蘑菇 ============
    for (mx, my, mw) in ((58, 268, 5), (168, 272, 4), (204, 264, 5)):
        rect(g, mx, my - 6, mx + 1, my, 25)
        ell(g, mx, my - 8, mw, 3, 30)
        ell(g, mx - 1, my - 9, mw - 2, 2, 31)

    # ============ 萤光点 ============
    for _ in range(26):
        x = 50 + int(rng.rand() * 140)
        y = 100 + int(rng.rand() * 170)
        if g[y, x] in (9, 10, 11, 12, 13):
            rect(g, x, y, x, y, 41)

    # ============ 顶部小兽 ============
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
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(surf)[:] = np.transpose(rgb, (1, 0, 2))
    pygame.surfarray.pixels_alpha(surf)[:] = np.transpose(
        np.where(solid | edge, 255, 0).astype(np.uint8))
    return surf


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
