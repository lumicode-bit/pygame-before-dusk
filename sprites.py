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
        {"name": "霜原猎手", "style": "fur", "pal": {
            1: (242, 216, 190), 2: (72, 78, 92), 3: (96, 152, 194),
            4: (52, 92, 128), 5: (214, 226, 240), 6: (32, 40, 56),
            7: (150, 108, 100), 8: (108, 96, 84), 9: (104, 108, 120),
            10: (58, 62, 74), 11: (236, 244, 255)}},
        {"name": "夜行刺客", "style": "mask", "pal": {
            1: (226, 192, 158), 2: (40, 40, 52), 3: (62, 58, 92),
            4: (34, 32, 54), 5: (176, 186, 208), 6: (24, 26, 36),
            7: (146, 96, 88), 8: (62, 54, 66), 9: (58, 54, 66),
            10: (40, 36, 44), 11: (198, 210, 232)}},
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
        {"name": "重装守门人", "style": "tower", "pal": {
            1: (230, 194, 156), 2: (46, 48, 56), 3: (86, 92, 108),
            4: (50, 54, 68), 5: (188, 196, 212), 6: (28, 30, 38),
            7: (148, 94, 82), 8: (108, 72, 44), 9: (78, 82, 94),
            10: (56, 50, 46), 11: (96, 160, 190)}},
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


def skin_style(kind, idx=None):
    lst = skin_list(kind)
    i = SKIN["archer" if kind == "archer" else "guard"] if idx is None else idx
    return lst[max(0, min(len(lst) - 1, i))].get("style", "hood")


def _mix(c1, c2, t):
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def _scale(c, k):
    return (max(0, min(255, int(c[0] * k))),
            max(0, min(255, int(c[1] * k))),
            max(0, min(255, int(c[2] * k))))


def skin_palette(kind, idx=None):
    lst = skin_list(kind)
    i = SKIN["archer" if kind == "archer" else "guard"] if idx is None else idx
    pal = dict(lst[max(0, min(len(lst) - 1, i))]["pal"])
    # 12~20：从基础 11 色自动派生"中间调 / 高光 / 最深 / 环境光"，
    # 不用给每套外观手写 20 个颜色，也保证六套风格一致。
    if 12 not in pal:
        pal[12] = _scale(pal[1], 0.80)                     # 皮肤暗部
        pal[13] = _mix(pal[3], (255, 255, 255), 0.30)      # 主色高光
        pal[14] = _scale(pal[4], 0.66)                     # 主色最深（缝）
        pal[15] = _scale(pal[8], 1.28)                     # 皮革亮
        pal[16] = _scale(pal[9], 1.30)                     # 裤子亮
        pal[17] = _scale(pal[5], 0.74)                     # 金饰暗
        pal[18] = _scale(pal[10], 1.35)                    # 靴子亮
        pal[19] = (238, 242, 248)                          # 眼白
        pal[20] = _mix(pal[3], (104, 146, 178), 0.55)      # 冷环境光
    return pal



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
def _character(kind, pose="idle0", frame=0, style="hood"):
    """角色：36x52 的**人形**剪影（2 倍分辨率绘制后降采样，边缘带抗锯齿）。

    旧版是"圆头 + 两只大耳朵"，怎么看都像小狗。这一版：
      · 去掉兽耳，改成兜帽 / 全罩盔的尖顶轮廓
      · 明确肩-腰-胯的收放，腿有膝盖、脚有靴口
      · 弓箭手：飘动的围巾 + 背后箭袋 + 侧持弓
      · 盾卫：红缨盔 + 双肩甲 + 圆盾 + 短剑
    """
    S = 4                      # 内部绘制倍率（4 倍超采样，降采样后边缘更细腻）
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
    elif pose == "swing":
        # 4 帧：0 预备后仰 / 1 加速过肩 / 2 命中前倾 / 3 收招回位
        lean = (-1, 0, 2, 1)[frame % 4]
        bob = (-1, 0, 1, 0)[frame % 4]
    elif pose == "shoot":
        # 3 帧：0 满弓 / 1 松弦回弹 / 2 收势
        lean = (-1, 0, 1)[frame % 3]
        bob = (0, 0, 0)[frame % 3]

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
    Ln(cx + 5 - swing, top + 28, cx + 5 - swing, top + 42, 16)   # 裤腿高光
    Ln(cx + 1 - swing, top + 35, cx + 5 - swing, top + 35, 2)    # 膝盖分节
    Ln(cx + 1 - swing, top + 41, cx + 5 - swing, top + 41, 2)    # 脚踝
    R(cx + 0 - swing, top + 42, cx + 6 - swing, top + 47, 10)
    Ln(cx + 6 - swing, top + 43, cx + 6 - swing, top + 46, 18)   # 靴口亮边
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
        Ln(cx + 4, top + 15, cx + 4, top + 26, 13)          # 右缘高光
        Ln(cx - 5, top + 15, cx - 5, top + 25, 14)          # 左缘最深缝
        Ln(cx - 1, top + 19, cx + 2, top + 25, 14)          # 衣褶
        Ln(cx + 2, top + 16, cx + 2, top + 20, 13)          # 胸前高光
        R(cx - 4, top + 22, cx + 4, top + 24, 8)            # 腰带
        Ln(cx - 4, top + 22, cx + 4, top + 22, 15)          # 腰带亮边
        Ln(cx - 4, top + 24, cx + 4, top + 24, 2)           # 腰带下阴影
        R(cx - 1, top + 22, cx + 1, top + 24, 5)            # 带扣
        R(cx - 2, top + 15, cx + 1, top + 19, 5)            # 胸扣
        R(cx - 2, top + 18, cx + 1, top + 18, 17)           # 胸扣暗边
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
        Ln(cx - 4, top + 18, cx + 4, top + 18, 4)           # 分片下阴影
        Ln(cx - 4, top + 21, cx + 4, top + 21, 4)
        Ln(cx + 4, top + 15, cx + 4, top + 26, 11)          # 右缘高光
        Ln(cx - 5, top + 15, cx - 5, top + 25, 14)          # 左缘最深缝
        E(cx - 7, top + 15, 4, 3, 5)                        # 肩甲
        E(cx + 7, top + 15, 4, 3, 5)
        E(cx - 7, top + 15, 2, 2, 4)

    # ================= 头 =================
    hy = top + 8
    R(cx - 2, hy + 5, cx + 2, hy + 6, 2)     # 脖子阴影
    E(cx, hy, 4, 4, 1)                    # 头部底面
    if archer:
        if style == "mask":
            # 夜行刺客：头巾 + 蒙面，没有帽尖
            E(cx, hy - 1, 5, 4, 3)
            R(cx - 5, hy - 1, cx + 5, hy + 1, 3)
            R(cx - 5, hy + 1, cx + 5, hy + 2, 4)
            T([(cx - 4, hy - 1), (cx - 10, hy + 4), (cx - 5, hy + 5)], 3)   # 头巾尾
            R(cx - 4, hy + 2, cx + 4, hy + 4, 2)          # 面罩
            R(cx - 3, hy + 2, cx - 2, hy + 3, 11)         # 眼（亮）
            R(cx + 1, hy + 2, cx + 2, hy + 3, 11)
            R(cx - 5, hy + 6, cx + 5, hy + 8, 4)          # 高领
            R(cx - 4, hy + 6, cx + 4, hy + 7, 2)
        elif style == "fur":
            # 霜原猎手：厚毛边兜帽，帽檐一圈亮毛
            E(cx, hy - 2, 6, 5, 3)
            P([(cx - 7, hy - 2), (cx - 7, hy + 5), (cx - 4, hy + 4),
               (cx - 4, hy - 3)], 3)
            T([(cx - 4, hy - 5), (cx + 1, hy - 11), (cx + 5, hy - 5)], 3)
            R(cx - 7, hy + 1, cx + 7, hy + 3, 11)         # 毛边
            R(cx - 6, hy + 1, cx + 6, hy + 2, 5)
            R(cx - 2, hy + 3, cx + 3, hy + 5, 1)
            R(cx - 1, hy + 3, cx + 0, hy + 4, 6)
            R(cx + 1, hy + 3, cx + 2, hy + 4, 6)
            R(cx - 5, hy + 6, cx + 5, hy + 8, 4)
        else:
            # 兜帽：包住头顶，帽尖向后上方
            E(cx, hy - 2, 6, 4, 3)
            P([(cx - 6, hy - 2), (cx - 6, hy + 4), (cx - 4, hy + 3),
               (cx - 4, hy - 3)], 3)
            T([(cx - 3, hy - 4), (cx + 2, hy - 9), (cx + 5, hy - 4)], 3)
            R(cx - 6, hy + 2, cx + 6, hy + 3, 4)          # 帽檐阴影
            # 帽檐下的脸（窄一点，眼睛压在下缘，才像"藏在兜帽里"）
            R(cx - 2, hy + 3, cx + 3, hy + 5, 1)
            Ln(cx - 2, hy + 5, cx + 3, hy + 5, 12)        # 下颌暗部
            R(cx - 1, hy + 3, cx + 0, hy + 4, 6)          # 眼窝
            R(cx + 1, hy + 3, cx + 2, hy + 4, 6)
            R(cx - 1, hy + 3, cx - 1, hy + 3, 19)         # 瞳点高光
            R(cx + 2, hy + 3, cx + 2, hy + 3, 19)
            Ln(cx - 2, hy + 2, cx + 3, hy + 2, 12)        # 眉骨阴影
            # 围巾领口
            R(cx - 5, hy + 6, cx + 5, hy + 8, 4)
            R(cx - 4, hy + 6, cx + 4, hy + 7, 3)
    else:
        if style == "tower":
            # 重装守门人：封闭大盔 + 横眼缝 + 竖脊，无缨
            E(cx, hy - 2, 5, 4, 5)
            R(cx - 5, hy - 2, cx + 5, hy + 3, 5)
            R(cx - 5, hy + 2, cx + 5, hy + 3, 4)
            R(cx - 4, hy + 1, cx + 4, hy + 2, 6)          # 横眼缝
            R(cx - 1, hy - 2, cx + 1, hy + 4, 11)         # 竖脊
            R(cx - 5, hy + 4, cx + 5, hy + 5, 3)          # 护颈
        else:
            # 全罩盔：圆顶 + 面甲缝 + 缨（收小，别把脑袋画成一个大蘑菇）
            E(cx, hy - 1, 4, 3, 5)
            R(cx - 4, hy - 1, cx + 4, hy + 1, 5)
            R(cx - 4, hy + 1, cx + 4, hy + 2, 4)          # 盔沿阴影
            R(cx - 3, hy + 2, cx + 3, hy + 4, 2)          # 面甲
            R(cx - 2, hy + 2, cx + 2, hy + 3, 6)          # 眼缝
            R(cx - 1, hy + 1, cx + 1, hy + 5, 5)          # 护鼻
            for i in range(3):                            # 缨
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
        # 弓弦 + 拉弦手：射击动画的 3 帧
        if pose == "shoot":
            _f = frame % 3
            # 弦被拉开的深度（0 帧拉满 -> 1 帧回弹 -> 2 帧归位）
            _pull = (6, 2, 0)[_f]
            _hx = int(bx) + 1 - _pull
            _hy = top + 17 + (0, 0, 2)[_f]
            Ln(int(bx) + 1, top + 7, _hx, _hy, 11)
            Ln(_hx, _hy, int(bx) + 1, top + 29, 11)
            # 拉弦的手臂
            R(cx - 6, top + 14, cx - 3, top + 18, 1)
            R(_hx - 1, _hy - 1, _hx + 1, _hy + 1, 8)      # 手
            # 满弓时弦上搭着箭
            if _f == 0:
                Ln(int(bx) + 2, top + 17, _hx + 1, _hy, 5)
        else:
            Ln(int(bx) + 1, top + 7, int(bx) + 1, top + 29, 19)
        # 后臂
        R(cx - 7, top + 15, cx - 5, top + 21, 1)
    else:
        # 右臂
        R(cx + 5, top + 15, cx + 7, top + 22, 2)
        R(cx + 5, top + 21, cx + 8, top + 23, 5)          # 拳
        if pose == "swing":
            # 挥剑 4 帧（只画"朝右"一套，方向由渲染层镜像）
            # 0 预备：剑后拉到肩后上方   1 加速：剑过肩
            # 2 命中：剑劈到最前最下     3 收招：剑收回体侧
            _S = (
                # (上臂x0,y0,x1,y1) (拳) (护手) (剑起点) (剑终点)
                ((cx + 3, top + 8, cx + 5, top + 14),
                 (cx + 3, top + 6, cx + 6, top + 9),
                 (cx + 4, top + 7, cx + 7, top + 8),
                 (cx + 6, top + 6), (cx + 9, top - 2)),
                ((cx + 4, top + 10, cx + 6, top + 16),
                 (cx + 5, top + 8, cx + 8, top + 11),
                 (cx + 6, top + 9, cx + 9, top + 10),
                 (cx + 8, top + 9), (cx + 13, top + 3)),
                ((cx + 6, top + 13, cx + 8, top + 19),
                 (cx + 7, top + 15, cx + 10, top + 18),
                 (cx + 7, top + 15, cx + 11, top + 16),
                 (cx + 10, top + 16), (cx + 17, top + 24)),
                ((cx + 5, top + 15, cx + 7, top + 20),
                 (cx + 6, top + 17, cx + 9, top + 20),
                 (cx + 6, top + 17, cx + 10, top + 18),
                 (cx + 9, top + 19), (cx + 13, top + 27)),
            )[frame % 4]
            R(*_S[0], 2)
            R(*_S[1], 5)
            R(*_S[2], 8)
            Ln(_S[3][0], _S[3][1], _S[4][0], _S[4][1], 5)
            Ln(_S[3][0] + 1, _S[3][1], _S[4][0] + 1, _S[4][1], 19)
        elif pose == "block":
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
            R(cx + 9, top + 8, cx + 9, top + 15, 19)      # 刃口高光（亮白）
            T([(cx + 6, top + 8), (cx + 9, top + 8), (cx + 8, top + 4)], 5)
            R(cx + 5, top + 16, cx + 10, top + 17, 8)     # 护手
            R(cx + 5, top + 16, cx + 5, top + 17, 19)
            R(cx + 10, top + 16, cx + 10, top + 17, 19)
            R(cx + 7, top + 17, cx + 9, top + 20, 8)      # 握柄
            R(cx + 7, top + 18, cx + 7, top + 19, 4)
            R(cx + 6, top + 20, cx + 10, top + 21, 5)     # 配重
        # 左臂 + 盾
        R(cx - 8, top + 15, cx - 6, top + 21, 2)
        if style == "tower":
            # 塔盾：方形大盾，竖脊 + 四角铆钉
            R(cx - 12, top + 12, cx - 6, top + 27, 3)
            R(cx - 12, top + 12, cx - 6, top + 13, 5)
            R(cx - 12, top + 12, cx - 12, top + 27, 4)
            R(cx - 9, top + 13, cx - 9, top + 26, 11)     # 竖脊
            R(cx - 11, top + 14, cx - 7, top + 15, 5)
            R(cx - 11, top + 24, cx - 7, top + 25, 5)
        else:
            E(cx - 10, top + 19, 4, 5, 5)                 # 外圈金属
            E(cx - 10, top + 19, 3, 4, 3)                 # 盾面
            E(cx - 10, top + 18, 2, 2, 4)                 # 上部暗面
            E(cx - 10, top + 19, 1, 1, 5)                 # 中心凸起
            R(cx - 12, top + 18, cx - 11, top + 20, 4)    # 左侧暗边
            R(cx - 11, top + 19, cx - 9, top + 19, 11)    # 横向徽记

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


def _boss(pose="walk0"):
    """熔炉守卫：铁铸巨像。

    分两层画：**腿**画在底层不动，**上半身**（躯干/肩/手臂/头/炉膛）
    画在独立矩阵上，最后按姿势做整体位移 —— 这样才有"重心起伏"和
    "前倾冲锋"，而不是只有手臂在原地抽动。

    pose: walk0..walk3 / raise0..1 / charge0..1 / slam_up / slam_down
    """
    if not isinstance(pose, str):
        pose = "walk1" if pose else "walk0"
    # (上半身 y 偏移, 上半身 x 偏移, 左臂偏移, 右臂偏移)
    _POSES = {
        "walk0": (0, 0, ((-3, 0), (3, 0))),
        "walk1": (-2, 0, ((2, 0), (-2, 0))),
        "walk2": (0, 0, ((3, 0), (-3, 0))),
        "walk3": (-2, 0, ((-2, 0), (2, 0))),
        "raise0": (1, 0, ((0, -14), (0, -14))),
        "raise1": (-2, 0, ((0, -30), (0, -30))),
        "raise": (-2, 0, ((0, -30), (0, -30))),
        "charge0": (0, 3, ((6, -6), (-6, -6))),
        "charge1": (-1, 5, ((9, -3), (-9, -3))),
        "charge": (-1, 5, ((9, -3), (-9, -3))),
        "slam_up": (-4, 0, ((0, -40), (0, -40))),
        "slam_down": (3, 0, ((7, 9), (-7, 9))),
    }
    bob, lean, arm_pose = _POSES.get(pose, _POSES["walk0"])

    g = _blank(BW, BH)
    up = _blank(BW, BH)          # 上半身单独一层，方便整体位移

    # ===== 腿（粗短，不动）=====
    _poly(g, [(30, 84), (44, 84), (43, 100), (31, 100)], 1)
    _poly(g, [(48, 84), (62, 84), (61, 100), (49, 100)], 1)
    _poly(g, [(38, 84), (44, 84), (43, 100), (39, 100)], 2)
    _poly(g, [(48, 84), (54, 84), (53, 100), (49, 100)], 2)
    _poly(g, [(26, 98), (46, 98), (48, 110), (24, 110)], 3)
    _poly(g, [(46, 98), (66, 98), (68, 110), (44, 110)], 3)
    _rect(g, 24, 107, 48, 110, 2)
    _rect(g, 44, 107, 68, 110, 2)

    # ===== 上半身：排气口 =====
    _poly(up, [(26, 22), (36, 22), (34, 42), (28, 42)], 2)
    _poly(up, [(56, 22), (66, 22), (64, 42), (58, 42)], 2)
    _rect(up, 25, 20, 37, 24, 7)
    _rect(up, 55, 20, 67, 24, 7)

    # ===== 躯干（宽肩窄腰）=====
    _poly(up, [(20, 42), (72, 42), (64, 90), (28, 90)], 1)
    _poly(up, [(20, 42), (32, 42), (36, 90), (28, 90)], 2)
    _line(up, 46, 44, 46, 82, 4)
    _poly(up, [(28, 80), (64, 80), (64, 90), (28, 90)], 2)
    _line(up, 30, 82, 62, 82, 3)

    # ===== 肩甲 =====
    _poly(up, [(4, 46), (18, 36), (34, 44), (32, 58), (8, 60)], 1)
    _poly(up, [(88, 46), (74, 36), (58, 44), (60, 58), (84, 60)], 1)
    _poly(up, [(4, 46), (12, 40), (20, 46), (18, 58), (8, 60)], 3)
    _poly(up, [(88, 46), (80, 40), (72, 46), (74, 58), (84, 60)], 3)
    _tri(up, [(7, 46), (4, 35), (13, 43)], 3)
    _tri(up, [(85, 46), (88, 35), (79, 43)], 3)

    # ===== 手臂 =====
    def _arm(side, dx, dy):
        if side < 0:
            polys = [([(4, 50), (17, 50), (16, 70), (3, 70)], 1),
                     ([(4, 50), (8, 50), (7, 70), (3, 70)], 3),
                     ([(2, 72), (16, 72), (18, 88), (0, 88)], 1),
                     ([(2, 72), (6, 72), (4, 88), (0, 88)], 3),
                     ([(0, 86), (19, 86), (21, 104), (-1, 104)], 1),
                     ([(0, 86), (21, 86), (21, 89), (0, 89)], 3)]
            rects = [((3, 68), (17, 72), 2)]
            lns = [((1, 95), (20, 95), 2)]
        else:
            polys = [([(88, 50), (75, 50), (76, 70), (89, 70)], 1),
                     ([(88, 50), (84, 50), (85, 70), (89, 70)], 3),
                     ([(90, 72), (76, 72), (74, 88), (92, 88)], 1),
                     ([(90, 72), (86, 72), (88, 88), (92, 88)], 3),
                     ([(92, 86), (73, 86), (71, 104), (93, 104)], 1),
                     ([(92, 86), (71, 86), (71, 89), (92, 89)], 3)]
            rects = [((75, 68), (89, 72), 2)]
            lns = [((73, 95), (92, 95), 2)]
        for pts, pid in polys:
            _poly(up, [(x + dx, y + dy) for x, y in pts], pid)
        for (a, b, pid) in rects:
            _rect(up, a[0] + dx, a[1] + dy, b[0] + dx, b[1] + dy, pid)
        for (a, b, pid) in lns:
            _line(up, a[0] + dx, a[1] + dy, b[0] + dx, b[1] + dy, pid)

    _arm(-1, *arm_pose[0])
    _arm(1, *arm_pose[1])

    # ===== 头 =====
    _poly(up, [(34, 16), (58, 16), (60, 24), (32, 24)], 3)
    _rect(up, 44, 14, 48, 18, 2)
    _poly(up, [(32, 24), (60, 24), (58, 42), (34, 42)], 1)
    _rect(up, 33, 27, 59, 36, 4)
    _rect(up, 36, 29, 44, 34, 5)
    _rect(up, 48, 29, 56, 34, 5)
    _rect(up, 38, 30, 42, 33, 6)
    _rect(up, 50, 30, 54, 33, 6)
    _poly(up, [(36, 38), (56, 38), (54, 43), (38, 43)], 2)

    # ===== 胸口熔炉 =====
    _ellipse(up, 46, 64, 16, 17, 4)
    _ellipse(up, 46, 64, 12, 13, 5)
    _ellipse(up, 46, 64, 6, 7, 6)
    for yy in (56, 62, 68, 74):
        _rect(up, 34, yy, 58, yy + 1, 4)

    # ===== 熔岩裂纹 / 锈斑 =====
    _line(up, 40, 80, 34, 88, 5)
    _line(up, 52, 80, 58, 88, 5)
    _line(up, 30, 56, 22, 50, 5)
    _rect(up, 26, 74, 30, 78, 7)
    _rect(up, 62, 48, 66, 52, 7)

    # ===== 上半身整体位移（重心起伏 + 前倾）=====
    if bob or lean:
        moved = np.zeros_like(up)
        for dy in range(BH):
            sy = dy - bob
            if sy < 0 or sy >= BH:
                continue
            row = up[sy]
            if lean > 0:
                moved[dy, lean:] = row[:BW - lean]
            elif lean < 0:
                moved[dy, :BW + lean] = row[-lean:]
            else:
                moved[dy] = row
        up = moved
    g = np.where(up > 0, up, g)
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
POSES = ("idle0", "idle1", "run0", "run1", "run2", "run3", "jump", "fall",
         "block", "swing0", "swing1", "swing2", "swing3",
         "shoot0", "shoot1", "shoot2")


def get_char(kind, pose="idle0", skin=None):
    kind = "archer" if kind == "archer" else "guard"
    skin = SKIN[kind] if skin is None else skin
    key = (kind, pose, skin)
    s = _cache.get(key)
    if s is not None:
        return s
    frame = (int(pose[-1]) if (pose.startswith("run") or pose.startswith("swing")
                               or pose.startswith("shoot")) else 0)
    base_pose = "idle" if pose.startswith("idle") else pose
    if pose.startswith("run"):
        base_pose = "run"
    elif pose.startswith("swing"):
        base_pose = "swing"
    elif pose.startswith("shoot"):
        base_pose = "shoot"
    g = _character(kind, base_pose, frame, skin_style(kind, skin))
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
