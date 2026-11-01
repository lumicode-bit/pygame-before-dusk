# -*- coding: utf-8 -*-
"""独立演示：树精 Boss（**不修改项目任何文件**，纯预览）

运行：
    python tools/demo_treeboss.py

产物写到 shots/demo_*.png，仅供效果确认。
确认满意后再决定要不要落地到 game_core / sprites。
"""
import os
import sys

import numpy as np
import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

W, H = 176, 208          # 参考图里树精大约这个量级（原图约 200px 高）

# ---- 调色板：22 色，4 阶明暗 + 苔藓独立色系 ----
PAL = {
    1: (44, 34, 26),      # 树皮最暗
    2: (70, 54, 38),      # 树皮
    3: (100, 78, 52),     # 树皮亮
    4: (134, 108, 74),    # 树皮高光
    5: (58, 74, 38),      # 苔藓暗
    6: (96, 124, 52),     # 苔藓
    7: (140, 168, 68),    # 苔藓亮
    8: (188, 216, 98),    # 苔藓高光
    9: (22, 16, 14),      # 树洞黑
    10: (54, 42, 34),     # 树洞内壁
    11: (206, 200, 178),  # 骨白
    12: (242, 240, 220),  # 球亮面
    13: (172, 168, 144),  # 球暗面
    14: (218, 120, 58),   # 小兽橙
    15: (150, 74, 36),    # 小兽暗
    16: (54, 54, 50),     # 石头暗
    17: (90, 90, 84),     # 石头
    18: (128, 128, 120),  # 石头亮
    19: (206, 62, 44),    # 眼红
    20: (78, 62, 44),     # 枯枝
    21: (36, 48, 26),     # 苔藓最深（缝）
    22: (16, 12, 12),     # 描边
}


def blank(w=W, h=H):
    return np.zeros((h, w), dtype=np.int16)


def _clip(v, lo, hi):
    return max(lo, min(hi, int(v)))


def poly(g, pts, pid):
    """扫描线填充多边形。"""
    h, w = g.shape
    ys = [p[1] for p in pts]
    y0, y1 = _clip(min(ys), 0, h - 1), _clip(max(ys), 0, h - 1)
    n = len(pts)
    for y in range(y0, y1 + 1):
        xs = []
        for i in range(n):
            ax, ay = pts[i]
            bx, by = pts[(i + 1) % n]
            if ay == by:
                continue
            if min(ay, by) <= y < max(ay, by):
                t = (y - ay) / float(by - ay)
                xs.append(ax + (bx - ax) * t)
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            xa = _clip(round(xs[i]), 0, w - 1)
            xb = _clip(round(xs[i + 1]), 0, w - 1)
            if xb >= xa:
                g[y, xa:xb + 1] = pid


def rect(g, x0, y0, x1, y1, pid):
    h, w = g.shape
    x0, x1 = _clip(x0, 0, w - 1), _clip(x1, 0, w - 1)
    y0, y1 = _clip(y0, 0, h - 1), _clip(y1, 0, h - 1)
    if x1 >= x0 and y1 >= y0:
        g[y0:y1 + 1, x0:x1 + 1] = pid


def ell(g, cx, cy, rx, ry, pid):
    h, w = g.shape
    for y in range(_clip(cy - ry, 0, h - 1), _clip(cy + ry, 0, h - 1) + 1):
        for x in range(_clip(cx - rx, 0, w - 1), _clip(cx + rx, 0, w - 1) + 1):
            dx = (x - cx) / max(0.7, rx)
            dy = (y - cy) / max(0.7, ry)
            if dx * dx + dy * dy <= 1.0:
                g[y, x] = pid


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
            rect(g, x - wdt // 2, y - wdt // 2,
                 x + wdt // 2, y + wdt // 2, pid)


# --------------------------------------------------------------------------
# 树精本体
# --------------------------------------------------------------------------
def build_tree():
    g = blank()
    rng = np.random.RandomState(11)

    # ===== 底部石堆 =====
    poly(g, [(14, 198), (24, 184), (44, 188), (58, 182), (72, 192),
             (88, 184), (102, 190), (118, 182), (134, 188), (150, 184),
             (162, 198)], 16)
    poly(g, [(24, 198), (28, 190), (44, 192), (56, 188), (68, 196),
             (84, 190), (98, 194), (114, 188), (130, 192), (142, 188),
             (154, 198)], 17)
    for (sx, sy, sr) in ((32, 190, 8), (60, 192, 7), (92, 190, 8),
                         (124, 192, 7), (150, 191, 6)):
        ell(g, sx, sy, sr, sr - 2, 18)
        ell(g, sx - 2, sy - 2, sr - 4, sr - 5, 17)

    # ===== 树桩主体：参数化轮廓（下宽上窄 + 每 7px 一点锯齿）=====
    left, right = [], []
    for y in range(74, 188, 7):
        t = (y - 74) / 114.0
        half = 40 + t * 16.0                       # 半宽 40 -> 56
        jag = (3, -2, 4, -3, 2, -4)[(y // 7) % 6]
        left.append((88 - half + jag, y))
        right.append((88 + half - jag, y))
    poly(g, left + right[::-1], 2)

    # 体积感：左侧受光、右侧背光
    for y in range(74, 188, 3):
        t = (y - 74) / 114.0
        half = 40 + t * 16.0
        line(g, int(88 - half) + 2, y, int(88 - half) + 9, y, 3)
        line(g, int(88 + half) - 8, y, int(88 + half) - 1, y, 1)

    # 每层的横向分界（深缝）+ 缝上的苔藓
    for i, yy in enumerate((92, 110, 128, 148, 166)):
        t = (yy - 74) / 114.0
        half = 40 + t * 16.0
        line(g, int(88 - half) + 1, yy, int(88 + half) - 1, yy + 1, 1, 2)
        for k in range(6):
            mx = int(88 - half + 6 + rng.rand() * (half * 2 - 12))
            ell(g, mx, yy + rng.randint(-1, 2), rng.randint(2, 4),
                rng.randint(1, 3), 6 if rng.rand() < 0.5 else 5)

    # 竖向树皮纹
    for i in range(34):
        x = 46 + int(rng.rand() * 84)
        y0 = 76 + int(rng.rand() * 34)
        y1 = y0 + 12 + int(rng.rand() * 28)
        line(g, x, y0, x + rng.randint(-2, 3), y1, 1)

    # ===== 树洞（嘴）=====
    poly(g, [(60, 132), (72, 124), (104, 123), (116, 132),
             (114, 152), (98, 162), (74, 161), (62, 151)], 9)
    poly(g, [(66, 134), (76, 129), (100, 128), (110, 134),
             (108, 148), (96, 156), (78, 155), (68, 146)], 10)
    for (tx, ty, tw) in ((72, 130, 5), (86, 128, 6), (100, 129, 5)):
        poly(g, [(tx, ty), (tx + tw, ty), (tx + tw // 2, ty + 12)], 11)
    for (tx, ty, tw) in ((76, 160, 5), (92, 161, 6)):
        poly(g, [(tx, ty), (tx + tw, ty), (tx + tw // 2, ty - 10)], 11)

    # ===== 眼睛 =====
    ell(g, 68, 114, 8, 6, 9)
    ell(g, 106, 114, 8, 6, 9)
    ell(g, 69, 115, 3, 2, 19)
    ell(g, 107, 115, 3, 2, 19)
    line(g, 58, 107, 76, 110, 1, 2)
    line(g, 98, 110, 116, 107, 1, 2)

    # ===== 苔藓：顶部厚厚一层 + 边缘垂落 =====
    poly(g, [(44, 80), (58, 72), (96, 71), (120, 76), (126, 86),
             (110, 82), (86, 78), (58, 80), (48, 86)], 6)
    poly(g, [(46, 80), (60, 74), (94, 73), (116, 78), (112, 84),
             (86, 80), (60, 82), (50, 86)], 7)
    for i in range(26):
        x = 44 + int(rng.rand() * 88)
        y = 76 + int(rng.rand() * 20)
        rect(g, x, y, x + 1, y, 8)
    # 两侧垂下来的苔藓
    for side in (-1, 1):
        for k in range(9):
            x = 88 + side * (44 + int(rng.rand() * 14))
            y = 84 + int(rng.rand() * 78)
            ell(g, x, y, rng.randint(2, 5), rng.randint(1, 4),
                6 if rng.rand() < 0.55 else 5)

    # ===== 左臂（枯枝，托白球）=====
    poly(g, [(52, 120), (34, 112), (20, 100), (24, 94), (38, 104),
             (56, 112)], 20)
    poly(g, [(22, 100), (12, 90), (16, 86), (26, 96)], 20)
    poly(g, [(24, 104), (12, 104), (12, 99), (24, 99)], 20)
    for (fx, fy) in ((12, 82), (19, 79), (26, 82)):
        line(g, fx, fy, fx - 1, fy - 6, 20, 2)

    ell(g, 20, 72, 16, 15, 13)
    ell(g, 19, 70, 14, 13, 12)
    ell(g, 14, 64, 6, 5, 12)
    ell(g, 24, 79, 5, 4, 13)

    # ===== 右臂（枯枝，张开）=====
    poly(g, [(122, 130), (142, 138), (156, 152), (149, 157),
             (136, 145), (120, 138)], 20)
    for (fx, fy, dx, dy) in ((157, 154, 9, 5), (155, 160, 7, 10),
                             (150, 165, 2, 11), (144, 168, -3, 9)):
        line(g, fx, fy, fx + dx, fy + dy, 20, 2)

    # ===== 背上的小枯枝 =====
    for (bx, by, ex, ey) in ((38, 96, 26, 86), (128, 100, 142, 88),
                             (60, 78, 54, 66), (112, 80, 122, 68)):
        line(g, bx, by, ex, ey, 20, 2)
        line(g, (bx + ex) // 2, (by + ey) // 2, (bx + ex) // 2 + 4,
             (by + ey) // 2 - 5, 20, 1)

    # ===== 顶部小兽 =====
    poly(g, [(104, 66), (114, 56), (118, 64), (108, 70)], 15)   # 尾巴
    ell(g, 96, 62, 10, 8, 14)
    rect(g, 89, 60, 103, 70, 14)
    ell(g, 96, 53, 7, 7, 14)
    poly(g, [(90, 48), (88, 39), (94, 46)], 14)
    poly(g, [(102, 48), (104, 39), (98, 46)], 14)
    ell(g, 96, 66, 6, 4, 12)
    rect(g, 93, 52, 94, 53, 9)
    rect(g, 99, 52, 100, 53, 9)
    rect(g, 95, 56, 97, 56, 15)

    return g


def render(g, outline=True):
    h, w = g.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    solid = (g > 0)
    for pid, col in PAL.items():
        rgb[g == pid] = col
    if outline:
        adj = np.zeros_like(solid)
        adj[1:, :] |= solid[:-1, :]
        adj[:-1, :] |= solid[1:, :]
        adj[:, 1:] |= solid[:, :-1]
        adj[:, :-1] |= solid[:, 1:]
        edge = (~solid) & adj
        rgb[edge] = PAL[22]
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(surf)[:] = np.transpose(rgb, (1, 0, 2))
    pygame.surfarray.pixels_alpha(surf)[:] = np.transpose(
        np.where(solid | (outline and ((~solid) & adj)), 255, 0).astype(np.uint8))
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

    # 对比板：树精 vs 当前 36x52 角色 vs 放大后的 64x96 角色
    board = pygame.Surface((760, 300))
    board.fill((30, 30, 40))
    board.blit(tree, (20, 300 - 208 - 20))
    try:
        import sprites
        cur = sprites.get_char("archer", "idle0", 0)
        board.blit(cur, (230, 300 - 52 - 20))
        big = pygame.transform.scale(cur, (64, 96))
        board.blit(big, (300, 300 - 96 - 20))
        pygame.draw.rect(board, (70, 70, 90), (300, 300 - 96 - 20, 64, 96), 1)
    except Exception as e:
        print("跳过角色对比:", e)
    pygame.image.save(board, os.path.join(out, "demo_compare.png"))

    # 场景预览：把它放进游戏的地面/夜色里，看当 Boss 的实际观感
    scene = pygame.Surface((640, 300))
    for i in range(300):
        k = i / 300.0
        scene.fill((int(38 + 26 * k), int(30 + 18 * k), int(46 + 20 * k)),
                   (0, i, 640, 1))
    pygame.draw.rect(scene, (58, 52, 44), (0, 250, 640, 50))
    pygame.draw.rect(scene, (86, 76, 62), (0, 250, 640, 3))
    for gx in range(0, 640, 32):
        pygame.draw.line(scene, (44, 40, 36), (gx, 253), (gx, 300), 1)
    scene.blit(tree, (240, 250 - 208 + 12))
    try:
        import sprites
        a = sprites.get_char("archer", "idle0", 0)
        gd = sprites.get_char("guard", "idle0", 0)
        scene.blit(a, (150, 250 - 52))
        scene.blit(gd, (450, 250 - 52))
    except Exception:
        pass
    pygame.image.save(scene, os.path.join(out, "demo_scene.png"))
    print("saved shots/demo_treeboss.png / demo_compare.png / demo_scene.png")


if __name__ == "__main__":
    main()
