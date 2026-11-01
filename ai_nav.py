# -*- coding: utf-8 -*-
"""ai_nav.py —— 离线导航图：把静态地图预处理成「可站立节点 + 可达边」。

背景：AI 之前所有移动能力都集中在 advance() 的启发式里——它只知道
"前方有没有墙/坑"，不知道目标在哪个楼层，更不知道怎么绕。
于是每处特殊地形（A/B 跳板、深坑阶板、瞭望塔）都得用硬编码像素坐标
（1120、1680、2010、96*TILE…）单独写规则，换一张地图就全失效。

这里把地图的**静态部分**（栅格 + 藤蔓）预处理成图：
  * 节点 = 可站立位置 (col, 支撑行)，世界坐标 (col*TILE + TILE/2, row*TILE)
  * 边   = 一次「步行 / 起跳 / 落下 / 跨沟 / 抓藤蔓」能到达的相邻节点
AI 沿 BFS 路径走：遇到上坡按跳，遇到下坡直接走出去，遇到藤蔓抓上去。

设计约束：
  * 不 import game_core（常量由调用方传入），避免循环导入
  * 图只含静态地形；移动阶板 / 压力机关跳板等动态元素仍由原有特判处理
"""

from collections import deque

TILE = 32
# 玩家能力上限（与 game_core 的手感一致）：
JUMP_UP_TILES = 4      # 单跳+二段跳可爬升 4 格（128px+）
GAP_JUMP_TILES = 4     # 平跳可跨 4 格沟
FALL_DEPTH_TILES = 16  # 主动跳下去最深 16 格
LEAP_TILES = 8         # 从高处向远处跳最远 8 格


def build_nav(grid, vines, solids, tile=TILE):
    """构建导航图。solids = 视作实心的字符集合。"""
    h = len(grid)
    w = len(grid[0]) if h else 0

    def solid(c, r):
        return 0 <= c < w and 0 <= r < h and grid[r][c] in solids

    # ---- 节点：可以站立的位置 ----
    nodes = {}                       # (col, top_row) -> (x, y)
    for c in range(w):
        for r in range(1, h):
            if solid(c, r) and not solid(c, r - 1) and not solid(c, r - 2):
                nodes[(c, r)] = (c * tile + tile // 2, r * tile)

    edges = {n: [] for n in nodes}   # 节点 -> [(邻节点, 移动方式)]

    def add(a, b, kind):
        if a != b and b in nodes and (b, kind) not in [(x, k) for x, k in edges[a]]:
            edges[a].append((b, kind))

    for (c, r) in list(nodes):
        # 1) 步行：相邻同层
        for d in (-1, 1):
            add((c, r), (c + d, r), "walk")

        # 2) 落下：走下平台边缘（脚所在列没有墙）
        for d in (-1, 1):
            if solid(c + d, r - 1) or solid(c + d, r):
                continue                     # 前面是墙，走不出去
            for dd in range(1, FALL_DEPTH_TILES + 1):
                if (c + d, r + dd) in nodes:
                    add((c, r), (c + d, r + dd), "fall")
                    break                    # 只连最近的可落点

        # 3) 起跳：向上 1~4 格（含原地跳上头顶平台）
        for du in range(1, JUMP_UP_TILES + 1):
            if (c, r - du) in nodes:
                add((c, r), (c, r - du), "jump")
        for du in range(1, JUMP_UP_TILES + 1):
            for d in (-1, 1):
                if (c + d, r - du) in nodes:
                    add((c, r), (c + d, r - du), "jump")

        # 4) 跨沟：中间列没有地面，跳过去（1~4 格）
        for g in range(2, GAP_JUMP_TILES + 1):
            for d in (-1, 1):
                tgt = (c + d * g, r)
                if tgt not in nodes:
                    continue
                if any(solid(c + d * k, r) for k in range(1, g)):
                    continue                 # 中间有地面，直接走过去就行
                if any(solid(c + d * k, r - 1) for k in range(1, g)):
                    continue                 # 中间有墙挡住跳跃弧线
                add((c, r), tgt, "gap")

        # 5) 高处大跳：从楼顶向远处跳（塔顶跳下、跨大平台）
        #    可跳的横向距离必须和下落深度挂钩：平地上最多 4 格，
        #    下落越深滞空越久、能跳越远（塔顶 F3 跳 6 列落到地面就是靠这个）
        for d in range(2, LEAP_TILES + 1):
            for dd in range(-2, FALL_DEPTH_TILES + 1):
                if d > GAP_JUMP_TILES + max(0, dd):
                    continue               # 平地上跳不了这么远
                tgt = (c + d, r + dd)
                if tgt not in nodes:
                    continue
                # 中间列的地形不能高出起跳点太多（否则弧线撞墙）
                ok = True
                for k in range(1, d):
                    for rr in range(max(0, r - JUMP_UP_TILES), r + dd):
                        if solid(c + k, rr):
                            ok = False
                            break
                    if not ok:
                        break
                if ok:
                    add((c, r), tgt, "leap")

    # ---- 藤蔓：两端各找最近节点，双向连接 ----
    for v in vines:
        ends = []
        for (vx, vy) in ((v[0], v[1]), (v[2], v[3])):
            best, bn = 1e18, None
            vc, vr = int(vx // tile), int(vy // tile)
            for (c, r), (nx, ny) in nodes.items():
                if abs(c - vc) > 2 or abs(r - vr) > 5:
                    continue
                d = abs(nx - vx) + abs(ny - vy)
                if d < best:
                    best, bn = d, (c, r)
            ends.append(bn)
        if len(ends) == 2 and ends[0] and ends[1]:
            add(ends[0], ends[1], "vine")
            add(ends[1], ends[0], "vine")

    return NavGraph(nodes, edges, tile)


class NavGraph:
    def __init__(self, nodes, edges, tile=TILE):
        self.nodes = nodes
        self.edges = edges
        self.tile = tile

    # ---- 坐标 -> 节点 ----
    def node_at(self, x, y):
        """取某坐标所在/最接近的可站立节点。"""
        c = int(x // self.tile)
        r = int(y // self.tile) + 1
        if (c, r) in self.nodes:
            return (c, r)
        best, bn = 1e18, None
        for (c2, r2), (nx, ny) in self.nodes.items():
            if abs(c2 - c) > 3:
                continue
            d = abs(nx - x) * 0.6 + abs(ny - y)
            if d < best:
                best, bn = d, (c2, r2)
        return bn

    # ---- BFS 找路径 ----
    def path(self, sx, sy, tx, ty):
        """返回 [(节点, 移动方式)]，第一个是起点、最后是终点；无路径返回 None。"""
        a = self.node_at(sx, sy)
        b = self.node_at(tx, ty)
        if a is None or b is None:
            return None
        if a == b:
            return [(a, "walk")]
        prev = {a: None}
        q = deque([a])
        while q:
            cur = q.popleft()
            if cur == b:
                break
            for nxt, kind in self.edges.get(cur, ()):
                if nxt not in prev:
                    prev[nxt] = (cur, kind)
                    q.append(nxt)
        if b not in prev:
            return None
        out = []
        cur = b
        while cur is not None:
            pk = prev[cur]
            out.append((cur, pk[1] if pk else "walk"))
            cur = pk[0] if pk else None
        out.reverse()
        return out
