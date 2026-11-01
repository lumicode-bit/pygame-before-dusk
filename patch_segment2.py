# -*- coding: utf-8 -*-
"""分段世界第二批：渲染端接线（green 分段、雪顶格子、藤蔓复绿、浮岛按段启用）。"""
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


# ---- 1) grass/dirt 分支：green 分段 + 悬浮平台雪顶格子 + 焦土密缝只对余烬段 ----
rep('''                if c in ('G', 'S', 's'):
                    d = self._depth(gx, gy, solid)
                    dj = min(d, self.tiles.DEPTHS - 1)
                    # 余烬裂缝密度递进：焦土区强制走"密缝"变体（var>=2）
                    if gx >= core.SCORCH_LEFT:
                        seed |= 2
                    if gx >= core.FORGE_LEFT:
                        surf.blit(self.tiles.metal[(dj, seed % self.tiles.VARIANTS)], (sx, sy))
                    elif gx >= core.SCORCH_LEFT:
                        surf.blit(self.tiles.scorch[(dj, seed % self.tiles.VARIANTS)], (sx, sy))
                    else:
                        img = self.tiles.get_grass(d, seed) if d <= 1 else self.tiles.get_dirt(d, seed)
                        surf.blit(img, (sx, sy))''',
    '''                if c in ('G', 'S', 's'):
                    d = self._depth(gx, gy, solid)
                    dj = min(d, self.tiles.DEPTHS - 1)
                    green = gx < GREEN_UNTIL
                    # 余烬裂缝密度递进：焦土区强制走"密缝"变体（var>=2）
                    if not green and gx >= core.SCORCH_LEFT:
                        seed |= 2
                    if gx >= core.FORGE_LEFT:
                        surf.blit(self.tiles.metal[(dj, seed % self.tiles.VARIANTS)], (sx, sy))
                    elif gx >= core.SCORCH_LEFT:
                        surf.blit(self.tiles.scorch[(dj, seed % self.tiles.VARIANTS)], (sx, sy))
                    elif (gx, gy) in self._snow_cells:
                        # 绿意段的悬浮平台：雪暮顶
                        img = self.tiles.snow[(min(d, 1), seed % self.tiles.VARIANTS)] if d <= 1 \\
                            else self.tiles.snow[(min(d, self.tiles.DEPTHS - 1), seed % self.tiles.VARIANTS)]
                        surf.blit(img, (sx, sy))
                    else:
                        img = (self.tiles.get_grass(d, seed, green) if d <= 1
                               else self.tiles.get_dirt(d, seed, green))
                        surf.blit(img, (sx, sy))''',
    "terrain_grass_seg")

# ---- 2) Q 压板格同样接 green ----
rep('''                    elif d <= 1:
                        surf.blit(self.tiles.get_grass(d, seed), (sx, sy))
                    else:
                        surf.blit(self.tiles.get_dirt(d, seed), (sx, sy))
                    self._draw_plate_tile(surf, sx, sy, self.time)''',
    '''                    else:
                        _g2 = gx < GREEN_UNTIL
                        if d <= 1:
                            surf.blit(self.tiles.get_grass(d, seed, _g2), (sx, sy))
                        else:
                            surf.blit(self.tiles.get_dirt(d, seed, _g2), (sx, sy))
                    self._draw_plate_tile(surf, sx, sy, self.time)''',
    "terrain_plate_seg")

# ---- 3) 草叶/装饰调用传 green ----
rep('''                if gx >= core.FORGE_LEFT:
                    surf.blit(self.tiles.get_metal_edge(seed),
                              (gx * TILE - cam_x, gy * TILE - cam_y - 8))
                elif gx >= core.SCORCH_LEFT:
                    surf.blit(self.tiles.get_edge(seed, scorch=True),
                              (gx * TILE - cam_x, gy * TILE - cam_y - 4))
                else:
                    surf.blit(self.tiles.get_edge(seed), (gx * TILE - cam_x, gy * TILE - cam_y - 4))''',
    '''                _g = gx < GREEN_UNTIL
                if gx >= core.FORGE_LEFT:
                    surf.blit(self.tiles.get_metal_edge(seed),
                              (gx * TILE - cam_x, gy * TILE - cam_y - 8))
                elif gx >= core.SCORCH_LEFT:
                    surf.blit(self.tiles.get_edge(seed, scorch=True),
                              (gx * TILE - cam_x, gy * TILE - cam_y - 4))
                else:
                    surf.blit(self.tiles.get_edge(seed, green=_g),
                              (gx * TILE - cam_x, gy * TILE - cam_y - 4))''',
    "edge_call_seg")

rep('''                    surf.blit(self.tiles.get_decor(kind, h % 4),
                              (gx * TILE - cam_x, gy * TILE - cam_y - 16))''',
    '''                    surf.blit(self.tiles.get_decor(kind, h % 4, green=gx < GREEN_UNTIL),
                              (gx * TILE - cam_x, gy * TILE - cam_y - 16))''',
    "decor_call_seg")

# ---- 4) _snow_cells 计算并缓存（在 _draw_terrain 开头）----
rep('''    def _draw_terrain(self, surf, grid, cam_x, cam_y, st, rocks_state):
        if not grid:
            return
        gx0 = max(0, cam_x // TILE - 1)''',
    '''    def _draw_terrain(self, surf, grid, cam_x, cam_y, st, rocks_state):
        if not grid:
            return
        # 绿意段悬浮平台的格子集合：这些格用雪暮 tile（懒计算，grid 不变则复用）
        if not hasattr(self, "_snow_cells_key") or self._snow_cells_key != id(grid):
            self._snow_cells_key = id(grid)
            cells = set()
            if FLOAT_ISLANDS and FLOAT_ISLAND_SNOW:
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
        gx0 = max(0, cam_x // TILE - 1)''',
    "snow_cells")

# ---- 5) 藤蔓复绿（恢复原配色）----
rep('''                # 余烬世界的藤 = 枯藤：暗褐主干，挂住时流暖橙光
                pygame.draw.lines(surf, (30, 26, 26), False, pts, 5)
                pygame.draw.lines(surf, (88, 66, 52) if not hot else (150, 96, 54), False, pts, 3)
                pygame.draw.lines(surf, (128, 96, 66) if not hot else (255, 176, 92), False, pts, 1)''',
    '''                # 开局绿意段的藤 = 原版绿藤（挂住时亮绿流光）
                pygame.draw.lines(surf, (32, 48, 30), False, pts, 5)
                pygame.draw.lines(surf, (74, 112, 60) if not hot else (110, 158, 78), False, pts, 3)
                pygame.draw.lines(surf, (120, 166, 88) if not hot else (186, 232, 130), False, pts, 1)''',
    "vines_green_stem")
rep("                    pygame.draw.polygon(surf, (58, 48, 40), leaf)",
    "                    pygame.draw.polygon(surf, (52, 82, 44), leaf)", "vines_green_leaf")
rep("                    pygame.draw.polygon(surf, (96, 76, 58) if not hot else (196, 128, 70), inner)",
    "                    pygame.draw.polygon(surf, (108, 158, 76) if not hot else (150, 206, 104), inner)",
    "vines_green_inner")
rep('''                pygame.draw.circle(surf, (52, 44, 42), (int(ax), int(ay)), 6, 3)
                pygame.draw.circle(surf, (128, 96, 66), (int(ax), int(ay)), 2)''',
    '''                pygame.draw.circle(surf, (58, 74, 52), (int(ax), int(ay)), 6, 3)
                pygame.draw.circle(surf, (132, 172, 96), (int(ax), int(ay)), 2)''',
    "vines_green_anchor")
rep("pygame.draw.arc(surf, (78, 62, 50),",
    "pygame.draw.arc(surf, (86, 126, 66),", "vines_green_arc")

# ---- 6) 浮岛按段启用 + 雪暮调色 ----
rep('''        if not FLOAT_ISLANDS:
            return
        if not hasattr(self, "_island_cache"):''',
    '''        if not FLOAT_ISLANDS:
            return
        # 只画绿意段的浮岛（雪暮顶）；余烬段不画
        if not hasattr(self, "_island_cache"):''',
    "islands_gate_doc")
rep('''        vw = surf.get_width()
        for seg in self._float_bottom_segments(grid):
            try:''',
    '''        vw = surf.get_width()
        for seg in self._float_bottom_segments(grid):
            try:
                if seg[0] >= GREEN_UNTIL:
                    continue''',
    "islands_green_only")

# 烘焙调色：绿意段浮岛固定雪暮
rep('''        c_top, c_mid, c_dark, c_hi = self._island_palette(c0)''',
    '''        if getattr(FLOAT_ISLAND_SNOW, "__class__", None) is bool and FLOAT_ISLAND_SNOW:
            # 雪暮：雪白过渡带 + 蓝灰岩体（不走 tile 采样）
            c_top = (222, 232, 246)
            c_mid = (150, 162, 184)
            c_dark = (96, 106, 130)
            c_hi = (232, 240, 252)
        else:
            c_top, c_mid, c_dark, c_hi = self._island_palette(c0)''',
    "island_snow_palette")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_seg2_log.txt", "w", encoding="utf-8").write(" | ".join(log))
print("done")
