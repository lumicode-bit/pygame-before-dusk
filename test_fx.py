# -*- coding: utf-8 -*-
"""丧钟 / 红心 / 生机 的边界回归测试。"""
import os, sys, json, traceback
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import pygame
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import main as M, game_core as core

fails = []
def ck(name, cond, info=""):
    print(("  OK   " if cond else "  FAIL ") + name + (("  " + str(info)) if info else ""))
    if not cond:
        fails.append(name)

keys = None
noop = []

def make_app():
    a = M.App()
    a.dt = 1 / 60
    a.start_single(0)
    a._apply_scene('GAME')
    a.post.fade = 0.0
    return a, M.engine

def run(app, frames, evs=None):
    global keys
    if keys is None:
        keys = pygame.key.get_pressed()      # 必须在 App 建好窗口之后取
    for i in range(frames):
        app.dt = 1 / 60
        app.t += app.dt
        app._tick_transition()
        if app.scene == 'GAME':
            app.scene_game(list(evs or []), keys, (0, 0))
        elif app.scene == 'RESULT':
            app.scene_result([], keys, (0, 0))

print("== A. 丧钟期间按键跳过 ==")
a, e = make_app()
e.lives = 1; e.deaths = 4; e.players[0]['hp'] = 0
run(a, 30)
ck("丧钟已开始", a.bell_t is not None, "bell_t=%s" % a.bell_t)
run(a, 1, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, unicode=' ')])
ck("按键后跳过", a.bell_t is None or a.bell_t >= 99, "bell_t=%s" % a.bell_t)
run(a, 120)
ck("跳过能进结算", a.scene == 'RESULT', a.scene)

print("== B. 丧钟期间按 ESC（不应崩、不应卡死）==")
a, e = make_app()
e.lives = 1; e.players[0]['hp'] = 0
run(a, 20)
try:
    run(a, 60, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode='')])
    ok = True
except Exception:
    traceback.print_exc(); ok = False
ck("ESC 不崩", ok)
ck("ESC 不会打开暂停菜单", a.scene != 'PAUSE', a.scene)
run(a, 400)
ck("ESC 后仍能到结算", a.scene == 'RESULT', a.scene)

print("== C. 失败后重开：状态复位 ==")
a, e = make_app()
e.lives = 1; e.players[0]['hp'] = 0
run(a, 600)
ck("已到结算", a.scene == 'RESULT', a.scene)
a.restart_run()            # 走真实的"再战一次"路径
run(a, 400)                # 等转场淡入结束
e = M.engine
ck("重开回到 GAME", a.scene == 'GAME', a.scene)
ck("重开后 bell_t 复位", a.bell_t is None, a.bell_t)
ck("重开后 生命=5", e.lives == 5, e.lives)
ck("重开后 fail=False", not e.fail, e.fail)
ck("重开后 碎心列表空", a.heart_break == [], a.heart_break)

print("== D. 重开后再失败，丧钟要能再演一次 ==")
e.lives = 1; e.players[0]['hp'] = 0
run(a, 30)
ck("第二次丧钟能触发", a.bell_t is not None, a.bell_t)
run(a, 400)
ck("第二次也能到结算", a.scene == 'RESULT', a.scene)

print("== E. 红心边界 ==")
a, e = make_app()
for lv in (5, 3, 1, 0):
    e.lives = lv
    a._lives_prev = None
    try:
        run(a, 2)
        ok = True
    except Exception:
        traceback.print_exc(); ok = False
    ck("lives=%d 绘制不崩" % lv, ok)
e.lives = 0
try:
    run(a, 60)
    ok = True
except Exception:
    traceback.print_exc(); ok = False
ck("lives=0 持续绘制不崩", ok, "scene=%s" % a.scene)

print("== F. 生机（bloom）边界 ==")
a, e = make_app()
e.monsters.clear(); e.wave = 3; e.wave1_spawned = True; e.wave2_spawned = True
for pid in (0, 1):
    e.players[pid]['x'] = (core.ALTAR_LEFT + 2) * core.TILE
    e.players[pid]['y'] = 15 * core.TILE
e._spawn_boss()
for r in e.rifts:
    r['t'] = r['delay']
e.step({0: {}, 1: {}}, core.TICK_DT)
for m in e.monsters:
    if m.state == 'spawn':
        m.state_t = 0.0
e.step({0: {}, 1: {}}, core.TICK_DT)
b = next((m for m in e.monsters if m.kind == 'boss' and getattr(m, 'tree', False)), None)
ck("树精已生成", b is not None)
e._kill_monster(b)
ck("bloom 已生成", len(e.blooms) == 1, len(e.blooms))
prof = e.blooms[0].get('prof') or []
ck("prof 非空", len(prof) > 3, len(prof))
if prof:
    ys = [p[1] for p in prof]
    ck("prof 全部贴地(与树精落差<80)", all(abs(y - b.y) < 80 for y in ys),
       "y范围 %.0f~%.0f 树精y=%.0f" % (min(ys), max(ys), b.y))
try:
    e._kill_monster(b)      # 重复击杀不应崩
    ok = True
except Exception:
    traceback.print_exc(); ok = False
ck("重复击杀不崩", ok)
pk = e.pack()
ck("封包含 bloom.prof", bool(pk['blooms'] and 'prof' in pk['blooms'][0]))
try:
    json.dumps(pk)
    ok = True
except Exception:
    ok = False
ck("封包可 JSON 序列化", ok)

print("== G. 钟声素材缺失时回退合成 ==")
import audio
p = os.path.join('assets', 'sfx', 'bell.wav')
bak = p + '.bak'
try:
    os.replace(p, bak)
    audio._sfx_bank.clear()
    audio.init()
    has = 'bell' in audio._sfx_bank
    ck("缺素材时仍有 bell 音效（回退合成）", has)
finally:
    if os.path.exists(bak):
        os.replace(bak, p)

print()
if fails:
    print("失败 %d 项: %s" % (len(fails), fails))
    sys.exit(1)
print("自检全部通过。")
