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
    app = M.App(); app.dt = 1 / 60
    app.start_single(0); app._apply_scene("GAME"); app.post.fade = 0
    app.tutorial_done = True
    eng = M.engine
    eng.monsters.clear(); eng.wave1_spawned = True; eng.rifts = []

    shots = [("75_fade_mid.png", 52, "渐变中段"), ("76_green_snow.png", 24, "绿段雪顶")]
    for name, col, _ in shots:
        eng.players[0]["x"], eng.players[0]["y"] = col * T, 19 * T
        eng.players[1]["x"], eng.players[1]["y"] = col * T + 40, 19 * T
        for _ in range(8):
            app.scene_game([], FK(), (640, 360))
            app.cam.snap(col * T, 520, (core.WORLD_W, core.WORLD_H))
        for _ in range(2):
            app.scene_game([], FK(), (640, 360))
        pygame.image.save(app.screen, "shots/" + name)
        print(name, "ok")
except Exception:
    traceback.print_exc()
