# -*- coding: utf-8 -*-
"""把 CC0 钟声素材处理成「丧钟」：降调 + 补低频 + 削高频 + 长尾。

用法: python tools/build_bell.py
输出: assets/sfx/bell.wav, shots/bell_ab_a.wav, shots/bell_ab_b.wav
"""
import os, sys, wave
import numpy as np

SR = 44100
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SFX = os.path.join(ROOT, "assets", "sfx")


def read_wav(p):
    w = wave.open(p, "rb")
    sr = w.getframerate()
    n = w.getnframes()
    ch = w.getnchannels()
    a = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    assert sr == SR, "采样率需为 44100"
    return a


def write_wav(p, x):
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def pitch_down(x, factor):
    """降调（同时变长）：factor<1 -> 音高变低、时长 /factor。线性插值，不产生混叠。"""
    n = int(len(x) / factor)
    idx = np.arange(n) * factor
    return np.interp(idx, np.arange(len(x)), x).astype(np.float32)


def lowpass(x, fc, order=2):
    """简单一阶级联低通（零相位近似用前后各滤一遍）。"""
    a = np.exp(-2.0 * np.pi * fc / SR)
    y = x.copy()
    for _ in range(order):
        out = np.empty_like(y)
        acc = 0.0
        for i in range(len(y)):
            acc = (1 - a) * y[i] + a * acc
            out[i] = acc
        y = out
    return y


def lowpass_fft(x, fc):
    """频域一阶低通，比逐样本快，且相位可控（这里只用幅度）。"""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / SR)
    H = 1.0 / (1.0 + (f / max(1.0, fc)) ** 2)
    return np.fft.irfft(X * H, n=len(x)).astype(np.float32)


def shelf_low(x, fc, gain):
    """低频搁架：低于 fc 的部分乘 (1+gain)。"""
    low = lowpass_fft(x, fc)
    return (x + gain * low).astype(np.float32)


def reverb_tail(x, length=2.2, tau=0.55, wet=0.30, seed=7):
    """用指数衰减噪声当冲激响应做卷积，给钟声接一条自然的尾音。

    源素材只有 2.9 秒，降调拉长到 3.7 秒后尾音还是断得太早；
    真大钟会响 5 秒以上，靠混响尾补齐比直接加正弦自然。
    """
    rng = np.random.RandomState(seed)
    n_ir = int(length * SR)
    t = np.arange(n_ir) / SR
    ir = rng.randn(n_ir).astype(np.float32) * np.exp(-t / tau)
    # 高频衰减更快：IR 做低通，避免"金属味"太亮
    ir = lowpass_fft(ir, 1100.0)
    ir /= max(1e-9, float(np.abs(ir).max()))
    ir[0] = 1.0                                   # 直达声
    n = len(x) + n_ir
    nfft = 1 << (n - 1).bit_length()
    Y = np.fft.rfft(x, nfft) * np.fft.rfft(ir, nfft)
    y = np.fft.irfft(Y, nfft)[:n].astype(np.float32)
    # 直达声与湿声按 wet 混合（湿声只保留尾部，避免起音被糊）
    dry = np.zeros(n, dtype=np.float32)
    dry[:len(x)] = x
    return (dry + wet * (y - dry[:n] if False else y)).astype(np.float32)


def make(x, pitch=0.78, sub=1.0, dur=None, fade=0.55, keep_attack=0.09, wet=0.30):
    y = pitch_down(x, pitch)
    # 起音瞬态保持原样（不降调）：真大钟被敲的那一下是"亮"的，
    # 全段降调会让敲击声也变闷，听起来像录音被放慢了。
    if keep_attack > 0:
        nA = int(keep_attack * SR)
        if nA < len(y) and nA < len(x):
            body_rms = float(np.sqrt((y[nA:nA + 2000] ** 2).mean()))
            atk = x[:nA].copy()
            atk_rms = float(np.sqrt((atk ** 2).mean())) or 1.0
            atk *= body_rms / atk_rms          # 音量对齐，别让起音把整段压低
            k = np.linspace(0.0, 1.0, nA) ** 1.6
            y[:nA] = y[:nA] * k + atk * (1.0 - k)
    n = len(y)
    t = np.arange(n) / SR

    # 次低频层：给"体量"，不是靠音高而是靠 60~95Hz 的能量
    if sub > 0:
        # 幅度必须小：次低频只是"体量"，一旦盖过钟体本身就成了电子轰声
        s = (0.10 * np.sin(2 * np.pi * 62.0 * t) * np.exp(-t / 1.55)
             + 0.07 * np.sin(2 * np.pi * 93.0 * t) * np.exp(-t / 1.15)
             + 0.04 * np.sin(2 * np.pi * 124.0 * t) * np.exp(-t / 0.85))
        s *= np.clip(t / 0.015, 0.0, 1.0)          # 15ms 起振，别"啪"一下
        y = y + sub * s

    if wet > 0:
        y = reverb_tail(y, length=2.2, tau=0.55, wet=wet)
    # 总时长裁剪放在混响之后（否则混响又把尾巴接回去了）
    if dur and len(y) > int(dur * SR):
        y = y[:int(dur * SR)]
    y = shelf_low(y, 190.0, 0.45)                  # 低频搁架 +45%（别压过钟体）
    y = lowpass_fft(y, 3200.0)                     # 削掉 3.2k 以上的"脆"
    y = lowpass_fft(y, 3000.0)                     # 混响带来的沙沙声再压一道

    # 尾部淡出，避免咔哒
    f = int(fade * SR)
    if len(y) > f:
        y[-f:] *= (np.linspace(1.0, 0.0, f) ** 1.4)
    pk = float(np.abs(y).max())
    if pk > 1e-6:
        y = (y / pk * 0.92).astype(np.float32)
    return y


def bands(x, label):
    seg = x[:int(min(len(x), 2.0 * SR))]
    seg = seg * np.hanning(len(seg))
    sp = np.abs(np.fft.rfft(seg))
    f = np.fft.rfftfreq(len(seg), 1.0 / SR)
    sp = sp / max(1e-9, sp.max())
    out = []
    for lo, hi in ((30, 60), (60, 100), (100, 160), (160, 260),
                   (260, 420), (420, 700), (700, 1200), (1200, 3000)):
        m = (f >= lo) & (f < hi)
        out.append("%d-%d:%.2f" % (lo, hi, float(sp[m].max())))
    # 衰减：0.5/1.5/2.5/3.5s 的 RMS
    dec = []
    for ts in (0.5, 1.5, 2.5, 3.5):
        i = int(ts * SR)
        if i + 4000 < len(x):
            dec.append("%.2f" % float(np.sqrt((x[i:i + 4000] ** 2).mean())))
        else:
            dec.append("-")
    print("%-10s 时长%.2fs  %s" % (label, len(x) / SR, " ".join(out)))
    print("%-10s RMS@0.5/1.5/2.5/3.5s: %s" % ("", "/".join(dec)))


if __name__ == "__main__":
    # 读原始单响（不是上次的处理结果，否则重跑会二次降调）
    base = read_wav(os.path.join(SFX, "bell_source.wav"))
    print("基准（当前 bell.wav）:")
    bands(base, "base")

    # A：降 -4.3 半音，中等次低频（保守，最像真钟）
    a = make(base, pitch=0.76, sub=0.55, dur=4.2, fade=0.7, wet=0.24)
    bands(a, "A -4.3半音")
    write_wav(os.path.join(ROOT, "shots", "bell_ab_a.wav"), a)

    # B：降 -6.2 半音，次低频更足（最沉）
    b = make(base, pitch=0.68, sub=0.70, dur=4.6, fade=0.7, wet=0.24)
    bands(b, "B -6.2半音")
    write_wav(os.path.join(ROOT, "shots", "bell_ab_b.wav"), b)
    print("已导出 shots/bell_ab_a.wav / bell_ab_b.wav")

    # 定稿：A 档参数再沉半档（-5.5 半音），写入 assets/sfx/bell.wav
    final = make(base, pitch=0.72, sub=0.65, dur=4.3, fade=0.7, wet=0.24)
    bands(final, "定稿")
    write_wav(os.path.join(SFX, "bell.wav"), final)
    write_wav(os.path.join(ROOT, "shots", "bell_deep_preview.wav"), final)
    print("定稿写入 assets/sfx/bell.wav")
