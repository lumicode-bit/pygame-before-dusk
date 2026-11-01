# -*- coding: utf-8 -*-
"""修审计断言 5/7/8/9。"""
import io

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


# ---- 5. 摆锤：圆-矩形判定（锤头圆 vs 玩家整个身体）----
# 旧判定用"身体中心点"到锤头中心的 y 差 < r+24。锤头最低点悬在头顶上方
# 几十像素，地面玩家中心差 92 > 50，永远打不中；跳跃中反而凑近了会被打。
rep('''                if (abs(h["bx"] - p["x"]) < h["r"] + 14 and
                        abs(h["by"] - (p["y"] - PLAYER_H / 2)) < h["r"] + 24):''',
    '''                # 圆-矩形最近距离：锤头扫过身体任何部分都算命中。
                # 旧写法只比"身体中心点"的 y 差，锤头悬在头顶上方 90px 时
                # 地面玩家永远打不中，跳跃的反而被打（主伤害机关完全空转）。
                _nr_y = min(max(h["by"], p["y"] - PLAYER_H), p["y"])
                _ndx = h["bx"] - p["x"]
                _ndy = h["by"] - _nr_y
                if _ndx * _ndx + _ndy * _ndy < (h["r"] + 9) ** 2:''',
    "hammer_circle_rect")

# ---- 7. 复活清 vine ----
# _respawn_all 不重置 vine，复活在检查点、下一帧被 _update_vine 无条件吸附回绳上，
# 死在岩浆藤蔓上会循环回危险区。
rep("    def _respawn_all(self, pid):",
    "    def _respawn_all(self, pid):\n        # 死亡复活必须脱离藤蔓：vine 不清会在下一帧被拽回绳上\n",
    "respawn_marker")
rep('''            p["hp"] = p["maxhp"]
            p["vine"] = p.get("vine", -1)''',
    '''            p["hp"] = p["maxhp"]
            p["vine"] = -1''', "respawn_vine")

# ---- 8. AI 弓箭手：只锁定箭的有效目标 ----
# 箭只对 fly/caster/boss 生效；旧回退逻辑把地面怪也当目标 -> 原地空射不跟队。
rep('''        # ================= AI 弓箭手 =================
        # 优先飞行怪，其次地面怪
        best, bd = None, 1e18
        for m in monsters:
            if m.kind in ("fly", "caster"):
                d = abs(m.x - px) + abs(m.y - py)
                if d < bd:
                    bd, best = d, m
        if best is None:
            bd = 1e18
            for m in monsters:
                d = abs(m.x - px) + abs(m.y - py)
                if d < bd:
                    bd, best = d, m''',
    '''        # ================= AI 弓箭手 =================
        # 只锁定箭真正能伤害的目标（fly/caster/boss）。
        # 旧版找不到飞行/施法者会回退到"任意怪"，而箭对 ground 无效 ->
        # AI 对着地面怪原地空射（shoot 按住不松，连触发都没有），也不跟随。
        best, bd = None, 1e18
        for m in monsters:
            if m.kind in ("fly", "caster", "boss"):
                d = abs(m.x - px) + abs(m.y - py)
                if d < bd:
                    bd, best = d, m''',
    "ai_targets")

# ---- 9. 守点 AI 不被归队兜底传走 ----
# guard 时 AI 站在守点上正好是 idle，人类走远就触发"far and idle"传送，
# 机关无人踩、共鸣门直接被破坏。guard 点由 main 设置到 engine.ai_guard_pos。
rep('''            elif far and idle:
                self._ai_stuck += dt''',
    '''            elif far and idle:
                # 守点指令下，AI 停在守点附近是职责不是卡死，不触发归队传送
                gp = getattr(self, "ai_guard_pos", None)
                on_guard = (gp is not None
                            and abs(a["x"] - gp[0]) < 90 and abs(a["y"] - gp[1]) < 120)
                if on_guard:
                    self._ai_stuck = max(0.0, self._ai_stuck - dt * 2.0)
                else:
                    self._ai_stuck += dt''',
    "rescue_guard")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_579_log.txt", "w", encoding="utf-8").write(" | ".join(log))
print("done")
