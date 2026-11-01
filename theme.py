# -*- coding: utf-8 -*-
"""
theme.py —— 《暮色之前》视觉设计系统
============================================================================
统一管理：配色 / 字体 / 绘图原语 / 缓动函数 / 文本渲染缓存。

设计语言（"暮色"）：
  * 深靛蓝夜色底 + 品红→橙金暮光高光，营造黄昏进入黑夜的过渡感；
  * 面板采用"玻璃拟态 + 细描边 + 内高光"，避免纯色块的廉价感；
  * 所有文本默认带 1px 深色投影，保证任何背景上的可读性。

本模块不依赖项目内其它模块，可被任意层安全导入。
"""
import os
import math
import pygame

# --------------------------------------------------------------------------
# 调色板
# --------------------------------------------------------------------------
INK_950 = (7, 9, 17)
INK_900 = (11, 14, 26)
INK_800 = (18, 22, 39)
INK_700 = (26, 32, 54)
INK_600 = (37, 44, 70)
INK_500 = (52, 61, 92)
SLATE_400 = (107, 117, 153)
SLATE_300 = (148, 158, 190)
SLATE_200 = (185, 194, 220)
SLATE_100 = (219, 225, 240)
CREAM = (245, 239, 226)

GOLD = (242, 193, 78)
GOLD_LIGHT = (255, 227, 155)
GOLD_DARK = (176, 130, 38)
EMBER = (255, 122, 61)
MAGENTA = (228, 82, 126)
ROSE = (255, 138, 168)
TEAL = (78, 214, 196)
TEAL_DARK = (32, 132, 124)
DANGER = (255, 90, 95)
BLOOD = (186, 32, 40)
LIME = (154, 230, 120)
SKY = (120, 190, 255)

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

# 角色主题色
ARCHER_COL = (126, 176, 240)
SHIELD_COL = (231, 172, 104)


def alpha(color, a):
    """给颜色加上 alpha（返回 4 元组）"""
    try:
        return (color[0], color[1], color[2], max(0, min(255, int(a))))
    except Exception:
        return (255, 255, 255, max(0, min(255, int(a))))


def mix(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return (int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t))


def shade(color, k):
    """k>0 提亮，k<0 压暗"""
    if k >= 0:
        return mix(color, (255, 255, 255), k)
    return mix(color, (0, 0, 0), -k)


# --------------------------------------------------------------------------
# 缓动
# --------------------------------------------------------------------------
def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def ease_out_cubic(t):
    t = clamp(t)
    return 1.0 - pow(1.0 - t, 3.0)


def ease_in_out_sine(t):
    t = clamp(t)
    return -(math.cos(math.pi * t) - 1.0) / 2.0


def ease_out_back(t, s=1.70158):
    t = clamp(t) - 1.0
    return t * t * ((s + 1) * t + s) + 1.0


def approach(cur, target, speed, dt):
    """指数趋近（帧率无关）"""
    try:
        k = 1.0 - math.exp(-speed * dt)
        return cur + (target - cur) * k
    except Exception:
        return target


# --------------------------------------------------------------------------
# 字体
# --------------------------------------------------------------------------
_FONT_PATHS = [
    (True, r"C:\Windows\Fonts\msyhbd.ttc"),
    (True, r"C:\Windows\Fonts\msyhbd.ttf"),
    (False, r"C:\Windows\Fonts\msyh.ttc"),
    (True, r"C:\Windows\Fonts\simhei.ttf"),
    (False, r"C:\Windows\Fonts\simsun.ttc"),
    (True, r"C:\Windows\Fonts\Deng.ttf"),
]
_font_cache = {}
_font_path_cache = {}


def _find_font(bold=False):
    if bold in _font_path_cache:
        return _font_path_cache[bold]
    order = [p for p in _FONT_PATHS if p[0] == bold] + _FONT_PATHS
    for _, path in order:
        try:
            if os.path.exists(path):
                _font_path_cache[bold] = path
                return path
        except Exception:
            continue
    _font_path_cache[bold] = None
    return None


def font(size, bold=False):
    """带缓存的字体获取。失败时逐级回退，绝不抛异常。"""
    key = (int(size), bool(bold))
    f = _font_cache.get(key)
    if f is not None:
        return f
    f = None
    try:
        path = _find_font(bold)
        if path:
            f = pygame.font.Font(path, int(size))
        else:
            f = pygame.font.SysFont("microsoftyahei,simhei,arial", int(size), bold=bold)
    except Exception:
        f = None
    if f is None:
        try:
            f = pygame.font.Font(None, int(size))
        except Exception:
            f = pygame.font.Font(pygame.font.get_default_font(), int(size))
    try:
        f.set_bold(bool(bold))
    except Exception:
        pass
    _font_cache[key] = f
    return f


# 常用字号档位
SIZES = {
    "tiny": 12, "small": 14, "body": 16, "label": 18,
    "sub": 22, "title": 28, "h1": 38, "h2": 48, "hero": 64, "mega": 84,
}
ui_scale = 1.0     # 全局 UI 字号倍率（设置里可调，辅助低视力玩家）
quality = 1        # 画质档位 0流畅 / 1标准 / 2精致（控制泛光、粒子密度等）

_text_cache = {}
_TEXT_CACHE_MAX = 600


def render_text(txt, size="body", color=CREAM, bold=False):
    """带 LRU 上限的文本渲染缓存（颜色/字号/内容为键）。"""
    if not isinstance(size, int):
        size = SIZES.get(size, 16)
    if ui_scale != 1.0:
        size = max(8, int(size * ui_scale))
    key = (str(txt), size, color, bold)
    surf = _text_cache.get(key)
    if surf is not None:
        return surf
    try:
        surf = font(size, bold).render(str(txt), True, color)
    except Exception:
        try:
            surf = font(16).render("?", True, color)
        except Exception:
            surf = pygame.Surface((8, 8), pygame.SRCALPHA)
    if len(_text_cache) > _TEXT_CACHE_MAX:
        _text_cache.clear()
    _text_cache[key] = surf
    return surf


def text(surf, txt, pos, size="body", color=CREAM, align="left",
         shadow=True, outline=0, bold=False, alpha_mul=1.0):
    """绘制文本。align: left / center / right / midleft / midright。"""
    try:
        img = render_text(txt, size, color, bold)
        if alpha_mul < 0.999:
            img = img.copy()
            img.set_alpha(int(255 * clamp(alpha_mul)))
        r = img.get_rect()
        x, y = pos
        if align == "center":
            r.center = (int(x), int(y))
        elif align == "right":
            r.topright = (int(x), int(y))
        elif align == "midleft":
            r.midleft = (int(x), int(y))
        elif align == "midright":
            r.midright = (int(x), int(y))
        else:
            r.topleft = (int(x), int(y))
        if outline > 0:
            edge = render_text(txt, size, (0, 0, 0) if shadow else color, bold)
            if alpha_mul < 0.999:
                edge = edge.copy()
                edge.set_alpha(int(255 * clamp(alpha_mul)))
            for dx, dy in ((-outline, 0), (outline, 0), (0, -outline), (0, outline),
                           (-outline, -outline), (outline, -outline),
                           (-outline, outline), (outline, outline)):
                surf.blit(edge, (r.x + dx, r.y + dy))
        elif shadow:
            sh = render_text(txt, size, (0, 0, 0), bold)
            if alpha_mul < 0.999:
                sh = sh.copy()
                sh.set_alpha(int(170 * clamp(alpha_mul)))
            surf.blit(sh, (r.x + 1, r.y + 2))
        surf.blit(img, r)
        return r
    except Exception:
        # 兜底本身也可能崩（比如 pos 不是坐标）——那样会把异常抛给调用方，
        # 一帧一次刷屏。这里保证"画不出来也绝不抛"。
        try:
            return pygame.Rect(int(pos[0]), int(pos[1]), 0, 0)
        except Exception:
            return pygame.Rect(0, 0, 0, 0)


def text_width(txt, size="body", bold=False):
    try:
        if not isinstance(size, int):
            size = SIZES.get(size, 16)
        if ui_scale != 1.0:
            size = max(8, int(size * ui_scale))
        return font(size, bold).size(str(txt))[0]
    except Exception:
        return 0


# --------------------------------------------------------------------------
# 绘图原语
# --------------------------------------------------------------------------
def gradient_rect(surf, rect, top, bottom, horizontal=False, radius=0):
    """垂直/水平线性渐变矩形（逐行绘制，带少量缓存友好性）。"""
    try:
        r = pygame.Rect(rect)
        if r.w <= 0 or r.h <= 0:
            return
        if horizontal:
            for i in range(r.w):
                t = i / max(1, r.w - 1)
                pygame.draw.line(surf, mix(top, bottom, t),
                                 (r.x + i, r.y), (r.x + i, r.y + r.h - 1))
        else:
            for i in range(r.h):
                t = i / max(1, r.h - 1)
                pygame.draw.line(surf, mix(top, bottom, t),
                                 (r.x, r.y + i), (r.x + r.w - 1, r.y + i))
    except Exception:
        pass


def rounded_panel(surf, rect, fill=INK_800, border=None, radius=14,
                  shadow=True, alpha=235, inner_highlight=True, border_w=1):
    """玻璃拟态面板：投影 + 半透明填充 + 细描边 + 顶部内高光。"""
    try:
        r = pygame.Rect(rect)
        if r.w <= 0 or r.h <= 0:
            return
        if shadow:
            sh = pygame.Surface((r.w + 12, r.h + 12), pygame.SRCALPHA)
            pygame.draw.rect(sh, (0, 0, 0, 70), (6, 8, r.w, r.h), border_radius=radius)
            surf.blit(sh, (r.x - 6, r.y - 6))
        if fill is not None:
            if alpha < 255:
                layer = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
                pygame.draw.rect(layer, alpha_color(fill, alpha), (0, 0, r.w, r.h),
                                 border_radius=radius)
                surf.blit(layer, (r.x, r.y))
            else:
                pygame.draw.rect(surf, fill, r, border_radius=radius)
        if inner_highlight and fill is not None:
            try:
                pygame.draw.line(surf, alpha_color(shade(fill, 0.22), 150),
                                 (r.x + radius // 2, r.y + 1),
                                 (r.right - radius // 2, r.y + 1), 1)
            except Exception:
                pass
        if border is not None:
            pygame.draw.rect(surf, border, r, border_w, border_radius=radius)
    except Exception:
        pass


def alpha_color(color, a):
    try:
        return (color[0], color[1], color[2], max(0, min(255, int(a))))
    except Exception:
        return (255, 255, 255, max(0, min(255, int(a))))


_glow_base_cache = {}


def _glow_base(size=96):
    """径向渐变底图：RGB 承载衰减，alpha 恒 255（配合 ADD 叠加才不会有硬边）。"""
    s = _glow_base_cache.get(size)
    if s is not None:
        return s
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size / 2.0
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - c + 0.5, y - c + 0.5) / c
            if d >= 1.0:
                continue
            v = int(255 * (1.0 - d) ** 2.1)
            s.set_at((x, y), (v, v, v, 255))
    _glow_base_cache[size] = s
    return s


_glow_cache = {}


def glow_circle(surf, center, radius, color, intensity=1.0, layers=4):
    """平滑加色辉光（无环带）。按 (尺寸, 颜色, 强度) 缓存，避免每帧重建表面。"""
    try:
        size = max(2, int(radius * 2))
        # 强度量化到 1/16，显著提高缓存命中率且肉眼无差别
        q = max(0, min(16, int(round(min(1.0, max(0.0, intensity)) * 16))))
        if q <= 0:
            return
        key = (size, color, q)
        img = _glow_cache.get(key)
        if img is None:
            base = _glow_base(96)
            img = pygame.transform.smoothscale(base, (size, size))
            img.fill((color[0], color[1], color[2], 255), special_flags=pygame.BLEND_RGBA_MULT)
            f = int(255 * q / 16.0)
            img.fill((f, f, f, 255), special_flags=pygame.BLEND_RGBA_MULT)
            if len(_glow_cache) > 220:
                _glow_cache.clear()
            _glow_cache[key] = img
        surf.blit(img, (int(center[0]) - size // 2, int(center[1]) - size // 2),
                  special_flags=pygame.BLEND_RGBA_ADD)
    except Exception:
        pass


_shadow_cache = {}


def soft_shadow(surf, center_x, bottom_y, width, height=8, alpha=90):
    try:
        key = (int(width), int(height), int(alpha))
        s = _shadow_cache.get(key)
        if s is None:
            s = pygame.Surface((max(2, int(width)), max(2, int(height * 2))), pygame.SRCALPHA)
            pygame.draw.ellipse(s, (0, 0, 0, int(alpha)), (0, 0, max(2, int(width)),
                                                          max(2, int(height * 2))))
            if len(_shadow_cache) > 120:
                _shadow_cache.clear()
            _shadow_cache[key] = s
        surf.blit(s, (int(center_x - width / 2), int(bottom_y - height)))
    except Exception:
        pass


def dashed_rect(surf, rect, color, dash=6, gap=5, width=1):
    try:
        r = pygame.Rect(rect)
        x = r.x
        while x < r.right:
            pygame.draw.line(surf, color, (x, r.y), (min(x + dash, r.right), r.y), width)
            pygame.draw.line(surf, color, (x, r.bottom), (min(x + dash, r.right), r.bottom), width)
            x += dash + gap
        y = r.y
        while y < r.bottom:
            pygame.draw.line(surf, color, (r.x, y), (r.x, min(y + dash, r.bottom)), width)
            pygame.draw.line(surf, color, (r.right, y), (r.right, min(y + dash, r.bottom)), width)
            y += dash + gap
    except Exception:
        pass


def progress_bar(surf, rect, ratio, color, bg=INK_600, radius=6,
                 ghost=None, border=None):
    """带"残影条"的血条/进度条：ghost 为滞后比例的亮色尾迹。"""
    try:
        r = pygame.Rect(rect)
        pygame.draw.rect(surf, bg, r, border_radius=radius)
        if ghost is not None and ghost > ratio:
            gw = int(r.w * clamp(ghost))
            if gw > 1:
                pygame.draw.rect(surf, alpha_color((255, 240, 220), 150),
                                 (r.x, r.y, gw, r.h), border_radius=radius)
        w = int(r.w * clamp(ratio))
        if w > 0:
            pygame.draw.rect(surf, color, (r.x, r.y, w, r.h), border_radius=radius)
            # 顶部高光，增加立体感
            pygame.draw.line(surf, alpha_color(shade(color, 0.45), 170),
                             (r.x + radius // 2, r.y + 1),
                             (r.x + max(radius // 2, w - radius // 2), r.y + 1), 1)
        if border:
            pygame.draw.rect(surf, border, r, 1, border_radius=radius)
    except Exception:
        pass


def icon(surf, name, center, size=20, color=CREAM):
    """程序化矢量图标：heart / arrow / shield / sword / gear / play / pause /
    note / check / cross / star / skull / clock / flag / dash。"""
    try:
        cx, cy = int(center[0]), int(center[1])
        s = size
        h = s / 2.0
        if name == "heart":
            pts = []
            for i in range(24):
                t = i / 24.0 * math.pi * 2
                x = 16 * math.sin(t) ** 3
                y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
                pts.append((cx + x * s / 34.0, cy + y * s / 34.0))
            if len(pts) > 2:
                pygame.draw.polygon(surf, color, pts)
        elif name == "arrow":
            pygame.draw.line(surf, color, (cx - h, cy + h * 0.6), (cx + h, cy - h * 0.6), max(2, s // 8))
            pygame.draw.polygon(surf, color, [(cx + h, cy - h * 0.6),
                                              (cx + h * 0.3, cy - h * 0.55),
                                              (cx + h * 0.6, cy + h * 0.05)])
        elif name == "shield":
            pts = [(cx, cy - h), (cx + h * 0.8, cy - h * 0.55), (cx + h * 0.7, cy + h * 0.35),
                   (cx, cy + h), (cx - h * 0.7, cy + h * 0.35), (cx - h * 0.8, cy - h * 0.55)]
            pygame.draw.polygon(surf, color, pts)
            pygame.draw.polygon(surf, shade(color, -0.45), pts, max(1, s // 12))
        elif name == "sword":
            pygame.draw.line(surf, color, (cx - h * 0.7, cy + h * 0.7), (cx + h * 0.6, cy - h * 0.6), max(2, s // 7))
            pygame.draw.line(surf, shade(color, -0.4), (cx - h * 0.85, cy + h * 0.45),
                             (cx - h * 0.35, cy + h * 0.85), max(2, s // 9))
        elif name == "gear":
            for i in range(8):
                a = i * math.pi / 4
                tx = cx + math.cos(a) * h * 0.66
                ty = cy + math.sin(a) * h * 0.66
                pygame.draw.circle(surf, color, (int(tx), int(ty)), max(2, int(s * 0.10)))
            pygame.draw.circle(surf, color, (cx, cy), int(h * 0.52), max(2, s // 8))
            pygame.draw.circle(surf, color, (cx, cy), max(1, int(s * 0.07)))
        elif name == "play":
            pygame.draw.polygon(surf, color, [(cx - h * 0.5, cy - h * 0.8),
                                              (cx + h * 0.8, cy),
                                              (cx - h * 0.5, cy + h * 0.8)])
        elif name == "pause":
            pygame.draw.rect(surf, color, (cx - h * 0.55, cy - h * 0.8, s * 0.28, s * 1.6), border_radius=2)
            pygame.draw.rect(surf, color, (cx + h * 0.2, cy - h * 0.8, s * 0.28, s * 1.6), border_radius=2)
        elif name == "note":
            pygame.draw.ellipse(surf, color, (cx - h * 0.8, cy + h * 0.25, s * 0.5, s * 0.38))
            pygame.draw.line(surf, color, (cx - h * 0.35, cy + h * 0.45), (cx - h * 0.35, cy - h * 0.85), max(2, s // 9))
            pygame.draw.line(surf, color, (cx - h * 0.35, cy - h * 0.85), (cx + h * 0.55, cy - h * 0.6), max(2, s // 9))
        elif name == "check":
            pygame.draw.lines(surf, color, False, [(cx - h * 0.75, cy), (cx - h * 0.1, cy + h * 0.6),
                                                   (cx + h * 0.8, cy - h * 0.65)], max(2, s // 7))
        elif name == "cross":
            pygame.draw.line(surf, color, (cx - h * 0.7, cy - h * 0.7), (cx + h * 0.7, cy + h * 0.7), max(2, s // 7))
            pygame.draw.line(surf, color, (cx + h * 0.7, cy - h * 0.7), (cx - h * 0.7, cy + h * 0.7), max(2, s // 7))
        elif name == "star":
            pts = []
            for i in range(10):
                a = -math.pi / 2 + i * math.pi / 5
                rr = h if i % 2 == 0 else h * 0.45
                pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
            pygame.draw.polygon(surf, color, pts)
        elif name == "clock":
            pygame.draw.circle(surf, color, (cx, cy), int(h * 0.9), max(2, s // 9))
            pygame.draw.line(surf, color, (cx, cy), (cx, cy - h * 0.5), max(2, s // 10))
            pygame.draw.line(surf, color, (cx, cy), (cx + h * 0.42, cy + h * 0.15), max(2, s // 10))
        elif name == "flag":
            pygame.draw.line(surf, color, (cx - h * 0.6, cy - h), (cx - h * 0.6, cy + h), max(2, s // 9))
            pygame.draw.polygon(surf, color, [(cx - h * 0.5, cy - h * 0.9), (cx + h * 0.85, cy - h * 0.5),
                                              (cx - h * 0.5, cy - h * 0.1)])
        elif name == "dash":
            for k in (-1, 0, 1):
                pygame.draw.line(surf, color, (cx - h + k * s * 0.22, cy - h * 0.55),
                                 (cx + h * 0.35 + k * s * 0.22, cy - h * 0.55), max(2, s // 9))
                pygame.draw.line(surf, color, (cx - h + k * s * 0.22, cy + h * 0.55),
                                 (cx + h * 0.35 + k * s * 0.22, cy + h * 0.55), max(2, s // 9))
    except Exception:
        pass
