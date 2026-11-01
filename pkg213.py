import os, shutil, zipfile, tempfile
old = "dist/暮色之前"
if os.path.isdir(old):
    tmp = os.path.join(tempfile.gettempdir(), "before_dusk_v212_backup")
    if os.path.exists(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
    shutil.move(old, tmp)
shutil.move("dist2/暮色之前", "dist/暮色之前")
try:
    os.rmdir("dist2")
except Exception as e:
    print("dist2:", e)
shutil.copyfile("dist_玩前必读.txt", "dist/暮色之前/玩前必读.txt")
for f in os.listdir("dist"):
    if f.endswith(".zip"):
        os.remove(os.path.join("dist", f))
zpath = "dist/暮色之前-v2.13-win64.zip"
with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk("dist/暮色之前"):
        for f in files:
            full = os.path.join(root, f)
            z.write(full, os.path.relpath(full, "dist"))
print("zip %.1f MB" % (os.path.getsize(zpath) / 1048576))
