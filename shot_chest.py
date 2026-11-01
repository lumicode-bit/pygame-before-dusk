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

shots = [
    ("05_chest_C4", 18 * T, 13 * T, 17 * T + 40),   # 森林上层平台
    ("05_chest_C5", 74 * T, 13 * T, 17 * T + 40),   # 岩浆上层
    ("05_chest_C6", 101 * T, 15 * T, 17 * T + 10),  # 塔 F1
    ("05_chest_C7", 100 * T, 11 * T, 13 * T + 10),  # 塔 F2
    ("05_chest_C3", 129 * T, 19 * T, 21 * T - 40),  # 熔炉地面
]
for name, px, py, camy in shots:
    eng.players[0]["x"], eng.players[0]["y"] = px, py
    eng.players[1]["x"], eng.players[1]["y"] = px + 40, py
    for _ in range(3):
        app.scene_game([], FK(), (640, 360))
    app.cam.snap(px, camy, (core.WORLD_W, core.WORLD_H))
    for _ in range(2):
        app.scene_game([], FK(), (640, 360))
        app.cam.snap(px, camy, (core.WORLD_W, core.WORLD_H))
    pygame.image.save(app.screen, "shots/%s.png" % name)
    print("%s: 箱子 gy 附近相机 y=%.0f" % (name, camy))
print("ok")
