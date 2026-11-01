# -*- coding: utf-8 -*-
"""v2.9 渲染：紫色裂隙（黑洞）+ 怪物出场动画。"""
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


# ---------- 1) 裂隙画在怪物之前（黑洞在后，怪从里面浮出来） ----------
rep("        self._draw_shockwaves(surf, cam_x, cam_y, st)\n"
    "        self._draw_monsters(surf, cam_x, cam_y, t, st)",
    "        self._draw_shockwaves(surf, cam_x, cam_y, st)\n"
    "        self._draw_rifts(surf, cam_x, cam_y, t, st)\n"
    "        self._draw_monsters(surf, cam_x, cam_y, t, st)", "rift_call")

# ---------- 2) 裂隙绘制 ----------
rep("    def _draw_monsters(self, surf, cam_x, cam_y, t, st):",
    '''    def _draw_rifts(self, surf, cam_x, cam_y, t, st):
        """刷怪前兆：紫色裂隙/黑洞。

        结构（由外到内）：外层辉光 -> 双向旋转光环 -> 引力弧 -> 深紫核心 -> 吸入粒子。
        进度 t/delay 驱动半径与亮度，越接近开启越亮越大。
        """
        for r in st.get("rifts", []):
            try:
                rx = float(r["x"]) - cam_x
                ry = float(r["y"]) - cam_y
                if rx < -140 or rx > surf.get_width() + 140:
                    continue
                prog = max(0.0, min(1.0, float(r.get("t", 0.0)) / max(0.01, float(r.get("delay", 1.0)))))
                base = float(r.get("size", 28.0)) * (0.52 + 0.48 * prog)
                wide = base * 1.05
                tall = base * 0.74
                cx, cy = int(rx), int(ry)

                # 地面投影光斑（让黑洞"坐"在地上，而不是浮着）
                spot = pygame.Surface((int(wide * 3.2), int(tall * 1.6)), pygame.SRCALPHA)
                for k in range(6, 0, -1):
                    f = k / 6.0
                    a = int(16 * prog * (1.0 - f) + 6)
                    pygame.draw.ellipse(spot, (120, 60, 200, a),
                                        (int(wide * 1.6 * (1 - f)), int(tall * 0.8 * (1 - f)),
                                         int(wide * 3.2 * f), int(tall * 1.6 * f)))
                surf.blit(spot, (cx - spot.get_width() // 2, cy - spot.get_height() // 2))

                # 外层辉光（3 层）
                for k in range(3):
                    rr = 1.0 + k * 0.30
                    a = int((30 + 26 * prog) / (1 + k * 0.7))
                    pygame.draw.ellipse(surf, theme.alpha_color((146, 84, 236), a),
                                        (cx - wide * rr, cy - tall * rr,
                                         wide * 2 * rr, tall * 2 * rr))
                # 双向旋转光环
                for k in range(2):
                    sgn = 1.0 if k == 0 else -1.0
                    ang = t * (2.3 + k * 1.4) * sgn + k * 1.9
                    rr = 1.12 + k * 0.20
                    rect = (cx - wide * rr, cy - tall * rr, wide * 2 * rr, tall * 2 * rr)
                    pygame.draw.arc(surf, theme.alpha_color((205, 158, 255), 190),
                                    rect, ang, ang + 2.1, 2)
                    pygame.draw.arc(surf, theme.alpha_color((255, 226, 255), 130),
                                    rect, ang + 0.35, ang + 1.35, 1)
                # 引力弧（向内收的短弧，制造"被吸进去"的感觉）
                for k in range(5):
                    ang = t * 1.9 + k * 1.256
                    rr = 0.94 + 0.10 * math.sin(t * 3.0 + k)
                    rect = (cx - wide * rr, cy - tall * rr, wide * 2 * rr, tall * 2 * rr)
                    pygame.draw.arc(surf, theme.alpha_color((180, 120, 250), 150),
                                    rect, ang, ang + 0.55, 1)
                # 核心：深紫近黑 + 内缘亮边
                pygame.draw.ellipse(surf, (18, 6, 30),
                                    (cx - wide * 0.86, cy - tall * 0.86,
                                     wide * 1.72, tall * 1.72))
                pygame.draw.ellipse(surf, theme.alpha_color((92, 40, 150), 220),
                                    (cx - wide * 0.86, cy - tall * 0.86,
                                     wide * 1.72, tall * 1.72), 2)
                pygame.draw.ellipse(surf, theme.alpha_color((216, 176, 255), int(120 + 110 * prog)),
                                    (cx - wide * 0.92, cy - tall * 0.92,
                                     wide * 1.84, tall * 1.84), 2)
                # 核心内的一点亮心（越接近开启越亮）
                theme.glow_circle(surf, (cx, cy), int(base * 0.55),
                                  (198, 140, 255), 0.30 + 0.32 * prog, 2)

                # 吸入粒子：从外圈螺旋掉进核心
                for k in range(7):
                    ph = (t * 1.35 + k / 7.0) % 1.0
                    rr = 2.05 - ph * 1.55
                    ang = k * 0.9 + t * 2.6 + ph * 3.1
                    px = cx + math.cos(ang) * wide * rr
                    py = cy + math.sin(ang) * tall * rr
                    a2 = int(235 * (1.0 - ph) * (0.45 + 0.55 * prog))
                    pygame.draw.circle(surf, theme.alpha_color((228, 190, 255), a2),
                                       (int(px), int(py)), 2 if ph < 0.6 else 1)
                # 即将开启：边缘闪烁提示
                if prog > 0.72:
                    flick = 0.5 + 0.5 * math.sin(t * 22.0)
                    pygame.draw.ellipse(surf, theme.alpha_color((255, 214, 255), int(150 * flick)),
                                        (cx - wide * 0.92, cy - tall * 0.92,
                                         wide * 1.84, tall * 1.84), 2)
            except Exception as e:
                if not getattr(_draw_rifts, "_warned", False):
                    _draw_rifts._warned = True
                    print("[裂隙绘制异常] %r" % (e,))

    def _draw_monsters(self, surf, cam_x, cam_y, t, st):''', "rift_draw")

# ---------- 3) 怪物出场动画：淡入 + 上浮 ----------
rep('''        for m in st.get("monsters", []):
            try:
                kind = m["kind"]''',
    '''        for m in st.get("monsters", []):
            try:
                kind = m["kind"]
                # 出场动画：0 -> 1（从黑洞里浮上来 + 淡入）
                _prog = None
                if m.get("state") == "spawn":
                    _prog = 1.0 - max(0.0, float(m.get("state_t", 0.0))) / 0.55
                    _prog = max(0.0, min(1.0, _prog))
                _yoff = int((1.0 - _prog) * 22) if _prog is not None else 0''',
    "monster_spawn_head")

rep('''                frame = int(t * 7 + m["mid"] * 0.7) % 2
                img = sprites.get_monster(kind, frame)
                wob = math.sin(t * 5 + m["mid"] * 1.7) * 2.0
                if m.get("elite"):
                    w0, h0 = img.get_size()
                    img = pygame.transform.scale(img, (int(w0 * 1.3), int(h0 * 1.3)))
                r = img.get_rect()
                if kind == "caster":
                    theme.glow_circle(surf, (int(m["x"]) - cam_x, int(m["y"]) - 22 - cam_y),
                                      34, (150, 110, 220), 0.45, 3)
                    r.midbottom = (int(m["x"]) - cam_x, int(m["y"]) - cam_y)
                elif kind == "fly":
                    r.center = (int(m["x"]) - cam_x, int(m["y"]) - 12 + int(wob))
                    theme.glow_circle(surf, r.center, 20, (190, 110, 240), 0.22, 2)
                else:
                    r.midbottom = (int(m["x"]) - cam_x, int(m["y"]) - cam_y + 2)
                    theme.soft_shadow(surf, int(m["x"]) - cam_x, int(m["y"]) - cam_y, 30, 7, 90)''',
    '''                frame = int(t * 7 + m["mid"] * 0.7) % 2
                img = sprites.get_monster(kind, frame)
                wob = math.sin(t * 5 + m["mid"] * 1.7) * 2.0
                if m.get("elite"):
                    w0, h0 = img.get_size()
                    img = pygame.transform.scale(img, (int(w0 * 1.3), int(h0 * 1.3)))
                if _prog is not None:
                    img = img.copy()
                    img.set_alpha(int(255 * min(1.0, _prog * 1.5)))
                r = img.get_rect()
                if kind == "caster":
                    theme.glow_circle(surf, (int(m["x"]) - cam_x, int(m["y"]) - 22 - cam_y + _yoff),
                                      34, (150, 110, 220), 0.45, 3)
                    r.midbottom = (int(m["x"]) - cam_x, int(m["y"]) - cam_y + _yoff)
                elif kind == "fly":
                    r.center = (int(m["x"]) - cam_x, int(m["y"]) - 12 + int(wob) + _yoff)
                    theme.glow_circle(surf, r.center, 20, (190, 110, 240), 0.22, 2)
                else:
                    r.midbottom = (int(m["x"]) - cam_x, int(m["y"]) - cam_y + 2 + _yoff)
                    theme.soft_shadow(surf, int(m["x"]) - cam_x, int(m["y"]) - cam_y + _yoff, 30, 7, 90)
                if _prog is not None and _prog < 0.95:
                    # 出场时脚下带一圈紫色余晖，视觉上"从裂隙里涌出来"
                    theme.glow_circle(surf, (r.centerx, r.bottom), 30,
                                      (170, 110, 250), 0.30 * (1.0 - _prog) + 0.10, 3)''',
    "monster_spawn_body")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_v29r_log.txt", "w", encoding="utf-8").write(" | ".join(log))
print("done")
