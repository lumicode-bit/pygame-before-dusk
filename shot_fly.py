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
eng.monsters.clear()
eng.wave1_spawned = True
eng.rifts = []
eng.players[0]["x"], eng.players[0]["y"] = 22 * T, 19 * T
eng.players[1]["x"], eng.players[1]["y"] = 24 * T, 19 * T

# 三只飞怪，分别悬停/俯冲，看是否都在头顶
flies = []
for i, px in enumerate((18, 22, 26)):
    f = core.Monster(9100 + i, "fly", px * T, 9 * T)
    f.atk_cd = 999.0 if i < 2 else 0.0
    eng.monsters.append(f)
    flies.append(f)

for _ in range(150):        # 不手动 snap，让相机自然跟随
    app.scene_game([], FK(), (640, 360))

print("cam.px,py = (%.0f, %.0f)" % (app.cam.px, app.cam.py))
for f in flies:
    print("fly x=%.0f y=%.0f state=%-5s dy=%.0f 视口=(%.0f,%.0f)"
          % (f.x, f.y, f.state, eng.players[0]["y"] - f.y,
             f.x - app.cam.px, f.y - app.cam.py))
pygame.image.save(app.screen, "shots/42_fly_check.png")
