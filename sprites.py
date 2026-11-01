# -*- coding: utf-8 -*-
"""
sprites.py —— 角色 / 怪物像素美术（程序化生成，带描边、明暗、动画帧）
============================================================================
相比旧版 26x44 的"色块狗"，本模块用像素级建模 + 自动描边 + 顶光/底部阴影
生成 36x52 的角色与 34x30 的怪物，并带多帧动画：

    角色：idle(2) / run(4) / jump / fall / block / hurt
    怪物：ground(2) / fly(2)

所有结果在首次调用时构建并缓存，运行时零开销。
"""
import math

import numpy as np
import pygame

W, H = 36, 52
MW, MH = 34, 30
FW, FH = 36, 28

OUTLINE = (22, 18, 26)

# 每个职业 3 套外观（选人界面可切换）。pal 的键和下面 _character 里用的一致：
#   1 皮肤 / 2 深布 / 3 主色 / 4 主色暗部 / 5 金属或金饰 / 6 眼
#   7 嘴鼻 / 8 皮革 / 9 裤子 / 10 靴子 / 11 亮金属或缨
SKINS = {
    "archer": [
        {"name": "林间游侠", "pal": {
            1: (234, 198, 160), 2: (78, 66, 60), 3: (86, 150, 134),
            4: (44, 92, 82), 5: (226, 188, 104), 6: (34, 36, 44),
            7: (150, 96, 84), 8: (128, 88, 54), 9: (96, 84, 72),
            10: (74, 58, 48), 11: (206, 214, 226)}},
        {"name": "赤羽斥候", "pal": {
            1: (238, 200, 158), 2: (74, 58, 52), 3: (176, 74, 62),
            4: (108, 40, 38), 5: (236, 176, 96), 6: (30, 28, 34),
            7: (152, 92, 78), 8: (96, 62, 42), 9: (86, 70, 60),
            10: (62, 46, 40), 11: (244, 216, 168)}},
        {"name": "霜原猎手", "pal": {
            1: (242, 216, 190), 2: (72, 78, 92), 3: (96, 152, 194),
            4: (52, 92, 128), 5: (214, 226, 240), 6: (32, 40, 56),
            7: (150, 108, 100), 8: (108, 96, 84), 9: (104, 108, 120),
            10: (58, 62, 74), 11: (236, 244, 255)}},
    ],
    "guard": [
        {"name": "熔炉卫兵", "pal": {
            1: (234, 198, 160), 2: (58, 60, 70), 3: (94, 108, 128),
            4: (54, 64, 82), 5: (198, 206, 220), 6: (30, 32, 40),
            7: (150, 96, 84), 8: (122, 78, 50), 9: (84, 88, 102),
            10: (62, 54, 50), 11: (168, 62, 58)}},
        {"name": "铁誓骑士", "pal": {
            1: (236, 202, 166), 2: (48, 50, 58), 3: (74, 78, 92),
            4: (40, 44, 54), 5: (226, 200, 120), 6: (28, 30, 38),
            7: (150, 96, 84), 8: (96, 66, 42), 9: (66, 68, 78),
            10: (48, 42, 40), 11: (236, 240, 248)}},
        {"name": "岩甲守备", "pal": {
            1: (228, 190, 150), 2: (70, 62, 52), 3: (150, 120, 72),
            4: (96, 74, 44), 5: (206, 184, 128), 6: (34, 30, 26),
            7: (148, 92, 76), 8: (110, 76, 46), 9: (108, 94, 76),
            10: (70, 56, 44), 11: (120, 96, 64)}},
    ],
}

# 当前选中的外观索引（选人界面 / 存档设置里改）
SKIN = {"archer": 0, "guard": 0}


def skin_list(kind):
    return SKINS["archer" if kind == "archer" else "guard"]


def skin_name(kind, idx=None):
    lst = skin_list(kind)
    i = SKIN["archer" if kind == "archer" else "guard"] if idx is None else idx
    return lst[max(0, min(len(lst) - 1, i))]["name"]


def skin_palette(kind, idx=None):
    lst = skin_list(kind)
    i = SKIN["archer" if kind == "archer" else "guard"] if idx is None else idx
    return lst[max(0, min(len(lst) - 1, i))]["pal"]



def _blank(w, h):
    return np.zeros((h, w), dtype=np.int16)


def _rect(g, x0, y0, x1, y1, pid):
    x0 = max(0, int(x0)); y0 = max(0, int(y0))
    x1 = min(g.shape[1] - 1, int(x1)); y1 = min(g.shape[0] - 1, int(y1))
    if x1 >= x0 and y1 >= y0:
        g[y0:y1 + 1, x0:x1 + 1] = pid


def _ellipse(g, cx, cy, rx, ry, pid):
    h, w = g.shape
    for y in range(max(0, int(cy - ry)), min(h, int(cy + ry) + 1)):
        for x in range(max(0, int(cx - rx)), min(w, int(cx + rx) + 1)):
            dx = (x - cx) / max(0.6, rx)
            dy = (y - cy) / max(0.6, ry)
            if dx * dx + dy * dy <= 1.0:
                g[y, x] = pid


def _tri(g, pts, pid):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    x0, x1 = int(min(xs)), int(max(xs))
    y0, y1 = int(min(ys)), int(max(ys))
    for y in range(max(0, y0), min(g.shape[0] - 1, y1) + 1):
        for x in range(max(0, x0), min(g.shape[1] - 1, x1) + 1):
            s = []
            for i in range(3):
                ax, ay = pts[i]
                bx, by = pts[(i + 1) % 3]
                s.append((bx - ax) * (y - ay) - (by - ay) * (x - ax))
            if (all(v >= -0.01 for v in s) or all(v <= 0.01 for v in s)):
                g[y, x] = pid


def _poly(g, pts, pid):
    """扫描线填充任意凸/凹多边形（Boss 的梯形躯干、不规则甲片用）。"""
    ys = [p[1] for p in pts]
    y0 = max(0, int(min(ys)))
    y1 = min(g.shape[0] - 1, int(max(ys)))
    for y in range(y0, y1 + 1):
        xs = []
        n = len(pts)
        for i in range(n):
            xa, ya = pts[i]
            xb, yb = pts[(i + 1) % n]
            if (ya <= y < yb) or (yb <= y < ya):
                xs.append(xa + (y - ya) * (xb - xa) / float(yb - ya))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            for x in range(max(0, int(xs[i])), min(g.shape[1] - 1, int(xs[i + 1])) + 1):
                g[y, x] = pid


def _render(g, pal, outline=True, shade=True):
    """把部件矩阵渲染成 Surface：自动外描边 + 顶部提亮 + 底部压暗。

    用 numpy 整块运算（原来逐像素 set_at，2 倍分辨率下会拖慢启动）。
    """
    h, w = g.shape
    solid = (g > 0)
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    alpha = np.where(solid, 255, 0).astype(np.uint8)

    for pid, col in pal.items():
        mask = (g == pid)
        if mask.any():
            rgb[mask] = col

    if shade and solid.any():
        up_empty = np.zeros_like(solid)
        up_empty[1:, :] = ~solid[:-1, :]
        top = solid & up_empty
        if top.any():
            v = rgb[top].astype(np.int16) * 1.18 + 14
            rgb[top] = np.clip(v, 0, 255).astype(np.uint8)
        dn_empty = np.zeros_like(solid)
        dn_empty[:-1, :] = ~solid[1:, :]
        bot = solid & dn_empty
        if bot.any():
            rgb[bot] = (rgb[bot].astype(np.float32) *
                        np.array([0.72, 0.72, 0.74])).astype(np.uint8)

    if outline and solid.any():
        empty = ~solid
        adj = np.zeros_like(empty)
        adj[1:, :] |= solid[:-1, :]
        adj[:-1, :] |= solid[1:, :]
        adj[:, 1:] |= solid[:, :-1]
        adj[:, :-1] |= solid[:, 1:]
        edge = empty & adj
        rgb[edge] = OUTLINE
        alpha[edge] = 255

    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(surf)[:] = np.transpose(rgb, (1, 0, 2))
    pygame.surfarray.pixels_alpha(surf)[:] = np.transpose(alpha)
    return surf


def _line(g, x0, y0, x1, y1, pid):
    n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    for i in range(n + 1):
        t = i / float(max(1, n))
        x = int(round(x0 + (x1 - x0) * t))
        y = int(round(y0 + (y1 - y0) * t))
        if 0 <= y < g.shape[0] and 0 <= x < g.shape[1]:
            g[y, x] = pid


# --------------------------------------------------------------------------
# 角色
# --------------------------------------------------------------------------
def _character(kind, pose="idle0", frame=0):
    """角色：36x52 的**人形**剪影（2 倍分辨率绘制后降采样，边缘带抗锯齿）。

    旧版是"圆头 + 两只大耳朵"，怎么看都像小狗。这一版：
      · 去掉兽耳，改成兜帽 / 全罩盔的尖顶轮廓
      · 明确肩-腰-胯的收放，腿有膝盖、脚有靴口
      · 弓箭手：飘动的围巾 + 背后箭袋 + 侧持弓
      · 盾卫：红缨盔 + 双肩甲 + 圆盾 + 短剑
    """
    S = 2                      # 内部绘制倍率（降采样后得到柔和边缘）
    g = _blank(W * S, H * S)
    archer = (kind == "archer")

    def R(x0, y0, x1, y1, pid):
        _rect(g, x0 * S, y0 * S, x1 * S + S - 1, y1 * S + S - 1, pid)

    def E(cx, cy, rx, ry, pid):
        _ellipse(g, cx * S, cy * S, rx * S, ry * S, pid)

    def T(pts, pid):
        _tri(g, [(x * S, y * S) for x, y in pts], pid)

    def P(pts, pid):
        _poly(g, [(x * S, y * S) for x, y in pts], pid)

    def Ln(x0, y0, x1, y1, pid):
        _line(g, x0 * S, y0 * S, x1 * S, y1 * S, pid)

    # ---- 姿态参数 ----
    bob = 0
    leg = 0.0
    lean = 0
    if pose == "idle1":
        bob = 1
    elif pose.startswith("run"):
        leg = (1.0, 0.2, -1.0, 0.2)[frame % 4]
        bob = (0, -1, 0, -1)[frame % 4]
        lean = 1
    elif pose == "jump":
        bob = -2
        leg = 0.9
    elif pose == "fall":
        leg = -0.9
    elif pose == "block":
        bob = 1

    top = 4 + bob
    cx = 18 + lean                       # 身体中轴

    # ================= 后层：围巾 / 披风 =================
    if archer:
        # 围巾：两片尾巴向后飘，跑动时上下摆
        fl = int(round(math.sin(frame * 1.6) * 1.5)) if pose.startswith("run") else 0
        T([(cx - 6, top + 14), (cx - 11, top + 13 + fl), (cx - 10, top + 18 + fl)], 4)
        T([(cx - 6, top + 15), (cx - 9, top + 16 + fl), (cx - 8, top + 19 + fl)], 3)
    else:
        # 短披风
        P([(cx - 6, top + 14), (cx + 6, top + 14), (cx + 7, top + 27),
           (cx - 8, top + 28)], 4)
        P([(cx - 5, top + 16), (cx - 1, top + 16), (cx - 2, top + 26),
           (cx - 7, top + 26)], 2)

    # ================= 腿 =================
    swing = int(round(leg * 3))
    # 后腿（暗）
    R(cx - 6 + swing, top + 27, cx - 2 + swing, top + 43, 2)
    R(cx - 7 + swing, top + 42, cx - 1 + swing, top + 47, 10)
    # 前腿
    R(cx + 1 - swing, top + 27, cx + 5 - swing, top + 43, 9)
    R(cx + 0 - swing, top + 42, cx + 6 - swing, top + 47, 10)
    if not archer:
        R(cx - 6 + swing, top + 31, cx - 2 + swing, top + 42, 3)   # 胫甲（深钢）
        R(cx + 1 - swing, top + 31, cx + 5 - swing, top + 42, 3)
        R(cx - 6 + swing, top + 31, cx - 6 + swing, top + 42, 4)   # 内侧暗边
        R(cx + 5 - swing, top + 31, cx + 5 - swing, top + 42, 4)
        R(cx - 2 + swing, top + 31, cx - 2 + swing, top + 42, 9)   # 外侧中调

    # ================= 躯干 =================
    if archer:
        # 皮甲：肩宽 12、腰宽 8
        P([(cx - 6, top + 14), (cx + 6, top + 14), (cx + 5, top + 22),
           (cx + 4, top + 27), (cx - 4, top + 27), (cx - 5, top + 22)], 3)
        P([(cx - 6, top + 14), (cx - 2, top + 14), (cx - 2, top + 27),
           (cx - 4, top + 27), (cx - 5, top + 22)], 4)      # 左侧暗面
        R(cx - 4, top + 22, cx + 4, top + 24, 8)            # 腰带
        R(cx - 1, top + 22, cx + 1, top + 24, 5)            # 带扣
        R(cx - 2, top + 15, cx + 1, top + 19, 5)            # 胸扣
        # 箭袋（背后，露出箭羽）
        R(cx + 4, top + 13, cx + 7, top + 22, 8)
        for i in range(3):
            Ln(cx + 5 + i, top + 13, cx + 4 + i * 2, top + 7, 11)
            T([(cx + 4 + i * 2, top + 8), (cx + 6 + i * 2, top + 7),
               (cx + 5 + i * 2, top + 5)], 3)
    else:
        # 板甲：宽肩收腰
        P([(cx - 7, top + 14), (cx + 7, top + 14), (cx + 5, top + 23),
           (cx + 5, top + 27), (cx - 5, top + 27), (cx - 5, top + 23)], 3)
        P([(cx - 7, top + 14), (cx - 2, top + 14), (cx - 3, top + 27),
           (cx - 5, top + 27), (cx - 5, top + 23)], 4)
        R(cx - 5, top + 22, cx + 5, top + 24, 8)            # 腰带
        R(cx - 1, top + 22, cx + 1, top + 24, 5)
        Ln(cx - 4, top + 17, cx + 4, top + 17, 5)           # 胸甲分片
        Ln(cx - 4, top + 20, cx + 4, top + 20, 5)
        E(cx - 7, top + 15, 4, 3, 5)                        # 肩甲
        E(cx + 7, top + 15, 4, 3, 5)
        E(cx - 7, top + 15, 2, 2, 4)

    # ================= 头 =================
    hy = top + 8
    R(cx - 2, hy + 5, cx + 2, hy + 6, 2)     # 脖子阴影
    E(cx, hy, 4, 4, 1)                    # 头部底面
    if archer:
        # 兜帽：包住头顶，帽尖向后上方
        E(cx, hy - 2, 6, 4, 3)
        P([(cx - 6, hy - 2), (cx - 6, hy + 4), (cx - 4, hy + 3),
           (cx - 4, hy - 3)], 3)
        T([(cx - 3, hy - 4), (cx + 2, hy - 9), (cx + 5, hy - 4)], 3)
        R(cx - 6, hy + 2, cx + 6, hy + 3, 4)              # 帽檐阴影
        # 帽檐下的脸（窄一点，眼睛压在下缘，才像"藏在兜帽里"）
        R(cx - 2, hy + 3, cx + 3, hy + 5, 1)
        R(cx - 1, hy + 3, cx + 0, hy + 4, 6)              # 眼
        R(cx + 1, hy + 3, cx + 2, hy + 4, 6)
        # 围巾领口
        R(cx - 5, hy + 6, cx + 5, hy + 8, 4)
        R(cx - 4, hy + 6, cx + 4, hy + 7, 3)
    else:
        # 全罩盔：圆顶 + 面甲缝 + 缨（收小，别把脑袋画成一个大蘑菇）
        E(cx, hy - 1, 4, 3, 5)
        R(cx - 4, hy - 1, cx + 4, hy + 1, 5)
        R(cx - 4, hy + 1, cx + 4, hy + 2, 4)              # 盔沿阴影
        R(cx - 3, hy + 2, cx + 3, hy + 4, 2)              # 面甲
        R(cx - 2, hy + 2, cx + 2, hy + 3, 6)              # 眼缝
        R(cx - 1, hy + 1, cx + 1, hy + 5, 5)              # 护鼻
        for i in range(3):                                # 缨
            R(cx - 1, hy - 5 - i, cx + 1, hy - 4 - i, 11)

    # ================= 手臂 / 武器 =================
    if archer:
        # 前臂伸向弓把
        R(cx + 5, top + 15, cx + 7, top + 20, 1)
        R(cx + 6, top + 19, cx + 9, top + 21, 8)          # 护腕
        R(cx + 8, top + 18, cx + 9, top + 20, 1)          # 手
        # 反曲弓：竖直弓臂（向右鼓）+ 中段握把 + 内侧直弦
        bx = cx + 9
        limb = []
        for i in range(11):
            t = i / 10.0
            limb.append((bx + 1 + 3.2 * math.sin(t * math.pi),
                         top + 7 + t * 22))
        for i in range(len(limb) - 1):
            for ox in (0, 1):
                Ln(int(limb[i][0]) + ox, int(limb[i][1]),
                   int(limb[i + 1][0]) + ox, int(limb[i + 1][1]), 8)
        # 弓臂高光（内侧一道亮木）
        for i in range(0, len(limb) - 1, 2):
            Ln(int(limb[i][0]), int(limb[i][1]),
               int(limb[i + 1][0]), int(limb[i + 1][1]), 5)
        # 握把
        R(int(bx) + 2, top + 16, int(bx) + 5, top + 20, 8)
        R(int(bx) + 3, top + 17, int(bx) + 4, top + 19, 5)
        # 弓梢
        R(int(limb[0][0]) - 1, top + 6, int(limb[0][0]) + 1, top + 8, 5)
        R(int(limb[-1][0]) - 1, top + 28, int(limb[-1][0]) + 1, top + 30, 5)
        # 弓弦
        Ln(int(bx) + 1, top + 7, int(bx) + 1, top + 29, 11)
        # 后臂
        R(cx - 7, top + 15, cx - 5, top + 21, 1)
    else:
        # 右臂
        R(cx + 5, top + 15, cx + 7, top + 22, 2)
        R(cx + 5, top + 21, cx + 8, top + 23, 5)          # 拳
        if pose == "block":
            # 举盾格挡：大盾立在前方
            P([(cx + 5, top + 9), (cx + 12, top + 11), (cx + 12, top + 24),
               (cx + 5, top + 26)], 3)
            P([(cx + 6, top + 11), (cx + 11, top + 12), (cx + 11, top + 23),
               (cx + 6, top + 24)], 5)
            P([(cx + 7, top + 14), (cx + 10, top + 15), (cx + 10, top + 20),
               (cx + 7, top + 21)], 4)
            R(cx + 7, top + 17, cx + 10, top + 18, 8)
        else:
            # 短剑：宽一点的剑身（3px）+ 亮刃边 + 护手 + 握柄 + 配重
            R(cx + 6, top + 7, cx + 9, top + 16, 2)       # 剑身暗面
            R(cx + 7, top + 7, cx + 9, top + 16, 5)       # 剑身
            R(cx + 9, top + 8, cx + 9, top + 15, 11)      # 刃口高光
            T([(cx + 6, top + 8), (cx + 9, top + 8), (cx + 8, top + 4)], 5)
            R(cx + 5, top + 16, cx + 10, top + 17, 8)     # 护手
            R(cx + 5, top + 16, cx + 5, top + 17, 11)
            R(cx + 10, top + 16, cx + 10, top + 17, 11)
            R(cx + 7, top + 17, cx + 9, top + 20, 8)      # 握柄
            R(cx + 7, top + 18, cx + 7, top + 19, 4)
            R(cx + 6, top + 20, cx + 10, top + 21, 5)     # 配重
        # 左臂 + 圆盾（金属边 + 盾面 + 中心凸起 + 徽记）
        R(cx - 8, top + 15, cx - 6, top + 21, 2)
        E(cx - 10, top + 19, 4, 5, 5)                     # 外圈金属
        E(cx - 10, top + 19, 3, 4, 3)                     # 盾面
        E(cx - 10, top + 18, 2, 2, 4)                     # 上部暗面
        E(cx - 10, top + 19, 1, 1, 5)                     # 中心凸起
        R(cx - 12, top + 18, cx - 11, top + 20, 4)        # 左侧暗边
        R(cx - 11, top + 19, cx - 9, top + 19, 11)        # 横向徽记

    return g


# --------------------------------------------------------------------------
# 怪物
# --------------------------------------------------------------------------
def _ground_monster(frame=0):
    g = _blank(MW, MH)
    squish = 1 if frame else 0
    y0 = 6 + squish
    # 身体
    _ellipse(g, 17, y0 + 11, 13, 10 - squish, 1)
    _rect(g, 5, y0 + 12, 29, y0 + 22, 1)
    # 背刺
    for i in range(4):
        x = 8 + i * 6
        _tri(g, [(x, y0 + 6), (x + 3, y0 - 2), (x + 6, y0 + 6)], 2)
    # 脚
    _rect(g, 6, y0 + 21, 13, y0 + 24, 2)
    _rect(g, 21, y0 + 21, 28, y0 + 24, 2)
    # 眼睛
    _rect(g, 11, y0 + 11, 13, y0 + 14, 3)
    _rect(g, 21, y0 + 11, 23, y0 + 14, 3)
    _rect(g, 12, y0 + 11, 12, y0 + 12, 4)
    _rect(g, 22, y0 + 11, 22, y0 + 12, 4)
    # 獠牙
    _tri(g, [(13, y0 + 18), (16, y0 + 18), (14, y0 + 22)], 4)
    _tri(g, [(18, y0 + 18), (21, y0 + 18), (20, y0 + 22)], 4)
    return g


def _fly_monster(frame=0):
    g = _blank(FW, FH)
    flap = frame % 2
    # 翅膀
    if flap == 0:
        _tri(g, [(2, 4), (16, 10), (3, 16)], 2)
        _tri(g, [(34, 4), (20, 10), (33, 16)], 2)
    else:
        _tri(g, [(2, 12), (16, 10), (4, 22)], 2)
        _tri(g, [(34, 12), (20, 10), (32, 22)], 2)
    # 身体
    _ellipse(g, 18, 13, 8, 7, 1)
    _rect(g, 14, 15, 22, 23, 1)
    # 耳朵
    _tri(g, [(11, 7), (14, 0), (16, 7)], 1)
    _tri(g, [(25, 7), (22, 0), (20, 7)], 1)
    # 眼睛
    _rect(g, 13, 11, 15, 15, 3)
    _rect(g, 21, 11, 23, 15, 3)
    _rect(g, 14, 11, 14, 12, 4)
    _rect(g, 22, 11, 22, 12, 4)
    # 小尖牙
    _tri(g, [(16, 18), (18, 18), (17, 21)], 4)
    _tri(g, [(19, 18), (21, 18), (20, 21)], 4)
    return g


BW, BH = 92, 112


def _boss(frame=0):
    """熔炉守卫：铁铸巨像（第二版）。

    轮廓全部用斜切多边形，不用矩形直边——上一版是"矩形+椭圆拼贴"，
    远看像积木。这一版：宽肩窄腰的铁砧躯干、斜切肩甲、两段手臂带肘关节、
    方拳、平顶盔（去掉头顶尖角）、胸口敞开炉膛 + 四道炉栅。
    """
    g = _blank(BW, BH)
    sway = 1 if frame else 0

    # ===== 背部排气口 =====
    _poly(g, [(26, 22), (36, 22), (34, 42), (28, 42)], 2)
    _poly(g, [(56, 22), (66, 22), (64, 42), (58, 42)], 2)
    _rect(g, 25, 20, 37, 24, 7)
    _rect(g, 55, 20, 67, 24, 7)

    # ===== 腿（粗短）=====
    _poly(g, [(30, 84), (44, 84), (43, 100), (31, 100)], 1)
    _poly(g, [(48, 84), (62, 84), (61, 100), (49, 100)], 1)
    _poly(g, [(38, 84), (44, 84), (43, 100), (39, 100)], 2)
    _poly(g, [(48, 84), (54, 84), (53, 100), (49, 100)], 2)
    # 铁靴（宽阔）
    _poly(g, [(26, 98), (46, 98), (48, 110), (24, 110)], 3)
    _poly(g, [(46, 98), (66, 98), (68, 110), (44, 110)], 3)
    _rect(g, 24, 107, 48, 110, 2)
    _rect(g, 44, 107, 68, 110, 2)

    # ===== 躯干（宽肩窄腰）=====
    _poly(g, [(20, 42), (72, 42), (64, 90), (28, 90)], 1)
    _poly(g, [(20, 42), (32, 42), (36, 90), (28, 90)], 2)
    _line(g, 46, 44, 46, 82, 4)
    _poly(g, [(28, 80), (64, 80), (64, 90), (28, 90)], 2)
    _line(g, 30, 82, 62, 82, 3)

    # ===== 肩甲（斜切，不带长尖刺）=====
    _poly(g, [(4, 46), (18, 36), (34, 44), (32, 58), (8, 60)], 1)
    _poly(g, [(88, 46), (74, 36), (58, 44), (60, 58), (84, 60)], 1)
    _poly(g, [(4, 46), (12, 40), (20, 46), (18, 58), (8, 60)], 3)
    _poly(g, [(88, 46), (80, 40), (72, 46), (74, 58), (84, 60)], 3)
    _tri(g, [(7, 46), (4, 35), (13, 43)], 3)
    _tri(g, [(85, 46), (88, 35), (79, 43)], 3)

    # ===== 手臂（上臂 / 肘 / 前臂 / 方拳）=====
    # 上臂（更靠外，和躯干留出缝隙）
    _poly(g, [(4 + sway, 50), (17 + sway, 50), (16 + sway, 70), (3 + sway, 70)], 1)
    _poly(g, [(74 - sway, 50), (87 - sway, 50), (88 - sway, 70), (75 - sway, 70)], 1)
    _poly(g, [(4 + sway, 50), (8 + sway, 50), (7 + sway, 70), (3 + sway, 70)], 3)
    _poly(g, [(83 - sway, 50), (87 - sway, 50), (88 - sway, 70), (84 - sway, 70)], 3)
    # 肘关节
    _rect(g, 3 + sway, 68, 17 + sway, 72, 2)
    _rect(g, 75 - sway, 68, 89 - sway, 72, 2)
    # 前臂
    _poly(g, [(2 + sway, 72), (16 + sway, 72), (18 + sway, 88), (0 + sway, 88)], 1)
    _poly(g, [(76 - sway, 72), (90 - sway, 72), (92 - sway, 88), (74 - sway, 88)], 1)
    _poly(g, [(2 + sway, 72), (6 + sway, 72), (4 + sway, 88), (0 + sway, 88)], 3)
    _poly(g, [(86 - sway, 72), (90 - sway, 72), (92 - sway, 88), (88 - sway, 88)], 3)
    # 方拳（比头大）
    _poly(g, [(0 + sway, 86), (19 + sway, 86), (21 + sway, 104), (-1 + sway, 104)], 1)
    _poly(g, [(73 - sway, 86), (92 - sway, 86), (94 - sway, 104), (72 - sway, 104)], 1)
    _rect(g, 0 + sway, 86, 21 + sway, 89, 3)
    _rect(g, 72 - sway, 86, 92 - sway, 89, 3)
    _line(g, 1 + sway, 95, 20 + sway, 95, 2)
    _line(g, 73 - sway, 95, 92 - sway, 95, 2)

    # ===== 头（陷在肩间，平顶盔）=====
    _poly(g, [(34, 16), (58, 16), (60, 24), (32, 24)], 3)
    _rect(g, 44, 14, 48, 18, 2)
    _poly(g, [(32, 24), (60, 24), (58, 42), (34, 42)], 1)
    _rect(g, 33, 27, 59, 36, 4)
    _rect(g, 36, 29, 44, 34, 5)
    _rect(g, 48, 29, 56, 34, 5)
    _rect(g, 38, 30, 42, 33, 6)
    _rect(g, 50, 30, 54, 33, 6)
    _poly(g, [(36, 38), (56, 38), (54, 43), (38, 43)], 2)

    # ===== 胸口熔炉（炉膛 + 熔岩 + 白热 + 炉栅）=====
    _ellipse(g, 46, 64, 16, 17, 4)
    _ellipse(g, 46, 64, 12, 13, 5)
    _ellipse(g, 46, 64, 6, 7, 6)
    for yy in (56, 62, 68, 74):
        _rect(g, 34, yy, 58, yy + 1, 4)

    # ===== 熔岩裂纹 =====
    _line(g, 40, 80, 34, 88, 5)
    _line(g, 52, 80, 58, 88, 5)
    _line(g, 30, 56, 22, 50, 5)

    # ===== 锈斑 =====
    _rect(g, 26, 74, 30, 78, 7)
    _rect(g, 62, 48, 66, 52, 7)

    return g


BPAL = {
    1: (106, 98, 94),      # 主体：偏暖的铸铁灰（冷紫灰会显得像塑料）
    2: (60, 52, 50),       # 暗面
    3: (150, 142, 132),    # 亮甲 / 高光
    4: (26, 22, 22),       # 深缝、炉膛
    5: (255, 142, 48),     # 熔岩橙
    6: (255, 234, 176),    # 白热
    7: (142, 76, 48),      # 锈红
}

CW, CH = 36, 44


def _caster(frame=0):
    """熔岩术士：漂浮的施法者，法杖顶端有火球。"""
    g = _blank(CW, CH)
    bob = 1 if frame else 0
    # 兜帽斗篷
    _ellipse(g, 18, 18 + bob, 10, 9, 1)
    _tri(g, [(8, 20 + bob), (18, 4 + bob), (28, 20 + bob)], 1)
    _rect(g, 9, 18 + bob, 27, 34 + bob, 2)
    _tri(g, [(9, 34 + bob), (18, 42 + bob), (27, 34 + bob)], 2)
    # 兜帽阴影与眼
    _ellipse(g, 18, 19 + bob, 6, 5, 3)
    _rect(g, 14, 18 + bob, 16, 20 + bob, 4)
    _rect(g, 20, 18 + bob, 22, 20 + bob, 4)
    # 法杖
    _line(g, 27, 10 + bob, 30, 34 + bob, 6)
    _ellipse(g, 27, 9 + bob, 3, 3, 5)
    # 飘带
    _line(g, 10, 28 + bob, 5, 34 + bob, 2)
    _line(g, 26, 28 + bob, 31, 34 + bob, 2)
    return g


CPAL = {
    1: (108, 84, 150),
    2: (76, 58, 108),
    3: (40, 30, 58),
    4: (255, 196, 120),
    5: (255, 150, 70),
    6: (138, 104, 76),
}

MPAL_GROUND = {
    1: (118, 148, 96),
    2: (84, 110, 72),
    3: (246, 214, 96),
    4: (250, 248, 236),
}
MPAL_FLY = {
    1: (150, 108, 176),
    2: (104, 68, 132),
    3: (255, 214, 120),
    4: (250, 248, 236),
}


# --------------------------------------------------------------------------
# 缓存接口
# --------------------------------------------------------------------------
_cache = {}
POSES = ("idle0", "idle1", "run0", "run1", "run2", "run3", "jump", "fall", "block")


def get_char(kind, pose="idle0", skin=None):
    kind = "archer" if kind == "archer" else "guard"
    skin = SKIN[kind] if skin is None else skin
    key = (kind, pose, skin)
    s = _cache.get(key)
    if s is not None:
        return s
    frame = int(pose[-1]) if pose.startswith("run") else 0
    base_pose = "idle" if pose.startswith("idle") else pose
    if pose.startswith("run"):
        base_pose = "run"
    g = _character(kind, base_pose, frame)
    pal = skin_palette(kind, skin)
    s = _render(g, pal)
    # 内部按 2 倍分辨率绘制，这里降采样回 36x52：
    # 轮廓不再是硬像素锯齿，观感接近手绘动画的柔边。
    if s.get_width() != W or s.get_height() != H:
        s = pygame.transform.smoothscale(s, (W, H))
    _cache[key] = s
    return s


def get_monster(kind, frame=0):
    key = ("mon", kind, frame)
    s = _cache.get(key)
    if s is not None:
        return s
    if kind == "boss":
        s = _render(_boss(frame), BPAL)
        _cache[key] = s
        return s
    if kind == "caster":
        s = _render(_caster(frame), CPAL)
        _cache[key] = s
        return s
    if kind == "fly":
        s = _render(_fly_monster(frame), MPAL_FLY)
    else:
        s = _render(_ground_monster(frame), MPAL_GROUND)
    _cache[key] = s
    return s


def prebuild():
    for kind in ("archer", "guard"):
        for si in range(len(skin_list(kind))):
            for pose in POSES:
                get_char(kind, pose, si)
    for f in (0, 1):
        get_monster("ground", f)
        get_monster("fly", f)
        get_monster("boss", f)
        get_monster("caster", f)
