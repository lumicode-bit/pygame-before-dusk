# -*- coding: utf-8 -*-
"""
assets.py —— 《暮色之前·双人联机合作》像素素材模块
============================================================================
全部角色 / 怪物 / 道具 / 背景贴图均在代码中逐像素绘制（pygame Surface），
不依赖任何外部图片素材文件。

【打包防黑屏设计】
  * 本模块不读取任何磁盘路径，因此不存在 exe 打包后素材路径丢失问题。
  * 若未来想替换素材，可在此统一修改，无需改动主逻辑。
"""
import math
import pygame

# --------------------------------------------------------------------------
# 调色板
# --------------------------------------------------------------------------
def px(surface, x, y, color, scale=1):
    """以 scale 为倍率画一个像素（像素画放大）"""
    try:
        if scale <= 1:
            surface.set_at((int(x), int(y)), color)
        else:
            sx = int(x) * scale
            sy = int(y) * scale
            for dy in range(scale):
                for dx in range(scale):
                    try:
                        surface.set_at((sx + dx, sy + dy), color)
                    except Exception:
                        pass
    except Exception:
        pass


def rect_px(surface, x, y, w, h, color, scale=1):
    try:
        for yy in range(h):
            for xx in range(w):
                px(surface, x + xx, y + yy, color, scale)
    except Exception:
        pass


def circle_px(surface, cx, cy, r, color):
    try:
        for yy in range(-r, r + 1):
            for xx in range(-r, r + 1):
                if xx * xx + yy * yy <= r * r:
                    px(surface, cx + xx, cy + yy, color)
    except Exception:
        pass


def paw(surface, x, y, color, scale=1):
    """小爪印"""
    circle_px(surface, x, y, 2 * scale, color)
    circle_px(surface, x - 2 * scale, y + 2 * scale, scale, color)
    circle_px(surface, x + 2 * scale, y + 2 * scale, scale, color)


# --------------------------------------------------------------------------
# 角色：白色小狗·弓箭手
# --------------------------------------------------------------------------
def make_white_dog(scale=2):
    """白色小狗（弓箭手）：白色皮毛 + 棕耳尖 + 黑眼 + 小红舌 + 尾尖棕"""
    w, h = 26, 44
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    WHITE = (248, 248, 248)
    DARK = (40, 40, 44)
    EAR = (190, 140, 90)
    NOSE = (45, 45, 50)
    TONGUE = (235, 90, 90)
    CHEEK = (255, 214, 214)
    for yy in range(h):
        for xx in range(w):
            # 身体（简单像素狗轮廓，白色）
            # 耳朵（左右竖耳）
            if (5 <= xx <= 8 and 6 <= yy <= 13) or (17 <= xx <= 20 and 6 <= yy <= 13):
                px(surf, xx, yy, EAR)
            if (6 <= xx <= 7 and 7 <= yy <= 9) or (18 <= xx <= 19 and 7 <= yy <= 9):
                px(surf, xx, yy, (245, 235, 225))
            # 头部
            if 7 <= xx <= 18 and 10 <= yy <= 19:
                px(surf, xx, yy, WHITE)
            # 眼睛
            if xx in (10, 15) and yy in (13, 14):
                px(surf, xx, yy, DARK)
            # 鼻子
            if 12 <= xx <= 13 and yy == 17:
                px(surf, xx, yy, NOSE)
            # 舌头
            if xx == 13 and yy in (18, 19):
                px(surf, xx, yy, TONGUE)
            # 腮红
            if xx == 8 and yy == 15:
                px(surf, xx, yy, CHEEK)
            if xx == 17 and yy == 15:
                px(surf, xx, yy, CHEEK)
            # 身体
            if 8 <= xx <= 17 and 20 <= yy <= 33:
                px(surf, xx, yy, WHITE)
            # 肚皮奶色
            if 11 <= xx <= 14 and 24 <= yy <= 32:
                px(surf, xx, yy, (240, 238, 235))
            # 背带
            if 8 <= xx <= 9 and 22 <= yy <= 32:
                px(surf, xx, yy, (120, 90, 60))
            if 16 <= xx <= 17 and 22 <= yy <= 32:
                px(surf, xx, yy, (120, 90, 60))
            # 尾巴
            if 19 <= xx <= 22 and 20 <= yy <= 23:
                px(surf, xx, yy, WHITE)
            if xx == 21 and yy == 19:
                px(surf, xx, yy, (190, 140, 90))
            # 腿
            if 9 <= xx <= 11 and 34 <= yy <= 40:
                px(surf, xx, yy, WHITE)
            if 14 <= xx <= 16 and 34 <= yy <= 40:
                px(surf, xx, yy, WHITE)
            # 脚
            if 8 <= xx <= 12 and 41 <= yy <= 43:
                px(surf, xx, yy, WHITE)
            if 13 <= xx <= 17 and 41 <= yy <= 43:
                px(surf, xx, yy, WHITE)

    if scale > 1:
        surf = pygame.transform.smoothscale(surf, (w * scale, h * scale))
    return surf


# --------------------------------------------------------------------------
# 角色：棕色小狗·盾卫
# --------------------------------------------------------------------------
def make_brown_dog(scale=2):
    """棕色小狗（盾卫）：棕色皮毛 + 深棕耳 + 白胸 + 护甲肩带"""
    w, h = 26, 44
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    BROWN = (150, 95, 55)
    DARKB = (105, 65, 38)
    WHITE = (245, 240, 230)
    DARK = (40, 40, 44)
    ARMOR = (130, 135, 145)
    NOSE = (40, 40, 44)
    for yy in range(h):
        for xx in range(w):
            # 耳朵（趴耳）
            if (4 <= xx <= 8 and 7 <= yy <= 12) or (17 <= xx <= 21 and 7 <= yy <= 12):
                px(surf, xx, yy, DARKB)
            # 头部
            if 7 <= xx <= 18 and 10 <= yy <= 19:
                px(surf, xx, yy, BROWN)
            # 额头浅棕
            if 10 <= xx <= 15 and 11 <= yy <= 12:
                px(surf, xx, yy, (180, 125, 78))
            # 眼睛
            if xx in (10, 15) and yy in (13, 14):
                px(surf, xx, yy, DARK)
            # 鼻子
            if 12 <= xx <= 13 and yy == 17:
                px(surf, xx, yy, NOSE)
            # 身体
            if 8 <= xx <= 17 and 20 <= yy <= 33:
                px(surf, xx, yy, BROWN)
            # 白胸
            if 11 <= xx <= 14 and 23 <= yy <= 32:
                px(surf, xx, yy, WHITE)
            # 护甲肩带
            if 8 <= xx <= 9 and 21 <= yy <= 31:
                px(surf, xx, yy, ARMOR)
            if 16 <= xx <= 17 and 21 <= yy <= 31:
                px(surf, xx, yy, ARMOR)
            if 9 <= xx <= 16 and 21 <= yy <= 22:
                px(surf, xx, yy, ARMOR)
            # 护甲圆片
            circle_px(surf, 13, 26, 2, (90, 95, 105))
            # 尾巴
            if 7 <= xx <= 9 and 20 <= yy <= 24:
                px(surf, xx, yy, DARKB)
            # 腿
            if 9 <= xx <= 11 and 34 <= yy <= 40:
                px(surf, xx, yy, BROWN)
            if 14 <= xx <= 16 and 34 <= yy <= 40:
                px(surf, xx, yy, BROWN)
            if 8 <= xx <= 12 and 41 <= yy <= 43:
                px(surf, xx, yy, BROWN)
            if 13 <= xx <= 17 and 41 <= yy <= 43:
                px(surf, xx, yy, BROWN)

    if scale > 1:
        surf = pygame.transform.smoothscale(surf, (w * scale, h * scale))
    return surf


# --------------------------------------------------------------------------
# 武器：弓
# --------------------------------------------------------------------------
def make_bow():
    """反曲弓（弓箭手持，画在狗子身上）"""
    surf = pygame.Surface((16, 30), pygame.SRCALPHA)
    WOOD = (122, 74, 40)
    WOD2 = (170, 115, 70)
    STR = (235, 230, 220)
    for yy in range(4, 26):
        t = (yy - 4) / 20.0
        offset = int(6 * math.sin(math.pi * t))
        px(surf, 7 + offset, yy, WOOD)
        px(surf, 8 + offset, yy, WOD2)
    # 弓弦
    for yy in range(4, 27):
        px(surf, 4, yy, STR)
    for yy in range(4, 27):
        px(surf, 11, yy, STR)
    return surf


# --------------------------------------------------------------------------
# 武器：剑
# --------------------------------------------------------------------------
def make_sword():
    """骑士剑"""
    surf = pygame.Surface((42, 12), pygame.SRCALPHA)
    STEEL = (210, 215, 225)
    STEEL2 = (240, 242, 248)
    GOLD = (215, 175, 80)
    GRIP = (110, 60, 35)
    # 剑身
    for xx in range(4, 32):
        px(surf, xx, 4, STEEL)
        px(surf, xx, 5, STEEL)
        px(surf, xx, 6, STEEL2)
        px(surf, xx, 7, STEEL)
    # 剑尖
    for xx in range(0, 4):
        px(surf, xx, 5 + (3 - xx), STEEL)
        px(surf, xx, 4 + (3 - xx), STEEL2)
    # 护手
    rect_px(surf, 2, 2, 2, 8, GOLD)
    # 剑柄
    rect_px(surf, 34, 4, 7, 4, GRIP)
    circle_px(surf, 41, 6, 2, GOLD)
    return surf


# --------------------------------------------------------------------------
# 武器：盾牌
# --------------------------------------------------------------------------
def make_shield():
    """圆盾"""
    surf = pygame.Surface((34, 34), pygame.SRCALPHA)
    OUT = (95, 100, 110)
    SILVER = (185, 190, 200)
    INNER = (225, 228, 235)
    GOLD = (215, 175, 80)
    circle_px(surf, 17, 17, 16, OUT)
    circle_px(surf, 17, 17, 14, SILVER)
    circle_px(surf, 17, 17, 10, INNER)
    rect_px(surf, 8, 15, 18, 3, SILVER)
    rect_px(surf, 15, 8, 3, 18, SILVER)
    circle_px(surf, 17, 17, 3, GOLD)
    return surf


# --------------------------------------------------------------------------
# 道具：弓箭（飞行中的箭）
# --------------------------------------------------------------------------
def make_arrow():
    """发射后的箭"""
    w, h = 16, 6
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    SHAFT = (160, 130, 90)
    HEAD = (225, 228, 235)
    FLETCH = (200, 100, 100)
    # 杆
    rect_px(surf, 2, 2, 12, 2, SHAFT)
    # 箭头
    px(surf, 0, 2, HEAD)
    px(surf, 1, 1, HEAD)
    px(surf, 1, 3, HEAD)
    # 尾羽
    px(surf, 13, 1, FLETCH)
    px(surf, 14, 0, FLETCH)
    px(surf, 13, 3, FLETCH)
    px(surf, 14, 4, FLETCH)
    return surf


# --------------------------------------------------------------------------
# 怪物：高空飞行小怪
# --------------------------------------------------------------------------
def make_fly_monster(scale=2):
    """飞行怪：紫灰色蝙蝠样小怪 + 黄眼"""
    w, h = 30, 24
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    BODY = (120, 90, 150)
    DARK = (80, 58, 105)
    EYE = (255, 220, 80)
    W_IN = (150, 120, 180)
    # 翅膀
    for yy in range(4, 12):
        px(surf, 2 + yy // 2, yy, W_IN)
        px(surf, 1 + yy // 2, yy, DARK)
    for yy in range(4, 12):
        px(surf, 27 - yy // 2, yy, W_IN)
        px(surf, 28 - yy // 2, yy, DARK)
    # 身体
    rect_px(surf, 9, 5, 12, 13, BODY)
    rect_px(surf, 10, 6, 10, 11, BODY)
    # 眼睛
    px(surf, 11, 8, EYE)
    px(surf, 17, 8, EYE)
    px(surf, 12, 9, (200, 80, 80))
    px(surf, 16, 9, (200, 80, 80))
    # 耳朵
    px(surf, 9, 4, DARK)
    px(surf, 19, 4, DARK)
    px(surf, 10, 3, DARK)
    px(surf, 18, 3, DARK)
    # 脚
    px(surf, 12, 19, DARK)
    px(surf, 16, 19, DARK)
    if scale > 1:
        surf = pygame.transform.smoothscale(surf, (w * scale, h * scale))
    return surf


# --------------------------------------------------------------------------
# 怪物：地面近战小怪
# --------------------------------------------------------------------------
def make_ground_monster(scale=2):
    """地面怪：暗绿史莱姆样 + 尖刺 + 红眼"""
    w, h = 28, 26
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    BODY = (70, 130, 80)
    DARK = (45, 95, 58)
    EYE = (255, 90, 80)
    MOUTH = (60, 60, 65)
    # 身体（圆润）
    for yy in range(4, 24):
        t = (yy - 4) / 19.0
        half = int(10 * (1 - (t - 0.5) ** 2 * 3.6)) + 4
        for xx in range(14 - half, 14 + half + 1):
            px(surf, xx, yy, BODY)
    # 高光
    for xx in range(8, 13):
        px(surf, xx, 8, (110, 180, 120))
    # 触角
    px(surf, 10, 2, DARK)
    px(surf, 17, 2, DARK)
    circle_px(surf, 10, 1, 1, (60, 200, 120))
    circle_px(surf, 17, 1, 1, (60, 200, 120))
    # 红眼
    px(surf, 11, 11, EYE)
    px(surf, 16, 11, EYE)
    px(surf, 12, 12, EYE)
    px(surf, 15, 12, EYE)
    # 嘴
    rect_px(surf, 12, 16, 4, 1, MOUTH)
    # 尖刺
    px(surf, 5, 9, DARK)
    px(surf, 6, 7, DARK)
    px(surf, 22, 9, DARK)
    px(surf, 21, 7, DARK)
    if scale > 1:
        surf = pygame.transform.smoothscale(surf, (w * scale, h * scale))
    return surf


# --------------------------------------------------------------------------
# 地图方块贴图
# --------------------------------------------------------------------------
def make_grass_tile():
    """草地地面瓦片"""
    surf = pygame.Surface((32, 32), pygame.SRCALPHA)
    BASE = (94, 168, 92)
    DARK = (74, 146, 74)
    LIGHT = (120, 192, 116)
    GRASS = (80, 168, 60)
    for yy in range(32):
        for xx in range(32):
            col = BASE
            if (xx + yy) % 5 == 0:
                col = DARK
            if (xx * 3 + yy) % 7 == 0:
                col = LIGHT
            px(surf, xx, yy, col)
    # 顶部草叶
    for xx in range(0, 32, 2):
        if (xx // 2) % 3 == 0:
            px(surf, xx, 1, GRASS)
            px(surf, xx + 1, 1, GRASS)
            px(surf, xx, 2, (62, 140, 52))
    return surf


def make_dirt_tile():
    """泥土瓦片（墙体/平台内侧）"""
    surf = pygame.Surface((32, 32), pygame.SRCALPHA)
    BASE = (140, 106, 70)
    DARK = (120, 88, 56)
    STONE = (165, 130, 88)
    for yy in range(32):
        for xx in range(32):
            col = BASE
            if (xx * 13 + yy * 7) % 11 == 0:
                col = DARK
            px(surf, xx, yy, col)
    for _ in range(6):
        sx = (_ * 5) % 28
        sy = (_ * 9) % 28
        px(surf, sx, sy, STONE)
        px(surf, sx + 1, sy, STONE)
    return surf


def make_rock_wall(scale=1):
    """岩石墙瓦片（可击碎）"""
    w, h = 32, 32
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    BASE = (118, 112, 110)
    DARK = (92, 86, 86)
    LIGHT = (150, 144, 142)
    CRACK = (66, 60, 60)
    for yy in range(h):
        for xx in range(w):
            col = BASE
            if ((xx + yy * 2) % 6) == 0:
                col = DARK
            px(surf, xx, yy, col)
    # 岩石棱角
    for xx in range(0, 32, 8):
        px(surf, xx, 20, LIGHT)
        px(surf, xx + 1, 18, LIGHT)
    circle_px(surf, 11, 9, 3, LIGHT)
    circle_px(surf, 22, 20, 3, DARK)
    # 裂纹
    px(surf, 6, 28, CRACK)
    px(surf, 7, 27, CRACK)
    px(surf, 8, 26, CRACK)
    px(surf, 8, 25, CRACK)
    if scale > 1:
        surf = pygame.transform.smoothscale(surf, (w * scale, h * scale))
    return surf


def make_pressure_plate():
    """压力机关瓦片"""
    surf = pygame.Surface((32, 32), pygame.SRCALPHA)
    BASE = (96, 96, 104)
    EDGE = (70, 70, 78)
    LIT = (255, 210, 90)
    for yy in range(32):
        for xx in range(32):
            px(surf, xx, yy, BASE)
    # 边缘
    for xx in range(32):
        px(surf, xx, 0, EDGE)
        px(surf, xx, 31, EDGE)
    for yy in range(32):
        px(surf, 0, yy, EDGE)
        px(surf, 31, yy, EDGE)
    # 十字饰纹
    for xx in range(12, 20):
        px(surf, xx, 15, LIT)
        px(surf, xx, 16, (230, 180, 60))
    for yy in range(12, 20):
        px(surf, 15, yy, LIT)
        px(surf, 16, yy, (230, 180, 60))
    circle_px(surf, 16, 16, 3, (255, 235, 150))
    return surf


def make_jump_pad():
    """浮空跳板（单边平台）"""
    surf = pygame.Surface((32, 12), pygame.SRCALPHA)
    WOOD = (168, 120, 70)
    WOD2 = (190, 145, 92)
    DARK = (120, 82, 46)
    # 木板
    for xx in range(32):
        px(surf, xx, 2, WOD2)
        px(surf, xx, 3, WOD2)
        px(surf, xx, 4, WOOD)
        px(surf, xx, 5, WOOD)
        px(surf, xx, 6, WOD2)
    # 木板节
    for xx in range(4, 32, 8):
        px(surf, xx, 3, DARK)
        px(surf, xx + 1, 3, DARK)
    # 边缘加固
    for yy in range(2, 8):
        px(surf, 0, yy, DARK)
        px(surf, 31, yy, DARK)
    # 底部闪光
    for xx in range(2, 30, 3):
        px(surf, xx, 8, (120, 200, 255))
    return surf


def make_portal():
    """终点传送门（多帧动画）"""
    frames = []
    for f in range(8):
        surf = pygame.Surface((5 * 32, 4 * 32), pygame.SRCALPHA)
        cx, cy = 80, 64
        r = 46 + f * 2
        for yy in range(-r, r + 1):
            for xx in range(-r, r + 1):
                if xx * xx + yy * yy <= r * r:
                    px(surf, cx + xx, cy + yy, (120, 200, 255))
        for yy in range(-(r - 10), (r - 10) + 1):
            for xx in range(-(r - 10), (r - 10) + 1):
                if xx * xx + yy * yy <= (r - 10) * (r - 10):
                    px(surf, cx + xx, cy + yy, (80, 160, 255))
        for yy in range(-(r - 22), (r - 22) + 1):
            for xx in range(-(r - 22), (r - 22) + 1):
                if xx * xx + yy * yy <= (r - 22) * (r - 22):
                    px(surf, cx + xx, cy + yy, (200, 240, 255))
        frames.append(surf)
    return frames


# --------------------------------------------------------------------------
# 背景（静态分层：远景树木 -> 中景灌木 -> 近景草地）
# --------------------------------------------------------------------------
def make_background(world_w, height):
    """生成整张静态分层森林背景（固定不滚动）"""
    bg = pygame.Surface((world_w, height), pygame.SRCALPHA)
    SKY_TOP = (150, 210, 240)
    SKY_BOT = (230, 242, 228)
    # 天空渐变
    for yy in range(height):
        t = yy / float(height)
        r = int(SKY_TOP[0] + (SKY_BOT[0] - SKY_TOP[0]) * t)
        g = int(SKY_TOP[1] + (SKY_BOT[1] - SKY_TOP[1]) * t)
        b = int(SKY_TOP[2] + (SKY_BOT[2] - SKY_TOP[2]) * t)
        pygame.draw.line(bg, (r, g, b), (0, yy), (world_w, yy))

    # --- 远景树木层 ---
    tree_colors = [(88, 142, 100), (72, 122, 90), (100, 158, 110), (60, 108, 80)]
    x = 0
    i = 0
    while x < world_w:
        if i % 3 != 0:  # 错落
            tw = 80 + (i % 4) * 20
            th = 180 + (i % 3) * 50
            col = tree_colors[i % len(tree_colors)]
            cx_t = x + tw // 2
            top_y = 60 + (i % 2) * 40
            _draw_tree(bg, cx_t, top_y, tw, th, col)
        x += 160 + (i % 3) * 60
        i += 1

    # --- 中景灌木层 ---
    bush_colors = [(70, 130, 80), (58, 115, 72), (80, 145, 88)]
    x = 20
    i = 0
    while x < world_w:
        bw = 120 + (i % 3) * 36
        bh = 60 + (i % 3) * 20
        by = 560 + (i % 2) * 30
        col = bush_colors[i % 3]
        _draw_bush(bg, x, by, bw, bh, col)
        x += 190 + (i % 2) * 80
        i += 1

    # --- 近景草地地面层（映射到地面高度）---
    GROUND_Y = 19 * 32
    for yy in range(GROUND_Y, height):
        t = (yy - GROUND_Y) / (height - GROUND_Y)
        r = int(96 - 40 * t)
        g = int(168 - 60 * t)
        b = int(92 - 42 * t)
        pygame.draw.line(bg, (max(0, r), max(0, g), max(0, b)), (0, yy), (world_w, yy))
    # 草纹理
    for i in range(world_w // 8):
        gx = i * 8
        gy = GROUND_Y + (i * 7) % 24
        pygame.draw.line(bg, (70, 150, 60), (gx, gy), (gx + 2, gy - 3), 1)
    return bg


def _draw_tree(surf, cx, top_y, tw, th, color):
    """像素树"""
    trunk = pygame.Surface((18, 60), pygame.SRCALPHA)
    for yy in range(60):
        for xx in range(18):
            if 3 <= xx <= 14:
                px(trunk, xx, yy, (80, 58, 38))
    surf.blit(trunk, (cx - 9, top_y + th - 60))
    # 树冠（多层圆）
    for layer in range(4):
        r = int(tw * 0.3 * (1 - layer * 0.12))
        y_off = layer * int(th * 0.22)
        d = color[0] - layer * 12
        d = max(30, d)
        _blit_circle(surf, cx, top_y + th * 0.3 + y_off, r, (d, color[1] - layer * 8, color[2] - layer * 6))


def _draw_bush(surf, x, y, bw, bh, color):
    for i in range(3):
        _blit_circle(surf, x + i * (bw // 2), y + (i % 2) * (bh // 3), bw // 2, color)


def _blit_circle(surf, cx, cy, r, color):
    try:
        for yy in range(-r, r + 1):
            for xx in range(-r, r + 1):
                if xx * xx + yy * yy <= r * r and 0 <= cx + xx < surf.get_width() and 0 <= cy + yy < surf.get_height():
                    px(surf, cx + xx, cy + yy, color)
    except Exception:
        pass


# --------------------------------------------------------------------------
# 边框装饰：草丛 / 石块 / 小树
# --------------------------------------------------------------------------
def make_grass_clump():
    surf = pygame.Surface((32, 24), pygame.SRCALPHA)
    GREEN = (90, 170, 70)
    DARK = (58, 130, 50)
    for i in range(6):
        bx = 4 + i * 5
        bh = 8 + (i % 3) * 5
        for yy in range(bh):
            px(surf, bx, 23 - yy, GREEN if yy < bh - 3 else DARK)
            if i % 2 == 0:
                px(surf, bx + 1, 23 - yy, GREEN)
    px(surf, 3, 23, DARK)
    px(surf, 28, 23, DARK)
    return surf


def make_small_rock():
    surf = pygame.Surface((28, 20), pygame.SRCALPHA)
    for yy in range(16):
        for xx in range(4 + yy // 2, 24 - yy // 2):
            px(surf, xx, yy, (130, 122, 118))
            if (xx + yy) % 4 == 0:
                px(surf, xx, yy, (112, 104, 100))
    for yy in range(3):
        px(surf, 10 + yy, 15 + yy, (120, 112, 108))
    return surf


def make_small_tree():
    surf = pygame.Surface((40, 64), pygame.SRCALPHA)
    for yy in range(20):
        for xx in range(14, 26):
            px(surf, xx, 44 + yy, (88, 60, 38))
    for layer in range(3):
        r = 14 - layer * 4
        _blit_circle(surf, 20, 30 - layer * 10, r, (60 + layer * 15, 130 - layer * 8, 70 - layer * 5))
    return surf


# --------------------------------------------------------------------------
# 生成工厂（缓存）
# --------------------------------------------------------------------------
_cache = {}


def get(name):
    """获取缓存的素材，重复调用不重新生成（防卡帧）"""
    if name in _cache:
        return _cache[name]
    try:
        fn = {
            "bg": lambda: make_background(80 * 32, 22 * 32),
            "grass": make_grass_tile,
            "dirt": make_dirt_tile,
            "rock": make_rock_wall,
            "plate": make_pressure_plate,
            "pad": make_jump_pad,
            "dog_white": lambda: make_white_dog(2),
            "dog_brown": lambda: make_brown_dog(2),
            "fly": lambda: make_fly_monster(2),
            "ground": lambda: make_ground_monster(2),
            "arrow": make_arrow,
            "bow": make_bow,
            "sword": make_sword,
            "shield": make_shield,
            "grass_clump": make_grass_clump,
            "small_rock": make_small_rock,
            "small_tree": make_small_tree,
            "portal": make_portal,
        }
        obj = fn[name]()
        _cache[name] = obj
        return obj
    except Exception as e:
        print("[素材] 生成失败 %s: %r" % (name, e))
        # 失败返回一个占位色块，绝不崩溃
        fallback = pygame.Surface((32, 32), pygame.SRCALPHA)
        fallback.fill((200, 80, 80))
        _cache[name] = fallback
        return fallback


def rot_center(image, angle):
    try:
        return pygame.transform.rotate(image, angle)
    except Exception:
        return image


def prebuild_all():
    """预热全部素材，避免游戏中途卡顿"""
    keys = ["bg", "grass", "dirt", "rock", "plate", "pad", "dog_white", "dog_brown",
            "fly", "ground", "arrow", "bow", "sword", "shield", "grass_clump",
            "small_rock", "small_tree", "portal"]
    for k in keys:
        try:
            get(k)
        except Exception:
            pass