# -*- coding: utf-8 -*-
"""
game_core.py —— 《暮色之前·双人联机合作》核心模块
============================================================================
本模块负责：地图构建 / 物理碰撞 / 角色技能 / 怪物波次 / 跳板机关 /
岩石破坏 / 传送门 / 服务器权威状态同步（TCP）。

【防不同步设计】
  * 服务器权威：玩家位置、血量、弓箭、怪物、机关、岩石、传送门全部由
    服务器（房主）统一计算，客户端只渲染收到的状态并做插值，从根源
    杜绝画面错位、怪物瞬移。
  * 固定逻辑步长 30Hz，全量状态广播，双方看到的永远是同一份世界。

【高频 Bug 专项修复】
  * 弓箭穿透怪 -> 每支箭命中飞行怪或岩石后立即销毁，且记录命中集合；
  * 跳板重复无限生成 -> 机关激活先检状态、跳板有生命周期、同一机关
    同时只能存在一组跳板；
  * 联机掉线崩溃 -> 所有 socket 读写、存取、pickle 均 try/except；
  * 怪物瞬移错位 -> 怪物只由服务器更新，客户端纯插值渲染；
  * 按键卡帧 -> 移动/格挡用 get_pressed 持续采样，攻击由冷却控制。
"""
import math
import random
import json
import struct
import socket
import select
import threading
import queue
import time
import logging

import ai_nav

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------
TILE = 32
MAP_W = 152                # 终章扩建：112 -> 152（新增"熔炉长廊"40 格 = 1280px）
MAP_H = 28                 # 加高地图：容纳深坑（掉入后跳不出来）
WORLD_W = MAP_W * TILE
WORLD_H = MAP_H * TILE

# ---- 暮色倒计时：天色随时间变暗，夜幕后怪物增援 ----
# 设计：不做硬失败（玩家不会被卡死），而是压力递增——
#   夜幕(默认14分钟)开始定期增援，完全入夜(19分钟)后增援翻倍；
#   赶在夜幕降临前通关有"残阳加成"分数，让速度分有了存在感。
DUSK_FULLNIGHT = 1140.0        # 完全入夜：19 分钟
DUSK_NIGHTFALL = 840.0         # 夜幕降临：14 分钟（难度越高越早，见 nightfall_at）
NIGHT_SPAWN_INTERVAL = 40.0    # 夜幕增援间隔（秒）


def region_of_x(x):
    """行程统计用：0 森林 / 1 岩浆段 / 2 熔炉·瞭望塔"""
    if x < 60 * TILE:
        return 0
    if x < 93 * TILE:
        return 1
    return 2

TICK_HZ = 30
TICK_DT = 1.0 / TICK_HZ
GRAVITY = 2200.0

PLAYER_W, PLAYER_H = 26, 44
MONSTER_W, MONSTER_H = 28, 26
FLY_W, FLY_H = 30, 24
CW_HIT, CH_HIT = 28, 38
ARROW_SPEED = 780.0
ARROW_LIFETIME = 2.2
ARROW_SIZE = 5

PROTOCOL = 4

ROLES = {
    0: {"name": "弓箭手", "spd": 250.0, "maxhp": 80,  "jump": 680.0, "label": "玩家1(弓箭手)"},
    1: {"name": "盾卫",   "spd": 235.0, "maxhp": 130, "jump": 660.0, "label": "玩家2(盾卫)"},
}
ROLE_NAME = {0: "弓箭手", 1: "盾卫"}
PLAYER_START = {
    0: (3 * TILE + 12, 19 * TILE),
    1: (10 * TILE + 12, 19 * TILE),
}
# 终点传送门（熔炉长廊尽头的祭坛高台中央）
PORTAL_RECT = (142 * TILE, 13 * TILE, 5 * TILE, 4 * TILE)
# 熔炉长廊（第三幕）范围：地面连续、无断崖，靠摆锤 / 地刺 / 落石制造压力
FORGE_LEFT = 94
SCORCH_LEFT = 56
DUO_GATE_COL = 120                # 熔炉中段的双人闸门
DUO_PLATE_COLS = (114, 118)       # 两块必须同时踩住的机关
DUO_PLATE_RANGE = 30
DUO_HOLD_TIME = 0.45

# ---- 藤蔓滑索（多层地图的纵向交通）----
# 藤蔓端点约定：
#   上端 y = 平台顶 - 6  （角色脚 = 绳点 +6，正好踩在平台面上）
#   上端 x = 落在平台列范围内，且绳子中段要绕开平台左/右边缘，避免穿模
VINES = [
    # 森林：地面 -> P2(17-20) 顶；终点留 4px 余量，别擦平台左缘
    (13 * TILE + 14, 19 * TILE - 20, 17 * TILE + 22, 13 * TILE - 6),
    # 森林：P3(24-27) 顶 -> 地面
    (26 * TILE + 30, 13 * TILE - 6, 33 * TILE + 16, 19 * TILE - 20),
    # 岩浆：地面 -> 平台(66-69) 顶
    (60 * TILE + 16, 19 * TILE - 20, 67 * TILE - 4, 13 * TILE - 6),
    # 岩浆：平台(79-81) 顶 -> 地面
    # （原起点在 73-76，直线会横穿 79-81 整块平台；改从 79-81 顶出发）
    (80 * TILE, 13 * TILE - 6, 84 * TILE + 16, 19 * TILE - 20),
    # 塔 F1 顶 -> F2 顶（贴 F2 左外侧上升，不穿 F2 底板）
    # 顶端必须离开 F2 左缘至少半个身位，否则角色会卡在平台边被挤进去
    # 底端锚在 col 98（F1 中间）而不是左缘 96：下藤松手时背后就是深坑(90~93)，
    # 落点太靠左会顺方向掉进去，来回折腾像卡死
    (98 * TILE, 15 * TILE - 6, 97 * TILE + 24, 11 * TILE - 6),
    # 塔 F2 顶 -> F3 顶
    (98 * TILE + 6, 11 * TILE - 6, 99 * TILE + 16, 7 * TILE - 6),
]
VINE_GRAB_R = 34.0

# ---- 飞怪巡逻高度带（不再贴着脸跟，改为有"领地高度"）----
FLY_BAND_TOP = 200.0
FLY_BAND_BOT = 430.0
FLY_DIVE_WINDOW = 60.0        # 玩家在这个高度带内才会被俯冲

# ---- 熔炉瞭望塔：三层楼 ----
TOWER_F2_Y = 11 * TILE        # 第二层顶面 352
TOWER_F3_Y = 7 * TILE         # 第三层顶面 224
TOWER_CHEST_X = 100 * TILE + 16
TOWER_WEAPON_X = 100 * TILE + 16
# 烈焰机关：第二层地面两处，周期性喷火
VENTS = [
    {"x": 98 * TILE + 16, "y": TOWER_F2_Y, "period": 2.6, "on": 0.55, "t": 0.0},
    {"x": 102 * TILE + 16, "y": TOWER_F2_Y, "period": 3.4, "on": 0.55, "t": 1.2},
]
VENT_DMG = 14
VENT_RANGE_X = 20.0
VENT_HEIGHT = 78.0
WEAPON_POWER = 1.5
# ---- 共鸣门：一人站符文，门才开，另一人进门取物（塔 F2 的可选遭遇）----
RUNE_COL = 98                 # 守门符文所在列（F2 表面）
RUNE_GATE_COL = 103           # 门所在列（F2 通道，挡住通往隔间的路）
RUNE_GATE_ROWS = (4, 10)      # 门占用行：9-10 是门扇，4-8 是门楣，防止二段跳翻越
RUNE_RANGE = 30.0
RUNE_CLOSE_DELAY = 0.5        # 符文释放后门的关闭延迟            # 拿到烈焰核心后全队伤害 +50%
TOWER_GUARD_R = 150.0
VINE_SPEED = 300.0

# ---- 双人机关（必须两人同时站住）----                            # 岩壁区起点：从这里到熔炉入口是焦土/玄武岩
FORGE_RIGHT = 151

# 压力机关 -> 生成的浮空跳板配置（跳板为单边平台，带弹跳）
# 仅保留 A 机关（跨 A 断崖用）；B 机关随旧地图布局废弃
PLATE_CONFIGS = [
    {"id": "A", "cx": 4,  "pads": [(37, 17), (38, 17), (39, 17), (40, 17), (41, 17)], "dur": 12.0},
]
PAD_BOUNCE = -760.0
PAD_HEIGHT = 10
WAVE2_TRIGGER_X = 56 * TILE + 16

# ---- 低洼岩浆坑上方的来回移动阶板 ----
# x0/x1 为阶板来回移动的网格列范围(左边缘)，y 为阶板站台顶面像素y，spd 为摆动角速度
# phase 错相使两个阶板交替出现在坑内任何位置，保证总有一个可搭乘
# 地面高608、岩浆表面640，阶板顶560：地面跳上48px、岩浆跳上80px，一跳/二段跳均可到达
M_PAD_CONFIGS = [
    {"id": "M1", "x0": 63, "x1": 79, "y": 560, "spd": 0.9, "phase": 0.0},
    {"id": "M2", "x0": 63, "x1": 79, "y": 560, "spd": 0.9, "phase": math.pi * 0.5},
]
M_PAD_W = TILE * 2            # 阶板宽度：2 格
M_PAD_H = 12                  # 阶板视觉厚度(px)
LAVA_DMG = 10                 # 岩浆每跳扣血
LAVA_TICK = 0.4               # 扣血间隔
LAVA_MONSTER_DMG = 3
LAVA_MONSTER_TICK = 0.35

# 岩浆坑区域（列号）
LAVA_LEFT = 64
LAVA_RIGHT = 79
LAVA_ROW = 20                 # 岩浆层所在 grid 行（玩家脚踩的岩浆表面 640px）
LAVA_REGION = (64, 19, 79, 21)  # (x0, y0, x1, y1) 整块坑洞区域
LAVA_SURFACE_Y = LAVA_ROW * TILE   # 岩浆表面像素高度
LAVA_LEFT_PX = LAVA_LEFT * TILE    # 坑左缘像素
LAVA_RIGHT_PX = (LAVA_RIGHT + 1) * TILE  # 坑右缘像素

# ---- 深坑刀刺陷阱：可覆盖坑口的上下往复刀刺阶板 ----
# 深坑位于岩浆坑（列64~79）的右侧，中间隔 10 格长走道（列80~89，宽320px）：
# 跨过岩浆后沿走道前进，再借助刀刺阶板过此深坑
PIT_COLS = (90, 93)                        # 深坑列范围（含，岩浆右侧）
PIT_TOP_ROW = 19                           # 坑口所在行（与地面齐平）
PIT_TOP_Y = PIT_TOP_ROW * TILE             # 坑口像素 y
PIT_FLOOR_ROW = 27                         # 坑底所在 grid 行（世界最底部行，作为深坑坑底）
PIT_FLOOR_Y = PIT_FLOOR_ROW * TILE         # 坑底像素 y（落坑后被困坑底，等待刀刺压落扎死）
SPIKE_PAD_W = 4 * TILE                     # 刀刺阶板宽（与坑同宽 4 格）
SPIKE_PAD_H = 14                           # 阶板厚
SPIKE_H = 34                               # 刀刺长度
SPIKE_CFG = {
    "x0": 90, "x1": 93,                    # 阶板列范围（深坑列，岩浆右侧长走道之后）
    # 上升大幅提高：顶面最高位 400（高出坑口地面208px，玩家在坑上方高空可踏上）；
    # 最低位 840（刀刺顶端伸入坑底顶面之下10px，仍能扎死坑底被困者；
    #             且板顶不进入坑底实体区，骑板者全程被携带、不会被物理吸到坑底）
    "y_top": 19 * TILE - 208,              # 顶面最高位 400
    "y_bot": PIT_FLOOR_Y - 24,             # 顶面最低位 840：刀尖扎入坑底，骑板不会脱板
    "spd": 1.2,                            # 上下摆动角速度(rad/s)
    "phase": math.pi / 2,                  # sin(+π/2)=1 -> y=mid+amp*1=400=最高位(y_top)，初始压顶随即下沉再上探
}

# ---- 熔炉长廊陷阱配置 ----
# 摆锤：pivot 为悬挂点，len 摆杆长度，r 锤头半径，spd 角速度，phase 初相
HAMMER_CFG = [
    {"id": "H1", "cx": 113, "cy": 12, "len": 150, "r": 26, "spd": 1.55, "phase": 0.0},
    {"id": "H2", "cx": 121, "cy": 12, "len": 150, "r": 26, "spd": 1.75, "phase": 2.1},
    {"id": "H3", "cx": 133, "cy": 11, "len": 176, "r": 30, "spd": 1.45, "phase": 4.0},
]
HAMMER_DMG = 14

# 地刺带：贴地尖刺，踩到扣血并向上弹开（不致死，用于消耗）
SPIKE_STRIPS = [(110, 111), (126, 127), (134, 135)]
BRAMBLE_IDX = (1, 2)           # 红黑荆棘条：视觉是"活物"，行为也和金属刺区分
SPIKE_STRIP_H = 12
SPIKE_STRIP_DMG = 9

# 落石：玩家靠近触发，从高处坠落，命中造成大量伤害
FALL_ROCK_CFG = [
    {"id": "F1", "cx": 117, "y0": 5 * TILE},
    {"id": "F2", "cx": 130, "y0": 4 * TILE},
    {"id": "F3", "cx": 145, "y0": 5 * TILE},
]
FALL_ROCK_DMG = 18
FALL_ROCK_TRIGGER = 108.0

# 检查点（触碰即激活，阵亡后在此复活）
CHECKPOINT_COLS = [46, 86, 108, 138]
# 补给箱（靠近按 E 开启，恢复生命）
CHEST_CFG = [
    {"id": "C1", "cx": 34, "heal": 28, "cy": 19},
    {"id": "C2", "cx": 82, "heal": 32, "cy": 19},
    {"id": "C3", "cx": 129, "heal": 36, "cy": 19},
    {"id": "C4", "cx": 18, "heal": 34, "cy": 13},
    {"id": "C5", "cx": 74, "heal": 34, "cy": 13},
    {"id": "C6", "cx": 101, "heal": 30, "cy": 15},     # 瞭望塔一层
    {"id": "C7", "cx": 100, "heal": 32, "cy": 11},     # 瞭望塔二层
    {"id": "C8", "cx": 104, "heal": 36, "cy": 11},     # 共鸣门后隔间
]
CHEST_RANGE = 60.0

# ---- 熔岩术士（远程敌人）----
CASTER_HP = 3
CASTER_SPEED = 66.0
CASTER_CAST_CD = 2.7
CASTER_KEEP_MIN = 190.0          # 靠得太近就后撤
CASTER_KEEP_MAX = 330.0          # 离得太远就贴近
CASTER_RANGE = 560.0
FIREBALL_SPEED = 285.0
FIREBALL_DMG = 10
FIREBALL_R = 7
FIREBALL_LIFE = 3.2

# ---- 精英变体 ----
ELITE_HP_MUL = 2.2
ELITE_DMG_MUL = 1.35

# ---- 熔炉守卫（Boss）----
BOSS_W, BOSS_H = 64, 86
BOSS_HP = 42
BOSS_SPEED = 78.0
BOSS_CHARGE_SPEED = 430.0
BOSS_CHARGE_TELE = 0.62          # 蓄力（红光警示）时长
BOSS_CHARGE_TIME = 0.72          # 冲刺持续时间
BOSS_RECOVER = 0.85
BOSS_TOUCH_DMG = 16
BOSS_TRIGGER_X = 130 * TILE       # 玩家越过此列 -> 唤醒守卫
BOSS_MAXHP_BAR = True
BOSS_PHASE2 = 0.66          # 血量低于此比例进入二阶段（砸地波）
BOSS_PHASE3 = 0.33          # 三阶段（召唤术士 + 更频繁冲锋）
BOSS_SLAM_CD = 4.2
BOSS_SLAM_POWER = 880
SHOCK_SPEED = 520.0
SHOCK_DMG = 12
SHOCK_MAX_R = 260.0
PARRY_WINDOW = 0.16         # 举盾后这段时间内被打中 = 完美格挡

# 冲刺
DASH_SPEED = 640.0
DASH_TIME = 0.16
DASH_CD = 1.15
DASH_IFRAME = 0.22
RESPAWN_IFRAME = 1.6
RESPAWN_HP_RATIO = 0.6

SWORD_RANGE = 56
SWORD_DMG = 1.5
ARROW_DMG = 1               # 每支箭基础伤害（弓箭手）
GROUND_MONSTER_HP = 3
FLY_MONSTER_HP = 2
DAMAGE_TICK_GAP = 0.5          # 触碰伤害间隔(持续扣血)
GROUND_DMG_TO_ARCHER = 8
GROUND_DMG_TO_SHIELD = 5
FLY_DMG = 6
ROCK_HP = 3


def write_log(msg):
    try:
        logging.getLogger("core").info(msg)
    except Exception:
        pass


def rect_overlap(a, b):
    """a,b = (x,y,w,h) 轴对齐矩形相交检测"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def point_in_rect(px, py, r):
    rx, ry, rw, rh = r
    return rx <= px <= rx + rw and ry <= py <= ry + rh


# --------------------------------------------------------------------------
# 网络封包
# --------------------------------------------------------------------------
def encode_pkt(obj):
    """JSON 序列化：不再用 pickle——对不可信地址连接时 pickle 可执行任意代码。"""
    data = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return struct.pack(">I", len(data)) + data


MAX_PACKET = 2 * 1024 * 1024


class PacketError(Exception):
    """封包协议错误：长度非法，流已不可信，调用方应断开连接。"""


def decode_pkt(buf):
    """从字节缓冲中解析一个包，返回 (对象或None, 剩余缓冲)。

    三种情况必须分清：
      * 数据没到齐           -> (None, buf)，原样保留等更多字节
      * 长度合法但 JSON 坏了 -> (None, buf[4+n:])，按声明长度跳过，流仍然对齐
      * 长度非法(<=0 或超限) -> 抛 PacketError。此时无法判断包边界，
        继续读只会把 payload 当包头，之后每个包都错位（旧版返回 buf[4:]
        就是这个坑：丢了 4 字节头却留着内容，整条连接从此读乱）。
    """
    if len(buf) < 4:
        return None, buf
    try:
        n = struct.unpack(">I", buf[:4])[0]
    except Exception:
        raise PacketError("包头损坏")
    if n <= 0 or n > MAX_PACKET:
        raise PacketError("封包长度非法: %d" % n)
    if len(buf) < 4 + n:
        return None, buf
    try:
        obj = json.loads(buf[4:4 + n].decode("utf-8"))
        # JSON 对象 key 只能是字符串：pack 里 players 用 int(0/1) 做 key，
        # 往返后变 "0"/"1"，消费端按 int 取值直接 KeyError（联机必崩的根因）。
        # 在解码边界统一转回 int，单机路径不经过 JSON 不受影响。
        if isinstance(obj, dict) and isinstance(obj.get("players"), dict):
            obj["players"] = {int(k) if str(k).lstrip("-").isdigit() else k: v
                              for k, v in obj["players"].items()}
    except Exception as e:
        if not getattr(decode_pkt, "_warned", False):
            decode_pkt._warned = True
            print("[封包解码失败] %r" % (e,))
        write_log("解码包失败: %r" % e)
        obj = None
    return obj, buf[4 + n:]


INPUT_KEYS = ("left", "right", "up", "down", "dash", "shoot", "sword",
              "block", "interact", "mx", "my")


def sanitize_input(raw):
    """只接受已知按键字段与有限数值，丢弃其余内容（防注入/防越界）。"""
    out = {}
    if not isinstance(raw, dict):
        return out
    for k in INPUT_KEYS:
        if k not in raw:
            continue
        v = raw[k]
        if isinstance(v, bool):
            out[k] = v
        elif isinstance(v, (int, float)):
            out[k] = max(-1e6, min(1e6, float(v)))
    return out


# --------------------------------------------------------------------------
# 游戏引擎（服务器权威）
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# 静态地形（房主 / 客户端共用同一份，保证联机画面一致）
# --------------------------------------------------------------------------
def build_static_grid():
    W, H = MAP_W, MAP_H
    g = [[' ' for _ in range(W)] for _ in range(H)]

    def fill(x0, y0, x1, y1, c):
        for y in range(max(0, y0), min(H - 1, y1) + 1):
            for x in range(max(0, x0), min(W - 1, x1) + 1):
                g[y][x] = c

    # 主体地面（起点A区 / 中段B区 / 岩浆右侧区 / 走道+深坑右岸+终点区 / 熔炉长廊）
    fill(0, 19, 35, 21, 'G')
    fill(44, 19, 63, 21, 'G')
    fill(80, 19, 111, 21, 'G')
    fill(FORGE_LEFT, 19, FORGE_RIGHT, 21, 'G')
    # 地下整体地基（行22~27全实心）：坠入深坑者被坑壁牢牢困住，
    # 无法在世界底部左右横向移动（修复“掉坑后地底可自由移动”bug）
    fill(0, 22, FORGE_RIGHT, 27, 'G')
    # 深坑（列90~93，岩浆右岸走道之后，行19~26挖空；行27保留为坑底——
    # 掉入后被困坑底跳不出来，上方刀刺阶板可上下压到坑底扎死坠坑者，
    # 不会被“坠出世界”传送回起点）
    fill(90, 19, 93, 26, ' ')
    # 低洼岩浆坑（列64~79，行19~21挖空不放地面，玩家坠入岩浆持续扣血）
    #   -> 必须借助上方来回移动的阶板才能跨越
    # 终点高台（3格厚，顶部480px，传送门在高台中央）
    fill(96, 15, 104, 18, 'G')
    # ---- 熔炉长廊（第三幕）地形 ----
    # 中段台阶（需要跳跃/冲刺翻越，制造节奏变化）
    # 熔炉中段高台：只能到 117。原来铺到 119，把 col 118 的双人机关整个压在
    # 石头底下（机关在 row 19，上面 rows 17-18 是实心），玩家根本踩不上去，
    # 双人闸门永远打不开 -> 熔炉中段卡死。脱困逻辑修好后这个冲突才暴露出来。
    fill(116, 17, 117, 18, 'G')
    # 终点前的两级台阶，便于走上祭坛
    fill(136, 17, 138, 18, 'G')
    # 祭坛必须铺到地图最右一列（151）：原来只到 150，col 151 缺了 4 格高的台面，
    # Boss 冲锋把玩家推到最右侧时会从 480 直接掉到 608，4 格高爬不回来 -> 卡死
    fill(139, 15, FORGE_RIGHT, 18, 'G')
    # ---- 上层结构：森林断桥 + 岩浆上方捷径（配合藤蔓滑索形成多层路线）----
    for _x0, _x1 in ((10, 13), (17, 20), (24, 27), (31, 33)):
        fill(_x0, 13, _x1, 14, 'G')
    # ---- 熔炉瞭望塔：F1(480 既有高台) / F2(352) / F3(224) ----
    fill(97, 11, 103, 12, 'G')
    fill(99, 7, 101, 8, 'G')
    # 共鸣门：F2 通道右侧，门后隔间放补给与精英
    fill(104, 11, 105, 12, 'G')
    if 0 <= RUNE_GATE_COL < W:
        fill(RUNE_GATE_COL, RUNE_GATE_ROWS[0], RUNE_GATE_COL, RUNE_GATE_ROWS[1], 'H')
    if 0 <= RUNE_COL < W:
        g[11][RUNE_COL] = 'q'
    for _x0, _x1 in ((66, 69), (73, 76), (79, 81)):
        fill(_x0, 13, _x1, 14, 'G')
    # 双人闸门：熔炉中段，必须两块机关同时被踩住才升起
    if 0 <= DUO_GATE_COL < W:
        # 15-18 是门扇；11-14 是门楣。左侧 116-117 有 64px 台阶，
        # 二段跳能翻过 4 格门，实测 17 帧就越过去了 -> 必须封到跳不上去的高度
        fill(DUO_GATE_COL, 11, DUO_GATE_COL, 18, 'H')
    for c in DUO_PLATE_COLS:
        if 0 <= c < W:
            g[19][c] = 'q'
    # 岩石墙（弓箭手必须远程击碎，盾卫才能通行）
    fill(54, 16, 55, 19, 'R')
    # 压力机关（A断崖前）
    g[19][4] = 'Q'
    g[19][5] = 'Q'
    # 传送门视觉区(不可碰撞)
    for cx in range(142, 147):
        g[13][cx] = 'O'
        g[14][cx] = 'O'
    # 出生点标记(仅装饰)
    g[19][2] = 'S'
    g[19][10] = 's'
    return g


class Monster:
    __slots__ = ("mid", "kind", "x", "y", "vx", "vy", "hp", "maxhp",
                 "stun", "dir", "t", "last_hit", "on_ground", "hit_arrows",
                 "last_lava", "state", "state_t", "flash", "atk_cd",
                 "elite", "enraged", "cast_cd", "anchor_y", "stuck_t",
                 "phase", "slam_cd", "summoned", "guard_x", "tower")

    def __init__(self, mid, kind, x, y):
        self.mid = mid
        self.kind = kind              # 'fly' 高空飞行 / 'ground' 地面近战
        self.x = x                    # 中心x
        self.y = y                    # 底部y(ground) / 中心y(fly)
        self.vx = 0.0
        self.vy = 0.0
        self.hp = BOSS_HP if kind == "boss" else (
            FLY_MONSTER_HP if kind == "fly" else GROUND_MONSTER_HP)
        self.maxhp = self.hp
        self.stun = 0.0
        self.dir = random.choice([-1, 1])
        self.t = random.uniform(0, 10)
        self.last_hit = {0: 0.0, 1: 0.0}
        self.on_ground = False
        self.hit_arrows = set()       # 已命中该怪的箭id（防弓箭穿透）
        self.last_lava = 0.0          # 岩浆灼烧计时
        self.state = "walk"           # Boss 用：walk / tele / charge / recover
        self.state_t = 0.0
        self.flash = 0.0              # 攻击前摇高亮（渲染用）
        self.atk_cd = 2.2
        self.elite = False            # 精英变体（更大更硬）
        self.enraged = False          # Boss 半血狂暴
        self.cast_cd = random.uniform(0.6, 1.8)
        self.anchor_y = y
        self.stuck_t = 0.0
        self.phase = 1
        self.slam_cd = BOSS_SLAM_CD
        self.summoned = False
        self.guard_x = None        # 守护型：只在这个 x 附近 TOWER_GUARD_R 内活动
        self.tower = False         # 塔内怪物：不计入波次进度

    def rect(self):
        if self.kind == "fly":
            return (self.x - FLY_W / 2, self.y - FLY_H, FLY_W, FLY_H)
        if self.kind == "boss":
            return (self.x - BOSS_W / 2, self.y - BOSS_H, BOSS_W, BOSS_H)
        if self.kind == "caster":
            return (self.x - CW_HIT / 2, self.y - CH_HIT, CW_HIT, CH_HIT)
        return (self.x - MONSTER_W / 2, self.y - MONSTER_H, MONSTER_W, MONSTER_H)


class GameEngine:
    """服务器端世界：所有逻辑都在这里推进，客户端永不直接修改世界。"""

    def __init__(self):
        self.mid_counter = 0
        self.aid_counter = 0
        self.ai_pid = None          # 单人模式下由 AI 托管的角色（None 表示不启用归队）
        self._ai_stuck = 0.0
        self._ai_last_x = 0.0
        self.tick = 0
        self.deaths = 0
        self.kills = 0
        self.elapsed = 0.0
        self._night_next = 0.0
        self._night_announced = False
        self.beat_night = False
        self.build_map()
        self.reset()

    # ------------------------------------------------------------------
    # 地图
    # ------------------------------------------------------------------
    def build_map(self):
        self.grid = build_static_grid()
        # 岩石血量表
        self.rocks = {}
        for y in range(MAP_H):
            for x in range(MAP_W):
                if self.grid[y][x] == 'R':
                    self.rocks[(x, y)] = ROCK_HP

    def _solid_at(self, cx, cy):
        if cx < 0 or cx >= MAP_W:
            return True            # 地图左右封边
        if cy < 0:
            return False
        if cy >= MAP_H:
            return True            # 世界底部视为实体，防止无限下坠
        c = self.grid[cy][cx]
        return c in ('G', 'R', 'Q', 'S', 's', 'q', 'H')

    def is_solid_tile(self, cx, cy):
        return self._solid_at(cx, cy)

    def surface_y(self, x):
        """某 x 处的地表高度（最上层实体的顶面）；整列都是空则给世界底部。"""
        cx = int(x // TILE)
        if cx < 0 or cx >= MAP_W:
            return WORLD_H
        for cy in range(MAP_H):
            if self._solid_at(cx, cy):
                return cy * TILE
        return WORLD_H

    # ------------------------------------------------------------------
    # 复位
    # ------------------------------------------------------------------
    def _nav_graph(self):
        """导航图缓存。栅格只有闸门开关时会变，按门状态缓存即可。

        注意缓存属性不能叫 _nav_graph：那会和这个方法同名，
        第一次调用后实例属性把方法覆盖掉，第二次 `eng._nav_graph()`
        就变成"调用一个 NavGraph 对象" -> TypeError，
        而 _nav_follow 的 except 会把它吞成 False ——
        表现是"导航图只在第一帧生效，之后 AI 全部退回旧启发式"。
        """
        key = (self.duo_gate_open, self.rune_open)
        if getattr(self, "_nav_key", None) != key:
            self._nav_cache = ai_nav.build_nav(self.grid, VINES, set("GRQSsqH"))
            self._nav_key = key
        return self._nav_cache

    CHAT_KEEP = 20          # 内存里只保留最近若干条，状态包只发最后 8 条

    def push_chat(self, who, text):
        """联机聊天入队。

        之前三处调用都是直接 append 且从不裁剪：一局打得久、聊得多，
        engine.chat 会无限增长（虽然 pack() 只发最后 8 条，其余全留在内存里）。
        """
        try:
            self.chat.append((who, text))
            if len(self.chat) > self.CHAT_KEEP:
                del self.chat[:-self.CHAT_KEEP]
        except Exception:
            pass

    def reset(self, msg=""):
        self.tick = 0                     # 归零逻辑时钟，保证刀刺阶板/移动阶板起始相位确定
        self.build_map()
        self.players = {}
        for pid in (0, 1):
            sx, sy = PLAYER_START[pid]
            base = ROLES[pid]
            self.players[pid] = {
                "x": float(sx), "y": float(sy),
                "vx": 0.0, "vy": 0.0,
                "hp": float(base["maxhp"]), "maxhp": float(base["maxhp"]),
                "facing": 1, "moving": False, "blocking": False,
                "swing": 0.0, "shoot_cd": 0.0, "sword_cd": 0.0,
                "jump_cd": 0.0, "drop_t": 0.0,
                "on_ground": False, "coyote": 0.0, "jumps": 0, "role": pid,
                "dash_cd": 0.0, "dash_t": 0.0, "dash_dir": 1, "invuln": 0.0,
                "block_hold": 0.0, "land": 0.0, "last_hp": 80.0,
                "vine": -1, "vine_t": 0.0,
            }
        self.arrows = []
        self.monsters = []
        self.rifts = []           # 刷怪前兆：紫色裂隙，延时后怪物从中走出来
        self.pads = []            # [x, y, dur, max_dur, bounce, plate_id]
        self.plates = []
        for cfg in PLATE_CONFIGS:
            self.plates.append({"id": cfg["id"], "cx": cfg["cx"],
                                "active": False, "remaining": 0.0, "cooldown": 0.0})
        self.portal_active = False
        self.win = False
        self.win_t = 0.0
        self.wave = 1
        self.wave2_spawned = False
        self.wave2_cleared = False
        self.deaths = 0
        self.kills = 0
        self.elapsed = 0.0
        self._night_next = 0.0
        self._night_announced = False
        self.beat_night = False
        # 行程统计（结算页"行程回顾 / 搭档评语"用）
        self.stats = {"reversals": 0, "dmg": [0.0, 0.0, 0.0],
                      "max_region": 0, "blocks": 0}
        self._prog_max = 0.0
        self._rev_armed = False
        self.msg = msg or "先熟悉一下：WASD 移动 · 空格跳 · Shift 冲刺 · 左键射箭 · F 给同伴下令"
        self.events = []
        self.chat = []
        # ---- 熔炉长廊陷阱 / 检查点 / 补给箱 ----
        self._hammers = []
        for cfg in HAMMER_CFG:
            self._hammers.append({
                "id": cfg["id"], "px": cfg["cx"] * TILE, "py": cfg["cy"] * TILE,
                "len": cfg["len"], "r": cfg["r"], "spd": cfg["spd"],
                "phase": cfg["phase"], "ang": 0.0, "bx": 0.0, "by": 0.0,
            })
        self._fall_rocks = []
        for cfg in FALL_ROCK_CFG:
            self._fall_rocks.append({
                "id": cfg["id"], "x": cfg["cx"] * TILE + 16, "y": cfg["y0"],
                "y0": cfg["y0"], "vy": 0.0, "state": "idle", "cd": 0.0,
                "squash": 0.0, "open_t": 0.0,
                # 初始化就算好真实落点，别留一个 608 的假默认值
                "land_y": self._ground_below(cfg["cx"] * TILE + 16, cfg["y0"]),
            })
        self._checkpoints = []
        for c in CHECKPOINT_COLS:
            gy = 19 * TILE
            for yy in range(MAP_H):
                if self._solid_at(c, yy):
                    gy = yy * TILE
                    break
            self._checkpoints.append({"cx": c, "x": c * TILE + 16, "gy": gy,
                                      "active": False, "flash": 0.0})
        self._chests = [{"id": cfg["id"], "x": cfg["cx"] * TILE + 16,
                         "heal": cfg["heal"], "opened": False, "open_t": 0.0,
                         "gy": cfg.get("cy", 19) * TILE}
                        for cfg in CHEST_CFG]
        self._respawn_point = None
        self._trap_cd = {0: 0.0, 1: 0.0}
        self._hint = ""
        self._hint_t = 0.0
        self.boss_spawned = False
        self.corpses = []
        self.fireballs = []
        self.shockwaves = []
        self.mods = set()           # 挑战词条：glass / elite / nosupply
        self.difficulty = 1.0        # 难度倍率：0.7 / 1.0 / 1.4
        self.duo_gate_open = False
        self._duo_hold = 0.0
        self.vines = [list(v) for v in VINES]
        self.vents = [dict(v) for v in VENTS]
        self.weapon_taken = False
        self.rune_open = False
        self._rune_timer = 0.0
        # 岩浆坑上方的来回移动阶板（左右摆动，用于跨越低洼岩浆坑）
        self._m_plates = {}
        for cfg in M_PAD_CONFIGS:
            self._m_plates[cfg["id"]] = {
                "id": cfg["id"], "x": float(cfg["x0"] * TILE), "y": float(cfg["y"]),
                "dx": 0.0,
            }
        self._lava_last = {0: 0.0, 1: 0.0}
        # 深坑刀刺阶板（上下往复，顶部覆盖坑口可站立，底部刀刺扎入坑底）
        self._spike_platform = {
            "x": float(SPIKE_CFG["x0"] * TILE),
            "y": float(SPIKE_CFG["y_top"]),
            "dy": 0.0,
            "bloody": False,
            "prev_y": float(SPIKE_CFG["y_top"]),
        }
        self._spike_kill_msg = ""
        self._death_pending = 0.0          # 刀刺扎死后血迹展示延时(秒)
        self.wave1_spawned = False
        self._wave1_timer = 5.0
        self._spawn_tower()
        self.events.append(("reset", 0, 0))

    def _spawn_wave(self, w):
        if w == 1:
            spawns = [
                ("ground", 14 * TILE + 16, 19 * TILE - MONSTER_H),
                ("ground", 22 * TILE + 16, 19 * TILE - MONSTER_H),
                ("ground", 25 * TILE + 16, 19 * TILE - MONSTER_H),
                ("fly", 7 * TILE + 16, 9 * TILE),
                ("fly", 26 * TILE + 16, 11 * TILE),
            ]
        else:
            spawns = [
                ("ground", 46 * TILE + 16, 19 * TILE - MONSTER_H),
                ("ground", 50 * TILE + 16, 19 * TILE - MONSTER_H),
                ("ground", 57 * TILE + 16, 19 * TILE - MONSTER_H),
                ("fly", 54 * TILE + 16, 9 * TILE),
                ("fly", 62 * TILE + 16, 6 * TILE),
                ("caster", 52 * TILE + 16, 11 * TILE),
                ("caster", 66 * TILE + 16, 10 * TILE),
            ]
        # 不再直接生成怪物：先开紫色裂隙，给玩家 1.2s 反应时间，再从里面走出来
        for i, (kind, x, y) in enumerate(spawns):
            elite = (w == 2 and kind == "ground" and ("elite" in self.mods or i == 0))
            # 黑洞开在怪物出生点（地面怪贴地，飞怪在半空）
            ry = float(y)
            self.rifts.append({
                "x": float(x), "y": float(ry), "kind": kind,
                "elite": elite, "t": 0.0,
                "delay": 1.15 + i * 0.14,
                "size": 30.0 if kind == "ground" else 25.0,
                "tier": w,
            })
        self.msg = ("第一波怪物来袭！弓箭手射飞行怪，盾卫斩杀地面怪！" if w == 1
                    else "第二波怪物来袭！")

    # ------------------------------------------------------------------
    # 输入规格: {pid: {'up','down','left','right','shoot','sword','block',
    #                 'mx','my'}}
    # ------------------------------------------------------------------
    def step(self, inputs, dt):
        try:
            dt = max(0.001, min(dt, 0.05))
            self.tick += 1
            self.elapsed += dt
            self.events = []
            now = self.tick * dt

            # 暮色进程：夜幕后定期增援（完全入夜后可能一次两个）
            if not self.win and self.elapsed >= self.nightfall_at():
                if not self._night_announced:
                    self._night_announced = True
                    self.events.append(("nightfall", 0, 0))
                    self.msg = "夜幕降临……援军的裂隙正在开启！"
                if self._night_next <= 0.0:
                    self._night_next = self.elapsed + NIGHT_SPAWN_INTERVAL
                elif self.elapsed >= self._night_next:
                    self._night_next = self.elapsed + NIGHT_SPAWN_INTERVAL
                    self._night_reinforce()

            # 行程统计：队伍最前沿的推进 / 折返（回落超过 4 格算一次折返）
            _cur = max(p["x"] for p in self.players.values())
            if _cur > self._prog_max:
                self._prog_max = _cur
                self._rev_armed = True
            elif self._rev_armed and self._prog_max - _cur > 4 * TILE:
                self.stats["reversals"] += 1
                self._rev_armed = False
            _rg = region_of_x(_cur)
            if _rg > self.stats["max_region"]:
                self.stats["max_region"] = _rg

            # 0) 更新岩浆坑上方的来回移动阶板位置（左右摆动，玩家可跳上搭乘过坑）
            for plate in self._m_plates.values():
                try:
                    cfg = M_PAD_CONFIGS[[pc["id"] for pc in M_PAD_CONFIGS].index(plate["id"])]
                    mid = (cfg["x0"] + cfg["x1"]) / 2.0 * TILE
                    amp = (cfg["x1"] - cfg["x0"]) / 2.0 * TILE
                    old_x = plate["x"]
                    plate["x"] = mid + amp * math.sin(cfg["spd"] * now + cfg["phase"])
                    plate["x"] = max(cfg["x0"] * TILE, min(cfg["x1"] * TILE, plate["x"]))
                    plate["dx"] = (plate["x"] - old_x) / dt if dt > 0 else 0.0
                except Exception as e:
                    write_log("移动阶板更新异常: %r" % (e,))

            # 0.4) 更新深坑刀刺阶板（上下往复移动，顶面覆盖坑口/底面刀刺扎入坑底）
            sp = self._spike_platform
            try:
                mid = (SPIKE_CFG["y_top"] + SPIKE_CFG["y_bot"]) / 2.0
                amp = (SPIKE_CFG["y_top"] - SPIKE_CFG["y_bot"]) / 2.0
                old_y = sp["y"]
                sp["prev_y"] = old_y
                sp["y"] = mid + amp * math.sin(SPIKE_CFG["spd"] * now + SPIKE_CFG["phase"])
                sp["y"] = min(SPIKE_CFG["y_bot"], max(SPIKE_CFG["y_top"], sp["y"]))
                sp["dy"] = (sp["y"] - old_y) / dt if dt > 0 else 0.0
            except Exception as e:
                write_log("刀刺阶板更新异常: %r" % (e,))

            # 0.5) 熔炉长廊：摆锤摆动 + 落石下落
            self._update_hammers(now, dt)
            self._update_fall_rocks(dt)

            # 1) 玩家移动 / 技能
            for pid in (0, 1):
                inp = inputs.get(pid) or {}
                self._step_player(pid, inp, dt, now)

            # 1.5) 熔炉长廊陷阱伤害 + 检查点 + 补给箱
            self._update_traps(dt, now)
            self._update_interactables(dt, inputs)

            # 1.6) AI 同伴归队兜底（避免策略 AI 在复杂地形里被永久卡死）
            self._update_ai_rescue(dt)

            # 2) 机关检测（仅盾卫踩踏 -> 生成跳板）
            self._update_plates(dt, now)

            # 2.5) 双人机关：两块必须同时有人
            self._update_duo(dt)

            # 3) 跳板生命周期
            self._update_pads(dt)

            # 3.5) 裂隙到期 -> 放怪
            self._update_rifts(dt)
            # 4) 怪物 AI + 伤害
            self._update_monsters(dt, now)

            # 5) 弓箭飞行与碰撞 + 敌方火球
            self._update_arrows(dt)
            self._update_fireballs(dt)
            self._update_shockwaves(dt)
            self._update_vents(dt)
            self._update_rune_gate(dt)
            self._try_take_weapon()

            # 6) 死亡判定与传送门
            if not self.win:
                self._check_portal(dt)

            # 7) 开局安全窗口：先给 5 秒 / 或玩家主动前进后再放第一波
            if not self.wave1_spawned:
                self._wave1_timer -= dt
                if self._wave1_timer <= 0 or any(p["x"] > 12 * TILE for p in self.players.values()):
                    self.wave1_spawned = True
                    self._spawn_wave(1)
                    self.msg = "第一波怪物来袭！弓箭手射飞行怪，盾卫斩杀地面怪！"
                    self.events.append(("wave_start", int(PLAYER_START[0][0]), 19 * TILE - 60))

            # 8) 波次推进：藤壶小路 -> 岩壁区 -> 熔炉守卫 -> 传送门
            #    注意：裂隙里还没出来的怪也算"没清完"，否则 Boss 刚开黑洞
            #    _alive 还是空 -> wave 走到 3 的 else 分支 -> 传送门提前开启，
            #    玩家可以直接绕过 Boss 通关。
            _alive = [m for m in self.monsters if not m.tower]
            if (not self.portal_active and len(_alive) == 0 and not self.rifts
                    and (self.wave1_spawned or self.wave > 1)):
                if self.wave == 1:
                    if not self.wave2_spawned:
                        # 等玩家突破岩石墙之后刷新第二波
                        if any(p["x"] > WAVE2_TRIGGER_X for p in self.players.values()):
                            self.wave2_spawned = True
                            self.wave = 2
                            self._spawn_wave(2)
                elif self.wave == 2:
                    self.wave2_cleared = True
                    # 第二波清完不直接开门：玩家踏入熔炉祭坛才唤醒守卫
                    if any(p["x"] > BOSS_TRIGGER_X for p in self.players.values()):
                        self._spawn_boss()
                        self.wave = 3
                else:
                    self.portal_active = True
                    self.msg = "守卫倒下了！传送门激活，两人同时走入即可通关！"
                    self.events.append(("portal", PORTAL_RECT[0] + 80, PORTAL_RECT[1] + 40))

            # 8) 任意玩家血量归零 -> 检查点复活（刀刺扎死：先展示血迹与尸体再复活）
            any_dead = any(p["hp"] <= 0 for p in self.players.values())
            if any_dead and not self.win:
                if self._spike_kill_msg and self._death_pending > 0:
                    self._death_pending -= dt
                    # 尸体钉在刀刺阶板上随板沉浮，血迹保持可见
                    for pid in (0, 1):
                        if self.players[pid]["hp"] <= 0:
                            self.players[pid]["x"] = sp["x"] + SPIKE_PAD_W / 2
                            self.players[pid]["y"] = sp["y"]
                else:
                    self._respawn_all(self._spike_kill_msg)
        except Exception as e:
            write_log("引擎step异常: %r" % (e,))
        # 行程统计：本帧成功格挡的次数（含弹反/挡火球/挡冲锋）
        try:
            self.stats["blocks"] += sum(1 for ev in self.events if ev[0] == "block")
        except Exception:
            pass

    def _update_ai_rescue(self, dt):
        """AI 托管角色若长时间滞留在深坑/岩浆或原地不动，就传送到人类角色身边。

        纯策略 AI 无法覆盖所有地形组合；"归队"是合作游戏常用的兜底，
        既避免 AI 反复送死，也不会让玩家被卡在半张图外。
        """
        try:
            ai = self.ai_pid
            if ai is None:
                return
            a = self.players[ai]
            human = self.players[1 - ai]
            if a["hp"] <= 0 or not human:
                return
            in_pit = (PIT_COLS[0] * TILE <= a["x"] <= (PIT_COLS[1] + 1) * TILE
                      and a["y"] > PIT_TOP_Y + 16)
            in_lava = (LAVA_LEFT_PX <= a["x"] <= LAVA_RIGHT_PX
                       and a["y"] >= LAVA_SURFACE_Y - 3)
            far = abs(a["x"] - human["x"]) > 700
            idle = abs(a["x"] - self._ai_last_x) < 2.0
            self._ai_last_x = a["x"]
            # 瞭望塔是垂直结构（塔基 96~104 列是一整块实心，只能靠藤蔓/连跳翻越），
            # 纯策略 AI 爬不上去：会在井道里上下弹跳、被喷火机关烧死，而人类一旦
            # 过了塔，两者距离又不到 700px，原来的 far 判定永远不触发。
            # 这里单独判一次"人和 AI 分处塔内外"，尽快把人带过去。
            # 内缩到塔内、且两人确实分开了才算（否则 AI 跟在塔口站着也会被误判）
            _tl, _tr = 96 * TILE + 48, 105 * TILE - 48
            split_tower = (((_tl <= a["x"] <= _tr) != (_tl <= human["x"] <= _tr))
                           and abs(a["x"] - human["x"]) > 80)
            if in_pit or in_lava:
                self._ai_stuck += dt
            elif split_tower and idle:
                self._ai_stuck += dt * 1.6
            elif far and idle:
                # 守点指令下，AI 停在守点附近是职责不是卡死，不触发归队传送
                gp = getattr(self, "ai_guard_pos", None)
                on_guard = (gp is not None
                            and abs(a["x"] - gp[0]) < 90 and abs(a["y"] - gp[1]) < 120)
                if on_guard:
                    self._ai_stuck = max(0.0, self._ai_stuck - dt * 2.0)
                else:
                    self._ai_stuck += dt
            else:
                self._ai_stuck = max(0.0, self._ai_stuck - dt * 2.0)
            if self._ai_stuck > 1.0:
                self._ai_stuck = 0.0
                a["x"] = human["x"] - 70 * (1 if human["facing"] > 0 else -1)
                a["y"] = human["y"] - 6
                a["vx"] = a["vy"] = 0.0
                a["invuln"] = 1.2
                a["dash_t"] = 0.0
                self.events.append(("ally_warp", int(a["x"]), int(a["y"])))
        except Exception as e:
            write_log("同伴归队异常: %r" % (e,))

    def _respawn_all(self, reason=""):
        """全队阵亡 -> 在最近激活的检查点复活（不再整关重置）。"""
        try:
            self.deaths += 1
            self._death_pending = 0.0
            self._spike_kill_msg = ""
            if self._respawn_point:
                rx, ry = self._respawn_point
            else:
                rx, ry = PLAYER_START[0][0], 19 * TILE
            for pid in (0, 1):
                p = self.players[pid]
                # 修复"送死回血"：复活血量不超过死前血量，且不超过 60%
                cap = float(p["maxhp"]) * RESPAWN_HP_RATIO
                last = float(p.get("last_hp", cap))
                p["hp"] = max(1.0, min(cap, last))
                p["vine"] = -1      # 不清会在下一帧被 _update_vine 拽回绳上（死循环回危险区）
                p["x"] = float(rx + (0 if pid == 0 else 46))
                p["y"] = float(ry)
                p["vx"] = p["vy"] = 0.0
                p["dash_t"] = 0.0
                p["dash_cd"] = 0.0
                p["invuln"] = RESPAWN_IFRAME
                p["on_ground"] = False
            self.arrows = []
            # 阵亡传送回检查点不算"折返"：不清掉推进基准的话，
            # 结算页会把每次死亡都记成一次主动回头（实测 120 -> 108 记 1 次）。
            self._prog_max = max(p["x"] for p in self.players.values())
            self._rev_armed = True
            self.msg = reason or "队伍阵亡！已在检查点复活"
            self.events.append(("respawn", int(rx), int(ry)))
        except Exception as e:
            write_log("复活处理异常: %r" % (e,))

    # ------------------------------------------------------------------
    # 玩家
    # ------------------------------------------------------------------
    def _step_player(self, pid, inp, dt, now):
        try:
            p = self.players[pid]
            if p["hp"] <= 0:
                return
            p["last_hp"] = p["hp"]      # 死前血量：复活时不允许超过它（禁止送死回血）
            role = ROLES[pid]

            # ---- 藤蔓滑索 ----
            if p["vine"] < 0 and not inp.get("up"):
                p["_vine_up_latch"] = False   # 松开跳跃键才允许再次抓取
            if self._update_vine(pid, inp, dt):
                return
            if (p["vine"] < 0 and not p.get("_vine_up_latch", False)
                    and (inp.get("up") or inp.get("interact"))):
                self._try_grab_vine(pid)
                if p["vine"] >= 0:
                    # 记住抓取这一帧跳键是否按着：按住不放不会被当成"再按一次"
                    p["_vine_up_latch"] = bool(inp.get("up"))
                    return        # 抓到就别在本帧继续走普通移动/起跳
            spd = role["spd"]

            # 计时器
            p["invuln"] = max(0.0, p["invuln"] - dt)
            p["dash_cd"] = max(0.0, p["dash_cd"] - dt)
            if p["dash_t"] > 0:
                p["dash_t"] = max(0.0, p["dash_t"] - dt)

            dx = 0
            if inp.get("left"):
                dx -= 1
            if inp.get("right"):
                dx += 1
            if dx != 0:
                p["vx"] = dx * spd
                p["facing"] = 1 if dx > 0 else -1
                p["moving"] = True
            else:
                p["vx"] *= 0.6
                p["moving"] = False

            # 冲刺（短促突进 + 起手无敌帧，用于躲摆锤/落石/穿身位）
            if inp.get("dash") and p["dash_cd"] <= 0 and p["dash_t"] <= 0:
                p["dash_dir"] = dx if dx != 0 else p["facing"]
                p["dash_t"] = DASH_TIME
                p["dash_cd"] = DASH_CD
                p["invuln"] = max(p["invuln"], DASH_IFRAME)
                p["facing"] = p["dash_dir"]
                self.events.append(("dash", int(p["x"]), int(p["y"] - 24)))
            if p["dash_t"] > 0:
                p["vx"] = p["dash_dir"] * DASH_SPEED
                p["moving"] = True

            # 盾卫举盾
            if pid == 1:
                p["blocking"] = bool(inp.get("block"))
                p["block_hold"] = (p["block_hold"] + dt) if p["blocking"] else 0.0

            # 跳跃（土狼时间 + 二段跳：落地后第一跳，空中再按/按住触发二段跳，跳得更高）
            p["coyote"] = 0.12 if p["on_ground"] else max(0.0, p["coyote"] - dt)
            p["jump_cd"] = max(0.0, p["jump_cd"] - dt)
            if p["on_ground"]:
                p["jumps"] = 0
            if inp.get("up") and p["jump_cd"] <= 0:
                if p["coyote"] > 0:
                    # 第一跳：地面 / 土狼时间
                    p["vy"] = -role["jump"]
                    p["jumps"] = 1
                    p["on_ground"] = False
                    p["coyote"] = 0.0
                    p["jump_cd"] = 0.14
                    self.events.append(("jump", int(p["x"]), int(p["y"] - 20)))
                elif p["jumps"] == 1:
                    # 二段跳：已离地，再跳一次，跳得更高
                    p["vy"] = -role["jump"] * 0.95
                    p["jumps"] = 2
                    p["jump_cd"] = 0.14
                    self.events.append(("jump", int(p["x"]), int(p["y"] - 20)))

            # 下跳穿透单边平台（跳板）
            if inp.get("down") and p["on_ground"]:
                p["drop_t"] = 0.2
                p["on_ground"] = False
            p["drop_t"] = max(0.0, p["drop_t"] - dt)

            # 物理移动 + 碰撞
            prev_bottom = p["y"]
            was_ground = p["on_ground"]
            vy_before = p["vy"]
            p["vy"] += GRAVITY * dt
            p["vy"] = min(p["vy"], 1600)
            grounded = self._move_entity(p, PLAYER_W, PLAYER_H, dt, prev_bottom,
                                         collide_pads=True, drop=p["drop_t"] > 0)
            p["on_ground"] = grounded
            # 落地：给渲染层一个 squash 信号
            if grounded and not was_ground and vy_before > 260:
                p["land"] = 1.0
                self.events.append(("land", int(p["x"]), int(p["y"])))
            else:
                p["land"] = max(0.0, p["land"] - dt * 5.5)

            # 1.5) 岩浆灼烧 + 移动阶板携带（站在板上被板带着水平移动）
            if p["hp"] > 0:
                try:
                    for plate in self._m_plates.values():
                        px0, py0 = plate["x"], plate["y"]
                        if (px0 - 2 < p["x"] - PLAYER_W / 2 and
                                p["x"] + PLAYER_W / 2 < px0 + M_PAD_W + 2 and
                                abs(p["y"] - py0) < 12):
                            p["x"] += plate["dx"] * dt
                            p["x"] = max(PLAYER_W / 2, min(WORLD_W - PLAYER_W / 2, p["x"]))
                            p["y"] = py0
                            p["on_ground"] = True
                            break
                    # 掉入低洼岩浆坑：被岩浆表面浮托，持续灼烧扣血
                    if (LAVA_LEFT_PX <= p["x"] <= LAVA_RIGHT_PX and
                            abs(p["y"] - LAVA_SURFACE_Y) <= 4):
                        if now - self._lava_last[pid] >= LAVA_TICK:
                            self._lava_last[pid] = now
                            p["hp"] = max(0, p["hp"] - LAVA_DMG)
                            self.events.append(("lava", int(p["x"]), int(LAVA_SURFACE_Y - 8)))
                except Exception as e:
                    write_log("岩浆/阶板携带异常: %r" % (e,))

            # 1.6) 深坑刀刺阶板：站在板顶被携带上下；掉入坑内被下压刀刺直接扎死
            try:
                sp = self._spike_platform
                if (sp["x"] - 2 < p["x"] - PLAYER_W / 2 and
                        p["x"] + PLAYER_W / 2 < sp["x"] + SPIKE_PAD_W + 2 and
                        abs(p["y"] - sp["y"]) < 12):
                    p["y"] = sp["y"]
                    p["x"] = max(PLAYER_W / 2, min(WORLD_W - PLAYER_W / 2, p["x"]))
                    p["on_ground"] = True
                elif p["y"] > PIT_TOP_Y + 8 and p["x"] > sp["x"] - 4 and p["x"] < sp["x"] + SPIKE_PAD_W + 4:
                    spike_rect = (sp["x"], sp["y"] + SPIKE_PAD_H, SPIKE_PAD_W, SPIKE_H)
                    pr = (p["x"] - PLAYER_W / 2, p["y"] - PLAYER_H, PLAYER_W, PLAYER_H)
                    if rect_overlap(spike_rect, pr):
                        p["hp"] = 0
                        sp["bloody"] = True
                        self._spike_kill_msg = "%s坠入深坑被刀刺扎死！" % ROLES[pid]["name"]
                        self.msg = self._spike_kill_msg
                        self._death_pending = 1.8     # 血迹展示窗口
                        self.events.append(("impale", int(sp["x"] + SPIKE_PAD_W / 2),
                                            int(sp["y"] + SPIKE_PAD_H + SPIKE_H - 4)))
            except Exception as e:
                write_log("刀刺阶板携带/扎死异常: %r" % (e,))

            # 跳板弹跳
            for pad in self.pads:
                px, py, pw = pad[0], pad[1], TILE
                if (p["x"] + PLAYER_W / 2 > px and p["x"] - PLAYER_W / 2 < px + pw and
                        abs(p["y"] - py) < 8 and p["vy"] >= 0):
                    p["vy"] = PAD_BOUNCE
                    p["on_ground"] = False
                    self.events.append(("pad", int(px + 16), int(py)))
                    break

            # 世界边界
            if p["x"] < PLAYER_W / 2:
                p["x"] = PLAYER_W / 2
            if p["x"] > WORLD_W - PLAYER_W / 2:
                p["x"] = WORLD_W - PLAYER_W / 2

            # 坠落（掉出世界）。注意别给 90~93 那个深坑加"救援"：
            # 那是设计好的死亡陷阱 —— 掉进去被困坑底，等刀刺阶板压下来扎死，
            # 有血迹和提示语（test_pit T3/T4 就是钉这个的）。
            if p["y"] > WORLD_H + 40:
                p["hp"] = max(0, p["hp"] - 20)
                p["x"], p["y"] = PLAYER_START[pid]
                p["vx"] = p["vy"] = 0.0
                # 被送回起点不算"主动折返"
                self._prog_max = max(q["x"] for q in self.players.values())
                self._rev_armed = True
                self.events.append(("fall", int(p["x"]), int(p["y"])))
                self.msg = "坠落深谷受伤！已回到起点"

            # 弓箭手射箭
            if pid == 0:
                p["shoot_cd"] = max(0.0, p["shoot_cd"] - dt)
                if inp.get("shoot") and p["shoot_cd"] <= 0:
                    p["shoot_cd"] = 0.35
                    bx = p["x"] + p["facing"] * 22
                    by = p["y"] - 26
                    tx = inp.get("mx", bx + p["facing"] * 100)
                    ty = inp.get("my", by)
                    ddx, ddy = tx - bx, ty - by
                    lg = math.hypot(ddx, ddy) or 1.0
                    ang = math.atan2(ddy, ddx)
                    _pw = float(p.get("power", 1.0))
                    a = Arrow(self.aid_counter, bx, by, ddx / lg, ddy / lg, ang,
                              ARROW_DMG * _pw)
                    self.aid_counter += 1
                    self.arrows.append(a)
                    self.events.append(("shoot", int(bx), int(by)))

            # 盾卫挥剑
            if pid == 1:
                p["sword_cd"] = max(0.0, p["sword_cd"] - dt)
                p["swing"] = max(0.0, p["swing"] - dt * 3.2)
                if inp.get("sword") and p["sword_cd"] <= 0:
                    p["sword_cd"] = 0.5
                    p["swing"] = 1.0
                    fx = p["x"] + p["facing"] * (PLAYER_W / 2 - 2)
                    fy = p["y"] - 6
                    if p["facing"] > 0:
                        rng = (fx, fy - SWORD_RANGE, SWORD_RANGE, SWORD_RANGE)
                    else:
                        rng = (fx - SWORD_RANGE, fy - SWORD_RANGE, SWORD_RANGE, SWORD_RANGE)
                    self.events.append(("swing", int(fx), int(fy - 10)))
                    # 剑也能砸碎岩石：清路不该只有弓手能办
                    try:
                        _c0 = max(0, int(rng[0] // TILE))
                        _c1 = min(MAP_W - 1, int((rng[0] + rng[2]) // TILE))
                        _r0 = max(0, int(rng[1] // TILE))
                        _r1 = min(MAP_H - 1, int((rng[1] + rng[3]) // TILE))
                        for _cy in range(_r0, _r1 + 1):
                            for _cx in range(_c0, _c1 + 1):
                                if self.grid[_cy][_cx] == 'R':
                                    if self._damage_rock(_cx, _cy, 2):
                                        self.events.append(("break", _cx * TILE + 16, _cy * TILE + 16))
                    except Exception:
                        pass
                    for m in list(self.monsters):
                        if m.kind not in ("ground", "boss"):
                            continue
                        if rect_overlap(rng, m.rect()):
                            boss = (m.kind == "boss")
                            _pw = float(p.get("power", 1.0))
                            m.hp -= SWORD_DMG * (0.6 if boss else 1.0) * _pw
                            m.stun = 0.12 if boss else 0.5
                            m.vx = p["facing"] * (60 if boss else 260)
                            self.events.append(("hit", int(m.x), int(m.y - 14)))
                            if m.hp <= 0:
                                self._kill_monster(m)
        except Exception as e:
            write_log("玩家%d step异常: %r" % (pid, e))

    # ------------------------------------------------------------------
    # 熔炉长廊：摆锤 / 落石 / 地刺 / 检查点 / 补给箱
    # ------------------------------------------------------------------
    def _update_hammers(self, now, dt):
        for h in self._hammers:
            try:
                ang = math.pi * 0.5 * math.sin(h["spd"] * now + h["phase"])
                h["ang"] = ang
                h["bx"] = h["px"] + math.sin(ang) * h["len"]
                h["by"] = h["py"] + math.cos(ang) * h["len"]
            except Exception:
                pass

    def _ground_below(self, x, y_from):
        """从 y_from 往下找第一个实体格的顶面 y（落石落地用）。

        不能再用固定的 19*TILE：F1 在高台上、F3 在祭坛上，硬编码会让石头
        穿过台面一直掉进砖里（"落石掉到地底"）。
        """
        try:
            cx = int(x // TILE)
            if cx < 0 or cx >= MAP_W:
                return float(MAP_H * TILE)
            for ry in range(max(0, int(y_from // TILE)), MAP_H):
                if self._solid_at(cx, ry):
                    return float(ry * TILE)
        except Exception:
            pass
        return float(MAP_H * TILE)

    def _update_fall_rocks(self, dt):
        gy = 19 * TILE
        for r in self._fall_rocks:
            try:
                if r["state"] == "idle":
                    r["cd"] = max(0.0, r["cd"] - dt)
                    if r["cd"] > 0:
                        continue
                    for p in self.players.values():
                        if p["hp"] > 0 and abs(p["x"] - r["x"]) < FALL_ROCK_TRIGGER and p["y"] < gy + 10:
                            # 先裂开天空，0.55 秒后才掉石头：给玩家"抬头看"的反应时间
                            r["state"] = "open"
                            r["open_t"] = 0.55
                            r["vy"] = 0.0
                            r["land_y"] = self._ground_below(r["x"], r["y"] + 6)
                            self.events.append(("rock_crack", int(r["x"]), int(r["y0"])))
                            break
                elif r["state"] == "open":
                    r["open_t"] -= dt
                    if r["open_t"] <= 0.0:
                        r["state"] = "fall"
                        r["vy"] = 40.0
                        self.events.append(("rock_warn", int(r["x"]), int(r["y0"])))
                elif r["state"] == "fall":
                    r["vy"] += GRAVITY * 0.8 * dt
                    r["y"] += r["vy"] * dt
                    rr = (r["x"] - 15, r["y"] - 15, 30, 30)
                    for pid, p in self.players.items():
                        if p["hp"] <= 0 or p["invuln"] > 0:
                            continue
                        pr = (p["x"] - PLAYER_W / 2, p["y"] - PLAYER_H, PLAYER_W, PLAYER_H)
                        if rect_overlap(rr, pr):
                            self._damage_player(pid, FALL_ROCK_DMG, "rock")
                            p["vy"] = -180.0
                            self.events.append(("rock_hit", int(r["x"]), int(r["y"])))
                    if r["y"] >= r["land_y"] - 14:
                        r["y"] = float(r["land_y"] - 14)
                        r["state"] = "rest"
                        r["vy"] = 0.0
                        r["squash"] = 0.0
                        r["cd"] = 4.5
                        self.events.append(("rock_land", int(r["x"]), int(r["land_y"])))
                elif r["state"] == "rest":
                    r["squash"] += dt
                    if r["squash"] > 2.0:
                        r["state"] = "idle"
                        r["y"] = float(r["y0"])
                        r["vy"] = 0.0
                        r["cd"] = 2.5
            except Exception as e:
                write_log("落石更新异常: %r" % (e,))

    def _damage_player(self, pid, amount, source="", knock_x=0.0, knock_y=0.0):
        """统一的玩家受伤入口：无敌帧 / 盾牌减伤 / 事件广播。"""
        try:
            p = self.players[pid]
            if p["hp"] <= 0 or p["invuln"] > 0:
                return False
            dmg = float(amount)
            if "glass" in self.mods:
                dmg *= 1.5
            dmg *= self.difficulty
            if pid == 1 and p["blocking"] and source in ("spike", "hammer", "rock"):
                dmg *= 0.35
                self.events.append(("block", int(p["x"]), int(p["y"] - 20)))
            self._track_dmg(pid, dmg)
            p["hp"] = max(0.0, p["hp"] - dmg)
            p["invuln"] = 0.42 if source else 0.6
            if knock_x:
                p["vx"] = knock_x
            if knock_y:
                p["vy"] = knock_y
                p["on_ground"] = False
            self.events.append(("hurt", int(p["x"]), int(p["y"] - 30)))
            self.events.append(("dmg", int(p["x"]), int(p["y"] - 46), int(dmg)))
            return True
        except Exception:
            return False

    def _update_traps(self, dt, now):
        try:
            for pid in (0, 1):
                self._trap_cd[pid] = max(0.0, self._trap_cd[pid] - dt)
                p = self.players[pid]
                if p["hp"] <= 0:
                    continue
                pr = (p["x"] - PLAYER_W / 2, p["y"] - PLAYER_H, PLAYER_W, PLAYER_H)
                # 地刺带（不致死：保底 1 HP，只作消耗）
                if p["y"] >= 19 * TILE - 6 and self._trap_cd[pid] <= 0:
                    for si, (c0, c1) in enumerate(SPIKE_STRIPS):
                        sr = (c0 * TILE, 19 * TILE - SPIKE_STRIP_H,
                              (c1 - c0 + 1) * TILE, SPIKE_STRIP_H)
                        center = (c0 + c1 + 1) * TILE * 0.5
                        kdir = -1.0 if p["x"] < center else 1.0
                        # 红黑荆棘（条 1/2）是"活物"：路过就伸手抓，判定圈比刺带
                        # 宽（左右各 22px），贴边路过也会被缠住；不弹开，往条心拽
                        if si in BRAMBLE_IDX:
                            grab = (sr[0] - 22, sr[1] - 26, sr[2] + 44, sr[3] + 26)
                            if not rect_overlap(pr, grab):
                                continue
                            if p["hp"] > 1.0:
                                self._damage_player(pid, SPIKE_STRIP_DMG, "spike")
                                p["hp"] = max(1.0, p["hp"])   # 不致死
                                self.events.append(("spike_hit", int(p["x"]), int(p["y"])))
                            nx = p["x"] - kdir * 12          # 往条心拽 = 被缠住
                            if not self._rect_solid(nx, p["y"], PLAYER_W, PLAYER_H):
                                p["x"] = nx
                            self._trap_cd[pid] = 0.9
                            break
                        if not rect_overlap(pr, sr):
                            continue
                        # 金属刺：踩上去弹开。弹开方向按"远离刺带中心"算，不能按朝向：
                        # 按朝向时，玩家面朝左就会被弹回刺上，然后反复弹飞
                        # （实测能从刺带一路弹到地图最左端，位移 3400px）
                        if p["hp"] > 1.0:
                            self._damage_player(pid, SPIKE_STRIP_DMG, "spike")
                            p["hp"] = max(1.0, p["hp"])   # 不致死
                            # 直接位移脱离刺带：只设 vx 会被下一帧的输入覆盖，
                            # 结果就是原地跳一下又落回刺上，被反复扎
                            nx = p["x"] + kdir * 58
                            nx = max(PLAYER_W, min(WORLD_W - PLAYER_W, nx))
                            if not self._rect_solid(nx, p["y"], PLAYER_W, PLAYER_H):
                                p["x"] = nx
                            p["vy"] = -320.0
                            p["on_ground"] = False
                            self.events.append(("spike_hit", int(p["x"]), int(p["y"])))
                        self._trap_cd[pid] = 0.95
                        break
                # 摆锤
                if self._trap_cd[pid] <= 0:
                    for h in self._hammers:
                        # 圆-矩形最近距离：锤头扫过身体任何部分都算命中。
                        # 旧写法只比"身体中心点"的 y 差，锤头悬在头顶上方约 90px，
                        # 地面玩家永远差 2~90px 打不中，跳跃的反而被打。
                        _nr_y = min(max(h["by"], p["y"] - PLAYER_H), p["y"])
                        _ndx = h["bx"] - p["x"]
                        _ndy = h["by"] - _nr_y
                        if _ndx * _ndx + _ndy * _ndy < (h["r"] + 9) ** 2:
                            self._damage_player(pid, HAMMER_DMG, "hammer",
                                                knock_x=520 if p["x"] < h["bx"] else -520,
                                                knock_y=-420)
                            self._trap_cd[pid] = 0.9
                            self.events.append(("hammer", int(h["bx"]), int(h["by"])))
                            break
        except Exception as e:
            write_log("陷阱伤害异常: %r" % (e,))

    def _update_interactables(self, dt, inputs):
        try:
            for cp in self._checkpoints:
                cp["flash"] = max(0.0, cp["flash"] - dt)
                if cp["active"]:
                    continue
                for p in self.players.values():
                    if (p["hp"] > 0 and abs(p["x"] - cp["x"]) < 42 and
                            abs(p["y"] - cp.get("gy", 19 * TILE)) < 110):
                        cp["active"] = True
                        cp["flash"] = 1.2
                        self._respawn_point = (float(cp["x"]), float(cp.get("gy", 19 * TILE)))
                        self.events.append(("checkpoint", int(cp["x"]), int(19 * TILE - 60)))
                        self.msg = "检查点已激活 · 阵亡后在此复活"
                        break
            for ch in self._chests:
                ch["open_t"] = max(0.0, ch["open_t"] - dt)
                if ch["opened"] or "nosupply" in self.mods:
                    continue
                for pid, p in self.players.items():
                    if p["hp"] <= 0:
                        continue
                    if (abs(p["x"] - ch["x"]) < CHEST_RANGE and
                            abs(p["y"] - ch.get("gy", 19 * TILE)) < 90):
                        want = bool((inputs.get(pid) or {}).get("interact"))
                        if want:
                            ch["opened"] = True
                            ch["open_t"] = 1.0
                            healed = min(p["maxhp"] - p["hp"], float(ch["heal"]))
                            p["hp"] += healed
                            self.events.append(("chest", int(ch["x"]),
                                                int(ch.get("gy", 19 * TILE) - 30), int(healed)))
                            self.msg = "开启补给箱：恢复 %d 点生命" % int(healed)
                            break
        except Exception as e:
            write_log("交互物更新异常: %r" % (e,))

    # ------------------------------------------------------------------
    # 物理移动
    # ------------------------------------------------------------------
    def _collide_x(self, old_x, nx, y, w, h, vx):
        try:
            left = nx - w / 2
            right = nx + w / 2
            top = y - h
            r0 = int(top // TILE)
            r1 = int((y - 0.001) // TILE)
            if vx > 0:
                cx = int(right // TILE)
                for ry in range(r0, r1 + 1):
                    if self._solid_at(cx, ry):
                        return cx * TILE - w / 2 - 0.01
            elif vx < 0:
                cx = int((left - 0.001) // TILE)
                for ry in range(r0, r1 + 1):
                    if self._solid_at(cx, ry):
                        return cx * TILE + TILE + w / 2 + 0.01
            return nx
        except Exception as e:
            write_log("x碰撞异常: %r" % (e,))
            return nx

    def _collide_y(self, x, old_y, ny, w, h, vy, prev_bottom, collide_pads, drop):
        try:
            left = x - w / 2
            right = x + w / 2
            rx0 = int(left // TILE)
            rx1 = int((right - 0.001) // TILE)
            if vy >= 0:  # 下落
                bottom = ny
                # ---- 深坑刀刺阶板：骑乘者优先于硬地面/坑底判定 ----
                # 骑板者被阶板顶面携带、全程悬浮在坑内，重力永远不会把他拉进
                # 坑底实体区（修复“骑到坑底自动穿墙左右乱走/被误扎死”bug）。
                # 仅当上一帧玩家脚底位于阶板顶面(prev_bottom<=prev_y)才承接，
                # 坑内非骑乘者照常落坑底等待刀刺压落扎死。
                sp = self._spike_platform
                if (left < sp["x"] + SPIKE_PAD_W - 4 and right > sp["x"] + 4 and
                        sp["y"] - 1 <= bottom and prev_bottom <= sp["prev_y"] + 2):
                    return sp["y"], True
                # 硬地面/坑底：必须扫描"上一帧脚底 -> 本帧脚底"跨过的所有行。
                # 只查落点那一行的话，快落地时一帧位移 > 1 格（600px/s 时约 20px，
                # 但从高处坠落可达 36px+）会直接穿过地板，把角色嵌进地里一格。
                cy0 = int((prev_bottom - 0.001) // TILE)
                cy1 = int((bottom - 0.001) // TILE)
                if cy1 >= 0:
                    for cy in range(max(0, cy0 + 1), cy1 + 1):
                        for rx in range(rx0, rx1 + 1):
                            if self._solid_at(rx, cy):
                                return cy * TILE, True
                # 单边跳板（跳板/platform）
                if collide_pads and not drop:
                    for pad in self.pads:
                        px, py, pw = pad[0], pad[1], TILE
                        if (left < px + pw - 4 and right > px + 4 and
                                py - 1 <= bottom and prev_bottom <= py + 6):
                            return py, True
                    # 岩浆坑上方的来回移动阶板（单边平台，踩上被携带）
                    for plate in self._m_plates.values():
                        px, py = plate["x"], plate["y"]
                        if (left < px + M_PAD_W - 4 and right > px + 4 and
                                py - 1 <= bottom and prev_bottom <= py + 6):
                            return py, True
                # 低洼岩浆坑浮托：坑内下落被岩浆表面接住，持续灼烧（不无限坠落）
                if LAVA_LEFT_PX <= x <= LAVA_RIGHT_PX and bottom >= LAVA_SURFACE_Y - 4 and prev_bottom <= LAVA_SURFACE_Y + 8:
                    return LAVA_SURFACE_Y, True
                return ny, False
            else:  # 上升
                top = ny - h
                cy = int(top // TILE)
                if cy >= 0:
                    for rx in range(rx0, rx1 + 1):
                        if self._solid_at(rx, cy):
                            return (cy + 1) * TILE + h, False
                return ny, False
        except Exception as e:
            write_log("y碰撞异常: %r" % (e,))
            return ny, False

    # ------------------------------------------------------------------
    # 压力机关 + 跳板
    # ------------------------------------------------------------------
    def _vine_point(self, idx, t):
        v = self.vines[idx]
        return (v[0] + (v[2] - v[0]) * t, v[1] + (v[3] - v[1]) * t)

    def _try_grab_vine(self, pid):
        try:
            p = self.players[pid]
            best, bd, bt = -1, VINE_GRAB_R ** 2, 0.0
            cy = p["y"] - PLAYER_H * 0.5      # 身体中心
            for i, v in enumerate(self.vines):
                dx, dy = v[2] - v[0], v[3] - v[1]
                L2 = dx * dx + dy * dy
                if L2 <= 1:
                    continue
                t = ((p["x"] - v[0]) * dx + (cy - v[1]) * dy) / L2
                t = max(0.0, min(1.0, t))
                px, py = self._vine_point(i, t)
                d2 = (px - p["x"]) ** 2 + (py - cy) ** 2
                # 取最近的一条：塔里两条藤蔓首尾都在 F2，
                # 若按 t 最大来选会抓到"往下的那条"的顶端，一抓就被端点弹开
                if d2 <= bd:
                    best, bd, bt = i, d2, t
            if best >= 0:
                p["vine"] = best
                p["vine_t"] = bt
                # 当帧就吸附到绳上，否则看起来像"按了没反应"
                gx, gy = self._vine_point(best, bt)
                p["x"] = gx
                p["y"] = gy + 6
                p["vx"] = p["vy"] = 0.0
                p["on_ground"] = False
                self.events.append(("vine_grab", int(gx), int(gy)))
        except Exception as e:
            write_log("抓藤蔓异常: %r" % (e,))

    def _update_vine(self, pid, inp, dt):
        """挂在藤蔓上时接管移动：左右滑动，按跳/交互/下键松手。

        修复两次"滑不上去"：
        1) 跳键既是抓取键又是松手键 -> 按住会被反复甩下。改成边沿检测。
        2) 抓取瞬间 t=0 被当成"已在端点"-> 一抓就掉。改成只有往端点外推才自动松手。
        """
        try:
            p = self.players[pid]
            if p["vine"] < 0:
                return False
            v = self.vines[p["vine"]]
            span = math.hypot(v[2] - v[0], v[3] - v[1]) or 1.0   # 按绳长算，斜索不会过快
            t = p["vine_t"]
            left = bool(inp.get("left"))
            right = bool(inp.get("right"))
            if left:
                t -= VINE_SPEED * dt / span
            if right:
                t += VINE_SPEED * dt / span
            # 跳键松手：必须"重新按下"才算，抓住时按着的不算
            up_now = bool(inp.get("up"))
            up_edge = up_now and not bool(p.get("_vine_up_latch", True))
            p["_vine_up_latch"] = up_now
            if inp.get("down") or inp.get("interact") or up_edge:
                self._release_vine(pid, hop=True)
                return True
            # 往端点外推才自动松手（带着方向冲出去的手感）
            if (t < 0.0 and left) or (t > 1.0 and right):
                self._release_vine(pid, hop=True)
                return True
            t = max(0.0, min(1.0, t))
            p["vine_t"] = t
            px, py = self._vine_point(p["vine"], t)
            p["x"] = px
            p["y"] = py + 6
            p["vx"] = p["vy"] = 0.0
            p["on_ground"] = False
            return True
        except Exception as e:
            write_log("滑索异常: %r" % (e,))
            return False

    def _rect_solid(self, x, y, w, h):
        """矩形（中心 x，底部 y）是否与实心格重叠。"""
        try:
            x0 = int((x - w * 0.5) // TILE)
            x1 = int((x + w * 0.5 - 0.01) // TILE)
            y0 = int((y - h) // TILE)
            y1 = int((y - 0.01) // TILE)
            for cy in range(y0, y1 + 1):
                for cx in range(x0, x1 + 1):
                    if self._solid_at(cx, cy):
                        return True
            return False
        except Exception:
            return False

    def _unstick(self, ent, w, h):
        """把嵌进实心格的角色推到最近的安全位置（优先向上）。

        为什么必须有这道保险：_collide_y 的下落分支是从 `cy0+1` 起扫的
        （只修正"这一帧新跨过"的行）。一旦角色因为 AI 跳跃失败、被挤到墙角、
        或高速下落穿层而**已经**嵌进砖里，那一行永远不会被修，
        角色就永久卡死、只能等死——这就是"卡进地底不能动"。
        """
        try:
            x = float(ent["x"])
            y = float(ent["y"])
            if not self._rect_solid(x, y, w, h):
                return False
            # 1) 向上抬（最符合"卡进地里"的直觉）
            lift = 4.0
            while lift <= h + TILE * 1.5:
                if not self._rect_solid(x, y - lift, w, h):
                    ent["y"] = y - lift
                    if float(ent.get("vy", 0.0)) > 0:
                        ent["vy"] = 0.0
                    if "on_ground" in ent:
                        ent["on_ground"] = True
                    return True
                lift += 4.0
            # 2) 左右推（卡在墙缝/夹缝里）
            for d in (w * 0.6, -w * 0.6, w * 1.2, -w * 1.2,
                      TILE * 1.5, -TILE * 1.5, TILE * 2.5, -TILE * 2.5):
                if not self._rect_solid(x + d, y, w, h):
                    ent["x"] = x + d
                    if "vx" in ent:
                        ent["vx"] = 0.0
                    return True
            # 3) 兜底：抬到该列地表之上
            ent["y"] = float(self.surface_y(x) - 2)
            ent["vy"] = 0.0
            return True
        except Exception as e:
            write_log("脱困异常: %r" % (e,))
            return False

    def _body_solid_at(self, x, y):
        """角色整个身体矩形是否与实心格重叠（松手脱困用）。"""
        return self._rect_solid(x, y, PLAYER_W, PLAYER_H)

    def _move_entity(self, ent, w, h, dt, prev_bottom, collide_pads=False, drop=False):
        """ent: x=中心, y=底部"""
        try:
            # 水平
            nx = ent["x"] + ent["vx"] * dt
            ent["x"] = self._collide_x(ent["x"], nx, ent["y"], w, h, ent["vx"])
            # 垂直
            ny = ent["y"] + ent["vy"] * dt
            new_y, grounded = self._collide_y(ent["x"], ent["y"], ny, w, h, ent["vy"],
                                              prev_bottom, collide_pads, drop)
            ent["y"] = new_y
            if grounded and ent["vy"] > 0:
                ent["vy"] = 0.0
            # 脱困保险：身体中心已在实心格里 = 深度嵌入，当帧就救；
            # 只是边缘擦碰（常见于落地/贴墙那一帧）则等 5 帧，避免误判抖动
            if self._rect_solid(ent["x"], ent["y"], w, h):
                ent["_stuck"] = int(ent.get("_stuck", 0)) + 1
                _deep = self._solid_at(int(ent["x"] // TILE),
                                       int((ent["y"] - h * 0.45) // TILE))
                if _deep or ent["_stuck"] >= 5:
                    self._unstick(ent, w, h)
                    ent["_stuck"] = 0
            else:
                ent["_stuck"] = 0
            return grounded
        except Exception as e:
            write_log("物理移动异常: %r" % (e,))
            return False

    def _release_vine(self, pid, hop=False):
        try:
            p = self.players[pid]
            p["vine"] = -1
            if hop:
                p["vy"] = -230.0
            # 松手点可能嵌在平台里（尤其贴着平台顶端松手时身体下半截在砖里）：
            # 用整个身体矩形判定，抬到该列地表之上，别只查中心点
            if self._body_solid_at(p["x"], p["y"]):
                p["y"] = float(self.surface_y(p["x"]) - 2)
                p["vy"] = 0.0
                p["vx"] = 0.0
                p["x"] = float(max(PLAYER_W, min(WORLD_W - PLAYER_W, p["x"])))
            self.events.append(("vine_release", int(p["x"]), int(p["y"])))
        except Exception:
            pass

    def _spawn_tower(self):
        """熔炉瞭望塔：三层各自有守卫，且都不阻塞波次进度（可选内容）。"""
        try:
            # F1（480）：两只守卫守着补给箱
            for dx in (-40, 40):
                m = Monster(self.mid_counter, "ground",
                            float(101 * TILE + 16 + dx), float(15 * TILE - MONSTER_H))
                self.mid_counter += 1
                m.guard_x = float(101 * TILE + 16)
                m.tower = True
                self.monsters.append(m)
            # F2（352）：一只飞怪在火机关上方巡逻
            m = Monster(self.mid_counter, "fly", float(100 * TILE + 16), float(11 * TILE - 40))
            self.mid_counter += 1
            m.tower = True
            self.monsters.append(m)
            # F3（224）：精英守着武器核心
            m = Monster(self.mid_counter, "ground", float(100 * TILE + 52), float(7 * TILE - MONSTER_H))
            self.mid_counter += 1
            m.elite = True
            m.hp *= ELITE_HP_MUL
            m.maxhp = m.hp
            m.guard_x = float(100 * TILE + 16)
            m.tower = True
            self.monsters.append(m)
            # 共鸣门后隔间：精英守着 C8 补给
            m = Monster(self.mid_counter, "ground", float(104 * TILE + 16),
                        float(11 * TILE - MONSTER_H))
            self.mid_counter += 1
            m.elite = True
            m.hp *= ELITE_HP_MUL
            m.maxhp = m.hp
            m.guard_x = float(104 * TILE + 16)
            m.tower = True
            self.monsters.append(m)
        except Exception as e:
            write_log("塔内刷怪异常: %r" % (e,))

    def _update_vents(self, dt):
        """烈焰机关：周期性喷火，站在火柱里会掉血。"""
        try:
            for v in self.vents:
                v["t"] += dt
                if v["t"] % v["period"] >= v["on"]:
                    continue
                top = v["y"] - VENT_HEIGHT
                for pid, p in self.players.items():
                    if p["hp"] <= 0 or p["invuln"] > 0:
                        continue
                    if abs(p["x"] - v["x"]) > VENT_RANGE_X:
                        continue
                    if not (top <= p["y"] - PLAYER_H * 0.5 <= v["y"] + 6):
                        continue
                    self._damage_player(pid, VENT_DMG, "spike")
        except Exception as e:
            write_log("烈焰机关异常: %r" % (e,))

    def _try_take_weapon(self):
        """第三层武器核心：全队伤害 +50%（一次）。"""
        try:
            if self.weapon_taken:
                return
            for pid, p in self.players.items():
                if p["hp"] <= 0:
                    continue
                if (abs(p["x"] - TOWER_WEAPON_X) < 46 and
                        abs(p["y"] - TOWER_F3_Y) < 60):
                    self.weapon_taken = True
                    for q in self.players.values():
                        q["power"] = WEAPON_POWER
                    self.msg = "拿到烈焰核心！全队伤害提升 50%！"
                    self.events.append(("weapon", int(TOWER_WEAPON_X), int(TOWER_F3_Y)))
                    return
        except Exception as e:
            write_log("武器核心异常: %r" % (e,))

    def _update_rune_gate(self, dt):
        """共鸣门：任一活着的玩家踩住符文则开门，松手 0.5 秒后关门。
        关门时若有人正卡在门格里，把他朝门中心推出去。"""
        try:
            held = False
            for p in self.players.values():
                if p["hp"] <= 0:
                    continue
                if (abs(p["x"] - (RUNE_COL * TILE + 16)) < RUNE_RANGE and
                        abs(p["y"] - 11 * TILE) < 34):
                    held = True
                    break
            if held:
                self._set_rune_gate(True)
                self._rune_timer = RUNE_CLOSE_DELAY
            elif self.rune_open:
                self._rune_timer -= dt
                if self._rune_timer <= 0.0:
                    self._set_rune_gate(False)
        except Exception as e:
            write_log("共鸣门异常: %r" % (e,))

    def _set_rune_gate(self, open_):
        try:
            if open_ == self.rune_open:
                return
            self.rune_open = open_
            gx = RUNE_GATE_COL * TILE + 16
            for y in range(RUNE_GATE_ROWS[0], RUNE_GATE_ROWS[1] + 1):
                if 0 <= y < MAP_H:
                    self.grid[y][RUNE_GATE_COL] = ' ' if open_ else 'H'
            if not open_:
                # 关门：把卡在门格里的玩家推出去
                for p in self.players.values():
                    if abs(p["x"] - gx) < TILE * 0.6:
                        p["x"] = gx - TILE if p["x"] <= gx else gx + TILE
            self.events.append(("rune_gate", gx, RUNE_GATE_ROWS[0] * TILE, int(open_)))
        except Exception as e:
            write_log("共鸣门切换异常: %r" % (e,))

    def _track_dmg(self, pid, dmg):
        """按区域累计实际承受的伤害（结算页"某段无伤"用）。"""
        try:
            self.stats["dmg"][region_of_x(self.players[pid]["x"])] += float(dmg)
        except Exception:
            pass

    def nightfall_at(self):
        """夜幕降临的时刻（秒）。难度越高天黑越早：hard(1.4)≈11分钟，easy(0.7)≈16分钟。"""
        return DUSK_NIGHTFALL * (1.0 + (1.0 - self.difficulty) * 0.5)

    def _night_reinforce(self):
        """夜幕增援：在任意存活角色附近（前后 8~14 格）开出增援裂隙。

        复用裂隙系统（有 1.2s 预警动画，不会凭空刷脸）；
        精英概率随暮色进程提高；完全入夜后一次可能开两个。
        """
        try:
            targets = [p for p in self.players.values() if p["hp"] > 0]
            if not targets:
                return
            hu = random.choice(targets)
            dk = min(1.0, self.elapsed / DUSK_FULLNIGHT)
            count = 2 if (dk >= 1.0 and random.random() < 0.5) else 1
            for _k in range(count):
                d = random.choice((-1, 1)) * random.randint(8, 14)
                cx = int(max(2, min(MAP_W - 3, hu["x"] // TILE + d)))
                sy = self.surface_y(cx * TILE + 16)
                if sy >= WORLD_H:
                    continue                      # 该列悬空（坑/沟），换个地方
                kind = "fly" if random.random() < 0.35 else "ground"
                y = (sy - random.randint(4, 8) * TILE) if kind == "fly" else (sy - MONSTER_H)
                elite = random.random() < 0.12 + 0.38 * dk
                self.rifts.append({
                    "x": float(cx * TILE + 16), "y": float(y),
                    "kind": kind, "elite": elite, "t": 0.0,
                    "delay": 1.2, "size": 30.0 if kind == "ground" else 25.0,
                    "tier": 9,
                })
                self.events.append(("rift_open", cx * TILE + 16, int(y)))
        except Exception as e:
            write_log("夜幕增援异常: %r" % (e,))

    def _update_duo(self, dt):
        """熔炉闸门：两块机关必须同时被踩住 0.45 秒才升起。"""
        try:
            if self.duo_gate_open:
                return
            held = [False, False]
            for p in self.players.values():
                if p["hp"] <= 0:
                    continue
                for i, cx in enumerate(DUO_PLATE_COLS):
                    if (abs(p["x"] - (cx * TILE + 16)) < DUO_PLATE_RANGE and
                            abs(p["y"] - 19 * TILE) < 34):
                        held[i] = True
            if all(held):
                self._duo_hold += dt
                if self._duo_hold >= DUO_HOLD_TIME:
                    self._open_duo_gate()
            else:
                if self._duo_hold > 0.0 and any(held):
                    self.msg = "闸门需要两块机关同时被踩住！"
                self._duo_hold = 0.0
        except Exception as e:
            write_log("双人机关异常: %r" % (e,))

    def _open_duo_gate(self):
        try:
            self.duo_gate_open = True
            self._duo_hold = 0.0
            for y in range(11, 19):
                if 0 <= y < MAP_H:
                    self.grid[y][DUO_GATE_COL] = ' '
            self.msg = "两块机关同时亮起，熔炉闸门升起了！"
            self.events.append(("duo_open", DUO_GATE_COL * TILE + 16, 15 * TILE + 64))
        except Exception as e:
            write_log("闸门开启异常: %r" % (e,))

    def _update_plates(self, dt, now):
        try:
            shield = self.players[1]
            for pl in self.plates:
                pl["cooldown"] = max(0.0, pl["cooldown"] - dt)
                if pl["active"]:
                    continue
                cfg = PLATE_CONFIGS[[p["id"] for p in self.plates].index(pl["id"])]
                # 机关矩形要向上覆盖玩家身高：站在地面时脚底 y 正好等于 19*TILE，
                # 而机关矩形从 19*TILE 起算，AABB 的 `ay+ah > by` 恰好是 608>608 -> 永远不成立。
                plate_rect = (cfg["cx"] * TILE, 19 * TILE - PLAYER_H,
                              TILE * 2, TILE + PLAYER_H)
                # 盾卫踩踏
                if shield["hp"] > 0 and rect_overlap(plate_rect, (shield["x"] - PLAYER_W / 2,
                                                                 shield["y"] - PLAYER_H, PLAYER_W, PLAYER_H)):
                    pl["active"] = True
                    pl["remaining"] = cfg["dur"]
                    for (pcx, pcy) in cfg["pads"]:
                        self.pads.append([pcx * TILE, pcy * TILE, cfg["dur"], cfg["dur"], True, pl["id"]])
                    self.events.append(("pad_spawn", cfg["cx"] * TILE + 16, 19 * TILE - 10))
                    self.msg = "盾卫踩踏机关！临时浮空跳板已生成！"
        except Exception as e:
            write_log("机关更新异常: %r" % (e,))

    def _update_pads(self, dt):
        try:
            remain_list = []
            for pad in self.pads:
                pad[2] -= dt
                if pad[2] > 0:
                    remain_list.append(pad)
            self.pads = remain_list
            # 机关状态与跳板组联动
            for pl in self.plates:
                if pl["active"]:
                    any_pad = any(pd[5] == pl["id"] for pd in self.pads)
                    if not any_pad:
                        pl["active"] = False
                        pl["remaining"] = 0.0
                        pl["cooldown"] = 0.8
        except Exception as e:
            write_log("跳板更新异常: %r" % (e,))

    # ------------------------------------------------------------------
    # 熔岩术士（远程）
    # ------------------------------------------------------------------
    def _caster_ai(self, m, dt):
        try:
            alive = [p for p in self.players.values() if p["hp"] > 0]
            if not alive:
                m.vx = 0.0
                m.vy = 0.0
                return
            target = min(alive, key=lambda p: abs(p["x"] - m.x))
            dx = target["x"] - m.x
            dy = (target["y"] - 26) - m.y
            dist = max(1.0, math.hypot(dx, dy))
            m.dir = 1 if dx > 0 else -1
            # 保持中距离：太近后撤，太远贴近，中间横向拉扯
            if dist < CASTER_KEEP_MIN:
                m.vx = -m.dir * CASTER_SPEED
                m.vy = 40.0
            elif dist > CASTER_KEEP_MAX:
                m.vx = m.dir * CASTER_SPEED * 0.8
                m.vy = -20.0
            else:
                m.vx = m.dir * CASTER_SPEED * 0.25
                m.vy = 0.0
            # 悬停回锚点高度
            m.vy += (m.anchor_y - m.y) * 1.6 + math.sin(m.t * 2.2) * 18.0
            m.vy = max(-90.0, min(90.0, m.vy))
            # 施法
            m.cast_cd -= dt
            if m.cast_cd <= 0 and dist < CASTER_RANGE:
                m.cast_cd = CASTER_CAST_CD * random.uniform(0.85, 1.2)
                self._spawn_fireball(m, target)
        except Exception as e:
            write_log("术士 AI 异常: %r" % (e,))

    def _spawn_fireball(self, m, target):
        try:
            sx = m.x + (12 if target["x"] > m.x else -12)
            sy = m.y - 18
            dx = target["x"] - sx
            dy = (target["y"] - 24) - sy
            d = max(1.0, math.hypot(dx, dy))
            self.fireballs.append({
                "x": sx, "y": sy,
                "vx": dx / d * FIREBALL_SPEED, "vy": dy / d * FIREBALL_SPEED,
                "t": FIREBALL_LIFE, "r": FIREBALL_R,
            })
            self.events.append(("cast", int(sx), int(sy)))
        except Exception as e:
            write_log("火球生成异常: %r" % (e,))

    def _update_fireballs(self, dt):
        """火球：撞墙消失、命中扣血；盾卫格挡可挡下，弓箭可以打爆。"""
        out = []
        for f in self.fireballs:
            try:
                f["t"] -= dt
                if f["t"] <= 0:
                    continue
                f["x"] += f["vx"] * dt
                f["y"] += f["vy"] * dt
                if (f["x"] < 0 or f["x"] > WORLD_W or f["y"] < 0 or f["y"] > WORLD_H or
                        self._solid_at(int(f["x"] // TILE), int(f["y"] // TILE))):
                    self.events.append(("fizzle", int(f["x"]), int(f["y"])))
                    continue
                fr = (f["x"] - f["r"], f["y"] - f["r"], f["r"] * 2, f["r"] * 2)
                consumed = False
                for pid, p in self.players.items():
                    if p["hp"] <= 0 or p["invuln"] > 0:
                        continue
                    pr = (p["x"] - PLAYER_W / 2, p["y"] - PLAYER_H, PLAYER_W, PLAYER_H)
                    if rect_overlap(fr, pr):
                        if pid == 1 and p["blocking"]:
                            self.events.append(("block", int(f["x"]), int(f["y"])))
                        else:
                            self._damage_player(pid, FIREBALL_DMG, "fireball")
                        consumed = True
                        break
                if consumed:
                    continue
                for a in list(self.arrows):
                    if rect_overlap(fr, (a["x"] - 6, a["y"] - 6, 12, 12)):
                        self.events.append(("fizzle", int(f["x"]), int(f["y"])))
                        try:
                            self.arrows.remove(a)
                        except ValueError:
                            pass
                        consumed = True
                        break
                if consumed:
                    continue
                out.append(f)
            except Exception:
                pass
        self.fireballs = out

    # ------------------------------------------------------------------
    # 熔炉守卫（Boss）
    # ------------------------------------------------------------------
    def _update_rifts(self, dt):
        """裂隙到期 -> 怪物从里面走出来（出场期间不动/不伤害/不可被射）。"""
        if not self.rifts:
            return
        keep = []
        for r in self.rifts:
            # 已放完怪：进入闭合动画，缩到 0 再移除
            if r.get("fade", 0.0) > 0.0:
                r["fade"] -= dt
                if r["fade"] > 0.0:
                    keep.append(r)
                continue
            r["t"] += dt
            if r["t"] < r["delay"]:
                keep.append(r)
                continue
            try:
                m = Monster(self.mid_counter, r["kind"], r["x"], r["y"])
                self.mid_counter += 1
                if r.get("elite"):
                    m.elite = True
                    m.hp *= ELITE_HP_MUL
                    m.maxhp = m.hp
                if self.difficulty != 1.0:
                    m.hp = max(1.0, m.hp * self.difficulty)
                    m.maxhp = m.hp
                m.state = "spawn"
                m.state_t = 0.55          # 出场动画时长，这段时间是安全的
                # 位置就用正常出生点：视觉上的"从黑洞里浮出来"由渲染偏移负责，
                # 引擎里挪 y 会让 Boss 这种大体型直接陷进祭坛卡住
                self.monsters.append(m)
                self.events.append(("rift_open", int(r["x"]), int(r["y"])))
                r["fade"] = 0.52          # 与出场动画同步收掉
                r["fade_max"] = 0.52
                keep.append(r)
            except Exception as e:
                write_log("裂隙生成怪物异常: %r" % (e,))
        self.rifts = keep

    def _spawn_boss(self):
        try:
            # Boss 也走裂隙出场：更大的黑洞 + 更长的预警，才有"守卫苏醒"的压迫感
            self.rifts.append({
                "x": float(144 * TILE), "y": float(15 * TILE - 6),
                "kind": "boss", "elite": False, "t": 0.0,
                "delay": 1.9, "size": 62.0, "tier": 3,
            })
            self.boss_spawned = True
            self.msg = "熔炉守卫苏醒！红光蓄力后会直线冲锋，用冲刺躲开！"
            self.events.append(("boss_spawn", 144 * TILE, 15 * TILE - 50))
        except Exception as e:
            write_log("Boss 生成异常: %r" % (e,))

    def _boss_summon(self, m):
        try:
            for dx in (-150, 150):
                c = Monster(self.mid_counter, "caster",
                            float(max(120, min(WORLD_W - 120, m.x + dx))), float(11 * TILE))
                self.mid_counter += 1
                c.cast_cd = 1.2
                self.monsters.append(c)
            self.msg = "熔炉守卫召唤了术士！弓箭手清场，盾卫顶住！"
            self.events.append(("boss_summon", int(m.x), int(m.y - 40)))
        except Exception as e:
            write_log("Boss 召唤异常: %r" % (e,))

    def _spawn_shockwave(self, m):
        try:
            self.shockwaves.append({"x": float(m.x), "y": float(m.y), "r": 20.0,
                                    "hit": [], "t": 0.0})
            self.events.append(("shock", int(m.x), int(m.y)))
        except Exception as e:
            write_log("冲击波生成异常: %r" % (e,))

    def _update_shockwaves(self, dt):
        """砸地冲击波：贴地扩散，跳起来才能躲过。"""
        out = []
        for w in self.shockwaves:
            try:
                w["t"] += dt
                w["r"] += SHOCK_SPEED * dt
                for pid, p in self.players.items():
                    if pid in w["hit"] or p["hp"] <= 0 or p["invuln"] > 0:
                        continue
                    if abs(p["x"] - w["x"]) > w["r"] + 14:
                        continue
                    if abs(p["y"] - w["y"]) > 26:      # 跳在空中就能躲
                        continue
                    w["hit"].append(pid)
                    if pid == 1 and p["blocking"]:
                        self.events.append(("block", int(p["x"]), int(p["y"] - 20)))
                    else:
                        self._damage_player(pid, SHOCK_DMG, "spike")
                if w["r"] < SHOCK_MAX_R:
                    out.append(w)
            except Exception:
                pass
        self.shockwaves = out

    def _boss_ai(self, m, dt):
        """三段式：接近 → 蓄力（红光） → 冲锋 → 收招。"""
        try:
            alive = [p for p in self.players.values() if p["hp"] > 0]
            if not alive:
                m.vx = 0.0
                return
            target = min(alive, key=lambda p: abs(p["x"] - m.x))
            dx = target["x"] - m.x
            hp_ratio = m.hp / float(max(1, m.maxhp))
            m.phase = 3 if hp_ratio <= BOSS_PHASE3 else (2 if hp_ratio <= BOSS_PHASE2 else 1)
            if m.phase >= 3 and not m.summoned:
                m.summoned = True
                self._boss_summon(m)
            if m.phase >= 2:
                m.slam_cd = max(0.0, m.slam_cd - dt)
                if not m.enraged:
                    m.enraged = True
                    m.atk_cd = min(m.atk_cd, 0.5)
                    self.events.append(("boss_enrage", int(m.x), int(m.y)))
            spd = BOSS_SPEED * (1.4 if m.enraged else 1.0)
            chg = BOSS_CHARGE_SPEED * (1.18 if m.enraged else 1.0)
            tele_t = 0.42 if m.enraged else BOSS_CHARGE_TELE
            rec_t = 0.58 if m.enraged else BOSS_RECOVER
            if m.state in ("walk", "recover"):
                m.dir = 1 if dx > 0 else -1
            m.state_t += dt
            m.flash = 0.0
            if m.state == "slam":
                m.vx *= 0.8
                if m.on_ground and m.state_t > 0.35:
                    self._spawn_shockwave(m)
                    m.state = "recover"
                    m.state_t = 0.0
                    m.slam_cd = BOSS_SLAM_CD
            elif m.state == "walk":
                # 二阶段起：近身会跳起砸地，制造必须跳过去的冲击波
                if m.phase >= 2 and m.slam_cd <= 0 and m.on_ground and abs(dx) < 330:
                    m.vy = -BOSS_SLAM_POWER
                    m.state = "slam"
                    m.state_t = 0.0
                    m.vx = 0.0
                    self.events.append(("boss_slam_up", int(m.x), int(m.y)))
                    return
                m.vx = m.dir * spd
                m.atk_cd = max(0.0, m.atk_cd - dt)
                if m.atk_cd <= 0 and abs(dx) < (520 if m.phase >= 3 else 430) and abs(target["y"] - m.y) < 140:
                    m.state = "tele"
                    m.state_t = 0.0
                    m.vx = 0.0
            elif m.state == "tele":
                m.vx = 0.0
                m.flash = min(1.0, m.state_t / max(0.01, tele_t))
                if m.state_t >= tele_t:
                    m.state = "charge"
                    m.state_t = 0.0
                    m.dir = 1 if dx > 0 else -1
                    self.events.append(("boss_charge", int(m.x), int(m.y)))
            elif m.state == "charge":
                m.vx = m.dir * chg
                if m.state_t >= BOSS_CHARGE_TIME:
                    m.state = "recover"
                    m.state_t = 0.0
                    self.events.append(("boss_slam", int(m.x), int(m.y)))
            else:  # recover
                m.vx *= 0.82
                if m.state_t >= rec_t:
                    m.state_t = 0.0
                    m.state = "walk"
                    m.atk_cd = 2.6 * (0.7 if m.enraged else 1.0)
                    # 狂暴后有机会立刻接第二次冲锋
                    if m.enraged and random.random() < 0.45:
                        m.state = "tele"
                        m.atk_cd = 0.0
        except Exception as e:
            write_log("Boss AI 异常: %r" % (e,))

    # ------------------------------------------------------------------
    # 怪物
    # ------------------------------------------------------------------
    def _update_monsters(self, dt, now):
        try:
            archer = self.players[0]
            shield = self.players[1]
            # 死亡残影（纯表现，不影响逻辑）
            for c in self.corpses:
                c["t"] += dt
            if self.corpses:
                self.corpses = [c for c in self.corpses if c["t"] < c["max"]]
            for m in list(self.monsters):
                try:
                    m.t += dt
                    if m.state == "spawn":
                        # 出场动画：不下落、不移动、不攻击
                        m.state_t -= dt
                        m.vx *= 0.4
                        m.vy = 0.0
                        if m.state_t <= 0.0:
                            m.state = "walk" if m.kind in ("ground", "boss") else "hover"
                            m.state_t = 0.0
                            m.atk_cd = max(m.atk_cd, 0.7)
                        continue
                    if m.kind == "boss":
                        if m.stun > 0:
                            m.stun -= dt
                            m.vx *= 0.5
                        else:
                            self._boss_ai(m, dt)
                    elif m.kind == "caster":
                        if m.stun > 0:
                            m.stun -= dt
                            m.vx *= 0.4
                        else:
                            self._caster_ai(m, dt)
                    elif m.stun > 0:
                        m.stun -= dt
                        m.vx *= 0.6
                    elif m.kind == "ground":
                        self._ground_monster_ai(m, archer, dt)
                        if m.guard_x is not None and abs(m.x - m.guard_x) > TOWER_GUARD_R:
                            # 守护型：追出范围就撤回到守卫点
                            m.vx = (60.0 if m.guard_x > m.x else -60.0)
                    else:
                        self._fly_monster_ai(m, archer, dt)

                    # 物理
                    if m.kind in ("ground", "boss"):
                        ew, eh = (BOSS_W, BOSS_H) if m.kind == "boss" else (MONSTER_W, MONSTER_H)
                        m.vy += GRAVITY * dt
                        m.vy = min(m.vy, 1500)
                        prev = m.y
                        nx = m.x + m.vx * dt
                        m.x = self._collide_x(m.x, nx, m.y, ew, eh, m.vx)
                        ny = m.y + m.vy * dt
                        new_y, grounded = self._collide_y(m.x, m.y, ny, ew, eh, m.vy,
                                                          prev, collide_pads=False, drop=False)
                        m.y = new_y
                        if m.kind == "boss":
                            # 关在祭坛石台上：它不会跳台阶，一旦冲出平台就会卡在台阶侧面，
                            # 玩家只看到血条不见人。这里把它限制在台面范围内。
                            m.x = max(139 * TILE + 36, min(150 * TILE - 36, m.x))
                            if m.y > 19 * TILE - 40:
                                m.y = 15 * TILE
                                m.vy = 0.0
                        m.on_ground = grounded
                        if grounded and m.vy > 0:
                            m.vy = 0.0    # 落地清空垂直速度
                    else:
                        m.x += m.vx * dt
                        m.y += m.vy * dt
                        m.x = max(FLY_W / 2, min(WORLD_W - FLY_W / 2, m.x))
                        m.y = max(60, min(WORLD_H - 40, m.y))
                        # 修复"飞怪钻进地下看不见却仍能攻击"：贴住所在地表，
                        # 玩家掉进坑里时它就在坑口上方等，而不是嵌进泥/墙里。
                        _surf = self.surface_y(m.x)
                        if m.y > _surf - 30:
                            m.y = _surf - 30
                            if m.vy > 0:
                                m.vy = 0.0
                        m.on_ground = False

                    # 接触伤害
                    self._monster_contact(m, archer, shield, now)

                    # 掉进坑里出不来 -> 拉回玩家附近的地面。
                    # 否则这一波的怪永远清不完，传送门永远不会开（软锁）。
                    if m.kind == "ground" and m.y > 19 * TILE + 20:
                        m.stuck_t += dt
                        if m.stuck_t > 2.5:
                            m.stuck_t = 0.0
                            alive = [p for p in self.players.values() if p["hp"] > 0]
                            if alive:
                                tgt = min(alive, key=lambda p: abs(p["x"] - m.x))
                                m.x = max(PLAYER_W, min(WORLD_W - PLAYER_W, tgt["x"] - 150))
                                m.y = tgt["y"]
                                m.vx = m.vy = 0.0
                                self.events.append(("monster_return", int(m.x), int(m.y - 10)))
                    else:
                        m.stuck_t = max(0.0, m.stuck_t - dt)

                    # 统一死亡清理（弓箭/挥剑/岩浆之外的伤害来源也能正确移除）
                    if m.hp <= 0:
                        self._kill_monster(m)
                        continue

                    # 岩浆灼烧：地面怪掉入低洼岩浆坑持续扣血
                    if (m.kind == "ground" and LAVA_LEFT_PX <= m.x <= LAVA_RIGHT_PX and
                            abs(m.y - LAVA_SURFACE_Y) <= 4):
                        if now - m.last_lava >= LAVA_MONSTER_TICK:
                            m.last_lava = now
                            m.hp -= LAVA_MONSTER_DMG
                            self.events.append(("lava", int(m.x), int(LAVA_SURFACE_Y - 8)))
                            if m.hp <= 0:
                                self._kill_monster(m, silent=True)
                                continue

                    # 坠入深渊
                    if m.y > WORLD_H + 40:
                        self._kill_monster(m, silent=True)
                except Exception as e:
                    write_log("单个怪物更新异常: %r" % (e,))
        except Exception as e:
            write_log("怪物更新异常: %r" % (e,))

    def _ground_monster_ai(self, m, archer, dt):
        try:
            spd = 105.0
            # 脱队追赶：玩家一路冲过去会把地面怪甩在身后（怪 105 vs 玩家 250），
            # 第一波永远清不完 -> 第二波不刷 -> 玩家在终点干等。离开远了就加速追。
            _dist = abs(archer["x"] - m.x)
            if _dist > 700:
                spd = 235.0
            elif _dist > 420:
                spd = 165.0
            tx = archer["x"]
            dx = tx - m.x
            m.dir = 1 if dx > 0 else -1
            # 前方判定
            front_x = m.x + m.dir * (MONSTER_W / 2 + 6)
            feet_y = m.y
            col = int(front_x // TILE)
            row = int((feet_y - MONSTER_H * 0.5) // TILE)
            # 前方坑检测（沿移动方向扫描，向左走时同样有效）
            gap = 0
            c2 = col
            step_dir = 1 if m.dir >= 0 else -1
            while gap < 8:
                if c2 < 0 or c2 >= MAP_W:
                    break
                solid_row = False
                for rr in range(row, min(MAP_H, row + 3)):
                    if self._solid_at(c2, rr):
                        solid_row = True
                        break
                if solid_row:
                    break
                gap += 1
                c2 += step_dir
            # 前方墙检测
            wall = False
            if 0 <= col < MAP_W and 0 <= row < MAP_H:
                wall = (self._solid_at(col, row) and self._solid_at(col, row - 1) and
                        self._solid_at(col, row - 2))
            if gap >= 3:
                m.vx = 0.0          # 深坑不跳，原地警戒，避免掉进深谷
            elif gap >= 1:
                if m.on_ground:
                    m.vy = -560.0   # 小沟跳跃
                m.vx = m.dir * spd * 0.6
            elif wall:
                if m.on_ground:
                    m.vy = -590.0   # 矮墙跳
                m.vx = m.dir * spd * 0.6
            else:
                m.vx = m.dir * spd
            # 转弯贴地
            if m.on_ground and abs(m.vx) < 1 and m.dir != 0:
                m.dir = -m.dir
        except Exception as e:
            write_log("地面怪AI异常: %r" % (e,))

    def _fly_monster_ai(self, m, archer, dt):
        """飞怪：恒在玩家头顶 90px 跟随，每 3~5 秒俯冲一次。

        旧逻辑有两种高度（头顶 95px / 贴脸 26px）按 4 秒切换，
        贴脸那半边会让它贴在玩家身上甚至压到地面以下，射不中也看不清。
        现在固定悬停高度，只有俯冲时才会下探。
        """
        try:
            spd = 110.0
            # 悬停高度：玩家脚底 - 身高 - 90（跟着玩家上平台/下坑一起走）
            hover_y = archer["y"] - PLAYER_H - 90.0
            hover_y = min(hover_y, self.surface_y(m.x) - 74.0)   # 不贴地
            hover_y = max(hover_y, 28.0)                          # 不飞出画面顶

            diving = (m.state == "dive")
            if diving:
                m.state_t -= dt
                if m.state_t <= 0.0:
                    m.state = "hover"
                    diving = False
            if not diving:
                if m.state not in ("hover", "walk"):
                    m.state = "hover"
                m.atk_cd = max(0.0, m.atk_cd - dt)
                # 玩家在下方、水平够近时才俯冲（在头顶才不会一头扎进地板）
                if (m.atk_cd <= 0.0 and abs(archer["x"] - m.x) < 175
                        and 20.0 < (archer["y"] - m.y) < 280.0):
                    m.state = "dive"
                    m.state_t = 0.6
                    m.atk_cd = random.uniform(3.2, 5.0)
                    diving = True

            if diving:
                tx = archer["x"]
                ty = archer["y"] - 22.0
                kx, ky = 3.2, 4.4
            else:
                tx = archer["x"] + math.sin(m.t * 1.25) * 42.0
                ty = hover_y + math.sin(m.t * 2.1) * 9.0
                kx, ky = 2.2, 2.6
            m.vx = max(-spd * 2.0, min(spd * 2.0, (tx - m.x) * kx))
            m.vy = max(-spd * 2.4, min(spd * 2.4, (ty - m.y) * ky))
        except Exception as e:
            write_log("飞行怪AI异常: %r" % (e,))

    def _monster_contact(self, m, archer, shield, now):
        try:
            if m.state == "spawn":      # 破壳期间不伤人
                return
            mr = m.rect()
            targets = []
            if archer["hp"] > 0 and rect_overlap(mr, (archer["x"] - PLAYER_W / 2,
                                                      archer["y"] - PLAYER_H, PLAYER_W, PLAYER_H)):
                targets.append(0)
            if shield["hp"] > 0 and rect_overlap(mr, (shield["x"] - PLAYER_W / 2,
                                                      shield["y"] - PLAYER_H, PLAYER_W, PLAYER_H)):
                targets.append(1)
            for pid in targets:
                if now - m.last_hit[pid] < DAMAGE_TICK_GAP:
                    continue
                p = self.players[pid]
                if p["invuln"] > 0:
                    continue
                m.last_hit[pid] = now
                if m.kind == "boss":
                    base = BOSS_TOUCH_DMG + (10 if getattr(m, "state", "") == "charge" else 0)
                elif m.kind == "fly":
                    base = FLY_DMG
                else:
                    base = GROUND_DMG_TO_ARCHER if pid == 0 else GROUND_DMG_TO_SHIELD
                if m.elite:
                    base *= ELITE_DMG_MUL
                if "glass" in self.mods:
                    base *= 1.5
                base *= self.difficulty
                if pid == 0:
                    self._track_dmg(pid, base)
                    p["hp"] = max(0, p["hp"] - base)
                else:
                    charging = (m.kind == "boss" and getattr(m, "state", "") == "charge")
                    if p["blocking"] and charging:
                        if p["block_hold"] <= PARRY_WINDOW:
                            # 完美格挡：Boss 硬直，这是"看红光"的奖励
                            m.stun = 1.5
                            m.state = "recover"
                            m.state_t = 0.0
                            m.vx = 0.0
                            self.events.append(("parry", int(p["x"]), int(p["y"] - 24)))
                        else:
                            # 硬顶冲锋：掉血 + 被击飞（不能只按住 K）
                            p["hp"] = max(0, p["hp"] - base * 0.7)
                            p["vx"] = (-1 if m.dir > 0 else 1) * 380
                            p["vy"] = -260
                            self.events.append(("guard_break", int(p["x"]), int(p["y"] - 20)))
                    elif p["blocking"]:
                        if m.kind == "boss":
                            # 挡下 Boss 的普通接触：免伤但不击退/不硬直，
                            # 否则盾卫可以一直举盾把 Boss 推出战场
                            self.events.append(("block", int(p["x"]), int(p["y"] - 20)))
                        else:
                            m.stun = 0.8
                            m.vx = 260 if p["facing"] > 0 else -260
                            self.events.append(("block", int(p["x"]), int(p["y"] - 20)))
                    else:
                        self._track_dmg(pid, base)
                        p["hp"] = max(0, p["hp"] - base)
                self.events.append(("hurt", int(p["x"]), int(p["y"] - 30)))
        except Exception as e:
            write_log("怪物接触伤害异常: %r" % (e,))

    def _kill_monster(self, m, silent=False):
        try:
            if m in self.monsters:
                self.monsters.remove(m)
                self.kills += 1
            # 守卫倒下时，它召唤的术士一并消散（避免"打完 Boss 还要追小怪"）
            if m.kind == "boss":
                for other in list(self.monsters):
                    if other.kind == "caster":
                        self._kill_monster(other, silent=True)
            self.corpses.append({"kind": m.kind, "x": float(m.x), "y": float(m.y),
                                 "t": 0.0, "max": 1.1 if m.kind == "boss" else 0.55,
                                 "dir": m.dir})
            if len(self.corpses) > 10:
                del self.corpses[:-10]
            self.events.append(("die", int(m.x), int(m.y - 10), m.kind))
        except Exception as e:
            write_log("怪物死亡处理异常: %r" % (e,))

    # ------------------------------------------------------------------
    # 弓箭
    # ------------------------------------------------------------------
    def _damage_rock(self, cx, cy, dmg=1):
        """统一的岩石破坏入口（箭 / 盾卫剑共用）。命中返回 True。

        之前只有箭能打碎 'R'，火箭墙这类"必须清路"的障碍如果玩家玩盾卫
        就完全无法处理（AI 弓手不一定在射程内）。
        """
        if not (0 <= cy < MAP_H and 0 <= cx < MAP_W):
            return False
        if self.grid[cy][cx] != 'R':
            return False
        key = (cx, cy)
        hp = self.rocks.get(key, ROCK_HP) - dmg
        if hp <= 0:
            self.rocks.pop(key, None)
            self.grid[cy][cx] = 'G' if cy == 19 else ' '
            self.events.append(("rock_break", cx * TILE + 16, cy * TILE + 16))
        else:
            self.rocks[key] = hp
        return True

    def _update_arrows(self, dt):
        try:
            remain = []
            for a in self.arrows:
                try:
                    a.t += dt
                    if a.t > ARROW_LIFETIME:
                        continue
                    steps = max(1, int(math.ceil(max(abs(a.vx), abs(a.vy)) * dt / 6.0)))
                    dead = False
                    for _ in range(steps):
                        a.x += a.vx * dt / steps
                        a.y += a.vy * dt / steps
                        cx = int(a.x // TILE)
                        cy = int(a.y // TILE)
                        if self._solid_at(cx, cy):
                            c = self.grid[cy][cx] if (0 <= cy < MAP_H and 0 <= cx < MAP_W) else ''
                            if c == 'R':
                                self._damage_rock(cx, cy, 1)
                                self.events.append(("break", int(a.x), int(a.y)))
                            else:
                                self.events.append(("break", int(a.x), int(a.y)))
                            dead = True
                            break
                        # 命中飞行怪与 Boss（弓箭对地面近战怪无效——那是盾卫的活）
                        for m in self.monsters:
                            if m.state == "spawn":     # 出场无敌
                                continue
                            if m.kind not in ("fly", "caster", "boss"):
                                continue
                            if a.aid in m.hit_arrows:
                                continue
                            mr = m.rect()
                            if (mr[0] - 4 < a.x < mr[0] + mr[2] + 4 and
                                    mr[1] - 4 < a.y < mr[1] + mr[3] + 4):
                                m.hit_arrows.add(a.aid)
                                m.hp -= getattr(a, "dmg", 1)
                                self.events.append(("hit", int(m.x), int(m.y - 12)))
                                if m.hp <= 0:
                                    self._kill_monster(m)
                                dead = True
                                break
                        if dead:
                            break
                    if not dead and a.y < WORLD_H + 40:
                        remain.append(a)
                except Exception as e:
                    write_log("弓箭单支更新异常: %r" % (e,))
            self.arrows = remain
        except Exception as e:
            write_log("弓箭更新异常: %r" % (e,))

    # ------------------------------------------------------------------
    # 传送门 / 通关
    # ------------------------------------------------------------------
    def _check_portal(self, dt):
        try:
            if not self.portal_active:
                self.win_t = 0.0
                return
            p0 = self.players[0]
            p1 = self.players[1]
            in0 = rect_overlap(PORTAL_RECT, (p0["x"] - PLAYER_W / 2, p0["y"] - PLAYER_H, PLAYER_W, PLAYER_H))
            in1 = rect_overlap(PORTAL_RECT, (p1["x"] - PLAYER_W / 2, p1["y"] - PLAYER_H, PLAYER_W, PLAYER_H))
            if in0 and in1:
                self.win_t += dt
                if self.win_t >= 1.0 and not self.win:
                    self.win = True
                    self.beat_night = self.elapsed < self.nightfall_at()
                    self.msg = ("合作通关！恭喜！你赶在了夜幕之前！"
                                if self.beat_night else "合作通关！恭喜！")
                    self.events.append(("win", 0, 0))
            else:
                self.win_t = 0.0
        except Exception as e:
            write_log("传送门检测异常: %r" % (e,))

    # ------------------------------------------------------------------
    # 状态打包（双方共用同一份，保证完全同步）
    # ------------------------------------------------------------------
    def pack(self):
        try:
            players = {}
            for pid, p in self.players.items():
                players[pid] = {
                    "x": round(p["x"], 2), "y": round(p["y"], 2),
                    "facing": p["facing"], "moving": p["moving"],
                    "blocking": p["blocking"], "swing": round(p["swing"], 2),
                    "hp": max(0, int(p["hp"])), "maxhp": int(p["maxhp"]),
                    "dash_cd": round(p["dash_cd"], 2), "dash_max": DASH_CD,
                    "invuln": round(p["invuln"], 2),
                    "jumps": p["jumps"], "on_ground": p["on_ground"],
                    "vine": p.get("vine", -1), "vine_t": round(p.get("vine_t", 0.0), 3),
                    "power": round(float(p.get("power", 1.0)), 2),
                    "vy": round(p["vy"], 1), "land": round(p["land"], 2),
                }
            arrows = [{"aid": a.aid, "x": round(a.x, 2), "y": round(a.y, 2),
                       "ang": round(a.ang, 3)} for a in self.arrows]
            monsters = [{"mid": m.mid, "kind": m.kind, "x": round(m.x, 2),
                         "y": round(m.y, 2), "hp": max(0, int(m.hp)),
                         "maxhp": m.maxhp, "stun": round(m.stun, 2),
                         "state": m.state, "state_t": round(m.state_t, 2),
                         "flash": round(m.flash, 2), "dir": m.dir,
                         "elite": bool(m.elite), "enraged": bool(m.enraged),
                         "phase": m.phase}
                        for m in self.monsters]
            plates = [{"id": pl["id"], "active": pl["active"],
                       "remaining": round(pl["remaining"], 2)}
                      for pl in self.plates]
            pads = [{"x": pd[0], "y": pd[1], "t": round(pd[2], 1), "max": round(pd[3], 1)}
                    for pd in self.pads]
            rocks = [{"cx": k[0], "cy": k[1], "hp": v} for k, v in self.rocks.items()]
            m_plates = [{"id": pl["id"], "x": round(pl["x"], 1), "y": pl["y"]}
                        for pl in self._m_plates.values()]
            sp = self._spike_platform
            spike_platform = {"x": round(sp["x"], 1), "y": round(sp["y"], 1),
                              "bloody": sp["bloody"]}
            hammers = [{"id": h["id"], "bx": round(h["bx"], 1), "by": round(h["by"], 1),
                        "px": h["px"], "py": h["py"], "ang": round(h["ang"], 3),
                        "len": h["len"], "r": h["r"]} for h in self._hammers]
            fall_rocks = [{"id": r["id"], "x": r["x"], "y": round(r["y"], 1),
                           "y0": r["y0"], "land_y": round(r["land_y"], 1),
                           "open_t": round(r["open_t"], 2),
                           "state": r["state"]} for r in self._fall_rocks]
            checkpoints = [{"x": cp["x"], "gy": cp.get("gy", 19 * TILE),
                            "active": cp["active"],
                            "flash": round(cp["flash"], 2)} for cp in self._checkpoints]
            # gy 必须打包：渲染端拿不到就会退回默认值 608（地面高度），
            # 结果高台上的箱子（上层平台/瞭望塔/隔间）全被画在地面上，
            # 和实际交互位置对不上——玩家在平台上能看到"E 开启"却看不到箱子
            chests = [{"id": ch["id"], "x": ch["x"], "opened": ch["opened"],
                       "gy": round(ch["gy"], 1),
                       "t": round(ch["open_t"], 2)} for ch in self._chests]
            return {
                "t": self.tick, "type": "state",
                "players": players,
                "arrows": arrows,
                "monsters": monsters,
                "rifts": [{"x": round(r["x"], 1), "y": round(r["y"], 1),
                           "t": round(min(r["t"], r["delay"]), 2), "delay": r["delay"],
                           "size": r["size"], "kind": r["kind"],
                           "fade": round(r.get("fade", 0.0), 2),
                           "fade_max": r.get("fade_max", 0.34)}
                          for r in self.rifts],
                "plates": plates,
                "pads": pads,
                "m_plates": m_plates,
                "spike_platform": spike_platform,
                "hammers": hammers,
                "fall_rocks": fall_rocks,
                "checkpoints": checkpoints,
                "chests": chests,
                "fireballs": [{"x": round(f["x"], 1), "y": round(f["y"], 1), "r": f["r"]}
                              for f in self.fireballs],
                "shockwaves": [{"x": round(w["x"], 1), "y": round(w["y"], 1),
                                "r": round(w["r"], 1)} for w in self.shockwaves],
                "duo_open": self.duo_gate_open,
                "difficulty": round(self.difficulty, 2),
                "weapon_taken": self.weapon_taken,
                "rune_open": self.rune_open,
                "vents": [{"x": v["x"], "y": v["y"],
                           "on": (v["t"] % v["period"]) < v["on"]} for v in self.vents],
                "duo_hold": round(self._duo_hold / DUO_HOLD_TIME, 2) if not self.duo_gate_open else 1.0,
                "corpses": [{"kind": c["kind"], "x": c["x"], "y": c["y"],
                             "t": round(c["t"], 2), "max": c["max"], "dir": c["dir"]}
                            for c in self.corpses],
                "rocks": rocks,
                "portal": self.portal_active,
                "win": self.win,
                "wave": self.wave,
                "left": len([m for m in self.monsters if not m.tower]),
                "msg": self.msg or "",
                "events": list(self.events),
                "chat": list(self.chat[-8:]),
                "deaths": self.deaths,
                "kills": self.kills,
                "elapsed": round(self.elapsed, 1),
                "dusk": round(min(1.0, self.elapsed / DUSK_FULLNIGHT), 3),
                "night": self.elapsed >= self.nightfall_at(),
                "night_in": round(max(0.0, self.nightfall_at() - self.elapsed), 1),
                "stats": {
                    "reversals": self.stats["reversals"],
                    "dmg": [round(v, 1) for v in self.stats["dmg"]],
                    "max_region": self.stats["max_region"],
                    "blocks": self.stats["blocks"],
                    "chests": sum(1 for ch in self._chests if ch["opened"]),
                    "weapon": self.weapon_taken,
                },
                "beat_night": self.win and self.elapsed < self.nightfall_at(),
                "respawn": self._respawn_point,
                "map_w": MAP_W,
            }
        except Exception as e:
            write_log("状态打包异常: %r" % (e,))
            return {"t": 0, "type": "state", "players": {}, "arrows": [],
                    "monsters": [], "rifts": [], "plates": [], "pads": [], "rocks": [],
                    "hammers": [], "fall_rocks": [], "checkpoints": [], "chests": [],
                    "corpses": [], "fireballs": [], "shockwaves": [],
                    "duo_open": False, "duo_hold": 0.0,
                    "difficulty": 1.0,
                    "weapon_taken": False, "vents": [],
                    "rune_open": False,
                    "portal": False, "win": False, "wave": 1, "left": 0,
                    "msg": "", "events": [], "chat": [], "deaths": 0,
                    "kills": 0, "elapsed": 0.0, "respawn": None, "map_w": MAP_W}


class Arrow:
    __slots__ = ("aid", "x", "y", "vx", "vy", "ang", "t", "hit", "dmg")

    def __init__(self, aid, x, y, dx, dy, ang, dmg=1):
        self.aid = aid
        self.x = x
        self.y = y
        self.vx = dx * ARROW_SPEED
        self.vy = dy * ARROW_SPEED
        self.ang = ang
        self.t = 0.0
        self.hit = None
        self.dmg = dmg


# --------------------------------------------------------------------------
# 房主服务器线程（权威计算 + TCP广播）
# --------------------------------------------------------------------------
class Shared:
    """房主进程内 主线程 <-> 服务器线程 的共享区"""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = True
        self.q_host_input = queue.Queue(maxsize=128)
        self.q_host_chat = queue.Queue(maxsize=32)
        self.latest_state = None       # (bytes, time)
        self.client_connected = False
        self.client_ready = False
        self.client_lost = False
        self.status = "等待队友加入..."
        self.port = 0
        self.error = None

    def set_state(self, data_bytes, now):
        try:
            with self.lock:
                self.latest_state = (data_bytes, now)
        except Exception:
            pass

    def get_state(self):
        try:
            with self.lock:
                return self.latest_state
        except Exception:
            return None


class HostServer:
    """房主服务器：监听TCP、权威推演、向客户端广播状态。"""

    def __init__(self, engine, shared, port=5555, host_pid=0):
        self.engine = engine
        self.shared = shared
        self.port = port
        self.host_pid = host_pid          # 房主操控的角色（0 弓箭手 / 1 盾卫）
        self.server = None
        self.csock = None
        self.caddr = None
        self.buf = b""
        self.client_input = {}
        self.thread = None
        self.started = False        # 双方就位前世界保持冻结
        self.paused = False         # 房主暂停 -> 世界冻结并广播
        self.last_recv = 0.0        # 最近一次收到客户端任何包的时刻（心跳判定）
        self.HEARTBEAT_TIMEOUT = 3.0

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name="HostServer")
        self.thread.start()

    def stop(self):
        self.shared.running = False
        try:
            if self.csock:
                self.csock.close()
        except Exception:
            pass
        try:
            if self.server:
                self.server.close()
        except Exception:
            pass

    def _send(self, obj):
        """发送一帧状态。

        只有真正的连接错误才判掉线；发送超时/缓冲满（异地高延迟常见）
        只丢这一帧——下一帧 33ms 后还会再发，状态本来就是全量覆盖的。
        """
        try:
            if self.csock:
                self.csock.sendall(encode_pkt(obj))
                return True
        except (socket.timeout, BlockingIOError):
            # 网络一时拥塞：跳过本帧，不误判断线
            return False
        except Exception as e:
            write_log("发送到客户端失败: %r" % (e,))
            self._on_lost(str(e))
        return False

    def _on_lost(self, reason=""):
        try:
            if not self.shared.client_lost:
                self.shared.client_lost = True
                self.shared.status = "队友已断开连接：" + (reason or "网络异常")
            # 清掉上一位客户端的残留：不清的话新客户端接入后会带着旧输入跑、
            # 半包还会污染新的字节流
            self.client_input = {}
            self.buf = b""
            self.started = False
            self.shared.client_ready = False
            self.last_recv = 0.0
        except Exception:
            pass

    def _pump_client(self):
        """非阻塞读取客户端输入包"""
        try:
            if not self.csock:
                return
            r, _, _ = select.select([self.csock], [], [], 0)
            if not r:
                return
            data = self.csock.recv(65536)
            if not data:
                raise ConnectionError("连接被对方关闭")
            self.last_recv = time.monotonic()   # 任何字节都算"队友还在"
            self.buf += data
            while True:
                obj, self.buf = decode_pkt(self.buf)
                if obj is None:
                    break
                try:
                    if obj.get("type") == "ping":
                        pass                    # 心跳：last_recv 已在收包时更新
                    elif obj.get("type") == "ready":
                        self.shared.client_ready = True
                    elif obj.get("type") == "input":
                        self.client_input = sanitize_input(obj.get("input"))
                    elif obj.get("type") == "chat":
                        text = str(obj.get("text", ""))[:60]
                        if text.strip():
                            _nm = ROLE_NAME[1 - self.host_pid]
                            self.engine.push_chat(_nm + "(队友)", text.strip())
                            self.engine.msg = ""
                    elif obj.get("type") == "restart":
                        if not self.engine.win:
                            self.engine.reset("房主请求重新开始")
                except Exception as e:
                    write_log("客户端包处理异常: %r" % (e,))
        except (socket.timeout, BlockingIOError):
            pass
        except Exception as e:
            write_log("客户端读取异常: %r" % (e,))
            self._on_lost(str(e))

    def _drain_host_input(self):
        try:
            while True:
                try:
                    item = self.shared.q_host_input.get_nowait()
                except queue.Empty:
                    break
                try:
                    if item.get("type") == "input":
                        self._host_input = sanitize_input(item.get("input"))
                    elif item.get("type") == "start":
                        if self.shared.client_connected and not self.started:
                            self.started = True
                            self.paused = False
                            self.engine.reset("联机开局")
                            # reset 会把词条/难度清空，必须在之后恢复，
                            # 否则"词条没生效却照样按 1.5x1.3x1.2 加分"
                            self.engine.mods = set(item.get("mods") or ())
                            self.engine.difficulty = float(item.get("difficulty", 1.0) or 1.0)
                            self.shared.status = "冒险开始！"
                    elif item.get("type") == "pause":
                        self.paused = bool(item.get("on"))
                    elif item.get("type") == "chat":
                        text = str(item.get("text", ""))[:60]
                        if text.strip():
                            self.engine.push_chat(ROLE_NAME[self.host_pid] + "(房主)", text.strip())
                    elif item.get("type") == "restart":
                        if not self.engine.win:
                            self.engine.reset("房主请求重新开始")
                except Exception as e:
                    write_log("房主输入处理异常: %r" % (e,))
        except Exception as e:
            write_log("drain_host_input异常: %r" % (e,))

    def run(self):
        try:
            self._host_input = {}
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind(("", self.port))
            self.server.listen(2)
            self.server.settimeout(0.3)
            self.shared.port = self.port
            self.shared.status = "房间已创建，等待队友加入..."
            write_log("服务器监听端口 %d" % self.port)

            # --- 单一权威 tick 循环：等待队友期间也持续推演世界 ---
            accepted = False
            last = time.monotonic()
            tick = 0
            while self.shared.running:
                try:
                    # 尚未接受客户端时尝试接入（非阻塞式，不影响世界推演）
                    if not accepted:
                        try:
                            csock, addr = self.server.accept()
                            self.csock = csock
                            self.caddr = addr
                            # 不能设 0.0（完全非阻塞）：那样 sendall 写不进缓冲就抛
                            # BlockingIOError，会被当成掉线把整局冻住。给 50ms，
                            # 正常小包足够写完，真堵住也能被识别成 timeout 而非掉线。
                            self.csock.settimeout(0.05)
                            self.last_recv = time.monotonic()
                            accepted = True
                            self.shared.client_connected = True
                            self.shared.client_lost = False
                            self.shared.client_ready = False
                            self.paused = False
                            self.shared.status = "队友已加入！准备开始冒险！"
                            write_log("客户端接入: %r" % (addr,))
                            try:
                                self.csock.sendall(encode_pkt({"type": "hello",
                                                              "you": 1 - self.host_pid,
                                                              "port": self.port}))
                            except Exception as e:
                                write_log("hello发送失败: %r" % (e,))
                            self.engine.msg = "两名勇者已就位！合作闯关开始！"
                        except socket.timeout:
                            pass
                        except BlockingIOError:
                            pass
                        except Exception as e:
                            if self.shared.running:
                                write_log("接受客户端异常: %r" % (e,))
                                self.shared.error = "监听/接受连接失败：" + str(e)
                            break

                    # 心跳超时：半开连接（NAT 超时/网络切换）时 recv 不会返回空，
                    # 只靠它判掉线会无限复用最后一帧输入（角色自己一直走）
                    if accepted and not self.shared.client_lost and self.last_recv:
                        if time.monotonic() - self.last_recv > self.HEARTBEAT_TIMEOUT:
                            self._on_lost("心跳超时（%.0f 秒无数据）" % self.HEARTBEAT_TIMEOUT)

                    # 队友掉线：冻结世界、把席位留着，等新连接进来再继续
                    if accepted and self.shared.client_lost:
                        try:
                            if self.csock:
                                self.csock.close()
                        except Exception:
                            pass
                        self.csock = None
                        accepted = False
                        self.paused = True
                        self.shared.client_ready = False
                        self.shared.status = "队友掉线，世界已冻结，等待重连…"

                    now = time.monotonic()
                    dt = now - last
                    if dt < TICK_DT:
                        time.sleep(max(0.0005, TICK_DT - dt))
                        continue
                    last = now

                    # 收集输入：客户端 + 房主
                    self._pump_client()
                    self._drain_host_input()

                    # 等待室 / 暂停：世界完全冻结，只广播"当前帧"
                    # （修复：原实现等待队友时也在推演，等 60 秒能刷出二十多次死亡）
                    if not (self.started and not self.paused):
                        state = self.engine.pack()
                        state["lobby"] = not self.started
                        state["paused"] = self.paused and self.started
                        data = encode_pkt(state)
                        self.shared.set_state(data, now)
                        if accepted:
                            self._send(state)
                        last = now
                        time.sleep(max(0.0005, TICK_DT - (time.monotonic() - now)))
                        continue

                    inputs = {}
                    cp = 1 - self.host_pid
                    if self.client_input:
                        inputs[cp] = self.client_input
                    if self._host_input:
                        inputs[self.host_pid] = self._host_input

                    # 权威推演
                    self.engine.step(inputs, TICK_DT)
                    tick += 1

                    # 状态写入共享区（等待界面与游戏界面均可读取）
                    state = self.engine.pack()
                    state["lobby"] = False
                    state["paused"] = False
                    data = encode_pkt(state)
                    self.shared.set_state(data, now)

                    # 客户端已接入才走网络广播
                    if accepted:
                        self._send(state)

                    # 客户端断开 -> 保持状态供房主查看，不崩溃
                    if self.shared.client_lost:
                        self.shared.status = "队友已断开（ESC返回主菜单）"
                except Exception as e:
                    write_log("权威tick循环异常: %r" % (e,))
                    time.sleep(0.01)
        except Exception as e:
            write_log("服务器主循环异常: %r" % (e,))
            try:
                msg = str(e)
                if "Address already in use" in msg or "10048" in msg:
                    msg = "端口 %s 已被占用！请关闭其他游戏窗口后重试。" % self.port
                self.shared.error = "服务器异常：" + msg
            except Exception:
                pass
        finally:
            try:
                if self.csock:
                    self.csock.close()
            except Exception:
                pass
            try:
                if self.server:
                    self.server.close()
            except Exception:
                pass


# --------------------------------------------------------------------------
# 客户端网络（加入房间）
# --------------------------------------------------------------------------
class NetClient:
    """客户端：连接房主TCP，接收状态、发送输入与聊天。"""

    def __init__(self, addr, port, out_q, error_cb):
        self.addr = addr
        self.port = port
        self.out_q = out_q            # 主线程读: ('state', dict, time) / ('hello', dict)
        self.error_cb = error_cb
        self.sock = None
        self.buf = b""
        self.connected = False
        self.error = None
        self._send_lock = threading.Lock()
        self._last_ping = 0.0
        self._last_state_t = time.monotonic()
        self.STATE_TIMEOUT = 5.0        # 超过这么久没收到状态 -> 判定连接中断
        self.thread = threading.Thread(target=self._recv_loop, daemon=True, name="NetClientRecv")
        self.thread.start()

    def _recv_loop(self):
        try:
            self.sock = socket.create_connection((self.addr, self.port), timeout=10)
            self.sock.settimeout(3.0)
            self.connected = True
            # 一连上就报"准备"，房主的开始按钮会因此解锁
            try:
                self.sock.sendall(encode_pkt({"type": "ready"}))
            except Exception:
                pass
            while True:
                try:
                    data = self.sock.recv(65536)
                except socket.timeout:
                    # 空闲时发心跳，让房主知道我们还活着（NAT 也会因此保活）
                    try:
                        if time.monotonic() - self._last_ping > 1.0:
                            self.sock.sendall(encode_pkt({"type": "ping"}))
                            self._last_ping = time.monotonic()
                    except Exception:
                        pass
                    if time.monotonic() - self._last_state_t > self.STATE_TIMEOUT:
                        raise ConnectionError("%.0f 秒未收到服务器状态" % self.STATE_TIMEOUT)
                    continue
                if not data:
                    raise ConnectionError("连接被服务器关闭")
                self.buf += data
                while True:
                    obj, self.buf = decode_pkt(self.buf)
                    if obj is None:
                        break
                    if obj.get("type") == "hello":
                        try:
                            self.out_q.put(("hello", obj, time.monotonic()))
                        except Exception:
                            pass
                    elif obj.get("type") == "state":
                        # 收到状态就刷新超时计时（否则空闲时会误判"5 秒无响应"）
                        self._last_state_t = time.monotonic()
                        try:
                            self.out_q.put(("state", obj, time.monotonic()))
                        except Exception:
                            pass
        except Exception as e:
            self.error = str(e)
            try:
                self.connected = False
                if self.sock:
                    self.sock.close()
            except Exception:
                pass
            try:
                self.error_cb(self.error)
            except Exception:
                pass

    def send(self, obj):
        try:
            if not self.connected or not self.sock:
                return
            with self._send_lock:
                self.sock.sendall(encode_pkt(obj))
        except Exception as e:
            self.error = str(e)
            try:
                self.connected = False
                self.sock.close()
            except Exception:
                pass
            try:
                self.error_cb(self.error)
            except Exception:
                pass

    def send_input(self, inp):
        self.send({"type": "input", "input": inp})

    def send_chat(self, text):
        self.send({"type": "chat", "text": text})

    def close(self):
        try:
            self.connected = False
            if self.sock:
                self.sock.close()
        except Exception:
            pass


LAN_PORT = 5556


def lan_announce_loop(stop_event, room_name, port):
    """房主：向局域网广播房间信息，客户端可自动发现、免手输 IP。"""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        pkt = json.dumps({"type": "lan_announce", "room": room_name, "port": int(port)}).encode("utf-8")
        while not stop_event.is_set():
            try:
                sock.sendto(pkt, ("255.255.255.255", LAN_PORT))
            except Exception:
                pass
            time.sleep(1.0)
    except Exception as e:
        write_log("LAN 广播异常: %r" % (e,))
    finally:
        try:
            if sock:
                sock.close()
        except Exception:
            pass


def lan_listen(out_q, stop_event):
    """客户端：监听局域网房间广播，把 (room, ip, port) 投进队列。"""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", LAN_PORT))
        except Exception:
            pass
        sock.settimeout(0.4)
        while not stop_event.is_set():
            try:
                data, addr = sock.recvfrom(1024)
                obj = json.loads(data.decode("utf-8", "ignore"))
                if obj.get("type") == "lan_announce":
                    out_q.put((obj.get("room", "局域网房间"), addr[0], int(obj.get("port", 5555))))
            except socket.timeout:
                continue
            except Exception:
                continue
    except Exception as e:
        write_log("LAN 监听异常: %r" % (e,))
    finally:
        try:
            if sock:
                sock.close()
        except Exception:
            pass


# --------------------------------------------------------------------------
# 单人模式 AI 控制器（AI 托管的非当前操控角色）
# --------------------------------------------------------------------------
def _make_ai_input_raw(ai_pid, eng, other_pid):
    """生成AI角色输入。ai_pid: AI控制角色(0弓箭手/1盾卫), other_pid: 玩家操控角色。

    AI策略：
      盾卫  -> 清地面怪 > 踩压力机关 > 低血格挡 > 跟随玩家
      弓箭手-> 射飞行怪 > 击碎挡路岩石墙 > 保持距离 > 跟随玩家
      传送门激活后AI会主动走到门口与玩家汇合。
    地图跳板跨越：A断崖(1120~1150起跳踩板可到B区)、B高台(1680~1850起跳
    踩板可弹上终点平台)，AI起跳命中率通过几何推演保证。
    """
    safe = {"left": False, "right": False, "up": False, "down": False,
            "shoot": False, "sword": False, "block": False,
            "dash": False, "interact": False,
            "mx": 0.0, "my": 0.0}
    try:
        me = eng.players[ai_pid]
        other = eng.players[other_pid]
        inp = {
            "left": False, "right": False, "up": False, "down": False,
            "shoot": False, "sword": False, "block": False,
            "dash": False, "interact": False,
            "mx": float(other["x"]), "my": float(other["y"]),
        }
        px, py = me["x"], me["y"]

        def solid(cx, cy):
            return eng._solid_at(int(cx), int(cy))

        # 飞行怪贴脸时先还击（否则 AI 会被蝙蝠一直啄而站着不动）
        if ai_pid == 0:
            near_fly, nd = None, 1e18
            for m in eng.monsters:
                if m.kind == "fly":
                    d = abs(m.x - px) + abs(m.y - py)
                    if d < nd:
                        nd, near_fly = d, m
            if near_fly is not None and nd < 380:
                inp["shoot"] = True
                inp["mx"] = float(near_fly.x)
                inp["my"] = float(near_fly.y - 10)

        # ---------- 深坑刀刺阶板跨越（优先于岩浆坑：防止AI跳入无底深坑）----------
        sp = eng._spike_platform
        pit_l = PIT_COLS[0] * TILE
        pit_r = (PIT_COLS[1] + 1) * TILE
        # 深坑位于岩浆坑右侧：AI 必须先跨越岩浆坑，到达右岸后才处理刀刺阶板跨越
        past_lava = px > LAVA_RIGHT_PX - 40
        # 是否正骑在刀刺阶板上（被上下携带，随板沉浮）
        on_plate = (me["on_ground"] and abs(py - sp["y"]) < 12 and
                    sp["x"] - 4 <= px <= sp["x"] + SPIKE_PAD_W + 4)
        crossing = None
        # 条件放宽：允许 AI 走出左/右岸并踏上阶板（右缘仍未超过阶板右端前都算过坑方向），
        # 否则当 AI 停在坑口边缘(px≈pit_l-14)时条件失效，被 advance 深坑刹车逻辑挡住永远上不了板
        need_left = px - PLAYER_W / 2 > pit_r - SPIKE_PAD_W + 6 and other["x"] < pit_l + 30
        need_right = px + PLAYER_W / 2 < pit_l + SPIKE_PAD_W - 6 and other["x"] > pit_r - 30
        if past_lava:
            if on_plate:
                # 骑板中：根据队友方向确定过坑方向，随板升到坑口时走下阶板
                crossing = "right" if other["x"] > px else "left"
            elif need_right:
                crossing = "right"
            elif need_left:
                crossing = "left"
        danger_near = any(m.kind == "ground" and abs(m.x - px) < 320
                          for m in eng.monsters)
        if crossing is not None and not danger_near:
            # 已骑在刀刺阶板上（被上下携带，随板沉浮）
            if on_plate:
                # 板面经过坑口高度时朝目标岸走；其余时间待在板中央，避免踩空
                if 556 <= sp["y"] <= 666:
                    if crossing == "right":
                        inp["right"] = True
                    else:
                        inp["left"] = True
                else:
                    center = sp["x"] + SPIKE_PAD_W / 2.0
                    if px < center - 18:
                        inp["right"] = True
                    elif px > center + 18:
                        inp["left"] = True
                return inp
            # 岸上：走到坑口边缘，等刀刺阶板升到与地面齐平再走上阶板
            if crossing == "right" and px < pit_l + 14:
                if me["on_ground"] and abs(py - 19 * TILE) < 10:
                    if px < pit_l - 46:
                        inp["right"] = True
                    elif sp["y"] <= 19 * TILE + 4:
                        inp["right"] = True   # 阶板已到顶盖住坑口，直接走上
                    else:
                        inp["right"] = False  # 站在坑口等板，不乱跳
                    return inp
                inp["right"] = True
                return inp
            if crossing == "left" and px > pit_r - 14:
                if me["on_ground"] and abs(py - 19 * TILE) < 10:
                    if px > pit_r + 46:
                        inp["left"] = True
                    elif sp["y"] <= 19 * TILE + 4:
                        inp["left"] = True
                    else:
                        inp["left"] = False
                    return inp
                inp["left"] = True
                return inp

        # ---------- 岩浆坑跨越（借助移动阶板）----------
        if px < LAVA_RIGHT_PX - 20 and other["x"] > 78 * TILE:
            if me["on_ground"] and me["y"] < 19 * TILE - 20:
                # 骑板中被携带：板近右岸时向右走出
                for plate in eng._m_plates.values():
                    if abs(px - (plate["x"] + M_PAD_W / 2)) < M_PAD_W + 4:
                        if plate["x"] + M_PAD_W >= 80 * TILE - 20:
                            inp["right"] = True
                        return inp
                return inp
            if px < 62 * TILE:
                inp["right"] = True
                return inp
            if not me["on_ground"]:
                # 空中或落入岩浆：等板经过时跳上，否则继续向右
                if me["y"] > 19 * TILE + 5:
                    for plate in eng._m_plates.values():
                        if plate["x"] - 10 <= px + 14 <= plate["x"] + M_PAD_W + 10 and plate["dx"] >= -30:
                            inp["up"] = True
                            return inp
                inp["right"] = True
                return inp
            # 站在左岸：等板靠近且向右折返时起跳
            ready = None
            for plate in eng._m_plates.values():
                if plate["x"] <= 2040 and plate["dx"] >= -5:
                    ready = plate
                    break
            if ready is not None:
                inp["up"] = True
                if px < 2010:
                    inp["right"] = True
                return inp
            if px < 2010:
                inp["right"] = True
            return inp

        # ---------- 前进辅助：目标移动 + 智能跳跃/跳板跨越 ----------
        def advance(tx, ty, move=True):
            dx = tx - px
            if abs(dx) < 12:
                return
            d = 1 if dx > 0 else -1
            if move:
                if d > 0:
                    inp["right"] = True
                else:
                    inp["left"] = True
            # 地刺带：提前起跳越过（熔炉长廊）
            if me["on_ground"] and abs(py - 19 * TILE) < 12:
                for (c0, c1) in SPIKE_STRIPS:
                    sx0, sx1 = c0 * TILE, (c1 + 1) * TILE
                    ahead = (sx0 - px) if d > 0 else (px - sx1)
                    if -24 < ahead < 86:
                        inp["up"] = True
                        break
            # 台阶：前方 1~2 格处比脚底高 1~4 格就自动起跳。
            # 没有这段时，队友上不了祭坛（64px 台阶），会卡在台阶底下一直站着。
            if me["on_ground"] and not inp["up"]:
                for look in (PLAYER_W * 0.5 + 8, PLAYER_W * 0.5 + 22):
                    acx = int((px + d * look) // TILE)
                    foot_row = int((py - 2) // TILE)
                    heading = False
                    for up in range(1, 5):
                        if eng._solid_at(acx, foot_row - up):
                            heading = True
                            break
                    if heading:
                        # 头顶要留得出一格空间，否则跳了也是撞天花板
                        if not eng._solid_at(int(px // TILE), foot_row - 1):
                            inp["up"] = True
                        break
            # 跳板跨越（仅在主地面层触发）
            if me["on_ground"] and abs(py - 19 * TILE) < 8:
                za = [p for p in eng.pads if p[5] == "A"]
                zb = [p for p in eng.pads if p[5] == "B"]
                # A断崖：地面A右缘起跳 -> 落板37-39 -> 弹射过崖
                if za and px <= 1408 and 1120 <= px <= 1150:
                    inp["up"] = True
                    return
                # B高台：地面B起跳 -> 落板57-61 -> 弹射上终点平台
                if zb and 60 * TILE < tx and 1680 <= px <= 1850:
                    inp["up"] = True
                    return
                # 越过起跳窗口却还没上平台 -> 退回重跳（最多2次收敛）
                if zb and 60 * TILE < tx and 1850 < px <= 2000:
                    inp["right"] = False
                    inp["left"] = True
                    return
            # 前方障碍判定（小墙/小坑/高台）
            # 注意：py 是"脚底"，直接用 py//TILE 会落到脚下那格地面上，
            # 导致 AI 永远认为自己面前有墙而原地狂跳。这里取身体中段所在行。
            front = px + d * (PLAYER_W / 2 + 4)
            col = int(front // TILE)
            row = int((py - PLAYER_H * 0.5) // TILE)
            wall = solid(col, row) or solid(col, row - 1)

            # 深坑（岩浆右侧列90~93无底坠亡坑）：前方见不到底 -> 绝不跳跃，刹住等刀刺阶板
            if not wall:
                for ck in range(col + d, col + d + 4):
                    if ck < 0 or ck >= MAP_W:
                        break
                    if PIT_COLS[0] <= ck <= PIT_COLS[1]:
                        has_floor = False
                        for ry in range(row + 1, min(MAP_H - 1, row + 5)):
                            if solid(ck, ry):
                                has_floor = True
                                break
                        if not has_floor:
                            # 站在坑口边缘：刹车等待，绝不跳入深坑（顶部逻辑负责骑板跨越）
                            if me["on_ground"]:
                                inp["right"] = False
                                inp["left"] = False
                            return
            pit = False
            if not wall:
                for dd in (1, 2):
                    if not solid(col + d * dd, row + 1):
                        pit = True
                        break
            high = ty < py - 45 and abs(tx - px) > 30
            if me["on_ground"]:
                if wall or pit or high:
                    inp["up"] = True
            else:
                # 空中：第一跳已用过(jumps==1)且前方障碍仍未越过 → 二段跳继续翻越
                if me["jumps"] == 1 and (wall or pit or high):
                    inp["up"] = True

        # ---------- 传送门激活：AI主动走到门口 ----------
        if eng.portal_active and not eng.win:
            target_x = PORTAL_RECT[0] + (120 if ai_pid == 0 else 60)
            advance(target_x, 15 * TILE)
            return inp

        monsters = eng.monsters

        # ---------- 补给箱：低血时靠近并开启 ----------
        if me["hp"] < me["maxhp"] * 0.72:
            for ch in eng._chests:
                if ch["opened"]:
                    continue
                dd = abs(ch["x"] - px)
                # 人类玩家就在箱子旁边时不要抢着开，避免"我按 E 却没反应"
                if abs(other["x"] - ch["x"]) < 150:
                    continue
                if dd < 160 and abs(py - 19 * TILE) < 96:
                    if dd < CHEST_RANGE - 8:
                        inp["interact"] = True
                    else:
                        inp["right"] = ch["x"] > px
                        inp["left"] = ch["x"] < px
                    return inp

        # ================= AI 盾卫 =================
        if ai_pid == 1:
            # 1) 攻击范围内地面怪
            best, bd = None, 1e18
            for m in monsters:
                if m.kind not in ("ground", "boss"):
                    continue
                # 剑的判定盒只有 SWORD_RANGE(56) 高：不同楼层的怪根本够不着。
                # 不加这条，AI 会站在平台上"追击"正下方 190px 的怪 —— 横向距离为 0，
                # advance() 不动，于是原地僵住、既不挥剑也不跟随玩家。
                if abs(m.y - py) > 64:
                    continue
                d = abs(m.x - px) + abs(m.y - py)
                if d < bd:
                    bd, best = d, m
            if best is not None and bd < SWORD_RANGE * 1.3:
                if bd < 70 and abs(best.x - px) < 90:
                    inp["sword"] = True
                # 追击移动也走导航图：怪在隔壁小沟对面时能绕/跳过去，
                # 而不是一头扎进沟里；够近就站住挥剑
                if not _nav_follow(eng, ai_pid, inp, best.x, best.y):
                    advance(best.x, best.y)
                return inp
            # 2) 主动追击近距地面怪
            if best is not None and bd < 430:
                if not _nav_follow(eng, ai_pid, inp, best.x, best.y):
                    advance(best.x, best.y)
                if bd < 76:
                    inp["sword"] = True
                return inp
            # 3) 未激活压力机关 -> 上前踩（队友被断崖挡住时，跨图也要回去踩）
            for pl in eng.plates:
                if pl["active"]:
                    continue
                try:
                    cfg = PLATE_CONFIGS[[p["id"] for p in eng.plates].index(pl["id"])]
                except Exception:
                    continue
                pcx = cfg["cx"] * TILE + TILE
                need = (1040 < other["x"] < 1420) or (1040 < px < 1420)
                if need and abs(py - 19 * TILE) < TILE * 2:
                    advance(pcx, 19 * TILE)
                    return inp
            # 4) 低血且近处有怪 -> 举盾格挡
            if me["hp"] < me["maxhp"] * 0.45 and any(
                    m.kind in ("ground", "boss") and abs(m.x - px) < 150 for m in monsters):
                inp["block"] = True
            # 5) 跟随玩家：优先走导航图（能上塔、能跨楼层），走不通再退回启发式
            if _nav_follow(eng, ai_pid, inp, other["x"], other["y"]):
                return inp
            advance(other["x"], other["y"])
            return inp

        # ================= AI 弓箭手 =================
        # 只锁定箭真正能伤害的目标（fly/caster/boss）。
        # 旧版找不到飞行/施法者会回退到"任意怪"，而箭对 ground 无效 ->
        # AI 对着地面怪原地空射（shoot 按住不松，连触发都没有），也不跟随。
        best, bd = None, 1e18
        for m in monsters:
            if m.kind in ("fly", "caster", "boss"):
                d = abs(m.x - px) + abs(m.y - py)
                if d < bd:
                    bd, best = d, m

        # 岩石墙未破且需要通行 -> 优先射墙（先打通行19的通道）
        wall_rock = None
        for (rx, ry), hp in sorted(eng.rocks.items(), key=lambda kv: (-kv[0][1], kv[0][0])):
            if hp > 0 and rx in (54, 55) and ry >= 18:
                wall_rock = ((rx + 0.5) * TILE, (ry + 0.5) * TILE)
                break
        need_cross = other["x"] > 50 * TILE or px > 50 * TILE
        if wall_rock and need_cross:
            if px < 46 * TILE:
                advance(47 * TILE, py)
            else:
                inp["shoot"] = True
                inp["mx"], inp["my"] = wall_rock
                if wall_rock[0] < px - 20:
                    inp["left"] = True
                elif wall_rock[0] > px + 20:
                    inp["right"] = True
            return inp

        # 攻击射程内怪物（保持安全距离）
        if best is not None and bd < 640:
            inp["shoot"] = True
            inp["mx"] = best.x
            inp["my"] = best.y - (10 if best.kind == "fly" else (20 if best.kind == "caster" else 16))
            # 移动方向：近了后退、远了逼近。但后退方向脚下没地板就不走 ——
            # 之前弓箭手会一边退一边射，直接退下悬崖摔死（两人共用一条命）。
            if bd < 120:
                dmv = 1 if best.x < px else -1
            else:
                dxm = best.x - px
                dmv = (1 if dxm > 0 else -1) if abs(dxm) > 50 else 0
            if dmv:
                # 安全落点判定：① 和当前地面差不多高的地板（退进 3 格深的坑里
                # 等于被堵死）② 不在岩浆范围内（弓箭手曾边退边射退进岩浆烧死）
                try:
                    _xa = px + dmv * 34
                    _c = int(_xa // TILE)
                    _fr = int(py // TILE)
                    _has_floor = any(eng._solid_at(_c, r) for r in range(_fr, _fr + 3))
                    if LAVA_LEFT_PX - 16 <= _xa <= LAVA_RIGHT_PX + 16:
                        _has_floor = False
                except Exception:
                    _has_floor = True
                if _has_floor:
                    inp["right"] = dmv > 0
                    inp["left"] = dmv < 0
            return inp

        # 跟随玩家
        if _nav_follow(eng, ai_pid, inp, other["x"], other["y"]):
            return inp
        advance(other["x"], other["y"])
        return inp
    except Exception:
        return dict(safe)


AI_COMMANDS = ("follow", "guard", "focus")
AI_CMD_LABEL = {"follow": "跟随", "guard": "守点", "focus": "集火"}


def _nav_follow(eng, ai_pid, inp, tx, ty):
    """沿导航图走向目标（知道楼层、藤蔓、大跳）。

    返回 True 表示已写入移动输入；图上没有路（比如 A 断崖必须先踩机关
    生成跳板）就返回 False，让调用方退回原来的启发式。
    """
    try:
        g = eng._nav_graph()
        me = eng.players[ai_pid]
        p = g.path(me["x"], me["y"], tx, ty)
        if not p or len(p) < 2:
            # 目标就在头顶、或已经跳到半空（路径塌缩成单个节点）时，
            # 要继续按住跳让二段跳补高度。否则：单次跳只有 90px，
            # 3 格台阶(96px)差 6px 上不去，AI 会永远卡在坑底/台阶下。
            if ty < me["y"] - 20 and abs(tx - me["x"]) < 90:
                if abs(tx - me["x"]) > 10:
                    inp["right" if tx > me["x"] else "left"] = True
                if me.get("jumps", 0) < 2:
                    inp["up"] = True
                return True
            return False
        node, kind = p[1]
        nx, ny = g.nodes[node]
        dx = nx - me["x"]
        hanging = me.get("vine", -1) >= 0
        if hanging:
            # 挂在藤蔓上：滑动方向按"下一节点在上方还是下方"决定，
            # 而不是按水平朝向 —— 近垂直的藤蔓（塔里那两根）水平差只有几像素，
            # 按水平方向会让 AI 顺着藤蔓滑反方向、永远爬不上去。
            v = eng.vines[me["vine"]]
            higher_at_t1 = v[3] < v[1]          # t=1 端是否更高
            # 用"最终目标"的高度判断该往上还是往下，而不是"下一个节点"：
            # 下一个节点常常是脚下的落点（比如 (33,19)），会让方向判反，
            # AI 挂在藤上原地不动。
            going_up = ty < me["y"] - 8
            slide_right = (going_up == higher_at_t1)
            inp["right"] = slide_right
            inp["left"] = not slide_right
            inp["up"] = False                   # 按着跳会松手
            return True
        if abs(dx) > 10:
            inp["right" if dx > 0 else "left"] = True
        if kind in ("jump", "gap", "leap"):
            if me["on_ground"] and abs(dx) < 70:
                inp["up"] = True
            elif me.get("jumps") == 1 and abs(dx) < 40:
                inp["up"] = True          # 二段跳补高度
        if kind == "vine" and me["on_ground"] and abs(dx) < 34:
            inp["up"] = True              # 走到藤蔓脚下时起跳抓索
        return True
    except Exception:
        return False


def make_ai_input(ai_pid, eng, other_pid, cmd="follow"):
    """AI 输入入口：在原始策略外层再加一道"深坑护栏"。

    原始策略在附近有怪物时会切进战斗分支，可能无视坑口直接走进深渊；
    这里统一在最后做一次安全裁剪：当刀刺阶板还没升到与地面齐平时，
    禁止 AI 从岸边朝坑内迈步（骑在板上或已越过坑时不受限制）。
    """
    inp = _make_ai_input_raw(ai_pid, eng, other_pid)
    try:
        me = eng.players[ai_pid]
        if cmd == "focus" and eng.monsters:
            tgt = min(eng.monsters, key=lambda m: abs(m.x - me["x"]) + abs(m.y - me["y"]))
            inp["right"] = tgt.x > me["x"] + 12
            inp["left"] = tgt.x < me["x"] - 12
            if ai_pid == 0:
                inp["shoot"] = True
                inp["mx"] = float(tgt.x)
                inp["my"] = float(tgt.y - 16)
            else:
                inp["sword"] = abs(tgt.x - me["x"]) < 76
                inp["block"] = False
        elif cmd == "guard":
            # 守在压力机关上；闸门未开时优先去"人类没站的那块双人机关"
            px = None
            try:
                if not eng.duo_gate_open:
                    _hx = eng.players[other_pid]["x"]
                    # 人类已经站在某块双人机关上 = 明确在叫你去补位，这时不该
                    # 因为"离得远"就改去守符文（符文对双人闸门毫无用处）
                    _human_holding = any(abs(_hx - (c * TILE + 16)) < DUO_PLATE_RANGE
                                         for c in DUO_PLATE_COLS)
                    for c in DUO_PLATE_COLS:
                        cx = c * TILE + 16
                        # 否则只在闸门附近补位，避免 AI 横穿半张地图
                        if abs(_hx - cx) > 70 and (abs(me["x"] - cx) < 520 or _human_holding):
                            px = cx
                            break
            except Exception:
                px = None
            if px is None:
                # 共鸣门：双人机关没匹配到才去守符文（若人类没在站，且离得近）
                try:
                    if not eng.rune_open:
                        rx = RUNE_COL * TILE + 16
                        if abs(eng.players[other_pid]["x"] - rx) > 50 and abs(me["x"] - rx) < 460:
                            px = rx
                except Exception:
                    pass
            if px is None:
                try:
                    px = PLATE_CONFIGS[0]["cx"] * TILE + 12
                except Exception:
                    px = None
            if px is not None:
                inp["right"] = px > me["x"] + 10
                inp["left"] = px < me["x"] - 10
                inp["shoot"] = False
                inp["sword"] = False
                # 守点模式接管了左右键，原始策略的"翻越地形"跳跃就不再为它工作，
                # 于是遇到台阶会一直贴着墙走。这里自己判一次：前方胸口高度有墙就跳。
                if inp["right"] or inp["left"]:
                    ahead = me["x"] + (24 if inp["right"] else -24)
                    try:
                        blocked = eng._solid_at(int(ahead // TILE), int((me["y"] - 24) // TILE))
                    except Exception:
                        blocked = False
                    if blocked:
                        inp["up"] = True
                # 站到机关上必须"钉住"：原始策略为了翻越地形会一直按跳/冲刺，
                # 而双人闸门和守门符文都要求连续踩住 0.45s —— 跳一下就清零，
                # 表现为 AI 在机关上原地弹跳、闸门永远打不开（单人模式卡死）。
                if abs(me["x"] - px) < 26:
                    inp["up"] = False
                    inp["dash"] = False
                # 把守点位置告知引擎：归队兜底（_update_ai_rescue）看到 AI
                # 停在守点附近就不再判定为"卡死"强制传送
                try:
                    eng.ai_guard_pos = (float(px), float(me["y"]))
                except Exception:
                    pass
                if ai_pid == 1:
                    inp["block"] = any(abs(m.x - me["x"]) < 110 and m.kind in ("ground", "boss")
                                       for m in eng.monsters)
    except Exception:
        pass
    try:
        # 烈焰机关回避：AI 之前会径直走到喷火口上站桩，被烧到死（塔里尤其明显，
        # 而两人共用一条命 -> 玩家被反复拖回检查点）。只在"正在喷火且已经站进
        # 火柱范围"时横向挪开，不干扰正常赶路。
        me = eng.players[ai_pid]
        for v in getattr(eng, "vents", ()):
            if (v["t"] % v["period"]) < v["on"] and abs(me["x"] - v["x"]) < VENT_RANGE_X + 8:
                # 站左边就往左撤，站右边就往右撤（方向别写反）
                if me["x"] < v["x"]:
                    inp["left"], inp["right"] = True, False
                else:
                    inp["right"], inp["left"] = True, False
                inp["up"] = False
                break

        # 岩浆逃生：泡在岩浆里时任何其他行为（后撤/追击/跟随）都只会让人继续扣血。
        # 往最近的坑缘走，一出去就恢复正常决策。
        if LAVA_LEFT_PX <= me["x"] <= LAVA_RIGHT_PX and me["y"] >= LAVA_SURFACE_Y - 40:
            near_left = (me["x"] - LAVA_LEFT_PX) < (LAVA_RIGHT_PX - me["x"])
            inp["left"], inp["right"] = near_left, not near_left
            inp["up"] = False
            return inp
    except Exception:
        pass
    try:
        me = eng.players[ai_pid]
        px, py = me["x"], me["y"]
        sp = eng._spike_platform
        pit_l = PIT_COLS[0] * TILE
        pit_r = (PIT_COLS[1] + 1) * TILE
        on_plate = (abs(py - sp["y"]) < 14 and
                    sp["x"] - 6 <= px <= sp["x"] + SPIKE_PAD_W + 6)
        if not on_plate and me["on_ground"] and sp["y"] < 19 * TILE - 6:
            if pit_l - 70 < px < pit_l and inp.get("right"):
                inp["right"] = False
            elif pit_r < px < pit_r + 70 and inp.get("left"):
                inp["left"] = False
    except Exception:
        pass
    # 射击是"按下沿"触发：AI 策略层每帧都输出 shoot=True 的话，
    # 引擎只认第一帧，之后一直空按——弓手 AI 会看起来"举着弓不发箭"。
    # 用固定节奏制造按下沿（11 帧 ≈ 0.18s，接近弓的射速）。
    try:
        if inp.get("shoot") and (eng.tick % 11) == 0:
            inp["shoot"] = False
    except Exception:
        pass
    return inp


# --------------------------------------------------------------------------
# 核心自检（无需图形/网络，验证引擎逻辑稳定）
# --------------------------------------------------------------------------
def core_selftest():
    print("[核心自检] 引擎逻辑测试开始...")
    eng = GameEngine()
    inputs = {}
    # 模拟 3 秒混合输入
    for i in range(120):
        inputs.clear()
        inputs[0] = {"right": i % 2 == 0, "shoot": i % 5 == 0,
                     "mx": 2000.0, "my": 200.0}
        inputs[1] = {"right": i % 2 == 1, "sword": i % 6 == 0,
                     "block": i % 9 == 0}
        eng.step(inputs, TICK_DT)
        st = eng.pack()
        assert st["type"] == "state"
    print("[核心自检] 引擎 120 tick 无异常，状态打包正常。")
    print("[核心自检] 弓箭: %d, 怪物: %d, 玩家血量: %s" %
          (len(eng.arrows), len(eng.monsters),
           {k: v["hp"] for k, v in eng.players.items()}))
    print("[核心自检] 通过。")


if __name__ == "__main__":
    core_selftest()