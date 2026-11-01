"""模拟人类：一直向右推进，遇怪就打，遇障碍就跳。测关卡能否真通。"""
import game_core as core

T = core.TILE


def human_input(e, pid, frame):
    p = e.players[pid]
    inp = {"left": False, "right": True, "up": False, "down": False,
           "shoot": False, "sword": False, "block": False, "dash": False,
           "interact": False, "mx": p["x"] + 200, "my": p["y"] - 30}
    # 附近有怪就打
    near = [m for m in e.monsters if abs(m.x - p["x"]) < 420]
    if near:
        tgt = min(near, key=lambda m: abs(m.x - p["x"]))
        inp["mx"], inp["my"] = tgt.x, tgt.y - 16
        if pid == 0:
            inp["shoot"] = True
        else:
            inp["sword"] = abs(tgt.x - p["x"]) < 70
            inp["block"] = abs(tgt.x - p["x"]) < 110
    # 每 40 帧跳一次，跨越台阶/断崖
    if frame % 40 < 2:
        inp["up"] = True
    # 挂藤蔓时朝上端滑
    if p["vine"] >= 0:
        v = core.VINES[p["vine"]]
        inp["right"] = v[3] < v[1]
        inp["left"] = not inp["right"]
        inp["up"] = False
    return inp


for diff, name in ((1.0, "标准"), (1.4, "困难"), (0.7, "简单")):
    e = core.GameEngine()
    e.difficulty = diff
    stall, last_x, stuck = 0, 0.0, None
    for frame in range(60 * 420):        # 最多 7 分钟
        i0 = human_input(e, 0, frame)
        i1 = human_input(e, 1, frame)
        e.step({0: i0, 1: i1}, core.TICK_DT)
        if e.win:
            break
        mx = max(e.players[0]["x"], e.players[1]["x"])
        if mx > last_x + 24:
            last_x, stall = mx, 0
        else:
            stall += 1
        if stall > 900:                  # 15 秒无进展
            stuck = (round(mx / T, 1), e.wave, e.portal_active,
                     len([m for m in e.monsters if not m.tower]))
            break
    print("[%s] 通关=%-5s 用时=%6.1fs 死亡=%2d 击杀=%2d 波次=%d 门=%s 卡点=%s"
          % (name, e.win, e.elapsed, e.deaths, e.kills, e.wave, e.portal_active, stuck))
