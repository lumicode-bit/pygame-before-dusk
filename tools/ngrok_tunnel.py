# -*- coding: utf-8 -*-
"""联机隧道启动器：把本机 5555 端口（游戏房主端口）映射到公网。

用法（房主执行）：
    python tools/ngrok_tunnel.py            # 需要 ngrok.exe 与 authtoken
    python tools/ngrok_tunnel.py 1234ABCD   # 首次可直接带上 authtoken

前提：
    1) ngrok.exe 已就位：tools/ngrok_bin/ngrok.exe（已自动下载）
    2) 免费注册 https://dashboard.ngrok.com -> Cloud Edge -> Authtokens 复制
    3) 隧道起来后，把脚本打印的公网地址发给队友，
       队友在「加入房间」里输入这个地址（不要带 https://）。

注意：
    * 隧道是临时的：每次重启 ngrok 公网地址都会变（免费版）。
    * 队友和你同一个局域网时，根本不用 ngrok —— 直接输房主的局域网 IP:5555。
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
NGROK = os.path.join(HERE, "ngrok_bin", "ngrok.exe")
PORT = 5555          # 与 main.py 里 HostServer 的端口一致
API = "http://127.0.0.1:4040/api/tunnels"


def fail(msg):
    print("\n[失败] " + msg)
    print("  局域网联机不需要 ngrok：房主在「创建房间」后把本机 IP 发给队友即可。")
    sys.exit(1)


def main():
    if not os.path.exists(NGROK):
        fail("找不到 %s" % NGROK)

    # 1) authtoken：命令行参数 > 环境变量 > 已保存的配置
    token = ""
    if len(sys.argv) > 1:
        token = sys.argv[1].strip()
    elif os.environ.get("NGROK_AUTHTOKEN"):
        token = os.environ["NGROK_AUTHTOKEN"].strip()

    if token:
        r = os.system('"%s" config add-authtoken %s >nul 2>&1' % (NGROK, token))
        print("[token] 已写入 ngrok 配置" if r == 0 else "[token] 写入失败（请检查是否完整复制）")

    # 2) 起隧道（独立窗口，关掉窗口=关隧道）
    print("[ngrok] 正在启动 TCP 隧道：本机 %d -> 公网 ..." % PORT)
    os.system('start "ngrok 隧道（关掉这个窗口=断开联机）" "%s" tcp %d' % (NGROK, PORT))

    # 3) 从本地 API 轮询出公网地址
    print("[ngrok] 等待隧道建立（首次约 3~10 秒）...")
    addr = None
    for _ in range(30):
        time.sleep(1.0)
        try:
            with urllib.request.urlopen(API, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for tn in data.get("tunnels", []):
                if tn.get("proto") == "tcp":
                    addr = tn.get("public_url", "")
                    break
        except urllib.error.URLError:
            pass          # ngrok 的本地 API 还没起，继续等
        except Exception as e:
            print("  [等待] %r" % (e,))
        if addr:
            break

    if not addr:
        fail("隧道没有建立。最常见原因：还没有配置 authtoken。"
             "\n  1) 打开 https://dashboard.ngrok.com/get-started/your-authtoken"
             "\n  2) 复制 token 后重新运行：python tools/ngrok_tunnel.py 你的token")

    addr = addr.replace("tcp://", "")
    print("\n" + "=" * 56)
    print("  公网联机地址:  %s" % addr)
    print("=" * 56)
    print("  1) 你自己：游戏里点「创建房间（房主）」")
    print("  2) 队友：点「加入房间（队友）」，地址栏输入上面那串")
    print("     （例如 %s，不要加 tcp://）" % addr)
    print("  3) 这个地址每次重启都会变，关掉 ngrok 窗口 = 隧道断开")
    try:
        input("\n按回车关闭隧道并退出...")
    except EOFError:
        pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
