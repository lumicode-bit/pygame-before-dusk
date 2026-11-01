# -*- coding: utf-8 -*-
"""余烬地表：替换 _grass_tile 表层、_edge 草叶、decor 绿色系；裂缝密度按区递进。"""
import io

P = "renderer.py"
s = io.open(P, encoding="utf-8").read()
log = []


def rep(old, new, tag, count=1):
    global s
    if old in s:
        s = s.replace(old, new, count)
        log.append(tag)
    elif new in s:
        log.append(tag + "(already)")
    else:
        log.append(tag + "(SKIP)")


# ---- 1) _grass_tile：绿草 -> 余烬焦土（保留 depth 分层/颗粒/变体机制）----
a = s.index("    def _grass_tile(self, depth, var):")
b = s.index("    def _rock_tile(self, var):")
NEW = '''    def _grass_tile(self, depth, var):
        """余烬地表（v2.19）：黑灰焦土 + 发光裂缝，取代绿草。

        世界观：火在熄灭、余温尚存。裂缝密度由 var 控制——
        var>=2 为"密缝"变体（3 条缝 + 更多 ember 点），渲染端按区域
        偏移 seed 实现森林(稀) -> 焦土(密) 的递进。
        """
        s = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
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

'''
s = s[:a] + NEW + s[b:]
log.append("grass_tile_ember")

# ---- 2) _edge 森林分支：绿草叶 -> 焦枯短茬 + ember ----
rep('''        for i in range(0, TILE, 2):
            h = rnd.randint(2, 7)
            c = (108, 162, 98) if rnd.random() > 0.3 else (88, 136, 82)
            pygame.draw.line(s, c, (i, 10), (i + rnd.randint(-1, 1), 10 - h), 2)
        return s''',
    '''        # 余烬世界的"草沿"：焦枯短茬 + 偶发 ember 光点
        for i in range(0, TILE, 2):
            h = rnd.randint(2, 5)
            c = (72, 62, 58) if rnd.random() > 0.3 else (56, 48, 46)
            pygame.draw.line(s, c, (i, 10), (i + rnd.randint(-1, 1), 10 - h), 2)
        for _ in range(2):
            pygame.draw.circle(s, (255, 150, 60),
                               (rnd.randrange(2, TILE - 2), rnd.randrange(8, 11)), 1)
        return s''',
    "edge_ember")

# ---- 3) decor：草丛(0) -> 焦黑灌木 + ember；野花(4) -> 火种花；蘑菇(2) 暗化 ----
rep('''        elif kind == 4:    # 野花
            x = rnd.randrange(6, 24)
            pygame.draw.line(s, (98, 148, 88), (x, 20), (x, 12), 1)
            for dx, dy in ((0, -2), (2, 0), (-2, 0), (0, 2)):
                pygame.draw.circle(s, (240, 214, 130), (x + dx, 11 + dy), 2)
            pygame.draw.circle(s, (255, 246, 200), (x, 11), 1)''',
    '''        elif kind == 4:    # 火种花（余烬世界的野花）
            x = rnd.randrange(6, 24)
            pygame.draw.line(s, (86, 60, 48), (x, 20), (x, 12), 1)
            for dx, dy in ((0, -2), (2, 0), (-2, 0), (0, 2)):
                pygame.draw.circle(s, (255, 140, 60), (x + dx, 11 + dy), 2)
            pygame.draw.circle(s, (255, 224, 150), (x, 11), 1)''',
    "decor_flower")
rep('''        elif kind == 2:    # 蘑菇
            x = rnd.randrange(8, 22)
            pygame.draw.rect(s, (222, 214, 190), (x, 14, 3, 6))
            pygame.draw.ellipse(s, (196, 84, 78), (x - 4, 9, 11, 7))
            pygame.draw.circle(s, (240, 200, 180), (x - 1, 11), 1)
            pygame.draw.circle(s, (240, 200, 180), (x + 3, 12), 1)''',
    '''        elif kind == 2:    # 蘑菇（暗红棕，避免鲜红跳戏）
            x = rnd.randrange(8, 22)
            pygame.draw.rect(s, (150, 130, 112), (x, 14, 3, 6))
            pygame.draw.ellipse(s, (122, 70, 62), (x - 4, 9, 11, 7))
            pygame.draw.circle(s, (170, 110, 96), (x - 1, 11), 1)
            pygame.draw.circle(s, (170, 110, 96), (x + 3, 12), 1)''',
    "decor_mush")
# 草丛 kind==0 的代码在 _decor 开头（120,174,104 附近）
rep("                pygame.draw.line(s, (120, 174, 104), (x, 20), (x + rnd.randint(-2, 2), 20 - h + 2), 1)",
    "                pygame.draw.line(s, (64, 56, 52), (x, 20), (x + rnd.randint(-2, 2), 20 - h + 2), 1)",
    "decor_grass_line")
# 草丛的茎色（找相邻的绿色）
rep('''        if kind == 0:      # 草丛''',
    '''        if kind == 0:      # 焦枯灌木（余烬世界）''',
    "decor_grass_tag")

# ---- 4) 渲染端：焦土区强制"密缝"变体 ----
rep('''                if c in ('G', 'S', 's'):
                    d = self._depth(gx, gy, solid)
                    dj = min(d, self.tiles.DEPTHS - 1)
                    if gx >= core.FORGE_LEFT:''',
    '''                if c in ('G', 'S', 's'):
                    d = self._depth(gx, gy, solid)
                    dj = min(d, self.tiles.DEPTHS - 1)
                    # 余烬裂缝密度递进：焦土区强制走"密缝"变体（var>=2）
                    if gx >= core.SCORCH_LEFT:
                        seed |= 2
                    if gx >= core.FORGE_LEFT:''',
    "density_progression")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_ember_log.txt", "w", encoding="utf-8").write(" | ".join(log))
print("done")
