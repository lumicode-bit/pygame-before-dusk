import os, traceback
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
try:
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
    eng.players[0]["x"], eng.players[0]["y"] = 25 * T, 13 * T
    eng.players[1]["x"], eng.players[1]["y"] = 26 * T, 13 * T
    for _ in range(8):
        app.scene_game([], FK(), (640, 360))
        app.cam.snap(24 * T, 470, (core.WORLD_W, core.WORLD_H))
    for _ in range(2):
        app.scene_game([], FK(), (640, 360))
    pygame.image.save(app.screen, "shots/63_forest_v3c.png")
    print("forest ok")
except Exception:
    traceback.print_exc()
