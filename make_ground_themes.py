# -*- coding: utf-8 -*-
"""去绿草后的地形配色方向对比图：4 个暮色系主题 × 平铺效果。"""
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame
import random
import math
pygame.init()
pygame.display.set_mode((1280, 720))
T = 32
W, H = 1000, 700
out = pygame.Surface((W, H))
for y in range(H):
    f = y / H
    pygame.draw.line(out, (int(30 + 16 * f), int(26 + 10 * f), int(48 + 8 * f)), (0, y), (W, y))

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
    if f >= 0:
        return _mix(c, (255, 255, 255), f)
    return _mix(c, (0, 0, 0), -f)


THEMES = {
    "暮青苔（青灰绿，湿冷苔原）": {
        "ramp": [(88, 120, 114), (78, 106, 102), (68, 92, 90),
                 (58, 78, 76), (48, 64, 62), (40, 52, 50)],
        "top": (100, 152, 138),
    },
    "枯秋草（黄褐，秋暮荒原）": {
        "ramp": [(128, 108, 74), (112, 94, 66), (96, 80, 58),
                 (80, 66, 50), (64, 52, 42), (52, 44, 36)],
        "top": (164, 138, 82),
    },
    "灰石原（无植被，冷石地表）": {
        "ramp": [(108, 108, 114), (96, 96, 102), (84, 84, 90),
                 (72, 72, 78), (60, 60, 66), (50, 50, 56)],
        "top": (132, 134, 142),
    },
    "暮紫苔（紫灰，呼应夜空）": {
        "ramp": [(110, 98, 130), (96, 86, 114), (82, 74, 98),
                 (68, 62, 82), (56, 50, 66), (46, 42, 54)],
        "top": (138, 120, 162),
    },
}


def grass_tile(theme, depth, var):
    """复刻游戏 _grass_tile 的生成逻辑，调色参数化。"""
    ramp = theme["ramp"]
    rock = [(r * 9 // 10, r * 9 // 10, r * 9 // 10) for r in (98, 86, 76, 66, 56)]
    s = pygame.Surface((T, T), pygame.SRCALPHA)
    base = rock[min(depth - 2, 4)] if depth >= 2 else ramp[min(depth, 5)]
    rnd = random.Random(depth * 97 + var * 13 + 7)
    s.fill(base)
    for _ in range(30):
        x = rnd.randrange(0, T)
        y = rnd.randrange(0, T)
        c = shade(base, rnd.uniform(-0.22, 0.14))
        s.fill(c, (x, y, rnd.randint(2, 4), rnd.randint(1, 3)))
    if depth >= 2:
        for _ in range(2):
            yy = rnd.randrange(4, T - 4)
            c = shade(base, rnd.uniform(-0.16, 0.1))
            pygame.draw.line(s, c, (0, yy), (T, yy + rnd.randint(-2, 2)), 1)
    if depth >= 1 and var % 2 == 0:
        rx, ry = rnd.randrange(4, 24), rnd.randrange(6, 26)
        pygame.draw.ellipse(s, shade(base, -0.28), (rx, ry, 7, 5))
        pygame.draw.ellipse(s, shade(base, 0.12), (rx + 1, ry + 1, 4, 2))
    if depth == 0:
        top = theme["top"]
        pygame.draw.rect(s, top, (0, 0, T, 9))
        pygame.draw.rect(s, shade(top, 0.2), (0, 0, T, 2))
        pygame.draw.rect(s, shade(top, -0.18), (0, 9, T, 2))
        for _ in range(10):
            x = rnd.randrange(0, T)
            h = rnd.randint(3, 9)
            pygame.draw.line(s, shade(top, rnd.uniform(-0.12, 0.28)),
                             (x, 5), (x + rnd.randint(-2, 2), 5 - h), 1)
    return s


def platform(theme, x, y, cols):
    for col in range(cols):
        out.blit(grass_tile(theme, 0, (col * 3) % 5), (x + col * T, y))
        out.blit(grass_tile(theme, 1, (col * 5 + 1) % 5), (x + col * T, y + T))


text("地形配色方向对比（去绿草 · 暮色基调 · 选定后正式实现）", 30, 18, (240, 240, 250), f22)
yy = 66
for name, th in THEMES.items():
    text(name, 30, yy + 22)
    platform(th, 420, yy, 5)
    yy += 92
    # 平铺 8 格
    platform(th, 420, yy, 10)
    text("↑ 平铺 10 格（看重复感与地面观感）", 30, yy + 22, (168, 176, 198), f13)
    yy += 86

pygame.image.save(out, "shots/71_ground_themes.png")
print("saved")
