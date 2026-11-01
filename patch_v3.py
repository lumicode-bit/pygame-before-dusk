# -*- coding: utf-8 -*-
"""1) 盾卫剑可击碎岩石（抽公共 _damage_rock，箭/剑共用）
   2) 绿段->余烬段渐变过渡（预烘焙 12 档混合 tile）
   3) 去掉悬浮岛岩根，保留雪顶方块
"""
import io

# ---------------- 引擎 ----------------
P = "game_core.py"
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


# 1) 公共岩石破坏入口
rep("    def _update_arrows(self, dt):",
    '''    def _damage_rock(self, cx, cy, dmg=1):
        """统一的岩石破坏入口（箭 / 盾卫剑共用）。命中返回 True。

        之前只有箭能打碎 'R'，火箭墙这类"必须清路"的障碍如果玩家玩盾卫
        就完全无法处理（AI 弓手不一定在射程内）。
        """
        if not (0 <= cy < MAP_H and 0 <= cx < MAP_W):
            return False
        if self.grid[cy][cx] != 'R':
            return False
        key = (cx, cy)
        hp = self.rocks.get(key, ROCK_HP) - dmg
        if hp <= 0:
            self.rocks.pop(key, None)
            self.grid[cy][cx] = 'G' if cy == 19 else ' '
            self.events.append(("rock_break", cx * TILE + 16, cy * TILE + 16))
        else:
            self.rocks[key] = hp
        return True

    def _update_arrows(self, dt):''', "damage_rock_fn")

# 2) 箭的破坏逻辑改用公共服务
rep('''                            if c == 'R':
                                key = (cx, cy)
                                hp = self.rocks.get(key, ROCK_HP) - 1
                                if hp <= 0:
                                    self.rocks.pop(key, None)
                                    self.grid[cy][cx] = 'G' if cy == 19 else ' '
                                    self.events.append(("rock_break", cx * TILE + 16, cy * TILE + 16))
                                else:
                                    self.rocks[key] = hp
                                self.events.append(("break", int(a.x), int(a.y)))''',
    '''                            if c == 'R':
                                self._damage_rock(cx, cy, 1)
                                self.events.append(("break", int(a.x), int(a.y)))''',
    "arrow_use_common")

# 3) 盾卫剑击也能碎岩（近战伤害 2：两下破一块）
rep('''                    self.events.append(("swing", int(fx), int(fy - 10)))
                    for m in list(self.monsters):''',
    '''                    self.events.append(("swing", int(fx), int(fy - 10)))
                    # 剑也能砸碎岩石：清路不该只有弓手能办
                    try:
                        _c0 = max(0, int(rng[0] // TILE))
                        _c1 = min(MAP_W - 1, int((rng[0] + rng[2]) // TILE))
                        _r0 = max(0, int(rng[1] // TILE))
                        _r1 = min(MAP_H - 1, int((rng[1] + rng[3]) // TILE))
                        for _cy in range(_r0, _r1 + 1):
                            for _cx in range(_c0, _c1 + 1):
                                if self.grid[_cy][_cx] == 'R':
                                    if self._damage_rock(_cx, _cy, 2):
                                        self.events.append(("break", _cx * TILE + 16, _cy * TILE + 16))
                    except Exception:
                        pass
                    for m in list(self.monsters):''', "sword_break_rock")

io.open(P, "w", encoding="utf-8").write(s)

# ---------------- 渲染 ----------------
P = "renderer.py"
s = io.open(P, encoding="utf-8").read()
log2 = []


def rep2(old, new, tag):
    global s
    if old in s:
        s = s.replace(old, new, 1)
        log2.append(tag)
    elif new in s:
        log2.append(tag + "(already)")
    else:
        log2.append(tag + "(SKIP)")


# 4) 常量：关掉岛体、保留雪顶、加渐变长度
rep2('''FLOAT_ISLANDS = True
FLOAT_ISLAND_SNOW = True      # 绿意段的浮岛用雪暮配色''',
     '''FLOAT_ISLANDS = False         # 岩根轮廓全部去掉（用户要求），平台回到方块状
FLOAT_ISLAND_SNOW = True      # 但绿意段的平台仍是雪暮顶（雪白 tile，独立开关）''',
     "switch_off_island")
rep2('''GREEN_UNTIL = 45''',
     '''GREEN_UNTIL = 45
FADE_LEN = 16                # 45..61 之间绿->余烬逐格渐变
FADE_STEPS = 12              # 渐变预烘焙档数''', "fade_consts")

# 5) 雪顶格子独立于 FLOAT_ISLANDS
rep2('''            if FLOAT_ISLANDS and FLOAT_ISLAND_SNOW:''',
     '''            if FLOAT_ISLAND_SNOW:          # 雪顶与岩根解耦：关掉岩根仍保留雪顶''',
     "snow_cells_decouple")

# 6) _build 预烘焙渐变档
rep2('''        # 金属/焦土只有一套（不分段）''',
     '''        # 绿->余烬渐变档：按 FADE_STEPS 预烘焙混合 tile（启动一次，运行时直接取）
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
        # 金属/焦土只有一套（不分段）''', "build_fade")

# 7) get 接口支持渐变档
rep2('''    def get_grass(self, depth, seed, green=False):
        return self.grass[(min(5, depth), seed % self.VARIANTS, 1 if green else 0)]''',
     '''    def get_grass(self, depth, seed, green=False, fade=-1):
        d = min(5, depth)
        v = seed % self.VARIANTS
        if fade >= 0:
            return self.fade[(max(0, min(FADE_STEPS, fade)), d, v, 0)]
        return self.grass[(d, v, 1 if green else 0)]''', "get_grass_fade")
rep2('''    def get_dirt(self, depth, seed, green=False):
        return self.dirt[(min(5, depth), (seed * 3 + 1) % self.VARIANTS, 1 if green else 0)]''',
     '''    def get_dirt(self, depth, seed, green=False, fade=-1):
        d = min(5, depth)
        v = (seed * 3 + 1) % self.VARIANTS
        if fade >= 0:
            return self.fade[(max(0, min(FADE_STEPS, fade)), d, v, 1)]
        return self.dirt[(d, v, 1 if green else 0)]''', "get_dirt_fade")

# 8) 渲染端：渐变区取混合档
rep2('''                    green = gx < GREEN_UNTIL
                    # 余烬裂缝密度递进：焦土区强制走"密缝"变体（var>=2）
                    if not green and gx >= core.SCORCH_LEFT:
                        seed |= 2''',
     '''                    green = gx < GREEN_UNTIL
                    # 渐变区：45..61 逐格混合绿/余烬两套 tile
                    fade_lvl = -1
                    if GREEN_UNTIL <= gx < GREEN_UNTIL + FADE_LEN:
                        fade_lvl = int((gx - GREEN_UNTIL) / float(FADE_LEN) * FADE_STEPS)
                    # 余烬裂缝密度递进：焦土区强制走"密缝"变体（var>=2）
                    if not green and gx >= core.SCORCH_LEFT:
                        seed |= 2''', "render_fade_calc")
rep2('''                    else:
                        img = (self.tiles.get_grass(d, seed, green) if d <= 1
                               else self.tiles.get_dirt(d, seed, green))
                        surf.blit(img, (sx, sy))''',
     '''                    else:
                        if fade_lvl >= 0:
                            img = (self.tiles.get_grass(d, seed, green, fade_lvl) if d <= 1
                                   else self.tiles.get_dirt(d, seed, green, fade_lvl))
                        else:
                            img = (self.tiles.get_grass(d, seed, green) if d <= 1
                                   else self.tiles.get_dirt(d, seed, green))
                        surf.blit(img, (sx, sy))''', "render_fade_use")

# 9) 渐变区的草沿/装饰按进度切（前半绿、后半余烬）
rep2('''                _g = gx < GREEN_UNTIL''',
     '''                _g = gx < (GREEN_UNTIL + FADE_LEN // 2)''', "edge_fade_split")
rep2('''                    surf.blit(self.tiles.get_decor(kind, h % 4, green=gx < GREEN_UNTIL),''',
     '''                    surf.blit(self.tiles.get_decor(kind, h % 4, green=gx < (GREEN_UNTIL + FADE_LEN // 2)),''',
     "decor_fade_split")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_v3_log.txt", "w", encoding="utf-8").write(" | ".join(log) + " || " + " | ".join(log2))
print("done")
