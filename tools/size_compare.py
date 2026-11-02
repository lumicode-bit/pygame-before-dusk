# -*- coding: utf-8 -*-
"""同比例尺对比：玩家 / 旧Boss(熔炉守卫) / 树怪Boss，共用地平线 + 32px 网格。"""
import os
import sys
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pygame
pygame.init()
pygame.display.set_mode((64, 64))
import sprites

TILE = 32

def tight(surf):
    al = pygame.surfarray.array_alpha(surf)   # shape (w, h)
    wi, hi = (al > 0).nonzero()
    x0, x1 = int(wi.min()), int(wi.max())
    y0, y1 = int(hi.min()), int(hi.max())
    return x0, y0, x1 - x0 + 1, y1 - y0 + 1

player = sprites.get_char("archer", "idle0", 0)
boss = sprites.get_monster("boss", "walk0")
tree = pygame.image.load("shots/demo_treeboss.png")

items = [("PLAYER", player, (200, 210, 230)),
         ("OLD BOSS", boss, (255, 170, 110)),
         ("TREE BOSS", tree, (150, 220, 150))]

# 打印精确数据
print("名称                画布        实体(w x h)      格(w x h)")
for name, s, _ in items:
    x, y, w, h = tight(s)
    print(f"{name:16s} {str(s.get_size()):12s} {w:3d}x{h:3d}px      {w/TILE:.2f}x{h/TILE:.2f}")

_, _, pw, ph = tight(player)
_, _, bw, bh = tight(boss)
_, _, tw, th = tight(tree)
print()
print(f"树怪 / 旧Boss : 宽 {tw/bw:.2f}x  高 {th/bh:.2f}x  面积 {(tw*th)/(bw*bh):.2f}x")
print(f"树怪 / 玩家   : 宽 {tw/pw:.2f}x  高 {th/ph:.2f}x")
print(f"旧Boss / 玩家 : 宽 {bw/pw:.2f}x  高 {bh/ph:.2f}x")

# ---- 画对比图 ----
Z = 2                      # 整体 2x，便于看清
GROUND = 360               # 地平线（1x 坐标）
W1 = 720
H1 = 420
scene = pygame.Surface((W1, H1))
# 天空渐变
for i in range(GROUND):
    k = i / GROUND
    scene.fill((int(30 + 22 * k), int(28 + 16 * k), int(46 + 20 * k)), (0, i, W1, 1))
# 地面
scene.fill((58, 50, 40), (0, GROUND, W1, H1 - GROUND))
scene.fill((92, 80, 64), (0, GROUND, W1, 3))
# 32px 网格（竖线）+ 横向格线，直观看出"格"
for gx in range(0, W1, TILE):
    pygame.draw.line(scene, (40, 36, 34), (gx, GROUND), (gx, H1), 1)
for gy in range(GROUND, H1, TILE):
    pygame.draw.line(scene, (40, 36, 34), (0, gy), (W1, gy), 1)
for gx in range(0, W1, TILE):
    pygame.draw.line(scene, (46, 44, 58), (gx, 0), (gx, GROUND), 1)
for gy in range(0, GROUND, TILE):
    pygame.draw.line(scene, (46, 44, 58), (0, gy), (W1, gy), 1)

# 摆放（midbottom 对齐地平线）
pos = [(70, player), (210, boss), (470, tree)]
for cx, s in pos:
    r = s.get_rect(midbottom=(cx, GROUND))
    scene.blit(s, r)

# 标注：高度刻度线
font = pygame.font.Font(None, 20)
for cx, s, (name, _, col) in zip([p[0] for p in pos], [p[1] for p in pos], items):
    _, _, w, h = tight(s)
    top = GROUND - h
    pygame.draw.line(scene, col, (cx - w // 2 - 8, top), (cx - w // 2 - 8, GROUND), 1)
    lab = font.render(f"{h}px / {h/TILE:.1f} tiles", True, col)
    scene.blit(lab, (cx - w // 2 - 8, top - 16))

lab = font.render("OLD BOSS", True, (255, 170, 110))
scene.blit(lab, (210 - 20, GROUND + 8))
lab = font.render("PLAYER", True, (200, 210, 230))
scene.blit(lab, (70 - 12, GROUND + 8))
lab = font.render("TREE BOSS", True, (150, 220, 150))
scene.blit(lab, (470 - 16, GROUND + 8))

big = pygame.transform.scale(scene, (W1 * Z, H1 * Z))
out = os.path.join("shots", "size_compare.png")
pygame.image.save(big, out)
print("saved", out, big.get_size())
