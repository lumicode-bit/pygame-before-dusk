# -*- coding: utf-8 -*-
"""生成 4 个方块渲染美化方案的对比图，供用户敲定。"""
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame
pygame.init()
pygame.display.set_mode((1280, 720))
import game_core as core
from renderer import WorldRenderer
import random

scr = pygame.display.get_surface()
r = WorldRenderer(scr)
tiles = r.tiles
T = core.TILE

W, H = 1000, 780
out = pygame.Surface((W, H), pygame.SRCALPHA)
# 暮色背景渐变（模拟游戏内深蓝紫环境）
for y in range(H):
    f = y / H
    c = (int(28 + 18 * f), int(24 + 10 * f), int(46 + 8 * f))
    pygame.draw.line(out, c, (0, y), (W, y))

font = pygame.font.Font(None, 22)
font_s = pygame.font.Font(None, 17)
font_big = pygame.font.Font(None, 30)

_CJK = None
for _fp in (r"C:/Windows/Fonts/msyh.ttc", r"C:/Windows/Fonts/msyh.ttf",
            r"C:/Windows/Fonts/simhei.ttf", r"C:/Windows/Fonts/simsun.ttc"):
    if os.path.exists(_fp):
        _CJK = _fp
        break
f17 = pygame.font.Font(_CJK, 17) if _CJK else font
f13 = pygame.font.Font(_CJK, 13) if _CJK else font_s
f24b = pygame.font.Font(_CJK, 22) if _CJK else font_big


def text(surf, s, x, y, col=(230, 230, 240), f=None):
    f = f or f17
    surf.blit(f.render(s, True, col), (x, y))


def draw_base(surf, x, y, cols=4, rows=2):
    """画平台 tile 底（方案 A/B/C/D 的公共底）。"""
    for row in range(rows):
        for col in range(cols):
            seed = random.randint(0, 99)
            d = 0 if row == 0 else 1
            img = tiles.get_grass(d, seed) if d <= 1 else tiles.get_dirt(d, seed)
            surf.blit(img, (x + col * T, y + row * T))


def plan_A(surf, x, y, cols=4, rows=2):
    """A 描边高光：16-bit 经典，轮廓清晰。"""
    draw_base(surf, x, y, cols, rows)
    w, h = cols * T, rows * T
    # 顶边 1px 亮草
    pygame.draw.line(surf, (168, 214, 140), (x, y + 1), (x + w - 1, y + 1), 1)
    # 草顶参差（每 4px 一簇，高低 2~4）
    rnd = random.Random(7)
    for px in range(0, w, 4):
        hh = rnd.choice((2, 3, 4, 3))
        pygame.draw.line(surf, (118, 176, 104), (x + px, y), (x + px, y), 1)
        pygame.draw.rect(surf, (128, 190, 110), (x + px, y, 3, 1))
        pygame.draw.rect(surf, (100, 158, 92), (x + px + 1, y + 1, 2, hh - 1))
    # 左右侧 2px 暗渐变 + 1px 深描边
    for side, xe in ((-1, x), (1, x + w - 1)):
        pygame.draw.rect(surf, (52, 74, 52), (min(xe, xe - side * 2), y, 2, h))
        pygame.draw.line(surf, (26, 38, 28), (xe, y + 1), (xe, y + h - 1), 1)
    # 底边
    pygame.draw.rect(surf, (34, 40, 44), (x, y + h - 2, w, 2))


def plan_B(surf, x, y, cols=4, rows=2):
    """B 体积块：斜面高光 + 圆角，现代独立游戏感。"""
    draw_base(surf, x, y, cols, rows)
    w, h = cols * T, rows * T
    # 侧面整体压暗（光照从上来）
    sh = pygame.Surface((w, h), pygame.SRCALPHA)
    sh.fill((8, 12, 24, 60), (0, 6, w, h - 6))
    surf.blit(sh, (x, y))
    # 顶面亮带 5px
    pygame.draw.rect(surf, (140, 198, 122), (x, y, w, 5))
    pygame.draw.rect(surf, (176, 224, 150), (x, y, w, 2))
    # 左上高光
    pygame.draw.line(surf, (210, 240, 190), (x + 1, y + 1), (x + w - 2, y + 1), 1)
    pygame.draw.line(surf, (120, 170, 110), (x + 1, y + 1), (x + 1, y + h - 2), 1)
    # 四角 1px 圆角（挖空成背景色）
    for cx2, cy2, dx, dy in ((x, y, -1, -1), (x + w - 1, y, 1, -1),
                             (x, y + h - 1, -1, 1), (x + w - 1, y + h - 1, 1, 1)):
        out.set_at((cx2 + 0, cy2), (28, 24, 46))
    # 底部反光边（悬浮能量感）
    pygame.draw.line(surf, (90, 120, 170), (x + 2, y + h - 1), (x + w - 3, y + h - 1), 1)


def plan_C(surf, x, y, cols=4, rows=2):
    """C 分层条纹岩块：地质感，Terraria 风。"""
    draw_base(surf, x, y, cols, rows)
    w, h = cols * T, rows * T
    rnd = random.Random(11)
    # 水平岩层纹
    for yy in range(y + 10, y + h - 4, 9):
        off = rnd.randint(0, 20)
        ln = rnd.randint(30, 70)
        pygame.draw.line(surf, (70, 92, 72), (x + off, yy), (x + min(w - 2, off + ln), yy), 1)
        pygame.draw.line(surf, (104, 126, 100), (x + off, yy + 1), (x + min(w - 2, off + ln // 2), yy + 1), 1)
    # 碎石点
    for _ in range(9):
        px = x + rnd.randint(2, w - 4)
        py = y + rnd.randint(10, h - 6)
        pygame.draw.rect(surf, (92, 116, 92), (px, py, 2, 1))
    # 底边深带 + 根须
    pygame.draw.rect(surf, (30, 42, 40), (x, y + h - 3, w, 3))
    for k in range(4):
        bx = x + 14 + k * (w // 4)
        pygame.draw.line(surf, (30, 42, 40), (bx, y + h), (bx + rnd.randint(-2, 2), y + h + 4), 1)
    # 顶草参差
    for px in range(0, w, 4):
        pygame.draw.rect(surf, (128, 190, 110), (x + px, y, 3, 1))


def plan_D(surf, x, y, cols=4, rows=2):
    """D 悬浮光晕：能量描边，魔幻感。"""
    draw_base(surf, x, y, cols, rows)
    w, h = cols * T, rows * T
    # 外圈柔光（多层 alpha 圆角矩形近似 glow）
    for grow, a in ((10, 26), (6, 44), (3, 70)):
        gl = pygame.Surface((w + grow * 2, h + grow * 2), pygame.SRCALPHA)
        pygame.draw.rect(gl, (140, 210, 255, a),
                         (0, 0, w + grow * 2, h + grow * 2), 1, border_radius=6)
        surf.blit(gl, (x - grow, y - grow))
    # 边缘亮描边
    pygame.draw.rect(surf, (170, 225, 255), (x, y, w, h), 1, border_radius=2)
    pygame.draw.line(surf, (210, 245, 255), (x + 1, y + 1), (x + w - 2, y + 1), 1)
    # 底边能量渐隐
    fade = pygame.Surface((w, 6), pygame.SRCALPHA)
    for i in range(6):
        pygame.draw.line(fade, (140, 210, 255, 90 - i * 14), (0, i), (w, i), 1)
    surf.blit(fade, (x, y + h))


plans = [("方案 A · 描边高光", plan_A, "轮廓清晰立体，16-bit 经典，改动小、最稳"),
         ("方案 B · 体积块", plan_B, "斜面高光+圆角+底部反光，现代独立游戏感"),
         ("方案 C · 分层岩纹", plan_C, "岩层横纹+碎石+根须，Terraria 式地质感"),
         ("方案 D · 悬浮光晕", plan_D, "青色能量描边+底部渐隐，魔幻悬浮感")]

title = f24b
text(out, "方块渲染美化方案对比（选定后正式实现进游戏）", 30, 20, (240, 240, 250), title)

yy = 80
for name, fn, desc in plans:
    text(out, name, 30, yy + 26)
    fn(out, 300, yy, 4, 2)
    text(out, desc, 30, yy + 56, (170, 178, 200), f13)
    yy += 118

# 下方补充：整段平台效果（方案 A 连续 8 格示意，看重复感）
text(out, "补充 · 方案 A 连续 8 格（看平铺重复感）", 30, yy + 6, (200, 205, 225), f13)
plan_A(out, 300, yy + 4, 8, 2)
yy += 78
text(out, "补充 · 方案 C 连续 8 格", 30, yy + 6, (200, 205, 225), f13)
plan_C(out, 300, yy + 4, 8, 2)

pygame.image.save(out, "shots/70_tile_plans.png")
print("saved")
