"""让两个 AI 自动打一遍，看能不能通关、要多久、死几次、卡在哪。"""
import game_core as core

for diff, name in ((1.0, "标准"), (1.4, "困难")):
    e = core.GameEngine()
    e.difficulty = diff
    TICK = core.TICK_DT
    stuck_at = None
    last_x = 0.0
    stall = 0
    for frame in range(60 * 300):          # 最多 5 分钟
        inp0 = core.make_ai_input(0, e, 1, "follow")
        inp1 = core.make_ai_input(1, e, 0, "follow")
        e.step({0: inp0, 1: inp1}, TICK)
        if e.win:
            break
        # 卡住检测：10 秒内两个人都没前进
        mx = max(e.players[0]["x"], e.players[1]["x"])
        if mx > last_x + 20:
            last_x = mx
            stall = 0
        else:
            stall += 1
        if stall > 600:
            stuck_at = (round(mx / 32, 1), round(e.players[0]["x"] / 32, 1),
                        round(e.players[1]["x"] / 32, 1), e.wave, e.portal_active)
            break
    print("[%s] 通关=%s 用时=%.1fs 帧=%d 死亡=%d 击杀=%d 波次=%d 传送门=%s 卡点=%s"
          % (name, e.win, e.elapsed, frame, e.deaths, e.kills, e.wave,
             e.portal_active, stuck_at))
