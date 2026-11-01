# -*- coding: utf-8 -*-
"""
sprites.py —— 角色 / 怪物像素美术（程序化生成，带描边、明暗、动画帧）
============================================================================
相比旧版 26x44 的"色块狗"，本模块用像素级建模 + 自动描边 + 顶光/底部阴影
生成 36x52 的角色与 34x30 的怪物，并带多帧动画：

    角色：idle(2) / run(4) / jump / fall / block / hurt
    怪物：ground(2) / fly(2)

所有结果在首次调用时构建并缓存，运行时零开销。
"""
import math

import numpy as np
import pygame

W, H = 36, 52
MW, MH = 34, 30
FW, FH = 36, 28

OUTLINE = (22, 18, 26)

PALETTES = {
    "archer": {
        1: (248, 246, 240),   # 亮毛
        2: (206, 204, 198),   # 暗毛
        3: (86, 150, 134),    # 斗篷/兜帽
        4: (46, 96, 86),      # 斗篷暗部
        5: (226, 188, 104),   # 金饰
        6: (40, 42, 52),      # 眼
        7: (66, 52, 48),      # 鼻
        8: (152, 110, 72),    # 皮带/木
    },
    "guard": {
        1: (208, 158, 108),
        2: (156, 108, 70),
        3: (94, 108, 128),    # 甲片
        4: (58, 68, 86),
        5: (198, 206, 220),   # 钢
        6: (40, 42, 52),
        7: (66, 52, 48),
        8: (122, 78, 50),
    },
}


def _blank(w, h):
    return np.zeros((h, w), dtype=np.int16)


def _rect(g, x0, y0, x1, y1, pid):
    x0 = max(0, int(x0)); y0 = max(0, int(y0))
    x1 = min(g.shape[1] - 1, int(x1)); y1 = min(g.shape[0] - 1, int(y1))
    if x1 >= x0 and y1 >= y0:
        g[y0:y1 + 1, x0:x1 + 1] = pid


def _ellipse(g, cx, cy, rx, ry, pid):
    h, w = g.shape
    for y in range(max(0, int(cy - ry)), min(h, int(cy + ry) + 1)):
        for x in range(max(0, int(cx - rx)), min(w, int(cx + rx) + 1)):
            dx = (x - cx) / max(0.6, rx)
            dy = (y - cy) / max(0.6, ry)
            if dx * dx + dy * dy <= 1.0:
                g[y, x] = pid


def _tri(g, pts, pid):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    x0, x1 = int(min(xs)), int(max(xs))
    y0, y1 = int(min(ys)), int(max(ys))
    for y in range(max(0, y0), min(g.shape[0] - 1, y1) + 1):
        for x in range(max(0, x0), min(g.shape[1] - 1, x1) + 1):
            s = []
            for i in range(3):
                ax, ay = pts[i]
                bx, by = pts[(i + 1) % 3]
                s.append((bx - ax) * (y - ay) - (by - ay) * (x - ax))
            if (all(v >= -0.01 for v in s) or all(v <= 0.01 for v in s)):
                g[y, x] = pid


def _poly(g, pts, pid):
    """扫描线填充任意凸/凹多边形（Boss 的梯形躯干、不规则甲片用）。"""
    ys = [p[1] for p in pts]
    y0 = max(0, int(min(ys)))
    y1 = min(g.shape[0] - 1, int(max(ys)))
    for y in range(y0, y1 + 1):
        xs = []
        n = len(pts)
        for i in range(n):
            xa, ya = pts[i]
            xb, yb = pts[(i + 1) % n]
            if (ya <= y < yb) or (yb <= y < ya):
                xs.append(xa + (y - ya) * (xb - xa) / float(yb - ya))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            for x in range(max(0, int(xs[i])), min(g.shape[1] - 1, int(xs[i + 1])) + 1):
                g[y, x] = pid


def _render(g, pal, outline=True, shade=True):
    """把部件矩阵渲染成 Surface：自动外描边 + 顶部提亮 + 底部压暗。"""
    h, w = g.shape
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    px = pygame.PixelArray(surf)
    # 描边（先画在最底层，避免覆盖主体）
    if outline:
        empty = (g == 0)
        adj = np.zeros_like(empty)
        adj[1:, :] |= (~empty)[:-1, :]
        adj[:-1, :] |= (~empty)[1:, :]
        adj[:, 1:] |= (~empty)[:, :-1]
        adj[:, :-1] |= (~empty)[:, 1:]
        edge = empty & adj
        for y, x in zip(*np.where(edge)):
            surf.set_at((int(x), int(y)), OUTLINE)
    for pid, col in pal.items():
        mask = (g == pid)
        if not mask.any():
            continue
        ys, xs = np.where(mask)
        for y, x in zip(ys, xs):
            c = col
            if shade:
                if y > 0 and g[y - 1, x] == 0:
                    c = (min(255, int(col[0] * 1.18 + 14)),
                         min(255, int(col[1] * 1.18 + 14)),
                         min(255, int(col[2] * 1.18 + 14)))
                elif y < h - 1 and g[y + 1, x] == 0:
                    c = (int(col[0] * 0.72), int(col[1] * 0.72), int(col[2] * 0.74))
            surf.set_at((int(x), int(y)), c)
    del px
    return surf


def _line(g, x0, y0, x1, y1, pid):
    n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    for i in range(n + 1):
        t = i / float(max(1, n))
        x = int(round(x0 + (x1 - x0) * t))
        y = int(round(y0 + (y1 - y0) * t))
        if 0 <= y < g.shape[0] and 0 <= x < g.shape[1]:
            g[y, x] = pid


# --------------------------------------------------------------------------
# 角色
# --------------------------------------------------------------------------
def _character(kind, pose="idle0", frame=0):
    g = _blank(W, H)
    archer = (kind == "archer")

    # ---- 姿态参数 ----
    bob = 0
    leg = 0.0
    lean = 0
    if pose == "idle1":
        bob = 1
    elif pose.startswith("run"):
        leg = (0, 1, 0, -1)[frame % 4]
        bob = (0, -1, 0, -1)[frame % 4]
        lean = 1
    elif pose == "jump":
        bob = -2
        leg = 0.8
    elif pose == "fall":
        leg = -0.8
    elif pose == "block":
        bob = 1

    top = 5 + bob
    hx, hy = 18 + lean, top + 12          # 头部中心

    # ---- 尾巴 / 披风 ----
    if archer:
        # 围巾（随风）
        _tri(g, [(12, top + 22), (2 - lean, top + 20), (10, top + 27)], 4)
        _tri(g, [(12, top + 23), (4 - lean, top + 25), (11, top + 28)], 3)
    else:
        _rect(g, 24, top + 25, 30, top + 28, 2)
        _tri(g, [(28, top + 25), (33, top + 20), (30, top + 28)], 2)

    # ---- 腿 ----
    swing = int(round(leg * 3))
    _rect(g, 11 + swing, top + 35, 16 + swing, top + 47, 2)
    _rect(g, 19 - swing, top + 35, 24 - swing, top + 47, 1)
    _rect(g, 10 + swing, top + 45, 17 + swing, top + 49, 8)
    _rect(g, 18 - swing, top + 45, 25 - swing, top + 49, 8)
    if not archer:
        _rect(g, 10 + swing, top + 34, 17 + swing, top + 37, 4)   # 护腿
        _rect(g, 18 - swing, top + 34, 25 - swing, top + 37, 4)

    # ---- 躯干 ----
    if archer:
        _rect(g, 12, top + 21, 24, top + 36, 3)
        _rect(g, 12, top + 21, 14, top + 36, 4)
        _rect(g, 12, top + 31, 24, top + 33, 8)
        _rect(g, 16, top + 24, 20, top + 28, 5)
        # 箭袋
        _rect(g, 7, top + 23, 11, top + 33, 8)
        _rect(g, 8, top + 21, 10, top + 24, 5)
    else:
        _rect(g, 10, top + 20, 26, top + 36, 3)
        _rect(g, 10, top + 20, 13, top + 36, 4)
        _rect(g, 10, top + 28, 26, top + 30, 4)
        _rect(g, 10, top + 34, 26, top + 37, 8)      # 战裙
        _rect(g, 8, top + 20, 12, top + 25, 5)
        _rect(g, 24, top + 20, 28, top + 25, 5)
        _rect(g, 16, top + 22, 20, top + 26, 5)

    # ---- 手臂 ----
    if archer:
        _rect(g, 23, top + 22, 26, top + 30, 1)
        _rect(g, 21, top + 28, 25, top + 31, 1)
        _rect(g, 21, top + 28, 25, top + 29, 8)      # 护腕
    else:
        _rect(g, 7, top + 23, 10, top + 32, 2)
        _rect(g, 7, top + 29, 11, top + 32, 5)
        if pose == "block":
            _rect(g, 25, top + 19, 28, top + 28, 2)
        else:
            _rect(g, 24, top + 24, 27, top + 32, 2)
            _rect(g, 24, top + 29, 28, top + 32, 5)

    # ---- 头 ----
    _ellipse(g, hx, hy, 8, 7, 1)
    _ellipse(g, hx, hy + 4, 4, 2, 1)
    # 口鼻
    _rect(g, hx - 1, hy + 3, hx + 1, hy + 4, 7)
    _line(g, hx, hy + 5, hx, hy + 6, 7)
    # 眼睛
    _rect(g, hx - 5, hy - 1, hx - 4, hy + 1, 6)
    _rect(g, hx + 4, hy - 1, hx + 5, hy + 1, 6)
    g[hy - 1, hx - 5] = 0
    g[hy - 1, hx + 4] = 0
    if archer:
        # 兜帽内侧投影：只压 1px，让脸有"藏在帽檐下"的层次，而不是一块白
        _rect(g, hx - 6, hy - 3, hx + 6, hy - 3, 2)

    # ---- 耳朵 ----
    if archer:
        _tri(g, [(hx - 8, hy - 3), (hx - 5, hy - 11), (hx - 2, hy - 4)], 1)
        _tri(g, [(hx + 2, hy - 4), (hx + 5, hy - 11), (hx + 8, hy - 3)], 1)
        _tri(g, [(hx - 6, hy - 5), (hx - 5, hy - 9), (hx - 4, hy - 5)], 2)
        _tri(g, [(hx + 4, hy - 5), (hx + 5, hy - 9), (hx + 6, hy - 5)], 2)
    else:
        _tri(g, [(hx - 8, hy - 2), (hx - 6, hy - 9), (hx - 3, hy - 4)], 2)
        _tri(g, [(hx + 3, hy - 4), (hx + 6, hy - 9), (hx + 8, hy - 2)], 2)

    # ---- 帽子 / 头盔 ----
    if archer:
        # 兜帽：覆盖头顶与后脑
        _ellipse(g, hx, hy - 4, 9, 5, 3)
        _rect(g, hx - 9, hy - 4, hx + 9, hy - 2, 3)
        _tri(g, [(hx - 9, hy - 3), (hx - 14, hy + 2), (hx - 8, hy + 4)], 4)
        _rect(g, hx - 9, hy - 3, hx + 9, hy - 2, 4)
        _rect(g, hx - 2, hy - 6, hx + 2, hy - 3, 5)
    else:
        # 头盔：金属盔 + 护鼻 + 红缨
        _ellipse(g, hx, hy - 3, 9, 6, 5)
        _rect(g, hx - 10, hy - 4, hx + 10, hy - 1, 5)
        _rect(g, hx - 10, hy - 1, hx + 10, hy, 4)
        _rect(g, hx - 1, hy - 3, hx + 1, hy + 4, 5)
        _rect(g, hx - 1, hy + 1, hx, hy + 3, 4)
        for i in range(4):
            _rect(g, hx - 1 + i // 2, hy - 9 - i, hx + 1, hy - 8 - i, 2)

    # ---- 弓（弓箭手）：上下弓臂 + 中间握把 + 弓弦，避免读成"圆环" ----
    if archer:
        # 弓：深木色弓臂 + 浅色细弦（金色会读成火把）
        pts = []
        for i in range(13):
            a = -1.15 + i * 0.19
            pts.append((29 + int(math.cos(a) * 6), int(top + 27 + math.sin(a) * 10)))
        for i in range(len(pts) - 1):
            _line(g, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], 8)
        _rect(g, 29, top + 25, 32, top + 29, 5)      # 握把（金饰）
        _line(g, pts[0][0] - 1, pts[0][1], pts[-1][0] - 1, pts[-1][1], 2)   # 浅色弓弦
    return g


# --------------------------------------------------------------------------
# 怪物
# --------------------------------------------------------------------------
def _ground_monster(frame=0):
    g = _blank(MW, MH)
    squish = 1 if frame else 0
    y0 = 6 + squish
    # 身体
    _ellipse(g, 17, y0 + 11, 13, 10 - squish, 1)
    _rect(g, 5, y0 + 12, 29, y0 + 22, 1)
    # 背刺
    for i in range(4):
        x = 8 + i * 6
        _tri(g, [(x, y0 + 6), (x + 3, y0 - 2), (x + 6, y0 + 6)], 2)
    # 脚
    _rect(g, 6, y0 + 21, 13, y0 + 24, 2)
    _rect(g, 21, y0 + 21, 28, y0 + 24, 2)
    # 眼睛
    _rect(g, 11, y0 + 11, 13, y0 + 14, 3)
    _rect(g, 21, y0 + 11, 23, y0 + 14, 3)
    _rect(g, 12, y0 + 11, 12, y0 + 12, 4)
    _rect(g, 22, y0 + 11, 22, y0 + 12, 4)
    # 獠牙
    _tri(g, [(13, y0 + 18), (16, y0 + 18), (14, y0 + 22)], 4)
    _tri(g, [(18, y0 + 18), (21, y0 + 18), (20, y0 + 22)], 4)
    return g


def _fly_monster(frame=0):
    g = _blank(FW, FH)
    flap = frame % 2
    # 翅膀
    if flap == 0:
        _tri(g, [(2, 4), (16, 10), (3, 16)], 2)
        _tri(g, [(34, 4), (20, 10), (33, 16)], 2)
    else:
        _tri(g, [(2, 12), (16, 10), (4, 22)], 2)
        _tri(g, [(34, 12), (20, 10), (32, 22)], 2)
    # 身体
    _ellipse(g, 18, 13, 8, 7, 1)
    _rect(g, 14, 15, 22, 23, 1)
    # 耳朵
    _tri(g, [(11, 7), (14, 0), (16, 7)], 1)
    _tri(g, [(25, 7), (22, 0), (20, 7)], 1)
    # 眼睛
    _rect(g, 13, 11, 15, 15, 3)
    _rect(g, 21, 11, 23, 15, 3)
    _rect(g, 14, 11, 14, 12, 4)
    _rect(g, 22, 11, 22, 12, 4)
    # 小尖牙
    _tri(g, [(16, 18), (18, 18), (17, 21)], 4)
    _tri(g, [(19, 18), (21, 18), (20, 21)], 4)
    return g


BW, BH = 92, 112


def _boss(frame=0):
    """熔炉守卫：铁铸巨像（第二版）。

    轮廓全部用斜切多边形，不用矩形直边——上一版是"矩形+椭圆拼贴"，
    远看像积木。这一版：宽肩窄腰的铁砧躯干、斜切肩甲、两段手臂带肘关节、
    方拳、平顶盔（去掉头顶尖角）、胸口敞开炉膛 + 四道炉栅。
    """
    g = _blank(BW, BH)
    sway = 1 if frame else 0

    # ===== 背部排气口 =====
    _poly(g, [(26, 22), (36, 22), (34, 42), (28, 42)], 2)
    _poly(g, [(56, 22), (66, 22), (64, 42), (58, 42)], 2)
    _rect(g, 25, 20, 37, 24, 7)
    _rect(g, 55, 20, 67, 24, 7)

    # ===== 腿（粗短）=====
    _poly(g, [(30, 84), (44, 84), (43, 100), (31, 100)], 1)
    _poly(g, [(48, 84), (62, 84), (61, 100), (49, 100)], 1)
    _poly(g, [(38, 84), (44, 84), (43, 100), (39, 100)], 2)
    _poly(g, [(48, 84), (54, 84), (53, 100), (49, 100)], 2)
    # 铁靴（宽阔）
    _poly(g, [(26, 98), (46, 98), (48, 110), (24, 110)], 3)
    _poly(g, [(46, 98), (66, 98), (68, 110), (44, 110)], 3)
    _rect(g, 24, 107, 48, 110, 2)
    _rect(g, 44, 107, 68, 110, 2)

    # ===== 躯干（宽肩窄腰）=====
    _poly(g, [(20, 42), (72, 42), (64, 90), (28, 90)], 1)
    _poly(g, [(20, 42), (32, 42), (36, 90), (28, 90)], 2)
    _line(g, 46, 44, 46, 82, 4)
    _poly(g, [(28, 80), (64, 80), (64, 90), (28, 90)], 2)
    _line(g, 30, 82, 62, 82, 3)

    # ===== 肩甲（斜切，不带长尖刺）=====
    _poly(g, [(4, 46), (18, 36), (34, 44), (32, 58), (8, 60)], 1)
    _poly(g, [(88, 46), (74, 36), (58, 44), (60, 58), (84, 60)], 1)
    _poly(g, [(4, 46), (12, 40), (20, 46), (18, 58), (8, 60)], 3)
    _poly(g, [(88, 46), (80, 40), (72, 46), (74, 58), (84, 60)], 3)
    _tri(g, [(7, 46), (4, 35), (13, 43)], 3)
    _tri(g, [(85, 46), (88, 35), (79, 43)], 3)

    # ===== 手臂（上臂 / 肘 / 前臂 / 方拳）=====
    # 上臂（更靠外，和躯干留出缝隙）
    _poly(g, [(4 + sway, 50), (17 + sway, 50), (16 + sway, 70), (3 + sway, 70)], 1)
    _poly(g, [(74 - sway, 50), (87 - sway, 50), (88 - sway, 70), (75 - sway, 70)], 1)
    _poly(g, [(4 + sway, 50), (8 + sway, 50), (7 + sway, 70), (3 + sway, 70)], 3)
    _poly(g, [(83 - sway, 50), (87 - sway, 50), (88 - sway, 70), (84 - sway, 70)], 3)
    # 肘关节
    _rect(g, 3 + sway, 68, 17 + sway, 72, 2)
    _rect(g, 75 - sway, 68, 89 - sway, 72, 2)
    # 前臂
    _poly(g, [(2 + sway, 72), (16 + sway, 72), (18 + sway, 88), (0 + sway, 88)], 1)
    _poly(g, [(76 - sway, 72), (90 - sway, 72), (92 - sway, 88), (74 - sway, 88)], 1)
    _poly(g, [(2 + sway, 72), (6 + sway, 72), (4 + sway, 88), (0 + sway, 88)], 3)
    _poly(g, [(86 - sway, 72), (90 - sway, 72), (92 - sway, 88), (88 - sway, 88)], 3)
    # 方拳（比头大）
    _poly(g, [(0 + sway, 86), (19 + sway, 86), (21 + sway, 104), (-1 + sway, 104)], 1)
    _poly(g, [(73 - sway, 86), (92 - sway, 86), (94 - sway, 104), (72 - sway, 104)], 1)
    _rect(g, 0 + sway, 86, 21 + sway, 89, 3)
    _rect(g, 72 - sway, 86, 92 - sway, 89, 3)
    _line(g, 1 + sway, 95, 20 + sway, 95, 2)
    _line(g, 73 - sway, 95, 92 - sway, 95, 2)

    # ===== 头（陷在肩间，平顶盔）=====
    _poly(g, [(34, 16), (58, 16), (60, 24), (32, 24)], 3)
    _rect(g, 44, 14, 48, 18, 2)
    _poly(g, [(32, 24), (60, 24), (58, 42), (34, 42)], 1)
    _rect(g, 33, 27, 59, 36, 4)
    _rect(g, 36, 29, 44, 34, 5)
    _rect(g, 48, 29, 56, 34, 5)
    _rect(g, 38, 30, 42, 33, 6)
    _rect(g, 50, 30, 54, 33, 6)
    _poly(g, [(36, 38), (56, 38), (54, 43), (38, 43)], 2)

    # ===== 胸口熔炉（炉膛 + 熔岩 + 白热 + 炉栅）=====
    _ellipse(g, 46, 64, 16, 17, 4)
    _ellipse(g, 46, 64, 12, 13, 5)
    _ellipse(g, 46, 64, 6, 7, 6)
    for yy in (56, 62, 68, 74):
        _rect(g, 34, yy, 58, yy + 1, 4)

    # ===== 熔岩裂纹 =====
    _line(g, 40, 80, 34, 88, 5)
    _line(g, 52, 80, 58, 88, 5)
    _line(g, 30, 56, 22, 50, 5)

    # ===== 锈斑 =====
    _rect(g, 26, 74, 30, 78, 7)
    _rect(g, 62, 48, 66, 52, 7)

    return g


BPAL = {
    1: (106, 98, 94),      # 主体：偏暖的铸铁灰（冷紫灰会显得像塑料）
    2: (60, 52, 50),       # 暗面
    3: (150, 142, 132),    # 亮甲 / 高光
    4: (26, 22, 22),       # 深缝、炉膛
    5: (255, 142, 48),     # 熔岩橙
    6: (255, 234, 176),    # 白热
    7: (142, 76, 48),      # 锈红
}

CW, CH = 36, 44


def _caster(frame=0):
    """熔岩术士：漂浮的施法者，法杖顶端有火球。"""
    g = _blank(CW, CH)
    bob = 1 if frame else 0
    # 兜帽斗篷
    _ellipse(g, 18, 18 + bob, 10, 9, 1)
    _tri(g, [(8, 20 + bob), (18, 4 + bob), (28, 20 + bob)], 1)
    _rect(g, 9, 18 + bob, 27, 34 + bob, 2)
    _tri(g, [(9, 34 + bob), (18, 42 + bob), (27, 34 + bob)], 2)
    # 兜帽阴影与眼
    _ellipse(g, 18, 19 + bob, 6, 5, 3)
    _rect(g, 14, 18 + bob, 16, 20 + bob, 4)
    _rect(g, 20, 18 + bob, 22, 20 + bob, 4)
    # 法杖
    _line(g, 27, 10 + bob, 30, 34 + bob, 6)
    _ellipse(g, 27, 9 + bob, 3, 3, 5)
    # 飘带
    _line(g, 10, 28 + bob, 5, 34 + bob, 2)
    _line(g, 26, 28 + bob, 31, 34 + bob, 2)
    return g


CPAL = {
    1: (108, 84, 150),
    2: (76, 58, 108),
    3: (40, 30, 58),
    4: (255, 196, 120),
    5: (255, 150, 70),
    6: (138, 104, 76),
}

MPAL_GROUND = {
    1: (118, 148, 96),
    2: (84, 110, 72),
    3: (246, 214, 96),
    4: (250, 248, 236),
}
MPAL_FLY = {
    1: (150, 108, 176),
    2: (104, 68, 132),
    3: (255, 214, 120),
    4: (250, 248, 236),
}


# --------------------------------------------------------------------------
# 缓存接口
# --------------------------------------------------------------------------
_cache = {}
POSES = ("idle0", "idle1", "run0", "run1", "run2", "run3", "jump", "fall", "block")


def get_char(kind, pose="idle0"):
    key = (kind, pose)
    s = _cache.get(key)
    if s is not None:
        return s
    frame = int(pose[-1]) if pose.startswith("run") else 0
    base_pose = "idle" if pose.startswith("idle") else pose
    if pose.startswith("run"):
        base_pose = "run"
    g = _character(kind, base_pose, frame)
    pal = PALETTES["archer" if kind == "archer" else "guard"]
    s = _render(g, pal)
    _cache[key] = s
    return s


def get_monster(kind, frame=0):
    key = ("mon", kind, frame)
    s = _cache.get(key)
    if s is not None:
        return s
    if kind == "boss":
        s = _render(_boss(frame), BPAL)
        _cache[key] = s
        return s
    if kind == "caster":
        s = _render(_caster(frame), CPAL)
        _cache[key] = s
        return s
    if kind == "fly":
        s = _render(_fly_monster(frame), MPAL_FLY)
    else:
        s = _render(_ground_monster(frame), MPAL_GROUND)
    _cache[key] = s
    return s


def prebuild():
    for kind in ("archer", "guard"):
        for pose in POSES:
            get_char(kind, pose)
    for f in (0, 1):
        get_monster("ground", f)
        get_monster("fly", f)
        get_monster("boss", f)
        get_monster("caster", f)
