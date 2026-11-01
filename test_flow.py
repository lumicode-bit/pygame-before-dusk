# -*- coding: utf-8 -*-
"""场景流转集成测试：菜单 → 选角 → 游戏 → 暂停 → 设置 → 结算 → 主菜单

不打开窗口（SDL dummy），模拟真实鼠标事件驱动整套状态机，
用于发现"单独测每个场景都正常、串起来就崩"的集成问题。
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

import main as M
import game_core as core

# --- 测试隔离：绝不碰玩家的真实存档 -------------------------------------
# 之前跑测试会把 records.json 的 runs/wins 直接 +1，best_time 还会被
# 写成测试里那个 0.5 秒的假成绩（"历史最佳 0:00"就是这么来的）。
import tempfile as _tf
_TMPDIR = _tf.mkdtemp(prefix="dusk_test_")
M.RECORDS_FILE = os.path.join(_TMPDIR, "records.json")
M.SETTINGS_FILE = os.path.join(_TMPDIR, "settings.json")

FAIL = []


def check(name, cond, detail=""):
    print(("  [PASS] " if cond else "  [FAIL] ") + name + ("  " + detail if detail else ""))
    if not cond:
        FAIL.append(name)


def click(app, pos):
    evs = [pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}),
           pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": pos, "button": 1})]
    return evs


def pump(app, frames=90, pos=(640, 360), dt=1 / 60.0):
    """推进 n 帧（只跑当前场景 + 过场）"""
    keys = pygame.key.get_pressed()
    for _ in range(frames):
        app.dt = dt
        app.t += dt
        app._tick_transition()
        scene = app.scene
        if scene == "MENU":
            app.scene_menu([], keys, pos)
        elif scene == "CHAR_SELECT":
            app.scene_char_select([], keys, pos)
        elif scene == "SETTINGS":
            app.scene_settings([], keys, pos)
        elif scene == "NET_MENU":
            app.scene_net_menu([], keys, pos)
        elif scene == "CLIENT_CONNECT":
            app.scene_client_connect([], keys, pos)
        elif scene == "HOST_WAIT":
            app.scene_host_wait([], keys, pos)
        elif scene == "GAME":
            app.scene_game([], keys, pos)
        elif scene == "PAUSE":
            app.scene_pause([], keys, pos)
        elif scene == "RESULT":
            app.scene_result([], keys, pos)


def main():
    app = M.App()
    app.post.fade = 0.0
    check("启动进入主菜单", app.scene == "MENU")

    # 菜单 -> 选角（点击"单人远征"）
    b = app.menu_buttons[0]
    app.scene_menu(click(app, b.rect.center), pygame.key.get_pressed(), b.rect.center)
    pump(app)
    check("菜单点击进入选角", app.scene == "CHAR_SELECT", app.scene)

    # 选角 -> 游戏（点击左侧卡片）
    evs = click(app, app.card_rects[0].center)
    app.scene_char_select(evs, pygame.key.get_pressed(), app.card_rects[0].center)
    pump(app)
    check("选角后进入游戏", app.scene == "GAME", app.scene)
    check("单人引擎已创建", M.engine is not None and M.single_mode)
    check("世界网格已绑定", app.grid is not None)

    # 跑 120 帧确认不崩、状态推进
    t0 = app.last_st["t"] if app.last_st else 0
    pump(app, 150)
    check("游戏内状态持续推进", app.last_st and app.last_st["t"] > t0,
          "t=%s" % (app.last_st["t"] if app.last_st else "?"))
    check("玩家已落到地面", app.last_st["players"][0]["y"] >= 19 * core.TILE - 2,
          "y=%.0f" % app.last_st["players"][0]["y"])

    # TAB 切换角色
    prev = M.player_pid
    key = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB, "unicode": ""})
    app.scene_game([key], pygame.key.get_pressed(), (640, 360))
    check("Tab 切换操控角色", M.player_pid != prev, "pid=%d" % M.player_pid)

    # ESC -> 暂停
    esc = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE, "unicode": ""})
    app.scene_game([esc], pygame.key.get_pressed(), (640, 360))
    pump(app)
    check("ESC 进入暂停", app.scene == "PAUSE", app.scene)

    # 暂停 -> 设置
    b = app.pause_buttons[1]
    app.scene_pause(click(app, b.rect.center), pygame.key.get_pressed(), b.rect.center)
    pump(app)
    check("暂停进入设置", app.scene == "SETTINGS", app.scene)

    # 设置 -> 返回（应回到暂停）
    b = app.set_back
    app.scene_settings(click(app, b.rect.center), pygame.key.get_pressed(), b.rect.center)
    pump(app)
    check("设置返回暂停", app.scene == "PAUSE", app.scene)

    # 暂停 -> 继续
    b = app.pause_buttons[0]
    app.scene_pause(click(app, b.rect.center), pygame.key.get_pressed(), b.rect.center)
    pump(app)
    check("暂停继续回到游戏", app.scene == "GAME", app.scene)

    # 强制通关 -> 结算
    M.engine.win = True
    M.last_state = None
    pump(app, 120)
    check("通关进入结算", app.scene == "RESULT", app.scene)

    # 结算 -> 再战
    b = app.result_buttons[0]
    app.scene_result(click(app, b.rect.center), pygame.key.get_pressed(), b.rect.center)
    pump(app, 60)
    check("再战回到游戏", app.scene == "GAME", app.scene)
    check("再战已重置关卡", M.engine is not None and not M.engine.win)

    # 暂停 -> 返回主菜单
    app.scene_game([esc], pygame.key.get_pressed(), (640, 360))
    pump(app)
    b = app.pause_buttons[3]
    app.scene_pause(click(app, b.rect.center), pygame.key.get_pressed(), b.rect.center)
    pump(app, 120)
    check("返回主菜单", app.scene == "MENU", app.scene)
    check("联机资源已释放", M.engine is None and M.server is None and M.client is None)

    print()
    if FAIL:
        print("失败项：", FAIL)
        sys.exit(1)
    print("场景流转全部通过。")


if __name__ == "__main__":
    main()
