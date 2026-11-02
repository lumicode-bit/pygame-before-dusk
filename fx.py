# -*- coding: utf-8 -*-
"""
fx.py —— 视觉特效层
============================================================================
  * Camera        —— 平滑跟随 + 创伤式屏幕震动 + 世界/屏幕坐标换算
  * Particles     —— 池化粒子系统（尘土/火花/血/碎片/余烬/治疗/魔法）
  * FloatingText  —— 伤害与提示飘字
  * Background    —— 程序化多层视差背景（星空/远山/林线/雾）
  * PostFX        —— 暗角、受伤红闪、区域色调、过场淡入淡出

全部程序化生成，不依赖外部图片。
"""
import math
import random

import pygame

import theme

SCREEN_W, SCREEN_H = 1280, 720

# --------------------------------------------------------------------------
# 相机
# --------------------------------------------------------------------------
class Camera:
    """平滑跟随 + 震动。震动采用"创伤值"模型：t^2 衰减，多个来源可叠加。"""

    def __init__(self, view_w, view_h):
        self.x = 0.0
        self.y = 0.0
        self.vw = view_w
        self.vh = view_h
        self.trauma = 0.0
        self.ox = 0.0
        self.oy = 0.0
        self._t = 0.0

    trauma_mul = 1.0        # 全局震屏强度（设置里可调）

    def add_trauma(self, amount):
        # 累积加阻尼：直接线性叠加的话，被连续打两三下 trauma 就冲到 1.0，
        # 屏幕抖得看不清人。改成"先衰减再叠加"，连续受击也不会失控。
        a = amount * Camera.trauma_mul
        self.trauma = min(1.0, self.trauma * 0.78 + a)

    def snap(self, tx, ty, bounds):
        self.x, self.y = self._clamp(tx - self.vw / 2.0, ty - self.vh / 2.0, bounds)
        self.ox = self.oy = 0.0

    def _clamp(self, x, y, bounds):
        """x/y 为相机左上角坐标（像素）。"""
        w, h = bounds
        x = max(0.0, min(max(0.0, w - self.vw), x))
        y = max(0.0, min(max(0.0, h - self.vh), y))
        return x, y

    def update(self, dt, target_x, target_y, bounds, speed=7.5):
        tx = target_x - self.vw / 2.0
        ty = target_y - self.vh / 2.0
        # 水平跟随更快，垂直稍慢以避免跳跃时画面上下抽搐
        self.x = theme.approach(self.x, tx, speed, dt)
        self.y = theme.approach(self.y, ty, speed * 0.62, dt)
        self.x, self.y = self._clamp(self.x, self.y, bounds)

        self._t += dt
        self.trauma = max(0.0, self.trauma - dt * 1.35)
        mag = self.trauma * self.trauma
        if mag > 0.0005:
            self.ox = random.uniform(-1, 1) * 12.5 * mag
            self.oy = random.uniform(-1, 1) * 9.5 * mag
        else:
            self.ox = self.oy = 0.0

    @property
    def px(self):
        return int(self.x + self.ox)

    @property
    def py(self):
        return int(self.y + self.oy)


# --------------------------------------------------------------------------
# 粒子
# --------------------------------------------------------------------------
_PRESETS = {
    # name: (count, speed, life, size, gravity, drag, kind)
    "dust": (7, 70, 0.55, 3, 220, 3.0, "soft"),
    "jump": (9, 120, 0.45, 3, 320, 3.4, "soft"),
    "land": (14, 170, 0.5, 4, 300, 3.0, "soft"),
    "blood": (10, 190, 0.7, 3, 760, 1.2, "hard"),
    "spark": (10, 300, 0.35, 2, 520, 2.0, "glow"),
    "ember": (5, 45, 1.2, 2, -35, 0.6, "glow"),
    "debris": (9, 230, 0.8, 3, 900, 1.0, "hard"),
    "heal": (12, 90, 1.0, 3, -150, 1.4, "glow"),
    "magic": (12, 140, 0.8, 3, -60, 1.6, "glow"),
    "smoke": (8, 60, 1.1, 6, -70, 1.2, "smoke"),
}


class Particles:
    """轻量粒子池。粒子是简单 list，避免对象开销。"""

    def __init__(self, cap=900):
        self.items = []
        self.cap = cap
        self.enabled = True

    def burst(self, kind, x, y, color, count=None, spread=None, power=1.0, angle_dir=None):
        if not self.enabled:
            return
        try:
            cfg = _PRESETS.get(kind, _PRESETS["spark"])
            cnt, spd, life, size, grav, drag, ptype = cfg
            n = int(count if count is not None else cnt)
            if len(self.items) > self.cap:
                return
            for _ in range(n):
                if angle_dir is None:
                    a = random.uniform(0, math.pi * 2)
                else:
                    a = angle_dir + random.uniform(-0.9, 0.9)
                v = spd * random.uniform(0.35, 1.0) * power
                lf = life * random.uniform(0.7, 1.25)
                self.items.append([
                    float(x), float(y),
                    math.cos(a) * v, math.sin(a) * v * (0.55 if spread is None else spread),
                    lf, lf,
                    size * random.uniform(0.7, 1.3) * (power ** 0.3),
                    color, grav, drag, ptype,
                ])
        except Exception:
            pass

    def trail(self, x, y, color, size=2, life=0.3, drift=(0, 0)):
        if not self.enabled or len(self.items) > self.cap:
            return
        self.items.append([float(x), float(y), drift[0], drift[1],
                           life, life, size, color, -10.0, 1.0, "glow"])

    def update(self, dt):
        out = []
        for p in self.items:
            p[4] -= dt
            if p[4] <= 0:
                continue
            # 不能把 p[5]（初始寿命）改写成剩余寿命：draw 里 t=p[4]/p[5] 恒为 1，
            # 所有粒子全亮度全尺寸、到期瞬间消失，淡出完全失效
            p[3] += p[8] * dt
            d = max(0.0, 1.0 - p[9] * dt)
            p[2] *= d
            p[3] *= d
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            out.append(p)
        self.items = out

    def draw(self, surf, cam_x, cam_y):
        for p in self.items:
            try:
                t = p[4] / p[5]
                sx = int(p[0] - cam_x)
                sy = int(p[1] - cam_y)
                if sx < -40 or sx > SCREEN_W + 40 or sy < -40 or sy > SCREEN_H + 40:
                    continue
                size = max(1, int(p[6] * (0.35 + 0.65 * t)))
                col = p[7]
                ptype = p[10]
                if ptype == "glow":
                    a = int(200 * t)
                    if a <= 3:
                        continue
                    s = pygame.Surface((size * 4 + 2, size * 4 + 2), pygame.SRCALPHA)
                    pygame.draw.circle(s, theme.alpha_color(col, a // 3), (size * 2 + 1, size * 2 + 1), size * 2)
                    pygame.draw.circle(s, theme.alpha_color(col, a), (size * 2 + 1, size * 2 + 1), size)
                    surf.blit(s, (sx - size * 2 - 1, sy - size * 2 - 1),
                              special_flags=pygame.BLEND_RGBA_ADD)
                elif ptype == "smoke":
                    a = int(70 * t)
                    s = pygame.Surface((size * 3, size * 3), pygame.SRCALPHA)
                    pygame.draw.circle(s, theme.alpha_color(col, a), (size * 3 // 2, size * 3 // 2), size * 3 // 2)
                    surf.blit(s, (sx - size * 3 // 2, sy - size * 3 // 2))
                elif ptype == "hard":
                    c = theme.mix(col, (20, 16, 24), 1.0 - t)
                    pygame.draw.rect(surf, c, (sx, sy, size, size))
                else:
                    a = int(150 * t)
                    if a <= 4:
                        continue
                    s = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
                    pygame.draw.circle(s, theme.alpha_color(col, a), (size, size), size)
                    surf.blit(s, (sx - size, sy - size))
            except Exception:
                pass


# --------------------------------------------------------------------------
# 飘字
# --------------------------------------------------------------------------
class FloatingText:
    def __init__(self):
        self.items = []

    def add(self, x, y, txt, color=theme.CREAM, size="label", vy=-52.0, life=1.0, bold=False):
        self.items.append([float(x), float(y), str(txt), color, size, vy, life, life, bold])

    def update(self, dt):
        out = []
        for it in self.items:
            it[6] -= dt
            if it[6] <= 0:
                continue
            it[1] += it[5] * dt
            it[5] *= (1.0 - 2.0 * dt)
            out.append(it)
        self.items = out

    def draw(self, surf, cam_x, cam_y):
        for it in self.items:
            try:
                t = max(0.0, min(1.0, it[6] / max(0.001, it[7])))
                a = 1.0 if t > 0.6 else t / 0.6
                theme.text(surf, it[2], (it[0] - cam_x, it[1] - cam_y), it[4],
                           it[3], align="center", alpha_mul=a, bold=it[8],
                           outline=2 if it[8] else 0)
            except Exception:
                pass


# --------------------------------------------------------------------------
# 程序化视差背景
# --------------------------------------------------------------------------
class Background:
    """按世界坐标滚动多层剪影背景。

    调色随世界 x 推进而改变：暮色森林（青蓝/紫）→ 熔岩荒野（暗红/橙）。
    """

    def __init__(self, world_w):
        self.W = world_w
        self.layers = []
        self._build()
        self._sky_cache = {}
        self._sky_key = None
        self._stars = [(random.uniform(0, 1), random.uniform(0, 0.45),
                        random.uniform(0.6, 1.8), random.uniform(0.6, 1.0)) for _ in range(90)]

    # ---- 生成 ----
    def _silhouette(self, w, h, base_y, amp, color, seed, jag=1.0, trees=0, tree_col=None,
                    rim=None):
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        rnd = random.Random(seed)
        pts = []
        n = 128
        phase = [rnd.uniform(0, 6.28) for _ in range(4)]
        for i in range(n + 1):
            t = i / n
            x = t * w
            ridge = (math.sin(t * 6.28 * 1.5 + phase[0]) * 0.52 +
                     math.sin(t * 6.28 * 4 + phase[1]) * 0.30 * jag +
                     math.sin(t * 6.28 * 9 + phase[2]) * 0.16 * jag +
                     math.sin(t * 6.28 * 21 + phase[3]) * 0.06 * jag)
            y = base_y - ridge * amp
            pts.append((x, y))
        body = list(pts) + [(w, h), (0, h)]
        pygame.draw.polygon(s, color, body)
        # 山脊轮廓光：暮光从上方打下来，勾出一道亮边，大幅增加层次
        if rim:
            pygame.draw.lines(s, rim, False, pts, 2)
        # 林线：在轮廓上加点针叶树剪影
        if trees:
            tc = tree_col or theme.shade(color, -0.12)
            for _ in range(trees):
                tx = rnd.uniform(0, w)
                th = rnd.uniform(amp * 1.2, amp * 2.8)
                tw = th * rnd.uniform(0.24, 0.34)
                ty = base_y - rnd.uniform(-amp * 0.35, amp * 0.85)
                pygame.draw.polygon(s, tc, [(tx, ty - th), (tx - tw, ty), (tx + tw, ty)])
                pygame.draw.rect(s, theme.shade(tc, -0.2), (tx - 2, ty, 4, th * 0.14))
        return s

    def _build(self):
        w = 1600
        h = 720
        # 远山（偏蓝的雾色，最低对比）
        far = self._silhouette(w, h, 470, 120, (62, 68, 112), 11, jag=0.75,
                              rim=(96, 100, 146))
        # 中景山脊（带林线）
        mid = self._silhouette(w, h, 552, 96, (40, 44, 80), 23, jag=0.95, trees=18,
                              tree_col=(36, 39, 70), rim=(78, 74, 112))
        # 近景林带（最深，压住画面底部）
        near = self._silhouette(w, h, 640, 58, (22, 24, 46), 37, jag=1.15, trees=24,
                                tree_col=(19, 21, 40), rim=(58, 56, 84))
        raw = [
            {"surf": far, "par": 0.10, "y": 30},
            {"surf": mid, "par": 0.20, "y": 46},
            {"surf": near, "par": 0.34, "y": 56},
        ]
        self.layers = []
        for l in raw:
            try:
                br = l["surf"].get_bounding_rect()
                if br.w > 0 and br.h > 0:
                    self.layers.append({"surf": l["surf"].subsurface(br).copy(),
                                        "par": l["par"], "y": l["y"] + br.y})
                else:
                    self.layers.append(l)
            except Exception:
                self.layers.append(l)
        # 云：预渲染成 4 张，避免每帧新建 Surface
        self._clouds = []
        for i, (cx0, cy0, cw, ch, cs) in enumerate((
                (0, 190, 520, 34, 0.03), (300, 250, 420, 26, 0.05),
                (700, 160, 560, 30, 0.04), (1000, 300, 380, 22, 0.06))):
            csurf = pygame.Surface((int(cw * 1.35), int(ch * 2.4)), pygame.SRCALPHA)
            for kk in range(5):
                ww = cw * (0.55 + 0.12 * kk)
                hh = ch * (0.8 + 0.1 * kk)
                a = 26 - kk * 4
                if a <= 0:
                    continue
                tmp = pygame.Surface((max(2, int(ww)), max(2, int(hh))), pygame.SRCALPHA)
                pygame.draw.ellipse(tmp, (255, 230, 235, a), (0, 0, max(2, int(ww)), max(2, int(hh))))
                csurf.blit(tmp, (kk * 26, kk * 6))
            self._clouds.append({"surf": csurf, "x": cx0, "y": cy0, "s": cs})

    # ---- 天空 ----
    def _sky_surface(self, kind, w, h):
        key = (kind, w, h)
        if key in self._sky_cache:
            return self._sky_cache[key]
        s = pygame.Surface((w, h))
        if kind == "dusk":
            top, bot = (22, 24, 52), (94, 60, 90)
            midc = (58, 44, 82)
        elif kind == "forge":
            top, bot = (26, 14, 22), (128, 44, 32)
            midc = (74, 26, 28)
        else:
            top, bot = (30, 34, 70), (150, 108, 92)
            midc = (74, 62, 92)
        theme.gradient_rect(s, (0, 0, w, h), top, bot)
        band = pygame.Surface((w, int(h * 0.36)), pygame.SRCALPHA)
        bh = band.get_height()
        for i in range(bh):
            a = int(52 * math.sin(math.pi * i / float(bh)))
            pygame.draw.line(band, theme.alpha_color(midc, a), (0, i), (w, i))
        s.blit(band, (0, h // 2 - bh // 2))
        self._sky_cache[key] = s
        return s

    def _ensure_scaled(self, w, h):
        if getattr(self, "_scaled_for", None) == (w, h):
            return
        k = h / 720.0
        self._clouds_s = []
        for c in self._clouds:
            cw = max(2, int(c["surf"].get_width() * k))
            ch = max(2, int(c["surf"].get_height() * k))
            self._clouds_s.append(pygame.transform.scale(c["surf"], (cw, ch)))
        # 月亮辉光（预渲染，避免每帧分配）
        gr = max(6, int(46 * k))
        g = pygame.Surface((gr * 2 + 2, gr * 2 + 2), pygame.SRCALPHA)
        for i in range(5, 0, -1):
            rr = int(gr * i / 5.0)
            f = 0.16 * 0.42 * (1.0 - (i - 1) / 5.0)
            pygame.draw.circle(g, (int(226 * f), int(224 * f), int(250 * f)), (gr + 1, gr + 1), rr)
        self._moon_glow = g
        self._scaled_for = (w, h)

    def draw(self, surf, cam_x, cam_y, t, region=0.0):
        """region: 0=暮色森林 1=熔岩荒野（用于混合色调）"""
        w, h = surf.get_size()
        k = h / 720.0
        self._ensure_scaled(w, h)
        surf.blit(self._sky_surface("dusk", w, h), (0, 0))
        # 进入熔炉区时天空交叉淡入（避免硬切）
        fr = theme.clamp(region * 1.55)
        if fr > 0.01:
            forge = self._sky_surface("forge", w, h)
            if fr >= 0.99:
                surf.blit(forge, (0, 0))
            else:
                tmp = forge.copy()
                tmp.set_alpha(int(255 * fr))
                surf.blit(tmp, (0, 0))

        # 星星（只在暮色段明显，缓慢闪烁）
        if region < 0.55:
            fade = 1.0 - region / 0.55
            for sx, sy, sz, br in self._stars:
                tw = 0.55 + 0.45 * math.sin(t * 1.6 + sx * 40)
                a = int(190 * br * tw * fade)
                if a <= 4:
                    continue
                x = int(sx * w)
                y = int(sy * h * 0.8)
                pygame.draw.circle(surf, (255, 246, 220), (x, y), 1)

        # 月亮 / 落日（弱光晕，避免抢标题与角色）
        mx = w * 0.81 - cam_x * 0.02
        my = h * 0.18 - cam_y * 0.02
        theme.glow_circle(surf, (mx, my), int(52 * k),
                          (255, 206, 168) if region > 0.5 else (222, 220, 250), 0.5, 4)
        pygame.draw.circle(surf, (255, 238, 212) if region < 0.5 else (255, 186, 140),
                           (int(mx), int(my)), max(10, int(24 * k)))
        pygame.draw.circle(surf, (255, 250, 236) if region < 0.5 else (255, 214, 178),
                           (int(mx - 6 * k), int(my - 6 * k)), max(3, int(9 * k)))

        # 地平线暖光（暮光带）
        hh = int(220 * k)
        hz = pygame.Surface((w, hh), pygame.SRCALPHA)
        hcol = (168, 116, 132) if region < 0.5 else (176, 84, 56)
        for i in range(hh):
            a = int(56 * math.sin(math.pi * i / float(hh)) ** 1.6)
            pygame.draw.line(hz, theme.alpha_color(hcol, a), (0, i), (w, i))
        surf.blit(hz, (0, int(372 * k) - int(cam_y * 0.06)))

        # 云带（预渲染，单次 blit）
        for i, c in enumerate(self._clouds):
            csurf = self._clouds_s[i]
            cw = csurf.get_width()
            if cw < 4:
                continue
            cx = (c["x"] * w / 1280.0 - cam_x * c["s"] + t * (7 + i * 3)) % (w + cw) - cw * 0.3
            cy = c["y"] * k - cam_y * c["s"]
            surf.blit(csurf, (cx, cy))

        # 剪影层
        for layer in self.layers:
            par = layer["par"]
            ox = int(-(cam_x * par) % 1600)
            oy = int(layer["y"] * k - cam_y * par * 0.55)
            # 画 (ox-1600, ox)：贴图本身 1600 宽，用 (ox, ox+1600) 时
            # ox>=800 两张都落在屏幕右侧之外，山体/林线在半程整层消失
            surf.blit(layer["surf"], (ox - 1600, oy))
            surf.blit(layer["surf"], (ox, oy))

        # 地平雾带（很轻，上下都柔化，用于拉开空间层次）
        fh = int(150 * k)
        fog = pygame.Surface((w, fh), pygame.SRCALPHA)
        fcol = (120, 110, 160) if region < 0.5 else (168, 86, 60)
        for i in range(fh):
            a = int(26 * math.sin(math.pi * i / float(max(1, fh))) ** 1.2)
            pygame.draw.line(fog, theme.alpha_color(fcol, a), (0, i), (w, i))
        surf.blit(fog, (0, int(470 * k) - int(cam_y * 0.18)))


# --------------------------------------------------------------------------
# 后处理
# --------------------------------------------------------------------------
class PostFX:
    def __init__(self):
        self._vignette = self._make_vignette()
        self._damage = self._make_damage_vig()
        self.flash = 0.0
        self.flash_color = (255, 255, 255)
        self.full_flash = False
        self.fade = 0.0
        self._fade_target = 0.0
        self._fade_speed = 2.0
        self.damage = 0.0
        self.flash_mul = 1.0

    def _make_damage_vig(self):
        s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        for i in range(26):
            a = int(38 * (1 - i / 26.0) ** 1.7)
            if a <= 0:
                continue
            pygame.draw.rect(s, (188, 22, 28, a),
                             (i * 5, i * 5, SCREEN_W - i * 10, SCREEN_H - i * 10),
                             10, border_radius=24)
        return s

    def _make_vignette(self):
        s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        cx, cy = SCREEN_W / 2, SCREEN_H / 2
        maxd = math.hypot(cx, cy)
        step = 4
        for yy in range(0, SCREEN_H, step):
            for xx in range(0, SCREEN_W, step):
                d = math.hypot(xx - cx, yy - cy) / maxd
                a = int(150 * max(0.0, d - 0.42) ** 1.6 * 2.2)
                if a > 2:
                    pygame.draw.rect(s, (4, 4, 10, min(190, a)), (xx, yy, step, step))
        return s

    def hit_flash(self, color=(255, 60, 60), amount=0.55, full=False):
        self.flash = max(self.flash, amount)
        self.flash_color = color
        self.full_flash = bool(full)

    def add_damage(self, amount=0.7):
        self.damage = min(1.0, self.damage + amount)

    def fade_to(self, target, speed=2.0):
        self._fade_target = max(0.0, min(1.0, target))
        self._fade_speed = speed

    def update(self, dt):
        self.flash = max(0.0, self.flash - dt * 2.6)
        self.damage = max(0.0, self.damage - dt * 1.9)
        if abs(self.fade - self._fade_target) < 0.002:
            self.fade = self._fade_target
        else:
            step = self._fade_speed * dt
            self.fade += max(-step, min(step, self._fade_target - self.fade))

    def draw(self, surf):
        surf.blit(self._vignette, (0, 0))
        if self.damage > 0.01:
            dmg = self._damage.copy()
            dmg.set_alpha(int(255 * min(1.0, self.damage)))
            surf.blit(dmg, (0, 0))
        if self.flash > 0.01:
            s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            a = int((150 if self.full_flash else 56) * self.flash *
                    getattr(self, "flash_mul", 1.0))
            s.fill(theme.alpha_color(self.flash_color, a))
            surf.blit(s, (0, 0))

    def draw_fade(self, surf):
        if self.fade > 0.005:
            s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            s.fill((5, 6, 12, int(255 * self.fade)))
            surf.blit(s, (0, 0))


def screen_shake_for_event(kind):
    """事件 -> 震动强度映射"""
    return {
        "die": 0.28, "rock_break": 0.42, "hit": 0.12, "hurt": 0.34,
        "block": 0.18, "pad": 0.1, "portal": 0.5, "win": 0.6,
        "impale": 0.55, "hammer": 0.45, "spike_hit": 0.3, "land": 0.06,
        "break": 0.08, "dash": 0.08, "explode": 0.4,
        "bloom": 0.2, "boss_windup": 0.12, "egg_throw": 0.05, "erupt": 0.3,
    }.get(kind, 0.0)
