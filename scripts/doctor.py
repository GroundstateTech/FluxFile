#!/usr/bin/env python3
import importlib.util
import platform
import shutil
import sys

print(f"FluxFile doctor")
print(f"Python: {sys.version.split()[0]} ({platform.platform()})")
print(f"Tkinter: ", end="")
try:
    import tkinter
    print("OK")
except Exception as exc:
    print(f"MISSING ({exc})")

for binary in ("pandoc", "libreoffice", "soffice"):
    print(f"{binary}: {shutil.which(binary) or 'not found'}")

for module in ("PIL", "pandas", "openpyxl", "odf", "pdf2docx"):
    print(f"{module}: {'OK' if importlib.util.find_spec(module) else 'not installed'}")
