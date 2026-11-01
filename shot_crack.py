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
app = M.App(); app.dt = 1 / 60
app.start_single(0); app._apply_scene("GAME"); app.post.fade = 0
app.tutorial_done = True
eng = M.engine
eng.monsters.clear(); eng.wave1_spawned = True; eng.rifts = []
r = next(x for x in eng._fall_rocks if x["id"] == "F3")
print("F3 land_y =", r["land_y"], " y0 =", r["y0"])

# 让玩家站在 F3 下方触发
eng.players[0]["x"], eng.players[0]["y"] = r["x"] - 20, 15 * T
eng.players[1]["x"], eng.players[1]["y"] = r["x"] + 40, 15 * T

# 推进到 open 中段
for _ in range(26):
    app.scene_game([], FK(), (640, 360))
    app.cam.snap(r["x"], 15 * T - 40, (core.WORLD_W, core.WORLD_H))
for _ in range(2):
    app.scene_game([], FK(), (640, 360))
print("state =", r["state"], " open_t =", round(r["open_t"], 2))
pygame.image.save(app.screen, "shots/57_crack_open.png")

# 推进到 fall 中段
for _ in range(14):
    app.scene_game([], FK(), (640, 360))
    app.cam.snap(r["x"], 15 * T - 40, (core.WORLD_W, core.WORLD_H))
for _ in range(2):
    app.scene_game([], FK(), (640, 360))
print("state =", r["state"], " y =", round(r["y"]))
pygame.image.save(app.screen, "shots/58_crack_fall.png")
