import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
import pygame
import main as M
import game_core as core


class FK:
    def __getattr__(self, k):
        return False


app = M.App()
app.dt = 1 / 60
app.start_single(0)
app._apply_scene("GAME")
app.post.fade = 0
eng = M.engine
eng.monsters.clear(); eng.wave1_spawned = True
app.tutorial_done = True

# 森林藤蔓：站在绳上
v = core.VINES[0]
eng.players[0]["vine"] = 0
eng.players[0]["vine_t"] = 0.5
eng.players[1]["x"], eng.players[1]["y"] = 480, 19 * core.TILE
for i in range(24):
    app.scene_game([], FK(), (640, 360))
    app.cam.snap(500, 470, (core.WORLD_W, core.WORLD_H))
pygame.image.save(app.screen, "shots/35_vine_fixed.png")

# 塔内两条藤蔓
eng.players[0]["vine"] = -1
eng.players[0]["x"], eng.players[0]["y"] = 3090, 480
for i in range(24):
    app.scene_game([], FK(), (640, 360))
    app.cam.snap(3150, 400, (core.WORLD_W, core.WORLD_H))
pygame.image.save(app.screen, "shots/36_tower_vines.png")
print("ok")
