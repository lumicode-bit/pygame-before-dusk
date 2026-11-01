# -*- coding: utf-8 -*-
"""黑洞美化第二轮：径向渐变核心 + 辐射光线 + 闭合动画。"""
import io

# ---------- 引擎：裂隙到期后进入 0.34s 闭合 ----------
P = "game_core.py"
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


rep('''        keep = []
        for r in self.rifts:
            r["t"] += dt
            if r["t"] < r["delay"]:
                keep.append(r)
                continue
            try:''',
    '''        keep = []
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
            try:''', "fade_tick")

rep('''                self.monsters.append(m)
                self.events.append(("rift_open", int(r["x"]), int(r["y"])))
            except Exception as e:
                write_log("裂隙生成怪物异常: %r" % (e,))
        self.rifts = keep''',
    '''                self.monsters.append(m)
                self.events.append(("rift_open", int(r["x"]), int(r["y"])))
                r["fade"] = 0.34          # 怪物走出来，黑洞同时开始闭合
                r["fade_max"] = 0.34
                keep.append(r)
            except Exception as e:
                write_log("裂隙生成怪物异常: %r" % (e,))
        self.rifts = keep''', "fade_start")

rep('''                "rifts": [{"x": round(r["x"], 1), "y": round(r["y"], 1),
                           "t": round(r["t"], 2), "delay": r["delay"],
                           "size": r["size"], "kind": r["kind"]}
                          for r in self.rifts],''',
    '''                "rifts": [{"x": round(r["x"], 1), "y": round(r["y"], 1),
                           "t": round(min(r["t"], r["delay"]), 2), "delay": r["delay"],
                           "size": r["size"], "kind": r["kind"],
                           "fade": round(r.get("fade", 0.0), 2),
                           "fade_max": r.get("fade_max", 0.34)}
                          for r in self.rifts],''', "fade_pack")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_fade_log.txt", "w", encoding="utf-8").write(" | ".join(log))

# ---------- 渲染：更精致的黑洞 ----------
P = "renderer.py"
s = io.open(P, encoding="utf-8").read()
log2 = []


def rep2(old, new, tag):
    global s
    if old in s:
        s = s.replace(old, new, 1)
        log2.append(tag)
    elif new in s:
        log2.append(tag + "(already)")
    else:
        log2.append(tag + "(SKIP)")


rep2('''                prog = max(0.0, min(1.0, float(r.get("t", 0.0)) / max(0.01, float(r.get("delay", 1.0)))))
                base = float(r.get("size", 28.0)) * (0.52 + 0.48 * prog)
                wide = base * 1.05
                tall = base * 0.74
                cx, cy = int(rx), int(ry)''',
     '''                prog = max(0.0, min(1.0, float(r.get("t", 0.0)) / max(0.01, float(r.get("delay", 1.0)))))
                # 闭合阶段：半径与亮度一起收掉
                _fade = float(r.get("fade", 0.0))
                _fm = max(0.01, float(r.get("fade_max", 0.34)))
                shrink = 1.0
                dim = 1.0
                if _fade > 0.0:
                    shrink = max(0.0, _fade / _fm)
                    dim = shrink ** 0.7
                base = float(r.get("size", 28.0)) * (0.52 + 0.48 * prog) * (0.55 + 0.45 * shrink)
                wide = base * 1.05
                tall = base * 0.86
                cx, cy = int(rx), int(ry)''', "fade_geom")

rep2('''                # 外层辉光（3 层）
                for k in range(3):
                    rr = 1.0 + k * 0.30
                    a = int((30 + 26 * prog) / (1 + k * 0.7))
                    pygame.draw.ellipse(surf, theme.alpha_color((146, 84, 236), a),
                                        (cx - wide * rr, cy - tall * rr,
                                         wide * 2 * rr, tall * 2 * rr))''',
     '''                # 外层辉光（5 层，越外越淡）
                for k in range(5):
                    rr = 1.0 + k * 0.22
                    a = int((26 + 22 * prog) * dim / (1 + k * 0.55))
                    pygame.draw.ellipse(surf, theme.alpha_color((138, 78, 232), a),
                                        (cx - wide * rr, cy - tall * rr,
                                         wide * 2 * rr, tall * 2 * rr))
                # 辐射光线（引力透镜感：从边缘向外拉出细丝）
                for k in range(10):
                    ang = k * 0.628 + t * 0.5
                    r0 = wide * 1.02
                    r1 = wide * (1.18 + 0.14 * math.sin(t * 2.6 + k * 1.7))
                    pygame.draw.line(surf, theme.alpha_color((176, 122, 250), int(78 * dim)),
                                     (cx + math.cos(ang) * r0, cy + math.sin(ang) * r0 * 0.82),
                                     (cx + math.cos(ang) * r1, cy + math.sin(ang) * r1 * 0.82), 1)''',
     "glow_rays")

rep2('''                # 核心：深紫近黑 + 内缘亮边
                pygame.draw.ellipse(surf, (18, 6, 30),
                                    (cx - wide * 0.86, cy - tall * 0.86,
                                     wide * 1.72, tall * 1.72))
                pygame.draw.ellipse(surf, theme.alpha_color((92, 40, 150), 220),
                                    (cx - wide * 0.86, cy - tall * 0.86,
                                     wide * 1.72, tall * 1.72), 2)
                pygame.draw.ellipse(surf, theme.alpha_color((216, 176, 255), int(120 + 110 * prog)),
                                    (cx - wide * 0.92, cy - tall * 0.92,
                                     wide * 1.84, tall * 1.84), 2)''',
     '''                # 核心：径向渐变的"深洞"（中心近黑，向外透紫），比单色圆更像塌缩
                for k in range(7):
                    f = k / 6.0                      # 0 内 -> 1 外
                    rr = 0.90 - 0.52 * f
                    sh = int(8 + 30 * f)
                    pygame.draw.ellipse(surf,
                                        (sh, max(2, int(sh * 0.30)), min(255, sh + 14)),
                                        (cx - wide * rr, cy - tall * rr,
                                         wide * 2 * rr, tall * 2 * rr))
                # 内缘亮边（环状，不填满）
                pygame.draw.ellipse(surf, theme.alpha_color((148, 92, 226), int(210 * dim)),
                                    (cx - wide * 0.90, cy - tall * 0.90,
                                     wide * 1.80, tall * 1.80), 2)
                pygame.draw.ellipse(surf, theme.alpha_color((224, 190, 255), int((110 + 120 * prog) * dim)),
                                    (cx - wide * 0.96, cy - tall * 0.96,
                                     wide * 1.92, tall * 1.92), 1)''',
     "core_gradient")

rep2('''                # 吸入粒子：从外圈螺旋掉进核心
                for k in range(7):
                    ph = (t * 1.35 + k / 7.0) % 1.0
                    rr = 2.05 - ph * 1.55
                    ang = k * 0.9 + t * 2.6 + ph * 3.1
                    px = cx + math.cos(ang) * wide * rr
                    py = cy + math.sin(ang) * tall * rr
                    a2 = int(235 * (1.0 - ph) * (0.45 + 0.55 * prog))
                    pygame.draw.circle(surf, theme.alpha_color((228, 190, 255), a2),
                                       (int(px), int(py)), 2 if ph < 0.6 else 1)''',
     '''                # 吸入粒子：从外圈螺旋掉进核心（外层大点、内层亮点）
                for k in range(9):
                    ph = (t * 1.25 + k / 9.0) % 1.0
                    rr = 2.10 - ph * 1.60
                    ang = k * 0.7 + t * 2.4 + ph * 3.4
                    px = cx + math.cos(ang) * wide * rr
                    py = cy + math.sin(ang) * tall * rr
                    a2 = int(245 * (1.0 - ph) * (0.45 + 0.55 * prog) * dim)
                    rad = 3 if ph < 0.35 else (2 if ph < 0.7 else 1)
                    pygame.draw.circle(surf, theme.alpha_color((214, 168, 255), a2),
                                       (int(px), int(py)), rad)
                    if ph < 0.5:
                        pygame.draw.circle(surf, theme.alpha_color((255, 245, 255), int(a2 * 0.7)),
                                           (int(px), int(py)), 1)''',
     "particles")

rep2('''                # 即将开启：边缘闪烁提示
                if prog > 0.72:''',
     '''                # 即将开启：边缘闪烁提示
                if prog > 0.72 and _fade <= 0.0:''',
     "flicker_guard")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_fade_r_log.txt", "w", encoding="utf-8").write(" | ".join(log2))
print("done")
