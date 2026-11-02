# -*- coding: utf-8 -*-
"""
renderer.py —— 世界渲染器
============================================================================
把 game_core 的状态画成"像一款商业游戏"的画面。所有美术资源程序化生成，
无外部图片依赖。

渲染顺序（从后到前）：
  天空/视差 → 地形 → 岩浆/深坑 → 陷阱 → 机关 → 交互物 → 传送门 →
  箭矢 → 怪物 → 玩家 → 粒子/飘字 → 前景雾/光斑

* 地形采用"按暴露深度分层着色 + 边缘草叶"的方案，避免平铺贴图的重复感；
* 所有随时间变化的动画都基于传入的 t，保证单机/联机表现一致；
* 单帧绘制预算约 1200~1800 次 blit，在 1280x720 下可稳定 60fps。
"""
import math
import random

import pygame

import assets
import game_core as core
import sprites
import theme
import fx

TILE = core.TILE

# 悬浮岛外观：只对"绿意段"（col < GREEN_UNTIL）的悬浮平台启用，配色固定雪暮。
# 用户要求取消全图悬浮岛后，又要求开局段用雪暮顶——改为按段启用。
# 烘焙/绘制代码保留在 _bake_island/_draw_float_shells 里。
FLOAT_ISLANDS = False         # 岩根轮廓全部去掉（用户要求），平台回到方块状
FLOAT_ISLAND_SNOW = True      # 但绿意段的平台仍是雪暮顶（雪白 tile，独立开关）
# 开局绿意段的列边界：这里之前是绿草/绿藤/雪暮浮岛（"记忆中的世界"），
# 之后进入余烬世界（黑灰焦土+发光裂缝）。想调分段长度改这一个数。
GREEN_UNTIL = 45
FADE_LEN = 16                # 45..61 之间绿->余烬逐格渐变
FADE_STEPS = 12              # 渐变预烘焙档数


# --------------------------------------------------------------------------
# 地形贴片预生成
# --------------------------------------------------------------------------
class TerrainTiles:
    """按"暴露深度 + 随机变体"预生成地形贴片（一次性，几十张 32x32）。"""

    DEPTHS = 6
    VARIANTS = 4

    def __init__(self):
        self.grass = {}
        self.dirt = {}
        self.metal = {}
        self.scorch = {}
        self.rock = {}
        self.edge = {}
        self.edge_scorch = {}
        self._build()

    # ---- 单块 ----
    def _grass_tile(self, depth, var, green=False):
        """地表 tile。green=True：原版绿草（开局"记忆中的世界"段）；
        green=False：余烬焦土（v2.19）——黑灰 + 发光裂缝。

        裂缝密度由 var 控制：var>=2 为"密缝"变体，渲染端按区域偏移
        seed 实现森林(稀) -> 焦土(密) 递进。
        """
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        if green:
            ramp = [
                (94, 130, 88), (82, 112, 80), (72, 96, 72),
                (62, 82, 64), (52, 68, 56), (44, 56, 50),
            ]
        else:
            ramp = [
                (62, 58, 62), (54, 50, 54), (46, 43, 47),
                (39, 37, 40), (33, 31, 34), (27, 26, 29),
            ]
        rock = [(98, 94, 90), (86, 82, 78), (76, 72, 70), (66, 63, 62), (56, 54, 54)]
        base = rock[min(depth - 2, 4)] if depth >= 2 else ramp[min(depth, 5)]
        rnd = random.Random(depth * 97 + var * 13 + 7)
        s.fill(base)
        # 灰烬颗粒
        for _ in range(30):
            x = rnd.randrange(0, TILE)
            y = rnd.randrange(0, TILE)
            c = theme.shade(base, rnd.uniform(-0.22, 0.14))
            s.fill(c, (x, y, rnd.randint(2, 4), rnd.randint(1, 3)))
        # 层理线
        if depth >= 2:
            for _ in range(2):
                yy = rnd.randrange(4, TILE - 4)
                c = theme.shade(base, rnd.uniform(-0.16, 0.1))
                pygame.draw.line(s, c, (0, yy), (TILE, yy + rnd.randint(-2, 2)), 1)
        # 小石块
        if depth >= 1 and var % 2 == 0:
            rx, ry = rnd.randrange(4, 24), rnd.randrange(6, 26)
            pygame.draw.ellipse(s, theme.shade(base, -0.28), (rx, ry, 7, 5))
            pygame.draw.ellipse(s, theme.shade(base, 0.12), (rx + 1, ry + 1, 4, 2))
        dense = var >= 2
        if depth == 0:
            if green:
                # 原版绿草皮
                top = (104, 158, 96)
                pygame.draw.rect(s, top, (0, 0, TILE, 9))
                pygame.draw.rect(s, theme.shade(top, 0.2), (0, 0, TILE, 2))
                pygame.draw.rect(s, theme.shade(top, -0.18), (0, 9, TILE, 2))
                for _ in range(10):
                    x = rnd.randrange(0, TILE)
                    h = rnd.randint(3, 9)
                    pygame.draw.line(s, theme.shade(top, rnd.uniform(-0.12, 0.28)),
                                     (x, 5), (x + rnd.randint(-2, 2), 5 - h), 1)
                if var == 2 and rnd.random() < 0.7:
                    pygame.draw.circle(s, (238, 208, 120), (rnd.randrange(6, 26), 4), 2)
                    pygame.draw.circle(s, (255, 236, 160), (rnd.randrange(6, 26), 4), 1)
                return s
            # 地表层：暗焦壳
            top = (72, 66, 68)
            pygame.draw.rect(s, top, (0, 0, TILE, 9))
            pygame.draw.rect(s, theme.shade(top, 0.16), (0, 0, TILE, 2))
            pygame.draw.rect(s, theme.shade(top, -0.2), (0, 9, TILE, 2))
            # 发光裂缝（余温）
            for _ in range(3 if dense else 2):
                x = rnd.randrange(2, TILE - 8)
                y = rnd.randrange(2, 8)
                pts = [(x, y)]
                for i in range(3):
                    x += rnd.randint(4, 9)
                    y += rnd.randint(-3, 4)
                    pts.append((x, y))
                pygame.draw.lines(s, (255, 128, 52), False, pts, 1)
                for px, py in pts[1::2]:
                    pygame.draw.circle(s, (255, 190, 90), (px, py), 1)
            # ember 余烬点
            for _ in range(6 if dense else 3):
                x, y = rnd.randrange(1, TILE - 1), rnd.randrange(3, 12)
                pygame.draw.circle(s, (255, 150, 60), (x, y), 1)
            # 偶发火种花
            if var == 2 and rnd.random() < 0.6:
                x = rnd.randrange(6, 26)
                pygame.draw.line(s, (90, 60, 46), (x, 6), (x, 1), 1)
                pygame.draw.circle(s, (255, 168, 70), (x, 2), 2)
                pygame.draw.circle(s, (255, 226, 150), (x, 2), 1)
        elif depth == 1:
            pygame.draw.rect(s, theme.shade(base, 0.1), (0, 0, TILE, 3))
            pygame.draw.rect(s, theme.shade(base, -0.14), (0, 3, TILE, 2))
            if dense and rnd.random() < 0.5:
                x, y = rnd.randrange(4, TILE - 10), rnd.randrange(6, TILE - 8)
                pygame.draw.line(s, (200, 92, 40), (x, y), (x + rnd.randint(5, 10), y + rnd.randint(-2, 2)), 1)
        return s

    def _snow_tile(self, depth, var):
        """雪暮 tile：积雪白顶 + 冻土蓝灰（绿意段悬浮平台专用）。"""
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        ramp = [(96, 104, 124), (84, 90, 108), (72, 76, 92),
                (60, 62, 76), (50, 50, 62), (42, 42, 52)]
        base = ramp[min(depth, 5)]
        rnd = random.Random(depth * 97 + var * 13 + 7)
        s.fill(base)
        for _ in range(26):
            x, y = rnd.randrange(0, TILE), rnd.randrange(0, TILE)
            c = theme.shade(base, rnd.uniform(-0.2, 0.12))
            s.fill(c, (x, y, rnd.randint(2, 4), rnd.randint(1, 3)))
        if depth == 0:
            pygame.draw.rect(s, (222, 232, 246), (0, 0, TILE, 9))
            pygame.draw.rect(s, (240, 248, 255), (0, 0, TILE, 3))
            pygame.draw.rect(s, (170, 188, 212), (0, 9, TILE, 3))
            for x in range(0, TILE, 5):
                h = rnd.randint(2, 5)
                pygame.draw.rect(s, (222, 232, 246), (x, 9, 4, h))
            for _ in range(4):
                x, y = rnd.randrange(0, TILE), rnd.randrange(2, 7)
                pygame.draw.circle(s, (196, 212, 234), (x, y), 1)
        elif depth == 1:
            pygame.draw.rect(s, (150, 162, 184), (0, 0, TILE, 3))
        return s

    def _rock_tile(self, var):
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        rnd = random.Random(var * 31 + 5)
        base = (92, 92, 106)
        s.fill(base)
        for _ in range(18):
            x = rnd.randrange(0, TILE)
            y = rnd.randrange(0, TILE)
            c = theme.shade(base, rnd.uniform(-0.28, 0.22))
            s.fill(c, (x, y, rnd.randint(3, 8), rnd.randint(2, 5)))
        pygame.draw.rect(s, theme.shade(base, -0.35), (0, 0, TILE, TILE), 1)
        pygame.draw.rect(s, theme.shade(base, 0.2), (1, 1, TILE - 2, 2))
        # 裂纹
        if var % 2 == 0:
            pygame.draw.lines(s, theme.shade(base, -0.42), False,
                              [(6, 4), (11, 12), (9, 20), (15, 28)], 1)
        return s

    def _edge(self, var, scorch=False, green=False):
        """地形上沿：绿意段是草叶，余烬段焦枯短茬，岩壁/岩浆区是灰烬。"""
        s = pygame.Surface((TILE, 12), pygame.SRCALPHA)
        rnd = random.Random(var * 17 + 3)
        if green and not scorch:
            # 原版绿草叶
            for i in range(0, TILE, 2):
                h = rnd.randint(2, 7)
                c = (108, 162, 98) if rnd.random() > 0.3 else (88, 136, 82)
                pygame.draw.line(s, c, (i, 10), (i + rnd.randint(-1, 1), 10 - h), 2)
            return s
        if scorch:
            for i in range(0, TILE, 3):
                if rnd.random() < 0.45:
                    continue
                h = rnd.randint(2, 5)
                c = (96, 82, 64) if rnd.random() > 0.4 else (74, 62, 50)
                pygame.draw.line(s, c, (i, 10), (i + rnd.randint(-1, 1), 10 - h), 2)
            for i in range(3):
                pygame.draw.circle(s, (120, 96, 72), (rnd.randrange(2, TILE - 2), 9), 1)
            return s
        # 余烬世界的"草沿"：焦枯短茬 + 偶发 ember 光点
        for i in range(0, TILE, 2):
            h = rnd.randint(2, 5)
            c = (72, 62, 58) if rnd.random() > 0.3 else (56, 48, 46)
            pygame.draw.line(s, c, (i, 10), (i + rnd.randint(-1, 1), 10 - h), 2)
        for _ in range(2):
            pygame.draw.circle(s, (255, 150, 60),
                               (rnd.randrange(2, TILE - 2), rnd.randrange(8, 11)), 1)
        return s

    def _scorch_tile(self, depth, var):
        """岩浆/岩壁区地面：焦土 + 玄武岩，配合暖色裂隙。"""
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        ramp = [(84, 70, 58), (68, 58, 50), (56, 48, 44), (46, 41, 40), (38, 35, 35)]
        base = ramp[min(depth, 4)]
        rnd = random.Random(depth * 211 + var * 23 + 5)
        s.fill(base)
        for _ in range(28):
            x = rnd.randrange(0, TILE); y = rnd.randrange(0, TILE)
            s.fill(theme.shade(base, rnd.uniform(-0.22, 0.14)),
                   (x, y, rnd.randint(2, 4), rnd.randint(1, 3)))
        if depth == 0:
            top = (104, 88, 70)
            pygame.draw.rect(s, top, (0, 0, TILE, 7))
            pygame.draw.rect(s, theme.shade(top, 0.22), (0, 0, TILE, 2))
            pygame.draw.rect(s, theme.shade(top, -0.25), (0, 7, TILE, 2))
            # 焦土裂缝里的余温
            for _ in range(2):
                x0 = rnd.randrange(2, TILE - 10)
                y0 = rnd.randrange(8, TILE - 6)
                pygame.draw.line(s, (150, 74, 40), (x0, y0), (x0 + rnd.randint(5, 9), y0 + rnd.randint(-2, 2)), 1)
        elif depth >= 2:
            for _ in range(2):
                yy = rnd.randrange(3, TILE - 3)
                pygame.draw.line(s, theme.shade(base, -0.22), (0, yy), (TILE, yy), 1)
        return s

    def _metal_tile(self, depth, var):
        """熔炉区地面：铁板 / 灰烬 / 玄武岩，和森林的草土完全区分开。"""
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        plate = [(104, 84, 68), (86, 70, 58), (72, 60, 52), (58, 50, 46), (46, 40, 38)]
        base = plate[min(depth, 4)]
        rnd = random.Random(depth * 131 + var * 17 + 3)
        s.fill(base)
        for _ in range(26):
            x = rnd.randrange(0, TILE); y = rnd.randrange(0, TILE)
            s.fill(theme.shade(base, rnd.uniform(-0.2, 0.12)),
                   (x, y, rnd.randint(2, 4), rnd.randint(1, 3)))
        if depth == 0:
            # 铁板顶面：亮边 + 铆钉 + 接缝
            top = (128, 104, 78)
            pygame.draw.rect(s, top, (0, 0, TILE, 6))
            pygame.draw.rect(s, theme.shade(top, 0.25), (0, 0, TILE, 2))
            pygame.draw.rect(s, (58, 46, 38), (0, 6, TILE, 2))
            for rx in (5, TILE - 6):
                pygame.draw.circle(s, (86, 72, 58), (rx, 4), 2)
                pygame.draw.circle(s, (150, 126, 98), (rx, 3), 1)
            pygame.draw.line(s, (56, 46, 40), (0, 16), (TILE, 16), 1)
            # 熔渣余烬
            for _ in range(3):
                ex = rnd.randrange(2, TILE - 2)
                s.set_at((ex, rnd.randrange(1, 5)), (232, 128, 62))
        elif depth == 1:
            for _ in range(5):
                ex = rnd.randrange(1, TILE - 1); ey = rnd.randrange(1, TILE - 1)
                s.set_at((ex, ey), (214, 104, 54))
            pygame.draw.rect(s, theme.shade(base, 0.12), (0, 0, TILE, 2))
        else:
            for _ in range(2):
                yy = rnd.randrange(3, TILE - 3)
                pygame.draw.line(s, theme.shade(base, -0.2), (0, yy), (TILE, yy), 1)
        return s

    def _metal_edge(self, seed):
        """熔炉地表边缘：灼热的金属沿，而不是草叶。"""
        s = pygame.Surface((TILE, 12), pygame.SRCALPHA)
        rnd = random.Random(seed * 7 + 1)
        pygame.draw.line(s, (196, 96, 52), (0, 10), (TILE, 10), 2)
        pygame.draw.line(s, (240, 152, 78), (0, 8), (TILE, 8), 1)
        for _ in range(3):
            x = rnd.randrange(0, TILE)
            pygame.draw.circle(s, (236, 132, 64), (x, 7), 1)
        return s

    def get_metal_edge(self, seed):
        key = ("me", seed)
        if key not in self._decor_cache:
            self._decor_cache[key] = self._metal_edge(seed)
        return self._decor_cache[key]

    def _decor(self, kind, var, green=False):
        """地表装饰：草丛 / 石块 / 蘑菇 / 野花 / 枯枝。green=开局绿意段配色。"""
        s = pygame.Surface((TILE, 20), pygame.SRCALPHA)
        rnd = random.Random(kind * 71 + var * 17)
        if kind == 0:      # 草丛（green=鲜绿草叶 / 余烬=焦黑灌木）
            stem = (96, 148, 90) if green else (64, 56, 52)
            stem2 = (120, 174, 104) if green else (40, 36, 34)
            for _ in range(6):
                x = rnd.randrange(4, 28)
                h = rnd.randint(5, 12)
                pygame.draw.line(s, stem, (x, 20), (x + rnd.randint(-3, 3), 20 - h), 2)
                pygame.draw.line(s, stem2, (x, 20), (x + rnd.randint(-2, 2), 20 - h + 2), 1)
        elif kind == 1:    # 石块
            for _ in range(3):
                x = rnd.randrange(3, 24)
                w = rnd.randint(5, 9)
                h = rnd.randint(3, 6)
                pygame.draw.ellipse(s, (86, 88, 96), (x, 20 - h, w, h))
                pygame.draw.ellipse(s, (118, 120, 128), (x + 1, 19 - h, w - 3, 2))
        elif kind == 2:    # 蘑菇（绿段原红伞 / 余烬段暗红棕）
            x = rnd.randrange(8, 22)
            cap, dot = ((196, 84, 78), (240, 200, 180)) if green else ((122, 70, 62), (170, 110, 96))
            pygame.draw.rect(s, (222, 214, 190) if green else (150, 130, 112), (x, 14, 3, 6))
            pygame.draw.ellipse(s, cap, (x - 4, 9, 11, 7))
            pygame.draw.circle(s, dot, (x - 1, 11), 1)
            pygame.draw.circle(s, dot, (x + 3, 12), 1)
        elif kind == 3:    # 枯枝
            x = rnd.randrange(6, 22)
            pygame.draw.line(s, (98, 78, 58), (x, 20), (x + 4, 12), 2)
            pygame.draw.line(s, (98, 78, 58), (x + 2, 16), (x - 2, 12), 1)
            pygame.draw.line(s, (120, 98, 74), (x + 3, 14), (x + 8, 10), 1)
        elif kind == 4:    # 野花（green 原黄白花 / 余烬=火种花）
            x = rnd.randrange(6, 24)
            stem = (98, 148, 88) if green else (86, 60, 48)
            petal = (240, 214, 130) if green else (255, 140, 60)
            core = (255, 246, 200) if green else (255, 224, 150)
            pygame.draw.line(s, stem, (x, 20), (x, 12), 1)
            for dx, dy in ((0, -2), (2, 0), (-2, 0), (0, 2)):
                pygame.draw.circle(s, petal, (x + dx, 11 + dy), 2)
            pygame.draw.circle(s, core, (x, 11), 1)
        else:              # 土块
            pygame.draw.rect(s, (74, 82, 66), (10, 15, 10, 5), border_radius=2)
            pygame.draw.rect(s, (92, 100, 78), (11, 15, 7, 2))
        return s

    def get_decor(self, kind, var, green=False):
        key = ("d", kind, var, green)
        if key not in self._decor_cache:
            self._decor_cache[key] = self._decor(kind, var, green)
        return self._decor_cache[key]

    def _build(self):
        self._decor_cache = {}
        for green in (False, True):
            tag = 1 if green else 0
            for d in range(self.DEPTHS):
                for v in range(self.VARIANTS):
                    self.grass[(d, v, tag)] = self._grass_tile(d, v, green)
                    self.dirt[(d, v, tag)] = self._grass_tile(min(5, d + 2), v, green)
            for v in range(self.VARIANTS):
                self.edge[(tag, v)] = self._edge(v, green=green)
        # 绿->余烬渐变档：按 FADE_STEPS 预烘焙混合 tile（启动一次，运行时直接取）
        self.fade = {}
        for lvl in range(FADE_STEPS + 1):
            f = lvl / float(FADE_STEPS)
            a = int(255 * f)
            for d in range(self.DEPTHS):
                for v in range(self.VARIANTS):
                    for kind in (0, 1):        # 0=grass 1=dirt
                        base = (self.grass if kind == 0 else self.dirt)
                        gimg = base[(d, v, 1)]
                        eimg = base[(d, v, 0)]
                        mixs = gimg.copy()
                        eimg.set_alpha(a)      # 临时给余烬层加 alpha
                        mixs.blit(eimg, (0, 0))
                        eimg.set_alpha(255)    # 恢复，避免影响其它绘制
                        self.fade[(lvl, d, v, kind)] = mixs
        # 金属/焦土只有一套（不分段）
        for d in range(self.DEPTHS):
            for v in range(self.VARIANTS):
                self.metal[(d, v)] = self._metal_tile(d, v)
                self.scorch[(d, v)] = self._scorch_tile(d, v)
        self.rock = {}
        for v in range(self.VARIANTS):
            self.rock[v] = self._rock_tile(v)
        self.edge_scorch = {}
        for v in range(self.VARIANTS):
            self.edge_scorch[v] = self._edge(v, scorch=True)
        # 绿意段悬浮平台：雪暮顶 tile（顶面雪白 + 冻土蓝灰）
        self.snow = {}
        for d in range(self.DEPTHS):
            for v in range(self.VARIANTS):
                self.snow[(d, v)] = self._snow_tile(d, v)

    def get_grass(self, depth, seed, green=False, fade=-1):
        d = min(5, depth)
        v = seed % self.VARIANTS
        if fade >= 0:
            return self.fade[(max(0, min(FADE_STEPS, fade)), d, v, 0)]
        return self.grass[(d, v, 1 if green else 0)]

    def get_dirt(self, depth, seed, green=False, fade=-1):
        d = min(5, depth)
        v = (seed * 3 + 1) % self.VARIANTS
        if fade >= 0:
            return self.fade[(max(0, min(FADE_STEPS, fade)), d, v, 1)]
        return self.dirt[(d, v, 1 if green else 0)]

    def get_rock(self, seed, hp=3):
        img = self.rock[seed % self.VARIANTS]
        return img

    def get_edge(self, seed, scorch=False, green=False):
        if scorch:
            return self.edge_scorch[seed % self.VARIANTS]
        return self.edge[(1 if green else 0, seed % self.VARIANTS)]


# --------------------------------------------------------------------------
# 世界渲染器
# --------------------------------------------------------------------------


def _island_mix(c1, c2, f):
    return (int(c1[0] + (c2[0] - c1[0]) * f),
            int(c1[1] + (c2[1] - c1[1]) * f),
            int(c1[2] + (c2[2] - c1[2]) * f))


class WorldRenderer:
    def __init__(self, screen=None):
        # screen 参数保留只为兼容旧调用点；绘制目标一律由 draw_world(surf, ...) 传入，
        # 这样切全屏重建 Surface 时渲染器无需重建。
        self.tiles = TerrainTiles()
        self.bg = fx.Background(core.WORLD_W)
        self._depth_cache = {}
        self._fg_cache = {}
        self._rock_sig = None
        self.time = 0.0
        self._vig_mask = None
        self._vig_size = None
        self._portal_glow = pygame.Surface((220, 220), pygame.SRCALPHA)
        for i in range(11, 0, -1):
            r = i * 10
            pygame.draw.circle(self._portal_glow, (255, 210, 130, 10),
                               (110, 110), r)
        self._rune_ring = None       # 符文环贴图（懒建一次，之后只做旋转）
        self._slash_ghost = {}       # pid -> [(方向, 已存在时间)]
        self._slash_last = {}        # pid -> 上一帧的 swing 值
        self._lava_cache = {}        # (kind,w,h) -> 静态渐变层
        self._tree_hp = {}           # mid -> 上一帧血量（检测受击闪白）
        self._tree_hurt = {}         # mid -> 受击时刻

    # ---- 深度（到最近暴露顶面的距离）----
    def _depth(self, gx, gy, solid_fn):
        key = (gx, gy)
        d = self._depth_cache.get(key)
        if d is not None:
            return d
        d = 0
        yy = gy - 1
        while d < 5 and yy >= 0 and solid_fn(gx, yy):
            d += 1
            yy -= 1
        self._depth_cache[key] = d
        return d

    def invalidate(self):
        self._depth_cache.clear()

    # ==================================================================
    # 主入口
    # ==================================================================
    def draw_world(self, surf, st, grid, cam, t, rocks_state, region=0.0, focus_pid=None):
        cam_x, cam_y = cam.px, cam.py
        self.time = t
        # 背景
        self.bg.draw(surf, cam_x, cam_y, t, region)
        # 地形
        # 双人机关的按下状态（渲染用）
        try:
            self._duo_held = [False, False]
            for _p in st.get("players", {}).values():
                if _p.get("hp", 0) <= 0:
                    continue
                for _i, _cx in enumerate(core.DUO_PLATE_COLS):
                    if (abs(_p["x"] - (_cx * TILE + 16)) < core.DUO_PLATE_RANGE and
                            abs(_p["y"] - 19 * TILE) < 34):
                        self._duo_held[_i] = True
        except Exception:
            self._duo_held = [False, False]
        self._draw_terrain(surf, grid, cam_x, cam_y, st, rocks_state)
        self._draw_float_shells(surf, grid, cam_x, cam_y)
        # 危险地形
        self._draw_lava(surf, cam_x, cam_y, t)
        self._draw_pit(surf, cam_x, cam_y, t, st)
        # 树精死亡后：附近地面焕发生机（画在地形之上、实体之下）
        self._draw_blooms(surf, cam_x, cam_y, t, st)
        # 陷阱
        self._draw_ground_spikes(surf, cam_x, cam_y, t, st)
        self._draw_hammers(surf, cam_x, cam_y, t, st)
        self._draw_fall_rocks(surf, cam_x, cam_y, t, st)
        # 机关 / 平台
        self._draw_spike_platform(surf, cam_x, cam_y, st)
        self._draw_moving_plates(surf, cam_x, cam_y, st)
        self._draw_pads(surf, cam_x, cam_y, t, st)
        # 交互物
        self._draw_checkpoints(surf, cam_x, cam_y, t, st)
        self._draw_chests(surf, cam_x, cam_y, t, st)
        # 传送门
        self._draw_portal(surf, cam_x, cam_y, t, st)
        # 实体
        self._draw_vines(surf, cam_x, cam_y, t, st)
        self._draw_tower(surf, cam_x, cam_y, t, st)
        self._draw_arrows(surf, cam_x, cam_y, t, st)
        self._draw_corpses(surf, cam_x, cam_y, st)
        self._draw_fireballs(surf, cam_x, cam_y, t, st)
        self._draw_eggs(surf, cam_x, cam_y, t, st)
        self._draw_shockwaves(surf, cam_x, cam_y, st)
        self._draw_rifts(surf, cam_x, cam_y, t, st)
        self._draw_monsters(surf, cam_x, cam_y, t, st)
        self._draw_explosions(surf, cam_x, cam_y, t, st)
        self._draw_lava_eruptions(surf, cam_x, cam_y, t, st)
        self._draw_players(surf, cam_x, cam_y, t, st, focus_pid)
        # 幽蓝火焰画在角色之上：让被喷中的角色被火舌包住
        self._draw_breaths(surf, cam_x, cam_y, t, st)
        # 前景
        self._draw_foreground(surf, cam_x, cam_y, t, region)

        # ---- 泛光：缩图提取高光再叠回原图 ----
        # 这是最便宜的"画质提升"：所有发光的东西（岩浆、传送门、火球、
        # 武器核心）会真的往外晕开，而不是一块死亮的像素。
        if getattr(theme, "quality", 1) >= 1:
            self._bloom(surf, 0.46 if theme.quality >= 2 else 0.34, 122)

        # ---- 暮色：色调随进程沉入夜色 + 视野收窄（st["dusk"] 0..1）----
        try:
            dk = float(st.get("dusk", 0.0) or 0.0)
        except Exception:
            dk = 0.0
        if dk > 0.02:
            if dk < 0.45:
                k = dk / 0.45                    # 黄金时刻：整体偏暖
                mul = (255 - int(18 * k), 255 - int(38 * k), 255 - int(72 * k))
            else:                                # 沉入夜色：偏冷偏暗
                k = (dk - 0.45) / 0.55
                mul = (int(237 - 100 * k), int(217 - 82 * k), int(183 + 12 * k))
            ov = pygame.Surface(surf.get_size())
            ov.fill(mul)
            surf.blit(ov, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            va = int(150 * (dk ** 1.5))          # 暗角随夜色加深
            if va > 5:
                if self._vig_size != surf.get_size():
                    w, h = surf.get_size()
                    v = pygame.Surface((w, h), pygame.SRCALPHA)
                    cx, cy = w // 2, h // 2
                    maxd = math.hypot(cx, cy)
                    steps = 20
                    for i in range(steps):
                        f = i / float(steps)
                        rad = int(maxd * (1.0 - 0.70 * f))
                        a = int(255 * ((1.0 - f) ** 1.8))
                        pygame.draw.circle(v, (6, 8, 18, a), (cx, cy), rad)
                    self._vig_mask = v
                    self._vig_size = surf.get_size()
                v2 = self._vig_mask.copy()
                v2.fill((6, 8, 18, va), special_flags=pygame.BLEND_RGBA_MULT)
                surf.blit(v2, (0, 0))

    def _lava_layer(self, w, h, kind):
        """岩浆的三块静态渐变层（按尺寸缓存）。"""
        key = (kind, int(w), int(h))
        img = self._lava_cache.get(key)
        if img is not None:
            return img
        img = pygame.Surface((int(w), int(h)), pygame.SRCALPHA)
        if kind == "depth":
            for i in range(0, int(h), 3):
                k = i / max(1.0, float(h))
                img.fill((36 + int(k * 40), 16 + int(k * 16), 18 + int(k * 10)),
                         (0, i, int(w), 3))
        elif kind == "body":
            for i in range(int(h)):
                k = i / max(1.0, float(h))
                img.fill(theme.mix((255, 196, 88), (176, 34, 18), k ** 0.6),
                         (0, i, int(w), 1))
        else:  # glow
            for i in range(int(h)):
                f = 0.34 * (i / max(1.0, float(h - 1))) ** 1.7
                img.fill((int(255 * f), int(120 * f), int(48 * f)),
                         (0, i, int(w), 1))
        if len(self._lava_cache) > 24:
            self._lava_cache.clear()
        self._lava_cache[key] = img
        return img

    def _bloom(self, surf, strength=0.4, thresh=96):
        """廉价泛光：缩小 -> 减掉中灰只留高光 -> 放大叠回。

        全屏两次 smoothscale，实测约 1~2ms，比逐物体画辉光划算得多。
        """
        try:
            w, h = surf.get_size()
            # 1/4 降采样 + 放大用最近邻：smoothscale 放大会吃掉 4~5ms，
            # 而泛光本来就是模糊的，最近邻放大看不出来，还快一倍多。
            sw, sh = max(1, w // 4), max(1, h // 4)
            small = pygame.transform.smoothscale(surf, (sw, sh))
            dark = pygame.Surface((sw, sh))
            dark.fill((thresh, thresh, thresh))
            small.blit(dark, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
            big = pygame.transform.scale(small, (w, h))
            f = int(255 * max(0.0, min(1.0, strength)))
            if f < 255:
                big.fill((f, f, f), special_flags=pygame.BLEND_RGB_MULT)
            surf.blit(big, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        except Exception:
            pass

    # ==================================================================
    # 地形
    # ==================================================================
    def _draw_terrain(self, surf, grid, cam_x, cam_y, st, rocks_state):
        if not grid:
            return
        # 绿意段悬浮平台的格子集合：这些格用雪暮 tile（懒计算，grid 不变则复用）
        if not hasattr(self, "_snow_cells_key") or self._snow_cells_key != id(grid):
            self._snow_cells_key = id(grid)
            cells = set()
            if FLOAT_ISLAND_SNOW:          # 雪顶与岩根解耦：关掉岩根仍保留雪顶
                for (c0, c1, gy) in self._float_bottom_segments(grid):
                    if c0 >= GREEN_UNTIL:
                        continue
                    thick = 1
                    while thick < 3 and gy - thick >= 0 and grid[gy - thick][c0] not in (' ', 'O'):
                        thick += 1
                    for rr in range(gy - thick + 1, gy + 1):
                        for cc in range(c0, c1 + 1):
                            cells.add((cc, rr))
            self._snow_cells = cells
        gx0 = max(0, cam_x // TILE - 1)
        gx1 = min(core.MAP_W - 1, (cam_x + surf.get_width()) // TILE + 1)
        gy0 = max(0, cam_y // TILE - 1)
        gy1 = min(core.MAP_H - 1, (cam_y + surf.get_height()) // TILE + 1)

        def solid(gx, gy):
            if gx < 0 or gx >= core.MAP_W or gy < 0:
                return False
            if gy >= core.MAP_H:
                return True
            return grid[gy][gx] in ('G', 'R', 'Q', 'S', 's')

        removed = set()
        for r in st.get("rocks", []):
            if r.get("hp", 0) <= 0:
                removed.add((r["cx"], r["cy"]))

        for gy in range(gy0, gy1 + 1):
            row = grid[gy]
            for gx in range(gx0, gx1 + 1):
                c = row[gx]
                if c in (' ', 'O'):
                    continue
                sx = gx * TILE - cam_x
                sy = gy * TILE - cam_y
                seed = (gx * 7 + gy * 13) & 0x7fffffff
                if c in ('G', 'S', 's'):
                    d = self._depth(gx, gy, solid)
                    dj = min(d, self.tiles.DEPTHS - 1)
                    green = gx < GREEN_UNTIL
                    # 渐变区：45..61 逐格混合绿/余烬两套 tile
                    fade_lvl = -1
                    if GREEN_UNTIL <= gx < GREEN_UNTIL + FADE_LEN:
                        fade_lvl = int((gx - GREEN_UNTIL) / float(FADE_LEN) * FADE_STEPS)
                    # 余烬裂缝密度递进：焦土区强制走"密缝"变体（var>=2）
                    if not green and gx >= core.SCORCH_LEFT:
                        seed |= 2
                    if gx >= core.FORGE_LEFT:
                        surf.blit(self.tiles.metal[(dj, seed % self.tiles.VARIANTS)], (sx, sy))
                    elif gx >= core.SCORCH_LEFT:
                        surf.blit(self.tiles.scorch[(dj, seed % self.tiles.VARIANTS)], (sx, sy))
                    elif (gx, gy) in self._snow_cells:
                        # 绿意段的悬浮平台：雪暮顶
                        img = self.tiles.snow[(min(d, 1), seed % self.tiles.VARIANTS)] if d <= 1 \
                            else self.tiles.snow[(min(d, self.tiles.DEPTHS - 1), seed % self.tiles.VARIANTS)]
                        surf.blit(img, (sx, sy))
                    else:
                        if fade_lvl >= 0:
                            img = (self.tiles.get_grass(d, seed, green, fade_lvl) if d <= 1
                                   else self.tiles.get_dirt(d, seed, green, fade_lvl))
                        else:
                            img = (self.tiles.get_grass(d, seed, green) if d <= 1
                                   else self.tiles.get_dirt(d, seed, green))
                        surf.blit(img, (sx, sy))
                elif c == 'Q':
                    # 先把整格地面画满，再把压板叠在上表面——
                    # 否则 'Q' 格下半部分没有地形，会直接漏出背景色（看起来像地面破了个洞）
                    d = self._depth(gx, gy, solid)
                    if gx >= core.FORGE_LEFT:
                        surf.blit(self.tiles.metal[(min(d, self.tiles.DEPTHS - 1), seed % self.tiles.VARIANTS)], (sx, sy))
                    elif gx >= core.SCORCH_LEFT:
                        surf.blit(self.tiles.scorch[(min(d, self.tiles.DEPTHS - 1), seed % self.tiles.VARIANTS)], (sx, sy))
                    else:
                        _g2 = gx < GREEN_UNTIL
                        if d <= 1:
                            surf.blit(self.tiles.get_grass(d, seed, _g2), (sx, sy))
                        else:
                            surf.blit(self.tiles.get_dirt(d, seed, _g2), (sx, sy))
                    self._draw_plate_tile(surf, sx, sy, self.time)
                elif c == 'q':
                    d = self._depth(gx, gy, solid)
                    dj = min(d, self.tiles.DEPTHS - 1)
                    surf.blit(self.tiles.metal[(dj, seed % self.tiles.VARIANTS)], (sx, sy))
                    held = self._duo_idx_held(gx)
                    self._draw_duo_plate(surf, sx, sy, held)
                elif c == 'H':
                    self._draw_gate(surf, sx, sy, self.time)
                elif c == 'R':
                    if (gx, gy) in removed:
                        # 被击碎的岩石 -> 露出后面的地面/空气
                        if gy >= 19:
                            surf.blit(self.tiles.get_grass(2, seed), (sx, sy))
                        continue
                    surf.blit(self.tiles.get_rock(seed), (sx, sy))
                elif c in ('s', 'S'):
                    pass

        # 顶部草叶（在所有地块之后统一叠加，避免被相邻块盖住）
        for gy in range(gy0, gy1 + 1):
            for gx in range(gx0, gx1 + 1):
                c = grid[gy][gx]
                if c not in ('G', 'S', 's'):
                    continue
                if gy > 0 and grid[gy - 1][gx] in ('G', 'R', 'Q', 'S', 's'):
                    continue
                seed = (gx * 11 + gy * 5) & 0x7fffffff
                _g = gx < (GREEN_UNTIL + FADE_LEN // 2)
                if gx >= core.FORGE_LEFT:
                    surf.blit(self.tiles.get_metal_edge(seed),
                              (gx * TILE - cam_x, gy * TILE - cam_y - 8))
                elif gx >= core.SCORCH_LEFT:
                    surf.blit(self.tiles.get_edge(seed, scorch=True),
                              (gx * TILE - cam_x, gy * TILE - cam_y - 4))
                else:
                    surf.blit(self.tiles.get_edge(seed, green=_g),
                              (gx * TILE - cam_x, gy * TILE - cam_y - 4))
                # 地表装饰（稀疏分布）
                h = (gx * 2654435761) & 0x7fffffff
                if h % 3 != 0:
                    kind = (h >> 5) % 6
                    if gx >= core.FORGE_LEFT:
                        kind = 1 if kind % 2 == 0 else 5      # 熔炉区只留碎石/土块
                    elif gx >= core.SCORCH_LEFT:
                        kind = 1 if kind % 2 == 0 else 3      # 岩壁区：碎石与枯枝
                    surf.blit(self.tiles.get_decor(kind, h % 4, green=gx < (GREEN_UNTIL + FADE_LEN // 2)),
                              (gx * TILE - cam_x, gy * TILE - cam_y - 16))

    def _duo_idx_held(self, gx):
        try:
            idx = list(core.DUO_PLATE_COLS).index(gx)
            return bool(self._duo_held[idx]) if hasattr(self, "_duo_held") else False
        except Exception:
            return False

    def _draw_duo_plate(self, surf, sx, sy, held):
        """双人机关：带两个插槽的重型压板，踩下时亮起。"""
        pygame.draw.rect(surf, (48, 46, 56), (sx - 2, sy, TILE + 4, 16), border_radius=3)
        col = (150, 210, 255) if held else (96, 100, 118)
        pygame.draw.rect(surf, (72, 76, 92), (sx, sy + 2, TILE, 12), border_radius=3)
        pygame.draw.rect(surf, col, (sx + 3, sy + 4, TILE - 6, 4), border_radius=2)
        for dx in (10, TILE - 11):
            pygame.draw.circle(surf, col, (sx + dx, sy + 11), 3)
            if held:
                pygame.draw.circle(surf, (230, 246, 255), (sx + dx, sy + 11), 1)

    def _draw_gate(self, surf, sx, sy, t):
        """熔炉闸门：铁栅 + 顶梁，关闭时挡住去路。"""
        pygame.draw.rect(surf, (38, 36, 44), (sx + 2, sy, TILE - 4, TILE))
        pygame.draw.rect(surf, (86, 82, 96), (sx + 2, sy, TILE - 4, 4))
        for i in range(3):
            bx = sx + 7 + i * 8
            pygame.draw.rect(surf, (58, 56, 68), (bx, sy + 3, 3, TILE - 4))
            pygame.draw.line(surf, (110, 106, 122), (bx, sy + 4), (bx, sy + TILE - 4), 1)
        for y in range(sy + 8, sy + TILE, 10):
            pygame.draw.line(surf, (46, 44, 54), (sx + 4, y), (sx + TILE - 4, y), 2)

    def _draw_plate_tile(self, surf, sx, sy, t):
        """压力机关：平贴地面的金属压板（只占格子顶部 16px，不向地下延伸）"""
        pygame.draw.rect(surf, (58, 60, 72), (sx, sy + 12, TILE, 3))
        pygame.draw.rect(surf, (92, 96, 112), (sx, sy + 12, TILE, 1))
        pygame.draw.rect(surf, (52, 54, 66), (sx, sy, TILE, 13), border_radius=3)
        pygame.draw.rect(surf, (124, 128, 148), (sx + 2, sy + 1, TILE - 4, 10), border_radius=3)
        for dx in (6, TILE - 7):
            pygame.draw.circle(surf, (188, 192, 206), (sx + dx, sy + 6), 2)
        glow = 0.25 + 0.2 * math.sin(t * 3.4)
        pygame.draw.rect(surf, theme.alpha_color((255, 206, 120), int(120 * glow)),
                         (sx + 3, sy + 2, TILE - 6, 2))

    # ==================================================================
    # 岩浆
    # ==================================================================
    def _draw_lava(self, surf, cam_x, cam_y, t):
        lx0 = core.LAVA_LEFT * TILE
        ly0 = core.LAVA_ROW * TILE
        lx1 = (core.LAVA_RIGHT + 1) * TILE
        ly1 = core.MAP_H * TILE
        sx0, sy0 = lx0 - cam_x, ly0 - cam_y
        if lx1 - cam_x < 0 or lx0 - cam_x > surf.get_width():
            return
        w = lx1 - lx0
        h = min(ly1 - cam_y, surf.get_height()) - sy0
        if h <= 0:
            return
        # 深渊底色 / 岩浆本体 / 上方热辉：三块都是静态渐变，
        # 按尺寸缓存起来，每帧只做 blit。原来每帧现画三整块（512×96 逐行
        # draw.line），光岩浆就吃掉好几毫秒。
        if sy0 + h > 0:
            depth = self._lava_layer(w, h, "depth")
            surf.blit(depth, (sx0, max(0, sy0)))
        # 岩浆本体
        surf_rect = pygame.Rect(sx0, max(0, sy0), w, max(0, min(h, 96)))
        if surf_rect.h > 0:
            surf.blit(self._lava_layer(w, surf_rect.h, "body"),
                      (surf_rect.x, surf_rect.y))
        # 波峰
        for i in range(w):
            wx = sx0 + i
            if wx < -4 or wx > surf.get_width() + 4:
                continue
            wave = math.sin(i * 0.06 + t * 2.6) * 3 + math.sin(i * 0.017 - t * 1.4) * 2
            yy = sy0 + int(wave)
            col = (255, 240, 180) if (i // 3 + int(t * 6)) % 9 == 0 else (255, 158, 60)
            pygame.draw.line(surf, col, (wx, yy), (wx, yy + 2))
        # 气泡与浮渣
        for k in range(7):
            bx = lx0 + ((k * 137 + int(t * 22)) % w)
            by = sy0 + 8 + (k * 11) % 60
            r = 2 + (k % 3)
            pygame.draw.circle(surf, (255, 214, 130), (bx - cam_x, by), r, 1)
        # 上方热辉（靠近岩浆表面最亮，向上渐隐；两侧多留 40px 避免硬竖边）
        gw, gh = w + 80, 150
        surf.blit(self._lava_layer(gw, gh, "glow"), (sx0 - 40, sy0 - gh),
                  special_flags=pygame.BLEND_RGBA_ADD)
        # 上升余烬：几粒暖光随热流上浮
        for k in range(9):
            ex = lx0 + ((k * 211 + int(t * 16)) % max(1, w)) - cam_x
            ph = (t * 0.30 + k * 0.137) % 1.0
            ey = sy0 - ph * 120
            a = int(150 * (1.0 - ph) ** 1.4)
            if a > 8:
                pygame.draw.circle(surf, (255, 206, 140, a),
                                   (int(ex), int(ey)), 1 + int(2 * (1.0 - ph)))

    # ==================================================================
    # 深坑
    # ==================================================================
    def _draw_pit(self, surf, cam_x, cam_y, t, st):
        pit_l = core.PIT_COLS[0] * TILE
        pit_r = (core.PIT_COLS[1] + 1) * TILE
        y0 = core.PIT_TOP_Y
        y1 = core.PIT_FLOOR_Y
        sx, sy = pit_l - cam_x, y0 - cam_y
        if sx > surf.get_width() or sx + (pit_r - pit_l) < 0:
            return
        pw, ph = pit_r - pit_l, y1 - y0
        pit = pygame.Surface((pw, ph), pygame.SRCALPHA)
        for i in range(ph):
            k = i / max(1, ph)
            c = (14 + int(k * 10), 12 + int(k * 7), 16 + int(k * 6))
            pygame.draw.rect(pit, c, (0, i, pw, 3))
        # 坑壁砖缝
        for row in range(0, ph, 18):
            pygame.draw.line(pit, (28, 24, 32), (0, row), (pw, row), 1)
        # 白骨
        for bx in range(6, pw - 6, 22):
            pygame.draw.line(pit, (96, 90, 82), (bx, ph - 22), (bx + 12, ph - 14), 2)
            pygame.draw.circle(pit, (108, 100, 92), (bx + 6, ph - 26), 3)
        surf.blit(pit, (sx, sy))
        # 坑口警示带（暗底 + 琥珀斜纹，比原来的红黄方块更像工业警示）
        strip = pygame.Surface((pw, 7), pygame.SRCALPHA)
        pygame.draw.rect(strip, (34, 28, 26), (0, 0, pw, 7))
        for i in range(-14, pw + 14, 16):
            pygame.draw.polygon(strip, (236, 168, 62),
                                [(i, 7), (i + 7, 0), (i + 15, 0), (i + 8, 7)])
        pygame.draw.line(strip, (255, 210, 120), (0, 0), (pw, 0), 1)
        surf.blit(strip, (sx, sy - 7))
        # 深坑上方的冷雾
        fog = pygame.Surface((pw + 40, 90), pygame.SRCALPHA)
        for i in range(90):
            a = int(30 * (1 - i / 90.0))
            pygame.draw.line(fog, (120, 140, 180, a), (0, i), (pw + 40, i))
        surf.blit(fog, (sx - 20, sy - 40))

    # ==================================================================
    # 陷阱
    # ==================================================================
    def _float_bottom_segments(self, grid):
        """找出所有"悬空底面"：某段实心格的正下方是空的。

        返回 [(c0, c1, gy)]，gy 是这段的底边所在行。
        地面 / 塔基（下面接着实心）不会被算进来。
        """
        solid_ch = ('G', 'R', 'Q', 'S', 's')
        segs = []
        try:
            for gy in range(core.MAP_H - 1):
                gx = 0
                while gx < core.MAP_W:
                    if grid[gy][gx] in solid_ch and grid[gy + 1][gx] in (' ', 'O'):
                        c0 = gx
                        while (gx + 1 < core.MAP_W and grid[gy][gx + 1] in solid_ch
                               and grid[gy + 1][gx + 1] in (' ', 'O')):
                            gx += 1
                        segs.append((c0, gx, gy))
                    gx += 1
        except Exception:
            pass
        return segs

    def _island_palette(self, c0):
        """运行时采样平台 tile 的真实像素色，派生岛体四档色。

        不采样必跑偏：平台侧面实际是 grass tile（平台下格 depth=1 仍走 grass），
        之前按 dirt 深档给灰褐，结果绿平台挂灰岩根，色系断裂。
        """
        try:
            if c0 >= core.FORGE_LEFT:
                img = self.tiles.metal[(1, 0)]
            elif c0 >= core.SCORCH_LEFT:
                img = self.tiles.scorch[(1, 0)]
            else:
                img = self.tiles.get_grass(1, 0)
            w, h = img.get_size()
            sr = sg = sb = cnt = 0
            for yy in range(h - 10, h - 2):          # 底部 8 行 = 侧面色
                for xx in range(0, w, 2):
                    c = img.get_at((xx, yy))
                    if c.a > 128:
                        sr += c.r; sg += c.g; sb += c.b; cnt += 1
            if cnt:
                tr, tg, tb = sr // cnt, sg // cnt, sb // cnt
            else:
                tr, tg, tb = 76, 72, 70

            def _mix(c1, c2, f):
                return (int(c1[0] + (c2[0] - c1[0]) * f),
                        int(c1[1] + (c2[1] - c1[1]) * f),
                        int(c1[2] + (c2[2] - c1[2]) * f))
            c_top = (tr, tg, tb)
            c_mid = _mix(c_top, (30, 30, 36), 0.22)
            c_dark = _mix(c_top, (12, 12, 16), 0.42)
            c_hi = _mix(c_top, (255, 255, 255), 0.22)
            return c_top, c_mid, c_dark, c_hi
        except Exception:
            return (76, 72, 70), (66, 63, 61), (52, 50, 48), (88, 84, 80)

    def _bake_island(self, seg, grid):
        """烘焙一个悬浮岛（v4，参考浮空岛概念图）。

        形状：薄草皮 + 厚实圆弧岩体（下半椭圆近似，占岛高 60%+），
        岩石垂直分三层（浅->深）、纵向裂纹、底部圆润挂漂浮碎石，
        部分岛有瀑布痕迹。碰撞仍是方块制。
        """
        c0, c1, gy = seg
        T = TILE
        px_w = (c1 - c0 + 1) * T
        thick = 1
        while thick < 3 and gy - thick >= 0 and grid[gy - thick][c0] not in (' ', 'O'):
            thick += 1
        # 岩体厚度：参考图里岩石占岛的 60~70%，比薄尾巴厚重得多
        # 4.4 格会让岩体底部戳进地面(608)，'悬浮'变'插地'；3.2 格底缘 ~519，
        # 离地面还有约 90px 的悬空层
        depth = int(min(T * 3.2, px_w * 0.85 + T))
        fringe = 34
        pad = 20
        w = px_w + pad * 2
        h = thick * T + depth + fringe
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        if getattr(FLOAT_ISLAND_SNOW, "__class__", None) is bool and FLOAT_ISLAND_SNOW:
            # 雪暮：雪白过渡带 + 蓝灰岩体（不走 tile 采样）
            c_top = (222, 232, 246)
            c_mid = (150, 162, 184)
            c_dark = (96, 106, 130)
            c_hi = (232, 240, 252)
        else:
            c_top, c_mid, c_dark, c_hi = self._island_palette(c0)
        # 岩石主体比草皮略浅偏灰（参考图：鲜绿草皮 + 浅灰岩体），底部再压深
        c_rock = _island_mix(c_top, (158, 164, 178), 0.62)   # 大幅去绿：草皮与岩石色相分离
        c_rock_hi = _island_mix(c_rock, (255, 255, 255), 0.18)
        c_rock_mid = _island_mix(c_rock, (30, 32, 40), 0.18)
        c_rock_deep = _island_mix(c_rock, (16, 16, 24), 0.48)
        rng = random.Random((c0 * 73856093) ^ (gy * 19349663))
        yb = thick * T
        x0, x1 = pad, pad + px_w
        cx = (x0 + x1) / 2.0
        rx = px_w * 0.5 + 10 + rng.randint(0, 6)     # 椭圆横轴（肩部略宽于平台）
        ry = depth                                    # 纵轴 = 岩体厚

        # ---- 轮廓：上边直线 + 下半椭圆（带噪声）+ 1~2 个底部凸块 ----
        body = [(x0 - 3, yb - 1), (x1 + 3, yb - 1)]
        n = 12
        for i in range(n + 1):
            f = i / float(n)                          # 0..1 右->左
            a = math.pi * f                           # 半圆参数
            ex = cx - math.cos(a) * rx
            ey = yb + math.sin(a) * ry
            # 噪声：边缘风化感（两端小，中段大）
            amp = 2 + 4 * math.sin(a)
            ey += rng.uniform(-amp, amp) * 0.6
            ex += rng.uniform(-2, 2)
            body.append((ex, ey))
        pygame.draw.polygon(surf, c_rock, body)

        # ---- 垂直分层（set_clip 分段填充同轮廓）----
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(0, yb, w, max(1, int(ry * 0.34))))
        pygame.draw.polygon(surf, c_rock_hi, body)
        surf.set_clip(pygame.Rect(0, yb + int(ry * 0.34), w, max(1, int(ry * 0.40))))
        pygame.draw.polygon(surf, c_rock_mid, body)
        surf.set_clip(pygame.Rect(0, yb + int(ry * 0.74), w, h - (yb + int(ry * 0.74))))
        pygame.draw.polygon(surf, c_rock_deep, body)
        surf.set_clip(clip)
        # 层间接缝（细暗线）
        for f in (0.34, 0.74):
            pygame.draw.line(surf, c_rock_deep,
                             (cx - rx * 0.92, yb + ry * f),
                             (cx + rx * 0.92, yb + ry * f), 1)

        # ---- 纵向裂纹（岩缝，微弯）----
        for k in range(4 + rng.randint(0, 2)):
            fx = rng.uniform(0.12, 0.88)
            sx2 = x0 + px_w * fx
            ln = depth * rng.uniform(0.45, 0.85)
            pts = []
            for i in range(4):
                t2 = i / 3.0
                pts.append((sx2 + rng.uniform(-2.5, 2.5) + math.sin(t2 * 4) * 2,
                            yb + 6 + t2 * ln))
            pygame.draw.lines(surf, c_rock_deep, False, pts, 1)

        # ---- 横向岩层纹理（少量短横线，避开裂纹感过重）----
        for k in range(3):
            yy = yb + depth * (0.30 + 0.22 * k)
            half = rx * (0.55 + 0.2 * k)
            pygame.draw.line(surf, c_rock_deep,
                             (cx - half, yy), (cx + half * 0.9, yy), 1)

        # ---- 草沿外溢 + 草皮投影带（参考图：草皮下的深色阴影让岩体立刻立体）----
        pygame.draw.line(surf, c_top, (x0 - 3, yb - 1), (x1 + 3, yb - 1), 2)
        pygame.draw.rect(surf, _island_mix(c_rock_deep, (0, 0, 0), 0.25),
                         (x0 - 3, yb + 1, px_w + 6, 4))

        # ---- 瀑布痕迹（30% 的岛，参考图点睛元素；静态淡蓝白条）----
        if rng.random() < 0.3 and px_w >= 96:
            wx2 = x0 + px_w * rng.uniform(0.18, 0.42)
            wy2 = yb + 4
            wl = depth * rng.uniform(0.62, 0.85)
            _fr = (0.0, 0.45, 0.80)
            _lw = (5, 3, 2)
            _al = (120, 70, 32)
            _ln = (0.45, 0.35, 0.20)
            for seg_i in range(3):
                seg_len = wl * _ln[seg_i]
                y_a = wy2 + wl * _fr[seg_i]
                pygame.draw.rect(surf, (205, 226, 255, _al[seg_i]),
                                 (wx2 - 2, y_a, _lw[seg_i], seg_len))
            pygame.draw.rect(surf, (240, 248, 255, 150), (wx2 - 2, wy2, 5, 4))

        # ---- 底部漂浮碎石（参考图岛下的小浮石）----
        for k in range(3 + rng.randint(0, 2)):
            ang = rng.uniform(0.15, 0.85) * math.pi
            dx = cx + math.cos(math.pi - ang) * (rx + rng.randint(-6, 14)) * rng.choice((1, -1))
            dy = yb + ry * (0.72 + 0.3 * rng.random()) + rng.randint(4, fringe - 10)
            rr3 = rng.randint(2, 5)
            st = [(dx - rr3, dy), (dx + rr3, dy + 1), (dx + rr3 * 0.4, dy + rr3),
                  (dx - rr3 * 0.6, dy + rr3 - 1)]
            pygame.draw.polygon(surf, c_rock_mid, st)
            pygame.draw.polygon(surf, c_rock_deep, st, 1)
        # 烘焙返回世界坐标：面 y=0 对齐平台顶
        return surf, c0 * TILE - pad, (gy + 1 - thick) * TILE

    def _draw_float_shells(self, surf, grid, cam_x, cam_y):
        """把烘焙好的岛体按视口 blit（缓存于 self._island_cache）。"""
        if not FLOAT_ISLANDS:
            return
        # 只画绿意段的浮岛（雪暮顶）；余烬段不画
        if not hasattr(self, "_island_cache"):
            self._island_cache = {}
        vw = surf.get_width()
        for seg in self._float_bottom_segments(grid):
            try:
                if seg[0] >= GREEN_UNTIL:
                    continue
                if seg not in self._island_cache:
                    self._island_cache[seg] = self._bake_island(seg, grid)
                isurf, wx, wy = self._island_cache[seg]
                sx, sy = wx - cam_x, wy - cam_y
                if sx > vw + 80 or sx + isurf.get_width() < -80:
                    continue
                surf.blit(isurf, (sx, sy))
            except Exception as e:
                if not getattr(self, "_island_warned", False):
                    self._island_warned = True
                    print("[悬浮岛绘制异常] %r" % (e,))

    # 哪几条地刺用"红黑荆棘"（其余保持金属三角刺）。按 SPIKE_STRIPS 索引，
    # 想全改或全留只动这个集合。
    BRAMBLE_STRIPS = set(core.BRAMBLE_IDX)

    def _bramble_stalks(self, bx_world):
        """按世界坐标生成一簇荆棘的【固定基准形状】并缓存。

        关键：种子必须吃世界坐标。之前用屏幕坐标 int(x0) 当种子，
        相机一动种子就变，形状每帧重掷——那不是"活"，是噪点。
        这里形状只生成一次，动画靠绘制阶段叠加时间相位。
        """
        cache = getattr(self, "_bramble_cache", None)
        if cache is None:
            cache = self._bramble_cache = {}
        key = int(bx_world)
        if key in cache:
            return cache[key]
        rnd = random.Random((key * 2654435761) & 0x7fffffff)
        stalks = []
        for _ in range(rnd.randint(3, 4)):
            side = rnd.choice((-1.0, 1.0)) * rnd.uniform(0.5, 1.0)
            stalks.append({
                "side": side,
                "h": rnd.uniform(26, 40),
                "ox": rnd.uniform(-3, 3),
                "phase": rnd.uniform(0.0, 6.283),      # 逐根独立相位
                "breath_ph": rnd.uniform(0.0, 6.283),
                "bend": rnd.uniform(5.5, 8.5),
                "hooks": [(i, rnd.uniform(-1.2, 1.2), rnd.uniform(5.0, 8.5))
                          for i in (1, 2, 3) if rnd.random() > 0.28],
            })
        cache[key] = stalks
        return stalks

    def _draw_bramble(self, surf, x0, x1, base_y, t, cam_x, near_dist=999.0):
        """红黑弯刺荆棘（三层生命感）。

        1) 摇曳：逐根独立相位，根部几乎不动、越靠尖端摆幅越大（f^1.5）
        2) 呼吸：整簇缓慢起伏，周期 ~7s，幅度 <1px
        3) 感知：玩家靠近（150px 内）时摆幅放大到 3 倍、频率加快
        """
        # 底部黑根 / 腐土带（不参与动画）
        pygame.draw.rect(surf, (24, 13, 15), (x0, base_y - 4, x1 - x0, 4))
        pygame.draw.rect(surf, (44, 20, 24), (x0, base_y - 4, x1 - x0, 1))

        # 感知强度：0（远）-> 1（贴脸）
        alert = max(0.0, 1.0 - near_dist / 150.0)
        boost = 1.0 + 2.0 * alert          # 摆幅倍率 1x -> 3x
        speed = 1.0 + 0.6 * alert          # 频率倍率

        bx = x0 + 4
        while bx < x1 - 2:
            for st in self._bramble_stalks(bx + cam_x):
                # 呼吸起伏（整簇极缓）
                breath = math.sin(t * 0.9 + st["breath_ph"]) * 1.4
                pts = []
                for i in range(5):
                    f = i / 4.0
                    # 摇曳：尖端滞后（+f*0.9 相位差），幅度按 f^1.5 递增
                    # 摆幅必须明显大于 1px：int 圆整会把 1px 级摆动完全吃掉
                    sway = (math.sin(t * 2.6 * speed + st["phase"] + f * 0.9)
                            * 2.8 * (f ** 1.2) * boost)
                    px = bx + st["ox"] + st["side"] * (f ** 1.6) * st["bend"] + sway
                    py = base_y - 3 - f * st["h"] + breath
                    pts.append((px, py))
                # 主干三层（暗红 / 亮红高光 / 阴影侧）
                pygame.draw.lines(surf, (86, 24, 32), False, pts, 2)
                pygame.draw.lines(surf, (150, 46, 56), False,
                                  [(p[0] - 1, p[1]) for p in pts], 1)
                pygame.draw.lines(surf, (48, 16, 20), False,
                                  [(p[0] + 1.5, p[1]) for p in pts], 1)
                # 斜生钩刺（随主干一起摆）
                for (hi, ha, hlen) in st["hooks"]:
                    if hi >= len(pts):
                        continue
                    _p = pts[hi]
                    _hx = _p[0] + ha * hlen
                    _hy = _p[1] - hlen * 0.85
                    pygame.draw.line(surf, (72, 20, 26), _p, (_hx, _hy), 1)
                    pygame.draw.circle(surf, (188, 62, 66), (int(_hx), int(_hy)), 1)
                # 顶梢亮红点（最强摆幅处，也点出"活着"的感觉）
                tp = pts[-1]
                pygame.draw.circle(surf, (214, 74, 74), (int(tp[0]), int(tp[1])), 1)
            bx += 19

    def _draw_ground_spikes(self, surf, cam_x, cam_y, t, st=None):
        """地面刺条（SPIKE_STRIPS）：金属三角刺 / 红黑弯荆棘（按条区分）。"""
        players = [p for p in (st or {}).get("players", {}).values() if p.get("hp", 1) > 0]
        for idx, (c0, c1) in enumerate(core.SPIKE_STRIPS):
            try:
                x0 = c0 * TILE - cam_x
                x1 = (c1 + 1) * TILE - cam_x
                if x1 < -40 or x0 > surf.get_width() + 40:
                    continue
                base_y = 19 * TILE - cam_y
                w = x1 - x0
                if idx in self.BRAMBLE_STRIPS:
                    # 最近玩家距离（世界坐标），驱动"感知"层
                    cxw = (c0 + c1 + 1) * 0.5 * TILE
                    near = min((abs(p["x"] - cxw) for p in players), default=999.0)
                    self._draw_bramble(surf, int(x0), int(x1), int(base_y),
                                       t, cam_x, near)
                    continue
                # 基座
                pygame.draw.rect(surf, (58, 54, 62), (x0, base_y - 6, w, 6))
                pygame.draw.rect(surf, (96, 90, 100), (x0, base_y - 6, w, 2))
                # 刺（每格 4 枚）
                n = max(1, w // 8)
                step = w / float(n)
                for i in range(n):
                    bx = x0 + i * step
                    tip = base_y - 6 - core.SPIKE_STRIP_H + 2
                    pygame.draw.polygon(surf, (196, 200, 214),
                                        [(bx + 1, base_y - 5), (bx + step * 0.5, tip),
                                         (bx + step - 1, base_y - 5)])
                    pygame.draw.line(surf, (240, 244, 252),
                                     (bx + step * 0.5, tip + 2), (bx + step * 0.42, base_y - 7), 1)
            except Exception:
                continue

    def _draw_hammers(self, surf, cam_x, cam_y, t, st):
        """摆锤：悬挂链 + 铁铸锤头 + 摆动轨迹弧（v3 重构时误删，按规格重写）。"""
        for h in st.get("hammers", []):
            try:
                px = h["px"] - cam_x
                py = h["py"] - cam_y
                bx = h["bx"] - cam_x
                by = h["by"] - cam_y
                r = h["r"]
                if bx < -120 or bx > surf.get_width() + 120:
                    continue
                # 链条（链节小圆）
                steps = 10
                for i in range(1, steps):
                    f = i / float(steps)
                    cx = px + (bx - px) * f
                    cy = py + (by - py) * f
                    pygame.draw.circle(surf, (72, 70, 82), (int(cx), int(cy)), 2)
                pygame.draw.circle(surf, (110, 106, 122), (int(px), int(py)), 4)
                # 锤头（不规则铁块）
                import random as _rr
                rnd = _rr.Random(int(h["id"][1:]) if isinstance(h["id"], str) else 7)
                pts = []
                for i in range(9):
                    a = i * 0.698
                    rr2 = r + rnd.uniform(-4, 4)
                    pts.append((bx + math.cos(a) * rr2, by + math.sin(a) * rr2 * 0.92))
                pygame.draw.polygon(surf, (96, 88, 86), pts)
                pygame.draw.polygon(surf, (50, 46, 50), pts, 2)
                pygame.draw.circle(surf, (138, 128, 122), (int(bx - 5), int(by - 6)), 6)
                # 危险辉光
                theme.glow_circle(surf, (int(bx), int(by)), r + 10, (255, 120, 70), 0.12, 2)
            except Exception:
                continue

    def _draw_danger_beam(self, surf, cx, top, bot, t):
        """落石预警光柱：从裂缝垂到地面，脉动一次比一次亮。"""
        try:
            h = int(bot - top)
            if h <= 6:
                return
            pulse = 0.5 + 0.5 * math.sin(t * 9.0)
            w = 16 + int(6 * pulse)
            beam = pygame.Surface((w, h), pygame.SRCALPHA)
            for i in range(h):
                k = i / float(max(1, h - 1))
                a = int((28 + 34 * pulse) * (0.35 + 0.65 * k))
                beam.fill((255, 150, 90, a), (0, i, w, 1))
            surf.blit(beam, (int(cx) - w // 2, int(top)),
                      special_flags=pygame.BLEND_RGBA_ADD)
            # 中轴亮线
            pygame.draw.line(surf, (255, 214, 170), (int(cx), int(top)),
                             (int(cx), int(bot)), 1)
            # 地面上的落点圈
            pygame.draw.ellipse(surf, theme.alpha_color((255, 120, 80), 170),
                                (int(cx) - 22, int(bot) - 8, 44, 14), 2)
            pygame.draw.ellipse(surf, theme.alpha_color((255, 90, 60), 90),
                                (int(cx) - 30, int(bot) - 12, 60, 20), 1)
        except Exception:
            pass

    def _draw_sky_crack(self, surf, cx, cy, t, ratio):
        """天空裂缝（落石前兆）：发光裂隙 + 放射碎纹 + 边缘碎屑。

        层次：外辉 -> 深空内核 -> 锯齿口沿 -> 分叉细纹 -> 掉落碎屑。
        """
        w = 34.0 + 78.0 * ratio
        h = 8.0 + 40.0 * ratio
        n = 13
        top, bot = [], []
        for i in range(n + 1):
            f = i / float(n)
            x = cx - w * 0.5 + w * f
            taper = math.sin(f * math.pi) ** 0.55
            tooth = (2.8 if i % 2 == 0 else -2.0) * ratio
            jt = math.sin(f * 9.3 + t * 3.1) * (1.2 + 2.0 * ratio) + tooth
            top.append((x, cy - h * taper * 0.5 + jt))
            bot.append((x, cy + h * taper * 0.5 - jt))

        # 外辉：裂缝整体在发光，越开越亮
        theme.glow_circle(surf, (cx, cy), int(w * 0.62), (150, 92, 200),
                          0.16 + 0.26 * ratio, 3)
        theme.glow_circle(surf, (cx, cy), int(w * 0.34), (206, 158, 255),
                          0.12 + 0.22 * ratio, 2)

        # 放射碎纹（先画在底下，被裂口盖住中段）
        if ratio > 0.2:
            rr = random.Random(int(cx) * 31 + 5)
            for k in range(9):
                side = -1.0 if k % 2 == 0 else 1.0
                a0 = rr.uniform(-0.7, 0.7)
                ln = (16 + rr.uniform(0, 34)) * ratio
                x0 = cx + side * w * 0.40
                y0 = cy + a0 * h * 0.5
                x1 = x0 + side * ln
                y1 = y0 + a0 * ln * 0.8
                pygame.draw.line(surf, theme.alpha_color((96, 52, 124), 150),
                                 (x0, y0), (x1, y1), 1)
                # 分叉
                if k % 3 == 0:
                    pygame.draw.line(surf, theme.alpha_color((120, 70, 150), 110),
                                     (x1, y1), (x1 + side * ln * 0.45,
                                                y1 + a0 * ln * 0.5 + 4), 1)

        # 裂口本体：深空 -> 内缘冷光
        poly = top + bot[::-1]
        pygame.draw.polygon(surf, (7, 4, 10), poly)
        inner = [(x * 0.82 + cx * 0.18, y * 0.82 + cy * 0.18) for x, y in poly]
        pygame.draw.polygon(surf, theme.alpha_color((44, 18, 62), 210), inner)

        # 口沿：暗紫描边 + 亮紫内缘 + 顶部高光
        pygame.draw.lines(surf, (58, 24, 76), False, top, 3)
        pygame.draw.lines(surf, (58, 24, 76), False, bot, 3)
        pygame.draw.lines(surf, theme.alpha_color((176, 118, 220), 220), False,
                          [(p[0], p[1] + 1) for p in top], 1)
        pygame.draw.lines(surf, theme.alpha_color((150, 96, 200), 170), False,
                          [(p[0], p[1] - 1) for p in bot], 1)

        # 裂缝里透出的能量脉动
        if ratio > 0.3:
            k = (0.5 + 0.5 * math.sin(t * 6.5)) * ratio
            theme.glow_circle(surf, (cx, cy), int(w * 0.22), (232, 186, 255),
                              0.10 + 0.18 * k, 2)

        # 边缘碎屑：小石块往下掉
        if ratio > 0.35:
            rr2 = random.Random(int(cx) * 17 + 3)
            for k in range(7):
                ph = (t * (0.9 + rr2.random() * 0.7) + rr2.random()) % 1.0
                dx = rr2.uniform(-w * 0.45, w * 0.45)
                dy = cy + ph * (40 + 60 * ratio)
                a = int(200 * (1.0 - ph))
                if a > 10:
                    s2 = 1 + int(2 * (1.0 - ph))
                    pygame.draw.rect(surf, (78, 60, 88, a),
                                     (int(cx + dx), int(dy), s2, s2))

    def _draw_fall_rocks(self, surf, cam_x, cam_y, t, st):
        for r in st.get("fall_rocks", []):
            try:
                state = r["state"]
                if state == "idle":
                    continue
                rx = r["x"] - cam_x
                ry = r["y"] - cam_y
                land_y = float(r.get("land_y", 19 * TILE)) - cam_y
                # 裂缝固定在"天空"：夹在 HUD 之下、落点之上的一段区域，
                # 24 会被血条卡片压住，72 才开始露出来
                # 裂缝要避开顶部 HUD 和消息横幅（72 正好被横幅压住，
                # 玩家会以为"落石没了"），能往下就往下放。
                _lo = 124.0
                _hi = max(_lo, land_y - 150.0)
                crack_y = min(max(float(r.get("y0", 5 * TILE)) - cam_y, _lo), _hi)

                # 落点危险光柱：从裂缝一直拉到地面。
                # 石头是从画面外掉下来的，没有这道光柱玩家根本看不到"上面要砸了"。
                if state in ("open", "fall"):
                    self._draw_danger_beam(surf, rx, crack_y, land_y, t)
                if state == "open":
                    ratio = 1.0 - max(0.0, float(r.get("open_t", 0.0))) / 0.55
                    ratio = max(0.0, min(1.0, ratio))
                    self._draw_sky_crack(surf, rx, crack_y, t, ratio)
                    # 石头要明显小于洞口，才像"塞在裂缝里"；比洞口大就变成浮在外面
                    _ch = 8.0 + 36.0 * ratio
                    drop = _ch * 0.34
                    pts = self._island_rock_poly(rx, crack_y + drop, int(r["x"]), 0.62)
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

                # 坠落拖尾
                if state == "fall":
                    for k in (1, 2, 3, 4):
                        ty = ry - k * 16
                        if ty < 0:
                            break
                        a = max(0, 120 - k * 26)
                        if a <= 4:
                            break
                        pygame.draw.circle(surf, theme.alpha_color((150, 140, 150), a),
                                           (int(rx), int(ty)), max(2, 9 - k * 2))

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
                    pygame.draw.line(surf, (255, 220, 160), (rx, ry - 20), (rx, ry - 34), 2)
            except Exception:
                pass

    # ==================================================================
    # 平台 / 机关
    # ==================================================================
    def _wood(self, surf, rect, cam_x, cam_y):
        r = pygame.Rect(rect[0] - cam_x, rect[1] - cam_y, rect[2], rect[3])
        pygame.draw.rect(surf, (140, 96, 56), r)
        pygame.draw.rect(surf, (108, 70, 40), (r.x, r.y, r.w, 3))
        for x in range(r.x + 4, r.right, 12):
            pygame.draw.line(surf, (120, 78, 46), (x, r.y + 3), (x, r.bottom - 1), 1)
        pygame.draw.rect(surf, (206, 168, 112), (r.x, r.y, r.w, 2))
        pygame.draw.rect(surf, (70, 46, 28), r, 1)

    def _draw_spike_platform(self, surf, cam_x, cam_y, st):
        sp = st.get("spike_platform")
        if not sp:
            return
        sx = int(sp["x"]) - cam_x
        sy = int(sp["y"]) - cam_y
        w = core.SPIKE_PAD_W
        # 按区域材质给踏刺配色，避免熔炉区出现"冰柱"
        _pc = int(sp["x"]) // TILE
        if _pc >= core.FORGE_LEFT:
            _b, _e, _s = (134, 112, 98), (52, 40, 34), (255, 176, 96)
        elif _pc >= 44:
            _b, _e, _s = (158, 140, 122), (72, 60, 50), (224, 204, 176)
        else:
            _b, _e, _s = (198, 206, 220), (108, 116, 132), (236, 242, 252)
        # 刀刺
        n = 7
        for i in range(n):
            x0 = sx + w * i / n + 5
            x1 = sx + w * (i + 1) / n - 5
            mid = (x0 + x1) / 2
            pygame.draw.polygon(surf, _b,
                                [(x0, sy), (x1, sy), (mid, sy + core.SPIKE_H)])
            pygame.draw.polygon(surf, _e,
                                [(x0, sy), (x1, sy), (mid, sy + core.SPIKE_H)], 1)
            pygame.draw.line(surf, _s, (mid - 2, sy + 4), (mid, sy + core.SPIKE_H - 4), 1)
        if sp.get("bloody"):
            for i in range(6):
                bx = sx + (i * 23) % w
                pygame.draw.polygon(surf, (170, 22, 22),
                                    [(bx - 3, sy + 16), (bx + 3, sy + 16), (bx, sy + 30)])
        self._wood(surf, (sp["x"], sp["y"] - core.SPIKE_PAD_H, w, core.SPIKE_PAD_H), cam_x, cam_y)
        # 顶部可站立提示
        pygame.draw.rect(surf, theme.alpha_color((255, 240, 140), 180),
                         (sx - 1, sy - core.SPIKE_PAD_H - 1, w + 2, 2))

    def _draw_moving_plates(self, surf, cam_x, cam_y, st):
        for mp in st.get("m_plates", []):
            try:
                x = int(mp["x"]) - cam_x
                y = int(mp["y"]) - cam_y
                w = core.M_PAD_W
                self._wood(surf, (mp["x"], mp["y"] - core.M_PAD_H, w, core.M_PAD_H), cam_x, cam_y)
                pygame.draw.rect(surf, theme.alpha_color((90, 240, 220), 190),
                                 (x - 1, y - core.M_PAD_H - 1, w + 2, 2))
                # 底部悬挂微光
                theme.glow_circle(surf, (x + w // 2, y), 10, (80, 220, 220), 0.5, 2)
            except Exception:
                pass

    def _draw_pads(self, surf, cam_x, cam_y, t, st):
        for pd in st.get("pads", []):
            x = pd["x"] - cam_x
            y = pd["y"] - cam_y
            img = assets.get("pad")
            surf.blit(img, (x, y))
            # 弹力光晕
            k = 0.5 + 0.5 * math.sin(t * 6)
            pygame.draw.rect(surf, theme.alpha_color((120, 220, 255), int(120 + 80 * k)),
                             (x, y - 2, TILE, 2))
            left = max(0.0, pd["t"])
            if left < 3.0:
                a = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(t * 14))
                theme.text(surf, "%d" % int(math.ceil(left)), (x + TILE // 2, y - 14), "small",
                           theme.alpha_color((255, 220, 120), int(255 * a)), align="center")

    # ==================================================================
    # 交互物
    # ==================================================================
    def _draw_checkpoints(self, surf, cam_x, cam_y, t, st):
        for cp in st.get("checkpoints", []):
            x = cp["x"] - cam_x
            ground = cp.get("gy", 19 * TILE) - cam_y
            active = cp["active"]
            # 石座
            pygame.draw.rect(surf, (44, 46, 60), (x - 16, ground - 8, 32, 8), border_radius=2)
            pygame.draw.rect(surf, (66, 70, 90), (x - 16, ground - 8, 32, 3))
            # 立柱
            pygame.draw.rect(surf, (58, 60, 76), (x - 7, ground - 56, 14, 50))
            pygame.draw.rect(surf, (86, 90, 112), (x - 7, ground - 56, 14, 3))
            pygame.draw.rect(surf, (38, 40, 52), (x - 7, ground - 56, 3, 50))
            # 顶部灯
            col = (255, 208, 120) if active else (96, 100, 124)
            if active:
                theme.glow_circle(surf, (x, ground - 62), 22 + int(4 * math.sin(t * 3)), col, 0.9, 4)
            pygame.draw.circle(surf, col, (x, ground - 62), 6)
            pygame.draw.circle(surf, theme.shade(col, 0.4), (x - 2, ground - 64), 2)
            if cp.get("flash", 0) > 0:
                r = int(40 + 60 * (1.2 - cp["flash"]))
                s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(s, (255, 230, 160, int(120 * cp["flash"])), (r, r), r, 3)
                surf.blit(s, (x - r, ground - 60 - r))

    def _draw_chests(self, surf, cam_x, cam_y, t, st):
        for ch in st.get("chests", []):
            x = ch["x"] - cam_x
            ground = int(ch.get("gy", 19 * TILE)) - cam_y
            if ch["opened"]:
                pygame.draw.rect(surf, (78, 56, 34), (x - 15, ground - 16, 30, 16), border_radius=2)
                pygame.draw.polygon(surf, (58, 40, 24),
                                    [(x - 15, ground - 16), (x - 13, ground - 26), (x + 13, ground - 26),
                                     (x + 15, ground - 16)])
                pygame.draw.rect(surf, (30, 22, 14), (x - 12, ground - 14, 24, 5))
            else:
                bob = math.sin(t * 2.4) * 1.5
                theme.glow_circle(surf, (x, ground - 12 + bob), 24, (255, 200, 100), 0.35, 3)
                pygame.draw.rect(surf, (122, 84, 46), (x - 15, ground - 17 + bob, 30, 17), border_radius=2)
                pygame.draw.rect(surf, (86, 58, 32), (x - 15, ground - 17 + bob, 30, 4))
                pygame.draw.rect(surf, (188, 142, 82), (x - 2, ground - 12 + bob, 4, 8))
                pygame.draw.rect(surf, (232, 194, 104), (x - 2, ground - 20 + bob, 4, 5))
                pygame.draw.rect(surf, (60, 40, 24), (x - 15, ground - 17 + bob, 30, 17), 1, border_radius=2)

    # ==================================================================
    # 传送门
    # ==================================================================
    def _portal_ring(self, size=160):
        """预渲染符文环（预乘色 + 黑底，专供 BLEND_RGB_ADD 叠加）。

        注意不能用 BLEND_RGBA_ADD：pygame 的 RGBA_ADD 会把 RGB **整份**加上去、
        完全忽略 alpha，于是半透明的描边会被当成纯白叠加 —— 传送门内芯
        会糊成一大团死白。
        """
        img = pygame.Surface((size, size))
        img.fill((0, 0, 0))
        c = size // 2
        r = c - 7

        def pm(col, a):
            k = a / 255.0
            return (int(col[0] * k), int(col[1] * k), int(col[2] * k))

        pygame.draw.circle(img, pm((255, 236, 190), 120), (c, c), r, 1)
        pygame.draw.circle(img, pm((255, 206, 140), 60), (c, c), r - 6, 1)
        n = 24
        for i in range(n):
            a = i * 2 * math.pi / n
            inner = r - (16 if i % 3 == 0 else 10)
            x1 = c + math.cos(a) * (r - 3)
            y1 = c + math.sin(a) * (r - 3)
            x2 = c + math.cos(a) * inner
            y2 = c + math.sin(a) * inner
            pygame.draw.line(img, pm((255, 246, 214), 185), (x1, y1), (x2, y2), 2)
        for i in range(4):
            a = i * math.pi / 2 + math.pi / 4
            pygame.draw.circle(img, pm((255, 250, 228), 235),
                               (int(c + math.cos(a) * (r - 20)),
                                int(c + math.sin(a) * (r - 20))), 3)
        return img

    def _draw_portal(self, surf, cam_x, cam_y, t, st):
        """祭坛传送门：石拱 + 三层反向旋转符文环 + 内旋粒子流 + 地面光池。"""
        px = core.PORTAL_RECT[0] - cam_x
        if px > surf.get_width() + 300 or px < -360:
            return
        active = st.get("portal")
        base_y = 15 * TILE - cam_y
        cx, cy = px + 80, base_y - 66
        wpx = core.PORTAL_RECT[2]

        # ---------- 祭坛基座 ----------
        pygame.draw.rect(surf, (40, 38, 48), (px - 22, base_y - 26, wpx + 44, 26))
        pygame.draw.rect(surf, (68, 64, 78), (px - 22, base_y - 26, wpx + 44, 4))
        pygame.draw.rect(surf, (88, 82, 100), (px - 22, base_y - 26, wpx + 44, 1))
        for i in range(6):
            bx = px - 22 + i * (wpx + 44) // 5
            pygame.draw.line(surf, (30, 28, 36), (bx, base_y - 22), (bx, base_y), 1)
        pygame.draw.rect(surf, (56, 52, 64), (px + 14, base_y - 34, wpx - 28, 9))
        pygame.draw.rect(surf, (94, 88, 106), (px + 14, base_y - 34, wpx - 28, 2))

        # 祭坛缝隙里的辉光（激活后整条缝亮起来）
        _seam = (255, 196, 120) if active else (128, 104, 168)
        for i in range(6):
            bx = px - 22 + i * (wpx + 44) // 5
            if active:
                theme.glow_circle(surf, (bx, base_y - 6), 9, _seam, 0.28, 2)

        if not active:
            # ---------- 封印状态：凿刻石拱 + 旋转封印法阵 ----------
            pulse = 0.5 + 0.5 * math.sin(t * 1.8)
            stone, hi, lo = (58, 54, 66), (92, 86, 100), (34, 32, 42)

            # 地面一圈紫光（封印在渗漏能量）
            theme.glow_circle(surf, (cx, base_y - 8), 76, (104, 76, 168),
                              0.10 + 0.07 * pulse, 3)

            # ---- 立柱：横向砌石 + 竖向刻槽 + 岩浆环境光 ----
            for side in (-1, 1):
                x0 = cx + side * 46 - 11
                pygame.draw.rect(surf, stone, (x0, cy - 50, 22, 96))
                for by in range(0, 96, 16):
                    pygame.draw.line(surf, lo, (x0, cy - 50 + by),
                                     (x0 + 21, cy - 50 + by), 1)
                    pygame.draw.line(surf, hi, (x0, cy - 50 + by + 1),
                                     (x0 + 21, cy - 50 + by + 1), 1)
                pygame.draw.line(surf, lo, (x0 + 10, cy - 48), (x0 + 10, cy + 44), 1)
                pygame.draw.rect(surf, lo, (x0 + 19, cy - 50, 3, 96))
                pygame.draw.line(surf, (156, 90, 58), (x0, cy - 46),
                                 (x0, cy + 44), 2)

            # ---- 拱顶：半环带（只画上半圈），两端落在立柱顶上 ----
            _ao, _ai = [], []
            for i in range(13):
                a = math.pi + i * math.pi / 12.0
                _ao.append((cx + math.cos(a) * 58, cy - 50 + math.sin(a) * 26))
                _ai.append((cx + math.cos(a) * 39, cy - 50 + math.sin(a) * 17))
            pygame.draw.polygon(surf, stone, _ao + _ai[::-1])
            pygame.draw.lines(surf, hi, False, _ao, 2)
            pygame.draw.lines(surf, lo, False, _ai, 1)
            for i in range(1, 12, 2):                     # 楔形石接缝
                pygame.draw.line(surf, lo, _ao[i], _ai[i], 1)
            pygame.draw.lines(surf, (160, 92, 60), False,
                              [(p[0], p[1] - 1) for p in _ao[:7]], 1)

            # ---- 内部虚空 ----
            pygame.draw.ellipse(surf, (14, 11, 20), (cx - 38, cy - 56, 76, 92))
            theme.glow_circle(surf, (cx, cy - 8), 46, (86, 58, 140),
                              0.12 + 0.10 * pulse, 2)

            # ---- 封印法阵：外圈符文环 + 内六芒 + 中心符核 ----
            if self._rune_ring is None:
                self._rune_ring = self._portal_ring(160)
            try:
                ring = pygame.transform.rotozoom(self._rune_ring, -t * 12.0, 0.42)
                ring = pygame.transform.smoothscale(
                    ring, (int(ring.get_width() * 0.92),
                           int(ring.get_height() * 1.10)))
                ring.fill((150, 116, 214), special_flags=pygame.BLEND_RGB_MULT)
                surf.blit(ring, ring.get_rect(center=(cx, cy - 8)),
                          special_flags=pygame.BLEND_RGB_ADD)
            except Exception:
                pass
            for k in range(2):
                ang = t * 0.5 + k * math.pi / 3
                pts = []
                for i in range(3):
                    a = ang + i * 2 * math.pi / 3
                    pts.append((cx + math.cos(a) * 26, cy - 8 + math.sin(a) * 30))
                pygame.draw.polygon(surf, theme.alpha_color((138, 104, 206),
                                                            110 + int(50 * pulse)),
                                    pts, 1)
            theme.glow_circle(surf, (cx, cy - 8), 13, (196, 158, 255),
                              0.30 + 0.22 * pulse, 2)
            pygame.draw.circle(surf, theme.alpha_color((226, 206, 255),
                                                       200 + int(55 * pulse)),
                               (int(cx), int(cy - 8)), 3, 1)

            # ---- 环绕封印符点 ----
            for i in range(6):
                a = t * 0.7 + i * 1.047
                rx = cx + math.cos(a) * 30
                ry = cy - 8 + math.sin(a * 1.3) * 34
                al = 90 + int(80 * (0.5 + 0.5 * math.sin(t * 2.2 + i)))
                pygame.draw.circle(surf, theme.alpha_color((168, 138, 232), al),
                                   (int(rx), int(ry)), 2)

            # ---- 拱顶垂下的锁链 ----
            for side in (-1, 1):
                for k in range(2):
                    x0 = cx + side * (20 + k * 16)
                    y0 = cy - 58
                    for j in range(4):
                        pygame.draw.circle(surf, (72, 66, 84),
                                           (int(x0), int(y0 + j * 7)), 2, 1)
            theme.text(surf, "封印中", (cx, cy - 96), "small", (152, 142, 186), align="center")
            return

        # ---------- 激活状态 ----------
        breath = 0.5 + 0.5 * math.sin(t * 1.35)
        # 1) 地面光池
        theme.glow_circle(surf, (cx, base_y - 6), 96, (255, 186, 110), 0.22 + 0.06 * breath, 3)
        theme.glow_circle(surf, (cx, base_y - 6), 58, (255, 224, 170), 0.24, 2)
        # 2) 大范围外辉（三层不同半径，形成柔和的衰减）
        theme.glow_circle(surf, (cx, cy), 138, (255, 150, 80), 0.10 + 0.035 * breath, 3)
        theme.glow_circle(surf, (cx, cy), 96, (255, 176, 110), 0.09, 3)

        # 3) 石制门框：外框 + 内发光边
        pygame.draw.ellipse(surf, (62, 56, 72), (cx - 60, cy - 74, 120, 148), 12)
        pygame.draw.ellipse(surf, (104, 96, 116), (cx - 60, cy - 74, 120, 148), 2)
        pygame.draw.ellipse(surf, (168, 150, 180), (cx - 48, cy - 60, 96, 122), 1)
        for i in range(10):
            a = i * math.pi * 2 / 10 + t * 0.22
            bx = cx + math.cos(a) * 60
            by = cy + math.sin(a) * 74
            theme.glow_circle(surf, (bx, by), 5, (255, 220, 160), 0.45, 2)

        # 4) 内旋粒子流：黄金角螺旋，越靠近中心越亮
        for i in range(26):
            ph = (t * 0.42 + i / 26.0) % 1.0
            ang = i * 2.3999 + t * 1.55
            rad = 1.0 - ph
            ppx = cx + math.cos(ang) * 62 * rad
            ppy = cy + math.sin(ang) * 78 * rad
            inten = 0.16 + 0.52 * (ph ** 1.4)
            col = theme.mix((150, 224, 255), (255, 232, 186), ph)
            theme.glow_circle(surf, (ppx, ppy), 4 + int(4 * ph), col, inten, 2)

        # 5) 三层反向旋转的符文环（越内越快，营造纵深）
        if self._rune_ring is None:
            self._rune_ring = self._portal_ring(160)
        rings = ((1.00, t * 22.0, (255, 214, 150)),
                 (0.78, -t * 34.0, (140, 208, 255)),
                 (0.54, t * 52.0, (255, 158, 226)))
        for scale, ang, col in rings:
            try:
                ring = pygame.transform.rotozoom(self._rune_ring, ang, scale)
                ring = pygame.transform.smoothscale(
                    ring, (int(ring.get_width() * 0.86),
                           int(ring.get_height() * 1.06)))
                # 先按环色调乘一遍，三圈才有颜色区分（否则叠出来全是白的）
                ring.fill((col[0], col[1], col[2]),
                          special_flags=pygame.BLEND_RGB_MULT)
                surf.blit(ring, ring.get_rect(center=(cx, cy)),
                          special_flags=pygame.BLEND_RGB_ADD)
            except Exception:
                pass

        # 6) 内芯：椭圆柔光（不是矩形！否则会变成一块白板）
        # 内芯压得很低：它下面还叠着三层辉光 + 符文环，再往上加就过曝成
        # 一团纯白，站在里面的人也会被吃掉。
        core_s = pygame.Surface((76, 108))
        core_s.fill((0, 0, 0))
        for i in range(108):
            f = 1.0 - abs(i - 54) / 54.0
            half = int(37 * (f ** 0.55))
            aa = int((70 + 26 * breath) * (f ** 1.5))
            if half > 0 and aa > 0:
                pygame.draw.line(core_s, (aa, int(aa * 0.84), int(aa * 0.62)),
                                 (38 - half, i), (38 + half, i))
        surf.blit(core_s, (cx - 38, cy - 54), special_flags=pygame.BLEND_RGB_ADD)
        theme.glow_circle(surf, (cx, cy), 30, (255, 210, 150), 0.07 + 0.03 * breath, 2)

        # 7) 上升光尘
        for i in range(14):
            ph = (t * 0.55 + i * 0.071) % 1.0
            mx = cx + math.sin(i * 2.1 + t * 0.9) * (16 + 10 * ph)
            my = base_y - 4 - ph * 118
            a = int(150 * (1.0 - ph) ** 1.3)
            if a > 6:
                pygame.draw.circle(surf, (255, 238, 200, a), (int(mx), int(my)),
                                   1 + int(2 * (1.0 - ph)))

        # 8) 环绕光点
        for i in range(6):
            a = -t * 1.9 + i * 1.047
            sx = cx + math.cos(a) * 66
            sy = cy + math.sin(a) * 82
            theme.glow_circle(surf, (sx, sy), 8, (255, 240, 196), 0.62, 3)

    # ==================================================================
    # 实体
    # ==================================================================
    def _draw_tower(self, surf, cam_x, cam_y, t, st):
        """瞭望塔：烈焰机关火柱 + 第三层武器核心。"""
        try:
            # 烈焰机关
            for v in st.get("vents", []):
                x = int(v["x"]) - cam_x
                y = int(v["y"]) - cam_y
                if x < -60 or x > surf.get_width() + 60:
                    continue
                # 地面格栅
                pygame.draw.rect(surf, (58, 50, 48), (x - 18, y - 5, 36, 7), border_radius=2)
                for i in range(3):
                    pygame.draw.line(surf, (86, 74, 66), (x - 14 + i * 12, y - 4),
                                     (x - 14 + i * 12, y + 1), 2)
                if v.get("on"):
                    h = int(core.VENT_HEIGHT)
                    flick = 0.82 + 0.18 * math.sin(t * 27 + x * 0.7)
                    # 外焰：橙红，向上收窄
                    for k in range(9):
                        fr = k / 9.0
                        w = int((19 - 11 * fr) * flick)
                        hh = int(h * (1.0 - fr * 0.14))
                        a = int(96 * (1.0 - fr * 0.72) * flick)
                        pygame.draw.ellipse(surf, theme.alpha_color((236, 92, 38), a),
                                            (x - w, y - 4 - int(hh * fr) - 24, w * 2,
                                             int(hh / 3.2) + 26))
                    # 内焰：橙黄
                    for k in range(7):
                        fr = k / 7.0
                        w = int((11 - 7 * fr) * flick)
                        hh = int(h * 0.82)
                        a = int(120 * (1.0 - fr * 0.7) * flick)
                        pygame.draw.ellipse(surf, theme.alpha_color((255, 176, 70), a),
                                            (x - w, y - 6 - int(hh * fr) - 12, w * 2,
                                             int(hh / 5.0) + 16))
                    # 焰芯：白热
                    pygame.draw.ellipse(surf, theme.alpha_color((255, 238, 190), 235),
                                        (x - 7, y - 26, 14, 26))
                    # 火星
                    for k in range(4):
                        fy = (t * 1.3 + k * 0.27) % 1.0
                        fx = x + math.sin(t * 9 + k * 2.1) * (4 + 6 * fy)
                        pygame.draw.circle(surf, theme.alpha_color((255, 210, 130), int(200 * (1 - fy))),
                                           (int(fx), int(y - 10 - fy * h * 0.9)), 1)
            # 共鸣门：门框 + 能量膜（开着时只剩门框）
            gx = int(core.RUNE_GATE_COL * core.TILE + 16) - cam_x
            gy0 = int(core.RUNE_GATE_ROWS[0] * core.TILE) - cam_y
            gy1 = int((core.RUNE_GATE_ROWS[1] + 1) * core.TILE) - cam_y
            if -80 < gx < surf.get_width() + 80:
                pygame.draw.rect(surf, (72, 64, 56), (gx - 19, gy0 - 7, 38, 8), border_radius=2)
                pygame.draw.rect(surf, (96, 86, 74), (gx - 19, gy0 - 7, 38, 3), border_radius=2)
                pygame.draw.rect(surf, (72, 64, 56), (gx - 19, gy1 - 1, 38, 8), border_radius=2)
                if not st.get("rune_open", False):
                    h = max(1, gy1 - gy0)
                    film = pygame.Surface((28, h), pygame.SRCALPHA)
                    pulse = 0.62 + 0.38 * math.sin(t * 5.2)
                    for yy in range(h):
                        f = 1.0 - abs(yy / float(h - 1) - 0.5) * 2.0
                        a = int((48 + 92 * f) * pulse)
                        pygame.draw.line(film, (128, 226, 255, a), (0, yy), (28, yy))
                    surf.blit(film, (gx - 14, gy0))
                    for k in range(3):
                        yy = gy0 + int((h * ((t * 1.6 + k / 3.0) % 1.0)))
                        pygame.draw.line(surf, theme.alpha_color((210, 250, 255), 180),
                                         (gx - 13, yy), (gx + 13, yy), 1)

            # 守门符文：地面法阵（椭圆透视），踩住时亮起加速旋转
            rx2 = int(core.RUNE_COL * core.TILE + 16) - cam_x
            ry2 = int(11 * core.TILE) - cam_y
            if -70 < rx2 < surf.get_width() + 70:
                on = bool(st.get("rune_open", False))
                R = 21
                pygame.draw.ellipse(surf, theme.alpha_color((110, 210, 250), 165 if on else 95),
                                    (rx2 - R, ry2 - int(R * 0.42), R * 2, int(R * 0.84)), 2)
                pygame.draw.ellipse(surf, theme.alpha_color((160, 236, 255), 130 if on else 70),
                                    (rx2 - int(R * 0.62), ry2 - int(R * 0.26),
                                     int(R * 1.24), int(R * 0.52)), 1)
                for k in range(6):
                    ang = t * (2.6 if on else 0.7) + k * math.pi / 3.0
                    px = rx2 + math.cos(ang) * (R - 4)
                    py = ry2 + math.sin(ang) * (R - 4) * 0.42
                    pygame.draw.circle(surf, (215, 248, 255) if on else (130, 186, 210),
                                       (int(px), int(py)), 2 if on else 1)
                if on:
                    theme.glow_circle(surf, (rx2, ry2), 26, (140, 230, 255), 0.45, 2)

            # 瞭望塔引导光柱：拿武器前，塔顶向上投一道淡金光束
            if not st.get("weapon_taken", False):
                tx = int((core.TOWER_WEAPON_X - cam_x))
                ty = int((core.TOWER_F3_Y - cam_y))
                if -40 < tx < surf.get_width() + 40 and ty > 8:
                    bh = max(1, min(int(ty) - 6, 300))
                    beam = pygame.Surface((52, bh), pygame.SRCALPHA)
                    for yy in range(bh):
                        f = 1.0 - yy / float(bh)              # 越往上越淡
                        wob = 1.0 + 0.12 * math.sin(t * 1.7 + yy * 0.06)
                        half = int((5 + 17 * f) * wob)
                        a = int(34 * (f ** 1.25))
                        pygame.draw.rect(beam, (255, 198, 124, a), (26 - half, yy, half * 2, 1))
                    surf.blit(beam, (tx - 26, ty - bh))
                    theme.glow_circle(surf, (tx, ty - 10), 22, (255, 200, 120), 0.4, 2)
            # 武器核心
            if not st.get("weapon_taken", False):
                wx = int(core.TOWER_WEAPON_X) - cam_x
                wy = int(core.TOWER_F3_Y) - cam_y - 26
                if -40 < wx < surf.get_width() + 40:
                    bob = math.sin(t * 2.2) * 4
                    theme.glow_circle(surf, (wx, int(wy + bob)), 34, (255, 170, 70), 0.55, 3)
                    pygame.draw.circle(surf, (255, 196, 110), (wx, int(wy + bob)), 9)
                    pygame.draw.circle(surf, (255, 240, 200), (wx, int(wy + bob)), 5)
                    for k in range(3):
                        a = t * 1.6 + k * 2.1
                        pygame.draw.circle(surf, theme.alpha_color((255, 190, 110), 150),
                                           (int(wx + math.cos(a) * 20), int(wy + bob + math.sin(a) * 8)),
                                           2)
                    theme.text(surf, "烈焰核心", (wx, int(wy + bob + 26)), "tiny",
                               theme.alpha_color((255, 210, 140), 220), align="center")
        except Exception as e:
            # 注意：不能写 getattr(_draw_tower, ...) —— 方法体内的这个名字不是局部变量，
            # 会抛 NameError，把"警告一次"变成"每帧整段渲染中断"。
            if not getattr(self, "_tower_warned", False):
                self._tower_warned = True
                print("[塔楼绘制异常] %r" % (e,))

    def _draw_vines(self, surf, cam_x, cam_y, t, st):
        """藤蔓滑索：波动主干 + 交错叶片 + 端点卷须；挂住时整条亮起并流光。"""
        try:
            holding = None
            for p in st.get("players", {}).values():
                if p.get("vine", -1) >= 0:
                    holding = p.get("vine")
            _vw = surf.get_width()
            for i, v in enumerate(core.VINES):
                x0 = float(v[0]) - cam_x
                y0 = float(v[1]) - cam_y
                x1 = float(v[2]) - cam_x
                y1 = float(v[3]) - cam_y
                if max(x0, x1) < -80 or min(x0, x1) > _vw + 80:
                    continue
                hot = (holding == i)
                N = 16
                pts = []
                for k in range(N + 1):
                    tt = k / float(N)
                    px = x0 + (x1 - x0) * tt + math.sin(tt * 5.2 + t * 1.1 + i * 1.7) * 2.6
                    py = y0 + (y1 - y0) * tt + math.sin(tt * 4.1 + t * 0.8 + i) * 1.8
                    pts.append((px, py))
                # 主干三层：暗描边 / 本体 / 高光
                # 开局绿意段的藤 = 原版绿藤（挂住时亮绿流光）
                pygame.draw.lines(surf, (32, 48, 30), False, pts, 5)
                pygame.draw.lines(surf, (74, 112, 60) if not hot else (110, 158, 78), False, pts, 3)
                pygame.draw.lines(surf, (120, 166, 88) if not hot else (186, 232, 130), False, pts, 1)

                # 叶片：沿绳交替左右
                ang_base = math.atan2(y1 - y0, x1 - x0)
                for k in range(1, N):
                    tt = k / float(N)
                    px, py = pts[k]
                    side = 1.0 if (k % 2) else -1.0
                    sway = math.sin(t * 1.9 + k * 0.7 + i) * 0.16
                    ang = ang_base + side * 1.15 + sway
                    L = 11.0 if (k % 3) else 8.5
                    W = 4.6 if (k % 3) else 3.6
                    ca, sa = math.cos(ang), math.sin(ang)
                    tip = (px + ca * L, py + sa * L)
                    m1 = (px + ca * L * 0.42 - sa * W, py + sa * L * 0.42 + ca * W)
                    m2 = (px + ca * L * 0.42 + sa * W, py + sa * L * 0.42 - ca * W)
                    leaf = [(px, py), m1, tip, m2]
                    pygame.draw.polygon(surf, (52, 82, 44), leaf)
                    inner = [(px + ca * 1.2, py + sa * 1.2),
                             ((m1[0] + tip[0]) * 0.5 - sa * 1.2, (m1[1] + tip[1]) * 0.5 + ca * 1.2),
                             (tip[0] - ca * 1.2, tip[1] - sa * 1.2),
                             ((m2[0] + tip[0]) * 0.5 + sa * 1.2, (m2[1] + tip[1]) * 0.5 - ca * 1.2)]
                    pygame.draw.polygon(surf, (108, 158, 76) if not hot else (150, 206, 104), inner)

                # 端点：上端锚环，下端卷须
                ax, ay = pts[0]
                pygame.draw.circle(surf, (58, 74, 52), (int(ax), int(ay)), 6, 3)
                pygame.draw.circle(surf, (132, 172, 96), (int(ax), int(ay)), 2)
                ex, ey = pts[-1]
                for c in range(3):
                    ca = ang_base + 1.6 + c * 0.9 + math.sin(t * 2 + c) * 0.2
                    r0 = 4 + c * 3.4
                    pygame.draw.arc(surf, (86, 126, 66),
                                    (int(ex - r0), int(ey - r0), int(r0 * 2), int(r0 * 2)),
                                    ca, ca + 1.7, 1)

                # 挂住时：沿绳流动的光点
                if hot:
                    for m in range(3):
                        ft = ((t * 0.85 + m / 3.0) % 1.0)
                        idx = ft * N
                        k0 = int(idx)
                        k1 = min(N, k0 + 1)
                        fr = idx - k0
                        lx = pts[k0][0] + (pts[k1][0] - pts[k0][0]) * fr
                        ly = pts[k0][1] + (pts[k1][1] - pts[k0][1]) * fr
                        theme.glow_circle(surf, (lx, ly), 9, (170, 240, 120), 0.5, 2)
                        pygame.draw.circle(surf, (226, 255, 190), (int(lx), int(ly)), 2)
        except Exception as e:
            if not getattr(self, "_vines_warned", False):
                self._vines_warned = True
                print("[藤蔓绘制异常] %r" % (e,))

    def _draw_arrows(self, surf, cam_x, cam_y, t, st):
        for a in st.get("arrows", []):
            x = int(a["x"]) - cam_x
            y = int(a["y"]) - cam_y
            ang = a["ang"]
            # 拖尾
            for i in range(4):
                k = i / 4.0
                tx = x - math.cos(ang) * (10 + i * 7)
                ty = y - math.sin(ang) * (10 + i * 7)
                pygame.draw.circle(surf, theme.alpha_color((255, 226, 160), int(90 * (1 - k))),
                                   (int(tx), int(ty)), max(1, 3 - i))
            img = assets.get("arrow")
            rot = assets.rot_center(img, -math.degrees(ang))
            surf.blit(rot, rot.get_rect(center=(x, y)))

    def _draw_corpses(self, surf, cam_x, cam_y, st):
        """死亡残影：淡出 + 微微上浮，比"瞬间消失"更有打击反馈。"""
        for c in st.get("corpses", []):
            try:
                k = c["kind"]
                p = min(1.0, c["t"] / max(0.01, c["max"]))
                img = sprites.get_monster(k, 0)
                if c.get("dir", 1) < 0:
                    img = pygame.transform.flip(img, True, False)
                img = img.copy()
                img.set_alpha(int(255 * (1.0 - p) ** 1.4))
                yy = c["y"] - cam_y - int(12 * p)
                if k in ("ground", "boss", "tree"):
                    theme.soft_shadow(surf, c["x"] - cam_x, c["y"] - cam_y, 34, 8,
                                      int(90 * (1.0 - p)))
                surf.blit(img, img.get_rect(midbottom=(c["x"] - cam_x, yy)))
            except Exception:
                pass

    def _draw_fireballs(self, surf, cam_x, cam_y, t, st):
        for f in st.get("fireballs", []):
            try:
                x = int(f["x"]) - cam_x
                y = int(f["y"]) - cam_y
                r = int(f.get("r", 7))
                theme.glow_circle(surf, (x, y), r * 4, (255, 120, 50), 0.55, 3)
                pygame.draw.circle(surf, (255, 168, 80), (x, y), r)
                pygame.draw.circle(surf, (255, 236, 190), (x - 1, y - 1), max(2, r // 2))
                # 拖尾
                for k in (1, 2, 3):
                    pygame.draw.circle(surf, theme.alpha_color((255, 120, 60), 90 - k * 25),
                                       (x - k * 5, y + int(math.sin(t * 12 + k) * 2)),
                                       max(1, r - k * 2))
            except Exception:
                pass

    def _draw_eggs(self, surf, cam_x, cam_y, t, st):
        """树精扔出的蛋：淡紫危险辉光 + 白色蛋体 + 拖尾。"""
        for e in st.get("eggs", []):
            try:
                x = int(e["x"]) - cam_x
                y = int(e["y"]) - cam_y
                trail = e.get("trail", [])
                for i, (tx, ty) in enumerate(trail):
                    a = int(120 * (i + 1) / max(1, len(trail)))
                    pygame.draw.circle(surf, theme.alpha_color((236, 232, 214), a),
                                       (int(tx) - cam_x, int(ty) - cam_y),
                                       max(1, 3 - i // 3))
                r = 10
                theme.glow_circle(surf, (x, y), r * 2 + 4, (150, 90, 220), 0.30, 2)
                pygame.draw.ellipse(surf, (24, 18, 26),
                                    (x - r - 1, y - r - 2, r * 2 + 2, r * 2 + 4))
                pygame.draw.ellipse(surf, (214, 208, 186),
                                    (x - r, y - r - 1, r * 2, r * 2 + 2))
                pygame.draw.ellipse(surf, (244, 240, 220),
                                    (x - r + 2, y - r + 1, r * 2 - 6, r * 2 - 6))
                pygame.draw.ellipse(surf, (255, 255, 250),
                                    (x - r + 4, y - r + 2, 4, 5))
                sp = float(e.get("spin", 0.0))
                pygame.draw.circle(surf, (255, 255, 255),
                                   (x + int(math.cos(sp) * 3), y - 3), 2)
            except Exception:
                pass

    def _draw_explosions(self, surf, cam_x, cam_y, t, st):
        """紫色爆炸：白核 -> 品红 -> 深紫的层次球 + 冲击环 + 放射碎片 + 上升余烬。"""
        for ex in st.get("explosions", []):
            try:
                x = int(ex["x"]) - cam_x
                y = int(ex["y"]) - cam_y
                k = max(0.0, min(1.0, ex["t"] / max(0.01, ex["max"])))
                r = int(ex.get("r", 44))
                fade = 1.0 - k
                if fade <= 0.01 or r <= 2:
                    continue
                rnd = random.Random(int(ex["x"]) * 31 + int(ex["y"]) * 7)
                # 地面紫色光斑
                theme.glow_circle(surf, (x, y), int(r * 1.5), (120, 50, 200),
                                  0.32 * fade, 3)
                # 外层紫雾（加法混合，发光感）
                d = r * 3
                if d > 0:
                    s = pygame.Surface((d, d), pygame.SRCALPHA)
                    for i in range(6, 0, -1):
                        rr = int(r * i / 6.0)
                        a = int(74 * fade * (1.0 - i / 7.0))
                        if a > 0 and rr > 0:
                            pygame.draw.circle(s, (96, 34, 168, a), (d // 2, d // 2), rr)
                    surf.blit(s, (x - d // 2, y - d // 2),
                              special_flags=pygame.BLEND_RGBA_ADD)
                # 主爆球：深紫 -> 品红 -> 亮紫 -> 白核
                pygame.draw.circle(surf, (58, 16, 108), (x, y), max(1, int(r * 0.92)))
                pygame.draw.circle(surf, (146, 58, 216), (x, y), max(1, int(r * 0.64)))
                pygame.draw.circle(surf, (208, 128, 250), (x, y), max(1, int(r * 0.36)))
                if k < 0.45:
                    pygame.draw.circle(surf, (250, 238, 255), (x, y),
                                       max(1, int(r * 0.17)))
                # 冲击环
                ring_r = int(r * (0.5 + k * 1.15))
                if ring_r > 1:
                    pygame.draw.circle(surf, theme.alpha_color((222, 160, 255),
                                                               int(200 * fade)),
                                       (x, y), ring_r, max(1, int(3 * fade) + 1))
                # 放射碎片
                for _i in range(10):
                    ang = rnd.uniform(0, 6.28)
                    dd = r * (0.4 + k * 1.35) * rnd.uniform(0.7, 1.1)
                    px_ = x + math.cos(ang) * dd
                    py_ = y + math.sin(ang) * dd * 0.8
                    sz = max(1, int(3 * (1 - k)))
                    pygame.draw.circle(surf, (200, 120, 255), (int(px_), int(py_)), sz)
                # 上升余烬
                for _i in range(8):
                    ang = rnd.uniform(-2.6, -0.5)
                    dd = r * (0.3 + k * 0.9)
                    px_ = x + math.cos(ang) * dd
                    py_ = y + math.sin(ang) * dd - k * 42
                    pygame.draw.circle(surf, (240, 200, 255), (int(px_), int(py_)), 1)
            except Exception:
                pass

    def _draw_lava_eruptions(self, surf, cam_x, cam_y, t, st):
        """熔炉守卫的岩浆喷发：预警红圈收缩 -> 岩浆柱喷起 + 溅射。"""
        ER = core.ERUPT_R
        for er in st.get("lava_eruptions", []):
            try:
                x = int(er["x"]) - cam_x
                y = int(er["y"]) - cam_y
                tt = float(er["t"])
                delay = float(er["delay"])
                mx = float(er["max"])
                rnd = random.Random(int(er["x"]) * 17 + 3)
                if tt < delay:
                    # ---- 预警：收缩红圈 + 地面透光 + 上升火星 ----
                    k = tt / max(0.01, delay)
                    rr = int(ER * (1.35 - 0.35 * k))
                    a = int(90 + 120 * k)
                    pygame.draw.ellipse(surf, theme.alpha_color((255, 92, 40), a),
                                        (x - rr, y - int(rr * 0.32), rr * 2,
                                         int(rr * 0.64)), 2)
                    pygame.draw.ellipse(surf, theme.alpha_color((255, 180, 96),
                                                                int(a * 0.6)),
                                        (x - int(rr * 0.6), y - int(rr * 0.2),
                                         int(rr * 1.2), int(rr * 0.4)), 2)
                    theme.glow_circle(surf, (x, y - 4), int(rr * 0.9),
                                      (255, 110, 50), 0.16 + 0.32 * k, 3)
                    for i in range(6):
                        ph = (t * 2.0 + i * 0.4) % 1.0
                        px_ = x + rnd.uniform(-rr * 0.6, rr * 0.6)
                        py_ = y - ph * 30
                        pygame.draw.circle(surf, (255, 170, 70),
                                           (int(px_), int(py_)),
                                           max(1, int(2 * (1 - ph))))
                else:
                    # ---- 喷发：岩浆柱（外橙内亮）+ 底部溅射 ----
                    k = (tt - delay) / max(0.01, mx - delay)      # 0..1
                    fade = 1.0 - k
                    if fade <= 0.01:
                        continue
                    h = int(120 * (1.0 - (1.0 - k) ** 2)) + 18
                    w = int(ER * 0.66 * (1.0 - 0.3 * k))
                    # 柱体外层
                    pygame.draw.polygon(surf, (255, 120, 40),
                                        [(x - w, y), (x + w, y),
                                         (x + int(w * 0.42), y - h),
                                         (x - int(w * 0.42), y - h)])
                    # 内层亮芯
                    pygame.draw.polygon(surf, (255, 236, 176),
                                        [(x - int(w * 0.4), y), (x + int(w * 0.4), y),
                                         (x + int(w * 0.16), y - int(h * 0.72)),
                                         (x - int(w * 0.16), y - int(h * 0.72))])
                    # 底部热光 + 溅射
                    theme.glow_circle(surf, (x, y), int(ER * 1.2),
                                      (255, 120, 40), 0.5 * fade, 3)
                    for i in range(10):
                        ang = rnd.uniform(-2.8, -0.3)
                        dd = rnd.uniform(20, 70) * (0.4 + k)
                        px_ = x + math.cos(ang) * dd
                        py_ = y + math.sin(ang) * dd * 0.5 - (1 - k) * 30
                        pygame.draw.circle(surf, (255, 150, 60),
                                           (int(px_), int(py_)), max(1, int(3 * fade)))
            except Exception:
                pass

    def _draw_breaths(self, surf, cam_x, cam_y, t, st):
        """树精幽蓝火焰：细长白热内核 + 稀疏湍流青蓝火舌 + 蓝色柔光 + 余烬。
        刻意不用紫色（之前紫雾叠加会糊成一坨紫团）。"""
        L = core.BREATH_LEN
        H = core.BREATH_H
        for br in st.get("breaths", []):
            try:
                mx = float(br["x"]) - cam_x
                my = float(br["y"]) - cam_y
                d = 1 if br["dir"] > 0 else -1
                age = float(br["t"])
                mx_t = float(br["max"])
                k = min(1.0, age / 0.10) * min(1.0, (mx_t - age) / 0.22)
                if k <= 0.01:
                    continue
                pad = 44
                fw = int(L) + pad * 2
                fh = int(H) + pad * 2
                ox = pad if d > 0 else fw - pad
                oy = fh * 0.5
                rnd = random.Random(2026)

                # ---- 背景蓝色柔光（只覆盖近口一半，避免远端发白）----
                glow = pygame.Surface((fw, fh), pygame.SRCALPHA)
                for i in range(7):
                    tt = (i / 6.0) * 0.55
                    x = ox + d * L * tt
                    rr = int(14 + 20 * tt)
                    a = int(24 * k)
                    if a > 0:
                        pygame.draw.circle(glow, (50, 140, 255, a),
                                           (int(x), int(oy + tt * tt * 10)), rr)
                surf.blit(glow, (mx - ox, my - oy), special_flags=pygame.BLEND_RGBA_ADD)

                fs = pygame.Surface((fw, fh), pygame.SRCALPHA)

                def tongue(x0, y0, ang, ln, w0, col):
                    """一条尖头火舌（根部有宽度，末端收尖，中段略鼓）。"""
                    ca, sa = math.cos(ang), math.sin(ang)
                    px, py = -sa, ca
                    b1 = (x0 + px * w0, y0 + py * w0)
                    b2 = (x0 - px * w0, y0 - py * w0)
                    m1 = (x0 + ca * ln * 0.5 + px * w0 * 0.95,
                          y0 + sa * ln * 0.5 + py * w0 * 0.95)
                    m2 = (x0 + ca * ln * 0.5 - px * w0 * 0.95,
                          y0 + sa * ln * 0.5 - py * w0 * 0.95)
                    tip = (x0 + ca * ln, y0 + sa * ln)
                    pygame.draw.polygon(fs, col, [b1, m1, tip, m2, b2])

                base = 0.0 if d > 0 else math.pi
                nseg = 4
                # 由外到内分层：深蓝轮廓 -> 蓝 -> 青 -> 白核（内层后画，压在最上）
                bands = [
                    ((26, 64, 150), 1.10, 1.34, 198),
                    ((44, 120, 230), 0.94, 0.98, 210),
                    ((108, 204, 255), 0.70, 0.58, 220),
                    ((236, 250, 255), 0.44, 0.28, 228),
                ]
                for (col, lmul, wmul, abase) in bands:
                    a = int(abase * k)
                    if a <= 2:
                        continue
                    c4 = (col[0], col[1], col[2], a)
                    for i in range(nseg):
                        tt = i / float(nseg - 1)
                        x0 = ox + d * L * (tt * 0.58)
                        y0 = oy + 4 + math.sin(t * 9 + i * 1.1) * (3 + 6 * tt)
                        sway = math.sin(t * 8 + i * 1.3) * 0.09
                        ln = (L * (0.37 - 0.12 * tt) *
                              (0.90 + 0.20 * math.sin(t * 12 + i)))
                        w0 = (7 + 3 * math.sin(t * 10 + i)) * (1.0 - 0.50 * tt)
                        tongue(x0, y0, base + sway, ln * lmul, w0 * wmul, c4)
                        # 分叉：只在中间两段各分出上下两条小舌（克制，不铺满）
                        if i in (1, 2):
                            fx = x0 + math.cos(base) * ln * 0.62
                            fy = y0 + math.sin(base) * ln * 0.62
                            for sgn in (-1, 1):
                                fa = base + sgn * (0.34 + 0.14 * math.sin(t * 6 + i + sgn))
                                fln = ln * (0.48 + 0.14 * math.sin(t * 9 + i + sgn * 2))
                                fw = w0 * 0.40
                                tongue(fx, fy, fa, fln * lmul,
                                       fw * wmul * 1.15, c4)
                surf.blit(fs, (mx - ox, my - oy))
                # ---- 嘴部白热核心 ----
                theme.glow_circle(surf, (int(mx), int(my)), 28,
                                  (120, 205, 255), 0.5 * k, 3)
                theme.glow_circle(surf, (int(mx), int(my)), 11,
                                  (240, 252, 255), 0.72 * k, 2)
                # ---- 飞散余烬 ----
                for i in range(12):
                    tt = (t * 1.6 + i * 0.13) % 1.0
                    fx = mx + d * L * tt
                    fy = my + rnd.uniform(-H * 0.32, H * 0.32) + math.sin(t * 9 + i) * 5
                    pygame.draw.circle(surf, (175, 228, 255),
                                       (int(fx), int(fy)), max(1, int(2 * (1 - tt))))
            except Exception:
                pass

    def _draw_blooms(self, surf, cam_x, cam_y, t, st):
        """树精死亡：附近地面长出草与花，逐渐焕发生机（带风摆 + 生命波纹 + 花瓣）。"""
        for b in st.get("blooms", []):
            try:
                bx = float(b["x"]) - cam_x
                by = float(b["y"]) - cam_y
                age = float(b["t"])
                prog = max(0.0, min(1.0, age / 1.6))
                rnd = random.Random(int(b.get("seed", 7)))
                maxr = 182                     # 收窄，别长到台子外面的空气里
                # 地面绿光（生命感）
                theme.glow_circle(surf, (int(bx), int(by) - 6), int(170 * prog),
                                  (76, 196, 96), 0.22 * prog, 4)
                # 初段：一圈扩散的绿色生命波纹
                if age < 0.9:
                    rr = int(40 + age * 220)
                    a = int(150 * (1.0 - age / 0.9))
                    pygame.draw.ellipse(surf, theme.alpha_color((150, 240, 150), a),
                                        (int(bx - rr), int(by - rr * 0.28),
                                         rr * 2, int(rr * 0.56)), 2)
                # 草簇
                n = 64
                for i in range(n):
                    dd = rnd.uniform(-maxr, maxr)
                    th = rnd.uniform(0.5, 0.92)
                    if prog < th:
                        continue
                    gx = int(bx + dd)
                    gy = int(by)
                    gh = int((prog - th) / max(0.01, 1.0 - th) *
                             rnd.uniform(12, 28)) + 2
                    sway = math.sin(t * 2.0 + i * 0.7) * 2
                    base_col = (44, 118, 52) if rnd.random() < 0.5 else (62, 148, 64)
                    tip_col = (128, 206, 94)
                    for h in range(gh):
                        xx = int(gx + sway * h / max(1, gh))
                        c = base_col if h < gh * 0.6 else tip_col
                        pygame.draw.line(surf, c, (xx, gy - h), (xx, gy - h - 1), 1)
                    # 分叉第二片草叶，增加密度
                    if rnd.random() < 0.55 and gh > 6:
                        sx2 = gx + (2 if rnd.random() < 0.5 else -2)
                        for h in range(int(gh * 0.7)):
                            xx = int(sx2 + sway * h / max(1, gh))
                            pygame.draw.line(surf, base_col, (xx, gy - h), (xx, gy - h - 1), 1)
                    # 花
                    if rnd.random() < 0.34 and gh > 9:
                        fc = rnd.choice([(250, 230, 120), (250, 160, 190),
                                         (206, 182, 250), (255, 255, 255),
                                         (255, 150, 120)])
                        fx = int(gx + sway)
                        fy = gy - gh
                        pygame.draw.circle(surf, fc, (fx, fy), 2)
                        pygame.draw.circle(surf, (250, 220, 90), (fx, fy), 1)
                # 飘起的花瓣 / 叶子
                for i in range(6):
                    ph = (age * 0.5 + i * 0.37) % 1.0
                    px_ = bx + math.sin(age * 1.5 + i * 2.0) * (40 + i * 22)
                    py_ = by - 6 - ph * (70 + i * 12)
                    a = int(200 * (1.0 - ph) * prog)
                    if a > 6:
                        col = (150, 220, 120) if i % 2 else (250, 200, 120)
                        pygame.draw.circle(surf, theme.alpha_color(col, a),
                                           (int(px_), int(py_)), 2)
            except Exception:
                pass

    def _draw_shockwaves(self, surf, cam_x, cam_y, st):
        """Boss 砸地：贴地扩散的冲击弧 + 地面碎裂 + 飞溅碎屑。"""
        for w in st.get("shockwaves", []):
            try:
                x = int(w["x"]) - cam_x
                y = int(w["y"]) - cam_y
                r = int(w["r"])
                if r <= 3:
                    continue
                age = float(w.get("t", 0.0))
                fade = max(0.0, 1.0 - r / 280.0)

                # ---- 地面碎裂：从落点向外辐射的锯齿裂纹 ----
                # 裂纹跟着冲击波一起长，但最多 110px；越往外越淡。
                cr = min(r, 110)
                if cr > 6:
                    rr = random.Random(int(w["x"]) * 7 + 11)
                    for i in range(8):
                        side = -1.0 if i % 2 == 0 else 1.0
                        a0 = rr.uniform(-0.42, 0.42)          # 贴着地面左右铺
                        pts = [(x, y)]
                        seg = cr / 3.0
                        for k in range(1, 4):
                            rr_ = seg * k
                            aa = a0 + rr.uniform(-0.22, 0.22)
                            pts.append((x + side * math.cos(aa) * rr_,
                                        y + math.sin(aa) * rr_ * 0.55))
                        ip = [(int(a), int(b)) for a, b in pts]
                        # 暗裂缝 + 内侧熔光：读起来像"被砸裂、底下透着热"
                        pygame.draw.lines(surf, (22, 16, 18), False, ip, 3)
                        pygame.draw.lines(
                            surf, theme.alpha_color((255, 146, 64), int(160 * fade)),
                            False, ip, 1)
                    # 落点焦痕
                    theme.glow_circle(surf, (x, y), int(26 + 18 * fade),
                                      (255, 128, 52), 0.30 * fade, 2)

                # ---- 冲击弧 ----
                col = theme.alpha_color((255, 170, 90), int(200 * fade))
                pygame.draw.arc(surf, col, (x - r, y - int(r * 0.5), r * 2, r), 0, math.pi, 5)
                pygame.draw.arc(surf, theme.alpha_color((255, 240, 200), int(120 * fade)),
                                (x - r, y - int(r * 0.5), r * 2, r), 0.3, 2.8, 2)

                # ---- 飞溅碎屑：只在最开始 0.35 秒 ----
                if age < 0.35:
                    k = 1.0 - age / 0.35
                    rr2 = random.Random(int(w["x"]) * 13 + 5)
                    for i in range(10):
                        ang = rr2.uniform(-2.9, -0.25)
                        dist = (18 + rr2.uniform(0, 46)) * (1.0 - k * 0.35)
                        px_ = x + math.cos(ang) * dist
                        py_ = y + math.sin(ang) * dist * 0.45 - (1.0 - k) * 26
                        sz = 1 + int(2 * k)
                        pygame.draw.rect(surf, theme.alpha_color((120, 104, 96), int(220 * k)),
                                         (int(px_), int(py_), sz, sz))
            except Exception:
                pass

    def _draw_rifts(self, surf, cam_x, cam_y, t, st):
        """刷怪前兆：紫色裂隙/黑洞。

        结构（由外到内）：外层辉光 -> 双向旋转光环 -> 引力弧 -> 深紫核心 -> 吸入粒子。
        进度 t/delay 驱动半径与亮度，越接近开启越亮越大。
        """
        for r in st.get("rifts", []):
            try:
                rx = float(r["x"]) - cam_x
                ry = float(r["y"]) - cam_y
                if rx < -140 or rx > surf.get_width() + 140:
                    continue
                prog = max(0.0, min(1.0, float(r.get("t", 0.0)) / max(0.01, float(r.get("delay", 1.0)))))
                # 闭合阶段：半径与亮度一起收掉
                _fade = float(r.get("fade", 0.0))
                _fm = max(0.01, float(r.get("fade_max", 0.34)))
                shrink = 1.0
                dim = 1.0
                if _fade > 0.0:
                    shrink = max(0.0, _fade / _fm)
                    dim = shrink ** 0.7
                base = float(r.get("size", 28.0)) * (0.52 + 0.48 * prog) * (0.55 + 0.45 * shrink)
                wide = base * 1.05
                tall = base * 0.86
                cx, cy = int(rx), int(ry)

                # 地面投影光斑（让黑洞"坐"在地上，而不是浮着）
                spot = pygame.Surface((int(wide * 3.2), int(tall * 1.6)), pygame.SRCALPHA)
                for k in range(6, 0, -1):
                    f = k / 6.0
                    a = int(16 * prog * (1.0 - f) + 6)
                    pygame.draw.ellipse(spot, (120, 60, 200, a),
                                        (int(wide * 1.6 * (1 - f)), int(tall * 0.8 * (1 - f)),
                                         int(wide * 3.2 * f), int(tall * 1.6 * f)))
                surf.blit(spot, (cx - spot.get_width() // 2, cy - spot.get_height() // 2))

                # 外层辉光（3 层薄雾，alpha 压得很低，否则叠成紫色实心球）
                for k in range(3):
                    rr = 1.0 + k * 0.26
                    a = int((13 + 11 * prog) * dim / (1 + k * 0.9))
                    pygame.draw.ellipse(surf, theme.alpha_color((138, 78, 232), a),
                                        (cx - wide * rr, cy - tall * rr,
                                         wide * 2 * rr, tall * 2 * rr))
                # 外缘细亮环（把"洞"的边界勾出来，比填充更像引力透镜）
                pygame.draw.ellipse(surf, theme.alpha_color((186, 132, 255), int(150 * dim)),
                                    (cx - wide, cy - tall, wide * 2, tall * 2), 2)
                # 辐射光线（引力透镜感：从边缘向外拉出细丝）
                for k in range(10):
                    ang = k * 0.628 + t * 0.5
                    r0 = wide * 1.02
                    r1 = wide * (1.18 + 0.14 * math.sin(t * 2.6 + k * 1.7))
                    pygame.draw.line(surf, theme.alpha_color((176, 122, 250), int(78 * dim)),
                                     (cx + math.cos(ang) * r0, cy + math.sin(ang) * r0 * 0.82),
                                     (cx + math.cos(ang) * r1, cy + math.sin(ang) * r1 * 0.82), 1)
                # 双向旋转光环
                for k in range(2):
                    sgn = 1.0 if k == 0 else -1.0
                    ang = t * (2.3 + k * 1.4) * sgn + k * 1.9
                    rr = 1.12 + k * 0.20
                    rect = (cx - wide * rr, cy - tall * rr, wide * 2 * rr, tall * 2 * rr)
                    pygame.draw.arc(surf, theme.alpha_color((205, 158, 255), 190),
                                    rect, ang, ang + 2.1, 2)
                    pygame.draw.arc(surf, theme.alpha_color((255, 226, 255), 130),
                                    rect, ang + 0.35, ang + 1.35, 1)
                # 引力弧（向内收的短弧，制造"被吸进去"的感觉）
                for k in range(5):
                    ang = t * 1.9 + k * 1.256
                    rr = 0.94 + 0.10 * math.sin(t * 3.0 + k)
                    rect = (cx - wide * rr, cy - tall * rr, wide * 2 * rr, tall * 2 * rr)
                    pygame.draw.arc(surf, theme.alpha_color((180, 120, 250), 150),
                                    rect, ang, ang + 0.55, 1)
                # 核心：径向渐变的"深洞"（中心近黑，向外透紫），比单色圆更像塌缩
                for k in range(7):
                    f = k / 6.0                      # 0 内 -> 1 外
                    rr = 0.90 - 0.52 * f
                    sh = int(8 + 30 * f)
                    pygame.draw.ellipse(surf,
                                        (sh, max(2, int(sh * 0.30)), min(255, sh + 14)),
                                        (cx - wide * rr, cy - tall * rr,
                                         wide * 2 * rr, tall * 2 * rr))
                # 内缘亮边（环状，不填满）
                pygame.draw.ellipse(surf, theme.alpha_color((148, 92, 226), int(210 * dim)),
                                    (cx - wide * 0.90, cy - tall * 0.90,
                                     wide * 1.80, tall * 1.80), 2)
                pygame.draw.ellipse(surf, theme.alpha_color((224, 190, 255), int((110 + 120 * prog) * dim)),
                                    (cx - wide * 0.96, cy - tall * 0.96,
                                     wide * 1.92, tall * 1.92), 1)
                # 核心内的一点亮心（越接近开启越亮）
                theme.glow_circle(surf, (cx, cy), int(base * 0.55),
                                  (198, 140, 255), 0.30 + 0.32 * prog, 2)

                # 吸入粒子：从外圈螺旋掉进核心（外层大点、内层亮点）
                for k in range(9):
                    ph = (t * 1.25 + k / 9.0) % 1.0
                    rr = 2.10 - ph * 1.60
                    ang = k * 0.7 + t * 2.4 + ph * 3.4
                    px = cx + math.cos(ang) * wide * rr
                    py = cy + math.sin(ang) * tall * rr
                    a2 = int(245 * (1.0 - ph) * (0.45 + 0.55 * prog) * dim)
                    rad = 3 if ph < 0.35 else (2 if ph < 0.7 else 1)
                    pygame.draw.circle(surf, theme.alpha_color((214, 168, 255), a2),
                                       (int(px), int(py)), rad)
                    if ph < 0.5:
                        pygame.draw.circle(surf, theme.alpha_color((255, 245, 255), int(a2 * 0.7)),
                                           (int(px), int(py)), 1)
                # 即将开启：边缘闪烁提示
                if prog > 0.72 and _fade <= 0.0:
                    flick = 0.5 + 0.5 * math.sin(t * 22.0)
                    pygame.draw.ellipse(surf, theme.alpha_color((255, 214, 255), int(150 * flick)),
                                        (cx - wide * 0.92, cy - tall * 0.92,
                                         wide * 1.84, tall * 1.84), 2)
            except Exception as e:
                if not getattr(self, "_rifts_warned", False):
                    self._rifts_warned = True
                    print("[裂隙绘制异常] %r" % (e,))

    def _draw_monsters(self, surf, cam_x, cam_y, t, st):
        for m in st.get("monsters", []):
            try:
                kind = m["kind"]
                # 出场动画：0 -> 1（从黑洞里浮上来 + 淡入）
                _prog = None
                if m.get("state") == "spawn":
                    _prog = 1.0 - max(0.0, float(m.get("state_t", 0.0))) / 0.55
                    _prog = max(0.0, min(1.0, _prog))
                _yoff = int((1.0 - _prog) * 22) if _prog is not None else 0
                if kind == "tree":
                    # 树精 Boss：投掷姿势（举手抬蛋）+ 蓄力紫光 + 受击闪白
                    _st = m.get("state", "walk")
                    img = sprites.get_monster("tree", 1 if _st == "throw" else 0)
                    if m.get("dir", 1) < 0:
                        img = pygame.transform.flip(img, True, False)
                    wu = float(m.get("windup", 0.0))
                    if 0.0 < wu < 0.6:
                        _k = 1.0 - wu / 0.6
                        w0, h0 = img.get_size()
                        img = pygame.transform.scale(
                            img, (int(w0 * (1 + 0.03 * _k)), int(h0 * (1 - 0.02 * _k))))
                    r = img.get_rect(midbottom=(int(m["x"]) - cam_x,
                                               int(m["y"]) - cam_y + 4 + _yoff))
                    theme.soft_shadow(surf, int(m["x"]) - cam_x,
                                      int(m["y"]) - cam_y, 62, 16,
                                      int(120 * (1.0 - (_prog or 0.0))))
                    # 蓄力/喷火：投掷=紫光（身后光晕），喷火=幽蓝光（嘴前，画在精灵之上）
                    _fl = float(m.get("flash", 0.0))
                    _blue = _st in ("breathe_wind", "breathe_fire")
                    if _fl > 0.02 and not _blue:
                        theme.glow_circle(surf, (r.centerx, r.centery + 8), 96,
                                          (168, 88, 232), 0.22 + 0.45 * _fl, 4)
                        theme.glow_circle(surf, (r.centerx, r.top + 40), 34,
                                          (226, 170, 255), 0.30 + 0.4 * _fl, 2)
                    if m.get("enraged"):
                        pulse = 0.55 + 0.45 * math.sin(t * 6)
                        theme.glow_circle(surf, (r.centerx, r.centery), 70,
                                          (255, 70, 60), 0.20 + 0.22 * pulse, 3)
                    surf.blit(img, r)
                    # 幽蓝聚气：画在嘴前（精灵之上），越蓄越亮
                    if _fl > 0.02 and _blue:
                        _mxs = int(m["x"]) - cam_x + 3
                        _mys = int(m["y"]) - cam_y - 58
                        theme.glow_circle(surf, (_mxs, _mys), 46,
                                          (80, 180, 255), 0.30 + 0.55 * _fl, 4)
                        theme.glow_circle(surf, (_mxs, _mys), 18,
                                          (210, 245, 255), 0.40 + 0.5 * _fl, 2)
                    # 受击闪白：血量下降的那一瞬叠一层亮白，逐帧衰减
                    _hp = int(m["hp"])
                    _mid = m["mid"]
                    _prev = self._tree_hp.get(_mid)
                    if _prev is not None and _hp < _prev:
                        self._tree_hurt[_mid] = t
                    self._tree_hp[_mid] = _hp
                    _ht = self._tree_hurt.get(_mid, -9.0)
                    if 0.0 <= t - _ht < 0.16:
                        _k2 = 1.0 - (t - _ht) / 0.16
                        wf = img.copy()
                        wf.fill((130, 120, 120), special_flags=pygame.BLEND_RGB_ADD)
                        wf.set_alpha(int(215 * _k2))
                        surf.blit(wf, r)
                    # 血条
                    bw = 104
                    ratio = max(0.0, min(1.0, m["hp"] / float(max(1, m.get("maxhp", 1)))))
                    bx = r.centerx - bw // 2
                    by = r.top - 12
                    pygame.draw.rect(surf, (16, 12, 18), (bx - 1, by - 1, bw + 2, 8), border_radius=4)
                    pygame.draw.rect(surf, (150, 90, 220), (bx, by, int(bw * ratio), 6), border_radius=3)
                    continue
                if kind == "boss":
                    # 手臂跟着状态走：走路摆臂 / 蓄力举拳 / 冲锋前顶 / 砸地
                    _bs = m.get("state", "walk")
                    _bt = float(m.get("state_t", 0.0))
                    if _bs == "slam":
                        # 起跳举拳 -> 落拳砸地
                        _pose = "slam_up" if _bt < 0.35 else "slam_down"
                    elif _bs == "tele":
                        # 蓄力：手臂分两段抬起（0.42s 的蓄力过程看得出来）
                        _pose = "raise0" if _bt < 0.18 else "raise1"
                    elif _bs == "charge":
                        # 冲锋：身体前倾 + 手臂前后小幅交替
                        _pose = "charge1" if int(t * 10) % 2 else "charge0"
                    elif _bs == "recover":
                        _pose = "slam_down" if _bt < 0.16 else "walk0"
                    else:
                        # 走路：4 帧循环（重心起伏 + 手臂反向摆）
                        _pose = "walk%d" % (int(t * 4) % 4)
                    img = sprites.get_monster("boss", _pose)
                    if m.get("dir", 1) < 0:
                        img = pygame.transform.flip(img, True, False)
                    r = img.get_rect(midbottom=(int(m["x"]) - cam_x, int(m["y"]) - cam_y + 4))
                    theme.soft_shadow(surf, int(m["x"]) - cam_x, int(m["y"]) - cam_y, 76, 15, 120)
                    if m.get("enraged"):
                        # 狂暴：核心变红、外环脉动
                        pulse = 0.55 + 0.45 * math.sin(t * 7)
                        theme.glow_circle(surf, (r.centerx, r.centery + 4), 54,
                                          (255, 60, 40), 0.35 + 0.3 * pulse, 4)
                    fl = m.get("flash", 0.0)
                    if fl > 0.02:
                        # 蓄力：红光越来越亮，给玩家反应时间
                        theme.glow_circle(surf, r.center, 84, (255, 70, 48), 0.30 + 0.55 * fl, 4)
                    theme.glow_circle(surf, (r.centerx, r.centery + 2), 34, (255, 150, 70), 0.55, 3)
                    if m.get("lava"):
                        # 岩浆小 Boss：脚下岩浆翻涌（上升泡泡 + 橙光），强化"泡在岩浆里"
                        for _i in range(5):
                            _ph = (t * 1.7 + _i * 1.3) % 1.0
                            _bx = r.centerx + int(math.sin(t * 2 + _i * 2.1) * 26)
                            _by = r.bottom - 4 - int(_ph * 10)
                            _br = max(1, int(4 * (1 - _ph)))
                            pygame.draw.circle(surf, (255, 150, 60), (_bx, _by), _br)
                        theme.glow_circle(surf, (r.centerx, r.bottom - 2), 58,
                                          (255, 110, 40), 0.45, 3)
                    # 砸地落拳：两只拳头位置各炸一团火，读起来才是"用手砸"
                    if _bs == "slam" and _bt >= 0.35:
                        _k = max(0.0, 1.0 - (_bt - 0.35) / 0.25)
                        for _fx in (17, 75):
                            theme.glow_circle(surf, (r.left + _fx, r.top + 108),
                                              22, (255, 170, 90), 0.55 * _k, 3)
                            theme.glow_circle(surf, (r.left + _fx, r.top + 108),
                                              10, (255, 246, 220), 0.85 * _k, 2)
                    if m.get("state") == "charge":
                        for k in (1, 2, 3):
                            g = img.copy()
                            g.set_alpha(70 - k * 18)
                            surf.blit(g, r.move(-k * 16 * (1 if m.get("dir", 1) > 0 else -1), 0))
                    surf.blit(img, r)
                    bw = 64
                    ratio = max(0.0, min(1.0, m["hp"] / float(max(1, m.get("maxhp", 1)))))
                    bx = r.centerx - bw // 2
                    by = r.top - 10
                    pygame.draw.rect(surf, (16, 12, 18), (bx - 1, by - 1, bw + 2, 8), border_radius=4)
                    pygame.draw.rect(surf, (255, 130, 60), (bx, by, int(bw * ratio), 6), border_radius=3)
                    continue
                frame = int(t * 7 + m["mid"] * 0.7) % 2
                img = sprites.get_monster(kind, frame)
                wob = math.sin(t * 5 + m["mid"] * 1.7) * 2.0
                if m.get("elite"):
                    w0, h0 = img.get_size()
                    img = pygame.transform.scale(img, (int(w0 * 1.3), int(h0 * 1.3)))
                if _prog is not None:
                    img = img.copy()
                    img.set_alpha(int(255 * min(1.0, _prog * 1.5)))
                r = img.get_rect()
                if kind == "caster":
                    theme.glow_circle(surf, (int(m["x"]) - cam_x, int(m["y"]) - 22 - cam_y + _yoff),
                                      34, (150, 110, 220), 0.45, 3)
                    r.midbottom = (int(m["x"]) - cam_x, int(m["y"]) - cam_y + _yoff)
                elif kind == "fly":
                    # 注意 - cam_y：caster/ground 都有，唯独 fly 漏了。
                    # 漏掉后飞怪按世界坐标 y 当屏幕坐标画，相机越往下它被画得越低，
                    # 看起来"永远贴在地上"，玩家瞄头打不到——这才是"打不到飞怪"的真原因。
                    r.center = (int(m["x"]) - cam_x,
                                int(m["y"]) - cam_y - 12 + int(wob) + _yoff)
                    theme.glow_circle(surf, r.center, 20, (190, 110, 240), 0.22, 2)
                else:
                    r.midbottom = (int(m["x"]) - cam_x, int(m["y"]) - cam_y + 2 + _yoff)
                    theme.soft_shadow(surf, int(m["x"]) - cam_x, int(m["y"]) - cam_y + _yoff, 30, 7, 90)
                if _prog is not None and _prog < 0.95:
                    # 出场时脚下带一圈紫色余晖，视觉上"从裂隙里涌出来"
                    theme.glow_circle(surf, (r.centerx, r.bottom), 30,
                                      (170, 110, 250), 0.30 * (1.0 - _prog) + 0.10, 3)
                if m.get("elite"):
                    # 精英：脚下紫色光环 + 头顶菱形，保证在混战中也一眼可辨
                    pulse = 0.6 + 0.4 * math.sin(t * 5 + m["mid"])
                    ring = pygame.Rect(0, 0, 46, 14)
                    ring.center = (r.centerx, r.bottom + 2)
                    pygame.draw.ellipse(surf, theme.alpha_color((190, 90, 255), int(150 * pulse)), ring, 2)
                    dy = r.top - 12
                    pygame.draw.polygon(surf, (215, 150, 255),
                                        [(r.centerx, dy - 5), (r.centerx + 4, dy),
                                         (r.centerx, dy + 5), (r.centerx - 4, dy)])
                if m.get("stun", 0) > 0:
                    tint = img.copy()
                    tint.fill((150, 150, 170, 0), special_flags=pygame.BLEND_RGBA_ADD)
                    surf.blit(tint, r)
                else:
                    surf.blit(img, r)
                # 血条（出场过程中不画：还没成型就顶个血条很出戏）
                if _prog is None or _prog >= 0.85:
                    bw = 30
                    ratio = max(0.0, min(1.0, m["hp"] / float(max(1, m.get("maxhp", 1)))))
                    bx = r.centerx - bw // 2
                    by = r.top - 7
                    pygame.draw.rect(surf, (18, 16, 24), (bx - 1, by - 1, bw + 2, 6), border_radius=3)
                    col = (232, 80, 84) if ratio > 0.4 else (255, 150, 70)
                    pygame.draw.rect(surf, col, (bx, by, int(bw * ratio), 4), border_radius=2)
            except Exception:
                pass

    def _draw_slash(self, surf, x, y, facing, d, k, alpha=1.0):
        """盾卫的斜斩刀光：dir=+1 从左上劈到右下，-1 反过来。

        连续两刀方向相反，叠起来就是一个 X；上一刀会留 0.26 秒残影，
        所以 X 是"画"出来的，而不是单帧的十字。
        """
        try:
            f = 1 if facing >= 0 else -1
            # 刀光是一条"月牙"：从斜上方扫到斜下方，用二次贝塞尔弯曲。
            # 两刀方向相反、各自弯向一侧，交叉处就自然叠成一个 X。
            cx = x + f * 2
            cy = y - 26
            if d > 0:
                p0 = (cx - 32 * f, cy - 34)
                p1 = (cx + 38 * f, cy + 28)
                ctrl = (cx + 16 * f, cy - 6)
            else:
                p0 = (cx + 32 * f, cy - 34)
                p1 = (cx - 38 * f, cy + 28)
                ctrl = (cx - 16 * f, cy - 6)
            prog = max(0.10, min(1.0, k))
            n = 14
            pts = []
            for i in range(n + 1):
                tt = (i / float(n)) * prog
                u = 1.0 - tt
                pts.append((u * u * p0[0] + 2 * u * tt * ctrl[0] + tt * tt * p1[0],
                            u * u * p0[1] + 2 * u * tt * ctrl[1] + tt * tt * p1[1]))
            # 三层叠加 + 末端更粗（锥形刀光）
            for wdt, col in ((9, (66, 152, 220)), (5, (168, 226, 255)),
                             (2, (246, 254, 255))):
                c = tuple(int(ch * (0.55 + 0.45 * alpha)) for ch in col)
                for i in range(len(pts) - 1):
                    tt = (i + 1) / float(max(1, len(pts) - 1))
                    w = max(1, int(wdt * (0.45 + 0.75 * tt)))
                    pygame.draw.line(surf, c, (int(pts[i][0]), int(pts[i][1])),
                                     (int(pts[i + 1][0]), int(pts[i + 1][1])), w)
            # 起手火花 + 刀锋最前端的高光
            theme.glow_circle(surf, pts[0], 10, (190, 232, 255), 0.50 * alpha, 2)
            theme.glow_circle(surf, pts[-1], 12, (255, 255, 255), 0.85 * alpha, 3)
        except Exception:
            pass

    def _draw_shot_fx(self, surf, rect, facing, fl):
        """弓箭手射击：弓弦松开的白色闪光 + 沿瞄准方向的一道箭气。"""
        try:
            f = 1 if facing >= 0 else -1
            bx = rect.centerx + f * 22
            by = rect.centery - 6
            theme.glow_circle(surf, (bx, by), int(16 * fl) + 6, (255, 246, 210),
                              0.55 * fl, 3)
            theme.glow_circle(surf, (bx, by), int(8 * fl) + 3, (255, 255, 255),
                              0.85 * fl, 2)
            # 箭气：一条快速变淡的短横线
            ln = int(13 * fl)
            if ln > 2:
                for i, (wdt, col) in enumerate(((4, (150, 226, 255)),
                                                (2, (245, 255, 255)))):
                    pygame.draw.line(surf, col, (int(bx), int(by)),
                                     (int(bx + f * ln), int(by)), wdt)
            # 弓臂两端的小亮点
            for sy in (-1, 1):
                theme.glow_circle(surf, (bx - f * 3, by + sy * 12), 5,
                                  (220, 240, 255), 0.5 * fl, 2)
        except Exception:
            pass

    def _draw_players(self, surf, cam_x, cam_y, t, st, focus_pid=None):
        # 残影计时用帧间隔（渲染器没有自己的 dt，从 t 差分算）
        _dt = t - getattr(self, "_fx_last_t", t)
        self._fx_last_t = t
        if not (0.0 < _dt < 0.2):
            _dt = 1.0 / 60.0
        for pid in (0, 1):
            p = st.get("players", {}).get(pid)
            if not p:
                continue
            x = int(p["x"]) - cam_x
            y = int(p["y"]) - cam_y
            kind = "archer" if pid == 0 else "guard"
            hp = p.get("hp", 1)
            sw_v = p.get("swing", 0.0)
            sw_dir = int(p.get("swing_dir", 1) or 1)
            swinging = (pid == 1 and sw_v > 0.02)
            if hp <= 0:
                pose = "fall"
            elif not p.get("on_ground", True):
                pose = "jump" if p.get("vy", 0) < 0 else "fall"
            elif p.get("blocking"):
                pose = "block"
            elif swinging:
                # 4 帧：预备 -> 加速 -> 命中 -> 收招
                _pr = 1.0 - sw_v
                pose = "swing%d" % (0 if _pr < 0.22 else
                                    (1 if _pr < 0.45 else (2 if _pr < 0.70 else 3)))
            elif pid == 0 and p.get("shoot_flash", 0.0) > 0.02:
                _fl = p.get("shoot_flash", 0.0)
                pose = "shoot%d" % (0 if _fl > 0.62 else (1 if _fl > 0.28 else 2))
            elif p.get("moving"):
                pose = "run%d" % (int(t * 12 + pid * 2) % 4)
            else:
                pose = "idle1" if int(t * 1.7 + pid) % 2 else "idle0"
            img = sprites.get_char(kind, pose)
            # 挥剑姿势只画了"朝右"一套：朝向和斩击方向相反时要再翻一次，
            # 这样"手在哪边、刀往哪边扫"才是对得上的。
            flip = (p["facing"] < 0)
            if swinging and sw_dir < 0:
                flip = not flip
            if flip:
                img = pygame.transform.flip(img, True, False)
            land = p.get("land", 0.0)
            if land > 0.04:
                w0, h0 = img.get_size()
                img = pygame.transform.scale(
                    img, (max(4, int(w0 * (1.0 + 0.20 * land))),
                          max(4, int(h0 * (1.0 - 0.18 * land)))))
            # 攻击形变：挥砍命中瞬间横向拉伸，松弦瞬间后坐
            _sx = _sy = 1.0
            if swinging:
                _pr = 1.0 - sw_v
                if 0.40 <= _pr < 0.72:
                    _k = 1.0 - abs(_pr - 0.56) / 0.16
                    _sx, _sy = 1.0 + 0.13 * _k, 1.0 - 0.07 * _k
            elif pid == 0 and p.get("shoot_flash", 0.0) > 0.62:
                _sx, _sy = 0.95, 1.06
            if abs(_sx - 1.0) > 0.005 or abs(_sy - 1.0) > 0.005:
                w0, h0 = img.get_size()
                img = pygame.transform.scale(
                    img, (max(4, int(w0 * _sx)), max(4, int(h0 * _sy))))
            rect = img.get_rect(midbottom=(x, y + 4))

            theme.soft_shadow(surf, x, y, 30, 8, 95)

            # 冲刺残影
            if p.get("dash_cd", 1) > p.get("dash_max", 1) - 0.16:
                for k in range(1, 4):
                    ghost = img.copy()
                    ghost.set_alpha(70 - k * 18)
                    surf.blit(ghost, rect.move(-p["facing"] * k * 9, 0))

            # 挥砍残影：攻击中段拖两帧半透明的自己，速度感主要靠这个
            if swinging:
                _pr2 = 1.0 - sw_v
                if 0.20 < _pr2 < 0.82:
                    _gk = max(0.0, 1.0 - abs(_pr2 - 0.5) / 0.32)
                    for _i, _off in ((1, 7), (2, 15)):
                        _g2 = img.copy()
                        _g2.set_alpha(int(78 * _gk / _i))
                        surf.blit(_g2, rect.move(-p["facing"] * _off, 0))
            inv = p.get("invuln", 0)
            if inv > 0 and int(t * 22) % 2 == 0:
                ghost = img.copy()
                ghost.set_alpha(120)
                surf.blit(ghost, rect)
            else:
                surf.blit(img, rect)

            # ---- 武器 / 攻击特效 ----
            if pid == 1:
                if p.get("blocking"):
                    # 盾牌本体已由精灵 block 姿势绘制；这里只叠一层护盾能量微光，
                    # 不再画第二面盾（旧版会叠出"两面盾"的怪画面）
                    _gx = rect.centerx + p["facing"] * 10
                    theme.glow_circle(surf, (_gx, rect.centery), 26,
                                      (150, 210, 255), 0.16, 2)
                sw = p.get("swing", 0.0)
                # 左右交替的 X 斩：新的一刀出手时，把上一刀留成残影
                prev = self._slash_last.get(pid, 0.0)
                if sw > 0.92 >= prev:
                    self._slash_ghost[pid] = [
                        (g, age + 0.0) for (g, age) in self._slash_ghost.get(pid, [])
                    ] + [(p.get("swing_dir", 1), 0.0)]
                    self._slash_ghost[pid] = self._slash_ghost[pid][-2:]
                self._slash_last[pid] = sw
                # 残影
                # 残影：形状**冻结**在"已经挥完"，只淡出。
                # 之前让残影跟着 age 重放，等于每一刀都从起手重新画，
                # 两刀永远凑不到一起，X 就出不来。
                keep = []
                for d, age in self._slash_ghost.get(pid, []):
                    na = age + _dt
                    if na < 0.45:
                        self._draw_slash(surf, x, y, p["facing"], d, 1.0,
                                         max(0.0, 1.0 - na / 0.45) * 0.65)
                        keep.append((d, na))
                self._slash_ghost[pid] = keep
                if sw > 0:
                    self._draw_slash(surf, x, y, p["facing"],
                                     p.get("swing_dir", 1), 1.0 - sw, 1.0)
            else:
                # 弓箭手：松弦的箭气 + 枪口闪光
                fl = p.get("shoot_flash", 0.0)
                if fl > 0.02:
                    self._draw_shot_fx(surf, rect, p["facing"], fl)

            # 灼烧：被幽蓝火焰点燃后身周跳动的蓝火苗 + 冷光
            if p.get("burn", 0.0) > 0.02:
                theme.glow_circle(surf, (x, y - 18), 24, (90, 180, 255), 0.22, 2)
                rnd = random.Random(int(p["x"]) * 7 + int(t * 9))
                for _i in range(5):
                    fx = x + rnd.uniform(-10, 10)
                    fy = y - rnd.uniform(6, 36)
                    pygame.draw.circle(surf, (150, 220, 255),
                                       (int(fx), int(fy)), max(1, int(rnd.uniform(1, 2.6))))

            # 主角标记
            if focus_pid is not None and pid == focus_pid:
                bob = int(math.sin(t * 3) * 2)
                pts = [(x - 5, rect.top - 14 + bob), (x + 5, rect.top - 14 + bob),
                       (x, rect.top - 7 + bob)]
                pygame.draw.polygon(surf, theme.GOLD_LIGHT, pts)

    def _draw_shield(self, surf, rect, facing, t):
        """盾卫举盾：金属渐变筝形大盾 + 金色包边 + 中心符文呼吸光 + 前缘高光 + 格挡弧光。"""
        w, h = 24, 34
        x = rect.right - 2 if facing > 0 else rect.left - w + 2
        y = rect.centery - h // 2 + 1
        pts = [(x + 3, y), (x + w - 3, y), (x + w, y + 9),
               (x + w // 2, y + h), (x, y + 9)]
        # 底色 -> 内层 -> 受光面（三层模拟金属渐变）
        pygame.draw.polygon(surf, (36, 42, 56), pts)
        inner = [(x + 4, y + 3), (x + w - 4, y + 3), (x + w - 3, y + 10),
                 (x + w // 2, y + h - 4), (x + 3, y + 10)]
        pygame.draw.polygon(surf, (78, 92, 116), inner)
        lit = [(x + 4, y + 3), (x + w // 2, y + 3),
               (x + w // 2 - 1, y + h - 6), (x + 3, y + 10)]
        pygame.draw.polygon(surf, (110, 128, 156), lit)
        # 金色包边
        pygame.draw.polygon(surf, (198, 162, 86), pts, 2)
        # 中心符文（呼吸发光）
        cx, cy = x + w // 2, y + 13
        pulse = 0.55 + 0.45 * math.sin(t * 6)
        theme.glow_circle(surf, (cx, cy), 13, (120, 200, 255), 0.30 * pulse, 2)
        pygame.draw.circle(surf, (120, 190, 240), (cx, cy), 4)
        pygame.draw.circle(surf, (222, 240, 255), (cx, cy), 2)
        # 迎击方向的前缘高光
        edge_x = x + w - 3 if facing > 0 else x + 3
        pygame.draw.line(surf, (224, 234, 248), (edge_x, y + 4), (edge_x, y + h - 10), 2)
        # 格挡闪光弧（迎击侧）
        try:
            arc_a = int(150 * (0.5 + 0.5 * math.sin(t * 9)))
            if facing > 0:
                pygame.draw.arc(surf, theme.alpha_color((175, 222, 255), arc_a),
                                (x - 2, y - 2, w + 6, h + 4), -0.9, 0.9, 2)
            else:
                pygame.draw.arc(surf, theme.alpha_color((175, 222, 255), arc_a),
                                (x - 4, y - 2, w + 6, h + 4), math.pi - 0.9, math.pi + 0.9, 2)
        except Exception:
            pass

    def _draw_sword(self, surf, rect, facing, prog):
        """挥剑：从后上方劈到前下方的刀光"""
        ang = math.radians(-115 + prog * 210.0)
        if facing < 0:
            ang = math.pi - ang
        hx = rect.centerx + facing * 6
        hy = rect.centery - 2
        L = 38
        tip = (hx + math.cos(ang) * L, hy + math.sin(ang) * L)
        base = (hx + math.cos(ang) * 7, hy + math.sin(ang) * 7)
        nx = math.cos(ang + math.pi / 2) * 2.6
        ny = math.sin(ang + math.pi / 2) * 2.6
        blade = [(base[0] - nx, base[1] - ny), (base[0] + nx, base[1] + ny),
                 (tip[0] + nx * 0.4, tip[1] + ny * 0.4), (tip[0] - nx * 0.4, tip[1] - ny * 0.4)]
        pygame.draw.polygon(surf, (226, 232, 244), blade)
        pygame.draw.polygon(surf, (140, 148, 168), blade, 1)
        pygame.draw.line(surf, (255, 255, 255), base, tip, 1)
        # 刀光
        arc = pygame.Surface((110, 110), pygame.SRCALPHA)
        a0 = math.radians(-115 + prog * 210.0 - 46)
        a1 = math.radians(-115 + prog * 210.0 + 12)
        if facing > 0:
            pygame.draw.arc(arc, (255, 246, 210, 130), (8, 8, 94, 94), -a1, -a0, 5)
        else:
            pygame.draw.arc(arc, (255, 246, 210, 130), (8, 8, 94, 94), math.pi + a0, math.pi + a1, 5)
        surf.blit(arc, (hx - 55, hy - 55))

    # ==================================================================
    # 前景氛围
    # ==================================================================
    def _fg_surfaces(self, w, h, region):
        key = (w, h, 1 if region >= 0.5 else 0)
        v = self._fg_cache.get(key)
        if v is not None:
            return v
        col = (100, 96, 140) if region < 0.5 else (150, 80, 60)
        fog = pygame.Surface((w, 90), pygame.SRCALPHA)
        for i in range(90):
            a = int(18 * (i / 90.0) ** 1.5)
            pygame.draw.line(fog, theme.alpha_color(col, a), (0, i), (w, i))
        dh = int(h * 0.26)
        dark = pygame.Surface((w, dh), pygame.SRCALPHA)
        for i in range(dh):
            a = int(118 * (i / float(dh)) ** 1.4)
            pygame.draw.line(dark, (6, 7, 12, a), (0, i), (w, i))
        self._fg_cache[key] = (fog, dark, dh)
        return self._fg_cache[key]

    def _draw_foreground(self, surf, cam_x, cam_y, t, region):
        w, h = surf.get_size()
        # 近景浮尘
        for i in range(14):
            px = (i * 173 + t * (8 + i % 5)) % (w + 120) - 60
            py = (i * 97 + math.sin(t * 0.6 + i) * 20 - cam_y * 0.3) % h
            a = 30 + int(18 * math.sin(t + i))
            pygame.draw.circle(surf, theme.alpha_color((255, 232, 190), a), (int(px), int(py)), 1)
        # 底部环境雾 + 压暗（静态，缓存）
        fog, dark, dh = self._fg_surfaces(w, h, region)
        surf.blit(fog, (0, 430))
        surf.blit(dark, (0, h - dh))
