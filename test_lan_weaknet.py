"""异地弱网模拟：TCP 限速+延迟代理，验证不误判断线、心跳超时生效。

场景 A（限速 25KB/s，低于 30Hz 全量状态的产生速率 ~60KB/s）：
  旧实现会在发送缓冲积压时抛 BlockingIOError -> 误判"队友掉线"，整局冻结。
  修复后应保持连接，客机持续收到状态（帧率下降但不掉线）。
场景 B（客机突然静默）：
  服务端应在 ~3 秒后通过心跳超时判掉线（而不是无限复用最后一帧输入）。
"""
import os, sys, time, socket, threading, queue, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game_core as core


class ThrottleProxy:
    """把 listen_port 的 TCP 流量限速+延迟转发到 target_port。"""

    def __init__(self, listen_port, target_port, rate_bps=25000, delay=0.05):
        self.listen_port = listen_port
        self.target_port = target_port
        self.rate = rate_bps
        self.delay = delay
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", listen_port))
        self.sock.listen(2)
        self.sock.settimeout(0.3)
        self.running = True
        self.thread = threading.Thread(target=self._accept, daemon=True, name="Proxy")
        self.thread.start()

    def _accept(self):
        while self.running:
            try:
                c, _ = self.sock.accept()
            except socket.timeout:
                continue
            except Exception:
                return
            try:
                u = socket.create_connection(("127.0.0.1", self.target_port), timeout=3)
            except Exception:
                c.close()
                continue
            threading.Thread(target=self._pipe, args=(c, u), daemon=True).start()
            threading.Thread(target=self._pipe, args=(u, c), daemon=True).start()

    def _pipe(self, src, dst):
        try:
            while self.running:
                try:
                    data = src.recv(8192)
                except Exception:
                    return
                if not data:
                    return
                time.sleep(self.delay)
                # 限速：按字节数睡眠，让发送方缓冲积压（模拟带宽不足）
                time.sleep(len(data) / float(self.rate))
                try:
                    dst.sendall(data)
                except Exception:
                    return
        finally:
            try:
                src.close(); dst.close()
            except Exception:
                pass

    def close(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass


def run_case(name, silent_client=False, seconds=9.0):
    print("\n=== %s ===" % name)
    shared = core.Shared()
    shared.running = True
    eng = core.GameEngine()
    host = core.HostServer(eng, shared, port=5571, host_pid=0)
    host.start()
    time.sleep(0.6)

    proxy = ThrottleProxy(5572, 5571, rate_bps=25000, delay=0.05)
    out_q = queue.Queue()
    errs = []
    cli = core.NetClient("127.0.0.1", 5572, out_q, lambda m: errs.append(m))
    time.sleep(1.2)

    # 双方就位 -> 开局
    shared.q_host_input.put_nowait({"type": "start"})
    states = 0
    last_state_t = time.time()
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            while True:
                item = out_q.get_nowait()
                if item[0] == "state":
                    states += 1
                    last_state_t = time.time()
        except queue.Empty:
            pass
        if not silent_client:
            try:
                cli.send({"type": "input", "input": {"right": True, "mx": 200, "my": 500}})
            except Exception:
                pass
        time.sleep(1 / 60.0)

    elapsed = time.time() - t0
    print(" 客机收到状态: %d 帧（%.1f 帧/秒）" % (states, states / elapsed))
    print(" 客机连接状态: connected=%s error=%s" % (cli.connected, errs[-1] if errs else None))
    print(" 房主判定: client_lost=%s  status=%s" % (shared.client_lost, shared.status))
    print(" 引擎 tick=%d（世界是否还在推进）" % eng.tick)

    ok = True
    if not silent_client:
        if shared.client_lost:
            print(" [FAIL] 弱网下被误判为掉线")
            ok = False
        elif states < 20:
            print(" [FAIL] 客机几乎收不到状态")
            ok = False
        else:
            print(" [OK] 限速弱网下保持连接、状态持续到达")
    else:
        if shared.client_lost:
            print(" [OK] 客户端静默后，服务端通过心跳超时判掉线")
        else:
            print(" [FAIL] 客户端静默但服务端未察觉（会无限复用最后一帧输入）")
            ok = False

    try:
        host.stop()
        cli.close()
    except Exception:
        pass
    proxy.close()
    shared.running = False
    time.sleep(0.4)
    return ok


if __name__ == "__main__":
    try:
        a = run_case("场景A：限速 25KB/s + 50ms 延迟（模拟异地弱网）")
        b = run_case("场景B：客机静默（模拟网络切换/NAT 超时）", silent_client=True, seconds=7.0)
        print("\n总结:", "全部通过" if (a and b) else "有失败项")
    except Exception:
        traceback.print_exc()
