# -*- coding: utf-8 -*-
"""
main.py —— 《暮色之前 · Before Dusk》主程序（重制版）
============================================================================
场景流：
    MENU ─┬─ CHAR_SELECT → GAME（单人，AI 托管另一角色）
          ├─ NET_MENU → HOST_WAIT / CLIENT_CONNECT → GAME（双人联机）
          └─ SETTINGS
    GAME ─┬─ PAUSE → SETTINGS / MENU
          └─ RESULT（通关结算）

本版新增：
  * 全套程序化音频（audio.py）：三段循环配乐 + 22 种音效
  * 商业级 UI（theme.py / ui.py）：玻璃面板、按钮动效、滑块、开关、提示条
  * 视觉特效（fx.py）：粒子、屏幕震动、飘字、视差背景、暗角
  * 世界渲染（renderer.py）：分层地形、岩浆/深坑、摆锤/地刺/落石、检查点/补给箱
  * 手感：固定步长 30Hz、冲刺、土狼时间、二段跳、伤害飘字、检查点复活
"""
import json
import math
import os
import queue
import random
import socket
import sys
import threading
import time
import traceback

import pygame

import audio
import fx
import game_core as core
import sprites
import theme
import ui
from game_core import GameEngine, HostServer, NetClient, Shared, TICK_DT
from renderer import WorldRenderer

SCREEN_W, SCREEN_H = 1280, 720
WORLD_VW, WORLD_VH = 800, 450   # 世界先按低分辨率渲染，再整数感放大，像素更饱满
FPS = 60


def app_dir():
    """exe / 源码所在目录（冻结后设置要写在 exe 旁边，而不是临时解包目录）。"""
    try:
        if getattr(sys, "frozen", False):
            return os.path.dirname(os.path.abspath(sys.executable))
    except Exception:
        pass
    return os.path.dirname(os.path.abspath(__file__))


def base_dir():
    try:
        if hasattr(sys, "_MEIPASS"):
            return sys._MEIPASS
    except Exception:
        pass
    return os.path.dirname(os.path.abspath(__file__))


os.chdir(base_dir())

# ==========================================================================
# 设置
# ==========================================================================
SETTINGS_FILE = os.path.join(app_dir(), "settings.json")
_FALLBACK_SETTINGS = os.path.join(os.path.expanduser("~"), ".before_dusk_settings.json")
RECORDS_FILE = os.path.join(app_dir(), "records.json")
_FALLBACK_RECORDS = os.path.join(os.path.expanduser("~"), ".before_dusk_records.json")
DEFAULT_SETTINGS = {
    "master": 0.85, "music": 0.42, "sfx": 0.72,
    "fullscreen": False, "quality": 1, "show_fps": False, "skins": [0, 0],
    "shake": 1.0, "flash": 1.0,      # 辅助选项：震屏/受击闪烁强度
    "ui_scale": 1.0,               # 界面缩放（0.9~1.4）
    "keys": {},                    # 自定义键位：必须在这里登记，否则 load_settings
                                   # 会按白名单把它丢掉（改键重启就回默认）
}


def load_settings():
    """读取设置：任何字段类型不对/越界都退回默认值，绝不因配置文件损坏而开不了游戏。"""
    s = dict(DEFAULT_SETTINGS)
    data = None
    for path in (SETTINGS_FILE, _FALLBACK_SETTINGS):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            break
        except Exception:
            continue
    # 浮点字段各自的合法区间。以前统一按 0~1 夹，导致界面缩放只要 >100%
    # 就会在重启后被静默改回 1.0（玩家以为设置没保存）。
    _FLOAT_RANGE = {"ui_scale": (0.9, 1.4)}
    try:
        if not isinstance(data, dict):
            return s
        for k, dv in DEFAULT_SETTINGS.items():
            if k not in data:
                continue
            v = data[k]
            if isinstance(dv, bool):
                s[k] = bool(v)
            elif isinstance(dv, float):
                try:
                    lo, hi = _FLOAT_RANGE.get(k, (0.0, 1.0))
                    s[k] = max(lo, min(hi, float(v)))
                except (TypeError, ValueError):
                    pass
            elif isinstance(dv, int):
                try:
                    s[k] = int(v)
                except (TypeError, ValueError):
                    pass
            else:
                s[k] = v
        s["quality"] = max(0, min(2, int(s.get("quality", 1) or 0)))
        # 外观索引：存档被写坏时（比如手改成字符串）也不能让选人界面炸掉
        _sk = s.get("skins")
        if not (isinstance(_sk, (list, tuple)) and len(_sk) == 2):
            s["skins"] = [0, 0]
        else:
            try:
                # 只做非负夹紧，上限交给 App（它知道每个职业有几套外观）
                s["skins"] = [max(0, int(_sk[0])), max(0, int(_sk[1]))]
            except Exception:
                s["skins"] = [0, 0]
    except Exception:
        pass
    return s


RANK_ORDER = {"S": 4, "A": 3, "B": 2, "C": 1, "": 0}


_RECORD_INT_KEYS = ("runs", "wins", "best_kills", "best_score")


def load_records():
    """读取记录：逐字段校验类型。

    之前只判断"是不是 int/float/str/None"就照单全收，
    结果 records.json 里一个 "best_time": "abc" 就会让 _update_records 里的
    float(bt) 抛异常、被整段 except 吞掉 —— 之后所有记录都静默不再更新，
    而且损坏值会被原样写回，永远不自愈。
    """
    rec = {"runs": 0, "wins": 0, "best_time": None, "best_kills": 0,
           "best_rank": "", "best_score": 0}
    for path in (RECORDS_FILE, _FALLBACK_RECORDS):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k in rec:
                    if k not in data:
                        continue
                    v = data[k]
                    if k in _RECORD_INT_KEYS:
                        try:
                            rec[k] = max(0, int(v))
                        except (TypeError, ValueError):
                            pass
                    elif k == "best_time":
                        try:
                            rec[k] = None if v is None else max(0.0, float(v))
                        except (TypeError, ValueError):
                            pass
                    elif k == "best_rank":
                        rank = str(v).strip().upper()
                        if rank in RANK_ORDER:
                            rec[k] = rank
                break
        except Exception:
            continue
    return rec


def save_records(rec):
    for path in (RECORDS_FILE, _FALLBACK_RECORDS):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
            return
        except Exception:
            continue


def _sync_gate_tiles(grid, st):
    """联机客端：按服务器广播的机关状态同步本地网格里的门。

    双人闸门是一次性开启（开着就一直空），共鸣门是动态的（关着要恢复 'H'）。
    抽成纯函数是为了能直接测——之前漏了 rune_open，队友会被"已开的门"挡住。
    """
    if not grid or not st:
        return
    try:
        if st.get("duo_open"):
            for y in range(15, 19):
                if 0 <= y < len(grid) and grid[y][core.DUO_GATE_COL] != ' ':
                    grid[y][core.DUO_GATE_COL] = ' '
    except Exception:
        pass
    try:
        want = ' ' if st.get("rune_open") else 'H'
        for y in range(core.RUNE_GATE_ROWS[0], core.RUNE_GATE_ROWS[1] + 1):
            if 0 <= y < len(grid) and 0 <= core.RUNE_GATE_COL < len(grid[y]):
                if grid[y][core.RUNE_GATE_COL] != want:
                    grid[y][core.RUNE_GATE_COL] = want
    except Exception:
        pass


def compute_score(st, mult=1.0):
    """分数：击杀 + 速度 + 通关，减阵亡；再乘挑战倍率。"""
    try:
        kills = int(st.get("kills", 0))
        deaths = int(st.get("deaths", 0))
        elapsed = float(st.get("elapsed", 0))
        base = kills * 100 + max(0.0, 600.0 - elapsed) * 2.0 + (1200 if st.get("win") else 0)
        if st.get("win") and st.get("beat_night"):
            base += 500.0                # 残阳加成：赶在夜幕降临前抵达传送门
        base -= deaths * 80
        return max(0, int(base * max(0.1, mult)))
    except Exception:
        return 0


def save_settings(s):
    """优先写在 exe 同目录；没有写权限时退到用户主目录。"""
    for path in (SETTINGS_FILE, _FALLBACK_SETTINGS):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(s, f, ensure_ascii=False, indent=2)
            return
        except Exception:
            continue


# ==========================================================================
# 全局运行时状态（联机 / 引擎）
# ==========================================================================
engine = None
shared = None
server = None
client = None
net_out = queue.Queue()
net_error = None
guest = False
single_mode = False
player_pid = 0
host_pid = 0
ai_cmd = "follow"
DIFFICULTIES = [("easy", "简单", 0.7), ("normal", "标准", 1.0), ("hard", "困难", 1.4)]
TUTORIAL_STEPS = [
    ("移动：按 A / D 或 ← →", lambda i, p: bool(i.get("left") or i.get("right"))),
    ("跳跃：按 空格 / W / ↑", lambda i, p: bool(i.get("up"))),
    ("冲刺：按 Shift（短暂无敌）", lambda i, p: bool(i.get("dash"))),
    ("攻击：左键射箭(弓) / J 挥剑(盾)", lambda i, p: bool(i.get("shoot") or i.get("sword"))),
    ("格挡：按 K（盾卫，完美格挡可弹反）", lambda i, p: bool(i.get("block"))),
]
CHALLENGES = [
    ("glass", "玻璃大炮", "受到伤害 ×1.5", 1.5),
    ("elite", "精英狩猎", "第二波地面怪全变精英", 1.3),
    ("nosupply", "断补给", "补给箱失效", 1.2),
]
last_state = None
last_state_time = 0.0
menu_input = ""
chat_log = []
chat_text = ""
chat_active = False
camera_x = camera_y = 0.0

CAM_WORLD_W = core.WORLD_W
CAM_WORLD_H = core.WORLD_H

ROLE_NAME = {0: "弓箭手", 1: "盾卫"}
ROLE_TAG = {0: "远程 · 破岩 · 制空", 1: "近战 · 格挡 · 机关"}
ROLE_COLOR = {0: theme.ARCHER_COL, 1: theme.SHIELD_COL}


def add_chat(who, text):
    try:
        chat_log.append((who, text, time.time()))
        if len(chat_log) > 8:
            del chat_log[:len(chat_log) - 8]
    except Exception:
        pass


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ==========================================================================
# 输入
# ==========================================================================
def _mask_input(inp):
    """聊天/帮助界面打开时屏蔽角色操作，避免"打字顺带把角色开走"。"""
    if not inp:
        return inp
    out = dict(inp)
    for k in ("left", "right", "up", "down", "dash", "shoot", "sword", "block", "interact"):
        out[k] = False
    return out


DEFAULT_KEYMAP = {
    "left": [pygame.K_a, pygame.K_LEFT],
    "right": [pygame.K_d, pygame.K_RIGHT],
    "up": [pygame.K_w, pygame.K_UP, pygame.K_SPACE],
    "down": [pygame.K_s, pygame.K_DOWN],
    "dash": [pygame.K_LSHIFT, pygame.K_RSHIFT, pygame.K_l],
    "sword": [pygame.K_j],
    "block": [pygame.K_k],
    "interact": [pygame.K_e],
    "switch": [pygame.K_TAB],
    "command": [pygame.K_f],
    "recall": [pygame.K_g],
}
KEYMAP = {k: list(v) for k, v in DEFAULT_KEYMAP.items()}
KEY_LABEL = {
    "left": "左移", "right": "右移", "up": "跳跃 / 二段跳", "down": "下蹲 / 穿板",
    "dash": "冲刺",
    "sword": "挥剑（盾卫）", "block": "格挡（盾卫）", "interact": "交互 / 开箱",
    "switch": "切换操控角色", "command": "同伴指令",
    "recall": "召回同伴",
}
REBIND_ORDER = ("left", "right", "up", "down", "dash", "sword",
                "block", "interact", "switch", "command", "recall")


def _key_name(code):
    try:
        return pygame.key.name(int(code)).upper()
    except Exception:
        return "?"


def _act(keys, action):
    for code in KEYMAP.get(action, ()):
        try:
            if keys[code]:
                return True
        except Exception:
            continue
    return False


def _key_is(code, action):
    return code in KEYMAP.get(action, ())


_bad_state_warned = False


def _valid_state(st):
    """客机收到的状态包是否可用。

    房主自己 pack() 出来的包一定合法；这里防的是网络上的畸形/半截包
    （或对端版本不一致）：不校验的话 scene_game 每帧 KeyError，客户端黑屏刷栈。
    """
    global _bad_state_warned
    try:
        ps = st["players"]
        for pid in (0, 1):
            p = ps[pid]
            if not isinstance(p, dict):
                raise TypeError("player 不是字典")
            if not isinstance(p.get("x"), (int, float)):
                raise TypeError("x 不是数字")
            if not isinstance(p.get("y"), (int, float)):
                raise TypeError("y 不是数字")
        return True
    except Exception as e:
        if not _bad_state_warned:
            _bad_state_warned = True
            print("[联机] 丢弃畸形状态包：%r" % (e,))
        return False


def apply_keymap(data):
    """从 settings 读回键位；非法/缺失项回退默认。"""
    global KEYMAP
    out = {k: list(v) for k, v in DEFAULT_KEYMAP.items()}
    if isinstance(data, dict):
        for act, codes in data.items():
            if act not in out:
                continue
            # 除了"是整数列表"，还要校验范围：负数会被 pygame 当负索引，
            # 读到一个随机的键；超大值永远读不到，等于把这个动作废掉
            if (isinstance(codes, list) and codes
                    and all(isinstance(c, int) and not isinstance(c, bool)
                            and 0 <= c <= 0x40000000 for c in codes)):
                out[act] = codes[:4]
    KEYMAP = out


def keymap_to_json():
    return {k: list(v) for k, v in KEYMAP.items()}


class Pad:
    """手柄：左摇杆移动，右摇杆瞄准，A 跳 / B 冲刺 / X 射箭 / Y 格挡 / LB 挥剑 / RB 交互。"""

    def __init__(self):
        self.joy = None
        self.name = ""

    def refresh(self):
        try:
            pygame.joystick.init()
            if pygame.joystick.get_count() > 0:
                if self.joy is None:
                    self.joy = pygame.joystick.Joystick(0)
                    self.joy.init()
                    self.name = self.joy.get_name()
                    add_chat("系统", "已连接手柄：" + self.name)
            else:
                if self.joy is not None:
                    self.joy = None
                    self.name = ""
        except Exception:
            self.joy = None

    def poll(self):
        if self.joy is None:
            return None
        try:
            ax = [self.joy.get_axis(i) for i in range(self.joy.get_numaxes())]
            bt = [self.joy.get_button(i) for i in range(self.joy.get_numbuttons())]
            return ax, bt
        except Exception:
            self.joy = None
            return None


PAD = Pad()


def _host_input(keys, mouse, pid=None, cam_x=0.0, cam_y=0.0, pad=None, aim_from=None):
    """统一输入采样：键盘（可重映射）+ 鼠标 + 手柄。

    注意：按键常量在 pygame 顶层（pygame.K_a），pygame.key 里没有 K_a。
    按键从 KEYMAP 读取，支持设置里重映射；异常只报一次，避免"静默无输入"。
    """
    try:
        left = _act(keys, "left")
        right = _act(keys, "right")
        up = _act(keys, "up")
        down = _act(keys, "down")
        dash = _act(keys, "dash")
        interact = _act(keys, "interact")
        sword = _act(keys, "sword")
        block = _act(keys, "block")
        shoot = bool(pygame.mouse.get_pressed()[0])

        # 鼠标是 1280x720 的屏幕坐标，世界是 800x450，再叠加相机偏移
        scale = WORLD_VW / float(SCREEN_W)
        mx = cam_x + mouse[0] * scale
        my = cam_y + mouse[1] * scale
        role = player_pid if pid is None else pid

        # ---- 手柄叠加 ----
        if pad:
            ax, bt = pad
            try:
                if ax:
                    if ax[0] < -0.35:
                        left = True
                    if ax[0] > 0.35:
                        right = True
                    if len(ax) > 1 and ax[1] < -0.45:
                        up = True
                    if len(ax) > 1 and ax[1] > 0.45:
                        down = True
                if bt:
                    up = up or bt[0]
                    dash = dash or (len(bt) > 1 and bt[1])
                    shoot = shoot or (len(bt) > 2 and bt[2])
                    block = block or (len(bt) > 3 and bt[3])
                    sword = sword or (len(bt) > 4 and bt[4])
                    interact = interact or (len(bt) > 5 and bt[5])
                # 右摇杆瞄准
                if aim_from and len(ax) > 3:
                    rx, ry = ax[2], ax[3]
                    if abs(rx) > 0.3 or abs(ry) > 0.3:
                        mx = float(aim_from[0]) + rx * 340
                        my = float(aim_from[1]) - 26 + ry * 340
            except Exception:
                pass

        return {
            "up": bool(up), "down": bool(down), "left": bool(left), "right": bool(right),
            "dash": bool(dash), "interact": bool(interact),
            "shoot": bool(shoot) and role == 0,
            "sword": bool(sword or pygame.mouse.get_pressed()[2]) and role == 1,
            "block": bool(block or pygame.mouse.get_pressed()[2]) and role == 1,
            "mx": float(mx), "my": float(my),
        }
    except Exception as e:
        if not getattr(_host_input, "_warned", False):
            _host_input._warned = True
            print("[输入采样异常] %r" % (e,))
            traceback.print_exc()
        return {}


# ==========================================================================
# 主程序
# ==========================================================================
class App:
    def __init__(self):
        pygame.init()
        self.settings = load_settings()
        apply_keymap(self.settings.get("keys"))
        try:
            fx.Camera.trauma_mul = theme.clamp(self.settings.get("shake", 1.0))
            self.post.flash_mul = theme.clamp(self.settings.get("flash", 1.0))
            theme.ui_scale = theme.clamp(self.settings.get("ui_scale", 1.0), 0.9, 1.4)
            theme.quality = max(0, min(2, int(self.settings.get("quality", 1) or 0)))
        except Exception:
            pass
        try:
            PAD.refresh()
        except Exception:
            pass
        audio.init()
        audio.set_volume(self.settings["master"], self.settings["music"], self.settings["sfx"])
        self.screen = None
        self._apply_display()

        pygame.display.set_caption("暮色之前 · Before Dusk")
        self.clock = pygame.time.Clock()
        self.t = 0.0
        self.dt = 0.0

        self.scene = "MENU"
        self._pending = None
        self.return_scene = "MENU"

        self.post = fx.PostFX()
        self.particles = fx.Particles(cap=520 if self.settings["quality"] else 260)
        self.floats = fx.FloatingText()
        self.world_surf = pygame.Surface((WORLD_VW, WORLD_VH))
        self.cam = fx.Camera(WORLD_VW, WORLD_VH)
        self.renderer = WorldRenderer(self.screen)
        self.grid = None

        self.acc = 0.0
        self.last_st = None
        self.run_started = 0.0
        self.result_shown = False
        self.hp_ghost = {0: 1.0, 1: 1.0}
        self.hp_smooth = {0: 1.0, 1: 1.0}
        self.msg_text = ""
        self.msg_t = 0.0
        self.chest_hint = 0.0
        self._ai_stuck = 0.0
        self.hitstop = 0.0
        self.challenges = set()
        self.diff_index = 1
        self.host_role = 0
        self.tutorial_step = 0
        self.tutorial_done = False
        self._lan_stop = None
        self._lan_q = queue.Queue()
        self._lan_rooms = {}       # ip -> (room, port)
        self.records = load_records()
        self._result_score = 0
        self._result_mult = 1.0
        self._result_new = {}
        self.rebind_action = None
        self.rebind_rects = {}
        self._ai_last_x = 0.0
        self.fps_show = 0.0
        self.music_name = None

        self.menu_index = 0
        self.menu_t = 0.0
        self.embers = [[random.uniform(0, SCREEN_W), random.uniform(0, SCREEN_H),
                        random.uniform(10, 30), random.uniform(0.4, 1.0)]
                       for _ in range(46)]
        self.char_index = 0
        self.char_t = 0.0
        self.help_open = False

        try:
            sprites.prebuild()
        except Exception:
            pass
        self._build_menu()
        self._build_char()
        self._build_settings()
        self._build_net()
        self._build_pause()
        self._build_result()

        self.post.fade = 1.0
        self.post.fade_to(0.0, 1.4)
        audio.play_music("menu")

    # ------------------------------------------------------------------
    # 显示
    # ------------------------------------------------------------------
    def _apply_display(self):
        try:
            if self.settings.get("fullscreen"):
                self.screen = pygame.display.set_mode(
                    (SCREEN_W, SCREEN_H), pygame.FULLSCREEN | pygame.SCALED)
            else:
                self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        except Exception:
            self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))

    # ------------------------------------------------------------------
    # 场景切换
    # ------------------------------------------------------------------
    def goto(self, scene, speed=3.4):
        if scene == self.scene and self._pending is None:
            return
        self._pending = scene
        self.post.fade_to(1.0, speed)

    def _apply_scene(self, scene):
        global chat_active, chat_text
        prev = self.scene
        # 联机：房主进出暂停时通知服务器冻结/恢复世界
        try:
            if server is not None and shared is not None:
                if scene == "PAUSE" and prev == "GAME":
                    shared.q_host_input.put_nowait({"type": "pause", "on": True})
                elif scene == "GAME" and prev == "PAUSE":
                    shared.q_host_input.put_nowait({"type": "pause", "on": False})
        except Exception:
            pass
        self.scene = scene
        if scene == "SETTINGS":
            if prev not in ("SETTINGS",):
                self.return_scene = prev
        if scene == "GAME":
            self.particles.items.clear()
            self.floats.items.clear()
            self.result_shown = False
            self.run_started = time.time()
            self.msg_text = ""
            self.msg_t = 0.0
            self.acc = 0.0
            self.hp_ghost = {0: 1.0, 1: 1.0}
            self.hp_smooth = {0: 1.0, 1: 1.0}
            chat_active = False
            chat_text = ""
            self.renderer.invalidate()
            if guest:
                self.grid = core.build_static_grid()
            elif engine is not None:
                self.grid = engine.grid
            if self.last_st:
                p = self.last_st.get("players", {}).get(player_pid, {})
                self.cam.snap(p.get("x", 120), p.get("y", 570),
                              (core.WORLD_W, core.WORLD_H))
        if scene == "RESULT":
            audio.music_duck(0.5, 2.4)
            self.last_state = getattr(self, "final_state", None) or last_state
            self.last_state_time = last_state_time
            self._update_records(self.last_state or {})
        if scene == "PAUSE":
            audio.set_volume(music=self.settings["music"] * 0.35)
        elif prev == "PAUSE":
            audio.set_volume(music=self.settings["music"])

    def _tick_transition(self):
        self.post.update(self.dt)
        if self._pending and self.post.fade >= 0.999:
            scene = self._pending
            self._pending = None
            self._apply_scene(scene)
            self.post.fade_to(0.0, 2.4)

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_menu(self):
        cx = SCREEN_W // 2
        self.menu_buttons = [
            ui.Button((cx - 176, 322, 352, 62), "单人远征", "gold", icon="play",
                      sub="AI 伙伴同行 · Tab 随时切换角色", size="sub"),
            ui.Button((cx - 176, 396, 352, 54), "双人联机", "primary", icon="shield",
                      sub="局域网 / ngrok 异地联机"),
            ui.Button((cx - 176, 460, 352, 48), "设置", "secondary", icon="gear"),
            ui.Button((cx - 176, 518, 352, 48), "退出游戏", "ghost", icon="cross"),
        ]

    def _build_char(self):
        cx = SCREEN_W // 2
        # 高度 330 时底部"按 Enter 开始"按钮离卡片下沿只剩 10px，视觉上像被切
        self.card_rects = [pygame.Rect(cx - 430, 196, 400, 338),
                           pygame.Rect(cx + 30, 196, 400, 338)]
        # 每个职业的外观索引（选人界面切换，写进 settings）
        _sk = self.settings.get("skins") or [0, 0]
        self.skin_index = {0: 0, 1: 0}
        for _pid, _kind in ((0, "archer"), (1, "guard")):
            try:
                _n = len(sprites.skin_list(_kind))
                self.skin_index[_pid] = max(0, min(_n - 1, int(_sk[_pid])))
            except Exception:
                self.skin_index[_pid] = 0
        self.skin_rects = {}
        # 卡片底边 = 196+330 = 526：难度行与词条行都必须排在它下面，
        # 否则会被两张卡压住（旧版难度行在 498，整行只剩中间一截露出来）
        self.char_back = pygame.Rect(24, 596, 150, 46)

    def _build_settings(self):
        w, h = 760, 620
        x, y = (SCREEN_W - w) // 2, (SCREEN_H - h) // 2
        self.set_panel = pygame.Rect(x, y, w, h)
        # 分页：音量 / 画面 / 操作。每页内容变少之后，界面缩放才敢做到 140%
        # （单页把所有控件堆在一起时，1.3 就开始互相挤，1.4 根本装不下）
        self.set_tab = getattr(self, "set_tab", 0)
        # ---- 音量页 ----
        self.sl_master = ui.Slider((x + 40, y + 200, 560, 8), self.settings["master"], "主音量")
        self.sl_music = ui.Slider((x + 40, y + 270, 560, 8), self.settings["music"], "背景音乐")
        self.sl_sfx = ui.Slider((x + 40, y + 340, 560, 8), self.settings["sfx"], "音效")
        # ---- 画面页 ----
        self.tg_fs = ui.Toggle((x + 600, y + 190, 54, 24), self.settings["fullscreen"], "")
        self.tg_fps = ui.Toggle((x + 600, y + 252, 54, 24), self.settings["show_fps"], "")
        self.seg_quality = ui.Segmented((x + 420, y + 314, 234, 30), ["流畅", "标准", "精致"],
                                        self.settings["quality"])
        # 宽度收到 340：140% 时数值文字才不会被右边的分段器压到
        self.sl_ui = ui.Slider((x + 40, y + 396, 340, 8),
                               (self.settings.get("ui_scale", 1.0) - 0.9) / 0.5, "界面缩放",
                               fmt=lambda v: "%.0f%%" % ((0.9 + v * 0.5) * 100))
        self.sl_shake = ui.Slider((x + 40, y + 450, 340, 8), self.settings["shake"], "震屏强度")
        self.sl_flash = ui.Slider((x + 40, y + 520, 340, 8), self.settings["flash"], "受击闪烁")
        self.set_back = ui.Button((x + w // 2 - 90, y + h - 64, 180, 44), "返回", "secondary")

    def _build_net(self):
        cx = SCREEN_W // 2
        self.net_buttons = [
            ui.Button((cx - 170, 300, 340, 58), "创建房间（房主）", "gold", icon="flag",
                      sub="本机作为权威服务器，端口 5555"),
            ui.Button((cx - 170, 372, 340, 52), "加入房间（队友）", "primary", icon="arrow",
                      sub="输入房主的 IP:端口 或 ngrok 地址"),
            ui.Button((cx - 170, 436, 340, 46), "返回", "ghost"),
        ]
        self.net_index = 0
        self.addr_input = ui.TextInput((cx - 260, 330, 520, 54), "",
                                       "例如 192.168.1.10:5555 或 2.tcp.ngrok.io:12345",
                                       size="sub")
        self.connect_btn = ui.Button((cx - 110, 410, 220, 54), "连接", "gold", icon="play")
        self.net_back = ui.Button((cx - 90, 486, 180, 44), "返回", "ghost")
        self.copy_btn = ui.Button((cx - 110, 500, 220, 46), "复制地址", "secondary", icon="check")

    def _build_pause(self):
        w, h = 380, 380
        x, y = (SCREEN_W - w) // 2, (SCREEN_H - h) // 2
        self.pause_panel = pygame.Rect(x, y, w, h)
        self.pause_buttons = [
            ui.Button((x + 40, y + 108, 300, 52), "继续远征", "gold", icon="play"),
            ui.Button((x + 40, y + 170, 300, 46), "设置", "secondary", icon="gear"),
            ui.Button((x + 40, y + 224, 300, 46), "重新开始", "secondary", icon="flag"),
            ui.Button((x + 40, y + 278, 300, 46), "返回主菜单", "danger", icon="cross"),
        ]

    def _build_result(self):
        # 470 太矮：加了"行程回顾 / 搭档评语"两行后，评语（r.y+378，居中）
        # 正好压在按钮顶边（r.y+h-86）上，字被切掉。加高到 500 让两者分开。
        w, h = 620, 500
        x, y = (SCREEN_W - w) // 2, (SCREEN_H - h) // 2
        self.result_panel = pygame.Rect(x, y, w, h)
        self.result_buttons = [
            ui.Button((x + 90, y + h - 86, 200, 52), "再战一次", "gold", icon="play"),
            ui.Button((x + 330, y + h - 86, 200, 52), "返回主菜单", "secondary", icon="cross"),
        ]

    # ==================================================================
    # 通用绘制
    # ==================================================================
    def draw_menu_background(self, dt):
        """菜单/选角/设置共用的动态背景"""
        s = self.screen
        self.renderer.bg.draw(s, self.t * 26, 0, self.t, 0.0)
        # 光晕
        theme.glow_circle(s, (SCREEN_W * 0.72, 210), 180, (255, 190, 150), 0.35, 5)
        # 萤火/余烬
        for e in self.embers:
            e[1] -= e[2] * dt
            e[0] += math.sin(self.t * 0.8 + e[1] * 0.02) * 8 * dt
            if e[1] < -10:
                e[1] = SCREEN_H + 10
                e[0] = random.uniform(0, SCREEN_W)
            a = int(120 * e[3] * (0.6 + 0.4 * math.sin(self.t * 3 + e[0])))
            theme.glow_circle(s, (e[0], e[1]), 3, (255, 200, 130), max(0, a) / 255.0, 2)

    def draw_title(self, y=148, scale=1.0):
        s = self.screen
        cy = y + math.sin(self.t * 1.2) * 4
        theme.text(s, "暮色之前", (SCREEN_W // 2, cy), int(76 * scale), (255, 238, 198),
                   align="center", bold=True)
        theme.text(s, "暮色之前", (SCREEN_W // 2, cy - 2), int(76 * scale), (255, 250, 232),
                   align="center", bold=True, alpha_mul=0.35)
        theme.text(s, "B  E  F  O  R  E     D  U  S  K", (SCREEN_W // 2, cy + 62), "small",
                   theme.alpha_color((230, 214, 190), 190), align="center")
        pygame.draw.line(s, theme.alpha_color(theme.GOLD, 110),
                         (SCREEN_W // 2 - 180, cy + 86), (SCREEN_W // 2 + 180, cy + 86), 1)
        pygame.draw.circle(s, theme.GOLD, (SCREEN_W // 2, cy + 86), 3)

    def draw_ui_fx(self):
        self.particles.update(self.dt)
        self.particles.draw(self.screen, 0, 0)

    # ==================================================================
    # 场景：主菜单
    # ==================================================================
    def scene_menu(self, events, keys, mouse):
        s = self.screen
        self.menu_t += self.dt
        self.draw_menu_background(self.dt)
        self.draw_title()

        for b in self.menu_buttons:
            b.update(self.dt, mouse)
        # 键盘导航
        for ev in events:
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_UP, pygame.K_w):
                    self.menu_index = (self.menu_index - 1) % len(self.menu_buttons)
                    audio.sfx("ui_hover", 0.5)
                elif ev.key in (pygame.K_DOWN, pygame.K_s):
                    self.menu_index = (self.menu_index + 1) % len(self.menu_buttons)
                    audio.sfx("ui_hover", 0.5)
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self._menu_activate(self.menu_index)
                    return
        hovered = -1
        for i, b in enumerate(self.menu_buttons):
            if b.rect.collidepoint(mouse):
                hovered = i
        if hovered >= 0:
            self.menu_index = hovered
        for i, b in enumerate(self.menu_buttons):
            b.focus = (i == self.menu_index)
            if b.handle(events, mouse):
                audio.sfx("ui_click", 0.8)
                self._menu_activate(i)
                return
        for b in self.menu_buttons:
            b.draw(s)

        # 底部信息
        theme.text(s, "1280×720  ·  程序化音频与像素美术  ·  无外部素材依赖",
                   (SCREEN_W // 2, SCREEN_H - 66), "small",
                   theme.alpha_color(theme.SLATE_300, 170), align="center")
        theme.text(s, "↑↓ 选择    Enter 确认    游戏中 ESC 暂停 / F1 帮助",
                   (SCREEN_W // 2, SCREEN_H - 40), "small",
                   theme.alpha_color(theme.SLATE_400, 190), align="center")
        if (not pygame.key.get_focused() and pygame.display.get_driver() != "dummy"):
            tip = pygame.Rect(0, 0, 420, 30)
            tip.center = (SCREEN_W // 2, SCREEN_H - 96)
            theme.rounded_panel(s, tip, (22, 16, 12), theme.alpha_color(theme.GOLD, 120), 9,
                                alpha=235, shadow=False)
            theme.text(s, "点击窗口获取键盘焦点后再操作", tip.center, "small",
                       theme.GOLD_LIGHT, align="center", shadow=False)

    def _menu_activate(self, i):
        audio.sfx("ui_click", 0.9)
        if i == 0:
            self.goto("CHAR_SELECT")
        elif i == 1:
            self.goto("NET_MENU")
        elif i == 2:
            self.goto("SETTINGS")
        else:
            self.quit()

    def quit(self):
        save_settings(self.settings)
        try:
            audio.shutdown()
            pygame.quit()
        except Exception:
            pass
        os._exit(0)

    # ==================================================================
    # 场景：角色选择
    # ==================================================================
    def scene_char_select(self, events, keys, mouse):
        s = self.screen
        self.char_t += self.dt
        self.draw_menu_background(self.dt)
        theme.text(s, "选择你的远征角色", (SCREEN_W // 2, 96), "h1", (255, 240, 200),
                   align="center", bold=True)
        theme.text(s, "另一名角色由 AI 托管 · 游戏中按 Tab 随时接管", (SCREEN_W // 2, 136),
                   "body", theme.alpha_color(theme.SLATE_200, 210), align="center")

        hovered = -1
        for i, r in enumerate(self.card_rects):
            if r.collidepoint(mouse):
                hovered = i
        if hovered >= 0:
            self.char_index = hovered

        for i, r in enumerate(self.card_rects):
            self._draw_role_card(i, r, i == self.char_index, mouse)

        # 难度选择
        # 注意：标签和"点击切换"提示原来都画在 (SCREEN_W//2, 548) 同一个点上，
        # 两段文字直接叠在一起糊成一团。改成标签居中、箭头分列两侧。
        self.diff_rect = pygame.Rect(SCREEN_W // 2 - 120, 534, 240, 26)
        if self.diff_rect.collidepoint(mouse):
            pygame.draw.rect(s, theme.alpha_color((255, 255, 255), 16), self.diff_rect, border_radius=6)
        theme.text(s, "难度：" + DIFFICULTIES[self.diff_index][1], (SCREEN_W // 2, 548), "small",
                   theme.GOLD_LIGHT, align="center")
        # 用 < > 而不是 ◀ ▶：微软雅黑粗体没有 U+25C0/25B6，会渲染成方框
        for _ax, _ar in ((SCREEN_W // 2 - 96, "<"), (SCREEN_W // 2 + 96, ">")):
            theme.text(s, _ar, (_ax, 548), "small",
                       theme.alpha_color(theme.GOLD, 200 if self.diff_rect.collidepoint(mouse)
                                         else 120), align="center")

        # 挑战词条
        theme.text(s, "挑战词条（可选，提升得分）", (SCREEN_W // 2, 578), "small",
                   theme.alpha_color(theme.SLATE_300, 220), align="center")
        self.challenge_rects = {}
        cw, gap = 230, 16
        cx0 = (SCREEN_W - (cw * 3 + gap * 2)) // 2
        for i, (cid, name, desc, mul) in enumerate(CHALLENGES):
            # 56 高时说明文字离底边只有 2px，看着像被裁掉；加到 62 给 10px 余量
            rect = pygame.Rect(cx0 + i * (cw + gap), 596, cw, 62)
            on = cid in self.challenges
            if rect.collidepoint(mouse):
                pygame.draw.rect(s, theme.alpha_color((255, 255, 255), 20), rect, border_radius=10)
            pygame.draw.rect(s, theme.alpha_color(theme.GOLD, 42) if on else (0, 0, 0, 0),
                             rect, border_radius=10)
            pygame.draw.rect(s, theme.alpha_color(theme.GOLD if on else theme.SLATE_400,
                                                  170 if on else 90),
                             rect, 1, border_radius=10)
            # 选中卡是金色实底：浅金文字 + 黑投影在亮底上会糊成一团，
            # 改用深墨色 + 关投影，对比度才够
            theme.text(s, ("√ " if on else "") + name, (rect.x + 14, rect.y + 12), "body",
                       (54, 38, 12) if on else theme.SLATE_300, bold=on, shadow=not on)
            theme.text(s, "×%.1f" % mul, (rect.right - 14, rect.y + 12), "small",
                       (70, 50, 18) if on else theme.alpha_color(theme.SLATE_400, 200),
                       align="right", shadow=not on)
            theme.text(s, desc, (rect.x + 14, rect.y + 36), "tiny",
                       (62, 44, 14) if on else theme.alpha_color(theme.SLATE_300, 200),
                       shadow=not on)
            self.challenge_rects[cid] = rect

        # 返回
        self.char_back_btn = getattr(self, "char_back_btn", None)
        if self.char_back_btn is None:
            self.char_back_btn = ui.Button(self.char_back, "返回", "ghost")
        self.char_back_btn.rect = self.char_back
        self.char_back_btn.update(self.dt, mouse)
        if self.char_back_btn.handle(events, mouse):
            audio.sfx("ui_click", 0.7)
            self.goto("MENU")
            return
        self.char_back_btn.draw(s)

        for ev in events:
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_LEFT, pygame.K_a):
                    self.char_index = 0
                    audio.sfx("ui_hover", 0.5)
                elif ev.key in (pygame.K_RIGHT, pygame.K_d):
                    self.char_index = 1
                    audio.sfx("ui_hover", 0.5)
                elif ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                    audio.sfx("ui_click", 1.0)
                    self.start_single(self.char_index)
                    return
                elif ev.key == pygame.K_ESCAPE:
                    self.goto("MENU")
                    return
        for ev in events:
            if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                if getattr(self, "diff_rect", None) and self.diff_rect.collidepoint(ev.pos):
                    self.diff_index = (self.diff_index + 1) % len(DIFFICULTIES)
                    audio.sfx("ui_hover", 0.7)
                    return
                for cid, crect in getattr(self, "challenge_rects", {}).items():
                    if crect.collidepoint(ev.pos):
                        if cid in self.challenges:
                            self.challenges.discard(cid)
                        else:
                            self.challenges.add(cid)
                        audio.sfx("ui_hover", 0.8)
                        return
                for pid, chips in getattr(self, "skin_rects", {}).items():
                    for i, chip in enumerate(chips):
                        if chip.collidepoint(ev.pos):
                            self.skin_index[pid] = i
                            sprites.SKIN["archer" if pid == 0 else "guard"] = i
                            self.settings["skins"] = [self.skin_index[0],
                                                      self.skin_index[1]]
                            try:
                                save_settings(self.settings)
                            except Exception:
                                pass
                            audio.sfx("ui_hover", 0.9)
                            return
                for i, r in enumerate(self.card_rects):
                    if r.collidepoint(ev.pos):
                        audio.sfx("ui_click", 1.0)
                        self.start_single(i)
                        return

    def _draw_role_card(self, pid, rect, selected, mouse):
        s = self.screen
        col = ROLE_COLOR[pid]
        hov = rect.collidepoint(mouse)
        lift = -6 if selected else (-3 if hov else 0)
        r = rect.move(0, lift)
        # 外发光：选中最亮，悬停给一点，鼠标移到卡片上要有反馈
        if selected or hov:
            glow = pygame.Surface((r.w + 40, r.h + 40), pygame.SRCALPHA)
            for i in range(6):
                pygame.draw.rect(glow, theme.alpha_color(col, 16 if selected else 9),
                                 (18 - i * 3, 18 - i * 3, r.w + i * 6, r.h + i * 6),
                                 border_radius=22, width=3)
            s.blit(glow, (r.x - 20, r.y - 20))
        theme.rounded_panel(s, r, (24, 28, 46),
                            theme.alpha_color(col, 200 if selected else (140 if hov else 90)),
                            18, alpha=244)
        # 顶部渐变条
        theme.gradient_rect(s, (r.x + 2, r.y + 2, r.w - 4, 64), (34, 38, 58), (24, 28, 46))
        theme.text(s, ROLE_NAME[pid], (r.x + 26, r.y + 34), "title", (255, 244, 214),
                   align="midleft", bold=True)
        theme.text(s, ROLE_TAG[pid], (r.right - 24, r.y + 34), "small",
                   theme.alpha_color(col, 220), align="midright")
        # 角色立绘
        base = sprites.get_char("archer" if pid == 0 else "guard", "idle0",
                                self.skin_index.get(pid, 0))
        big = pygame.transform.scale(base, (int(base.get_width() * 3.4),
                                            int(base.get_height() * 3.4)))
        bob = int(math.sin(self.char_t * 2.2 + pid) * 5)
        theme.glow_circle(s, (r.centerx, r.y + 148 + bob), 74,
                          col, 0.30 if selected else 0.14, 4)
        theme.soft_shadow(s, r.centerx, r.y + 224, 120, 13, 110)
        s.blit(big, big.get_rect(midbottom=(r.centerx, r.y + 220 + bob)))
        # 技能说明
        skills = ("左键 射击 · 可击碎岩石墙", "J 挥剑 · K 格挡 · 踩机关") if pid == 0 else \
                 ("近战斩杀地面怪 · 举盾免伤", "踩压力机关生成浮空跳板")
        for i, line in enumerate(skills):
            theme.text(s, "· " + line, (r.x + 26, r.y + 240 + i * 22), "small",
                       theme.alpha_color(theme.SLATE_200, 220))
        # 选中按钮
        btn = pygame.Rect(r.x + 26, r.y + 280, r.w - 52, 30)
        if selected:
            ui._blend_panel(s, btn, theme.shade(col, -0.5), 235, 8)
            pygame.draw.rect(s, col, btn, 1, border_radius=8)
            theme.text(s, "按 Enter 或 点击卡片开始", btn.center, "body", (255, 248, 226),
                       align="center", bold=True, shadow=False)
        else:
            pygame.draw.rect(s, theme.alpha_color(col, 80), btn, 1, border_radius=8)
            theme.text(s, "点击选择", btn.center, "body", theme.alpha_color(col, 200),
                       align="center", shadow=False)

        # ---- 外观（皮肤）选择 ----
        kind = "archer" if pid == 0 else "guard"
        lst = sprites.skin_list(kind)
        cur = self.skin_index.get(pid, 0)
        sy = r.y + 318
        self.skin_rects[pid] = []
        theme.text(s, "外观", (r.x + 26, sy + 8), "tiny",
                   theme.alpha_color(theme.SLATE_300, 210), align="midleft")
        for i, sk in enumerate(lst):
            chip = pygame.Rect(r.x + 64 + i * 36, sy, 32, 16)
            on = (i == cur)
            pal = sk["pal"]
            pygame.draw.rect(s, pal[3], chip, border_radius=5)
            pygame.draw.rect(s, pal[5], (chip.x + 4, chip.y + 4, 7, 8), border_radius=2)
            pygame.draw.rect(s, pal[9], (chip.x + 14, chip.y + 4, 6, 8), border_radius=2)
            if on:
                pygame.draw.rect(s, theme.GOLD_LIGHT, chip, 2, border_radius=5)
            else:
                pygame.draw.rect(s, theme.alpha_color(theme.SLATE_400, 130),
                                 chip, 1, border_radius=5)
            self.skin_rects[pid].append(chip)
        theme.text(s, lst[cur]["name"], (r.right - 24, sy + 8), "tiny",
                   theme.alpha_color(theme.GOLD_LIGHT, 225), align="midright")

    # ==================================================================
    # 场景：设置
    # ==================================================================
    def _assign_key(self, act, code):
        try:
            if act not in KEYMAP:
                return          # 动作名写错时不要往 KEYMAP 里塞垃圾项
            for other in KEYMAP:
                if code in KEYMAP[other]:
                    KEYMAP[other] = [c for c in KEYMAP[other] if c != code]
                    if not KEYMAP[other]:
                        KEYMAP[other] = list(DEFAULT_KEYMAP[other])
            KEYMAP[act] = [code]
            audio.sfx("ui_click", 0.8)
            add_chat("系统", "%s → %s" % (KEY_LABEL.get(act, act), _key_name(code)))
        except Exception:
            pass

    def scene_settings(self, events, keys, mouse):
        s = self.screen
        self.draw_menu_background(self.dt)
        ui.panel(s, self.set_panel, "设置", "改动即时生效，返回时自动保存", icon="gear")
        x = self.set_panel.x
        y = self.set_panel.y
        tab = getattr(self, "set_tab", 0)

        # ---- 分页按钮 ----
        tw, th, gap = 200, 40, 12
        tx0 = x + (self.set_panel.w - (tw * 3 + gap * 2)) // 2
        self.tab_rects = []
        for i, name in enumerate(("音量", "画面", "操作")):
            r = pygame.Rect(tx0 + i * (tw + gap), y + 100, tw, th)
            self.tab_rects.append(r)
            on = (i == tab)
            if on:
                ui._blend_panel(s, r, theme.alpha_color(theme.GOLD, 46), 235, 10)
                pygame.draw.rect(s, theme.alpha_color(theme.GOLD, 200), r, 1, border_radius=10)
            else:
                if r.collidepoint(mouse):
                    ui._blend_panel(s, r, theme.alpha_color((255, 255, 255), 16), 220, 10)
                pygame.draw.rect(s, theme.alpha_color(theme.SLATE_400, 90), r, 1, border_radius=10)
            theme.text(s, name, r.center, "label",
                       theme.GOLD_LIGHT if on else theme.SLATE_300,
                       align="center", bold=on, shadow=False)
            for ev in events:
                if (ev.type == pygame.MOUSEBUTTONUP and ev.button == 1
                        and r.collidepoint(ev.pos) and not on):
                    self.set_tab = i
                    tab = i
                    # 切页时取消改键：否则"按任意键…"会留在看不见的那一页上，
                    # 下一次按键被悄悄吞掉
                    self.rebind_action = None
                    audio.sfx("ui_click", 0.7)
        ui.divider(s, x + 40, x + 720, y + 150)

        # ---- 音量 ----
        if tab == 0:
            for sl in (self.sl_master, self.sl_music, self.sl_sfx):
                sl.update(self.dt, mouse)
            if self.sl_master.handle(events, mouse):
                self.settings["master"] = self.sl_master.value
                audio.set_volume(master=self.sl_master.value)
            if self.sl_music.handle(events, mouse):
                self.settings["music"] = self.sl_music.value
                audio.set_volume(music=self.sl_music.value)
            if self.sl_sfx.handle(events, mouse):
                self.settings["sfx"] = self.sl_sfx.value
                audio.set_volume(sfx_=self.sl_sfx.value)
            self.sl_master.draw(s)
            self.sl_music.draw(s)
            self.sl_sfx.draw(s)
            theme.text(s, "主音量同时影响音乐与音效；两者可分别再调。",
                       (x + 40, y + 430), "small", theme.alpha_color(theme.SLATE_400, 200))

        # ---- 画面 ----
        elif tab == 1:
            self.tg_fs.update(self.dt, mouse)
            if self.tg_fs.handle(events, mouse):
                self.settings["fullscreen"] = self.tg_fs.value
                self._apply_display()
                audio.sfx("ui_click", 0.7)
            self.tg_fps.update(self.dt, mouse)
            if self.tg_fps.handle(events, mouse):
                self.settings["show_fps"] = self.tg_fps.value
                audio.sfx("ui_click", 0.7)
            theme.text(s, "全屏显示", (x + 570, y + 202), "label", theme.SLATE_200,
                       align="midright", bold=True)
            theme.text(s, "显示帧率", (x + 570, y + 264), "label", theme.SLATE_200,
                       align="midright", bold=True)
            self.tg_fs.draw(s)
            self.tg_fps.draw(s)
            theme.text(s, "特效质量", (x + 40, y + 318), "label", theme.SLATE_200, bold=True)
            self.seg_quality.update(self.dt, mouse)
            if self.seg_quality.handle(events, mouse):
                self.settings["quality"] = self.seg_quality.index
                theme.quality = self.seg_quality.index
                self.particles.cap = (260, 520, 900)[self.seg_quality.index]
                audio.sfx("ui_click", 0.7)
            self.seg_quality.draw(s)
            self.sl_ui.update(self.dt, mouse)
            if self.sl_ui.handle(events, mouse):
                self.settings["ui_scale"] = round(0.9 + self.sl_ui.value * 0.5, 2)
                theme.ui_scale = self.settings["ui_scale"]
            self.sl_ui.draw(s)
            self.sl_shake.update(self.dt, mouse)
            if self.sl_shake.handle(events, mouse):
                self.settings["shake"] = self.sl_shake.value
            self.sl_shake.draw(s)
            self.sl_flash.update(self.dt, mouse)
            if self.sl_flash.handle(events, mouse):
                self.settings["flash"] = self.sl_flash.value
            self.sl_flash.draw(s)

        # ---- 操作 ----
        else:
            theme.text(s, "点击右侧按键可重映射", (x + 40, y + 172), "small",
                       theme.alpha_color(theme.SLATE_300, 210))
            theme.text(s, "恢复默认键位", (x + 720, y + 172), "small",
                       theme.alpha_color(theme.SLATE_300, 200), align="midright")
            self._reset_rect = pygame.Rect(x + 640, y + 162, 84, 20)
            if self._reset_rect.collidepoint(mouse):
                theme.text(s, "恢复默认键位", (x + 720, y + 172), "small",
                           theme.GOLD_LIGHT, align="midright")
            self.rebind_rects = {}
            for i, act in enumerate(REBIND_ORDER):
                col, row = i % 2, i // 2
                px = x + 46 + col * 340
                py = y + 208 + row * 36
                rect = pygame.Rect(px - 8, py - 13, 314, 26)
                self.rebind_rects[act] = rect
                if self.rebind_action == act:
                    pygame.draw.rect(s, theme.alpha_color(theme.GOLD, 46), rect, border_radius=6)
                    pygame.draw.rect(s, theme.alpha_color(theme.GOLD, 140), rect, 1, border_radius=6)
                    theme.text(s, "按任意键…（Esc 取消）", (rect.centerx, rect.centery), "tiny",
                               theme.GOLD_LIGHT, align="center", shadow=False)
                else:
                    if rect.collidepoint(mouse):
                        pygame.draw.rect(s, theme.alpha_color((255, 255, 255), 18),
                                         rect, border_radius=6)
                    theme.text(s, KEY_LABEL.get(act, act), (px, py), "small", theme.SLATE_300,
                               align="midleft")
                    theme.text(s, " / ".join(_key_name(c) for c in KEYMAP[act][:2]),
                               (px + 300, py), "small", theme.GOLD_LIGHT, align="midright")

        # ---- 改键：捕获下一次按键 ----
        if self.rebind_action:
            for ev in events:
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        self.rebind_action = None
                    else:
                        self._assign_key(self.rebind_action, ev.key)
                        self.rebind_action = None
                    break
            self.set_back.draw(s)
            return

        # ---- 操作页的点击：恢复默认 / 选中改键 ----
        if tab == 2:
            for ev in events:
                if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                    if getattr(self, "_reset_rect", None) and self._reset_rect.collidepoint(ev.pos):
                        apply_keymap(None)
                        audio.sfx("ui_click", 0.7)
                        break
                    for act, rect in getattr(self, "rebind_rects", {}).items():
                        if rect.collidepoint(ev.pos):
                            self.rebind_action = act
                            break

        self.set_back.update(self.dt, mouse)
        if self.set_back.handle(events, mouse):
            audio.sfx("ui_click", 0.7)
            self._commit_settings()
            self.goto(self.return_scene if self.return_scene != "SETTINGS" else "MENU")
            return
        self.set_back.draw(s)
        theme.text(s, "设置自动保存至 settings.json", (x + self.set_panel.w - 30, y + 592),
                   "tiny", theme.alpha_color(theme.SLATE_400, 180), align="right")

        for ev in events:
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self._commit_settings()
                self.goto(self.return_scene if self.return_scene != "SETTINGS" else "MENU")
                return

    def _commit_settings(self):
        self.settings["master"] = self.sl_master.value
        self.settings["music"] = self.sl_music.value
        self.settings["sfx"] = self.sl_sfx.value
        self.settings["fullscreen"] = self.tg_fs.value
        self.settings["show_fps"] = self.tg_fps.value
        self.settings["quality"] = self.seg_quality.index
        self.settings["shake"] = round(self.sl_shake.value, 2)
        self.settings["flash"] = round(self.sl_flash.value, 2)
        self.settings["ui_scale"] = round(0.9 + self.sl_ui.value * 0.3, 2)
        audio.set_volume(self.settings["master"], self.settings["music"], self.settings["sfx"])
        self._apply_fx_settings()
        # 键位必须一起落盘：apply_keymap() 启动时读的是 settings["keys"]，
        # 但之前没有任何地方写它（keymap_to_json 是死代码），
        # 结果改完键位重启就回默认，和 README 写的"键位保存在 settings.json"不符。
        self.settings["keys"] = keymap_to_json()
        save_settings(self.settings)

    def _apply_fx_settings(self):
        try:
            fx.Camera.trauma_mul = theme.clamp(self.settings.get("shake", 1.0))
            self.post.flash_mul = theme.clamp(self.settings.get("flash", 1.0))
            theme.ui_scale = theme.clamp(self.settings.get("ui_scale", 1.0), 0.9, 1.4)
            theme.quality = max(0, min(2, int(self.settings.get("quality", 1) or 0)))
        except Exception:
            pass

    # ==================================================================
    # 场景：联机菜单
    # ==================================================================
    def scene_net_menu(self, events, keys, mouse):
        s = self.screen
        self.draw_menu_background(self.dt)
        theme.text(s, "双人联机", (SCREEN_W // 2, 120), "h1", (255, 240, 200),
                   align="center", bold=True)
        theme.text(s, "房主为权威服务器 · 队友只发送输入并渲染同步状态",
                   (SCREEN_W // 2, 162), "body", theme.alpha_color(theme.SLATE_200, 210),
                   align="center")
        for b in self.net_buttons:
            b.update(self.dt, mouse)
        for i, b in enumerate(self.net_buttons):
            b.focus = (i == self.net_index)
            if b.handle(events, mouse):
                audio.sfx("ui_click", 0.8)
                if i == 0:
                    self.goto("HOST_SETUP")
                elif i == 1:
                    self.goto("CLIENT_CONNECT")
                else:
                    self.goto("MENU")
                return
        for b in self.net_buttons:
            b.draw(s)
        for ev in events:
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    self.goto("MENU")
                    return
                if ev.key in (pygame.K_UP, pygame.K_DOWN):
                    self.net_index = (self.net_index + (1 if ev.key == pygame.K_DOWN else -1)) % 3
                    audio.sfx("ui_hover", 0.5)
                if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.net_index < 2:
                    if self.net_index == 0:
                        self.goto("HOST_SETUP")
                    else:
                        self.goto("CLIENT_CONNECT")
                    return

    def start_host(self):
        global engine, shared, server, client, guest, single_mode, last_state
        global player_pid, host_pid
        try:
            guest = False
            single_mode = False
            server and server.stop()
            engine = GameEngine()
            engine.mods = set(self.challenges)     # 房主选的词条是服务器权威
            engine.difficulty = DIFFICULTIES[self.diff_index][2]
            host_pid = self.host_role
            player_pid = host_pid
            shared = Shared()
            server = HostServer(engine, shared, port=5555, host_pid=host_pid)
            server.start()
            self._stop_lan()
            self._lan_stop = threading.Event()
            threading.Thread(target=core.lan_announce_loop,
                             args=(self._lan_stop, "暮色之前房间", 5555),
                             daemon=True).start()
            client = None
            last_state = None
            self.grid = engine.grid
            self.goto("HOST_WAIT")
        except Exception as e:
            print("[创建房间失败]", e)

    def scene_host_setup(self, events, keys, mouse):
        """创建房间前：房主选角色、词条、难度。"""
        s = self.screen
        self.draw_menu_background(self.dt)
        theme.text(s, "创建房间", (SCREEN_W // 2, 108), "h1", (255, 240, 200),
                   align="center", bold=True)
        theme.text(s, "选角色 · 词条 · 难度后创建（队友自动取另一个角色）",
                   (SCREEN_W // 2, 150), "body", theme.alpha_color(theme.SLATE_200, 210),
                   align="center")

        # 角色选择（两个按钮）
        cx = SCREEN_W // 2
        self.host_role_btns = []
        for i in (0, 1):
            nm = core.ROLE_NAME[i]
            r = pygame.Rect(cx - 260 + i * 280, 190, 240, 120)
            self.host_role_btns.append(r)
            pygame.draw.rect(s, (255, 255, 255, 16), r, border_radius=12)
            if self.host_role == i:
                pygame.draw.rect(s, theme.alpha_color(ROLE_COLOR[i], 80), r, border_radius=12)
                pygame.draw.rect(s, theme.alpha_color(ROLE_COLOR[i], 200), r, 2, border_radius=12)
            theme.text(s, nm, (r.centerx, r.centery - 12), "title",
                       (255, 244, 220) if self.host_role == i else theme.SLATE_300,
                       align="center", bold=self.host_role == i)
            theme.text(s, "弓手射飞行怪" if i == 0 else "盾卫清地面怪", (r.centerx, r.centery + 22),
                       "tiny", theme.alpha_color(theme.SLATE_300, 200), align="center")

        # 难度
        theme.text(s, "难度", (cx, 326), "label", theme.GOLD_LIGHT, bold=True)
        self.diff_rect = pygame.Rect(cx - 150, 356, 300, 40)
        pygame.draw.rect(s, (255, 255, 255, 12), self.diff_rect, border_radius=8)
        theme.text(s, "<  " + DIFFICULTIES[self.diff_index][1] + "  >",
                   self.diff_rect.center, "title", theme.GOLD_LIGHT, align="center", bold=True)
        theme.text(s, "点击切换（影响怪物血量/伤害）", (cx, 412), "tiny",
                   theme.alpha_color(theme.SLATE_400, 200), align="center")

        # 词条 chips
        theme.text(s, "挑战词条（可选，提升得分）", (cx, 446), "small",
                   theme.alpha_color(theme.SLATE_300, 220), align="center")
        self.setup_challenge_rects = {}
        cw, gap = 230, 16
        cx0 = (SCREEN_W - (cw * 3 + gap * 2)) // 2
        for i, (cid, name, desc, mul) in enumerate(CHALLENGES):
            # 52 高时说明文字离底边只剩 1px，几乎贴在边框上
            rect = pygame.Rect(cx0 + i * (cw + gap), 468, cw, 58)
            on = cid in self.challenges
            pygame.draw.rect(s, theme.alpha_color(theme.GOLD, 42) if on else (0, 0, 0, 0),
                             rect, border_radius=10)
            pygame.draw.rect(s, theme.alpha_color(theme.GOLD if on else theme.SLATE_400,
                                                  170 if on else 90), rect, 1, border_radius=10)
            theme.text(s, ("√ " if on else "") + name, (rect.x + 14, rect.y + 10), "body",
                       (54, 38, 12) if on else theme.SLATE_300, bold=on, shadow=not on)
            theme.text(s, "×%.1f" % mul, (rect.right - 14, rect.y + 10), "small",
                       (70, 50, 18) if on else theme.alpha_color(theme.SLATE_400, 200),
                       align="right", shadow=not on)
            theme.text(s, desc, (rect.x + 14, rect.y + 34), "tiny",
                       (62, 44, 14) if on else theme.alpha_color(theme.SLATE_300, 200),
                       shadow=not on)
            self.setup_challenge_rects[cid] = rect

        # 创建按钮
        self.host_create_btn = getattr(self, "host_create_btn", None)
        if self.host_create_btn is None:
            self.host_create_btn = ui.Button(pygame.Rect(0, 0, 260, 54), "创建房间", "gold", icon="play")
        self.host_create_btn.rect.x = cx - 130
        self.host_create_btn.rect.y = 560
        self.host_create_btn.update(self.dt, mouse)
        if self.host_create_btn.handle(events, mouse):
            audio.sfx("ui_click", 1.0)
            self.start_host()
            return
        self.host_create_btn.draw(s)

        for ev in events:
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.goto("NET_MENU")
                return
            if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                for i, r in enumerate(self.host_role_btns):
                    if r.collidepoint(ev.pos):
                        self.host_role = i
                        audio.sfx("ui_hover", 0.7)
                        return
                if self.diff_rect.collidepoint(ev.pos):
                    self.diff_index = (self.diff_index + 1) % len(DIFFICULTIES)
                    audio.sfx("ui_hover", 0.7)
                    return
                for cid, crect in self.setup_challenge_rects.items():
                    if crect.collidepoint(ev.pos):
                        if cid in self.challenges:
                            self.challenges.discard(cid)
                        else:
                            self.challenges.add(cid)
                        audio.sfx("ui_hover", 0.8)
                        return
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_LEFT, pygame.K_a):
                    self.host_role = 0
                elif ev.key in (pygame.K_RIGHT, pygame.K_d):
                    self.host_role = 1
                elif ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.start_host()
                    return

    def _start_lan_listen(self):
        if self._lan_stop is None:
            self._lan_stop = threading.Event()
            self._lan_q = queue.Queue()
            self._lan_rooms = {}
            threading.Thread(target=core.lan_listen,
                             args=(self._lan_q, self._lan_stop), daemon=True).start()

    def _stop_lan(self):
        try:
            if self._lan_stop is not None:
                self._lan_stop.set()
        except Exception:
            pass
        self._lan_stop = None

    def scene_client_connect(self, events, keys, mouse):
        s = self.screen
        self._start_lan_listen()
        self.draw_menu_background(self.dt)
        theme.text(s, "加入房间", (SCREEN_W // 2, 140), "h1", (255, 240, 200),
                   align="center", bold=True)
        theme.text(s, "输入房主地址：局域网 IP:5555，或 ngrok 分配的 域名:端口",
                   (SCREEN_W // 2, 186), "body", theme.alpha_color(theme.SLATE_200, 210),
                   align="center")
        # 收集局域网广播并显示可一键加入的房间
        try:
            while True:
                room, ip, port = self._lan_q.get_nowait()
                self._lan_rooms[ip] = (room, port)
        except queue.Empty:
            pass
        if self._lan_rooms:
            theme.text(s, "局域网发现（点击加入）", (SCREEN_W // 2, 240), "small",
                       theme.alpha_color(theme.LIME, 220), align="center")
            self.lan_room_rects = []
            for i, (ip, (room, port)) in enumerate(list(self._lan_rooms.items())[:2]):
                r = pygame.Rect(SCREEN_W // 2 - 240, 262 + i * 34, 480, 28)
                self.lan_room_rects.append((ip, port, r))
                pygame.draw.rect(s, (255, 255, 255, 12), r, border_radius=7)
                theme.text(s, "%s  %s:%d" % (room, ip, port), (r.x + 12, r.centery),
                           "small", theme.SLATE_200, align="midleft")
        self.addr_input.rect.x = SCREEN_W // 2 - 260
        self.addr_input.rect.y = 320
        self.addr_input.update(self.dt, mouse)
        res = self.addr_input.handle(events, mouse)
        if res == "submit":
            self._do_connect()
            return
        self.addr_input.draw(s)

        self.connect_btn.rect.x = SCREEN_W // 2 - 110
        self.connect_btn.rect.y = 400
        self.connect_btn.update(self.dt, mouse)
        if self.connect_btn.handle(events, mouse):
            audio.sfx("ui_click", 0.8)
            self._do_connect()
            return
        self.connect_btn.draw(s)
        for ip, port, r in getattr(self, "lan_room_rects", []):
            for ev in events:
                if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and r.collidepoint(ev.pos):
                    self.addr_input.text = "%s:%d" % (ip, port)
                    audio.sfx("ui_click", 0.8)
                    self._do_connect()
                    return

        self.net_back.rect.x = SCREEN_W // 2 - 90
        self.net_back.rect.y = 476
        self.net_back.update(self.dt, mouse)
        if self.net_back.handle(events, mouse):
            audio.sfx("ui_click", 0.6)
            self.goto("NET_MENU")
            return
        self.net_back.draw(s)

        if net_error:
            theme.text(s, "连接失败：" + str(net_error), (SCREEN_W // 2, 548), "body",
                       theme.DANGER, align="center")
        theme.text(s, "房主请先点击「创建房间」，端口需在防火墙放行",
                   (SCREEN_W // 2, 586), "small", theme.alpha_color(theme.SLATE_400, 190),
                   align="center")

        for ev in events:
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                self.goto("NET_MENU")
                return

    def _do_connect(self):
        global client, net_out, net_error, guest, single_mode
        try:
            text = self.addr_input.text.strip()
            if not text or "例如" in text:
                net_error = "请输入房主地址，例如 192.168.1.10:5555"
                return
            host, port = parse_addr(text)
            if not host:
                net_error = "地址格式错误，需要 域名:端口"
                return
            net_error = None
            net_out = queue.Queue()
            guest = True
            single_mode = False
            client = NetClient(host, port, net_out, self._client_err)
            self.goto("HOST_WAIT")
        except Exception as e:
            net_error = str(e)

    def _client_err(self, msg):
        global net_error
        try:
            net_error = str(msg)
            if self.scene in ("GAME", "HOST_WAIT"):
                add_chat("系统", "网络异常：" + str(msg))
        except Exception:
            pass

    def scene_host_wait(self, events, keys, mouse):
        s = self.screen
        self.draw_menu_background(self.dt)
        if not guest:
            theme.text(s, "房间已创建", (SCREEN_W // 2, 130), "h1", (255, 240, 200),
                       align="center", bold=True)
            ip = local_ip()
            port = shared.port if shared and shared.port else 5555
            box = pygame.Rect(SCREEN_W // 2 - 280, 210, 560, 96)
            theme.rounded_panel(s, box, (20, 24, 40), theme.alpha_color(theme.GOLD, 110), 14, alpha=240)
            theme.text(s, "局域网地址", (box.x + 24, box.y + 24), "small",
                       theme.alpha_color(theme.SLATE_300, 220))
            theme.text(s, f"{ip}:{port}", (box.x + 24, box.y + 52), "title", theme.GOLD_LIGHT,
                       bold=True)
            theme.text(s, "异地联机请用  ngrok tcp 5555  并把转发地址发给队友",
                       (SCREEN_W // 2, 330), "body", theme.alpha_color(theme.SLATE_200, 210),
                       align="center")
            # 等待动画
            dots = "." * (int(self.t * 2) % 4)
            theme.text(s, "等待队友加入" + dots, (SCREEN_W // 2, 400), "title",
                       theme.GOLD_LIGHT, align="center", bold=True)
            status = shared.status if shared else ""
            theme.text(s, status, (SCREEN_W // 2, 442), "small",
                       theme.alpha_color(theme.SLATE_300, 210), align="center")
            if shared and shared.error:
                theme.text(s, shared.error, (SCREEN_W // 2, 476), "small", theme.DANGER,
                           align="center")
            ready = bool(shared and shared.client_ready)
            if shared and shared.client_connected:
                theme.text(s, "队友已准备！" if ready else "队友已加入，正在准备…",
                           (SCREEN_W // 2, 496), "body", theme.LIME if ready else theme.GOLD_LIGHT,
                           align="center", bold=True)
                if ready:
                    a = 0.6 + 0.4 * math.sin(self.t * 4)
                    theme.text(s, "按 空格 开始冒险（世界在开始前保持冻结）",
                               (SCREEN_W // 2, 528), "small",
                               theme.alpha_color(theme.GOLD_LIGHT, int(150 + 90 * a)),
                               align="center")
            theme.text(s, "ESC 返回主菜单", (SCREEN_W // 2, 580), "small",
                       theme.alpha_color(theme.SLATE_400, 190), align="center")
            for ev in events:
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    if server:
                        server.stop()
                    self.goto("MENU")
                    return
                if (ev.type == pygame.KEYDOWN and ev.key in (pygame.K_SPACE, pygame.K_RETURN)
                        and ready and shared):
                    try:
                        shared.q_host_input.put_nowait({"type": "start",
                                                "mods": set(self.challenges),
                                                "difficulty": DIFFICULTIES[self.diff_index][2]})
                    except Exception:
                        pass
                    audio.sfx("portal", 0.7)
                    self.goto("GAME", 0.4)
        else:
            theme.text(s, "正在连接房主", (SCREEN_W // 2, 220), "h1", (255, 240, 200),
                       align="center", bold=True)
            dots = "." * (int(self.t * 2) % 4)
            theme.text(s, "同步世界状态" + dots, (SCREEN_W // 2, 300), "title",
                       theme.GOLD_LIGHT, align="center")
            if net_error:
                theme.text(s, "错误：" + str(net_error), (SCREEN_W // 2, 360), "body",
                           theme.DANGER, align="center")
            theme.text(s, "ESC 取消并返回", (SCREEN_W // 2, 470), "small",
                       theme.alpha_color(theme.SLATE_400, 190), align="center")
            for ev in events:
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    if client:
                        client.close()
                    self.goto("MENU")
                    return
            got = False
            try:
                while True:
                    item = net_out.get_nowait()
                    if item[0] == "state":
                        if _valid_state(item[1]):
                            self.last_state = item[1]
                            got = True
                    elif item[0] == "hello":
                        global player_pid
                        try:
                            player_pid = int(item[1].get("you", 1))
                        except Exception:
                            player_pid = 1
                        add_chat("系统", "已连接房主 · 你是" + ROLE_NAME[player_pid])
            except queue.Empty:
                pass
            if got:
                self.goto("GAME", 2.2)

    # ==================================================================
    # 场景：游戏
    # ==================================================================
    def scene_game(self, events, keys, mouse):
        global last_state, last_state_time, chat_active, chat_text, player_pid, ai_cmd
        # ---------- 1. 推进世界 ----------
        evs = []
        st = None
        if guest:
            try:
                while True:
                    item = net_out.get_nowait()
                    if item[0] == "state":
                        if _valid_state(item[1]):
                            last_state = item[1]
                            last_state_time = item[2]
            except queue.Empty:
                pass
            st = last_state
            if st:
                _sync_gate_tiles(self.grid, st)
                evs = list(st.get("events", []))
                _aim = (st["players"][player_pid]["x"], st["players"][player_pid]["y"]) if st else None
                inp = _host_input(keys, mouse, player_pid, self.cam.x, self.cam.y, PAD.poll(), _aim)
                frozen = bool(st.get("lobby") or st.get("paused"))
                if chat_active or self.help_open or frozen:
                    inp = _mask_input(inp)
                if client:
                    client.send_input(inp)
        elif single_mode:
            if self.hitstop > 0:
                # 命中定格：世界暂停 30~250ms，只保留渲染，手感会"实"很多
                self.hitstop -= self.dt
                self.acc = min(self.acc, TICK_DT)
            else:
                self.acc += min(self.dt, 0.12)
            steps = 0
            _aim = (self.last_st["players"][player_pid]["x"],
                    self.last_st["players"][player_pid]["y"]) if self.last_st else None
            inp = _host_input(keys, mouse, player_pid, self.cam.x, self.cam.y,
                              PAD.poll(), _aim)
            if chat_active or self.help_open:
                inp = _mask_input(inp)
            while self.acc >= TICK_DT and steps < 4 and self.hitstop <= 0:
                try:
                    ai_pid = 1 - player_pid
                    inp_ai = core.make_ai_input(ai_pid, engine, player_pid, ai_cmd)
                    engine.step({player_pid: inp, ai_pid: inp_ai}, TICK_DT)
                    evs.extend(engine.events)
                except Exception as e:
                    print("[推演异常]", e)
                self.acc -= TICK_DT
                steps += 1
            self._ai_catch_up()
            self._advance_tutorial(inp, engine.pack())
            st = engine.pack()
        else:
            try:
                if shared:
                    data = shared.get_state()
                    if data and data[0]:
                        obj, _ = core.decode_pkt(data[0])
                        if obj:
                            st = obj
            except Exception:
                pass
            if st:
                evs = list(st.get("events", []))
                _aim = (st["players"][player_pid]["x"], st["players"][player_pid]["y"]) if st else None
                inp = _host_input(keys, mouse, player_pid, self.cam.x, self.cam.y, PAD.poll(), _aim)
                if chat_active or self.help_open or st.get("lobby") or st.get("paused"):
                    inp = _mask_input(inp)
                if server:
                    # 只丢弃过期的 "input"，其他消息（pause/chat）必须保留——
                    # 原来无条件清空整条队列，会把刚放进来的恢复消息抢在
                    # 服务线程 30Hz 读取之前丢掉，房主"暂停->继续"后世界永久冻结
                    keep = []
                    try:
                        while True:
                            item = shared.q_host_input.get_nowait()
                            if isinstance(item, dict) and item.get("type") == "input":
                                continue
                            keep.append(item)
                    except queue.Empty:
                        pass
                    for item in keep:
                        try:
                            shared.q_host_input.put_nowait(item)
                        except Exception:
                            pass
                    try:
                        shared.q_host_input.put_nowait({"type": "input", "input": inp})
                    except Exception:
                        pass

        if st is None:
            self.draw_menu_background(self.dt)
            # 少传了画布：字符串被当成 surf、坐标被当成文本，
            # theme.text 内部抛 ValueError，客机首帧（还没收到状态包）每帧崩一次
            theme.text(self.screen, "同步世界状态…", (SCREEN_W // 2, SCREEN_H // 2), "title",
                       theme.GOLD_LIGHT, align="center")
            return
        self.last_st = st

        focus_pid = player_pid
        fp = st["players"].get(focus_pid, {})
        fx_x, fx_y = fp.get("x", 120), fp.get("y", 570)

        # ---------- 2. 事件 → 音效/粒子/震动 ----------
        self.handle_events(evs, focus_pid)

        # ---------- 3. 相机 ----------
        self.cam.update(self.dt, fx_x, fx_y - 105, (core.WORLD_W, core.WORLD_H), 8.0)


        # ---------- 4. 绘制 ----------
        s = self.screen
        region = theme.clamp((fx_x - (core.FORGE_LEFT - 3) * core.TILE) / (5 * core.TILE), 0.0, 1.0)
        ws = self.world_surf
        self.renderer.draw_world(ws, st, self.grid, self.cam, self.t, st.get("rocks", []), region, focus_pid)
        self.particles.update(self.dt)
        self.particles.draw(ws, self.cam.px, self.cam.py)
        self.floats.update(self.dt)
        self.floats.draw(ws, self.cam.px, self.cam.py)
        pygame.transform.scale(ws, (SCREEN_W, SCREEN_H), s)
        self.post.draw(s)
        # 无敌/低血屏幕效果
        if fp.get("hp", 1) / max(1, fp.get("maxhp", 1)) < 0.28:
            pulse = 0.10 + 0.06 * math.sin(self.t * 5)
            edge = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            pygame.draw.rect(edge, (180, 20, 24, 60), (0, 0, SCREEN_W, SCREEN_H), 26)
            edge.set_alpha(int(200 * pulse * 3))
            s.blit(edge, (0, 0))
        # 冲刺速度线
        if fp.get("dash_cd", 1) > fp.get("dash_max", 1) - 0.12:
            for i in range(10):
                y = random.randint(60, SCREEN_H - 60)
                ln = random.randint(40, 120)
                x0 = 0 if fp.get("facing", 1) > 0 else SCREEN_W
                pygame.draw.line(s, theme.alpha_color((255, 255, 255), 90),
                                 (x0, y), (x0 + (ln if fp.get("facing", 1) > 0 else -ln), y), 2)
        # 熔岩区的余烬（增强"熔炉"氛围）
        if region > 0.45 and len(self.particles.items) < self.particles.cap * 0.6:
            if random.random() < 0.55:
                ex = self.cam.x + random.uniform(0, WORLD_VW)
                ey = self.cam.y + WORLD_VH - random.uniform(0, 40)
                self.particles.burst("ember", ex, ey, (255, 150, 60), count=1, power=0.7)
        # 暮色区的萤火
        elif region < 0.35 and len(self.particles.items) < self.particles.cap * 0.5:
            if random.random() < 0.10:
                ex = self.cam.x + random.uniform(0, WORLD_VW)
                ey = self.cam.y + random.uniform(WORLD_VH * 0.45, WORLD_VH * 0.9)
                self.particles.burst("ember", ex, ey, (196, 240, 140), count=1, power=0.35)

        self.draw_hud(st, focus_pid)
        if not single_mode and (st.get("lobby") or st.get("paused")):
            if st.get("paused"):
                self._draw_net_overlay(s, "房主已暂停", "等待房主继续…")
            else:
                self._draw_net_overlay(
                    s, "等待房主开始",
                    "队友已准备 · 房主按 空格 开始" if guest else "按 空格 开始（世界尚未开始）")
        if (not pygame.key.get_focused() and not chat_active
                and pygame.display.get_driver() != "dummy"):
            tip = pygame.Rect(0, 0, 430, 32)
            tip.center = (SCREEN_W // 2, SCREEN_H - 92)
            theme.rounded_panel(s, tip, (18, 14, 12), theme.alpha_color(theme.GOLD, 130), 9,
                                alpha=235, shadow=False)
            theme.text(s, "窗口未获得键盘焦点 · 点击画面后即可操作", tip.center, "small",
                       theme.GOLD_LIGHT, align="center", shadow=False)
        # 双人机关提示
        if not st.get("duo_open", False):
            _px = fp.get("x", -999)
            _on = any(abs(_px - (c * core.TILE + 16)) < 46 for c in core.DUO_PLATE_COLS)
            if _on and abs(fp.get("y", 0) - 19 * core.TILE) < 40:
                _box = pygame.Rect(0, 0, 520, 40)
                _box.center = (SCREEN_W // 2, SCREEN_H - 128)
                theme.rounded_panel(s, _box, (16, 18, 30), theme.alpha_color(theme.GOLD, 120), 9,
                                    alpha=236, shadow=False)
                theme.text(s, "需要两人同时站上两块机关 · 按 F 给同伴下「守点」指令",
                           _box.center, "small", theme.GOLD_LIGHT, align="center", shadow=False)

        # 藤蔓抓取提示
        _near_vine = False
        for _v in core.VINES:
            _dx, _dy = _v[2] - _v[0], _v[3] - _v[1]
            _L2 = _dx * _dx + _dy * _dy
            if _L2 <= 1:
                continue
            _t = ((fp.get("x", 0) - _v[0]) * _dx + (fp.get("y", 0) - 6 - _v[1]) * _dy) / _L2
            _t = max(0.0, min(1.0, _t))
            _px = _v[0] + _dx * _t
            _py = _v[1] + _dy * _t
            if (_px - fp.get("x", 0)) ** 2 + (_py - (fp.get("y", 0) - 6)) ** 2 <= 46 ** 2:
                _near_vine = True
                break
        if _near_vine and fp.get("vine", -1) < 0:
            _sc = SCREEN_W / float(WORLD_VW)
            _vx = int((fp.get("x", 0) - self.cam.px) * _sc)
            _vy = int((fp.get("y", 0) - self.cam.py) * _sc) - 46
            theme.text(s, "空格 / E 抓住藤蔓", (_vx, _vy), "tiny", theme.alpha_color(theme.LIME, 230),
                       align="center", shadow=True)

        # 弓箭手准星
        if focus_pid == 0 and not chat_active:
            mx_, my_ = mouse
            if my_ > 76:
                col = (255, 236, 180) if not pygame.mouse.get_pressed()[0] else (255, 170, 120)
                pygame.draw.circle(s, theme.alpha_color(col, 210), (mx_, my_), 9, 1)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    pygame.draw.line(s, theme.alpha_color(col, 200),
                                     (mx_ + dx * 12, my_ + dy * 12),
                                     (mx_ + dx * 17, my_ + dy * 17), 1)
                pygame.draw.circle(s, theme.alpha_color(col, 150), (mx_, my_), 1)
        self.draw_banner(st)
        self.draw_chat()
        if self.help_open:
            self.draw_help()
        if self.settings.get("show_fps"):
            fps = self.clock.get_fps()
            theme.text(s, "FPS %d" % fps, (SCREEN_W - 14, SCREEN_H - 24), "small",
                       theme.alpha_color(theme.LIME, 200), align="right")

        # ---------- 5. 音乐 ----------
        if self.scene == "GAME":
            has_boss = any(m["kind"] == "boss" for m in st.get("monsters", []))
            near = any(abs(m["x"] - fx_x) < 900 for m in st.get("monsters", []))
            audio.play_music("boss" if has_boss else ("battle" if near else "explore"))

        # ---------- 6. 输入 ----------
        for ev in events:
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    if self.help_open:
                        self.help_open = False
                    elif chat_active:
                        chat_active = False
                    else:
                        self.goto("PAUSE", 5.0)
                        return
                elif ev.key == pygame.K_F1:
                    self.help_open = not self.help_open
                    audio.sfx("ui_click", 0.6)
                elif _key_is(ev.key, "switch") and single_mode:
                    player_pid = 1 - player_pid
                    audio.sfx("ui_click", 0.7)
                    add_chat("系统", "已切换到：" + ROLE_NAME[player_pid])
                elif _key_is(ev.key, "command") and single_mode:
                    idx = core.AI_COMMANDS.index(ai_cmd) if ai_cmd in core.AI_COMMANDS else 0
                    ai_cmd = core.AI_COMMANDS[(idx + 1) % len(core.AI_COMMANDS)]
                    audio.sfx("ui_click", 0.7)
                    add_chat("系统", "同伴指令：" + core.AI_CMD_LABEL[ai_cmd])
                elif _key_is(ev.key, "recall") and single_mode:
                    # 一键召回：AI 卡地形 / 追怪跑偏时按一下，立刻切回跟随并归位
                    ai_cmd = "follow"
                    warped = engine is not None and engine.recall_ally()
                    audio.sfx("ui_click", 0.8)
                    add_chat("系统", "同伴已召回身边" if warped else "同伴指令：跟随")
                elif ev.key == pygame.K_F12:
                    self.tutorial_done = True
                    add_chat("系统", "已跳过教学")
                elif ev.key == pygame.K_RETURN and not chat_active:
                    chat_active = True
                    chat_text = ""
                    try:
                        pygame.key.start_text_input()
                        self._ti_ok = True
                    except Exception:
                        self._ti_ok = False
                elif chat_active and ev.key == pygame.K_RETURN:
                    if chat_text.strip():
                        self._send_chat(chat_text.strip(), focus_pid)
                    chat_text = ""
                    chat_active = False
                    try:
                        pygame.key.stop_text_input()
                    except Exception:
                        pass
                elif chat_active and ev.key == pygame.K_BACKSPACE:
                    chat_text = chat_text[:-1]
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if self.pause_rect_hit(ev.pos):
                    self.goto("PAUSE", 5.0)
                    return

        # 聊天文本：按"批次"去重——同一批事件里只要有 TEXTINPUT，就只认它；
        # 没有 TEXTINPUT 时才回退 KEYDOWN.unicode（兼容部分输入法/驱动）。
        if chat_active:
            ti = "".join(e.text for e in events if e.type == pygame.TEXTINPUT)
            if ti:
                chat_text = (chat_text + ti)[:50]
            else:
                for ev in events:
                    if ev.type == pygame.KEYDOWN and ev.unicode and ev.unicode.isprintable():
                        if ev.key in (pygame.K_RETURN, pygame.K_BACKSPACE, pygame.K_ESCAPE):
                            continue
                        if len(chat_text) < 50:
                            chat_text += ev.unicode

        # 胜负
        if st.get("win") and not self.result_shown:
            self.result_shown = True
            # 结算必须用这一帧的真实状态包。全局 last_state 只有客机分支会赋值，
            # 单人/房主走这里是 None -> _update_records({}) -> compute_score 恒 1200、
            # win 恒假、records 永不更新（主玩法的计分一直是坏的）
            self.final_state = st
            audio.sfx("win", 1.0)
            self.goto("RESULT", 1.4)

    def _ai_catch_up(self):
        """把当前 AI 托管角色同步给引擎（引擎负责实际的"归队"兜底）。"""
        try:
            if single_mode and engine is not None:
                engine.ai_pid = 1 - player_pid
        except Exception:
            pass

    def pause_rect_hit(self, pos):
        return pygame.Rect(SCREEN_W - 56, 14, 42, 42).collidepoint(pos)

    def _send_chat(self, text, pid):
        if single_mode and engine is not None:
            engine.push_chat(ROLE_NAME[pid] + "(你)", text)
            add_chat(ROLE_NAME[pid], text)
        elif guest and client:
            client.send_chat(text)
            add_chat("我", text)
        elif server and shared:
            try:
                shared.q_host_chat.put_nowait({"type": "chat", "text": text})
            except Exception:
                pass
            add_chat(ROLE_NAME[pid], text)

    # ------------------------------------------------------------------
    # 事件处理（音效 / 粒子 / 震屏 / 飘字）
    # ------------------------------------------------------------------
    def handle_events(self, evs, focus_pid):
        for ev in evs:
            try:
                k = ev[0]
                x = ev[1] if len(ev) > 1 else 0
                y = ev[2] if len(ev) > 2 else 0
                if k == "jump":
                    audio.sfx("jump", 0.55)
                    self.particles.burst("jump", x, y + 22, (170, 190, 210), count=6, power=0.8)
                elif k == "dash":
                    audio.sfx("dash", 0.6)
                    self.particles.burst("dust", x, y + 30, (200, 210, 230), count=8, power=1.2)
                    self.cam.add_trauma(0.10)
                elif k == "shoot":
                    audio.sfx("shoot", 0.55)
                elif k == "hit":
                    audio.sfx("hit", 0.5)
                    self.particles.burst("spark", x, y, (255, 214, 140), count=7, power=0.9)
                    if single_mode:
                        self.hitstop = max(self.hitstop, 0.03)
                elif k == "swing":
                    audio.sfx("sword", 0.5)
                    self.particles.burst("spark", x, y, (220, 236, 255), count=5, power=0.7)
                elif k == "break":
                    audio.sfx("hit", 0.35)
                    self.particles.burst("debris", x, y, (180, 168, 150), count=4, power=0.7)
                elif k == "rock_break":
                    audio.sfx("rock_break", 0.85)
                    self.particles.burst("debris", x, y, (168, 158, 146), count=16, power=1.3)
                    self.floats.add(x, y - 10, "岩墙崩塌", theme.GOLD_LIGHT, "small")
                    self.cam.add_trauma(0.32)
                elif k == "stray_clear":
                    # 卡在地形里的残余怪被兜底清掉了，给个明确的视觉反馈，
                    # 免得玩家以为"怪怎么突然没了"
                    self.particles.burst("dust", x, y, (150, 138, 170), count=14, power=1.1)
                    self.floats.add(x, y - 20, "残敌退散", (176, 168, 190), "small")
                elif k == "die":
                    kind = ev[3] if len(ev) > 3 else "ground"
                    if kind == "boss":
                        audio.sfx("death", 1.0)
                        self.cam.add_trauma(0.85)
                        self.post.hit_flash((255, 200, 140), 0.5, full=True)
                        self.particles.burst("spark", x, y - 30, (255, 190, 110), count=40, power=1.8)
                        self.particles.burst("debris", x, y, (150, 140, 130), count=26, power=1.5)
                        self.hitstop = max(self.hitstop, 0.30) if single_mode else 0.0
                        self.floats.add(x, y - 60, "守卫倒下", theme.GOLD_LIGHT, "title", bold=True)
                    else:
                        audio.sfx("hit", 0.5)
                        self.particles.burst("blood", x, y, (200, 50, 58), count=12, power=1.0)
                        self.cam.add_trauma(0.16)
                        if single_mode:
                            self.hitstop = max(self.hitstop, 0.045)
                elif k == "hurt":
                    audio.sfx("hurt", 0.7)
                    self.particles.burst("blood", x, y + 10, (210, 60, 66), count=6, power=0.8)
                    self.cam.add_trauma(0.26)
                    self.post.hit_flash((220, 40, 40), 0.36)
                elif k == "dmg":
                    amt = ev[3] if len(ev) > 3 else 0
                    self.floats.add(x, y, "-%d" % int(amt), (255, 150, 150), "label", bold=True)
                elif k == "block":
                    audio.sfx("block", 0.75)
                    self.particles.burst("spark", x, y, (150, 220, 255), count=10, power=1.0)
                    self.floats.add(x, y - 16, "格挡", (150, 225, 255), "small")
                    self.cam.add_trauma(0.14)
                elif k == "pad":
                    audio.sfx("pad", 0.8)
                    self.particles.burst("spark", x, y, (120, 220, 255), count=10, power=1.2)
                elif k == "pad_spawn":
                    audio.sfx("plate", 0.7)
                    self.particles.burst("magic", x, y, (255, 210, 120), count=12, power=1.2)
                elif k == "plate":
                    audio.sfx("plate", 0.75)
                elif k == "lava":
                    audio.sfx("lava", 0.35)
                    self.particles.burst("ember", x, y, (255, 140, 50), count=3, power=0.8)
                elif k == "impale":
                    audio.sfx("spike", 1.0)
                    self.particles.burst("blood", x, y, (200, 30, 40), count=18, power=1.4)
                    self.cam.add_trauma(0.5)
                    self.post.hit_flash((160, 20, 24), 0.6)
                elif k == "spike_hit":
                    audio.sfx("spike", 0.7)
                    self.particles.burst("blood", x, y, (210, 50, 56), count=8, power=0.9)
                    self.cam.add_trauma(0.28)
                elif k == "hammer":
                    audio.sfx("hammer", 0.9)
                    self.particles.burst("spark", x, y, (255, 190, 120), count=14, power=1.3)
                    self.cam.add_trauma(0.42)
                elif k == "rock_crack":
                    audio.sfx("rock_break", 0.35)
                    self.particles.burst("debris", x, y + 8, (150, 132, 150), count=9, power=0.8)
                    self.floats.add(x, y + 30, "裂缝！", (190, 140, 220), "small")
                elif k == "rock_warn":
                    audio.sfx("ui_hover", 0.3)
                    self.particles.burst("smoke", x, y + 20, (180, 170, 160), count=6, power=0.6)
                elif k == "rock_land":
                    audio.sfx("rock_break", 0.6)
                    self.particles.burst("debris", x, y - 6, (150, 142, 134), count=14, power=1.2)
                    self.cam.add_trauma(0.3)
                elif k == "rock_hit":
                    audio.sfx("hurt", 0.8)
                    self.cam.add_trauma(0.3)
                elif k == "checkpoint":
                    audio.sfx("checkpoint", 0.8)
                    self.particles.burst("heal", x, y, (255, 220, 150), count=16, power=1.1)
                    self.floats.add(x, y - 20, "检查点已激活", theme.GOLD_LIGHT, "body", bold=True)
                elif k == "weapon":
                    audio.sfx("portal", 0.9)
                    self.cam.add_trauma(0.35)
                    self.post.hit_flash((255, 180, 80), 0.4)
                    self.particles.burst("magic", x, y, (255, 210, 120), count=40, power=2.4)
                    self.floats.add(x, y - 24, "烈焰核心！伤害 +50%", (255, 210, 120), "title", bold=True)
                elif k == "chest":
                    audio.sfx("chest", 0.8)
                    self.particles.burst("heal", x, y, (180, 255, 190), count=16, power=1.0)
                    if len(ev) > 3:
                        self.floats.add(x, y - 10, "+%d HP" % ev[3], (150, 240, 160), "label", bold=True)
                elif k == "vine_grab":
                    audio.sfx("pad", 0.55)
                    self.particles.burst("spark", x, y, (150, 200, 110), count=7, power=0.7)
                elif k == "vine_release":
                    audio.sfx("ui_hover", 0.45)
                elif k == "rune_gate":
                    _on = bool(ev[3]) if len(ev) > 3 else False
                    audio.sfx("plate", 0.85 if _on else 0.6)
                    self.particles.burst("magic", x, y, (140, 230, 255),
                                         count=14 if _on else 7, power=1.1 if _on else 0.7)
                    self.floats.add(x, y - 18, "符文激活" if _on else "符文熄灭",
                                    (170, 236, 255) if _on else (150, 170, 190), "small")
                elif k == "portal":
                    audio.sfx("portal", 0.9)
                    self.cam.add_trauma(0.35)
                    self.particles.burst("magic", x, y, (255, 210, 140), count=26, power=1.4)
                elif k == "win":
                    audio.sfx("win", 1.0)
                    self.cam.add_trauma(0.5)
                elif k == "nightfall":
                    audio.sfx("portal", 0.55)
                    self.cam.add_trauma(0.3)
                    add_chat("系统", "夜幕降临……援军的裂隙正在开启")
                elif k == "ally_warp":
                    audio.sfx("checkpoint", 0.45)
                    self.particles.burst("magic", x, y - 30, (120, 220, 255), count=14, power=1.1)
                    add_chat("系统", "同伴已归队")
                elif k == "cast":
                    audio.sfx("shoot", 0.35)
                    self.particles.burst("spark", x, y, (255, 150, 70), count=6, power=0.7)
                elif k == "fizzle":
                    self.particles.burst("smoke", x, y, (180, 120, 120), count=5, power=0.6)
                elif k == "boss_enrage":
                    audio.sfx("death", 0.8)
                    self.cam.add_trauma(0.7)
                    self.post.hit_flash((255, 60, 40), 0.5, full=False)
                    self.particles.burst("ember", x, y - 30, (255, 110, 60), count=24, power=1.5)
                    self.floats.add(x, y - 90, "狂暴！", (255, 120, 90), "title", bold=True)
                # ---- 以下 8 个事件原来完全没有反馈（引擎抛出、主程序没有分支）----
                elif k == "parry":
                    # 完美格挡是"看红光"的核心奖励，必须有明确回馈
                    audio.sfx("block", 1.0)
                    self.cam.add_trauma(0.4)
                    self.post.hit_flash((255, 255, 230), 0.22, full=False)
                    self.particles.burst("spark", x, y, (255, 246, 210), count=22, power=1.6)
                    self.floats.add(x, y - 26, "完美格挡！", (255, 246, 200), "label", bold=True)
                elif k == "guard_break":
                    # 破防被击飞：玩家需要知道"举盾硬顶"失败了
                    audio.sfx("hurt", 1.0)
                    self.cam.add_trauma(0.45)
                    self.post.hit_flash((255, 120, 90), 0.3, full=False)
                    self.particles.burst("dust", x, y, (220, 190, 160), count=14, power=1.2)
                    self.floats.add(x, y - 26, "破防！", (255, 140, 110), "label", bold=True)
                elif k == "shock":
                    # Boss 的冲击波是会造成伤害的，没有声音等于"偷袭"
                    audio.sfx("hammer", 0.75)
                    self.cam.add_trauma(0.4)
                    self.particles.burst("dust", x, y, (240, 200, 170), count=18, power=1.5)
                elif k == "boss_slam_up":
                    audio.sfx("hammer", 0.4)
                    self.particles.burst("dust", x, y, (220, 190, 160), count=8, power=0.8)
                elif k == "boss_summon":
                    audio.sfx("portal", 0.5)
                    self.particles.burst("magic", x, y, (200, 120, 255), count=16, power=1.2)
                elif k == "duo_open":
                    audio.sfx("portal", 0.8)
                    self.cam.add_trauma(0.3)
                    self.particles.burst("magic", x, y, (255, 214, 140), count=20, power=1.3)
                    self.floats.add(x, y - 30, "闸门升起", theme.GOLD_LIGHT, "label", bold=True)
                elif k == "rift_open":
                    audio.sfx("hammer", 0.3)
                    self.particles.burst("magic", x, y, (170, 120, 240), count=10, power=0.9)
                elif k == "wave_start":
                    audio.sfx("plate", 0.85)
                    self.cam.add_trauma(0.2)
                    self.msg = "熔炉守卫狂暴了！冲锋更快、还会连续冲锋！"
                elif k == "land":
                    self.particles.burst("land", x, y, (176, 160, 146), count=9, power=1.0)
                    self.cam.add_trauma(0.06)
                elif k == "boss_spawn":
                    audio.sfx("hammer", 1.0)
                    self.cam.add_trauma(0.6)
                    self.post.hit_flash((255, 120, 60), 0.45, full=False)
                    self.particles.burst("spark", x, y, (255, 160, 80), count=30, power=1.6)
                    self.floats.add(x, y - 70, "熔炉守卫", (255, 170, 90), "title", bold=True)
                elif k == "boss_charge":
                    audio.sfx("dash", 0.9)
                    self.cam.add_trauma(0.35)
                    self.particles.burst("dust", x, y - 10, (200, 180, 160), count=14, power=1.4)
                elif k == "boss_slam":
                    audio.sfx("hammer", 0.85)
                    self.cam.add_trauma(0.5)
                    self.particles.burst("debris", x, y - 4, (160, 150, 140), count=20, power=1.3)
                elif k == "respawn":
                    audio.sfx("death", 0.8)
                    self.post.hit_flash((120, 20, 30), 0.7)
                    self.cam.add_trauma(0.45)
                elif k == "fall":
                    audio.sfx("fall", 0.7)
                elif k == "boss_windup":
                    # 树精举手蓄力：低沉轰鸣 + 汇聚的紫光
                    audio.sfx("lava", 0.7)
                    self.cam.add_trauma(0.12)
                    self.particles.burst("magic", x, y, (168, 90, 232), count=12, power=1.0)
                elif k == "egg_throw":
                    audio.sfx("shoot", 0.6)
                    self.particles.burst("dust", x, y, (220, 210, 190), count=6, power=0.8)
                elif k == "explode":
                    # 紫色爆炸：轰击 + 紫色火花 + 屏幕震动
                    audio.sfx("hammer", 0.85)
                    self.cam.add_trauma(0.42)
                    self.post.hit_flash((150, 70, 220), 0.30, full=False)
                    self.particles.burst("spark", x, y, (190, 110, 250), count=24, power=1.5)
                    self.particles.burst("magic", x, y, (220, 160, 255), count=14, power=1.2)
                elif k == "bloom":
                    # 树精死亡：大地回春的柔和绿光
                    audio.sfx("checkpoint", 0.7)
                    self.post.hit_flash((120, 220, 120), 0.22, full=False)
                    self.particles.burst("heal", x, y - 10, (130, 220, 120), count=26, power=1.3)
                elif k == "reset":
                    pass
                sh = fx.screen_shake_for_event(k)
                if sh:
                    self.cam.add_trauma(sh * 0.5)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # HUD
    # ------------------------------------------------------------------
    def _advance_tutorial(self, inp, st):
        """按玩家动作逐步推进教学。"""
        try:
            if self.tutorial_done or self.tutorial_step >= len(TUTORIAL_STEPS):
                return
            p = st.get("players", {}).get(player_pid, {})
            if TUTORIAL_STEPS[self.tutorial_step][1](inp, p):
                self.tutorial_step += 1
                if self.tutorial_step >= len(TUTORIAL_STEPS):
                    self.tutorial_done = True
        except Exception:
            pass

    def draw_hud(self, st, focus_pid):
        s = self.screen
        # 分步教学提示（未完成且单机）：放在画面下方，避免和波次横幅/塔提示挤在顶部
        if single_mode and not self.tutorial_done and self.tutorial_step < len(TUTORIAL_STEPS):
            _tip = TUTORIAL_STEPS[self.tutorial_step][0]
            _b = pygame.Rect(0, 0, 620, 32)
            _b.center = (SCREEN_W // 2, SCREEN_H - 96)
            theme.rounded_panel(s, _b, (16, 20, 34), theme.alpha_color(theme.GOLD, 110), 9,
                                alpha=232, shadow=False)
            theme.text(s, _tip + "（F12 跳过）", _b.center, "small", theme.GOLD_LIGHT,
                       align="center", shadow=False)
        # 塔引导：靠近瞭望塔时提示上层有补给与武器
        _px = st.get("players", {}).get(focus_pid, {}).get("x", 0)
        if 88 * core.TILE < _px < 107 * core.TILE and not st.get("weapon_taken", False):
            # 底部是三层叠放的槽位（自下而上）：
            #   键位行 678~698 / 塔引导 645~675 / 教程 608~640 / 交互提示 571~605
            _b = pygame.Rect(0, 0, 480, 30)
            _b.center = (SCREEN_W // 2, SCREEN_H - 60)
            theme.rounded_panel(s, _b, (14, 22, 34), theme.alpha_color(theme.LIME, 110), 9,
                                alpha=210, shadow=False)
            theme.text(s, "↑ 瞭望塔上层有补给与烈焰核心（藤蔓/二段跳可上）", _b.center,
                       "small", theme.alpha_color(theme.LIME, 235), align="center", shadow=False)
        # 顶部渐变底
        top = pygame.Surface((SCREEN_W, 96), pygame.SRCALPHA)
        for i in range(96):
            a = int(190 * (1 - i / 96.0) ** 1.3)
            pygame.draw.line(top, (8, 10, 20, a), (0, i), (SCREEN_W, i))
        s.blit(top, (0, 0))

        # ---- 关卡进度条（最顶部 4px）----
        prog = theme.clamp(st.get("players", {}).get(focus_pid, {}).get("x", 0) / float(core.WORLD_W))
        pygame.draw.rect(s, (26, 30, 46), (0, 0, SCREEN_W, 4))
        # 难度标签：联机时 guest 直接读房主广播的值，避免显示本地默认档
        try:
            _dmul = float(st.get("difficulty", 1.0))
        except Exception:
            _dmul = 1.0
        _dname = {0.7: "简单", 1.0: "标准", 1.4: "困难"}.get(round(_dmul, 2), "标准")
        _dcol = {0.7: (150, 230, 160), 1.0: theme.SLATE_300, 1.4: (255, 150, 140)}.get(
            round(_dmul, 2), theme.SLATE_300)
        theme.text(s, "难度 " + _dname, (SCREEN_W - 16, 74), "small", _dcol,
                   align="right", shadow=False)
        pygame.draw.rect(s, theme.GOLD, (0, 0, int(SCREEN_W * prog), 4))
        for cp in st.get("checkpoints", []):
            cx = int(cp["x"] / float(core.WORLD_W) * SCREEN_W)
            pygame.draw.rect(s, theme.LIME if cp["active"] else (90, 96, 124),
                             (cx - 1, 0, 3, 6))
        px = int(core.PORTAL_RECT[0] / float(core.WORLD_W) * SCREEN_W)
        pygame.draw.rect(s, theme.MAGENTA if st.get("portal") else (80, 70, 96), (px - 2, 0, 5, 7))

        # ---- 暮色进度（顶部中央）：天色进程 + 夜幕倒计时 ----
        try:
            dk = float(st.get("dusk", 0.0) or 0.0)
        except Exception:
            dk = 0.0
        night = bool(st.get("night"))
        night_in = float(st.get("night_in", 0.0) or 0.0)
        # 位置：两张角色卡占 16~582，顶部正中会被第二张卡压住（旧版居中
        # 510~770，左半截藏在卡下面）。挪到卡片右侧的空白带 620~860。
        bw, bh, by = 240, 6, 14
        bx = 620
        pygame.draw.rect(s, (18, 22, 38), (bx, by, bw, bh), border_radius=3)
        pygame.draw.rect(s, theme.mix((255, 196, 110), (86, 108, 170), theme.clamp(dk)),
                         (bx, by, int(bw * theme.clamp(dk)), bh), border_radius=3)
        phase = "深夜" if dk >= 1.0 else ("夜幕" if night else ("暮色" if dk > 0.4 else "黄昏"))
        theme.text(s, phase, (bx + bw + 10, by + 3), "tiny",
                   (150, 170, 230) if night else theme.SLATE_300, align="left", shadow=False)
        if 0 < night_in <= 60:
            blink = int(self.t * 2.5) % 2 == 0
            theme.text(s, "夜幕将至 %ds" % int(night_in), (bx + bw + 52, by + 3), "tiny",
                       (255, 170, 120) if blink else theme.SLATE_300, align="left", shadow=False)

        # ---- 玩家卡片 ----
        for idx, pid in enumerate((0, 1)):
            p = st.get("players", {}).get(pid)
            if not p:
                continue
            x = 16 + idx * 292
            y = 12
            r = pygame.Rect(x, y, 274, 60)
            is_focus = (pid == focus_pid)
            theme.rounded_panel(s, r, (16, 20, 34), theme.alpha_color(
                ROLE_COLOR[pid], 150 if is_focus else 60), 12, alpha=225, shadow=False)
            # 头像
            port = pygame.Rect(x + 8, y + 8, 44, 44)
            theme.rounded_panel(s, port, (30, 34, 52), theme.alpha_color(ROLE_COLOR[pid], 120), 9,
                                shadow=False, alpha=255)
            img = sprites.get_char("archer" if pid == 0 else "guard", "idle0")
            mini = pygame.transform.scale(img, (22, 32))
            s.blit(mini, mini.get_rect(center=port.center))
            # 名字与血量
            nm = ROLE_NAME[pid] + ("（你）" if pid == focus_pid else "")
            theme.text(s, nm, (x + 62, y + 12), "body", (255, 244, 220), bold=True, shadow=False)
            hp = p.get("hp", 0)
            mxh = max(1, p.get("maxhp", 1))
            ratio = theme.clamp(hp / float(mxh))
            self.hp_ghost[pid] = max(ratio, self.hp_ghost[pid] - self.dt * 0.55)
            if single_mode and pid != focus_pid:
                # 只放一行：卡片右侧到血条只有 20px，两行会压住血量数字
                theme.text(s, core.AI_CMD_LABEL.get(ai_cmd, "跟随") + "[F] 召回[G]",
                           (r.right - 12, y + 12), "tiny",
                           theme.alpha_color(theme.GOLD_LIGHT, 190), align="right", shadow=False)
            if float(p.get("power", 1.0)) > 1.01:
                theme.text(s, "\u70ac\u7089\u6838\u5fc3 +50%", (x + 62, y + 52), "tiny",
                           theme.alpha_color((255, 190, 110), 230), shadow=False)
            bar = pygame.Rect(x + 62, y + 36, 158, 12)
            col = theme.LIME if ratio > 0.5 else (theme.GOLD if ratio > 0.25 else theme.DANGER)
            theme.progress_bar(s, bar, ratio, col, bg=(38, 32, 40), radius=6,
                               ghost=self.hp_ghost[pid], border=(70, 62, 70))
            theme.text(s, "%d/%d" % (hp, mxh), (bar.right + 6, bar.centery), "tiny",
                       theme.alpha_color(theme.SLATE_200, 230), align="midleft", shadow=False)

        # ---- 右侧统计 ----
        stats = [("clock", self._fmt_time(st.get("elapsed", 0))),
                 ("star", "%d" % st.get("kills", 0)),
                 ("skull", "%d" % st.get("deaths", 0))]
        bx = SCREEN_W - 72
        for icon_name, val in reversed(stats):
            w = 26 + theme.text_width(val, "body")
            bx -= w
            theme.icon(s, icon_name, (bx + 8, 30), 15, theme.alpha_color(theme.SLATE_300, 220))
            theme.text(s, val, (bx + 20, 30), "body", (255, 240, 214), align="midleft", shadow=False)
            bx -= 12

        # ---- 目标 / Boss 血条 ----
        boss = None
        for m in st.get("monsters", []):
            if m.get("kind") == "boss":
                boss = m
                break
        if boss is not None:
            self._draw_boss_bar(s, boss)
        wave = st.get("wave", 1)
        left = st.get("left", 0)
        if boss is not None:
            pass
        elif st.get("portal"):
            obj = "传送门已激活 · 两人同时进入"
            ocol = theme.MAGENTA
        elif left > 0:
            obj = ("第 %d 波 · 剩余 %d 只" % (wave, left)) if wave else ("剩余 %d 只" % left)
            ocol = theme.GOLD_LIGHT
        else:
            obj = "向熔炉长廊推进"
            ocol = theme.SLATE_200
        if boss is None:
            tw = theme.text_width(obj, "body") + 46
            pill = pygame.Rect(0, 0, tw, 28)
            pill.midtop = (SCREEN_W // 2, 78)
            theme.rounded_panel(s, pill, (14, 18, 32), theme.alpha_color(ocol, 90), 15, alpha=215,
                                shadow=False)
            theme.text(s, obj, pill.center, "body", ocol, align="center", shadow=False, bold=True)

        # ---- 暂停按钮 ----
        pb = pygame.Rect(SCREEN_W - 56, 14, 42, 42)
        ui._blend_panel(s, pb, (24, 28, 44), 210, 10)
        pygame.draw.rect(s, (74, 82, 112), pb, 1, border_radius=10)
        theme.icon(s, "pause", pb.center, 14, theme.SLATE_200)

        # ---- 底部提示 ----
        hints = (("WASD", "移动"), ("空格", "跳跃"), ("Shift", "冲刺"),
                 ("Tab", "切换"), ("E", "交互"), ("Esc", "暂停"))
        x = 16
        y = SCREEN_H - 42
        for keyname, desc in hints:
            cap = pygame.Rect(x, y, theme.text_width(keyname, "tiny") + 14, 20)
            ui.keycap(s, keyname, cap.center, "tiny")
            theme.text(s, desc, (cap.right + 6, cap.centery), "tiny",
                       theme.alpha_color(theme.SLATE_300, 210), align="midleft", shadow=False)
            x = cap.right + 10 + theme.text_width(desc, "tiny") + 14

        # ---- 冲刺冷却环 ----
        p = st.get("players", {}).get(focus_pid, {})
        cd = p.get("dash_cd", 0)
        cdmax = p.get("dash_max", 1)
        ready = cd <= 0.001
        cx, cy = SCREEN_W - 54, SCREEN_H - 52
        pygame.draw.circle(s, (22, 26, 42), (cx, cy), 24)
        pygame.draw.circle(s, (60, 68, 96), (cx, cy), 24, 2)
        if not ready:
            ang0 = -math.pi / 2
            ang1 = ang0 + (1 - cd / cdmax) * math.pi * 2
            pygame.draw.arc(s, theme.TEAL, (cx - 24, cy - 24, 48, 48), ang0, ang1, 4)
        else:
            theme.glow_circle(s, (cx, cy), 22, theme.TEAL, 0.5, 3)
            pygame.draw.circle(s, theme.TEAL, (cx, cy), 24, 2)
        theme.icon(s, "dash", (cx, cy), 18,
                   theme.TEAL if ready else theme.alpha_color(theme.SLATE_400, 200))
        theme.text(s, "冲刺", (cx, cy + 30), "tiny",
                   theme.alpha_color(theme.SLATE_300, 200), align="center", shadow=False)

        # ---- 补给箱提示 ----
        fp = st.get("players", {}).get(focus_pid, {})
        for ch in st.get("chests", []):
            if ch["opened"]:
                continue
            if abs(ch["x"] - fp.get("x", -999)) < core.CHEST_RANGE:
                tip = pygame.Rect(0, 0, 240, 34)
                tip.center = (SCREEN_W // 2, SCREEN_H - 132)
                theme.rounded_panel(s, tip, (16, 20, 34), theme.alpha_color(theme.GOLD, 120), 9,
                                    alpha=230, shadow=False)
                ui.keycap(s, "E", (tip.x + 22, tip.centery), "small")
                theme.text(s, "开启补给箱", (tip.x + 42, tip.centery), "body",
                           theme.GOLD_LIGHT, align="midleft", shadow=False)
                break

    def _update_records(self, st):
        """结算时结算分数、刷新记录。"""
        try:
            mult = 1.0
            for cid, _n, _d, m in CHALLENGES:
                if cid in self.challenges:
                    mult *= m
            self._result_mult = mult
            score = compute_score(st, mult)
            self._result_score = score
            rec = dict(self.records)
            new = {}
            rec["runs"] = int(rec.get("runs", 0)) + 1
            if st.get("win"):
                rec["wins"] = int(rec.get("wins", 0)) + 1
                elapsed = float(st.get("elapsed", 0))
                bt = rec.get("best_time")
                if bt is None or elapsed < float(bt):
                    rec["best_time"] = round(elapsed, 1)
                    new["time"] = True
                kills = int(st.get("kills", 0))
                if kills > int(rec.get("best_kills", 0)):
                    rec["best_kills"] = kills
                    new["kills"] = True
                deaths = int(st.get("deaths", 0))
                rank = "S" if deaths == 0 and elapsed < 260 else "A" if deaths <= 1 else \
                       "B" if deaths <= 3 else "C"
                if RANK_ORDER.get(rank, 0) > RANK_ORDER.get(str(rec.get("best_rank", "")), 0):
                    rec["best_rank"] = rank
                    new["rank"] = True
                if score > int(rec.get("best_score", 0)):
                    rec["best_score"] = score
                    new["score"] = True
            self.records = rec
            self._result_new = new
            save_records(rec)
        except Exception:
            pass

    def _draw_net_overlay(self, s, title, sub):
        try:
            ui.dim(s, 150, (6, 8, 14))
            r = pygame.Rect(0, 0, 540, 150)
            r.center = (SCREEN_W // 2, SCREEN_H // 2)
            theme.rounded_panel(s, r, (18, 20, 32), theme.alpha_color(theme.GOLD, 120), 14,
                                alpha=242)
            theme.text(s, title, (r.centerx, r.y + 48), "h2", theme.GOLD_LIGHT,
                       align="center", bold=True)
            theme.text(s, sub, (r.centerx, r.y + 98), "body",
                       theme.alpha_color(theme.SLATE_200, 230), align="center")
        except Exception:
            pass

    def _draw_boss_bar(self, s, boss):
        """Boss 血条：替代普通目标条，附带蓄力警告。"""
        try:
            w = 560
            # 70 时血条顶边(70)压住角色卡底边(72)，视觉上贴在卡上；
            # 横幅在 114，所以挪到 76 并压到 34 高，上下各留 4px。
            r = pygame.Rect((SCREEN_W - w) // 2, 76, w, 34)
            self._boss_bar_rect = r        # 供回归测试检查排版
            theme.rounded_panel(s, r, (26, 14, 16), theme.alpha_color((255, 110, 70), 140), 9,
                                alpha=234, shadow=False)
            ratio = theme.clamp(boss.get("hp", 0) / float(max(1, boss.get("maxhp", 1))))
            theme.text(s, "熔炉守卫", (r.x + 12, r.y + 6), "small", (255, 218, 186),
                       shadow=False, bold=True)
            theme.text(s, "%d / %d" % (boss.get("hp", 0), boss.get("maxhp", 1)),
                       (r.right - 12, r.y + 6), "tiny", (255, 190, 160), align="right", shadow=False)
            inner = pygame.Rect(r.x + 10, r.y + 24, r.w - 20, 7)
            pygame.draw.rect(s, (44, 20, 22), inner, border_radius=3)
            if ratio > 0:
                pygame.draw.rect(s, (255, 126, 62),
                                 (inner.x, inner.y, max(2, int(inner.w * ratio)), inner.h),
                                 border_radius=3)
                pygame.draw.line(s, (255, 210, 170),
                                 (inner.x + 2, inner.y + 1), (inner.x + 2 + int(inner.w * ratio) - 4,
                                                              inner.y + 1), 1)
            if boss.get("enraged"):
                a = 0.5 + 0.5 * math.sin(self.t * 8)
                # 同"冲锋"：align=midleft 时 y 是中心，r.y+6 会让字顶出面板
                theme.text(s, "狂暴", (r.x + 92, r.y + 14), "tiny",
                           theme.alpha_color((255, 90, 80), int(160 + 95 * a)),
                           align="midleft", shadow=False)
            if boss.get("flash", 0) > 0.55 or boss.get("state") == "charge":
                a = 0.5 + 0.5 * math.sin(self.t * 22)
                # y 是"中心"（align=center）：写 r.y+6 时 16px 的字会顶出面板上沿
                theme.text(s, "冲锋！" if boss.get("state") == "charge" else "蓄力中…",
                           (r.centerx + 70, r.y + 14), "tiny",
                           theme.alpha_color((255, 120, 90), int(150 + 105 * a)),
                           align="center", shadow=False)
        except Exception:
            pass

    def _fmt_time(self, sec):
        sec = int(sec)
        return "%d:%02d" % (sec // 60, sec % 60)

    # ------------------------------------------------------------------
    def draw_banner(self, st):
        msg = st.get("msg", "")
        if msg != self.msg_text:
            self.msg_text = msg
            self.msg_t = 4.2 if msg else 0.0
        if self.msg_t <= 0 or not self.msg_text:
            return
        self.msg_t -= self.dt
        a = 1.0 if self.msg_t > 0.8 else max(0.0, self.msg_t / 0.8)
        s = self.screen
        w = min(760, theme.text_width(self.msg_text, "sub") + 64)
        r = pygame.Rect(0, 0, w, 44)
        r.midtop = (SCREEN_W // 2, 114)
        layer = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(layer, theme.alpha_color((10, 12, 22), int(200 * a)),
                         (0, 0, r.w, r.h), border_radius=11)
        pygame.draw.rect(layer, theme.alpha_color(theme.GOLD, int(110 * a)),
                         (0, 0, r.w, r.h), 1, border_radius=11)
        s.blit(layer, (r.x, r.y))
        theme.text(s, self.msg_text, r.center, "sub", (255, 240, 200), align="center",
                   alpha_mul=a)

    def draw_chat(self):
        s = self.screen
        now = time.time()
        vis = [c for c in chat_log if now - c[2] < 9.0]
        y = SCREEN_H - 76
        for who, text, ts in reversed(vis[-5:]):
            age = now - ts
            a = 1.0 if age < 6 else max(0.0, (9.0 - age) / 3.0)
            line = "%s：%s" % (who, text)
            w = theme.text_width(line, "small") + 20
            layer = pygame.Surface((w, 22), pygame.SRCALPHA)
            pygame.draw.rect(layer, theme.alpha_color((10, 12, 22), int(150 * a)),
                             (0, 0, w, 22), border_radius=6)
            s.blit(layer, (12, y - 4))
            theme.text(s, line, (18, y), "small", (232, 238, 252), alpha_mul=a)
            y -= 24
        if chat_active:
            box = pygame.Rect(12, SCREEN_H - 46, 520, 34)
            ui._blend_panel(s, box, (18, 22, 36), 240, 8)
            pygame.draw.rect(s, theme.GOLD, box, 1, border_radius=8)
            caret = "▍" if int(self.t * 2) % 2 == 0 else ""
            theme.text(s, chat_text + caret, (22, box.centery), "body", theme.CREAM,
                       align="midleft", shadow=False)
            theme.text(s, "Enter 发送 · Esc 取消", (box.right + 10, box.centery), "tiny",
                       theme.alpha_color(theme.SLATE_300, 200), align="midleft", shadow=False)

    def draw_help(self):
        s = self.screen
        ui.dim(s, 180)
        w, h = 720, 470
        r = pygame.Rect((SCREEN_W - w) // 2, (SCREEN_H - h) // 2, w, h)
        ui.panel(s, r, "操作说明", "F1 或 Esc 关闭", icon="gear")
        rows = [("移动", "WASD / 方向键"), ("跳跃 / 二段跳", "空格 或 W"),
                ("冲刺（短暂无敌）", "Shift 或 L"), ("射击（弓箭手）", "鼠标左键"),
                ("挥剑（盾卫）", "J"), ("格挡（盾卫）", "K 或 鼠标右键"),
                ("交互 / 开箱", "E"), ("切换操控角色", "Tab"),
                ("同伴指令（循环）", "F"), ("召回同伴", "G"),
                ("聊天", "Enter"), ("暂停", "Esc")]
        for i, (a, b) in enumerate(rows):
            col = i % 2
            row = i // 2
            x = r.x + 40 + col * 330
            y = r.y + 96 + row * 46
            theme.text(s, a, (x, y), "body", theme.SLATE_200, align="midleft")
            theme.text(s, b, (x + 290, y), "body", theme.GOLD_LIGHT, align="midright")
        theme.text(s, "提示：岩浆会持续灼烧，深坑会被刀刺扎死，落石与摆锤可被冲刺躲开",
                   (r.centerx, r.bottom - 46), "small",
                   theme.alpha_color(theme.SLATE_300, 210), align="center")

    # ==================================================================
    # 场景：暂停
    # ==================================================================
    def scene_pause(self, events, keys, mouse):
        s = self.screen
        if self.last_st:
            region = theme.clamp(
                (self.last_st.get("players", {}).get(player_pid, {}).get("x", 0) -
                 (core.FORGE_LEFT - 3) * core.TILE) / (5 * core.TILE), 0, 1)
            self.renderer.draw_world(self.world_surf, self.last_st, self.grid, self.cam, self.t,
                                     self.last_st.get("rocks", []), region, player_pid)
            pygame.transform.scale(self.world_surf, (SCREEN_W, SCREEN_H), s)
            self.post.draw(s)
        ui.dim(s, 165, (4, 5, 12))
        ui.panel(s, self.pause_panel, "暂停", "远征已暂停", icon="pause")
        for b in self.pause_buttons:
            b.update(self.dt, mouse)
            if b.handle(events, mouse):
                audio.sfx("ui_click", 0.8)
                if b is self.pause_buttons[0]:
                    self.goto("GAME", 5.0)
                elif b is self.pause_buttons[1]:
                    self.goto("SETTINGS")
                elif b is self.pause_buttons[2]:
                    self.restart_run()
                else:
                    self.leave_game()
                return
        for b in self.pause_buttons:
            b.draw(s)
        for ev in events:
            if ev.type == pygame.KEYDOWN and ev.key in (pygame.K_ESCAPE, pygame.K_p):
                self.goto("GAME", 5.0)
                return

    # ==================================================================
    # 场景：结算
    # ==================================================================
    def scene_result(self, events, keys, mouse):
        s = self.screen
        st = self.last_st or {}
        if self.last_st:
            region = theme.clamp(
                (self.last_st.get("players", {}).get(player_pid, {}).get("x", 0) -
                 (core.FORGE_LEFT - 3) * core.TILE) / (5 * core.TILE), 0, 1)
            self.renderer.draw_world(s, self.last_st, self.grid, self.cam, self.t,
                                     self.last_st.get("rocks", []), region)
            self.post.draw(s)
        # 金色光尘
        for i in range(30):
            x = (i * 137 + self.t * 30) % SCREEN_W
            y = (SCREEN_H - (self.t * (24 + i % 7) * 3) % (SCREEN_H + 100))
            theme.glow_circle(s, (x, y), 3, (255, 214, 140), 0.5, 2)
        ui.dim(s, 150, (8, 6, 10))
        # 界面缩放：整块内容按 k 一起放大，面板高度也跟着变。
        # 之前只有字号放大、偏移写死，120% 下"击杀 12"会和下面的"得分"标签叠住。
        k = max(1.0, theme.ui_scale)
        h = int(500 * k)
        r = pygame.Rect((SCREEN_W - 620) // 2, (SCREEN_H - h) // 2, 620, h)
        self.result_panel = r
        self.result_buttons[0].rect.topleft = (r.x + 90, r.y + h - 86)
        self.result_buttons[1].rect.topleft = (r.x + 330, r.y + h - 86)

        def _ry(v):
            return r.y + int(v * k)

        ui.panel(s, r, "远征成功", "暮色之前，你们抵达了传送门", icon="star")

        # 数值字段一律强制转型：联机时 st 来自网络，字段可能是字符串/None，
        # 直接 "%d" % kills 或 elapsed < 260 会抛 TypeError
        def _num(v, d=0.0):
            try:
                return float(v)
            except (TypeError, ValueError):
                return d

        deaths = int(_num(st.get("deaths"), 0))
        elapsed = _num(st.get("elapsed"), 0.0)
        kills = int(_num(st.get("kills"), 0))
        rank = "S" if deaths == 0 and elapsed < 260 else "A" if deaths <= 1 else \
               "B" if deaths <= 3 else "C"
        rcol = {"S": theme.GOLD_LIGHT, "A": theme.LIME, "B": theme.TEAL, "C": theme.SLATE_200}[rank]
        # 评级
        theme.text(s, rank, (r.x + 118, _ry(176)), 96, rcol, align="center", bold=True)
        theme.text(s, "评级", (r.x + 118, _ry(240)), "small",
                   theme.alpha_color(theme.SLATE_300, 200), align="center")
        theme.text(s, "用时", (r.x + 250, _ry(130)), "small", theme.SLATE_300)
        theme.text(s, self._fmt_time(elapsed), (r.x + 250, _ry(152)), "title", (255, 244, 220), bold=True)
        theme.text(s, "击杀", (r.x + 250, _ry(196)), "small", theme.SLATE_300)
        theme.text(s, "%d" % kills, (r.x + 250, _ry(218)), "title", (255, 244, 220), bold=True)
        theme.text(s, "阵亡", (r.x + 400, _ry(130)), "small", theme.SLATE_300)
        theme.text(s, "%d" % deaths, (r.x + 400, _ry(152)), "title", (255, 244, 220), bold=True)
        theme.text(s, "评价", (r.x + 400, _ry(196)), "small", theme.SLATE_300)
        comment = "完美远征" if rank == "S" else "配合默契" if rank == "A" else "顺利归来" if rank == "B" else "惊险生还"
        theme.text(s, comment, (r.x + 400, _ry(218)), "sub", rcol, bold=True)

        # ---- 得分与历史记录 ----
        score = self._result_score
        mult = self._result_mult
        theme.text(s, "得分", (r.x + 250, _ry(256)), "small", theme.SLATE_300)
        theme.text(s, str(score), (r.x + 250, _ry(278)), "title", theme.GOLD_LIGHT, bold=True)
        sw = theme.text_width(str(score), "title")
        if mult > 1.001:
            theme.text(s, "挑战 ×%.2f" % mult, (r.x + 250 + sw + 14, _ry(290)), "small",
                       theme.alpha_color(theme.MAGENTA, 230))
        if self._result_new.get("score"):
            theme.text(s, "新纪录", (r.x + 250 + sw + 14, _ry(262)), "tiny", theme.LIME, bold=True)
        if st.get("beat_night"):
            theme.text(s, "残阳加成 +500", (r.x + 250, _ry(316)), "small",
                       theme.alpha_color((255, 196, 110), 240), bold=True)
        rec = self.records
        bt = rec.get("best_time")
        theme.text(s, "历史最佳：%s · %d 杀 · %s 级 · %d 分" % (
            self._fmt_time(float(bt)) if bt else "--:--",
            int(rec.get("best_kills", 0)),
            rec.get("best_rank") or "-",
            int(rec.get("best_score", 0))),
            (r.centerx, _ry(346)), "small", theme.alpha_color(theme.SLATE_300, 215),
            align="center")

        # ---- 行程回顾与搭档评语（数据来自 engine.stats）----
        rst = st.get("stats", {})
        _dmg = rst.get("dmg", [0, 0, 0])
        _bits = []
        if rst.get("max_region", 0) >= 1 and _dmg[1] == 0:
            _bits.append("岩浆段无伤")
        if rst.get("reversals", 0) > 0:
            _bits.append("折返 %d 次" % rst["reversals"])
        if rst.get("weapon"):
            _bits.append("带回了武器核心")
        if rst.get("chests", 0):
            _bits.append("开箱 %d 个" % rst["chests"])
        recap = " · ".join(_bits) if _bits else "一路直奔终点"
        theme.text(s, "行程：" + recap, (r.centerx, _ry(364)), "tiny",
                   theme.alpha_color(theme.SLATE_300, 225), align="center", shadow=False)
        if single_mode:
            if deaths >= 4:
                _line = "下次别逞强……我差点没救回来。"
            elif rst.get("blocks", 0) >= 4:
                _line = "你挡下的那一击救了我。"
            elif not st.get("beat_night"):
                _line = "夜里的路真难走……下次早点出发。"
            elif _dmg[1] == 0 and rst.get("max_region", 0) >= 1:
                _line = "岩浆那段你走得真稳。"
            elif rst.get("weapon"):
                _line = "塔顶那东西真沉——不过值了。"
            elif deaths == 0:
                _line = "零阵亡通关……跟着你很安心。"
            else:
                _line = "活着回来，比什么都重要。"
            theme.text(s, "「%s」—— %s" % (_line, ROLE_NAME[1 - player_pid]),
                       (r.centerx, _ry(380)), "tiny",
                       theme.alpha_color((255, 214, 150), 235), align="center", shadow=False)

        for b in self.result_buttons:
            b.update(self.dt, mouse)
            if b.handle(events, mouse):
                audio.sfx("ui_click", 0.8)
                if b is self.result_buttons[0]:
                    self.restart_run()
                else:
                    self.leave_game()
                return
        for b in self.result_buttons:
            b.draw(s)
        for ev in events:
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.restart_run()
                    return
                if ev.key == pygame.K_ESCAPE:
                    self.leave_game()
                    return

    # ==================================================================
    # 流程控制
    # ==================================================================
    def start_single(self, pid):
        # 把选人界面选的外观同步给精灵系统
        try:
            for _pid, _kind in ((0, "archer"), (1, "guard")):
                _n = len(sprites.skin_list(_kind))
                _v = max(0, min(_n - 1, int(self.skin_index.get(_pid, 0))))
                self.skin_index[_pid] = _v
                sprites.SKIN[_kind] = _v
        except Exception:
            pass
        global engine, shared, server, client, guest, single_mode, player_pid, last_state
        try:
            guest = False
            single_mode = True
            server = None
            client = None
            player_pid = pid
            engine = GameEngine()
            engine.ai_pid = 1 - pid
            engine.mods = set(self.challenges)
            engine.difficulty = DIFFICULTIES[self.diff_index][2]
            self.tutorial_step = 0
            self.tutorial_done = False
            shared = Shared()
            shared.port = 0
            shared.status = "单人模式"
            last_state = None
            self.last_st = None
            self.grid = engine.grid
            add_chat("系统", "单人远征开始 · Tab 切换操控角色 · Shift 冲刺")
            self.goto("GAME")
        except Exception as e:
            print("[单人模式启动失败]", e)

    def restart_run(self):
        global engine
        try:
            if guest:
                self.leave_game()
                return
            if engine is None:
                engine = GameEngine()
            else:
                engine.reset("新的远征开始！")
            self.grid = engine.grid
            self.last_st = None
            self.renderer.invalidate()
            self.goto("GAME", 4.0)
        except Exception:
            self.leave_game()

    def leave_game(self):
        global engine, shared, server, client, guest, single_mode, player_pid, last_state
        try:
            if server:
                server.stop()
            if client:
                client.close()
        except Exception:
            pass
        self._stop_lan()
        server = None
        client = None
        engine = None
        shared = None
        guest = False
        single_mode = False
        player_pid = 0
        last_state = None
        self.last_st = None
        self.grid = None
        self.particles.items.clear()
        self.floats.items.clear()
        self.goto("MENU")

    # ==================================================================
    # 主循环
    # ==================================================================
    def run(self):
        running = True
        while running:
            try:
                self.dt = min(0.05, self.clock.tick(FPS) / 1000.0)
                self.t += self.dt
                events = pygame.event.get()
                for e in events:
                    if e.type == pygame.QUIT:
                        running = False
                keys = pygame.key.get_pressed()
                mouse = pygame.mouse.get_pos()
                self._tick_transition()

                if self.scene == "MENU":
                    self.scene_menu(events, keys, mouse)
                elif self.scene == "CHAR_SELECT":
                    self.scene_char_select(events, keys, mouse)
                elif self.scene == "SETTINGS":
                    self.scene_settings(events, keys, mouse)
                elif self.scene == "NET_MENU":
                    self.scene_net_menu(events, keys, mouse)
                elif self.scene == "HOST_SETUP":
                    self.scene_host_setup(events, keys, mouse)
                elif self.scene == "CLIENT_CONNECT":
                    self.scene_client_connect(events, keys, mouse)
                elif self.scene == "HOST_WAIT":
                    self.scene_host_wait(events, keys, mouse)
                elif self.scene == "GAME":
                    self.scene_game(events, keys, mouse)
                elif self.scene == "PAUSE":
                    self.scene_pause(events, keys, mouse)
                elif self.scene == "RESULT":
                    self.scene_result(events, keys, mouse)
                else:
                    self.goto("MENU")

                # 过场淡入淡出（最顶层）
                if self.post.fade > 0.005:
                    ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
                    ov.fill((5, 6, 12, int(255 * self.post.fade)))
                    self.screen.blit(ov, (0, 0))
                pygame.display.flip()
            except KeyboardInterrupt:
                running = False
            except pygame.error as e:
                if "video system not initialized" in str(e).lower():
                    running = False
                else:
                    print("[pygame错误]", e)
                    time.sleep(0.05)
            except Exception as e:
                print("[主循环异常]", e)
                traceback.print_exc()
                time.sleep(0.05)
        try:
            save_settings(self.settings)
            if server:
                server.stop()
            if client:
                client.close()
            audio.shutdown()
            pygame.quit()
        except Exception:
            pass


def parse_addr(text):
    try:
        t = str(text).strip().replace("：", ":")
        if "://" in t:
            t = t.split("://", 1)[1]
        t = t.split("/")[0]
        if ":" in t:
            host, port = t.rsplit(":", 1)
            return host.strip(), int(port)
        return t, 5555
    except Exception:
        return None, None


def _smoketest(frames=120):
    """打包/部署自检：无窗口跑若干帧并截图，结果写到 exe 同目录。

    用法： 暮色之前.exe --smoketest [帧数]
    配合 SDL_VIDEODRIVER=dummy 可在无人值守环境下验证打包完整性。
    """
    import traceback
    path = os.path.join(app_dir(), "smoketest.txt")
    try:
        app = App()
        app.dt = 1.0 / 60.0
        app.start_single(0)
        app._apply_scene("GAME")
        app.post.fade = 0.0
        keys = pygame.key.get_pressed()
        for _ in range(max(1, frames)):
            app.scene_game([], keys, (640, 360))
        pygame.image.save(app.screen, os.path.join(app_dir(), "smoketest.png"))
        msg = "OK frames=%d tick=%d fps_ok=%s music=%s sfx=%s" % (
            frames, engine.tick if engine else -1,
            pygame.display.get_driver(), audio.status().get("music"),
            audio.status().get("sfx"))
        with open(path, "w", encoding="utf-8") as f:
            f.write(msg + "\n")
        print("[smoketest] " + msg)

        def _mark(tag):
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(tag + "\n")
            except Exception:
                pass

        _mark("before_shutdown")
        audio.shutdown()
        _mark("after_shutdown")
        pygame.quit()
        _mark("after_pygame_quit")
        os._exit(0)
    except Exception:
        with open(path, "w", encoding="utf-8") as f:
            f.write("FAIL\n" + traceback.format_exc())
        traceback.print_exc()
        os._exit(1)


def main():
    try:
        print("[启动] 暮色之前 · Before Dusk")
        print("[启动] 素材与音频均为程序化生成，无外部文件依赖")
    except Exception:
        pass
    if "--smoketest" in sys.argv:
        idx = sys.argv.index("--smoketest")
        n = 120
        try:
            if idx + 1 < len(sys.argv):
                n = max(1, int(sys.argv[idx + 1]))
        except Exception:
            pass
        _smoketest(n)
        return
    app = App()
    app.run()
    try:
        audio.shutdown()
        pygame.quit()
    except Exception:
        pass
    os._exit(0)


if __name__ == "__main__":
    main()
