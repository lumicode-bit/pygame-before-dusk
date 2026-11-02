# -*- coding: utf-8 -*-
"""离线验证：树精 Boss / 扔蛋 / 紫色爆炸 / 死亡焕发生机 / 岩浆小 Boss / 盾卫格挡。
产物写入 shots/boss_*.png。不打开窗口。"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame
import main as M
import game_core as core

OUT = os.path.join(ROOT, "shots")
os.makedirs(OUT, exist_ok=True)

app = M.App()
app.dt = 1.0 / 60.0
keys = pygame.key.get_pressed()
noop = []


def frames(n):
    for _ in range(n):
        app.scene_game(noop, keys, (640, 360))


def save(name):
    pygame.image.save(app.screen, os.path.join(OUT, name))
    print("  saved", name)


app.start_single(0)
app._apply_scene("GAME")
app.post.fade = 0.0
eng = M.engine

# 把两人放上祭坛
for pid in (0, 1):
    eng.players[pid]["x"] = (162 + pid) * core.TILE
    eng.players[pid]["y"] = 15 * core.TILE
    eng.players[pid]["hp"] = 100

frames(20)

# ---- 召唤树精（跳过波次直接触发）----
eng.wave = 3
eng._spawn_boss()
frames(160)          # 裂隙 1.9s + 出场
tree = next((m for m in eng.monsters if m.kind == "tree"), None)
print("tree spawned:", tree is not None, "monsters:", len(eng.monsters))
if tree:
    print("  tree x,y=", int(tree.x), int(tree.y), "hp=", int(tree.hp))
    # 让树精立刻扔蛋
    tree.egg_cd = 0.0
frames(8)
print("eggs in flight:", len(eng.eggs))
frames(6)
save("boss_1_windup.png")
frames(24)
save("boss_2_egg.png")
frames(40)
save("boss_3_explosion.png")

# ---- 杀死树精 -> 焕发生机 ----
if tree and tree in eng.monsters:
    tree.hp = 0
frames(18)
save("boss_4_bloom_a.png")
frames(70)
save("boss_5_bloom_b.png")
print("blooms:", len(eng.blooms))

# ---- 岩浆小 Boss ----
for pid in (0, 1):
    eng.players[pid]["x"] = (core.LAVA_LEFT + 8) * core.TILE
    eng.players[pid]["y"] = 19 * core.TILE
    eng.players[pid]["hp"] = 100
eng.wave = 2
eng.lava_boss_spawned = False
eng.lava_boss_dead = False
frames(120)
lb = [m for m in eng.monsters if m.kind == "boss" and m.lava]
print("lava boss:", len(lb), ("y=%d" % int(lb[0].y)) if lb else "")
save("boss_6_lava.png")

# ---- 盾卫举盾（挪到左侧空旷地面，避免被 Boss 挡住）----
for pid in (0, 1):
    eng.players[pid]["blocking"] = False
eng.players[1]["x"] = 50 * core.TILE
eng.players[1]["y"] = 19 * core.TILE
eng.players[1]["blocking"] = True
eng.players[0]["x"] = 47 * core.TILE
eng.players[0]["y"] = 19 * core.TILE
frames(6)
save("boss_7_shield.png")
# 放大裁剪盾卫区域，检查盾牌细节
try:
    scr = app.screen
    # 盾卫大致屏幕位置：按相机换算
    cam = app.cam if hasattr(app, "cam") else None
    if cam is not None:
        SC = app.screen.get_width() / float(M.WORLD_VW)
        gx = int((eng.players[1]["x"] - cam.px) * SC)
        gy = int((eng.players[1]["y"] - cam.py) * SC)
        crop = pygame.Surface((130, 130))
        crop.blit(scr, (0, 0), (gx - 65, gy - 100, 130, 130))
        big = pygame.transform.scale(crop, (520, 520))
        pygame.image.save(big, os.path.join(OUT, "boss_7_shield_zoom.png"))
        print("  saved boss_7_shield_zoom.png")
except Exception as e:
    print("zoom skip:", e)

print("done")
