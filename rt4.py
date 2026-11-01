import subprocess, io
py = r"C:/Users/clm/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
tests = ["test_move.py", "test_pit.py", "test_gameplay.py",
         "test_flow.py", "test_audit.py", "test_fuzz.py"]
lines = []
for t in tests:
    p = subprocess.run([py, t], cwd=r"C:/Users/clm/Desktop/game",
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    lines.append("%s rc=%d" % (t, p.returncode))
    for ln in (p.stdout or "").splitlines():
        if "FAIL" in ln:
            lines.append("    " + ln.strip())
io.open(r"C:/Users/clm/Desktop/game/tr4.txt", "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines))
