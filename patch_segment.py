# -*- coding: utf-8 -*-
"""分段世界：开局绿意段（绿草/绿藤/雪暮浮岛）-> 余烬世界（col >= GREEN_UNTIL）。

- 地表 tile / edge / decor 全部双份（green=True 原版绿，False 余烬）
- 悬浮平台：green 段专用，顶面用雪暮 tile + 岛体雪白调色（FLOAT_ISLANDS 开关改按段生效）
- 藤蔓恢复原版绿色（都在开局段）
"""
import io

P = "renderer.py"
s = io.open(P, encoding="utf-8").read()
log = []


def rep(old, new, tag):
    global s
    if old in s:
        s = s.replace(old, new, 1)
        log.append(tag)
    elif new in s:
        log.append(tag + "(already)")
    else:
        log.append(tag + "(SKIP)")


# ---- 0) 常量：绿色段的列边界 ----
rep('''# 悬浮岛外观开关（v3/v4 的岛体轮廓：参差侧边+圆弧岩根+瀑布+碎石）。
# 用户要求取消设计——置 False 即回到 tile 原本的规整方块。
# 烘焙/绘制代码都保留在 _bake_island/_draw_float_shells 里，随时可重新打开。
FLOAT_ISLANDS = False''',
    '''# 悬浮岛外观：只对"绿意段"（col < GREEN_UNTIL）的悬浮平台启用，配色固定雪暮。
# 用户要求取消全图悬浮岛后，又要求开局段用雪暮顶——改为按段启用。
# 烘焙/绘制代码保留在 _bake_island/_draw_float_shells 里。
FLOAT_ISLANDS = True
FLOAT_ISLAND_SNOW = True      # 绿意段的浮岛用雪暮配色
# 开局绿意段的列边界：这里之前是绿草/绿藤/雪暮浮岛（"记忆中的世界"），
# 之后进入余烬世界（黑灰焦土+发光裂缝）。想调分段长度改这一个数。
GREEN_UNTIL = 45''',
    "consts")

# ---- 1) _grass_tile 加 green 参数：green=True 恢复原版绿草 ----
rep('''    def _grass_tile(self, depth, var):
        """余烬地表（v2.19）：黑灰焦土 + 发光裂缝，取代绿草。

        世界观：火在熄灭、余温尚存。裂缝密度由 var 控制——
        var>=2 为"密缝"变体（3 条缝 + 更多 ember 点），渲染端按区域
        偏移 seed 实现森林(稀) -> 焦土(密) 的递进。
        """
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        ramp = [
            (62, 58, 62), (54, 50, 54), (46, 43, 47),
            (39, 37, 40), (33, 31, 34), (27, 26, 29),
        ]''',
    '''    def _grass_tile(self, depth, var, green=False):
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
            ]''',
    "grass_green_ramp")

# depth==0 表层：green 草皮 / 余烬焦壳
rep('''        dense = var >= 2
        if depth == 0:
            # 地表层：暗焦壳
            top = (72, 66, 68)''',
    '''        dense = var >= 2
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
            top = (72, 66, 68)''',
    "grass_green_top")

# ---- 2) _build：grass/dirt/edge/decor 双份 ----
rep('''    def _build(self):
        self._decor_cache = {}
        for d in range(self.DEPTHS):
            for v in range(self.VARIANTS):
                self.grass[(d, v)] = self._grass_tile(d, v)
                self.dirt[(d, v)] = self._grass_tile(min(5, d + 2), v)
                self.metal[(d, v)] = self._metal_tile(d, v)
                self.scorch[(d, v)] = self._scorch_tile(d, v)
        for v in range(self.VARIANTS):
            self.rock[v] = self._rock_tile(v)
            self.edge[v] = self._edge(v)
            self.edge_scorch[v] = self._edge(v, scorch=True)''',
    '''    def _build(self):
        self._decor_cache = {}
        for green in (False, True):
            tag = 1 if green else 0
            for d in range(self.DEPTHS):
                for v in range(self.VARIANTS):
                    self.grass[(d, v, tag)] = self._grass_tile(d, v, green)
                    self.dirt[(d, v, tag)] = self._grass_tile(min(5, d + 2), v, green)
                    self.metal[(d, v, tag)] = self._metal_tile(d, v)
                    self.scorch[(d, v, tag)] = self._scorch_tile(d, v)
            for v in range(self.VARIANTS):
                self.edge[(tag, v)] = self._edge(v, green=green)
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
                self.snow[(d, v)] = self._snow_tile(d, v)''',
    "build_dual")

# ---- 3) get_grass/get_dirt/get_edge/get_decor 加 green 维度 ----
rep('''    def get_grass(self, depth, seed):
        return self.grass[(min(5, depth), seed % self.VARIANTS)]

    def get_dirt(self, depth, seed):
        return self.dirt[(min(5, depth), (seed * 3 + 1) % self.VARIANTS)]''',
    '''    def get_grass(self, depth, seed, green=False):
        return self.grass[(min(5, depth), seed % self.VARIANTS, 1 if green else 0)]

    def get_dirt(self, depth, seed, green=False):
        return self.dirt[(min(5, depth), (seed * 3 + 1) % self.VARIANTS, 1 if green else 0)]''',
    "get_grass_dirt")

rep('''    def get_edge(self, seed, scorch=False):
        if scorch:
            return self.edge_scorch[seed % self.VARIANTS]
        return self.edge[seed % self.VARIANTS]''',
    '''    def get_edge(self, seed, scorch=False, green=False):
        if scorch:
            return self.edge_scorch[seed % self.VARIANTS]
        return self.edge[(1 if green else 0, seed % self.VARIANTS)]''',
    "get_edge")

rep('''    def get_decor(self, kind, var):
        key = ("d", kind, var)
        if key not in self._decor_cache:
            self._decor_cache[key] = self._decor(kind, var)
        return self._decor_cache[key]''',
    '''    def get_decor(self, kind, var, green=False):
        key = ("d", kind, var, green)
        if key not in self._decor_cache:
            self._decor_cache[key] = self._decor(kind, var, green)
        return self._decor_cache[key]''',
    "get_decor")

# ---- 4) _edge 加 green 分支 ----
rep('''    def _edge(self, var, scorch=False):
        """地形上沿：森林是草叶，岩壁/岩浆区是焦枯的短茬与灰烬。"""
        s = pygame.Surface((TILE, 12), pygame.SRCALPHA)
        rnd = random.Random(var * 17 + 3)
        if scorch:''',
    '''    def _edge(self, var, scorch=False, green=False):
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
        if scorch:''',
    "edge_green")

# ---- 5) _decor 加 green：绿草丛 / 原版蘑菇 / 野花 ----
rep('''    def _decor(self, kind, var):
        """地表装饰：草丛 / 石块 / 蘑菇 / 野花 / 枯枝"""
        s = pygame.Surface((TILE, 20), pygame.SRCALPHA)
        rnd = random.Random(kind * 71 + var * 17)
        if kind == 0:      # 焦枯灌木（余烬世界）
            for _ in range(6):
                x = rnd.randrange(4, 28)
                h = rnd.randint(5, 12)
                pygame.draw.line(s, (96, 148, 90), (x, 20), (x + rnd.randint(-3, 3), 20 - h), 2)
                pygame.draw.line(s, (64, 56, 52), (x, 20), (x + rnd.randint(-2, 2), 20 - h + 2), 1)''',
    '''    def _decor(self, kind, var, green=False):
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
                pygame.draw.line(s, stem2, (x, 20), (x + rnd.randint(-2, 2), 20 - h + 2), 1)''',
    "decor_green_bush")
rep('''        elif kind == 2:    # 蘑菇（暗红棕，避免鲜红跳戏）
            x = rnd.randrange(8, 22)
            pygame.draw.rect(s, (150, 130, 112), (x, 14, 3, 6))
            pygame.draw.ellipse(s, (122, 70, 62), (x - 4, 9, 11, 7))
            pygame.draw.circle(s, (170, 110, 96), (x - 1, 11), 1)
            pygame.draw.circle(s, (170, 110, 96), (x + 3, 12), 1)''',
    '''        elif kind == 2:    # 蘑菇（绿段原红伞 / 余烬段暗红棕）
            x = rnd.randrange(8, 22)
            cap, dot = ((196, 84, 78), (240, 200, 180)) if green else ((122, 70, 62), (170, 110, 96))
            pygame.draw.rect(s, (222, 214, 190) if green else (150, 130, 112), (x, 14, 3, 6))
            pygame.draw.ellipse(s, cap, (x - 4, 9, 11, 7))
            pygame.draw.circle(s, dot, (x - 1, 11), 1)
            pygame.draw.circle(s, dot, (x + 3, 12), 1)''',
    "decor_green_mush")
rep('''        elif kind == 4:    # 火种花（余烬世界的野花）
            x = rnd.randrange(6, 24)
            pygame.draw.line(s, (86, 60, 48), (x, 20), (x, 12), 1)
            for dx, dy in ((0, -2), (2, 0), (-2, 0), (0, 2)):
                pygame.draw.circle(s, (255, 140, 60), (x + dx, 11 + dy), 2)
            pygame.draw.circle(s, (255, 224, 150), (x, 11), 1)''',
    '''        elif kind == 4:    # 野花（green 原黄白花 / 余烬=火种花）
            x = rnd.randrange(6, 24)
            stem = (98, 148, 88) if green else (86, 60, 48)
            petal = (240, 214, 130) if green else (255, 140, 60)
            core = (255, 246, 200) if green else (255, 224, 150)
            pygame.draw.line(s, stem, (x, 20), (x, 12), 1)
            for dx, dy in ((0, -2), (2, 0), (-2, 0), (0, 2)):
                pygame.draw.circle(s, petal, (x + dx, 11 + dy), 2)
            pygame.draw.circle(s, core, (x, 11), 1)''',
    "decor_green_flower")

# ---- 6) _snow_tile 新方法（雪暮顶）----
rep('''    def _rock_tile(self, var):''',
    '''    def _snow_tile(self, depth, var):
        """雪暮 tile：积雪白顶 + 冻土蓝灰（绿意段悬浮平台专用）。"""
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
        ramp = [(96, 104, 124), (84, 90, 108), (72, 76, 92),
                (60, 62, 76), (50, 50, 62), (42, 42, 52)]
        base = ramp[min(depth, 5)]
        rnd = random.Random(depth * 97 + var * 13 + 7)
        s.fill(base)
        for _ in range(26):
            x, y = rnd.randrange(0, T), rnd.randrange(0, T)
            c = theme.shade(base, rnd.uniform(-0.2, 0.12))
            s.fill(c, (x, y, rnd.randint(2, 4), rnd.randint(1, 3)))
        if depth == 0:
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

    def _rock_tile(self, var):''',
    "snow_tile")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_seg1_log.txt", "w", encoding="utf-8").write(" | ".join(log))
print("done")
