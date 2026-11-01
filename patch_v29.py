# -*- coding: utf-8 -*-
"""v2.9：
1) 飞怪改成"悬在玩家头顶跟随 + 周期性俯冲"，不再贴地/钻地形
2) 刷怪改成"先开紫色裂隙(黑洞) -> 延时 -> 怪物从里面走出来"，
   出场期间不移动/不伤害/不可被射，给玩家反应时间
"""
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


# ---------- 1) 裂隙状态 ----------
rep("        self.monsters = []\n        self.pads = []",
    "        self.monsters = []\n"
    "        self.rifts = []           # 刷怪前兆：紫色裂隙，延时后怪物从中走出来\n"
    "        self.pads = []", "rift_field")

# ---------- 2) _spawn_wave 改成开裂隙 ----------
rep('''        for i, (kind, x, y) in enumerate(spawns):
            m = Monster(self.mid_counter, kind, float(x), float(y))
            self.mid_counter += 1
            # 第二波里给第一只地面怪挂精英标记：更肉、更疼、带紫光
            if w == 2 and kind == "ground" and ("elite" in self.mods or i == 0):
                m.elite = True
                m.hp *= ELITE_HP_MUL
                m.maxhp = m.hp
            if self.difficulty != 1.0:
                m.hp = max(1.0, m.hp * self.difficulty)
                m.maxhp = m.hp
            self.monsters.append(m)
        self.msg = "第一波怪物来袭！弓箭手射飞行怪，盾卫斩杀地面怪！" if w == 1 else "第二波怪物来袭！"''',
    '''        # 不再直接生成怪物：先开紫色裂隙，给玩家 1.2s 反应时间，再从里面走出来
        for i, (kind, x, y) in enumerate(spawns):
            elite = (w == 2 and kind == "ground" and ("elite" in self.mods or i == 0))
            # 地面怪的黑洞贴地一点，飞怪开在半空
            ry = (19 * TILE - 26) if kind == "ground" else float(y)
            self.rifts.append({
                "x": float(x), "y": float(ry), "kind": kind,
                "elite": elite, "t": 0.0,
                "delay": 1.15 + i * 0.14,
                "size": 30.0 if kind == "ground" else 25.0,
                "tier": w,
            })
        self.msg = ("第一波怪物来袭！弓箭手射飞行怪，盾卫斩杀地面怪！" if w == 1
                    else "第二波怪物来袭！")''', "wave_rifts")

# ---------- 3) _update_rifts ----------
rep("    def _spawn_boss(self):",
    '''    def _update_rifts(self, dt):
        """裂隙到期 -> 怪物从里面走出来（出场期间不动/不伤害/不可被射）。"""
        if not self.rifts:
            return
        keep = []
        for r in self.rifts:
            r["t"] += dt
            if r["t"] < r["delay"]:
                keep.append(r)
                continue
            try:
                m = Monster(self.mid_counter, r["kind"], r["x"], r["y"])
                self.mid_counter += 1
                if r.get("elite"):
                    m.elite = True
                    m.hp *= ELITE_HP_MUL
                    m.maxhp = m.hp
                if self.difficulty != 1.0:
                    m.hp = max(1.0, m.hp * self.difficulty)
                    m.maxhp = m.hp
                m.state = "spawn"
                m.state_t = 0.55          # 出场动画时长，这段时间是安全的
                if m.kind in ("ground", "boss"):
                    m.y = r["y"] + 16         # 从黑洞里"升"出来
                    m.vy = 0.0
                self.monsters.append(m)
                self.events.append(("rift_open", int(r["x"]), int(r["y"])))
            except Exception as e:
                write_log("裂隙生成怪物异常: %r" % (e,))
        self.rifts = keep

    def _spawn_boss(self):''', "update_rifts")

# ---------- 4) step 里调用 ----------
rep("            # 4) 怪物 AI + 伤害\n            self._update_monsters(dt, now)",
    "            # 3.5) 裂隙到期 -> 放怪\n"
    "            self._update_rifts(dt)\n"
    "            # 4) 怪物 AI + 伤害\n            self._update_monsters(dt, now)", "step_call")

# ---------- 5) 怪物更新：spawn 状态 ----------
rep("            for m in list(self.monsters):\n"
    "                try:\n"
    "                    m.t += dt\n"
    "                    if m.kind == \"boss\":",
    "            for m in list(self.monsters):\n"
    "                try:\n"
    "                    m.t += dt\n"
    "                    if m.state == \"spawn\":\n"
    "                        # 出场动画：不下落、不移动、不攻击\n"
    "                        m.state_t -= dt\n"
    "                        m.vx *= 0.4\n"
    "                        m.vy = 0.0\n"
    "                        if m.state_t <= 0.0:\n"
    "                            m.state = \"walk\" if m.kind in (\"ground\", \"boss\") else \"hover\"\n"
    "                            m.state_t = 0.0\n"
    "                            m.atk_cd = max(m.atk_cd, 0.7)\n"
    "                        continue\n"
    "                    if m.kind == \"boss\":", "monster_spawn")

# ---------- 6) 接触伤害跳过 spawn ----------
rep("    def _monster_contact(self, m, archer, shield, now):\n"
    "        try:\n"
    "            mr = m.rect()",
    "    def _monster_contact(self, m, archer, shield, now):\n"
    "        try:\n"
    "            if m.state == \"spawn\":      # 破壳期间不伤人\n"
    "                return\n"
    "            mr = m.rect()", "contact_spawn")

# ---------- 7) 箭命中跳过 spawn ----------
rep("                        for m in self.monsters:\n"
    "                            if m.kind not in (\"fly\", \"caster\", \"boss\"):\n"
    "                                continue",
    "                        for m in self.monsters:\n"
    "                            if m.state == \"spawn\":     # 出场无敌\n"
    "                                continue\n"
    "                            if m.kind not in (\"fly\", \"caster\", \"boss\"):\n"
    "                                continue", "arrow_spawn")

# ---------- 8) 飞怪：头顶悬浮 + 俯冲 ----------
rep('''    def _fly_monster_ai(self, m, archer, dt):
        try:
            spd = 95.0
            phase = int(m.t / 4) % 2
            # 依旧跟着玩家飞，但加一个"高度下限"：不低于所在地表之上 120px，
            # 且不低于 FLY_BAND_TOP。既不会钻进地下，也不会永远碰不到人。
            floor_lim = max(FLY_BAND_TOP, self.surface_y(m.x) - 120.0)
            if phase == 0:
                hy = max(floor_lim, archer["y"] - 95 + math.sin(m.t * 2.0) * 22)
            else:
                hy = max(floor_lim, archer["y"] - 26)
            hx = archer["x"] + math.sin(m.t * 1.3) * 45
            m.vx = max(-spd, min(spd, (hx - m.x) * 2.2))
            m.vy = max(-spd, min(spd, (hy - m.y) * 2.2))
        except Exception as e:
            write_log("飞行怪AI异常: %r" % (e,))''',
    '''    def _fly_monster_ai(self, m, archer, dt):
        """飞怪：恒在玩家头顶 90px 跟随，每 3~5 秒俯冲一次。

        旧逻辑有两种高度（头顶 95px / 贴脸 26px）按 4 秒切换，
        贴脸那半边会让它贴在玩家身上甚至压到地面以下，射不中也看不清。
        现在固定悬停高度，只有俯冲时才会下探。
        """
        try:
            spd = 110.0
            # 悬停高度：玩家脚底 - 身高 - 90（跟着玩家上平台/下坑一起走）
            hover_y = archer["y"] - PLAYER_H - 90.0
            hover_y = min(hover_y, self.surface_y(m.x) - 74.0)   # 不贴地
            hover_y = max(hover_y, 28.0)                          # 不飞出画面顶

            diving = (m.state == "dive")
            if diving:
                m.state_t -= dt
                if m.state_t <= 0.0:
                    m.state = "hover"
                    diving = False
            if not diving:
                if m.state not in ("hover", "walk"):
                    m.state = "hover"
                m.atk_cd = max(0.0, m.atk_cd - dt)
                # 玩家在下方、水平够近时才俯冲（在头顶才不会一头扎进地板）
                if (m.atk_cd <= 0.0 and abs(archer["x"] - m.x) < 175
                        and 20.0 < (archer["y"] - m.y) < 280.0):
                    m.state = "dive"
                    m.state_t = 0.6
                    m.atk_cd = random.uniform(3.2, 5.0)
                    diving = True

            if diving:
                tx = archer["x"]
                ty = archer["y"] - 22.0
                kx, ky = 3.2, 4.4
            else:
                tx = archer["x"] + math.sin(m.t * 1.25) * 42.0
                ty = hover_y + math.sin(m.t * 2.1) * 9.0
                kx, ky = 2.2, 2.6
            m.vx = max(-spd * 2.0, min(spd * 2.0, (tx - m.x) * kx))
            m.vy = max(-spd * 2.4, min(spd * 2.4, (ty - m.y) * ky))
        except Exception as e:
            write_log("飞行怪AI异常: %r" % (e,))''', "fly_ai")

# ---------- 9) Boss 也用裂隙 ----------
rep('''            m = Monster(self.mid_counter, "boss", float(144 * TILE), float(15 * TILE))
            self.mid_counter += 1
            m.atk_cd = 1.8
            self.monsters.append(m)
            self.boss_spawned = True
            self.msg = "熔炉守卫苏醒！红光蓄力后会直线冲锋，用冲刺躲开！"
            self.events.append(("boss_spawn", 144 * TILE, 15 * TILE - 50))''',
    '''            # Boss 也走裂隙出场：更大的黑洞 + 更长的预警，才有"守卫苏醒"的压迫感
            self.rifts.append({
                "x": float(144 * TILE), "y": float(15 * TILE - 6),
                "kind": "boss", "elite": False, "t": 0.0,
                "delay": 1.9, "size": 62.0, "tier": 3,
            })
            self.boss_spawned = True
            self.msg = "熔炉守卫苏醒！红光蓄力后会直线冲锋，用冲刺躲开！"
            self.events.append(("boss_spawn", 144 * TILE, 15 * TILE - 50))''', "boss_rift")

# ---------- 10) pack 传 rift 与 state_t ----------
rep('''                         "state": m.state, "flash": round(m.flash, 2), "dir": m.dir,
                         "elite": bool(m.elite), "enraged": bool(m.enraged),
                         "phase": m.phase}''',
    '''                         "state": m.state, "state_t": round(m.state_t, 2),
                         "flash": round(m.flash, 2), "dir": m.dir,
                         "elite": bool(m.elite), "enraged": bool(m.enraged),
                         "phase": m.phase}''', "pack_state_t")

rep('                "monsters": monsters,\n                "plates": plates,',
    '                "monsters": monsters,\n'
    '                "rifts": [{"x": round(r["x"], 1), "y": round(r["y"], 1),\n'
    '                           "t": round(r["t"], 2), "delay": r["delay"],\n'
    '                           "size": r["size"], "kind": r["kind"]}\n'
    '                          for r in self.rifts],\n'
    '                "plates": plates,', "pack_rifts")

rep('                    "monsters": [], "plates": [], "pads": [], "rocks": [],',
    '                    "monsters": [], "rifts": [], "plates": [], "pads": [], "rocks": [],',
    "blank_rifts")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_v29_log.txt", "w", encoding="utf-8").write(" | ".join(log))
print("done")
