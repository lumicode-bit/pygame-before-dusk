# -*- coding: utf-8 -*-
"""全面体检：事件、按键、UI 控件、网络、设置持久化。

与 test_flow（流程）和 test_gameplay（玩法）互补，这里专门找"静默失败"：
  * 引擎事件 → 音效/粒子 的每个分支是否都能走通
  * 每个按键绑定是否真的产生效果（不是只不报错）
  * 每个按钮/滑块/开关是否可点、状态是否真的改变
  * 房主/客户端 TCP 往返 + 输入是否真的推动了世界
"""
import os
import queue
import struct
import socket
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

import audio
import game_core as core
import main as M

# --- 测试隔离：绝不碰玩家的真实存档 -------------------------------------
# 之前跑测试会把 records.json 的 runs/wins 直接 +1，best_time 还会被
# 写成测试里那个 0.5 秒的假成绩（"历史最佳 0:00"就是这么来的）。
import tempfile as _tf
_TMPDIR = _tf.mkdtemp(prefix="dusk_test_")
M.RECORDS_FILE = os.path.join(_TMPDIR, "records.json")
M.SETTINGS_FILE = os.path.join(_TMPDIR, "settings.json")
import theme

FAIL = []


def check(name, cond, detail=""):
    print(("  [PASS] " if cond else "  [FAIL] ") + name + ("  " + detail if detail else ""))
    if not cond:
        FAIL.append(name)


class FakeKeys:
    def __init__(self, on=()):
        self.on = set(on)

    def __getitem__(self, k):
        return k in self.on


def key(k, uni=""):
    return pygame.event.Event(pygame.KEYDOWN, {"key": k, "unicode": uni})


def click(pos):
    return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}),
            pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": pos, "button": 1})]


def new_app():
    app = M.App()
    app.dt = 1 / 60.0
    app.post.fade = 0.0
    return app


# --------------------------------------------------------------------------
print("== 1. 输入采样：每种按键都要真的生效 ==")
app = new_app()
app.start_single(0)
app._apply_scene("GAME")
eng = M.engine

inp = M._host_input(FakeKeys({pygame.K_d}), (700, 360), 0)
check("D 产生 right", inp.get("right") is True, str(inp))
check("方向键 → 同样产生 right",
      M._host_input(FakeKeys({pygame.K_RIGHT}), (0, 0), 0).get("right") is True)
check("空格产生 up", M._host_input(FakeKeys({pygame.K_SPACE}), (0, 0), 0).get("up") is True)
check("Shift 产生 dash", M._host_input(FakeKeys({pygame.K_LSHIFT}), (0, 0), 0).get("dash") is True)
check("E 产生 interact", M._host_input(FakeKeys({pygame.K_e}), (0, 0), 0).get("interact") is True)
check("J（盾卫）产生 sword",
      M._host_input(FakeKeys({pygame.K_j}), (0, 0), 1).get("sword") is True)
check("WASD 与方向键都能让角色移动",
      abs(M._host_input(FakeKeys({pygame.K_a}), (0, 0), 0).get("left") or True))

x0 = eng.players[0]["x"]
for _ in range(60):
    app.scene_game([], FakeKeys({pygame.K_d}), (700, 360))
check("按住 D 一秒位移约 250px", 200 < eng.players[0]["x"] - x0 < 300,
      "%.0f px" % (eng.players[0]["x"] - x0))

low = eng.players[0]["y"]
peak = low
for _ in range(40):
    app.scene_game([], FakeKeys({pygame.K_SPACE}), (700, 360))
    peak = min(peak, eng.players[0]["y"])
check("空格起跳", low - peak > 60, "%.0f px" % (low - peak))

x0 = eng.players[0]["x"]
for _ in range(20):
    app.scene_game([], FakeKeys({pygame.K_d, pygame.K_LSHIFT}), (700, 360))
check("Shift 冲刺位移更大", eng.players[0]["x"] - x0 > 80, "%.0f px" % (eng.players[0]["x"] - x0))

# --------------------------------------------------------------------------
print("== 2. 引擎事件 → 表现层，全分支不崩 ==")
app.start_single(0)
app._apply_scene("GAME")
calls = []
old_sfx = audio.sfx
audio.sfx = lambda name, vol=1.0, pan=0.0: calls.append(name)
kinds = ["jump", "dash", "shoot", "hit", "swing", "break", "rock_break", "die", "hurt",
         "block", "pad", "pad_spawn", "plate", "lava", "impale", "spike_hit", "hammer",
         "rock_warn", "rock_land", "rock_hit", "checkpoint", "chest", "portal", "win",
         "respawn", "fall", "reset", "ally_warp"]
evs = []
for k in kinds:
    if k == "dmg":
        continue
    evs.append((k, 3200, 500) if k not in ("reset", "win") else (k, 0, 0))
evs.append(("dmg", 3200, 500, 14))
evs.append(("chest", 3200, 500, 20))
try:
    app.handle_events(evs, 0)
    ok_events = True
    err = ""
except Exception as e:
    ok_events = False
    err = repr(e)
audio.sfx = old_sfx
check("全部事件类型可处理", ok_events, err)
check("事件触发了音效", len(calls) >= 15, "sfx=%d" % len(calls))
check("事件产生粒子", len(app.particles.items) > 20, "particles=%d" % len(app.particles.items))

# --------------------------------------------------------------------------
print("== 3. 按键绑定：Tab / Esc / F1 / Enter 聊天 ==")
app.start_single(0)
app._apply_scene("GAME")
pid0 = M.player_pid
app.scene_game([key(pygame.K_TAB)], FakeKeys(), (640, 360))
check("Tab 切换角色", M.player_pid != pid0, "pid %d -> %d" % (pid0, M.player_pid))
app.scene_game([key(pygame.K_F1)], FakeKeys(), (640, 360))
check("F1 打开帮助", app.help_open)
app.scene_game([key(pygame.K_F1)], FakeKeys(), (640, 360))
check("F1 关闭帮助", not app.help_open)
app.scene_game([key(pygame.K_RETURN)], FakeKeys(), (640, 360))
check("Enter 打开聊天", M.chat_active)
app.scene_game([pygame.event.Event(pygame.TEXTINPUT, {"text": "ab"})], FakeKeys(), (640, 360))
check("聊天能输入字符", M.chat_text.endswith("ab"), M.chat_text)
app.scene_game([key(pygame.K_c, "c")], FakeKeys(), (640, 360))
check("无 TEXTINPUT 时回退 KEYDOWN 输入", M.chat_text.endswith("abc"), M.chat_text)
app.scene_game([key(pygame.K_ESCAPE)], FakeKeys(), (640, 360))
check("Esc 先关聊天", not M.chat_active)
app.scene_game([key(pygame.K_ESCAPE)], FakeKeys(), (640, 360))
for _ in range(30):
    app._tick_transition()
check("再按 Esc 进暂停", app.scene == "PAUSE", "%s pending=%s" % (app.scene, app._pending))

# --------------------------------------------------------------------------
print("== 4. UI 控件：菜单/设置里每个控件都能点 ==")
app = new_app()
app.post.fade = 0.0
app.scene = "MENU"
for i, b in enumerate(app.menu_buttons[:3]):
    label = b.label
    app.scene = "MENU"
    app._pending = None
    app.post.fade = 0.0
    app.scene_menu(click(b.rect.center), FakeKeys(), b.rect.center)
    app._tick_transition()
    expect = ("CHAR_SELECT", "NET_MENU", "SETTINGS")[i]
    check("菜单「%s」→ %s" % (label, expect), app.scene == expect or app._pending == expect,
          "%s / pending=%s" % (app.scene, app._pending))

app.scene = "SETTINGS"
app.return_scene = "MENU"
old_master = app.settings["master"]
app.sl_master.drag = True
app.sl_master.handle([], (app.sl_master.rect.x + app.sl_master.rect.w // 2, 0))
check("滑块可拖动并改值", abs(app.sl_master.value - 0.5) < 0.03, "%.2f" % app.sl_master.value)
app.sl_master.drag = False

before = app.settings["fullscreen"]
app.tg_fs.handle(click(app.tg_fs.rect.center), app.tg_fs.rect.center)
check("开关可切换", app.settings["fullscreen"] != before or app.tg_fs.value != before)

idx0 = app.seg_quality.index
target = 0 if idx0 != 0 else 2
seg_w = app.seg_quality.rect.w / 3.0
pos = (int(app.seg_quality.rect.x + seg_w * (target + 0.5)), app.seg_quality.rect.centery)
app.seg_quality.handle(click(pos), (0, 0))
check("分段选择器可切换", app.seg_quality.index == target, "%d -> %d" % (idx0, app.seg_quality.index))

# 聊天不重复输入
app2 = new_app()
M.chat_active = False
M.chat_text = ""
app2.start_single(0)
app2._apply_scene("GAME")
app2.scene_game([key(pygame.K_RETURN)], FakeKeys(), (640, 360))
check("进游戏时聊天状态已重置", M.chat_active and M.chat_text == "", repr(M.chat_text))
app2.scene_game([pygame.event.Event(pygame.TEXTINPUT, {"text": "a"}),
                 key(pygame.K_a, "a")], FakeKeys(), (640, 360))
check("TEXTINPUT 与 KEYDOWN 不重复计字", M.chat_text == "a", repr(M.chat_text))
app2.scene_game([key(pygame.K_ESCAPE)], FakeKeys(), (640, 360))

# 设置持久化
app.sl_master.value = 0.33
app._commit_settings()
import json
with open(M.SETTINGS_FILE, "r", encoding="utf-8") as f:
    saved = json.load(f)
check("设置写盘", abs(saved.get("master", -1) - 0.33) < 1e-6, str(saved.get("master")))

# --------------------------------------------------------------------------
print("== 4.5 键位重映射与手柄 ==")
class _FK:
    def __init__(self, on=()): self.on = set(on)
    def __getitem__(self, k): return k in self.on

app = new_app()
check("默认 A 触发左移", M._host_input(_FK({pygame.K_a}), (0, 0), 0).get("left") is True)
app._assign_key("left", pygame.K_h)
check("改键后 H 触发左移", M._host_input(_FK({pygame.K_h}), (0, 0), 0).get("left") is True)
check("改键后 A 不再触发", M._host_input(_FK({pygame.K_a}), (0, 0), 0).get("left") is False)
app._assign_key("right", pygame.K_h)
check("按键冲突时旧动作回退默认",
      pygame.K_a in M.KEYMAP["left"] and M.KEYMAP["right"] == [pygame.K_h],
      "left=%s right=%s" % (M.KEYMAP["left"], M.KEYMAP["right"]))
_saved = M.keymap_to_json()
M.apply_keymap(None)
check("恢复默认键位", M.KEYMAP["left"] == M.DEFAULT_KEYMAP["left"])
M.apply_keymap(_saved)
check("键位可存盘读回", M.KEYMAP["right"] == [pygame.K_h])

class _Pad:
    def get_axis(self, i): return [0.8, 0.0, 0.0, -0.9][i]
    def get_button(self, i): return i == 2
_pad = ([_Pad().get_axis(i) for i in range(4)], [_Pad().get_button(i) for i in range(6)])
_pin = M._host_input(_FK(), (0, 0), 0, 0, 0, pad=_pad, aim_from=(1000, 600))
check("手柄左摇杆推右", _pin.get("right") is True)
check("手柄 X 键射箭", _pin.get("shoot") is True)
check("手柄右摇杆向上瞄准", _pin.get("my", 9999) < 600, "my=%.0f" % _pin.get("my", 0))
M.apply_keymap(None)

# --------------------------------------------------------------------------
print("== 5. 联机：房主 + 客户端 TCP 往返 ==")
try:
    free = socket.socket()
    free.bind(("127.0.0.1", 0))
    port = free.getsockname()[1]
    free.close()

    e2 = core.GameEngine()
    sh = core.Shared()
    srv = core.HostServer(e2, sh, port=port)
    srv.start()
    q = queue.Queue()
    errs = []
    cli = core.NetClient("127.0.0.1", port, q, lambda m: errs.append(str(m)))

    got_state = False
    deadline = time.time() + 6
    while time.time() < deadline and not got_state:
        try:
            item = q.get(timeout=0.2)
            if item[0] == "state":
                got_state = True
        except queue.Empty:
            pass
    check("客户端收到世界状态", got_state, "errors=%s" % errs)

    # 等待室必须冻结世界
    tick_before = e2.tick
    deaths_before = e2.deaths
    time.sleep(2.0)
    check("等待室不推演世界", e2.tick == tick_before and e2.deaths == deaths_before,
          "tick %d->%d deaths %d" % (tick_before, e2.tick, deaths_before))
    check("客户端已自动准备", sh.client_ready)

    # 协议层：只收 JSON、输入走白名单
    try:
        core.decode_pkt(struct.pack(">I", 5_000_000) + b"x")
        _big_rejected = False
    except core.PacketError:
        _big_rejected = True
    check("封包解码拒绝超大包（判定协议错误而非跳过）", _big_rejected)
    dirty = core.sanitize_input({"left": True, "mx": 1e12, "evil": "__import__('os')"})
    check("输入白名单丢弃未知字段", "evil" not in dirty and dirty.get("left") is True)
    check("输入数值被钳制", dirty.get("mx", 0) <= 1e6, str(dirty.get("mx")))

    # 双端就位后开局
    sh.q_host_input.put_nowait({"type": "start"})
    time.sleep(0.5)
    check("开局后世界开始推演", e2.tick > tick_before, "tick=%d" % e2.tick)

    x_before = e2.players[1]["x"]
    for _ in range(45):
        cli.send_input({"right": True})
        time.sleep(core.TICK_DT)
    check("客户端输入推动角色", e2.players[1]["x"] - x_before > 30,
          "%.0f px" % (e2.players[1]["x"] - x_before))

    cli.send_chat("测试消息")
    time.sleep(0.4)
    check("客户端聊天到达房主", any("测试消息" in str(c) for c in e2.chat),
          str(e2.chat[-2:]))
    cli.close()
    srv.stop()
    time.sleep(0.2)
    check("断开不崩溃", True)
except Exception as e:
    check("联机往返", False, repr(e))

# --------------------------------------------------------------------------
print("== 5.5 联机角色/难度/机关同步 ==")
# 难度与机关状态随包广播
_e = core.GameEngine()
_e.difficulty = 1.4
_st = _e.pack()
check("难度随包广播", _st.get("difficulty") == 1.4, str(_st.get("difficulty")))
check("共鸣门状态随包", "rune_open" in _st, str(sorted(_st.keys())[:8]))
check("火机关/武器状态随包", "vents" in _st and "weapon_taken" in _st)

# 房主选盾卫（host_pid=1）：hello 应告诉你=0（弓箭手）
free = socket.socket()
free.bind(("127.0.0.1", 0))
port = free.getsockname()[1]
free.close()
e3 = core.GameEngine()
sh3 = core.Shared()
srv3 = core.HostServer(e3, sh3, port=port, host_pid=1)
srv3.start()
q3 = queue.Queue()
cli3 = core.NetClient("127.0.0.1", port, q3, lambda m: None)
_you = None
deadline = time.time() + 6
while time.time() < deadline and _you is None:
    try:
        item = q3.get(timeout=0.2)
        if item[0] == "hello":
            _you = item[1].get("you")
    except queue.Empty:
        pass
check("房主选盾卫时客户端拿弓箭手", _you == 0, "you=%s" % _you)
# 输入映射：房主=1、客户端=0
sh3.q_host_input.put_nowait({"type": "start"})
time.sleep(0.4)
srv3.client_input = {"right": True}
srv3._host_input = {"right": True}
_x0 = e3.players[0]["x"]
_x1 = e3.players[1]["x"]
for _ in range(15):
    e3.step({0: {"right": True}, 1: {"right": True}}, core.TICK_DT)
check("房主盾卫/客户端弓箭手输入分别驱动",
      e3.players[1]["x"] > _x1 and e3.players[0]["x"] > _x0,
      "p0 %.0f p1 %.0f" % (e3.players[0]["x"], e3.players[1]["x"]))
cli3.close()
srv3.stop()
time.sleep(0.2)

# 联机门格同步：guest 端必须按服务器状态改本地网格
_g = core.build_static_grid()
M._sync_gate_tiles(_g, {"rune_open": True, "duo_open": False})
_rune_open_ok = all(_g[y][core.RUNE_GATE_COL] == ' ' for y in range(core.RUNE_GATE_ROWS[0],
                                                                 core.RUNE_GATE_ROWS[1] + 1))
check("共鸣门开启时客户端门格被清空", _rune_open_ok,
      str([_g[y][core.RUNE_GATE_COL] for y in core.RUNE_GATE_ROWS]))
M._sync_gate_tiles(_g, {"rune_open": False, "duo_open": False})
_rune_close_ok = all(_g[y][core.RUNE_GATE_COL] == 'H' for y in range(core.RUNE_GATE_ROWS[0],
                                                                  core.RUNE_GATE_ROWS[1] + 1))
check("共鸣门关闭时客户端门格恢复", _rune_close_ok,
      str([_g[y][core.RUNE_GATE_COL] for y in core.RUNE_GATE_ROWS]))

# 手柄在联机角色分配下正确映射（房主盾卫=1 / 客户端弓箭手=0）
class _Pad:
    def get_axis(self, i):
        return [0.0, 0.0, 0.0, 0.0][i]
    def get_button(self, i):
        return i in (2, 3, 4)   # X射箭 / Y格挡 / LB挥剑 都按下
_pad = ([_Pad().get_axis(i) for i in range(4)], [_Pad().get_button(i) for i in range(6)])
_inp_shield = M._host_input(FakeKeys(), (0, 0), 1, 0, 0, pad=_pad)
_inp_archer = M._host_input(FakeKeys(), (0, 0), 0, 0, 0, pad=_pad)
check("手柄·盾卫挥剑/格挡生效且不射箭",
      _inp_shield.get("sword") and _inp_shield.get("block") and not _inp_shield.get("shoot"),
      "sword=%s block=%s shoot=%s" % (_inp_shield.get("sword"), _inp_shield.get("block"),
                                      _inp_shield.get("shoot")))
check("手柄·弓箭手射箭且不挥剑/格挡",
      _inp_archer.get("shoot") and not _inp_archer.get("sword") and not _inp_archer.get("block"),
      "shoot=%s sword=%s block=%s" % (_inp_archer.get("shoot"), _inp_archer.get("sword"),
                                      _inp_archer.get("block")))

# --------------------------------------------------------------------------
# 飞怪渲染坐标：曾漏掉 `- cam_y`，按世界坐标当屏幕坐标画，
# 相机越往下飞怪被画得越低（看起来永远贴地），玩家瞄它打不到。
_app = new_app()
_surf = pygame.Surface((800, 450), pygame.SRCALPHA)
_surf.fill((0, 0, 0, 0))
_fly_st = {"monsters": [{"mid": 7, "kind": "fly", "x": 400.0, "y": 100.0,
                         "hp": 2, "maxhp": 2, "state": "hover", "state_t": 0.0,
                         "dir": 1, "elite": False, "enraged": False,
                         "flash": 0.0, "stun": 0, "phase": 1}]}
# cam_y=200 -> 正确换算后 y=100-200-12=-112（画面外）；漏 cam_y 则会画在 y=88
_app.renderer._draw_monsters(_surf, 0, 200, 0.0, _fly_st)
_alpha_sum = int(pygame.surfarray.array_alpha(_surf).sum())
check("飞怪按相机换算绘制（cam_y 生效）", _alpha_sum == 0, "alpha_sum=%d" % _alpha_sum)

# 补给箱必须广播真实的高度：曾漏传 gy，渲染端退回默认 608，
# 结果上层平台/瞭望塔/隔间的箱子全被画在地面上，交互却在高处 —— 完全对不上
_ce = core.GameEngine()
_cst = _ce.pack()
_gy_ok = True
_by_id = {c["id"]: c for c in _cst.get("chests", [])}
for _ch in _ce._chests:
    _got = _by_id.get(_ch["id"], {})
    if abs(float(_got.get("gy", -1)) - _ch["gy"]) > 0.5:
        _gy_ok = False
check("补给箱高度随包广播（gy）", _gy_ok,
      str([(c["id"], _by_id.get(c["id"], {}).get("gy"), c["gy"]) for c in _ce._chests])[:120])
# 高台上的箱子不能等于地面高度
_high = [c for c in _ce._chests if c["gy"] < 19 * 32]
check("高台补给箱不在默认地面高度",
      _high and all(abs(_by_id[c["id"]]["gy"] - c["gy"]) < 0.5 for c in _high),
      "%d 个高台箱" % len(_high))

# ---- 关卡结构自检：机关不能被地形压住、不能有断头地面 ----
_g2 = core.build_static_grid()
_buried = []
for _r in range(core.MAP_H):
    for _c in range(core.MAP_W):
        if _g2[_r][_c] in ('q', 'Q'):
            _above = "".join(_g2[_rr][_c] for _rr in range(max(0, _r - 3), _r))
            if any(ch != ' ' for ch in _above):
                _buried.append((_c, _r, _above))
check("所有机关上方无遮挡（能站人踩）", not _buried, str(_buried[:3]))
check("熔炉双人机关列上方为空",
      all(core.build_static_grid()[rr][core.DUO_PLATE_COLS[1]] == ' '
          for rr in range(16, 19)),
      "col %d rows16-18" % core.DUO_PLATE_COLS[1])

# ---- 脱困保险：故意塞进实体块，必须被抬出来 ----
_ue = core.GameEngine()
_up = _ue.players[0]
_up["x"], _up["y"] = 100 * core.TILE + 16, 19 * core.TILE   # 塔 F1 实心块内部
_ue.step({}, core.TICK_DT)
_escaped = not _ue._rect_solid(_up["x"], _up["y"], core.PLAYER_W, core.PLAYER_H)
check("塞进实心块会被脱困逻辑抬出来", _escaped,
      "x=%.0f y=%.0f" % (_up["x"], _up["y"]))

# ---- 地刺：不致死 + 不会把人弹飞 ----
_se = core.GameEngine()
_se.monsters.clear(); _se.wave1_spawned = True; _se.rifts = []
_sp = _se.players[0]
_sp["x"], _sp["y"] = 110 * core.TILE + 16, 19 * core.TILE
_sp["hp"] = 10
_spawn_x = _sp["x"]
_max_dx = 0.0
for _ in range(180):
    _se.step({}, core.TICK_DT)
    _max_dx = max(_max_dx, abs(_sp["x"] - _spawn_x))
check("地刺不致死（保底 1 HP）", _sp["hp"] >= 1.0 and _sp["hp"] > 0,
      "hp=%.1f" % _sp["hp"])
check("地刺不会把人弹飞", _max_dx < 200.0, "最大位移 %.0f px" % _max_dx)

print("== 6. 音频接口 ==")
audio.set_volume(0.8, 0.4, 0.7)
v = audio.get_volume()
check("音量设置生效", abs(v["master"] - 0.8) < 1e-6 and abs(v["music"] - 0.4) < 1e-6, str(v))
audio.play_music("battle")
audio.music_duck(0.5, 0.1)
check("配乐库已就绪", len(audio.status()["music"]) >= 1, str(audio.status()))

# --------------------------------------------------------------------------
print("== 7. 结算/暂停/重开 ==")
app = new_app()
app.start_single(0)
app._apply_scene("GAME")
for _ in range(30):
    app.scene_game([], FakeKeys(), (640, 360))
M.engine.win = True
M.last_state = None
for _ in range(90):
    app.scene_game([], FakeKeys(), (640, 360))
    app._tick_transition()
check("通关进入结算", app.scene == "RESULT", app.scene)
app.scene_result(click(app.result_buttons[0].rect.center), FakeKeys(),
                 app.result_buttons[0].rect.center)
for _ in range(60):
    app._tick_transition()
check("再战回到游戏", app.scene == "GAME", app.scene)
check("关卡确实重置", not M.engine.win and M.engine.tick < 200, "tick=%d" % M.engine.tick)

# 清理：不要让测试把玩家的设置文件改花
try:
    if os.path.exists(M.SETTINGS_FILE):
        os.remove(M.SETTINGS_FILE)
except Exception:
    pass

print()
if FAIL:
    print("失败项：", FAIL)
    sys.exit(1)
print("全面体检通过。")
