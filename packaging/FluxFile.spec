# PyInstaller configuration for the FluxFile desktop app.

from pathlib import Path

project = Path(SPECPATH).resolve().parent

analysis = Analysis(
    [str(project / "fluxfile.py")],
    pathex=[str(project)],
    binaries=[],
    datas=[],
    hiddenimports=["openpyxl", "odf.opendocument", "odf.table", "odf.text", "xlrd"],
    hookspath=[],
    excludes=[],
    noarchive=False,
)
modules = PYZ(analysis.pure)

desktop = EXE(
    modules,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="FluxFile",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

distribution = COLLECT(
    desktop,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="FluxFile",
)
