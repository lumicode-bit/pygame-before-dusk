# -*- coding: utf-8 -*-
"""荆棘三层生命感：固定基准形状（世界坐标）+ 逐根相位摇曳 + 呼吸 + 感知玩家。"""
import io

P = "renderer.py"
s = io.open(P, encoding="utf-8").read()

a = s.index("    def _draw_bramble(self, surf, x0, x1, base_y, rnd):")
b = s.index("    def _draw_ground_spikes(self, surf, cam_x, cam_y, t):")

NEW = '''    def _bramble_stalks(self, bx_world):
        """按世界坐标生成一簇荆棘的【固定基准形状】并缓存。

        关键：种子必须吃世界坐标。之前用屏幕坐标 int(x0) 当种子，
        相机一动种子就变，形状每帧重掷——那不是"活"，是噪点。
        这里形状只生成一次，动画靠绘制阶段叠加时间相位。
        """
        cache = getattr(self, "_bramble_cache", None)
        if cache is None:
            cache = self._bramble_cache = {}
        key = int(bx_world)
        if key in cache:
            return cache[key]
        rnd = random.Random((key * 2654435761) & 0x7fffffff)
        stalks = []
        for _ in range(rnd.randint(3, 4)):
            side = rnd.choice((-1.0, 1.0)) * rnd.uniform(0.5, 1.0)
            stalks.append({
                "side": side,
                "h": rnd.uniform(26, 40),
                "ox": rnd.uniform(-3, 3),
                "phase": rnd.uniform(0.0, 6.283),      # 逐根独立相位
                "breath_ph": rnd.uniform(0.0, 6.283),
                "bend": rnd.uniform(5.5, 8.5),
                "hooks": [(i, rnd.uniform(-1.2, 1.2), rnd.uniform(5.0, 8.5))
                          for i in (1, 2, 3) if rnd.random() > 0.28],
            })
        cache[key] = stalks
        return stalks

    def _draw_bramble(self, surf, x0, x1, base_y, t, cam_x, near_dist=999.0):
        """红黑弯刺荆棘（三层生命感）。

        1) 摇曳：逐根独立相位，根部几乎不动、越靠尖端摆幅越大（f^1.5）
        2) 呼吸：整簇缓慢起伏，周期 ~7s，幅度 <1px
        3) 感知：玩家靠近（150px 内）时摆幅放大到 3 倍、频率加快
        """
        # 底部黑根 / 腐土带（不参与动画）
        pygame.draw.rect(surf, (24, 13, 15), (x0, base_y - 4, x1 - x0, 4))
        pygame.draw.rect(surf, (44, 20, 24), (x0, base_y - 4, x1 - x0, 1))

        # 感知强度：0（远）-> 1（贴脸）
        alert = max(0.0, 1.0 - near_dist / 150.0)
        boost = 1.0 + 2.0 * alert          # 摆幅倍率 1x -> 3x
        speed = 1.0 + 0.6 * alert          # 频率倍率

        world_x0 = x0 + cam_x              # 屏幕 -> 世界，用于取固定形状
        bx = x0 + 4
        while bx < x1 - 2:
            for st in self._bramble_stalks(bx + cam_x):
                # 呼吸起伏（整簇极缓）
                breath = math.sin(t * 0.9 + st["breath_ph"]) * 0.8
                pts = []
                for i in range(5):
                    f = i / 4.0
                    # 摇曳：尖端滞后（+f*0.9 相位差），幅度按 f^1.5 递增
                    sway = (math.sin(t * 2.2 * speed + st["phase"] + f * 0.9)
                            * 1.3 * (f ** 1.5) * boost)
                    px = bx + st["ox"] + st["side"] * (f ** 1.6) * st["bend"] + sway
                    py = base_y - 3 - f * st["h"] + breath
                    pts.append((px, py))
                # 主干三层（暗红 / 亮红高光 / 阴影侧）
                pygame.draw.lines(surf, (86, 24, 32), False, pts, 2)
                pygame.draw.lines(surf, (150, 46, 56), False,
                                  [(p[0] - 1, p[1]) for p in pts], 1)
                pygame.draw.lines(surf, (48, 16, 20), False,
                                  [(p[0] + 1.5, p[1]) for p in pts], 1)
                # 斜生钩刺（随主干一起摆）
                for (hi, ha, hlen) in st["hooks"]:
                    if hi >= len(pts):
                        continue
                    _p = pts[hi]
                    _hx = _p[0] + ha * hlen
                    _hy = _p[1] - hlen * 0.85
                    pygame.draw.line(surf, (72, 20, 26), _p, (_hx, _hy), 1)
                    pygame.draw.circle(surf, (188, 62, 66), (int(_hx), int(_hy)), 1)
                # 顶梢亮红点（最强摆幅处，也点出"活着"的感觉）
                tp = pts[-1]
                pygame.draw.circle(surf, (214, 74, 74), (int(tp[0]), int(tp[1])), 1)
            bx += 19

'''
s = s[:a] + NEW + s[b:]

# 更新 _draw_ground_spikes：签名加 st，传 t/cam_x/最近玩家距离
old = '''    def _draw_ground_spikes(self, surf, cam_x, cam_y, t):
        """地面刺条（SPIKE_STRIPS）：金属三角刺 / 红黑弯荆棘（按条区分）。"""
        for idx, (c0, c1) in enumerate(core.SPIKE_STRIPS):
            try:
                x0 = c0 * TILE - cam_x
                x1 = (c1 + 1) * TILE - cam_x
                if x1 < -40 or x0 > surf.get_width() + 40:
                    continue
                base_y = 19 * TILE - cam_y
                w = x1 - x0
                if idx in self.BRAMBLE_STRIPS:
                    self._draw_bramble(surf, int(x0), int(x1), int(base_y),
                                       random.Random(int(x0) * 31 + 9))
                    continue'''
new = '''    def _draw_ground_spikes(self, surf, cam_x, cam_y, t, st=None):
        """地面刺条（SPIKE_STRIPS）：金属三角刺 / 红黑弯荆棘（按条区分）。"""
        players = [p for p in (st or {}).get("players", {}).values() if p.get("hp", 1) > 0]
        for idx, (c0, c1) in enumerate(core.SPIKE_STRIPS):
            try:
                x0 = c0 * TILE - cam_x
                x1 = (c1 + 1) * TILE - cam_x
                if x1 < -40 or x0 > surf.get_width() + 40:
                    continue
                base_y = 19 * TILE - cam_y
                w = x1 - x0
                if idx in self.BRAMBLE_STRIPS:
                    # 最近玩家距离（世界坐标），驱动"感知"层
                    cxw = (c0 + c1 + 1) * 0.5 * TILE
                    near = min((abs(p["x"] - cxw) for p in players), default=999.0)
                    self._draw_bramble(surf, int(x0), int(x1), int(base_y),
                                       t, cam_x, near)
                    continue'''
assert old in s
s = s.replace(old, new, 1)
s = s.replace("        self._draw_ground_spikes(surf, cam_x, cam_y, t)",
              "        self._draw_ground_spikes(surf, cam_x, cam_y, t, st)", 1)
io.open(P, "w", encoding="utf-8").write(s)
print("bramble life added")
