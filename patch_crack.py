# -*- coding: utf-8 -*-
"""裂缝美化：下移避开 HUD、加大、加放射裂纹、石头从缝下缘探出。"""
import io

P = "renderer.py"
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


# 1) 裂缝本体：更大、锯齿更凶、加放射裂纹
rep('''        w = 26.0 + 52.0 * ratio
        h = 5.0 + 21.0 * ratio
        n = 9
        top, bot = [], []
        for i in range(n + 1):
            f = i / float(n)
            x = cx - w * 0.5 + w * f
            taper = math.sin(f * math.pi) ** 0.65
            jt = math.sin(f * 9.3 + t * 3.1) * (1.2 + 1.8 * ratio)
            top.append((x, cy - h * taper * 0.5 + jt))
            bot.append((x, cy + h * taper * 0.5 - jt))''',
    '''        w = 34.0 + 74.0 * ratio
        h = 6.0 + 26.0 * ratio
        n = 11
        top, bot = [], []
        for i in range(n + 1):
            f = i / float(n)
            x = cx - w * 0.5 + w * f
            taper = math.sin(f * math.pi) ** 0.55
            # 交替尖齿：偶数格往外咬，奇数额内收，做出"被硬掰开"的锯齿
            tooth = (2.6 if i % 2 == 0 else -1.8) * ratio
            jt = math.sin(f * 9.3 + t * 3.1) * (1.2 + 1.8 * ratio) + tooth
            top.append((x, cy - h * taper * 0.5 + jt))
            bot.append((x, cy + h * taper * 0.5 - jt))
        # 往外扩散的细裂纹（像玻璃碎开的纹路）
        if ratio > 0.25:
            rr = random.Random(int(cx) * 31 + 5)
            for k in range(5):
                side = -1.0 if k % 2 == 0 else 1.0
                a0 = rr.uniform(-0.5, 0.5)
                ln = (14 + rr.uniform(0, 22)) * ratio
                x0 = cx + side * w * 0.42
                y0 = cy + a0 * 6
                pygame.draw.line(surf, theme.alpha_color((120, 68, 148), 130),
                                 (x0, y0), (x0 + side * ln, y0 + a0 * ln * 0.7), 1)''',
    "crack_shape")

# 2) 裂缝位置下移（避开 HUD 卡片），并限制不要盖到落点
rep('''                # 裂缝固定在"天空"：至少贴在屏幕顶部，别跑到视口上方看不见
                crack_y = max(float(r.get("y0", 5 * TILE)) - cam_y, 24)''',
    '''                # 裂缝固定在"天空"：夹在 HUD 之下、落点之上的一段区域，
                # 24 会被血条卡片压住，72 才开始露出来
                _lo = 72.0
                _hi = max(_lo, land_y - 170.0)
                crack_y = min(max(float(r.get("y0", 5 * TILE)) - cam_y, _lo), _hi)''',
    "crack_pos")

# 3) open 状态石头从裂缝下缘探出，而不是糊在裂缝正中
rep('''                    # 石头从裂缝里探出下半截
                    drop = 6 + 10 * ratio
                    pts = self._island_rock_poly(rx, crack_y + drop, int(r["x"]), 0.92)''',
    '''                    # 石头从裂缝下缘探出（中心压在下边缘，只露下半截）
                    drop = 12 + 12 * ratio
                    pts = self._island_rock_poly(rx, crack_y + drop, int(r["x"]), 0.95)''',
    "rock_peek")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_crack_log.txt", "w", encoding="utf-8").write(" | ".join(log))
print("done")
