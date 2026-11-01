# -*- coding: utf-8 -*-
"""Boss 重画：铁铸熔炉守卫，体型放大，胸口熔炉 + 熔岩眼 + 肩刺。"""
import io

P = "sprites.py"
s = io.open(P, encoding="utf-8").read()
log = []


def rep(old, new, tag):
    global s
    if old in s:
        s = s.replace(old, new, 1)
        log.append(tag)
    elif new in s:
        log.append(tag + "(already)")
    else:
        log.append(tag + "(SKIP)")


# 1) 多边形填充辅助（放在 _tri 之后）
rep('''def _render(g, pal, outline=True, shade=True):''',
    '''def _poly(g, pts, pid):
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


def _render(g, pal, outline=True, shade=True):''', "poly_helper")

# 2) 尺寸
rep("BW, BH = 72, 84", "BW, BH = 92, 112", "size")

# 3) 重画 boss
old_start = s.index("def _boss(frame=0):")
old_end = s.index("BPAL = {")
new_boss = '''def _boss(frame=0):
    """熔炉守卫：铁铸巨像。

    设计要点（相对旧版的改动）：
      - 体型 72x84 -> 92x112，比玩家高 2.5 倍，才有 Boss 压迫感
      - 躯干做成上宽下窄的铁砧梯形（旧版是直筒矩形，像积木人）
      - 胸口开一个真正的熔炉口：深色炉膛 + 熔岩 + 白热芯 + 炉栅
      - 眼睛是两道熔岩缝（旧版是两个橙色小方块，像纽扣）
      - 加背部烟囱、肩刺、锈斑、从炉口辐射的熔岩裂纹
    """
    g = _blank(BW, BH)
    sway = 1 if frame else 0
    CX = 46

    # ---- 背部烟囱（在身体后面）----
    _rect(g, 24, 12, 36, 38, 2)
    _rect(g, 56, 9, 68, 38, 2)
    _rect(g, 22, 8, 38, 14, 7)
    _rect(g, 54, 5, 70, 11, 7)
    _line(g, 26, 14, 31, 36, 4)
    _line(g, 58, 11, 63, 36, 4)

    # ---- 腿（粗短机械腿）----
    _poly(g, [(26, 84), (42, 84), (40, 104), (28, 104)], 1)
    _poly(g, [(50, 84), (66, 84), (64, 104), (52, 104)], 1)
    _poly(g, [(26, 84), (31, 84), (31, 104), (28, 104)], 2)
    _poly(g, [(50, 84), (55, 84), (55, 104), (52, 104)], 2)
    # 铁靴
    _rect(g, 22, 100, 44, 110, 3)
    _rect(g, 48, 100, 70, 110, 3)
    _rect(g, 22, 107, 44, 110, 2)
    _rect(g, 48, 107, 70, 110, 2)

    # ---- 躯干（铁砧梯形：肩宽腰窄）----
    _poly(g, [(20, 40), (72, 40), (64, 88), (28, 88)], 1)
    _poly(g, [(20, 40), (34, 40), (34, 88), (28, 88)], 2)   # 左侧暗面
    # 腰甲
    _rect(g, 27, 78, 65, 88, 3)
    _rect(g, 27, 84, 65, 88, 2)
    _line(g, 30, 82, 62, 82, 4)

    # ---- 肩甲（外扩，带高光和尖刺）----
    _ellipse(g, 17, 48, 17, 15, 1)
    _ellipse(g, 75, 48, 17, 15, 1)
    _ellipse(g, 13, 44, 9, 8, 3)
    _ellipse(g, 79, 44, 9, 8, 3)
    _tri(g, [(6, 42), (-2, 18), (22, 36)], 3)
    _tri(g, [(86, 42), (94, 18), (70, 36)], 3)
    _line(g, (6, 42), (-2, 18), 4) if False else None
    _line(g, 8, 40, 2, 22, 4)
    _line(g, 84, 40, 90, 22, 4)

    # ---- 手臂 + 拳（比头还大）----
    _poly(g, [(6 + sway, 52), (22 + sway, 52), (20 + sway, 88), (8 + sway, 88)], 1)
    _poly(g, [(70 - sway, 52), (86 - sway, 52), (84 - sway, 88), (72 - sway, 88)], 1)
    _poly(g, [(6 + sway, 52), (12 + sway, 52), (11 + sway, 88), (8 + sway, 88)], 2)
    _poly(g, [(70 - sway, 52), (76 - sway, 52), (75 - sway, 88), (72 - sway, 88)], 2)
    _ellipse(g, 14 + sway, 94, 14, 12, 1)
    _ellipse(g, 78 - sway, 94, 14, 12, 1)
    _rect(g, 4 + sway, 88, 26 + sway, 93, 3)      # 指节高光
    _rect(g, 66 - sway, 88, 88 - sway, 93, 3)
    _line(g, 6 + sway, 98, 22 + sway, 98, 4)
    _line(g, 70 - sway, 98, 86 - sway, 98, 4)

    # ---- 头（低伏在双肩之间）----
    _ellipse(g, CX, 32, 16, 14, 1)
    _rect(g, 30, 26, 62, 44, 2)                   # 面甲暗底
    _rect(g, 31, 20, 61, 27, 3)                   # 额甲
    _tri(g, [(CX, 8), (40, 21), (52, 21)], 3)     # 额心尖
    # 熔岩眼缝
    _rect(g, 35, 30, 44, 36, 4)
    _rect(g, 48, 30, 57, 36, 4)
    _rect(g, 36, 31, 43, 35, 5)
    _rect(g, 49, 31, 56, 35, 5)
    _rect(g, 38, 32, 41, 34, 6)
    _rect(g, 51, 32, 54, 34, 6)
    # 面甲下沿
    _rect(g, 34, 40, 58, 44, 4)
    _line(g, 46, 36, 46, 44, 2)

    # ---- 胸口熔炉（视觉核心）----
    _ellipse(g, CX, 64, 17, 19, 4)                # 炉膛（最深）
    _ellipse(g, CX, 64, 13, 15, 5)                # 熔岩
    _ellipse(g, CX, 64, 7, 9, 6)                  # 白热芯
    # 炉栅
    _rect(g, 30, 58, 62, 60, 4)
    _rect(g, 30, 68, 62, 70, 4)
    _rect(g, 30, 58, 62, 59, 2)

    # ---- 熔岩裂纹（从炉口/肩缝向外辐射）----
    _line(g, CX - 8, 80, 36, 87, 5)
    _line(g, CX + 8, 80, 56, 87, 5)
    _line(g, 30, 56, 21, 49, 5)
    _line(g, 62, 56, 71, 49, 5)
    _line(g, 34, 44, 29, 37, 5)
    _line(g, 58, 44, 63, 37, 5)

    # ---- 锈斑 / 铆钉（打破大色块）----
    _rect(g, 24, 70, 28, 74, 7)
    _rect(g, 62, 46, 66, 50, 7)
    _rect(g, 38, 94, 42, 98, 7)
    _rect(g, 22, 44, 24, 46, 4)
    _rect(g, 68, 44, 70, 46, 4)
    _rect(g, 44, 88, 48, 90, 4)

    return g


'''
s = s[:old_start] + new_boss + s[old_end:]
log.append("boss_redraw")

# 4) 配色
rep('''BPAL = {
    1: (104, 100, 96),
    2: (70, 66, 64),
    3: (78, 74, 72),
    4: (52, 46, 44),
    5: (255, 150, 66),
}''',
    '''BPAL = {
    1: (96, 94, 106),      # 主体：冷铁灰
    2: (54, 52, 64),       # 暗面
    3: (138, 134, 148),    # 亮甲 / 高光
    4: (26, 24, 32),       # 深缝、炉膛
    5: (255, 146, 54),     # 熔岩橙
    6: (255, 232, 170),    # 白热
    7: (132, 72, 50),      # 锈红
}''', "palette")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_boss_log.txt", "w", encoding="utf-8").write(" | ".join(log))
print("done")
