# -*- coding: utf-8 -*-
"""
audio.py —— 《暮色之前》全程序化音频引擎
============================================================================
不依赖任何外部音频文件：所有背景音乐与音效都在运行时用 numpy 合成，
打包成 exe 后同样可用（无素材丢失风险）。

结构：
  * Synth      —— 基础振荡器 / 包络 / 滤波 / 混响
  * COMPOSER   —— 三段循环配乐（menu / explore / battle）
  * SFX        —— 20+ 个游戏音效
  * Mixer      —— pygame.mixer 通道管理、音量总线、淡入淡出

所有对外接口都是"不会抛异常"的：音频设备不可用时静默降级，
游戏逻辑与画面不受影响。
"""
import math
import threading
import time

try:
    import numpy as np
except Exception:                                    # pragma: no cover
    np = None

from pygame import mixer

SAMPLE_RATE = 44100
CHANNELS = 2
BUFFER = 512

# --------------------------------------------------------------------------
# 全局状态
# --------------------------------------------------------------------------
_ok = False                    # mixer 是否可用
_ready = False                 # 音效是否构建完成
_music_ready = set()
_vol = {"master": 0.85, "music": 0.42, "sfx": 0.72}
_sfx_bank = {}
_music_bank = {}
_music_chan = None
_current_music = None
_cur_music_vol = 1.0
_lock = threading.Lock()
_stop = threading.Event()
_music_thread = None


def _log(msg):
    try:
        print("[audio]", msg)
    except Exception:
        pass


def init():
    """初始化混音器并构建音效库（音乐在后台线程构建）。"""
    global _ok, _ready
    if np is None:
        _log("未安装 numpy，音频已禁用")
        return False
    try:
        mixer.pre_init(SAMPLE_RATE, -16, CHANNELS, BUFFER)
        mixer.init(SAMPLE_RATE, -16, CHANNELS, BUFFER)
        mixer.set_num_channels(24)
        _ok = True
    except Exception as e:
        _log("混音器不可用: %r" % (e,))
        _ok = False
        return False
    try:
        _build_sfx()
        _ready = True
    except Exception as e:
        _log("音效构建失败: %r" % (e,))
    global _music_thread
    _music_thread = threading.Thread(target=_build_music_all, daemon=True, name="AudioMusic")
    _music_thread.start()
    return True


# --------------------------------------------------------------------------
# 基础合成工具
# --------------------------------------------------------------------------
def _midi(m):
    return 440.0 * (2.0 ** ((m - 69) / 12.0))


def _env(n, a=0.01, d=0.1, s=0.6, r=0.2, sus=0.0):
    """ADSR 包络（采样级）。"""
    a_n = max(1, int(a * SAMPLE_RATE))
    d_n = max(1, int(d * SAMPLE_RATE))
    r_n = max(1, int(r * SAMPLE_RATE))
    body = max(0, n - a_n - d_n - r_n)
    env = np.zeros(n, dtype=np.float32)
    i = 0
    k = min(a_n, n)
    env[i:i + k] = np.linspace(0, 1, k, dtype=np.float32)
    i += k
    k = min(d_n, n - i)
    if k > 0:
        env[i:i + k] = np.linspace(1, sus, k, dtype=np.float32)
    i += k
    k = min(body, n - i)
    if k > 0:
        env[i:i + k] = sus
    i += k
    k = min(r_n, n - i)
    if k > 0:
        env[i:i + k] = np.linspace(env[i - 1] if i > 0 else sus, 0, k, dtype=np.float32)
    return env


def _osc(freq, dur, kind="sine", detune=0.0, phase=0.0):
    n = max(1, int(dur * SAMPLE_RATE))
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    f = freq * (1.0 + detune)
    ph = 2.0 * math.pi * f * t + phase
    if kind == "sine":
        return np.sin(ph).astype(np.float32)
    if kind == "tri":
        return (2.0 / math.pi * np.arcsin(np.sin(ph))).astype(np.float32)
    if kind == "saw":
        # 带限近似：叠加前若干谐波，避免刺耳混叠
        out = np.zeros(n, dtype=np.float32)
        for k in range(1, 9):
            out += (np.sin(ph * k) / k).astype(np.float32)
        return (out * 0.55).astype(np.float32)
    if kind == "square":
        out = np.zeros(n, dtype=np.float32)
        for k in range(1, 8, 2):
            out += (np.sin(ph * k) / k).astype(np.float32)
        return (out * 0.7).astype(np.float32)
    if kind == "noise":
        return (np.random.uniform(-1, 1, n)).astype(np.float32)
    if kind == "pink":
        w = np.random.uniform(-1, 1, n).astype(np.float32)
        out = np.zeros(n, dtype=np.float32)
        b0 = b1 = b2 = 0.0
        for i in range(n):
            b0 = 0.99765 * b0 + w[i] * 0.0990460
            b1 = 0.96300 * b1 + w[i] * 0.2965164
            b2 = 0.57000 * b2 + w[i] * 1.0526913
            out[i] = (b0 + b1 + b2 + w[i] * 0.1848) * 0.22
        return out
    return np.sin(ph).astype(np.float32)


def _sweep(f0, f1, dur, kind="sine"):
    """指数扫频振荡器。"""
    n = max(1, int(dur * SAMPLE_RATE))
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    f0 = max(20.0, f0)
    f1 = max(20.0, f1)
    k = math.log(f1 / f0) / max(1e-6, dur)
    phase = 2.0 * math.pi * f0 * (np.exp(k * t) - 1.0) / k
    if kind == "sine":
        return np.sin(phase).astype(np.float32)
    if kind == "tri":
        return (2.0 / math.pi * np.arcsin(np.sin(phase))).astype(np.float32)
    return np.sin(phase).astype(np.float32)


def _lowpass(x, cutoff):
    """低通：两次滑动平均近似（向量化，比逐样本 IIR 快两个数量级）。"""
    try:
        k = max(2, int(SAMPLE_RATE / max(80.0, cutoff)))
        if k <= 2 or len(x) < k * 2:
            return x
        y = x.astype(np.float32)
        for _ in range(2):
            c = np.cumsum(np.concatenate((np.zeros(1, dtype=np.float32), y)))
            z = (c[k:] - c[:-k]) / float(k)
            pad = len(y) - len(z)
            if pad > 0:
                z = np.concatenate((z, np.full(pad, z[-1] if len(z) else 0.0, dtype=np.float32)))
            y = z.astype(np.float32)
        return y
    except Exception:
        return x


def _reverb(x, mix_amt=0.22, decay=0.35):
    """轻量多抽头混响：几条衰减延迟叠加，营造空间感。"""
    try:
        out = x.copy()
        taps = [(0.037, 0.42), (0.061, 0.30), (0.089, 0.22), (0.131, 0.15)]
        for delay, gain in taps:
            d = int(delay * SAMPLE_RATE)
            if d <= 0 or d >= len(x):
                continue
            out[d:] += x[:-d] * gain * decay
        return out * (1.0 - mix_amt) + x * mix_amt
    except Exception:
        return x


def _place(buf, sig, at_sec, gain=1.0):
    """把信号叠加到缓冲的指定时间点（超出部分自动裁剪）。"""
    try:
        i = int(at_sec * SAMPLE_RATE)
        if i >= len(buf):
            return
        n = min(len(sig), len(buf) - i)
        if n > 0:
            buf[i:i + n] += sig[:n] * gain
    except Exception:
        pass


def _to_sound(stereo):
    """numpy float32 (n,2) -> pygame.Sound，带软限幅。"""
    try:
        x = np.tanh(stereo * 1.05) * 0.92
        pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16)
        return mixer.Sound(array=pcm)
    except Exception as e:
        _log("Sound 生成失败: %r" % (e,))
        return None


def _stereo(mono, pan=0.0, width=1.0):
    """单声道转立体声，pan -1..1；width 为轻微去相关（增宽）。"""
    try:
        m = mono
        if width > 0:
            d = int(0.004 * SAMPLE_RATE)
            l = m.copy()
            r = m.copy()
            if d < len(m):
                r[d:] = m[:-d] * 0.75 + m[d:] * 0.25
            wave = np.stack([l * (1.0 - max(0.0, pan) * 0.5),
                             r * (1.0 + min(0.0, pan) * 0.5)], axis=1)
        else:
            wave = np.stack([m, m], axis=1)
        return wave.astype(np.float32)
    except Exception:
        return np.stack([mono, mono], axis=1).astype(np.float32)


# --------------------------------------------------------------------------
# 音效库
# --------------------------------------------------------------------------
def _sfx_jump():
    d = 0.22
    s = _sweep(320, 620, d, "sine") * _env(int(d * SAMPLE_RATE), 0.004, 0.05, 0.3, 0.12, 0.25)
    n = _osc(0, d, "pink") * _env(int(d * SAMPLE_RATE), 0.002, 0.04, 0.05, 0.08, 0.05) * 0.18
    return s + n


def _sfx_double_jump():
    d = 0.3
    a = _sweep(520, 1180, d, "tri") * _env(int(d * SAMPLE_RATE), 0.003, 0.06, 0.35, 0.16, 0.3)
    b = _osc(_midi(88), d, "sine") * _env(int(d * SAMPLE_RATE), 0.001, 0.09, 0.0, 0.12, 0.2) * 0.35
    return a + b


def _sfx_dash():
    d = 0.26
    n = _lowpass(_osc(0, d, "pink"), 2600) * _env(int(d * SAMPLE_RATE), 0.01, 0.06, 0.4, 0.14, 0.2)
    s = _sweep(900, 220, d, "sine") * 0.25 * _env(int(d * SAMPLE_RATE), 0.005, 0.05, 0.2, 0.1, 0.1)
    return n * 0.7 + s


def _sfx_shoot():
    d = 0.24
    tw = _osc(_midi(64), d, "saw") * _env(int(d * SAMPLE_RATE), 0.002, 0.05, 0.12, 0.14, 0.08)
    tw *= 1.0 + 0.005 * np.sin(np.arange(len(tw)) * 0.3)
    air = _lowpass(_osc(0, d, "noise"), 5200) * _env(int(d * SAMPLE_RATE), 0.001, 0.03, 0.0, 0.1, 0.3)
    return tw * 0.8 + air * 0.35


def _sfx_hit():
    d = 0.16
    th = _sweep(180, 70, d, "sine") * _env(int(d * SAMPLE_RATE), 0.001, 0.03, 0.2, 0.09, 0.4)
    n = _lowpass(_osc(0, d, "noise"), 3800) * _env(int(d * SAMPLE_RATE), 0.001, 0.02, 0.0, 0.06, 0.6)
    return th * 0.9 + n * 0.5


def _sfx_sword():
    d = 0.2
    n = _lowpass(_osc(0, d, "pink"), 2200)
    n *= np.linspace(0.35, 1.0, len(n)) * _env(len(n), 0.01, 0.05, 0.3, 0.1, 0.05)
    return n * 0.75


def _mix(*sigs):
    """把若干不同长度的信号按最长对齐相加。"""
    try:
        n = max(len(s) for s in sigs)
        out = np.zeros(n, dtype=np.float32)
        for s in sigs:
            out[:len(s)] += s
        return out
    except Exception:
        return np.zeros(1, dtype=np.float32)


def _sfx_rock_break():
    d = 0.42
    cr = _lowpass(_osc(0, d, "noise"), 1800) * _env(int(d * SAMPLE_RATE), 0.001, 0.05, 0.25, 0.3, 0.12)
    th = _sweep(120, 55, 0.3) * _env(int(0.3 * SAMPLE_RATE), 0.001, 0.04, 0.2, 0.2, 0.4)
    return _mix(cr * 0.9, th * 0.6)


def _sfx_hurt():
    d = 0.3
    sq = _sweep(420, 150, d, "tri") * _env(int(d * SAMPLE_RATE), 0.002, 0.06, 0.3, 0.16, 0.35)
    n = _lowpass(_osc(0, d, "noise"), 1400) * 0.25 * _env(int(d * SAMPLE_RATE), 0.001, 0.03, 0.1, 0.1, 0.2)
    return sq * 0.8 + n


def _sfx_block():
    d = 0.35
    a = _osc(1180, d, "sine") * _env(int(d * SAMPLE_RATE), 0.001, 0.08, 0.1, 0.2, 0.1)
    b = _osc(1760, d, "sine") * _env(int(d * SAMPLE_RATE), 0.001, 0.06, 0.05, 0.15, 0.1)
    c = _lowpass(_osc(0, d, "noise"), 6000) * _env(int(d * SAMPLE_RATE), 0.001, 0.02, 0.0, 0.05, 0.3)
    return a * 0.5 + b * 0.28 + c * 0.2


def _sfx_pad():
    d = 0.36
    body = _sweep(260, 720, d, "sine")
    body *= _env(int(d * SAMPLE_RATE), 0.004, 0.1, 0.35, 0.18, 0.25)
    body += _osc(_midi(84), d, "sine") * 0.25 * _env(int(d * SAMPLE_RATE), 0.001, 0.08, 0.0, 0.2, 0.1)
    return body


def _sfx_plate():
    d = 0.5
    click = _lowpass(_osc(0, 0.06, "noise"), 3000) * _env(int(0.06 * SAMPLE_RATE), 0.001, 0.01, 0.0, 0.01, 0.6)
    chime = (_osc(_midi(79), d, "sine") * 0.5 + _osc(_midi(86), d, "sine") * 0.4) * \
        _env(int(d * SAMPLE_RATE), 0.01, 0.12, 0.3, 0.3, 0.3)
    return _mix(click * 0.8, chime)


def _sfx_portal():
    d = 1.4
    out = np.zeros(int(d * SAMPLE_RATE), dtype=np.float32)
    for i, m in enumerate((69, 76, 81, 84, 88)):
        sig = _osc(_midi(m), d - i * 0.09, "sine") * _env(int((d - i * 0.09) * SAMPLE_RATE),
                                                            0.02, 0.2, 0.45, 0.5, 0.4)
        _place(out, sig, i * 0.09, 0.34)
    return _reverb(out, 0.3, 0.5)


def _sfx_win():
    d = 2.0
    out = np.zeros(int(d * SAMPLE_RATE), dtype=np.float32)
    seq = [(60, 0.0), (64, 0.14), (67, 0.28), (72, 0.42), (76, 0.62), (79, 0.82)]
    for m, t0 in seq:
        sig = (_osc(_midi(m), 1.1, "tri") * 0.5 + _osc(_midi(m + 12), 1.1, "sine") * 0.25)
        sig *= _env(len(sig), 0.01, 0.25, 0.35, 0.6, 0.15)
        _place(out, sig, t0, 0.4)
    return _reverb(out, 0.3, 0.55)


def _sfx_death():
    d = 1.2
    out = np.zeros(int(d * SAMPLE_RATE), dtype=np.float32)
    for i, m in enumerate((64, 60, 55, 50)):
        sig = _osc(_midi(m), 0.55, "tri") * _env(int(0.55 * SAMPLE_RATE), 0.005, 0.15, 0.3, 0.3, 0.2)
        _place(out, sig, i * 0.16, 0.4)
    low = _sweep(90, 40, 0.8) * _env(int(0.8 * SAMPLE_RATE), 0.002, 0.1, 0.3, 0.4, 0.4)
    _place(out, low, 0.0, 0.6)
    return _reverb(out, 0.25, 0.4)


def _sfx_spike():
    d = 0.4
    th = _sweep(140, 45, d) * _env(int(d * SAMPLE_RATE), 0.001, 0.05, 0.2, 0.25, 0.4)
    n = _lowpass(_osc(0, d, "noise"), 2600) * 0.5 * _env(int(d * SAMPLE_RATE), 0.001, 0.03, 0.1, 0.15, 0.3)
    return th * 0.8 + n


def _sfx_hammer():
    d = 0.8
    a = _osc(_midi(43), d, "tri") * _env(int(d * SAMPLE_RATE), 0.002, 0.18, 0.2, 0.4, 0.2)
    b = _lowpass(_osc(0, d, "noise"), 3000) * _env(int(d * SAMPLE_RATE), 0.001, 0.1, 0.1, 0.3, 0.25)
    c = _osc(_midi(74), d, "sine") * 0.2 * _env(int(d * SAMPLE_RATE), 0.001, 0.2, 0.0, 0.3, 0.1)
    return a * 0.7 + b * 0.5 + c


def _sfx_ui_hover():
    d = 0.07
    return _osc(_midi(88), d, "sine") * _env(int(d * SAMPLE_RATE), 0.001, 0.02, 0.0, 0.02, 0.05) * 0.5


def _sfx_ui_click():
    d = 0.13
    a = _osc(_midi(83), d, "tri") * _env(int(d * SAMPLE_RATE), 0.001, 0.03, 0.1, 0.06, 0.1)
    b = _osc(_midi(90), d, "sine") * 0.5 * _env(int(d * SAMPLE_RATE), 0.001, 0.03, 0.0, 0.05, 0.1)
    return a * 0.6 + b


def _sfx_checkpoint():
    d = 1.0
    out = np.zeros(int(d * SAMPLE_RATE), dtype=np.float32)
    for i, m in enumerate((72, 79, 84)):
        sig = _osc(_midi(m), 0.7, "sine") * _env(int(0.7 * SAMPLE_RATE), 0.01, 0.15, 0.3, 0.3, 0.2)
        _place(out, sig, i * 0.1, 0.35)
    return _reverb(out, 0.35, 0.5)


def _sfx_chest():
    d = 0.8
    out = np.zeros(int(d * SAMPLE_RATE), dtype=np.float32)
    for i, m in enumerate((76, 81, 83, 88, 93)):
        sig = _osc(_midi(m), 0.35, "sine") * _env(int(0.35 * SAMPLE_RATE), 0.002, 0.08, 0.0, 0.15, 0.1)
        _place(out, sig, i * 0.045, 0.28)
    return _reverb(out, 0.2, 0.35)


def _sfx_lava():
    d = 0.5
    s = _lowpass(_osc(0, d, "pink"), 900) * _env(int(d * SAMPLE_RATE), 0.02, 0.1, 0.3, 0.25, 0.2)
    return s * 0.5


def _sfx_fall():
    d = 0.7
    return _sweep(700, 90, d, "tri") * _env(int(d * SAMPLE_RATE), 0.01, 0.1, 0.5, 0.4, 0.12) * 0.7


def _sfx_bell():
    """丧钟：低频基音 + 钟体非谐分音（2.76 / 5.4 / 8.93 倍），长衰减 + 混响。"""
    d = 3.2
    out = np.zeros(int(d * SAMPLE_RATE), dtype=np.float32)
    base = 98.0
    for mult, amp, dur in ((1.0, 0.62, 3.0), (2.76, 0.30, 2.0),
                           (5.40, 0.16, 1.2), (8.93, 0.09, 0.7)):
        sig = _osc(base * mult, dur, "sine") * _env(int(dur * SAMPLE_RATE),
                                                   0.004, 0.08, 0.30, 0.5, 0.0)
        _place(out, sig, 0.0, amp)
    # 撞击瞬间的高频"叮"
    strike = _osc(1180.0, 0.09, "sine") * _env(int(0.09 * SAMPLE_RATE),
                                               0.001, 0.02, 0.02, 0.03, 0.0)
    _place(out, strike, 0.0, 0.28)
    return _reverb(out, 0.5, 0.7)


def _build_sfx():
    """构建全部音效（约 0.3~0.6 秒）。"""
    table = {
        "jump": _sfx_jump, "double_jump": _sfx_double_jump, "dash": _sfx_dash,
        "shoot": _sfx_shoot, "hit": _sfx_hit, "sword": _sfx_sword,
        "rock_break": _sfx_rock_break, "hurt": _sfx_hurt, "block": _sfx_block,
        "pad": _sfx_pad, "plate": _sfx_plate, "portal": _sfx_portal,
        "win": _sfx_win, "death": _sfx_death, "spike": _sfx_spike,
        "hammer": _sfx_hammer, "ui_hover": _sfx_ui_hover, "ui_click": _sfx_ui_click,
        "checkpoint": _sfx_checkpoint, "chest": _sfx_chest,
        "lava": _sfx_lava, "fall": _sfx_fall, "bell": _sfx_bell,
    }
    for name, fn in table.items():
        try:
            mono = fn()
            snd = _to_sound(_stereo(mono, 0.0, 0.6))
            if snd is not None:
                _sfx_bank[name] = snd
        except Exception as e:
            _log("音效 %s 构建失败: %r" % (name, e))


# --------------------------------------------------------------------------
# 配乐
# --------------------------------------------------------------------------
def _soft_pad(m, dur, gain=1.0):
    """温暖的 pad 音色：三个失谐正弦叠加 + 缓慢起振。"""
    out = np.zeros(int(dur * SAMPLE_RATE), dtype=np.float32)
    for det in (-0.006, 0.0, 0.007):
        out += _osc(_midi(m), dur, "sine", detune=det) * 0.33
    out = _lowpass(out, 1800)
    return out * _env(len(out), 0.45, 0.6, 0.7, 0.9, 0.6) * gain


def _pluck(m, dur, gain=1.0):
    out = (_osc(_midi(m), dur, "tri") * 0.65 +
           _osc(_midi(m + 12), dur, "sine") * 0.2)
    return out * _env(len(out), 0.004, 0.18, 0.16, 0.35, 0.12) * gain


def _bell(m, dur, gain=1.0):
    out = (_osc(_midi(m), dur, "sine") * 0.6 +
           _osc(_midi(m + 7), dur, "sine") * 0.18 +
           _osc(_midi(m + 12), dur, "sine") * 0.12)
    return out * _env(len(out), 0.003, 0.35, 0.1, 0.6, 0.0) * gain


def _bass(m, dur, gain=1.0):
    out = _osc(_midi(m), dur, "tri") * 0.75 + _osc(_midi(m), dur, "sine") * 0.45
    out = _lowpass(out, 420)
    return out * _env(len(out), 0.01, 0.12, 0.5, 0.2, 0.55) * gain


def _kick(gain=1.0):
    d = 0.34
    s = _sweep(150, 42, d) * _env(int(d * SAMPLE_RATE), 0.001, 0.09, 0.2, 0.2, 0.2)
    return s * gain


def _snare(gain=1.0):
    d = 0.2
    n = _lowpass(_osc(0, d, "noise"), 4200) * _env(int(d * SAMPLE_RATE), 0.001, 0.05, 0.0, 0.12, 0.15)
    t = _sweep(240, 170, 0.09) * _env(int(0.09 * SAMPLE_RATE), 0.001, 0.02, 0.0, 0.05, 0.2)
    return _mix(n * 0.7, t * 0.4) * gain


def _hat(gain=1.0, open_=False):
    d = 0.12 if open_ else 0.045
    n = _osc(0, d, "noise") * _env(int(d * SAMPLE_RATE), 0.001, 0.02, 0.0, 0.02, 0.02)
    return _lowpass(n, 12000) * gain


def _master(x, peak=0.86):
    """统一电平并做 8ms 收尾淡化，避免循环接缝爆音。"""
    try:
        p = float(np.max(np.abs(x))) or 1.0
        x = (x * (peak / p)).astype(np.float32)
        n = int(0.008 * SAMPLE_RATE)
        if len(x) > n * 3:
            x[:n] *= np.linspace(0.0, 1.0, n, dtype=np.float32)
            x[-n:] *= np.linspace(1.0, 0.0, n, dtype=np.float32)
        return x
    except Exception:
        return x


def _render_track(events, total, gain=1.0):
    buf = np.zeros(int(total * SAMPLE_RATE) + SAMPLE_RATE, dtype=np.float32)
    for sig, at, g in events:
        _place(buf, sig, at, g)
    return buf * gain


def _compose_menu():
    """菜单：84 BPM，Am - F - C - G，钟琴 + 暖 pad，氛围感。"""
    bpm = 84.0
    beat = 60.0 / bpm
    bars = 8
    total = bars * 4 * beat
    chords = [(57, [57, 60, 64]), (53, [53, 57, 60]), (48, [48, 52, 55]), (55, [55, 59, 62])]
    pad_ev, bell_ev, bass_ev = [], [], []
    for b in range(bars):
        root, notes = chords[b % 4]
        t0 = b * 4 * beat
        for m in notes:
            pad_ev.append((_soft_pad(m, 4 * beat * 1.05, 0.28), t0, 0.6))
        bass_ev.append((_bass(root - 12, 2 * beat, 0.35), t0, 0.5))
        bass_ev.append((_bass(root - 12, 2 * beat, 0.28), t0 + 2 * beat, 0.45))
        # 分解和弦：每拍一个音，逐渐上行
        pattern = [0, 1, 2, 1, 2, 1, 0, 2]
        for i in range(8):
            m = notes[pattern[i]] + 12
            bell_ev.append((_bell(m, 1.6, 0.3), t0 + i * beat * 0.5, 0.42))
    mix = (_render_track(pad_ev, total, 0.55) +
           _render_track(bell_ev, total, 0.6) +
           _render_track(bass_ev, total, 0.45))
    # 轻微"呼吸"滤波，增加氛围
    t = np.arange(len(mix), dtype=np.float32) / SAMPLE_RATE
    mix *= (0.85 + 0.15 * np.sin(2 * math.pi * 0.06 * t)).astype(np.float32)
    return _master(_reverb(mix[:int(total * SAMPLE_RATE)], 0.3, 0.4))


def _compose_explore():
    """探索：100 BPM，Dm - Bb - F - C，拨弦 + 低音 + 轻鼓。"""
    bpm = 100.0
    beat = 60.0 / bpm
    bars = 8
    total = bars * 4 * beat
    chords = [(50, [50, 53, 57]), (46, [46, 50, 53]), (41, [41, 45, 48]), (48, [48, 52, 55])]
    pluck_ev, bass_ev, drum_ev = [], [], []
    for b in range(bars):
        root, notes = chords[b % 4]
        t0 = b * 4 * beat
        bass_ev.append((_bass(root - 12, beat * 1.8, 0.4), t0, 0.55))
        bass_ev.append((_bass(root - 12, beat * 1.8, 0.32), t0 + 2 * beat, 0.5))
        for i in range(8):
            m = notes[(i * 2) % 3] + (12 if i % 4 == 2 else 0)
            pluck_ev.append((_pluck(m, 0.9, 0.3), t0 + i * beat * 0.5, 0.5))
        for i in range(4):
            drum_ev.append((_kick(0.55), t0 + i * beat, 0.5))
            if i % 2 == 1:
                drum_ev.append((_snare(0.32), t0 + i * beat, 0.4))
            drum_ev.append((_hat(0.18), t0 + i * beat + beat * 0.5, 0.35))
    mix = (_render_track(pluck_ev, total, 0.5) +
           _render_track(bass_ev, total, 0.5) +
           _render_track(drum_ev, total, 0.45))
    return _master(_reverb(mix[:int(total * SAMPLE_RATE)], 0.16, 0.28))


def _compose_battle():
    """战斗：132 BPM，Dm - Bb - Gm - A，16 分琶音 + 驱动鼓组。"""
    bpm = 132.0
    beat = 60.0 / bpm
    bars = 8
    total = bars * 4 * beat
    chords = [(50, [50, 53, 57]), (46, [46, 50, 53]), (43, [43, 46, 50]), (45, [45, 49, 52])]
    arp_ev, bass_ev, drum_ev, pad_ev = [], [], [], []
    for b in range(bars):
        root, notes = chords[b % 4]
        t0 = b * 4 * beat
        for m in notes:
            pad_ev.append((_soft_pad(m, 4 * beat, 0.14), t0, 0.4))
        for i in range(16):
            m = notes[i % 3] + (12 if i % 8 >= 4 else 0)
            g = 0.34 if i % 4 == 0 else 0.22
            arp_ev.append((_pluck(m, 0.42, g), t0 + i * beat * 0.25, 0.55))
        for i in range(4):
            drum_ev.append((_kick(0.7), t0 + i * beat, 0.5))
            drum_ev.append((_snare(0.4), t0 + i * beat + beat * 0.5, 0.42))
            drum_ev.append((_hat(0.14, open_=(i == 3)), t0 + i * beat + beat * 0.25, 0.3))
        bass_ev.append((_bass(root - 12, beat * 0.9, 0.45), t0, 0.55))
        bass_ev.append((_bass(root - 12, beat * 0.9, 0.4), t0 + beat * 2, 0.5))
        bass_ev.append((_bass(root - 5, beat * 0.9, 0.32), t0 + beat * 3, 0.45))
    mix = (_render_track(arp_ev, total, 0.5) +
           _render_track(bass_ev, total, 0.55) +
           _render_track(drum_ev, total, 0.5) +
           _render_track(pad_ev, total, 0.35))
    return _master(_reverb(mix[:int(total * SAMPLE_RATE)], 0.12, 0.22))


def _compose_boss():
    """Boss 战：152 BPM，Dm - Bb - Gm - A，低音铜管 + 密集鼓点 + 半音紧张感。"""
    bpm = 152.0
    beat = 60.0 / bpm
    bars = 8
    total = bars * 4 * beat
    chords = [(50, [50, 53, 57]), (46, [46, 50, 53]), (43, [43, 46, 50]), (45, [45, 49, 52])]
    arp, bass, drum, pad = [], [], [], []
    for b in range(bars):
        root, notes = chords[b % 4]
        t0 = b * 4 * beat
        for m in notes:
            pad.append((_soft_pad(m, 4 * beat, 0.16), t0, 0.4))
        for i in range(16):
            m = notes[i % 3] + (12 if i % 8 >= 4 else 0)
            g = 0.40 if i % 4 == 0 else 0.24
            arp.append((_pluck(m, 0.36, g), t0 + i * beat * 0.25, 0.6))
        for i in range(4):
            drum.append((_kick(0.9), t0 + i * beat, 0.55))
            drum.append((_kick(0.5), t0 + i * beat + beat * 0.5, 0.4))
            drum.append((_snare(0.5), t0 + i * beat + beat * 0.5, 0.45))
            drum.append((_hat(0.16, open_=(i == 3)), t0 + i * beat + beat * 0.25, 0.32))
        # 低音铜管：每拍一记，半音下行制造压迫感
        for i, iv in enumerate((0, 0, -1, 0)):
            bass.append((_bass(root - 12 + iv, beat * 0.85, 0.5), t0 + i * beat, 0.6))
    mix = (_render_track(arp, total, 0.5) +
           _render_track(bass, total, 0.6) +
           _render_track(drum, total, 0.55) +
           _render_track(pad, total, 0.3))
    return _master(_reverb(mix[:int(total * SAMPLE_RATE)], 0.1, 0.2))


def _build_music_all():
    """后台构建全部配乐，构建好一段就能立刻播放。"""
    builders = {"menu": _compose_menu, "explore": _compose_explore,
                "battle": _compose_battle, "boss": _compose_boss}
    for name, fn in builders.items():
        if _stop.is_set():
            return
        try:
            t0 = time.time()
            mono = fn()
            snd = _to_sound(_stereo(mono, 0.0, 0.9))
            if snd is not None:
                with _lock:
                    _music_bank[name] = snd
                    _music_ready.add(name)
                _log("配乐 %s 就绪 (%.1fs, %.1fs)" % (name, time.time() - t0,
                                                     len(mono) / float(SAMPLE_RATE)))
                if _current_music == name:
                    _start_music_channel(name)
        except Exception as e:
            _log("配乐 %s 构建失败: %r" % (name, e))


# --------------------------------------------------------------------------
# 播放接口
# --------------------------------------------------------------------------
def sfx(name, vol=1.0, pan=0.0):
    """播放音效。name 不存在时静默忽略。"""
    if not _ok:
        return
    try:
        snd = _sfx_bank.get(name)
        if snd is None:
            return
        ch = mixer.find_channel(True)
        if ch is None:
            return
        v = _vol["master"] * _vol["sfx"] * max(0.0, min(2.0, vol))
        ch.set_volume(theme_clamp(v))
        ch.play(snd)
    except Exception:
        pass


def theme_clamp(v):
    """容错钳制：传入非数字时按 0 处理（设置文件损坏也不应让游戏崩掉）。"""
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def play_music(name, fade=1.2):
    """切换背景音乐（循环）。同曲重入不重启。"""
    global _current_music
    if not _ok:
        return
    if name == _current_music and _music_chan is not None:
        try:
            if _music_chan.get_busy():
                return
        except Exception:
            pass
    _current_music = name
    if name in _music_ready:
        _start_music_channel(name, fade)
    # 未就绪：构建完成后自动开始（见 _build_music_all）


def _start_music_channel(name, fade=1.2):
    global _music_chan
    try:
        snd = _music_bank.get(name)
        if snd is None:
            return
        old = _music_chan
        ch = mixer.find_channel(True)
        if ch is None:
            ch = mixer.Channel(0)
        ch.play(snd, loops=-1)
        ch.set_volume(theme_clamp(_vol["master"] * _vol["music"] * _cur_music_vol))
        _music_chan = ch
        if old is not None and old is not ch:
            try:
                old.fadeout(int(fade * 1000))
            except Exception:
                old.stop()
    except Exception:
        pass


def stop_music(fade=0.8):
    global _current_music
    _current_music = None
    try:
        if _music_chan is not None:
            _music_chan.fadeout(int(fade * 1000))
    except Exception:
        pass


def set_volume(master=None, music=None, sfx_=None):
    if master is not None:
        _vol["master"] = theme_clamp(master)
    if music is not None:
        _vol["music"] = theme_clamp(music)
    if sfx_ is not None:
        _vol["sfx"] = theme_clamp(sfx_)
    try:
        if _music_chan is not None:
            _music_chan.set_volume(theme_clamp(_vol["master"] * _vol["music"] * _cur_music_vol))
    except Exception:
        pass


def get_volume():
    return dict(_vol)


def music_duck(amount=0.45, hold=1.4):
    """短暂的"压低音乐"（用于通关/死亡演出）。"""
    global _cur_music_vol
    _cur_music_vol = max(0.0, 1.0 - amount)
    try:
        if _music_chan is not None:
            _music_chan.set_volume(theme_clamp(_vol["master"] * _vol["music"] * _cur_music_vol))
    except Exception:
        pass

    def _restore():
        global _cur_music_vol
        time.sleep(hold)
        _cur_music_vol = 1.0
        try:
            if _music_chan is not None:
                _music_chan.set_volume(theme_clamp(_vol["master"] * _vol["music"]))
        except Exception:
            pass

    threading.Thread(target=_restore, daemon=True).start()


def shutdown(timeout=2.0):
    """停止后台合成线程并关闭混音器。

    单文件 exe 里如果合成线程还在合成时解释器开始退出，
    PyInstaller 的父进程会一直等着，表现为"关掉游戏进程却残留/卡住"。
    """
    try:
        _stop.set()
        t = _music_thread
        if t is not None and t.is_alive():
            t.join(timeout)
    except Exception:
        pass
    try:
        mixer.quit()
    except Exception:
        pass


def is_ok():
    return _ok


def status():
    return {"mixer": _ok, "sfx": len(_sfx_bank), "music": sorted(_music_ready)}
