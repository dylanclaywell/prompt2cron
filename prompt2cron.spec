# PyInstaller spec for prompt2cron.
# Build with:  uv run pyinstaller prompt2cron.spec
#
# A few packages need their data/backends force-collected or the frozen app
# breaks at runtime:
#   - customtkinter   ships theme JSON + assets (not just .py)
#   - cron_descriptor ships locale files for the descriptions
#   - keyring         discovers OS backends via entry points
#   - certifi         ships the CA bundle httpx/anthropic need for TLS
#   - anthropic       pull in submodules so lazy imports resolve

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
for pkg in ("customtkinter", "cron_descriptor", "keyring", "certifi", "anthropic"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Windows credential-store backend + its native bridge.
hiddenimports += ["keyring.backends.Windows", "win32ctypes.core"]

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir: binaries/datas go in COLLECT below
    name="prompt2cron",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # windowed app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="prompt2cron",
)
