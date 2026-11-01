# -*- coding: utf-8 -*-
"""
ui.py —— 交互控件库
============================================================================
  Button / IconButton / Slider / Toggle / TextInput / Segmented / Tooltip

设计要点：
  * 控件自身持有动画状态（hover/press/lift），跨帧连续，无需外部维护；
  * 所有控件返回"本帧是否被点击/是否变化"，由场景层驱动逻辑；
  * 视觉统一走 theme 的玻璃面板 + 描边 + 发光，保证整体一致性。
"""
import pygame

import theme


def _blend_panel(surf, rect, base, alpha, radius):
    layer = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(layer, theme.alpha_color(base, alpha), (0, 0, rect.w, rect.h),
                     border_radius=radius)
    surf.blit(layer, (rect.x, rect.y))


class Button:
    STYLES = {
        # fill, hover_fill, border, text
        "primary": ((58, 46, 82), (86, 62, 116), theme.GOLD, theme.CREAM),
        "gold": ((92, 70, 30), (128, 96, 40), theme.GOLD_LIGHT, (255, 246, 220)),
        "secondary": ((30, 36, 58), (44, 52, 82), (86, 96, 134), theme.SLATE_100),
        "ghost": ((24, 28, 44), (34, 40, 62), (56, 64, 94), theme.SLATE_200),
        "danger": ((70, 28, 34), (98, 38, 46), (216, 96, 100), (255, 226, 226)),
    }

    def __init__(self, rect, label, style="primary", icon=None, sub=None,
                 size="sub", key_hint=None, enabled=True):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.style = style
        self.icon = icon
        self.sub = sub
        self.size = size
        self.key_hint = key_hint
        self.enabled = enabled
        self.hover = False
        self.hover_t = 0.0
        self.press_t = 0.0
        self.focus = False
        self._sweep = -1.0

    def update(self, dt, mouse):
        was = self.hover
        self.hover = self.enabled and self.rect.collidepoint(mouse)
        if self.hover and not was:
            self._sweep = 0.0
        self.hover_t = theme.approach(self.hover_t, 1.0 if self.hover else 0.0, 14.0, dt)
        self.press_t = max(0.0, self.press_t - dt * 6.0)
        if self._sweep >= 0.0:
            self._sweep += dt * 2.2
            if self._sweep > 1.6:
                self._sweep = -1.0

    def handle(self, events, mouse):
        clicked = False
        for ev in events:
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if self.enabled and self.rect.collidepoint(ev.pos):
                    self.press_t = 1.0
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                if self.enabled and self.rect.collidepoint(ev.pos):
                    clicked = True
        return clicked

    def draw(self, surf):
        try:
            fill, hfill, border, tcol = self.STYLES.get(self.style, self.STYLES["primary"])
            if not self.enabled:
                fill, hfill, border, tcol = ((30, 32, 44), (30, 32, 44),
                                             (62, 66, 82), (110, 116, 136))
            lift = int(3 * self.hover_t) - int(3 * self.press_t)
            r = self.rect.move(0, -lift)
            base = theme.mix(fill, hfill, self.hover_t)
            # 外发光
            if self.hover_t > 0.02:
                glow = pygame.Surface((r.w + 26, r.h + 26), pygame.SRCALPHA)
                pygame.draw.rect(glow, theme.alpha_color(border, int(46 * self.hover_t)),
                                 (0, 0, r.w + 26, r.h + 26), border_radius=18)
                surf.blit(glow, (r.x - 13, r.y - 13))
            # 主体
            _blend_panel(surf, r, base, 246, 12)
            pygame.draw.rect(surf, theme.alpha_color(theme.shade(base, 0.35), 90),
                             (r.x + 10, r.y + 1, r.w - 20, 2), border_radius=2)
            pygame.draw.rect(surf, theme.mix(border, theme.WHITE, 0.35 * self.hover_t),
                             r, 1 + (1 if self.hover else 0), border_radius=12)
            if self.focus:
                pygame.draw.rect(surf, theme.GOLD_LIGHT, r.inflate(6, 6), 2, border_radius=15)

            # 扫光
            if 0.0 <= self._sweep <= 1.4:
                sx = int(r.x + (r.w + 160) * self._sweep - 160)
                band = pygame.Surface((120, r.h), pygame.SRCALPHA)
                for i in range(120):
                    a = int(28 * (1 - abs(i - 60) / 60.0))
                    pygame.draw.line(band, theme.alpha_color(theme.WHITE, a), (i, 0), (i, r.h))
                old_clip = surf.get_clip()
                surf.set_clip(r)
                surf.blit(band, (sx, r.y))
                surf.set_clip(old_clip)

            # 内容
            cx = r.centerx
            if self.icon:
                icon_x = r.x + 26
                theme.icon(surf, self.icon, (icon_x, r.centery), 20,
                           theme.mix(tcol, (255, 255, 255), 0.15))
                cx = r.centerx + 10
            if self.sub:
                theme.text(surf, self.label, (cx, r.centery - 11), self.size, tcol,
                           align="center", bold=True, shadow=False)
                theme.text(surf, self.sub, (cx, r.centery + 12), "small",
                           theme.mix(tcol, (255, 255, 255), -0.35), align="center", shadow=False)
            else:
                theme.text(surf, self.label, (cx, r.centery), self.size, tcol,
                           align="center", bold=True, shadow=False)
            if self.key_hint:
                theme.text(surf, self.key_hint, (r.right - 14, r.centery), "small",
                           theme.alpha_color(theme.SLATE_300, 200), align="midright", shadow=False)
        except Exception:
            pass


class IconButton:
    def __init__(self, rect, icon, style="ghost", size=22, tip=None):
        self.rect = pygame.Rect(rect)
        self.icon = icon
        self.style = style
        self.size = size
        self.tip = tip
        self.hover = False
        self.hover_t = 0.0

    def update(self, dt, mouse):
        self.hover = self.rect.collidepoint(mouse)
        self.hover_t = theme.approach(self.hover_t, 1.0 if self.hover else 0.0, 14.0, dt)

    def handle(self, events, mouse):
        for ev in events:
            if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                if self.rect.collidepoint(ev.pos):
                    return True
        return False

    def draw(self, surf):
        r = self.rect
        _blend_panel(surf, r, theme.mix((26, 30, 46), (48, 56, 82), self.hover_t), 210, 10)
        pygame.draw.rect(surf, theme.mix((64, 72, 102), theme.GOLD, self.hover_t), r, 1, border_radius=10)
        theme.icon(surf, self.icon, r.center, self.size,
                   theme.mix(theme.SLATE_200, theme.GOLD_LIGHT, self.hover_t))


class Slider:
    def __init__(self, rect, value=0.7, label="", icon=None, fmt=lambda v: "%d%%" % int(round(v * 100))):
        self.rect = pygame.Rect(rect)
        # 值域固定 0~1：外部传入越界值（比如旧存档里的 ui_scale=1.4）
        # 会让滑块画到轨道外面，且显示值与实际生效值不一致
        self.value = max(0.0, min(1.0, float(value)))
        self.label = label
        self.icon = icon
        self.fmt = fmt
        self.drag = False
        self.hover = False
        self.glow = 0.0

    def _knob_x(self):
        return int(self.rect.x + self.value * self.rect.w)

    def handle(self, events, mouse):
        changed = False
        for ev in events:
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                hit = self.rect.inflate(16, 20).collidepoint(ev.pos)
                if hit:
                    self.drag = True
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                self.drag = False
        if self.drag:
            v = (mouse[0] - self.rect.x) / max(1, self.rect.w)
            v = max(0.0, min(1.0, v))
            if abs(v - self.value) > 1e-4:
                self.value = v
                changed = True
        return changed

    def update(self, dt, mouse):
        self.hover = self.rect.inflate(16, 20).collidepoint(mouse) or self.drag
        self.glow = theme.approach(self.glow, 1.0 if self.hover else 0.0, 12.0, dt)

    def draw(self, surf, x_label=None):
        r = self.rect
        y = r.centery
        # 标签/数值的偏移要跟着字号缩放，否则放大后文字会直接压在滑轨上。
        # 22 时 18px 的标签底边正好落在滑轨上（看起来像被划掉），改 28 留 4px。
        lab_dy = int(28 * max(1.0, theme.ui_scale))
        if self.label:
            theme.text(surf, self.label, (r.x, r.y - lab_dy), "label", theme.SLATE_200, bold=True)
        if self.icon:
            theme.icon(surf, self.icon, (r.x - 22, y), 16, theme.SLATE_300)
        theme.text(surf, self.fmt(self.value), (r.right, r.y - lab_dy), "small",
                   theme.mix(theme.SLATE_300, theme.GOLD_LIGHT, self.glow), align="right")
        # 轨道
        pygame.draw.rect(surf, (24, 28, 44), (r.x, y - 3, r.w, 6), border_radius=3)
        fill_w = int(r.w * self.value)
        if fill_w > 0:
            col = theme.mix(theme.TEAL_DARK, theme.TEAL, self.glow)
            pygame.draw.rect(surf, col, (r.x, y - 3, fill_w, 6), border_radius=3)
        # 旋钮
        kx = self._knob_x()
        if self.glow > 0.02:
            theme.glow_circle(surf, (kx, y), 11, theme.TEAL, self.glow, 3)
        pygame.draw.circle(surf, (240, 246, 255), (kx, y), 7)
        pygame.draw.circle(surf, theme.mix(theme.TEAL_DARK, theme.TEAL, self.glow), (kx, y), 7, 2)


class Toggle:
    def __init__(self, rect, value=False, label=""):
        self.rect = pygame.Rect(rect)
        self.value = bool(value)
        self.label = label
        self.t = 1.0 if value else 0.0
        self.hover = False

    def handle(self, events, mouse):
        for ev in events:
            if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                if self.rect.inflate(140, 10).collidepoint(ev.pos):
                    self.value = not self.value
                    return True
        return False

    def update(self, dt, mouse):
        self.hover = self.rect.inflate(140, 10).collidepoint(mouse)
        self.t = theme.approach(self.t, 1.0 if self.value else 0.0, 16.0, dt)

    def draw(self, surf):
        r = self.rect
        if self.label:
            theme.text(surf, self.label, (r.x - 150, r.centery), "label",
                       theme.mix(theme.SLATE_200, theme.WHITE, 0.3 if self.hover else 0.0),
                       align="midleft", bold=True)
        track = pygame.Rect(r.x, r.centery - 11, r.w, 22)
        col = theme.mix((40, 46, 66), theme.TEAL_DARK, self.t)
        pygame.draw.rect(surf, col, track, border_radius=11)
        pygame.draw.rect(surf, theme.mix((70, 78, 104), theme.TEAL, self.t), track, 1, border_radius=11)
        kx = int(theme.lerp(track.x + 11, track.right - 11, self.t))
        pygame.draw.circle(surf, (240, 246, 255), (kx, track.centery), 8)
        if self.t > 0.5:
            theme.text(surf, "开", (kx, track.centery), "tiny", (20, 40, 38),
                       align="center", shadow=False)
        else:
            theme.text(surf, "关", (kx, track.centery), "tiny", (70, 76, 96),
                       align="center", shadow=False)


class TextInput:
    """单行输入框，支持 ASCII 与粘贴。中文依赖 TEXTINPUT 事件（可选）。"""

    def __init__(self, rect, text="", placeholder="", size="sub", maxlen=60):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.placeholder = placeholder
        self.size = size
        self.maxlen = maxlen
        self.active = False
        self.caret_t = 0.0
        self.hover = False

    def handle(self, events, mouse):
        # 同一批事件里若已有 TEXTINPUT，就不要再吃 KEYDOWN.unicode，否则字符会翻倍
        has_textinput = any(getattr(e, "type", 0) == pygame.TEXTINPUT for e in events)
        for ev in events:
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if self.rect.collidepoint(ev.pos):
                    self.active = True
                else:
                    self.active = False
            elif ev.type == pygame.KEYDOWN and self.active:
                if ev.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return "submit"
                elif ev.key == pygame.K_ESCAPE:
                    self.active = False
                elif (ev.unicode and ev.unicode.isprintable() and not has_textinput
                      and len(self.text) < self.maxlen):
                    self.text += ev.unicode
            elif ev.type == pygame.TEXTINPUT and self.active:
                if len(self.text) < self.maxlen:
                    self.text += ev.text
        return None

    def update(self, dt, mouse):
        self.hover = self.rect.collidepoint(mouse)
        self.caret_t = (self.caret_t + dt) % 1.0

    def draw(self, surf):
        r = self.rect
        _blend_panel(surf, r, (16, 19, 32), 235, 10)
        border = theme.mix((60, 68, 96), theme.GOLD if self.active else theme.SLATE_400,
                           1.0 if self.active else (0.35 if self.hover else 0.0))
        pygame.draw.rect(surf, border, r, 2 if self.active else 1, border_radius=10)
        shown = self.text or self.placeholder
        col = theme.CREAM if self.text else theme.SLATE_400
        theme.text(surf, shown, (r.x + 14, r.centery), self.size, col, align="midleft",
                   shadow=False)
        if self.active:
            w = theme.text_width(self.text, self.size)
            if self.caret_t < 0.55:
                cx = min(r.right - 12, r.x + 14 + w + 2)
                pygame.draw.line(surf, theme.GOLD_LIGHT, (cx, r.y + 10), (cx, r.bottom - 10), 2)


class Segmented:
    """分段选择器（画质/模式等）"""

    def __init__(self, rect, options, index=0, size="body"):
        self.rect = pygame.Rect(rect)
        self.options = list(options)
        self.index = int(index)
        self.size = size
        self.hover_i = -1
        self._seg_w = self.rect.w / max(1, len(self.options))

    def handle(self, events, mouse):
        for ev in events:
            if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                if self.rect.collidepoint(ev.pos):
                    i = int((ev.pos[0] - self.rect.x) // self._seg_w)
                    i = max(0, min(len(self.options) - 1, i))
                    if i != self.index:
                        self.index = i
                        return True
        return False

    def update(self, dt, mouse):
        self.hover_i = -1
        if self.rect.collidepoint(mouse):
            self.hover_i = int((mouse[0] - self.rect.x) // self._seg_w)

    def draw(self, surf):
        r = self.rect
        _blend_panel(surf, r, (18, 22, 36), 220, 9)
        # 选中滑块
        sel = pygame.Rect(int(r.x + self.index * self._seg_w) + 2, r.y + 2,
                          int(self._seg_w) - 4, r.h - 4)
        _blend_panel(surf, sel, (74, 58, 26), 235, 7)
        pygame.draw.rect(surf, theme.GOLD_DARK, sel, 1, border_radius=7)
        for i, opt in enumerate(self.options):
            cx = r.x + int((i + 0.5) * self._seg_w)
            col = theme.GOLD_LIGHT if i == self.index else (
                theme.SLATE_100 if i == self.hover_i else theme.SLATE_300)
            theme.text(surf, opt, (cx, r.centery), self.size, col, align="center",
                       shadow=False, bold=(i == self.index))
        pygame.draw.rect(surf, (60, 68, 98), r, 1, border_radius=9)


# --------------------------------------------------------------------------
# 组合绘制辅助
# --------------------------------------------------------------------------
def panel(surf, rect, title=None, subtitle=None, icon=None, accent=theme.GOLD):
    """带标题的窗口面板"""
    r = pygame.Rect(rect)
    theme.rounded_panel(surf, r, theme.INK_800, theme.alpha_color(accent, 110), 18, alpha=246)
    if title:
        ty = r.y + 30
        if icon:
            theme.icon(surf, icon, (r.x + 34, ty), 22, accent)
            tx = r.x + 54
        else:
            tx = r.x + 28
        theme.text(surf, title, (tx, ty), "title", theme.GOLD_LIGHT, align="midleft", bold=True)
        # 副标题/分隔线的偏移必须随字号一起放大：
        # 之前写死 +26 / +46，界面缩放到 140% 时标题本身就有 39px 高，
        # 副标题直接压在标题上（设置/结算/帮助/暂停四个界面全中招）。
        k = max(1.0, theme.ui_scale)
        sub_dy = int(26 * k)
        div_dy = int((46 if subtitle else 30) * k)
        if subtitle:
            theme.text(surf, subtitle, (tx, ty + sub_dy), "small", theme.SLATE_300, align="midleft")
        pygame.draw.line(surf, theme.alpha_color(accent, 70),
                         (r.x + 24, ty + div_dy),
                         (r.right - 24, ty + div_dy), 1)
    return r


def keycap(surf, text, center, size="small", color=theme.SLATE_200, w=None):
    try:
        tw = theme.text_width(text, size) + 14
        ww = w or tw
        r = pygame.Rect(0, 0, ww, 20)
        r.center = center
        _blend_panel(surf, r, (40, 46, 68), 230, 5)
        pygame.draw.rect(surf, (86, 96, 130), r, 1, border_radius=5)
        pygame.draw.line(surf, (110, 122, 162), (r.x + 3, r.bottom - 2), (r.right - 3, r.bottom - 2), 1)
        theme.text(surf, text, r.center, size, color, align="center", shadow=False)
        return r
    except Exception:
        return pygame.Rect(0, 0, 0, 0)


def badge(surf, text, pos, color=theme.GOLD, align="left", size="small"):
    theme.text(surf, text, pos, size, color, align=align, shadow=True)


def divider(surf, x1, x2, y, color=None):
    color = color or theme.alpha_color(theme.SLATE_400, 90)
    pygame.draw.line(surf, color, (x1, y), (x2, y), 1)


def dim(surf, alpha=170, color=(5, 6, 12)):
    s = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    s.fill(theme.alpha_color(color, alpha))
    surf.blit(s, (0, 0))
    return s


def toast(surf, text, y=96, t=0.0, color=theme.GOLD_LIGHT):
    """顶部提示条（t 为生命周期进度 0..1）"""
    a = 1.0 if t < 0.75 else max(0.0, (1.0 - t) / 0.25)
    w = theme.text_width(text, "body") + 44
    r = pygame.Rect(0, 0, w, 36)
    r.center = (surf.get_width() // 2, y)
    layer = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
    pygame.draw.rect(layer, (10, 12, 22, int(190 * a)), (0, 0, r.w, r.h), border_radius=9)
    pygame.draw.rect(layer, theme.alpha_color(color, int(140 * a)), (0, 0, r.w, r.h), 1, border_radius=9)
    surf.blit(layer, (r.x, r.y))
    theme.text(surf, text, r.center, "body", color, align="center", alpha_mul=a)
