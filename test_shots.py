# -*- coding: utf-8 -*-
"""离线截图 / 性能自检（不打开窗口）：

    python test_shots.py

产物写入 shots/ 目录，用于人工检查 UI 与画面构图。
"""
import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

import main as M
import game_core as core

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(OUT, exist_ok=True)


def save(app, name):
    pygame.image.save(app.screen, os.path.join(OUT, name))
    print("  saved", name)


def main():
    app = M.App()
    app.dt = 1.0 / 60.0
    keys = pygame.key.get_pressed()
    noop = []

    # 菜单
    app.t = 2.0
    app.scene_menu(noop, keys, (640, 350))
    save(app, "01_menu.png")

    # 角色选择
    app.scene_char_select(noop, keys, (300, 350))
    save(app, "02_char.png")

    # 设置
    app.scene_settings(noop, keys, (640, 400))
    save(app, "03_settings.png")

    # 单人开局
    app.start_single(0)
    app._apply_scene("GAME")
    app.post.fade = 0.0
    app.grid = app.last_st["grid"] if False else app.grid
    for _ in range(90):
        app.scene_game(noop, keys, (700, 360))
    save(app, "04_game_start.png")

    # 中段（岩浆坑）
    eng = M.engine
    eng.players[0]["x"] = 70 * core.TILE
    eng.players[0]["y"] = 19 * core.TILE
    eng.players[1]["x"] = 72 * core.TILE
    eng.players[1]["y"] = 19 * core.TILE
    for _ in range(20):
        app.scene_game(noop, keys, (700, 360))
    save(app, "05_lava.png")

    # 熔炉长廊（新区域）
    eng.players[0]["x"] = 118 * core.TILE
    eng.players[0]["y"] = 19 * core.TILE
    eng.players[1]["x"] = 116 * core.TILE
    eng.players[1]["y"] = 19 * core.TILE
    for _ in range(30):
        app.scene_game(noop, keys, (700, 360))
    save(app, "06_forge.png")

    # 终点祭坛
    eng.players[0]["x"] = 144 * core.TILE
    eng.players[0]["y"] = 15 * core.TILE
    eng.players[1]["x"] = 143 * core.TILE
    eng.players[1]["y"] = 15 * core.TILE
    eng.portal_active = True
    for _ in range(20):
        app.scene_game(noop, keys, (700, 360))
    save(app, "07_portal.png")

    # 帮助层
    app.help_open = True
    app.scene_game(noop, keys, (700, 360))
    save(app, "08_help.png")
    app.help_open = False

    # 暂停
    app._apply_scene("PAUSE")
    app.scene_pause(noop, keys, (640, 360))
    save(app, "09_pause.png")

    # 结算
    app._apply_scene("RESULT")
    app.scene_result(noop, keys, (640, 400))
    save(app, "10_result.png")

    # 性能：绘制 120 帧
    app._apply_scene("GAME")
    eng.players[0]["x"] = 60 * core.TILE
    t0 = time.perf_counter()
    for _ in range(120):
        app.scene_game(noop, keys, (700, 360))
    dt = time.perf_counter() - t0
    print("  render avg: %.2f ms/frame -> %.0f fps" % (dt / 120 * 1000, 120 / dt))
    print("  audio:", __import__("audio").status())
    print("  map: %dx%d world=%dpx" % (core.MAP_W, core.MAP_H, core.WORLD_W))


if __name__ == "__main__":
    main()
