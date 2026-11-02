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
    # 眼（余烬瞳）：独立的暖色阶，和小兽的橙区分开
    43: (118, 24, 16), 44: (226, 92, 36), 45: (255, 214, 148),
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
    Y_TOP, Y_BOT = 86, 258
    H_TOP, H_BOT = 38, 90

    # ==================================================================
    # 轮廓：左右用**不同**的收窄曲线 + 不同相位起伏 + 中心漂移
    # 目的：彻底打破左右对称。像活物，不像程序生成的标准件。
    # ==================================================================
    def clamp01(v):
        return max(0.0, min(1.0, v))

    def center(y):
        """中轴线：随高度缓慢漂移（树干微微歪斜）"""
        t = clamp01((y - Y_TOP) / float(Y_BOT - Y_TOP))
        return CX + 3.8 * math.sin(t * 2.5 + 0.3) * (0.25 + 0.75 * t)

    def half_l(y):
        """左半宽：指数 1.12 → 收得快，左肩略高"""
        t = clamp01((y - Y_TOP) / float(Y_BOT - Y_TOP))
        base = H_TOP + (H_BOT - H_TOP) * (t ** 1.12)
        return base + 2.7 * math.sin(y * 0.155 + 0.7) + 1.4 * math.sin(y * 0.41 + 2.2)

    def half_r(y):
        """右半宽：指数 1.00 → 线性张开，右肩略低更宽"""
        t = clamp01((y - Y_TOP) / float(Y_BOT - Y_TOP))
        base = H_TOP + (H_BOT - H_TOP) * (t ** 1.00)
        return base + 3.0 * math.sin(y * 0.128 + 2.5) + 1.6 * math.sin(y * 0.37 + 0.9)

    def bark_mask():
        return (g > 0) & (g < 17)

    def is_bark(x, y):
        return 0 <= y < H and 0 <= x < W and 0 < g[y, x] < 17

    # ==================================================================
    # 1. 树根（先画，被主体压住根部）
    # ==================================================================
    ROOTS = [
        # (x0, y0, x1, y1, w_top, w_tip, 弯曲量, 层) —— 长度刻意不等
        (78, 232, 30, 282, 32, 12, -9, 0),
        (158, 232, 206, 278, 30, 12, 9, 0),
        (100, 240, 66, 296, 28, 11, -5, 1),
        (138, 240, 172, 292, 26, 11, 6, 1),
        (118, 244, 114, 298, 34, 13, -3, 2),
    ]
    # 根盘：不对称的三层扁椭圆（收窄，别做成螃蟹腿）
    for (ry_, rw_, rh_, cc, ox) in ((250, 72, 14, 4, -4), (258, 66, 11, 3, -2),
                                    (266, 56, 8, 2, 1)):
        ell(g, center(252) + ox, ry_, rw_, rh_, cc)
    for y in range(246, 276, 2):
        t = (y - 246) / 30.0
        w = 74 - 14 * t
        c = center(y)
        line(g, int(c - w) + 3, y, int(c - w) + 15, y, 5)
        line(g, int(c + w) - 19, y, int(c + w) - 8, y, 3)
        line(g, int(c + w) - 7, y, int(c + w) - 1, y, 2)

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

    # ==================================================================
    # 2. 手臂（画在主体**之前**，肩部被身体压住 → 从躯干里长出来）
    # ==================================================================
    def limb(pts, col=37, lit=38, shd=39):
        """有体积的枝条肢：pts = [(x, y, 半宽), ...]"""
        for i in range(len(pts) - 1):
            x0, y0, w0 = pts[i]
            x1, y1, w1 = pts[i + 1]
            poly(g, [(x0 - w0, y0), (x0 + w0, y0),
                     (x1 + w1, y1), (x1 - w1, y1)], col)
            # 上缘受光 / 下缘背光
            line(g, int(x0 - w0) + 1, int(y0), int(x1 - w1) + 1, int(y1), lit, 2)
            line(g, int(x0 + w0) - 1, int(y0), int(x1 + w1) - 1, int(y1), shd, 2)
        # 关节鼓包
        for (jx, jy, jw) in pts[1:-1]:
            ell(g, jx, jy, jw * 1.18, jw * 1.05, col)
            ell(g, jx - 1, jy - 2, jw * 0.7, jw * 0.6, lit)

    # 左臂：托着鸟蛋，肘部有明显折角
    limb([(78, 166, 14), (52, 150, 11), (32, 126, 9), (24, 112, 8)])
    # 左手指（张开托住蛋）
    for (fx, fy, dx, dy) in ((22, 108, -8, -6), (26, 106, -1, -10),
                             (31, 109, 6, -8)):
        line(g, fx, fy, fx + dx, fy + dy, 37, 4)
        line(g, fx, fy, fx + dx, fy + dy, 38, 2)
    # 右臂：向外下方探，肘部折角更锐
    limb([(162, 176, 12), (188, 190, 9), (208, 206, 7)])
    # 右手指：4 根粗爪
    for (fx, fy, dx, dy) in ((210, 208, 13, 5), (209, 214, 11, 12),
                             (204, 219, 5, 15), (197, 223, -4, 13)):
        line(g, fx, fy, fx + dx, fy + dy, 37, 5)
        line(g, fx + dx, fy + dy, fx + dx + 2, fy + dy + 6, 39, 2)
        line(g, fx, fy, fx + dx, fy + dy, 38, 2)

    # ==================================================================
    # 3. 主体：平滑但**不对称**的轮廓
    # ==================================================================
    pl, pr = [], []
    for y in range(Y_TOP, Y_BOT + 1, 2):
        c = center(y)
        pl.append((c - half_l(y), y))
        pr.append((c + half_r(y), y))
    poly(g, pl + pr[::-1], 4)

    # 体积：左受光、右背光（宽色带）
    for y in range(Y_TOP, Y_BOT + 1, 2):
        c = center(y)
        hl, hr = half_l(y), half_r(y)
        line(g, int(c - hl) + 3, y, int(c - hl) + 16, y, 5)
        line(g, int(c - hl) + 17, y, int(c - hl) + 29, y, 4)
        line(g, int(c + hr) - 26, y, int(c + hr) - 13, y, 3)
        line(g, int(c + hr) - 12, y, int(c + hr) - 1, y, 2)

    # ==================================================================
    # 4. 树皮：低频噪声调制密度 → 疏密成片，而不是均匀噪点
    # ==================================================================
    def rough(y, x):
        return (math.sin(x * 0.085 + y * 0.125) +
                math.sin(x * 0.21 - y * 0.065) * 0.7 +
                math.sin(y * 0.30 + x * 0.05) * 0.55)

    # 纤维：沿"纹路方向"的长笔触，不是孤立黑点
    # 走向：顺着树干的纵向纤维，但整体向左倾（像被风压弯的树）
    for _ in range(260):
        y0 = Y_TOP + int(rng.rand() * (Y_BOT - Y_TOP))
        c = center(y0)
        hl, hr = half_l(y0), half_r(y0)
        x = int(c + (rng.rand() * 2 - 1) * (hl if rng.rand() < 0.5 else hr) * 0.9)
        if not (0 <= x < W) or not is_bark(x, y0):
            continue
        if rough(y0, x) < 0.30:          # 平滑区：留白，让树皮成"面"
            continue
        # 长纤维：几乎竖直，整体略向左倾；靠边缘的沿轮廓弯
        edge = (x - c) / max(1.0, (hr if x > c else hl))
        drift = edge * 0.30 - 0.12 + rng.uniform(-0.10, 0.10)
        ln = 14 + int(rng.rand() * 26)
        # 相近色为主（2/3/5），少用极端色 → 纹理而非噪点
        cc = (3, 4, 5, 5, 6)[int(rng.rand() * 5)]
        for k in range(ln):
            yy = y0 + k
            xx = int(x + drift * k)
            if not (0 <= xx < W and 0 <= yy < H) or not is_bark(xx, yy):
                break
            if g[yy, xx] == cc:
                continue
            g[yy, xx] = cc

    # 树皮纹：沿轮廓的暗色边（让树皮从苔藓底下透出来，不是一片平色）
    for y in range(Y_TOP, Y_BOT + 1, 2):
        c = center(y)
        hl, hr = half_l(y), half_r(y)
        line(g, int(c - hl) + 1, y, int(c - hl) + 3, y, 2)
        line(g, int(c + hr) - 3, y, int(c + hr) - 1, y, 1)

    # 树皮：只保留**少量**大色块（打破平色即可，密了会脏）
    for _ in range(26):
        y0 = Y_TOP + int(rng.rand() * (Y_BOT - Y_TOP))
        c = center(y0)
        hl, hr = half_l(y0), half_r(y0)
        x0 = int(c + (rng.rand() * 2 - 1) * (hl if rng.rand() < 0.5 else hr) * 0.8)
        if not is_bark(x0, y0):
            continue
        rr = 6 + int(rng.rand() * 12)
        ell(g, x0, y0, rr, max(1, rr - int(rng.rand() * 3)),
            (3, 4, 5)[int(rng.rand() * 3)])

    # 不规则色块：打破"木板"的横平竖直
    for _ in range(24):
        y0 = Y_TOP + int(rng.rand() * (Y_BOT - Y_TOP))
        c = center(y0)
        hl, hr = half_l(y0), half_r(y0)
        x0 = int(c + (rng.rand() * 2 - 1) * (hl if rng.rand() < 0.5 else hr) * 0.84)
        if not is_bark(x0, y0):
            continue
        rr = 3 + int(rng.rand() * 9)
        ell(g, x0, y0, rr, rr - 1,
            3 if rng.rand() < 0.45 else (2 if rng.rand() < 0.6 else 5))

    # 树瘤：带暗环的凸起
    for (kx, ky, kr) in ((78, 168, 9), (150, 205, 7), (104, 232, 8), (166, 130, 6)):
        if not is_bark(kx, ky):
            continue
        ell(g, kx, ky, kr, kr - 1, 3)
        ell(g, kx - 1, ky - 1, kr - 2, kr - 3, 4)
        ell(g, kx, ky, max(1, kr - 4), max(1, kr - 5), 2)

    # 横向层缝：**断续**的凹槽（不是通贯直线），带下沿亮边
    # 注意：段要短、断口要多 → 否则会连成"木板横条"，把树画成木桶
    for (yy, span) in ((124, 0.80), (160, 0.66), (200, 0.78), (236, 0.60)):
        c = center(yy)
        hl, hr = half_l(yy), half_r(yy)
        x0 = int(c - hl * span)
        x1 = int(c + hr * span)
        x = x0
        while x < x1:
            seglen = 5 + int(rng.rand() * 9)
            if rng.rand() < 0.52:
                for xx in range(x, min(x + seglen, x1)):
                    k = (xx - c) / max(1.0, hl + hr)
                    sag = int(2.0 * (1.0 - min(1.0, k * k * 4.0)))
                    y2 = yy + sag
                    if not (0 <= y2 < H and 0 <= xx < W):
                        continue
                    if not is_bark(xx, y2):
                        continue
                    g[y2, xx] = 1
                    if is_bark(xx, y2 + 2):
                        g[y2 + 2, xx] = 6
            x += seglen + 2 + int(rng.rand() * 6)

    # 树皮主裂纹：手绘走向 + 分叉
    CRACKS = [
        [(96, 100), (92, 118), (98, 134), (94, 150)],
        [(150, 104), (156, 122), (150, 140), (158, 156)],
        [(70, 168), (76, 188), (70, 208), (78, 228)],
        [(176, 172), (170, 194), (176, 214), (168, 236)],
        [(112, 226), (108, 242), (114, 256)],
        [(134, 200), (140, 218), (132, 236)],
        [(184, 148), (192, 168), (186, 188)],
        [(190, 196), (182, 214), (190, 232)],
    ]
    for path in CRACKS:
        for i in range(len(path) - 1):
            line(g, path[i][0], path[i][1], path[i + 1][0], path[i + 1][1], 1, 3)
            line(g, path[i][0], path[i][1], path[i + 1][0], path[i + 1][1], 2, 1)
        for i in range(1, len(path) - 1):
            bx, by = path[i]
            for sgn in (-1, 1):
                line(g, bx, by, bx + sgn * (6 + i * 2), by + 7 + i * 2, 1, 1)

    # ==================================================================
    # 5. 顶部碎裂木冠 —— 打破"一条平线"
    # ==================================================================
    CROWN = [
        # (x, 顶高, 半宽, 倾斜, 颜色)
        (90, 60, 11, -3, 4),
        (114, 54, 12, 2, 3),
        (158, 64, 9, 3, 4),
    ]
    for (px_, ptop, pw, lean, pc) in CROWN:
        poly(g, [(px_ - pw, Y_TOP + 10), (px_ + lean, ptop),
                 (px_ + pw, Y_TOP + 10)], pc)
        # 断口：一边亮一边暗（受光在左）
        line(g, px_ + lean - 1, ptop + 3, px_ + pw - 1, Y_TOP + 9, 6, 2)
        line(g, px_ + lean + 1, ptop + 4, px_ - pw + 1, Y_TOP + 9, 2, 2)

    # 冠上的缺口（往下切 V 形）
    for (nx, nw, nd) in ((102, 14, 11), (136, 12, 9), (78, 10, 7)):
        for y in range(Y_TOP, Y_TOP + nd):
            t = (y - Y_TOP) / float(nd)
            ins = int(nw * 0.5 * t)
            lo = max(0, nx - nw // 2 + ins)
            hi = min(W - 1, nx + nw // 2 - ins)
            if lo <= hi:
                g[y, lo:hi + 1] = 0

    # ==================================================================
    # 6. 脸：左右**不对称** —— 眼高低、大小、眉毛角度都不同
    # ==================================================================
    # 眉脊（压低 → 怒意）
    line(g, 68, 122, 100, 130, 2, 4)
    line(g, 100, 130, 104, 127, 3, 3)
    line(g, 142, 137, 170, 125, 2, 4)
    line(g, 142, 137, 138, 133, 3, 3)

    # 眼窝：外圈阴影
    ell(g, 85, 135, 16, 14, 1)
    ell(g, 154, 143, 13, 11, 1)
    # 眼
    ell(g, 85, 137, 13, 11, 17)
    ell(g, 154, 145, 11, 9, 17)
    # 余烬虹膜（暗红 → 琥珀 → 亮点）
    ell(g, 85, 137, 8, 7, 43)
    ell(g, 154, 145, 6, 5, 43)
    ell(g, 85, 137, 5, 4, 44)
    ell(g, 154, 145, 4, 3, 44)
    ell(g, 85, 137, 2, 2, 45)
    ell(g, 154, 145, 2, 2, 45)
    # 高光
    rect(g, 82, 134, 84, 135, 22)
    rect(g, 151, 142, 153, 143, 22)

    # ==================================================================
    # 7. 嘴（树洞）：中心右移 + 倾斜 → 不对称
    #    关键是**别做成一大坨纯黑**：用 5 阶递进，中间夹暖棕，才像有壁的洞
    # ==================================================================
    # 洞沿（最外圈，最暗）
    poly(g, [(84, 172), (102, 158), (150, 159), (168, 176),
             (162, 204), (140, 216), (104, 211), (86, 195)], 18)
    # 洞壁（往上收一圈）
    poly(g, [(92, 174), (106, 163), (145, 164), (159, 177),
             (153, 198), (136, 208), (110, 204), (96, 190)], 19)
    # 洞壁高光侧（左上受光 → 用暖棕提亮，给"壁"的厚度）
    poly(g, [(92, 174), (106, 163), (126, 165), (118, 172),
             (100, 180), (96, 190)], 20)
    # 洞口内侧（下半更深）
    poly(g, [(100, 180), (110, 172), (138, 173), (150, 182),
             (144, 196), (130, 203), (112, 198), (102, 189)], 18)
    # 最深处
    poly(g, [(108, 183), (116, 178), (130, 179), (137, 184),
             (133, 194), (124, 198), (114, 194)], 17)
    # 上牙：长度宽度各不相同（不对称）
    for (tx, ty, tw, th) in ((96, 162, 7, 15), (110, 159, 9, 19),
                             (130, 161, 6, 16), (145, 164, 8, 13)):
        poly(g, [(tx, ty), (tx + tw, ty), (tx + tw // 2, ty + th)], 21)
        poly(g, [(tx + 1, ty), (tx + tw // 2, ty), (tx + tw // 2, ty + th - 5)], 22)
        line(g, tx, ty, tx + tw, ty, 18, 2)
        rect(g, tx + tw // 2, ty + th - 3, tx + tw // 2, ty + th - 2, 22)
    # 下牙
    for (tx, ty, tw, th) in ((103, 209, 7, 13), (119, 212, 8, 16),
                             (137, 208, 6, 11)):
        poly(g, [(tx, ty), (tx + tw, ty), (tx + tw // 2, ty - th)], 21)
        poly(g, [(tx + 1, ty), (tx + tw // 2, ty), (tx + tw // 2, ty - th + 4)], 22)

    # ==================================================================
    # 8. 苔藓：连续的"团块"，从缝隙长出来（不是均匀撒点）
    # ==================================================================
    BM = bark_mask()

    def in_bark(x, y):
        return 0 <= y < H and 0 <= x < W and bool(BM[y, x])

    def moss_carpet(x0, x1, ytop, ybot, dens):
        """横向苔毯：顶部一条连续的苔藓带"""
        n = max(3, int((x1 - x0) / 8))
        for i in range(n + 1):
            t = i / float(n)
            px_ = int(x0 + (x1 - x0) * t)
            wob = math.sin(t * 7.0) * 3.0 + math.sin(t * 3.1 + 1.4) * 4.0
            py_ = int(ytop + (ybot - ytop) * 0.5 + wob * 0.4)
            rr = 6 + int(abs(wob))
            ell(g, px_, py_, 7, max(3, rr), 10)
            ell(g, px_ - 1, py_ - 2, 5, max(2, rr - 3), 11)
        for i in range(0, n + 1, 2):
            t = i / float(n)
            px_ = int(x0 + (x1 - x0) * t)
            py_ = int(ytop + (ybot - ytop) * 0.22)
            ell(g, px_, py_, 4, 2, 12)

    def moss_edge_band(side, y_from, y_to, depth, seed=0):
        """沿轮廓边缘长的一条苔藓带（贴着外形，内缘起伏）

        side: -1 左 / +1 右。这是让苔藓"长在树上"而不是"贴在上面的圆球"的关键。
        """
        pts_l, pts_r = [], []
        N = max(8, int((y_to - y_from) / 3))
        for i in range(N + 1):
            t = i / float(N)
            y = y_from + (y_to - y_from) * t
            c = center(y)
            h = half_l(y) if side < 0 else half_r(y)
            edge = c + side * h
            # 内缘深度：正弦起伏 + 端部收窄
            d = depth * (0.55 + 0.45 * math.sin(t * 6.5 + seed)) \
                * (0.45 + 0.55 * math.sin(t * math.pi) ** 0.5)
            d = max(0, d)
            pts_l.append((edge - side * d, y))
            pts_r.append((edge, y))
        # 外缘贴轮廓，内缘起伏 → 一条真正的"苔带"
        poly(g, pts_l + pts_r[::-1], 10)
        # 亮面：靠轮廓一侧（受光）
        mid = [(a[0] + (b[0] - a[0]) * 0.42, a[1]) for a, b in zip(pts_l, pts_r)]
        poly(g, pts_l + mid[::-1], 11)
        # 更亮的芯
        core = [(a[0] + (b[0] - a[0]) * 0.22, a[1]) for a, b in zip(pts_l, pts_r)]
        poly(g, pts_l + core[::-1], 12)
        # 下缘叶尖：每 3px 一片小三角
        for i in range(0, N + 1):
            x, y = pts_l[i]
            xi, yi = int(x), int(y)
            if not in_bark(xi, yi):
                continue
            ln = 2 + (i % 3)
            poly(g, [(xi - 1, yi), (xi + 1, yi), (xi, yi + ln)], 10)
            if i % 2 == 0:
                poly(g, [(xi - 1, yi), (xi, yi), (xi, yi + ln - 1)], 11)
        # 垂挂的须
        for i in range(2, N, 5):
            x, y = pts_l[i]
            ell(g, int(x), int(y) + 3, 2, 3, 9)
            ell(g, int(x), int(y) + 8, 1, 2, 10)

    def moss_clump(cx_, cy_, r):
        """一块连通苔藓：多椭圆围成团 + 垂挂须 + 叶尖"""
        n = 6 + int(rng.rand() * 4)
        ang0 = rng.rand() * 6.28
        for i in range(n):
            a = ang0 + i * 6.28 / n + rng.uniform(-0.45, 0.45)
            d = r * rng.uniform(0.22, 0.60)
            px_ = int(cx_ + math.cos(a) * d)
            py_ = int(cy_ + math.sin(a) * d * 0.60)
            rr = max(3, int(r * rng.uniform(0.42, 0.66)))
            ell(g, px_, py_, rr, max(1, int(rr * 0.74)), 10)
            ell(g, px_ - 1, py_ - 1, max(1, rr - 2), max(1, rr - 2), 11)
        # 顶面受光
        ell(g, int(cx_ - r * 0.16), int(cy_ - r * 0.34),
            max(2, int(r * 0.58)), max(1, int(r * 0.30)), 12)
        # 垂挂的须
        for _ in range(4 + int(rng.rand() * 4)):
            sx = int(cx_ + rng.uniform(-r * 0.80, r * 0.80))
            sy = int(cy_ + r * 0.34)
            L = int(r * rng.uniform(1.1, 2.4))
            for k in range(L):
                yy = sy + k
                if not (0 <= yy < H and 0 <= sx < W):
                    break
                if k % 3 == 0:
                    rr = max(1, 4 - k // 5)
                    ell(g, sx, yy, rr, 1, 10 if k == 0 else 9)
        # 叶尖
        for _ in range(7):
            a = rng.uniform(0, 6.28)
            px_ = int(cx_ + math.cos(a) * r * 0.78)
            py_ = int(cy_ + math.sin(a) * r * 0.52)
            if in_bark(px_, py_):
                poly(g, [(px_ - 1, py_), (px_ + 1, py_), (px_, py_ + 2)], 11)

    # 苔藓会盖住脸 —— 画之前先给脸拍张快照，苔藓画完再恢复
    face_snap = g.copy()
    FACE_IDS = (17, 18, 19, 20, 21, 22, 43, 44, 45)

    # ---- 苔藓布局：左密右疏（不对称），且全部贴轮廓 ----
    # 1) 左侧主苔带：从顶一直挂到腰下（加宽，主体连成片）
    moss_edge_band(-1, 92, 220, 34, seed=0.6)
    # 2) 左侧第二条细苔带（错开，制造层次）
    moss_edge_band(-1, 140, 244, 20, seed=2.4)
    # 3) 右侧苔带：只到胸口，稀疏
    moss_edge_band(1, 98, 168, 20, seed=1.5)
    # 4) 顶部横向苔帽
    moss_carpet(CX - 46, CX + 34, 88, 120, 50)
    # 5) 团块：打破带的规律，制造"丛"
    CLUMPS = [
        (CX - 40, 118, 15), (CX - 52, 152, 16), (CX - 30, 186, 14),
        (CX + 14, 100, 14), (CX + 38, 134, 11), (CX - 18, 232, 14),
        (CX + 8, 244, 11), (CX - 44, 210, 13), (CX - 6, 152, 11),
        # 右腰：几块苔藓打断右侧"硬横边"，别让苔带断口变成一条横线
        (CX + 42, 168, 12), (CX + 34, 190, 10), (CX + 46, 208, 9),
    ]
    for (mx, my, mr) in CLUMPS:
        if not in_bark(mx, my):
            continue
        moss_clump(mx, my, mr)

    # 苔藓亮斑（蓬松感）
    for _ in range(160):
        x = 44 + int(rng.rand() * 152)
        y = 88 + int(rng.rand() * 168)
        if in_bark(x, y) and g[y, x] in (9, 10, 11, 12, 13):
            rect(g, x, y, x, y, 14 if rng.rand() < 0.6 else 15)

    # 眼/嘴周围清出干净树皮（视觉焦点）
    for (cx_, cy_, rx_, ry_) in ((85, 137, 26, 20), (154, 145, 24, 18),
                                 (125, 188, 54, 42)):
        for yy in range(cy_ - ry_, cy_ + ry_ + 1):
            for xx in range(cx_ - rx_, cx_ + rx_ + 1):
                if not (0 <= yy < H and 0 <= xx < W):
                    continue
                if ((xx - cx_) / rx_) ** 2 + ((yy - cy_) / ry_) ** 2 <= 1.0:
                    if g[yy, xx] in (9, 10, 11, 12, 13, 14, 15, 16):
                        g[yy, xx] = 3 if (xx + yy) % 7 else 4

    # 把脸从苔藓底下恢复出来（眼、嘴、牙不能被苔藓吃掉）
    for _y in range(H):
        for _x in range(W):
            if face_snap[_y, _x] in FACE_IDS:
                g[_y, _x] = face_snap[_y, _x]

    # ==================================================================
    # 9. 藤蔓
    # ==================================================================
    for (vx, vy, vlen) in ((74, 106, 62), (150, 102, 84), (196, 130, 52)):
        px = vx
        for i in range(vlen):
            py = vy + i
            if i % 5 == 0:
                px += rng.randint(-1, 2)
            rect(g, px, py, px + 1, py, 11 if i % 7 else 12)
            if i % 9 == 4:
                ell(g, px + 3, py, 3, 2, 12)

    # ==================================================================
    # 10. 鸟蛋（画在手之后 → 手在蛋前面，有握持关系）
    # ==================================================================
    ECX, ECY = 26, 86
    egg = []
    N = 44
    for i in range(N):
        a = i * 2 * math.pi / N
        sa, ca = math.sin(a), math.cos(a)
        kx = 1.0 - 0.14 * max(0.0, -sa)      # 上半收窄 14%
        ry = 26 if sa > 0 else 22             # 下半略长
        egg.append((ECX + ca * 20 * kx, ECY + sa * ry))
    poly(g, egg, 23)
    for (dx, dy, rx, ry, c) in ((0, 0, 18, 24, 24), (-2, -3, 15, 20, 25),
                                (-4, -7, 11, 14, 26), (-6, -11, 6, 8, 27)):
        poly(g, [(ECX + dx + math.cos(a * 2 * math.pi / 32) * rx * (
            1.0 - 0.12 * max(0.0, -math.sin(a * 2 * math.pi / 32))),
            ECY + dy + math.sin(a * 2 * math.pi / 32) * ry) for a in range(32)], c)
    for _ in range(20):
        a = rng.rand() * 2 * math.pi
        rr = 0.5 + rng.rand() * 0.4
        px_ = int(ECX + math.cos(a) * 18 * rr)
        py_ = int(ECY + math.sin(a) * 22 * rr)
        if g[py_, px_] in (23, 24, 25):
            ell(g, px_, py_, 1 + int(rng.rand() * 2), 1,
                26 if rng.rand() < 0.5 else 27)
    ell(g, 30, 102, 10, 4, 24)

    # ==================================================================
    # 11. 顶部枯枝：从侧面伸出，不与木冠打架
    # ==================================================================
    for (bx, by, ex, ey, w) in ((84, 124, 48, 98, 5), (158, 132, 196, 106, 4),
                                (104, 118, 92, 92, 3)):
        line(g, bx, by, ex, ey, 2, w)
        line(g, bx, by, ex, ey, 4, 1)
        mx, my = (bx + ex) // 2, (by + ey) // 2
        line(g, mx, my, mx + 8, my - 10, 3, 2)

    # ==================================================================
    # 12. 底部小石头 / 蘑菇 / 萤光
    # ==================================================================
    for (sx, sy, sr) in ((40, 292, 9), (74, 296, 8), (120, 297, 9),
                         (164, 296, 8), (198, 292, 8)):
        ell(g, sx, sy, sr, sr - 3, 34)
        ell(g, sx - 2, sy - 2, sr - 4, sr - 5, 35)

    for (mx, my, mw) in ((58, 272, 5), (168, 276, 4), (204, 268, 5)):
        rect(g, mx, my - 6, mx + 1, my, 25)
        ell(g, mx, my - 8, mw, 3, 30)
        ell(g, mx - 1, my - 9, mw - 2, 2, 31)

    for _ in range(26):
        x = 50 + int(rng.rand() * 140)
        y = 100 + int(rng.rand() * 160)
        if in_bark(x, y) and g[y, x] in (9, 10, 11, 12, 13):
            rect(g, x, y, x, y, 41)

    # ==================================================================
    # 13. 顶部小兽（站在木冠上）
    # ==================================================================
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

    # ==================================================================
    # 14. 左缘轮廓光：把主体从暗背景里"切"出来
    # ==================================================================
    for y in range(Y_TOP, Y_BOT + 1):
        row = np.nonzero(g[y] > 0)[0]
        if row.size == 0:
            continue
        x = int(row[0])
        if not (1 <= g[y, x] <= 8):
            continue
        g[y, x] = 8
        if 0 <= x + 1 < W and 1 <= g[y, x + 1] <= 8:
            g[y, x + 1] = 7

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
    # （乘子不要压太狠，否则下半身糊成一团黑）
    if solid.any():
        yy = np.arange(h, dtype=np.float32)[:, None] / float(h)
        xx = np.arange(w, dtype=np.float32)[None, :] / float(w)
        k = (1.34 - 0.34 * yy) * (1.16 - 0.16 * xx)
        lit = np.clip(rgb.astype(np.float32) * k[..., None], 0, 255).astype(np.uint8)
        # 暖调偏移：暗部偏冷、亮部偏暖（比纯乘子更有空气感）
        warm = (lit[..., 0].astype(np.int16) + 4,
                lit[..., 1].astype(np.int16) + 1,
                lit[..., 2].astype(np.int16) - 3)
        lit = np.stack(warm, axis=-1).clip(0, 255).astype(np.uint8)
        rgb[solid] = lit[solid]
        if outline:
            rgb[edge] = PAL[42]        # 描边不参与明暗，保持轮廓清晰

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
