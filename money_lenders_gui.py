#!/usr/bin/env python3
"""
香港放債人牌照資料管理 — 圖形介面
================================
包裝 update_money_lenders.py 的完整功能。

相依套件：
    pip install pdfplumber requests

執行：
    python money_lenders_gui.py
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path
from tkinter import (
    Tk, Frame, Label, Button, Text, Scrollbar, Entry, Toplevel,
    StringVar, filedialog, messagebox, simpledialog,
    END, BOTH, LEFT, RIGHT, X, Y, WORD, DISABLED, NORMAL,
)
from tkinter import ttk
from tkinter import font as tkfont

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    import update_money_lenders as ml
except ImportError:
    print("錯誤：找不到 update_money_lenders.py")
    print("請把 money_lenders_gui.py 與 update_money_lenders.py 放在同一資料夾後再執行。")
    sys.exit(1)

_FONT_FAMILY = None

def _pick_font_family() -> str:
    global _FONT_FAMILY
    if _FONT_FAMILY:
        return _FONT_FAMILY
    candidates = [
        "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI",
        "PingFang HK", "PingFang TC", "Noto Sans CJK TC",
        "Arial", "Helvetica", "TkDefaultFont",
    ]
    try:
        available = set(tkfont.families())
    except Exception:
        available = set()
    for name in candidates:
        if name in available:
            _FONT_FAMILY = name
            break
    else:
        _FONT_FAMILY = "TkDefaultFont"
    return _FONT_FAMILY

def F(size: int = 10, weight: str = "normal") -> tuple:
    family = _pick_font_family()
    if weight and weight != "normal":
        return (family, size, weight)
    return (family, size)

def F_mono(size: int = 9) -> tuple:
    try:
        available = set(tkfont.families())
    except Exception:
        available = set()
    for name in ("Consolas", "Cascadia Mono", "Courier New", "Menlo", "Monaco", "TkFixedFont"):
        if name in available:
            return (name, size)
    return ("TkFixedFont", size)
