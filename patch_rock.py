# -*- coding: utf-8 -*-
"""1) 落石落地按真实地形（原来硬编码 608，会穿过高台/祭坛掉进内部）
   2) 加 "open" 阶段：天空先裂开一道口子，再掉石头
   3) 受击震屏降强度 + 累积阻尼
"""
import io

# ---------------- 引擎 ----------------
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


# 1) 落石结构加 land_y
rep('''                "id": cfg["id"], "x": cfg["cx"] * TILE + 16, "y": cfg["y0"],
                "y0": cfg["y0"], "vy": 0.0, "state": "idle", "cd": 0.0,
                "squash": 0.0,''',
    '''                "id": cfg["id"], "x": cfg["cx"] * TILE + 16, "y": cfg["y0"],
                "y0": cfg["y0"], "vy": 0.0, "state": "idle", "cd": 0.0,
                "squash": 0.0, "land_y": 19 * TILE, "open_t": 0.0,''',
    "rock_land_y")

# 2) 地表探测辅助
rep("    def _update_fall_rocks(self, dt):",
    '''    def _ground_below(self, x, y_from):
        """从 y_from 往下找第一个实体格的顶面 y（落石落地用）。

        不能再用固定的 19*TILE：F1 在高台上、F3 在祭坛上，硬编码会让石头
        穿过台面一直掉进砖里（"落石掉到地底"）。
        """
        try:
            cx = int(x // TILE)
            if cx < 0 or cx >= MAP_W:
                return float(MAP_H * TILE)
            for ry in range(max(0, int(y_from // TILE)), MAP_H):
                if self._solid_at(cx, ry):
                    return float(ry * TILE)
        except Exception:
            pass
        return float(MAP_H * TILE)

    def _update_fall_rocks(self, dt):''', "ground_below")

# 3) 状态机：idle -> open -> fall -> rest
rep('''                    for p in self.players.values():
                        if p["hp"] > 0 and abs(p["x"] - r["x"]) < FALL_ROCK_TRIGGER and p["y"] < gy + 10:
                            r["state"] = "fall"
                            r["vy"] = 30.0
                            self.events.append(("rock_warn", int(r["x"]), int(r["y0"])))
                            break
                elif r["state"] == "fall":''',
    '''                    for p in self.players.values():
                        if p["hp"] > 0 and abs(p["x"] - r["x"]) < FALL_ROCK_TRIGGER and p["y"] < gy + 10:
                            # 先裂开天空，0.55 秒后才掉石头：给玩家"抬头看"的反应时间
                            r["state"] = "open"
                            r["open_t"] = 0.55
                            r["vy"] = 0.0
                            r["land_y"] = self._ground_below(r["x"], r["y"] + 6)
                            self.events.append(("rock_crack", int(r["x"]), int(r["y0"])))
                            break
                elif r["state"] == "open":
                    r["open_t"] -= dt
                    if r["open_t"] <= 0.0:
                        r["state"] = "fall"
                        r["vy"] = 40.0
                        self.events.append(("rock_warn", int(r["x"]), int(r["y0"])))
                elif r["state"] == "fall":''', "open_state")

# 4) 落地改用 land_y
rep('''                    if r["y"] >= gy - 14:
                        r["y"] = float(gy - 14)
                        r["state"] = "rest"
                        r["vy"] = 0.0
                        r["squash"] = 0.0
                        r["cd"] = 4.5
                        self.events.append(("rock_land", int(r["x"]), int(gy)))''',
    '''                    if r["y"] >= r["land_y"] - 14:
                        r["y"] = float(r["land_y"] - 14)
                        r["state"] = "rest"
                        r["vy"] = 0.0
                        r["squash"] = 0.0
                        r["cd"] = 4.5
                        self.events.append(("rock_land", int(r["x"]), int(r["land_y"])))''',
    "land_use")

# 5) pack 里补 land_y
rep('''            fall_rocks = [{"id": r["id"], "x": r["x"], "y": round(r["y"], 1),
                           "state": r["state"]} for r in self._fall_rocks]''',
    '''            fall_rocks = [{"id": r["id"], "x": r["x"], "y": round(r["y"], 1),
                           "y0": r["y0"], "land_y": round(r["land_y"], 1),
                           "open_t": round(r["open_t"], 2),
                           "state": r["state"]} for r in self._fall_rocks]''',
    "pack_land_y")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_rock_log.txt", "w", encoding="utf-8").write(" | ".join(log))

# ---------------- 相机震动 ----------------
P = "fx.py"
s = io.open(P, encoding="utf-8").read()
log2 = []


def rep2(old, new, tag):
    global s
    if old in s:
        s = s.replace(old, new, 1)
        log2.append(tag)
    elif new in s:
        log2.append(tag + "(already)")
    else:
        log2.append(tag + "(SKIP)")


rep2('''    def add_trauma(self, amount):
        self.trauma = min(1.0, self.trauma + amount * Camera.trauma_mul)''',
     '''    def add_trauma(self, amount):
        # 累积加阻尼：直接线性叠加的话，被连续打两三下 trauma 就冲到 1.0，
        # 屏幕抖得看不清人。改成"先衰减再叠加"，连续受击也不会失控。
        a = amount * Camera.trauma_mul
        self.trauma = min(1.0, self.trauma * 0.78 + a)''', "trauma_damp")

rep2("            self.ox = random.uniform(-1, 1) * 16.0 * mag\n"
     "            self.oy = random.uniform(-1, 1) * 12.0 * mag",
     "            self.ox = random.uniform(-1, 1) * 12.5 * mag\n"
     "            self.oy = random.uniform(-1, 1) * 9.5 * mag", "amplitude")

io.open(P, "w", encoding="utf-8").write(s)
io.open("patch_cam_log.txt", "w", encoding="utf-8").write(" | ".join(log2))
print("done")
