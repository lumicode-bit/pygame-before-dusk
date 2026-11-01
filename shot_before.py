import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
import pygame
import main as M
import game_core as core


class FK:
    def __getattr__(self, k):
        return False

    def __getitem__(self, k):
        return False


T = core.TILE
app = M.App()
app.dt = 1 / 60
app.start_single(0)
app._apply_scene("GAME")
app.post.fade = 0
app.tutorial_done = True
eng = M.engine
eng.monsters.clear(); eng.wave1_spawned = True; eng.rifts = []

# Boss 特写
b = core.Monster(1, "boss", 144 * T, 15 * T)
b.state = "walk"
eng.monsters.append(b)
eng.players[0]["x"], eng.players[0]["y"] = 140 * T, 15 * T
eng.players[1]["x"], eng.players[1]["y"] = 141 * T, 15 * T
for _ in range(30):
    app.scene_game([], FK(), (640, 360))
pygame.image.save(app.screen, "shots/50_boss_now.png")

# 森林悬浮平台（看岛底）
eng.monsters.clear()
eng.players[0]["x"], eng.players[0]["y"] = 25 * T, 13 * T
eng.players[1]["x"], eng.players[1]["y"] = 26 * T, 13 * T
for _ in range(6):
    app.scene_game([], FK(), (640, 360))
    app.cam.snap(24 * T, 470, (core.WORLD_W, core.WORLD_H))
for _ in range(2):
    app.scene_game([], FK(), (640, 360))
pygame.image.save(app.screen, "shots/51_islands_now.png")

# 塔（多层悬浮）
eng.players[0]["x"], eng.players[0]["y"] = 100 * T, 11 * T
for _ in range(6):
    app.scene_game([], FK(), (640, 360))
    app.cam.snap(100 * T, 330, (core.WORLD_W, core.WORLD_H))
for _ in range(2):
    app.scene_game([], FK(), (640, 360))
pygame.image.save(app.screen, "shots/52_tower_now.png")
print("ok")
