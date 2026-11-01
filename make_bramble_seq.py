import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame
pygame.init()
pygame.display.set_mode((1280, 720))
from renderer import WorldRenderer
import random

T = 32
W, H = 980, 520
out = pygame.Surface((W, H))
for y in range(H):
    f = y / H
    pygame.draw.line(out, (int(46 + 10 * f), int(38 + 8 * f), int(42 + 6 * f)), (0, y), (W, y))

r = WorldRenderer(pygame.display.get_surface())

_CJK = None
for _fp in (r"C:/Windows/Fonts/msyh.ttc", r"C:/Windows/Fonts/simhei.ttf"):
    if os.path.exists(_fp):
        _CJK = _fp
        break
f17 = pygame.font.Font(_CJK, 17)
f13 = pygame.font.Font(_CJK, 13)
f22 = pygame.font.Font(_CJK, 22)


def text(s, x, y, col=(232, 232, 244), f=None):
    out.blit((f or f17).render(s, True, col), (x, y))


WX = 126 * T
text("荆棘三层生命感 · 时间序列（每帧 0.5s，同一丛，玩家在远处）", 24, 14, (240, 240, 250), f22)
for i in range(4):
    s = pygame.Surface((230, 70), pygame.SRCALPHA)
    # 地面
    pygame.draw.rect(s, (56, 48, 50), (0, 58, 230, 12))
    r._draw_bramble(s, 20, 210, 60, 2.0 + i * 0.5, WX - 20, 999.0)
    out.blit(s, (24, 56 + i * 84))
    text("t = %.1fs" % (2.0 + i * 0.5), 264, 88 + i * 84, (170, 178, 198), f13)

text("对比 · 玩家贴脸（20px，摆幅 3 倍、频率 1.6 倍）", 24, 400, (240, 240, 250), f22)
for i in range(2):
    s = pygame.Surface((230, 70), pygame.SRCALPHA)
    pygame.draw.rect(s, (56, 48, 50), (0, 58, 230, 12))
    r._draw_bramble(s, 20, 210, 60, 2.0 + i * 0.5, WX - 20, 20.0)
    out.blit(s, (24, 436 + i * 44))
text("← 荆棘「发现」玩家：摆得更急、更凶", 264, 452, (255, 170, 120), f13)

pygame.image.save(out, "shots/78_bramble_anim.png")
print("saved")
