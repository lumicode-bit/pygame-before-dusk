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

# 场景1：第一波裂隙刚开（进度约 70%，最漂亮）
eng._spawn_wave(1)
for i in range(2):
    r = eng.rifts[i]
    r["t"] = r["delay"] * 0.72
eng.players[0]["x"] = 20 * T
eng.players[0]["y"] = 19 * T
eng.players[1]["x"] = 24 * T
eng.players[1]["y"] = 19 * T
for _ in range(3):
    app.scene_game([], FK(), (640, 360))
    app.cam.snap(21 * T, 500, (core.WORLD_W, core.WORLD_H))
pygame.image.save(app.screen, "shots/37_rift.png")

# 场景2：裂隙全开 + 怪物从里面走出来（出场动画中段）
for r in eng.rifts:
    r["t"] = r["delay"]
app.scene_game([], FK(), (640, 360))
for m in eng.monsters:
    if m.state == "spawn":
        m.state_t = 0.28
for _ in range(2):
    app.scene_game([], FK(), (640, 360))
    app.cam.snap(21 * T, 500, (core.WORLD_W, core.WORLD_H))
pygame.image.save(app.screen, "shots/38_spawn.png")

# 场景3：飞怪悬在玩家头顶（含俯冲）
eng.rifts = []
eng.monsters.clear()
fly = core.Monster(9001, "fly", 22 * T, 9 * T)
eng.monsters.append(fly)
fly.atk_cd = 99.0        # 先悬停，不俯冲
eng.players[0]["x"] = 22 * T
eng.players[0]["y"] = 19 * T
for _ in range(90):
    app.scene_game([], FK(), (640, 360))
    app.cam.snap(22 * T, 470, (core.WORLD_W, core.WORLD_H))
print("飞怪相对玩家: dx=%.0f dy=%.0f (应约 -180，即头顶上方)" % (fly.x - eng.players[0]["x"],
                                                          eng.players[0]["y"] - fly.y))
pygame.image.save(app.screen, "shots/39_fly_hover.png")

# 场景4：俯冲瞬间
fly.atk_cd = 0.0
fly.state = "hover"
for _ in range(18):
    app.scene_game([], FK(), (640, 360))
    app.cam.snap(22 * T, 470, (core.WORLD_W, core.WORLD_H))
print("俯冲中 state=%s dy=%.0f" % (fly.state, eng.players[0]["y"] - fly.y))
pygame.image.save(app.screen, "shots/40_fly_dive.png")
print("ok")
