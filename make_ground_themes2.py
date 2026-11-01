# -*- coding: utf-8 -*-
"""第二款地形款式对比：结构差异款（雪顶/余烬/遗迹砖/发光菌野）。"""
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame
import random
pygame.init()
pygame.display.set_mode((1280, 720))
T = 32
W, H = 1000, 700
out = pygame.Surface((W, H))
for y in range(H):
    f = y / H
    pygame.draw.line(out, (int(28 + 16 * f), int(24 + 10 * f), int(46 + 8 * f)), (0, y), (W, y))

_CJK = None
for _fp in (r"C:/Windows/Fonts/msyh.ttc", r"C:/Windows/Fonts/simhei.ttf"):
    if os.path.exists(_fp):
        _CJK = _fp
        break
f17 = pygame.font.Font(_CJK, 17)
f13 = pygame.font.Font(_CJK, 13)
f22 = pygame.font.Font(_CJK, 22)


def text(s, x, y, col=(232, 232, 244), f=None):
    f = f or f17
    out.blit(f.render(s, True, col), (x, y))


def _mix(c1, c2, f):
    return (int(c1[0] + (c2[0] - c1[0]) * f),
            int(c1[1] + (c2[1] - c1[1]) * f),
            int(c1[2] + (c2[2] - c1[2]) * f))


def shade(c, f):
    return _mix(c, (255, 255, 255), f) if f >= 0 else _mix(c, (0, 0, 0), -f)


# ---------------- 各款 tile 生成（结构差异，不只换色） ----------------

def snow_tile(depth, var):
    """雪顶：积雪白 + 冻土，冷冽暮雪。"""
    s = pygame.Surface((T, T), pygame.SRCALPHA)
    ramp = [(96, 104, 124), (84, 90, 108), (72, 76, 92),
            (60, 62, 76), (50, 50, 62), (42, 42, 52)]
    base = ramp[min(depth, 5)]
    rnd = random.Random(depth * 97 + var * 13 + 7)
    s.fill(base)
    for _ in range(26):
        x, y = rnd.randrange(0, T), rnd.randrange(0, T)
        s.fill(shade(base, rnd.uniform(-0.2, 0.12)), (x, y, rnd.randint(2, 4), rnd.randint(1, 3)))
    if depth == 0:
        # 积雪顶 10px，下缘波浪
        pygame.draw.rect(s, (222, 232, 246), (0, 0, T, 9))
        pygame.draw.rect(s, (240, 248, 255), (0, 0, T, 3))
        pygame.draw.rect(s, (170, 188, 212), (0, 9, T, 3))
        for x in range(0, T, 5):
            h = rnd.randint(2, 5)
            pygame.draw.rect(s, (222, 232, 246), (x, 9, 4, h))
        for _ in range(4):
            x, y = rnd.randrange(0, T), rnd.randrange(2, 7)
            pygame.draw.circle(s, (196, 212, 234), (x, y), 1)
    elif depth == 1:
        pygame.draw.rect(s, (150, 162, 184), (0, 0, T, 3))
    return s


def ember_tile(depth, var):
    """余烬地表：黑灰焦土 + 发光裂缝，火后世界。"""
    s = pygame.Surface((T, T), pygame.SRCALPHA)
    ramp = [(56, 52, 56), (48, 44, 50), (42, 38, 44),
            (36, 33, 38), (30, 28, 32), (26, 24, 28)]
    base = ramp[min(depth, 5)]
    rnd = random.Random(depth * 97 + var * 13 + 7)
    s.fill(base)
    for _ in range(26):
        x, y = rnd.randrange(0, T), rnd.randrange(0, T)
        s.fill(shade(base, rnd.uniform(-0.25, 0.14)), (x, y, rnd.randint(2, 4), rnd.randint(1, 3)))
    if depth == 0:
        pygame.draw.rect(s, (66, 60, 66), (0, 0, T, 8))
        pygame.draw.rect(s, (84, 74, 74), (0, 0, T, 2))
        # 发光裂缝（橙红，2~3 条折线）
        for _ in range(rnd.randint(2, 3)):
            x = rnd.randrange(2, T - 6)
            y = rnd.randrange(2, 8)
            pts = [(x, y)]
            for i in range(3):
                x += rnd.randint(3, 7)
                y += rnd.randint(-3, 4)
                pts.append((x, y))
            pygame.draw.lines(s, (255, 128, 52), False, pts, 1)
            for px, py in pts[1::2]:
                pygame.draw.circle(s, (255, 190, 90), (px, py), 1)
    elif depth == 1 and var % 3 == 0:
        # 深层也有微光缝
        x, y = rnd.randrange(4, T - 8), rnd.randrange(4, T - 6)
        pygame.draw.line(s, (200, 90, 40), (x, y), (x + rnd.randint(4, 9), y + rnd.randint(-2, 2)), 1)
    return s


def ruin_tile(depth, var):
    """遗迹砖顶：石砖铺装 + 苔缝，文明遗迹感。"""
    s = pygame.Surface((T, T), pygame.SRCALPHA)
    ramp = [(104, 100, 94), (92, 88, 84), (80, 78, 74),
            (68, 66, 64), (58, 56, 54), (48, 46, 46)]
    base = ramp[min(depth, 5)]
    rnd = random.Random(depth * 97 + var * 13 + 7)
    s.fill(base)
    for _ in range(24):
        x, y = rnd.randrange(0, T), rnd.randrange(0, T)
        s.fill(shade(base, rnd.uniform(-0.2, 0.12)), (x, y, rnd.randint(2, 4), rnd.randint(1, 3)))
    if depth == 0:
        # 砖排（2 排，错缝）
        pygame.draw.rect(s, (122, 118, 110), (0, 0, T, 14))
        pygame.draw.rect(s, (146, 142, 132), (0, 0, T, 2))
        for row, oy in ((0, 0), (1, 7)):
            off = 0 if (var + row) % 2 == 0 else 8
            yy = oy * 2
            pygame.draw.line(s, shade(base, -0.3), (0, yy + 7), (T, yy + 7), 1)
            bx = (off - 8) % 16 - 8
            while bx < T:
                pygame.draw.line(s, shade(base, -0.3), (bx, yy), (bx, yy + 7), 1)
                pygame.draw.line(s, shade(base, 0.12), (bx + 1, yy), (bx + 1, yy + 7), 1)
                bx += 16
        # 砖缝苔点
        for _ in range(rnd.randint(2, 4)):
            x, y = rnd.randrange(0, T), rnd.choice((6, 7, 13, 14))
            pygame.draw.rect(s, (96, 118, 88), (x, y, 2, 1))
    return s


def shroom_tile(depth, var):
    """发光菌野：暗紫腐土 + 发光蘑菇簇，奇幻暗黑。"""
    s = pygame.Surface((T, T), pygame.SRCALPHA)
    ramp = [(84, 74, 100), (74, 66, 90), (64, 58, 78),
            (54, 48, 66), (44, 40, 54), (36, 32, 44)]
    base = ramp[min(depth, 5)]
    rnd = random.Random(depth * 97 + var * 13 + 7)
    s.fill(base)
    for _ in range(26):
        x, y = rnd.randrange(0, T), rnd.randrange(0, T)
        s.fill(shade(base, rnd.uniform(-0.22, 0.14)), (x, y, rnd.randint(2, 4), rnd.randint(1, 3)))
    if depth == 0:
        top = (96, 86, 118)
        pygame.draw.rect(s, top, (0, 0, T, 7))
        pygame.draw.rect(s, shade(top, 0.18), (0, 0, T, 2))
        # 发光蘑菇（伞盖青/橙，1~2 株）
        cols = [(120, 230, 220), (255, 176, 96)]
        for _ in range(rnd.randint(1, 2)):
            x = rnd.randrange(3, T - 6)
            h = rnd.randint(4, 8)
            c = rnd.choice(cols)
            pygame.draw.line(s, shade(c, -0.3), (x, 6), (x, 6 - h), 1)
            pygame.draw.ellipse(s, c, (x - 3, 6 - h - 3, 7, 4))
            pygame.draw.circle(s, (240, 255, 250), (x, 6 - h - 1), 1)
        # 孢子微粒
        for _ in range(3):
            x, y = rnd.randrange(0, T), rnd.randrange(0, 10)
            pygame.draw.circle(s, (150, 220, 210, 120), (x, y), 1)
    return s


PLANS = [
    ("雪暮顶（积雪 + 冻土，冷冽）", snow_tile,
     "白色雪沿在全暗场景里极醒目，'暮色之前'的冷冽凛冬感"),
    ("余烬地表（焦土 + 发光裂缝）", ember_tile,
     "黑地橙缝自带发光，呼应熔炉区，世界'火后余温'的叙事"),
    ("遗迹砖顶（石砖 + 苔缝）", ruin_tile,
     "文明遗迹感，砖缝错列不变重复，和塔/闸门的石构呼应"),
    ("发光菌野（暗紫 + 蘑菇簇）", shroom_tile,
     "奇幻暗黑，蘑菇点冷青/暖橙双发色，夜戏最出彩"),
]

text = lambda s, x, y, col=(232, 232, 244), f=None: out.blit((f or f17).render(s, True, col), (x, y))
text("地形款式对比 · 第二批（结构差异款，非换色草）", 30, 16, (240, 240, 250), f22)
yy = 60
for name, fn, desc in PLANS:
    text(name, 30, yy + 20)
    for col in range(5):
        out.blit(fn(0, (col * 3) % 5), (420 + col * T, yy))
        out.blit(fn(1, (col * 5 + 1) % 5), (420 + col * T, yy + T))
    text(desc, 30, yy + 52, (168, 176, 198), f13)
    yy += 108
# 平铺
text("补充 · 雪暮顶 / 余烬 平铺 10 格", 30, yy + 4, (200, 205, 225), f13)
for col in range(10):
    out.blit(snow_tile(0, (col * 3) % 5), (420 + col * T, yy))
    out.blit(snow_tile(1, (col * 5 + 1) % 5), (420 + col * T, yy + T))
yy += 78
for col in range(10):
    out.blit(ember_tile(0, (col * 3) % 5), (420 + col * T, yy))
    out.blit(ember_tile(1, (col * 5 + 1) % 5), (420 + col * T, yy + T))

pygame.image.save(out, "shots/72_ground_themes2.png")
print("saved")
