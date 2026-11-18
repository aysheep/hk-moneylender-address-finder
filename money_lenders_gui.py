#!/usr/bin/env python3
"""
香港放債人牌照資料管理 — 圖形介面
================================
包裝 update_money_lenders.py 的完整功能。

日常使用以搜尋、列表、詳情複製為主；更新／匯入／匯出放在選單。

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
    StringVar, filedialog, messagebox, simpledialog, Menu,
    END, BOTH, LEFT, RIGHT, X, Y, WORD, DISABLED, NORMAL, N,
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


NAVY = "#1a365d"
NAVY_SOFT = "#2a4365"
INK = "#1a202c"
MUTED = "#718096"
LINE = "#e2e8f0"
PAPER = "#ffffff"
CANVAS = "#f4f6f8"
CHIP = "#eef2f6"
MISSING = "#9b2c2c"
PLACEHOLDER = "輸入中文或英文名稱、地址…"
LIST_LIMIT = 500


# ────────────────────────────────────────────────
# 跨平台安全字型
# ────────────────────────────────────────────────

_FONT_FAMILY = None


def _pick_font_family() -> str:
    global _FONT_FAMILY
    if _FONT_FAMILY:
        return _FONT_FAMILY
    candidates = [
        "Microsoft JhengHei UI",
        "Microsoft JhengHei",
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "PingFang HK",
        "PingFang TC",
        "Noto Sans CJK HK",
        "Noto Sans CJK TC",
        "Source Han Sans TC",
        "WenQuanYi Micro Hei",
        "Segoe UI",
        "Arial",
        "Helvetica",
        "TkDefaultFont",
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


# ────────────────────────────────────────────────
# 主視窗
# ────────────────────────────────────────────────

class MoneyLendersGUI:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("香港放債人牌照資料管理工具")
        self.root.geometry("1120x760")
        self.root.minsize(980, 640)
        self.root.configure(bg=CANVAS)

        self.busy = False
        self.companies: list[dict] = []
        self._result_rows: list[dict] = []
        self._detail_company: dict | None = None
        self._job_menus: list[tuple[Menu, int]] = []
        self._context_cell = ""
        self._search_placeholder_active = False
        self._updating_search = False
        self._search_job = None
        self._ui_ready = False
        self._log_open = False
        self.filter_mode = "all"  # "all" | "missing"
        self._detail_values: dict[str, Label] = {}
        self._detail_buttons: dict[str, Button] = {}
        self._gazette_values: dict[str, Label] = {}

        self._init_style()
        self._build_ui()
        self._ui_ready = True
        self.refresh_stats()

    # ── 外觀 ─────────────────────────────────────

    def _init_style(self):
        style = ttk.Style(self.root)
        try:
            if sys.platform != "win32":
                style.theme_use("clam")
        except Exception:
            pass
        try:
            style.configure(
                "Treeview",
                font=F(10),
                rowheight=28,
                background=PAPER,
                fieldbackground=PAPER,
                borderwidth=0,
                relief="flat",
            )
            style.configure(
                "Treeview.Heading",
                font=F(9, "bold"),
                background=CHIP,
                foreground=NAVY,
                relief="flat",
            )
            style.map(
                "Treeview",
                background=[("selected", NAVY)],
                foreground=[("selected", PAPER)],
            )
        except Exception:
            pass
        try:
            style.configure(
                "Busy.Horizontal.TProgressbar",
                thickness=8,
                background=NAVY,
                troughcolor="#cbd5e0",
                bordercolor="#cbd5e0",
                lightcolor=NAVY,
                darkcolor=NAVY,
            )
        except Exception:
            pass

    def _style_menu(self, menu: Menu):
        try:
            menu.configure(
                font=F(10),
                bg=PAPER,
                fg=INK,
                activebackground=NAVY,
                activeforeground=PAPER,
                relief="flat",
            )
        except Exception:
            pass

    def _add_cmd(self, menu: Menu, label: str, command, *, job: bool = False, accelerator: str = ""):
        kwargs = {"label": label, "command": command}
        if accelerator:
            kwargs["accelerator"] = accelerator
        menu.add_command(**kwargs)
        if job:
            end = menu.index(END)
            if end is not None:
                self._job_menus.append((menu, end))

    def _quiet_button(self, parent, text, command, *, primary: bool = False) -> Button:
        if primary:
            bg, fg, active = NAVY, PAPER, NAVY_SOFT
        else:
            bg, fg, active = PAPER, NAVY, CHIP
        return Button(
            parent,
            text=text,
            command=command,
            font=F(8),
            bg=bg,
            fg=fg,
            activebackground=active,
            activeforeground=fg,
            disabledforeground="#a0aec0",
            relief="solid",
            bd=1,
            highlightthickness=0,
            padx=8,
            pady=2,
            cursor="hand2",
        )

    def _build_ui(self):
        self._build_header()
        self._build_menu()
        self._build_toolbar()
        self._build_search()
        self._build_footer()
        self._build_main()
        self._install_shortcuts()
        self._set_search_placeholder()

    def _build_header(self):
        header = Frame(self.root, bg=NAVY)
        header.pack(fill=X)
        Label(
            header,
            text="香港放債人牌照資料管理工具",
            font=F(14, "bold"),
            fg=PAPER,
            bg=NAVY,
            padx=14,
            pady=8,
        ).pack(side=LEFT)

    def _build_menu(self):
        # 原生選單列（在標題列下方）。Menubutton 在部分 Linux/X11 上點了不會展開。
        menubar = Menu(self.root, tearoff=0)
        self.root.configure(menu=menubar)

        file_menu = Menu(menubar, tearoff=0)
        self._add_cmd(file_menu, "新增", self.on_add_company, job=True)
        self._add_cmd(file_menu, "刪除選取", self.on_delete_company, job=True)
        self._add_cmd(file_menu, "重新整理", self.refresh_stats, job=True, accelerator="F5")
        file_menu.add_separator()
        self._add_cmd(file_menu, "開啟資料夾", self.open_folder)
        self._add_cmd(file_menu, "開啟 Google Sheet", self.open_sheet)
        file_menu.add_separator()
        self._add_cmd(file_menu, "結束", self.root.destroy)

        maint_menu = Menu(menubar, tearoff=0)
        self._add_cmd(maint_menu, "更新官方名稱", self.on_update_names, job=True)
        self._add_cmd(maint_menu, "憲報 PDF 提取地址", self.on_gazette, job=True)
        self._add_cmd(maint_menu, "本地持牌人 PDF", self.on_import_licensee_pdf, job=True)
        maint_menu.add_separator()
        self._add_cmd(maint_menu, "從 Google Sheet 匯入", self.on_import_sheet, job=True)
        self._add_cmd(maint_menu, "設定 Sheet URL", self.on_set_sheet_url, job=True)
        self._add_cmd(maint_menu, "從 CSV 匯入", self.on_import_csv, job=True)
        maint_menu.add_separator()
        self._add_cmd(maint_menu, "匯出 CSV", self.on_export, job=True)

        settings_menu = Menu(menubar, tearoff=0)
        self._add_cmd(settings_menu, "設定 Google Sheet URL", self.on_set_sheet_url, job=True)
        self._add_cmd(settings_menu, "開啟 Google Sheet", self.open_sheet)

        help_menu = Menu(menubar, tearoff=0)
        self._add_cmd(help_menu, "使用說明", self.on_help)
        help_menu.add_separator()
        self._add_cmd(
            help_menu,
            "e-Search 官方查冊",
            lambda: webbrowser.open("https://www.e-services.cr.gov.hk"),
        )
        self._add_cmd(
            help_menu,
            "政府憲報",
            lambda: webbrowser.open("https://www.gld.gov.hk/egazette/"),
        )
        self._add_cmd(
            help_menu,
            "data.gov.hk 放債人",
            lambda: webbrowser.open(
                "https://data.gov.hk/tc-data/dataset/hk-cr-crdata-list-of-licensed-money-lenders"
            ),
        )
        help_menu.add_separator()
        self._add_cmd(help_menu, "關於", self.on_about)

        self.file_menu = file_menu
        self.maint_menu = maint_menu
        self.settings_menu = settings_menu
        self.help_menu = help_menu
        for menu in (file_menu, maint_menu, settings_menu, help_menu):
            self._style_menu(menu)

        menubar.add_cascade(label="檔案", menu=file_menu)
        menubar.add_cascade(label="維護", menu=maint_menu)
        menubar.add_cascade(label="設定", menu=settings_menu)
        menubar.add_cascade(label="說明", menu=help_menu)

    def _build_toolbar(self):
        toolbar = Frame(self.root, bg=CANVAS)
        toolbar.pack(fill=X)

        stats = Frame(toolbar, bg=CANVAS)
        stats.pack(side=LEFT, padx=8, pady=8)
        self.var_total = StringVar(value="—")
        self.var_with_addr = StringVar(value="—")
        self.var_no_addr = StringVar(value="—")
        self._stat_chip(stats, "公司總數", self.var_total, NAVY)
        self._stat_chip(stats, "已有地址", self.var_with_addr, NAVY)
        self._stat_chip(stats, "尚未有地址", self.var_no_addr, MISSING)

        filters = Frame(toolbar, bg=CANVAS)
        filters.pack(side=RIGHT, padx=8, pady=8)
        self.btn_show_all = self._filter_chip(filters, "顯示全部", self.on_show_all)
        self.btn_show_missing = self._filter_chip(filters, "只看缺地址", self.on_show_missing)
        self._style_filter_chips()

    def _stat_chip(self, parent, caption: str, var: StringVar, color: str):
        box = Frame(parent, bg=PAPER, highlightbackground=LINE, highlightthickness=1)
        box.pack(side=LEFT, padx=4)
        Label(
            box, text=caption, font=F(8), fg=MUTED, bg=PAPER, padx=10, pady=4,
        ).pack(side=LEFT)
        Label(
            box, textvariable=var, font=F(11, "bold"), fg=color, bg=PAPER, padx=8, pady=4,
        ).pack(side=LEFT)

    def _filter_chip(self, parent, text: str, command) -> Button:
        btn = Button(
            parent,
            text=text,
            command=command,
            font=F(9),
            relief="flat",
            bd=0,
            highlightthickness=1,
            padx=12,
            pady=4,
            cursor="hand2",
        )
        btn.pack(side=LEFT, padx=4)
        return btn

    def _style_filter_chips(self):
        pairs = (
            (self.btn_show_all, self.filter_mode == "all"),
            (self.btn_show_missing, self.filter_mode == "missing"),
        )
        for btn, active in pairs:
            if active:
                btn.configure(
                    bg=NAVY,
                    fg=PAPER,
                    activebackground=NAVY_SOFT,
                    activeforeground=PAPER,
                    highlightbackground=NAVY,
                )
            else:
                btn.configure(
                    bg=PAPER,
                    fg=NAVY,
                    activebackground=CHIP,
                    activeforeground=NAVY,
                    highlightbackground=LINE,
                )

    def _build_search(self):
        wrap = Frame(self.root, bg=CANVAS)
        wrap.pack(fill=X, padx=12, pady=4)
        box = Frame(wrap, bg=PAPER, highlightbackground=LINE, highlightthickness=1)
        box.pack(side=LEFT, fill=X, expand=True)
        self._search_box = box
        self.search_var = StringVar()
        self.search_var.trace_add("write", self._on_search_write)
        self.search_entry = Entry(
            box,
            textvariable=self.search_var,
            font=F(12),
            relief="flat",
            bg=PAPER,
            fg=INK,
            insertbackground=INK,
            highlightthickness=0,
        )
        self.search_entry.pack(fill=X, padx=10, ipady=6)
        self.search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self.search_entry.bind("<FocusOut>", self._on_search_focus_out)
        self.search_entry.bind("<Return>", self._on_search_enter)
        self.search_entry.bind("<Escape>", self._on_search_escape)

        self.var_shown = StringVar(value="")
        Label(
            wrap, textvariable=self.var_shown, font=F(9), fg=MUTED, bg=CANVAS, padx=10,
        ).pack(side=RIGHT)

    def _build_main(self):
        main = Frame(self.root, bg=CANVAS)
        main.pack(fill=BOTH, expand=True, padx=12, pady=6)

        self.paned = ttk.Panedwindow(main, orient="horizontal")
        self.paned.pack(fill=BOTH, expand=True)

        list_card = Frame(self.paned, bg=PAPER, highlightbackground=LINE, highlightthickness=1)
        detail_card = Frame(self.paned, bg=PAPER, highlightbackground=LINE, highlightthickness=1)
        self.paned.add(list_card, weight=3)
        self.paned.add(detail_card, weight=2)
        try:
            self.paned.pane(list_card, minsize=420)
            self.paned.pane(detail_card, minsize=340)
        except Exception:
            pass
        self._build_list(list_card)
        self._build_details(detail_card)
        self.root.after(80, self._place_sash)

    def _place_sash(self):
        try:
            width = self.paned.winfo_width()
            if width > 200:
                self.paned.sashpos(0, max(480, width - 400))
        except Exception:
            pass

    def _build_list(self, parent):
        cols = ("eng", "chi", "addr_chi", "gazette_no")
        self.result_tree = ttk.Treeview(
            parent,
            columns=cols,
            show="headings",
            selectmode="browse",
        )
        headings = {
            "eng": "英文名稱",
            "chi": "中文名稱",
            "addr_chi": "中文地址",
            "gazette_no": "G.N.",
        }
        widths = {"eng": 200, "chi": 150, "addr_chi": 240, "gazette_no": 72}
        stretch = {"eng": True, "chi": True, "addr_chi": True, "gazette_no": False}
        for c in cols:
            self.result_tree.heading(c, text=headings[c], anchor="w")
            self.result_tree.column(
                c, width=widths[c], minwidth=56, anchor="w", stretch=stretch[c],
            )
        self.result_tree.tag_configure("odd", background="#f7fafc")
        self.result_tree.tag_configure("even", background=PAPER)
        self.result_tree.tag_configure("missing", background="#fffaf3")

        yscroll = Scrollbar(parent, orient="vertical", command=self.result_tree.yview)
        xscroll = Scrollbar(parent, orient="horizontal", command=self.result_tree.xview)
        self.result_tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.result_tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        self.result_tree.bind("<<TreeviewSelect>>", self.on_select_company)
        self.result_tree.bind("<Double-1>", self.on_result_double_click)
        self.result_tree.bind("<Button-3>", self.on_result_right_click)
        self.result_tree.bind("<MouseWheel>", self._on_mousewheel)
        self.result_tree.bind("<Button-4>", lambda e: self.result_tree.yview_scroll(-3, "units"))
        self.result_tree.bind("<Button-5>", lambda e: self.result_tree.yview_scroll(3, "units"))
        self.result_tree.bind("<Control-c>", lambda e: self.copy_selected_row())
        self.result_tree.bind("<Control-C>", lambda e: self.copy_selected_row())

        self.ctx_menu = Menu(self.root, tearoff=0)
        try:
            self.ctx_menu.configure(font=F(10), bg=PAPER, fg=INK, activebackground=NAVY, activeforeground=PAPER)
        except Exception:
            pass
        self.ctx_menu.add_command(label="複製儲存格", command=self.copy_context_cell)
        self.ctx_menu.add_command(label="複製整列（Tab）", command=self.copy_selected_row)

    def _build_details(self, parent):
        parent.configure(bg=PAPER)
        inner = Frame(parent, bg=PAPER)
        inner.pack(fill=BOTH, expand=True, padx=14, pady=12)

        head = Frame(inner, bg=PAPER)
        head.pack(fill=X)
        Label(
            head, text="公司詳情", font=F(12, "bold"), fg=NAVY, bg=PAPER,
        ).pack(side=LEFT, anchor=N)
        self.btn_edit = self._quiet_button(head, "編輯", self.on_edit_company)
        self.btn_edit.pack(side=RIGHT, anchor=N)
        self.btn_edit.configure(state=DISABLED)

        self._rule(inner).pack(fill=X, pady=8)

        self._add_copy_field(inner, "英文名稱", "複製英文名", "eng", "英文名")
        self._add_copy_field(inner, "中文名稱", "複製中文名", "chi", "中文名")
        self._add_copy_field(inner, "英文地址", "複製英文地址", "addr_eng", "英文地址")
        self._add_copy_field(inner, "中文地址", "複製中文地址", "addr_chi", "中文地址")

        self._rule(inner).pack(fill=X, pady=8)
        Label(
            inner, text="憲報", font=F(8), fg=MUTED, bg=PAPER, anchor="w",
        ).pack(fill=X)
        for key, caption in (
            ("gazette_no", "編號"),
            ("gazette_date", "日期"),
            ("gazette_file", "檔案"),
        ):
            row = Frame(inner, bg=PAPER)
            row.pack(fill=X, pady=2)
            Label(
                row, text=caption, font=F(9), fg=MUTED, bg=PAPER, width=4, anchor="w",
            ).pack(side=LEFT, anchor=N)
            value = Label(
                row, text="—", font=F(10), fg=INK, bg=PAPER, anchor="w", justify="left", wraplength=260,
            )
            value.pack(side=LEFT, fill=X, expand=True, anchor=N)
            self._gazette_values[key] = value
            self._bind_wrap(row, value, reserve=48)

        Label(
            inner,
            text="雙擊儲存格可複製　·　右鍵可複製整列",
            font=F(8),
            fg=MUTED,
            bg=PAPER,
            anchor="w",
        ).pack(fill=X, pady=10)
        self._show_details(None)

    def _add_copy_field(self, parent, caption: str, button_text: str, key: str, copy_label: str):
        block = Frame(parent, bg=PAPER)
        block.pack(fill=X, pady=4)
        Label(
            block, text=caption, font=F(8), fg=MUTED, bg=PAPER, anchor="w",
        ).pack(fill=X)
        row = Frame(block, bg=PAPER)
        row.pack(fill=X, pady=1)
        value = Label(
            row,
            text="—",
            font=F(11),
            fg=INK,
            bg=PAPER,
            anchor="w",
            justify="left",
            wraplength=240,
        )
        btn = self._quiet_button(
            row, button_text, lambda k=key, lab=copy_label: self.copy_detail_field(k, lab),
        )
        value.grid(row=0, column=0, sticky="nw")
        btn.grid(row=0, column=1, sticky="nw", padx=8)
        btn.configure(state=DISABLED)
        self._detail_values[key] = value
        self._detail_buttons[key] = btn
        self._bind_wrap(row, value, reserve=btn)

    def _rule(self, parent) -> Frame:
        rule = Frame(parent, bg=LINE, height=1)
        rule.pack_propagate(False)
        return rule

    def _bind_wrap(self, row: Frame, label: Label, reserve):
        def on_cfg(event, label=label, reserve=reserve):
            if isinstance(reserve, int):
                used = reserve
            else:
                try:
                    used = reserve.winfo_reqwidth() + 16
                except Exception:
                    used = 140
            new = max(120, int(event.width) - used)
            try:
                current = int(label.cget("wraplength"))
            except Exception:
                current = -1
            if current != new:
                label.configure(wraplength=new)
        row.bind("<Configure>", on_cfg)

    def _build_footer(self):
        self.footer = Frame(self.root, bg=CHIP)
        self.footer.pack(side="bottom", fill=X)
        self.progress = ttk.Progressbar(
            self.footer, mode="indeterminate", style="Busy.Horizontal.TProgressbar",
        )
        self._footer_bar = Frame(self.footer, bg=CHIP)
        self._footer_bar.pack(fill=X)
        self.log_toggle = Button(
            self._footer_bar,
            text="▶  執行日誌",
            command=self.toggle_log,
            font=F(9),
            relief="flat",
            bg=CHIP,
            fg=NAVY,
            activebackground=LINE,
            activeforeground=NAVY,
            cursor="hand2",
            padx=10,
            pady=5,
        )
        self.log_toggle.pack(side=LEFT)
        self.status_var = StringVar(value="就緒")
        Label(
            self._footer_bar,
            textvariable=self.status_var,
            font=F(8),
            anchor="e",
            bg=CHIP,
            fg="#4a5568",
            padx=12,
            pady=5,
        ).pack(side=RIGHT)

        self.log_frame = Frame(self.footer, bg=CHIP)
        self.log_text = Text(
            self.log_frame,
            height=7,
            wrap=WORD,
            font=F_mono(9),
            bg=PAPER,
            fg=INK,
            insertbackground=INK,
            relief="flat",
            highlightthickness=1,
            highlightbackground=LINE,
            padx=8,
            pady=6,
        )
        scroll = Scrollbar(self.log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True, padx=8, pady=4)
        scroll.pack(side=RIGHT, fill=Y, pady=4)
        self.log_text.configure(state=DISABLED)

    def _install_shortcuts(self):
        self.root.bind("<F5>", lambda e: self.refresh_stats())
        self.root.bind("<Control-f>", self._focus_search)
        self.root.bind("<Control-F>", self._focus_search)

    # ── 搜尋框 ───────────────────────────────────

    def _set_search_placeholder(self):
        self._updating_search = True
        self._search_placeholder_active = True
        self.search_var.set(PLACEHOLDER)
        self.search_entry.configure(fg="#a0aec0")
        self._updating_search = False

    def _clear_search_placeholder(self):
        if not self._search_placeholder_active:
            return
        self._updating_search = True
        self._search_placeholder_active = False
        self.search_var.set("")
        self.search_entry.configure(fg=INK)
        self._updating_search = False

    def _search_query(self) -> str:
        if self._search_placeholder_active:
            return ""
        return self.search_var.get().strip()

    def _on_search_focus_in(self, _event=None):
        self._search_box.configure(highlightbackground=NAVY)
        self._clear_search_placeholder()

    def _on_search_focus_out(self, _event=None):
        self._search_box.configure(highlightbackground=LINE)
        if not self.search_var.get().strip():
            self._set_search_placeholder()

    def _on_search_write(self, *_args):
        if not self._ui_ready or self._updating_search or self._search_placeholder_active:
            return
        if self._search_job is not None:
            try:
                self.root.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.root.after(60, self._apply_search)

    def _apply_search(self):
        self._search_job = None
        self.apply_view()

    def _on_search_enter(self, _event=None):
        if self._search_job is not None:
            try:
                self.root.after_cancel(self._search_job)
            except Exception:
                pass
            self._search_job = None
        self.apply_view()
        children = self.result_tree.get_children()
        if children:
            self.result_tree.selection_set(children[0])
            self.result_tree.focus(children[0])
            self.result_tree.see(children[0])
            self.result_tree.focus_set()
        return "break"

    def _on_search_escape(self, _event=None):
        self._updating_search = True
        self._search_placeholder_active = False
        self.search_var.set("")
        self.search_entry.configure(fg=INK)
        self._updating_search = False
        self.apply_view()
        return "break"

    def _focus_search(self, _event=None):
        self.search_entry.focus_set()
        self.search_entry.icursor(END)
        return "break"

    def on_search(self):
        """Enter／程式呼叫仍會套用目前搜尋字。"""
        self.apply_view()

    # ── 日誌與狀態 ───────────────────────────────

    def log(self, msg: str):
        self.log_text.configure(state=NORMAL)
        self.log_text.insert(END, msg + "\n")
        self.log_text.see(END)
        self.log_text.configure(state=DISABLED)
        if self.busy and not self._log_open:
            self._expand_log()

    def set_status(self, text: str):
        self.status_var.set(text)

    def toggle_log(self):
        if self._log_open:
            self._collapse_log()
        else:
            self._expand_log()

    def _expand_log(self):
        if self._log_open:
            return
        self._log_open = True
        self.log_toggle.configure(text="▼  執行日誌")
        self.log_frame.pack(fill=X)

    def _collapse_log(self):
        self._log_open = False
        self.log_toggle.configure(text="▶  執行日誌")
        self.log_frame.pack_forget()

    def _set_job_controls(self, state: str):
        for menu, index in self._job_menus:
            try:
                menu.entryconfig(index, state=state)
            except Exception:
                pass
        try:
            if state == DISABLED or self._detail_company is None:
                self.btn_edit.configure(state=DISABLED)
            else:
                self.btn_edit.configure(state=NORMAL)
        except Exception:
            pass

    def set_busy(self, busy: bool):
        self.busy = busy
        self._set_job_controls(DISABLED if busy else NORMAL)
        if busy:
            self._expand_log()
            self.set_status("執行中…")
            if not self.progress.winfo_ismapped():
                self.progress.pack(fill=X, before=self._footer_bar)
            self.progress.start(12)
        else:
            self.progress.stop()
            if self.progress.winfo_manager():
                self.progress.pack_forget()
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def _ensure_idle(self) -> bool:
        if self.busy:
            messagebox.showinfo("請稍候", "目前有工作正在執行，請等待完成。")
            return False
        return True

    def refresh_stats(self):
        if self.busy:
            self._ensure_idle()
            return
        try:
            self.companies = ml.load_companies()
            # 把舊格式（只有 addr）遷移成 addr_eng / addr_chi 並寫回磁碟
            if self.companies:
                ml.save_companies(self.companies)
            total = len(self.companies)
            with_addr = sum(1 for c in self.companies if ml.has_any_address(c))
            self.var_total.set(f"{total:,}")
            self.var_with_addr.set(f"{with_addr:,}")
            self.var_no_addr.set(f"{total - with_addr:,}")
            if self._ui_ready and hasattr(self, "result_tree"):
                self.apply_view()
            elif total:
                self.set_status(f"已載入 companies.json（{total:,} 筆，其中 {with_addr:,} 筆有地址）")
            else:
                self.set_status("就緒")
        except Exception as e:
            self.var_total.set("—")
            self.var_with_addr.set("—")
            self.var_no_addr.set("—")
            self.set_status(f"載入失敗：{e}")
            try:
                self.log(f"❌ 載入 companies.json 失敗：{e}")
            except Exception:
                pass

    def run_in_thread(self, target, on_done=None):
        if self.busy:
            messagebox.showinfo("請稍候", "目前有工作正在執行，請等待完成。")
            return

        def wrapper():
            self.root.after(0, lambda: self.set_busy(True))
            try:
                result = target()
                self.root.after(0, lambda: self._on_thread_done(None, result, on_done))
            except Exception as e:
                err = e
                self.root.after(0, lambda: self._on_thread_done(err, None, on_done))

        threading.Thread(target=wrapper, daemon=True).start()

    def _on_thread_done(self, error, result, on_done):
        self.set_busy(False)
        self.refresh_stats()
        if error:
            self.log(f"❌ 錯誤：{error}")
            self.set_status("發生錯誤")
            messagebox.showerror("錯誤", str(error))
        elif on_done:
            on_done(result)

    # ── 更新 ─────────────────────────────────────

    def on_update_names(self):
        self.log("─" * 40)
        self.log("開始從公司註冊處下載最新官方名單…")

        def work():
            official = ml.download_official_csv()
            data = ml.load_companies()
            data, added, updated = ml.merge_names(data, official)
            ml.save_companies(data)
            ml.export_csv(data)
            return added, updated, len(data)

        def done(result):
            added, updated, total = result
            self.log(f"✅ 名稱更新完成：新增 {added} 間，更新中文名 {updated} 間")
            self.log(f"   目前總數：{total:,}")
            self.set_status("名稱名單已更新")
            messagebox.showinfo("完成", f"新增：{added}\n更新中文名：{updated}\n總數：{total:,}")

        self.run_in_thread(work, done)

    def on_gazette(self):
        if not self._ensure_idle():
            return
        paths = filedialog.askopenfilenames(
            title="選擇政府憲報 PDF（可多選）",
            filetypes=[("PDF 檔案", "*.pdf"), ("所有檔案", "*.*")],
        )
        if not paths:
            return
        self.log("─" * 40)
        self.log(f"準備解析 {len(paths)} 份憲報 PDF…")
        for p in paths:
            self.log(f"  · {os.path.basename(p)}")

        def work():
            name_to_addr = ml.extract_addresses_from_gazette(list(paths))
            data = ml.load_companies()
            data, filled = ml.merge_addresses(data, name_to_addr)
            ml.save_companies(data)
            ml.export_csv(data)
            return filled, len(name_to_addr), len(data)

        def done(result):
            filled, extracted, total = result
            self.log(f"✅ 地址合併完成：填充／新增了 {filled} 筆")
            self.log(f"   憲報共提取 {extracted} 個不重複地址")
            self.set_status("憲報地址已合併")
            messagebox.showinfo("完成", f"提取：{extracted}\n填充／新增：{filled}\n總數：{total:,}")

        self.run_in_thread(work, done)

    def on_import_licensee_pdf(self):
        if not self._ensure_idle():
            return
        path = filedialog.askopenfilename(
            title="選擇持牌人名單 PDF（ml_licensees…）",
            filetypes=[("PDF 檔案", "*.pdf"), ("所有檔案", "*.*")],
        )
        if not path:
            return
        self.log("─" * 40)
        self.log(f"解析本地持牌人 PDF：{os.path.basename(path)}")

        def work():
            extracted = ml.extract_names_from_licensee_pdf(path)
            data = ml.load_companies()
            data, added, updated = ml.merge_names(
                data,
                [{"eng": c["eng"], "chi": c["chi"]} for c in extracted],
            )
            ml.save_companies(data)
            ml.export_csv(data)
            return added, updated, len(data)

        def done(result):
            added, updated, total = result
            self.log(f"✅ 本地 PDF 匯入：新增 {added}，更新 {updated}，總數 {total:,}")
            self.set_status("本地持牌人 PDF 已匯入")
            messagebox.showinfo("完成", f"新增 {added}\n更新 {updated}\n總數 {total:,}")

        self.run_in_thread(work, done)

    def on_export(self):
        if not self._ensure_idle():
            return
        data = ml.load_companies()
        if not data:
            messagebox.showwarning("無資料", "目前沒有公司資料可匯出。")
            return
        path = filedialog.asksaveasfilename(
            title="匯出 CSV",
            defaultextension=".csv",
            initialfile="ml_licensees_with_addr.csv",
            filetypes=[("CSV 檔案", "*.csv")],
        )
        if not path:
            return
        try:
            ml.export_csv(data, path)
            self.log(f"✅ 已匯出：{path}")
            self.set_status(f"已匯出 {len(data):,} 筆")
            messagebox.showinfo("匯出完成", f"已匯出 {len(data):,} 筆到：\n{path}")
        except Exception as e:
            messagebox.showerror("匯出失敗", str(e))

    # ── 匯入 ─────────────────────────────────────

    def on_import_sheet(self):
        url = ml.load_sheet_url()
        if not url:
            messagebox.showinfo("尚未設定", "請先按「設定 Sheet URL」儲存 Google Sheet 網址。")
            return
        self.log("─" * 40)
        self.log("從 Google Sheet 匯入…")

        def work():
            data = ml.load_companies()
            data, imported, skipped = ml.import_from_google_sheet(data, url)
            ml.save_companies(data)
            ml.export_csv(data)
            return imported, skipped, len(data)

        def done(result):
            imported, skipped, total = result
            self.log(f"✅ Sheet 匯入：新增 {imported}，略過／更新 {skipped}，總數 {total:,}")
            self.set_status("Google Sheet 已匯入")
            messagebox.showinfo("完成", f"新增 {imported}\n略過／更新 {skipped}\n總數 {total:,}")

        self.run_in_thread(work, done)

    def on_set_sheet_url(self):
        if not self._ensure_idle():
            return
        current = ml.load_sheet_url()
        url = simpledialog.askstring(
            "設定 Google Sheet URL",
            "請貼上 Google Sheet 完整網址\n（需設為「知道連結的任何人可檢視」）：",
            initialvalue=current,
            parent=self.root,
        )
        if url is None:
            return
        url = url.strip()
        if not url:
            messagebox.showwarning("空白", "URL 不可為空")
            return
        if "docs.google.com" not in url:
            messagebox.showwarning("格式", "請輸入有效的 Google Sheet 網址")
            return
        ml.save_sheet_url(url)
        self.log(f"✅ 已儲存 Sheet URL：{url}")
        self.set_status("Sheet URL 已儲存")
        messagebox.showinfo("完成", "Google Sheet URL 已儲存到 sheet_url.json")

    def on_import_csv(self):
        if not self._ensure_idle():
            return
        path = filedialog.askopenfilename(
            title="選擇 CSV 檔案",
            filetypes=[("CSV 檔案", "*.csv"), ("所有檔案", "*.*")],
        )
        if not path:
            return
        self.log("─" * 40)
        self.log(f"從 CSV 匯入：{os.path.basename(path)}")

        def work():
            data = ml.load_companies()
            data, imported, skipped = ml.import_from_csv_file(data, path)
            ml.save_companies(data)
            ml.export_csv(data)
            return imported, skipped, len(data)

        def done(result):
            imported, skipped, total = result
            self.log(f"✅ CSV 匯入：新增 {imported}，略過／更新 {skipped}，總數 {total:,}")
            self.set_status("CSV 已匯入")
            messagebox.showinfo("完成", f"新增 {imported}\n略過／更新 {skipped}\n總數 {total:,}")

        self.run_in_thread(work, done)

    # ── 列表、篩選、詳情 ─────────────────────────

    def _display_addrs(self, c: dict) -> tuple[str, str]:
        """保證英文／中文地址欄都盡量有值（相容舊的單一 addr）。"""
        c = ml._normalize_company(c)
        return (c.get("addr_eng") or "", c.get("addr_chi") or "")

    def _gazette_bits(self, c: dict) -> tuple[str, str, str]:
        gfile = c.get("gazette_file") or c.get("addr_chi_file") or c.get("addr_eng_file") or ""
        gdate = c.get("gazette_date") or c.get("addr_chi_date") or c.get("addr_eng_date") or ""
        gno = c.get("gazette_no") or ""
        return gfile, gdate, gno

    def _company_haystack(self, c: dict) -> str:
        addr_eng, addr_chi = self._display_addrs(c)
        gfile, gdate, gno = self._gazette_bits(c)
        return " ".join([
            c.get("eng") or "",
            c.get("chi") or "",
            addr_eng,
            addr_chi,
            c.get("addr") or "",
            gfile,
            gdate,
            gno,
            c.get("addr_eng_file") or "",
            c.get("addr_chi_file") or "",
        ]).lower()

    def _filtered_rows(self) -> tuple[list[dict], str]:
        rows = list(self.companies)
        if self.filter_mode == "missing":
            rows = [c for c in rows if not ml.has_any_address(c)]
            label = "缺地址"
        else:
            label = "全部資料"
        query = self._search_query().lower()
        if query:
            rows = [c for c in rows if query in self._company_haystack(c)]
            label = "搜尋結果" if self.filter_mode == "all" else "缺地址 · 搜尋"
        rows = sorted(rows, key=lambda x: (x.get("eng") or x.get("chi") or "").lower())
        return rows, label

    def apply_view(self, prefer: tuple[str, str] | None = None):
        if prefer is None and self._detail_company:
            prefer = (
                self._detail_company.get("eng") or "",
                self._detail_company.get("chi") or "",
            )
        rows, label = self._filtered_rows()
        self._fill_tree(rows, label)
        self._style_filter_chips()
        chosen = None
        if prefer and (prefer[0] or prefer[1]):
            chosen = self._find_visible_iid(prefer[0], prefer[1])
        children = self.result_tree.get_children()
        if chosen is None and children:
            chosen = children[0]
        if chosen is not None:
            self.result_tree.selection_set(chosen)
            self.result_tree.focus(chosen)
            self.result_tree.see(chosen)
            self._show_details_for_iid(chosen)
        else:
            self._show_details(None)

    def _fill_tree(self, rows: list[dict], status: str):
        self.result_tree.unbind("<<TreeviewSelect>>")
        try:
            self._fill_tree_items(rows, status)
        finally:
            self.result_tree.bind("<<TreeviewSelect>>", self.on_select_company)

    def _fill_tree_items(self, rows: list[dict], status: str):
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self._result_rows = []
        shown_with_addr = 0
        for i, raw in enumerate(rows[:LIST_LIMIT]):
            c = ml._normalize_company(raw)
            addr_eng, addr_chi = self._display_addrs(c)
            if addr_eng or addr_chi:
                shown_with_addr += 1
            _gfile, _gdate, gno = self._gazette_bits(c)
            tag = "missing" if not (addr_eng or addr_chi) else ("odd" if i % 2 else "even")
            self.result_tree.insert(
                "",
                END,
                values=(
                    c.get("eng") or "",
                    c.get("chi") or "",
                    addr_chi,
                    gno,
                ),
                tags=(tag,),
            )
            self._result_rows.append(c)
        extra = "（只顯示前 500）" if len(rows) > LIST_LIMIT else ""
        self.var_shown.set(f"{len(rows):,} 筆" if rows else "0 筆")
        if not self.companies:
            self.set_status("尚無資料。可從「維護」更新官方名稱。")
        elif not rows and self._search_query():
            self.set_status("搜尋無結果")
        else:
            self.set_status(f"{status}：{len(rows):,} 筆{extra}｜本頁有地址 {shown_with_addr:,} 筆")

    def _find_visible_iid(self, eng: str, chi: str):
        eng_l = (eng or "").lower()
        chi_l = (chi or "").lower()
        for iid, c in zip(self.result_tree.get_children(), self._result_rows):
            if eng_l and (c.get("eng") or "").lower() == eng_l:
                return iid
            if chi_l and (c.get("chi") or "").lower() == chi_l:
                return iid
        return None

    def _row_for_iid(self, iid) -> dict | None:
        children = list(self.result_tree.get_children())
        try:
            idx = children.index(iid)
        except ValueError:
            return None
        if 0 <= idx < len(self._result_rows):
            return self._result_rows[idx]
        return None

    def on_show_all(self):
        if not self.companies:
            self.companies = ml.load_companies()
        self.filter_mode = "all"
        self.apply_view(prefer=None)
        self.log(f"顯示全部 {len(self.companies):,} 筆")

    def on_show_missing(self):
        if not self.companies:
            self.companies = ml.load_companies()
        self.filter_mode = "missing"
        missing = sum(1 for c in self.companies if not ml.has_any_address(c))
        self.apply_view(prefer=None)
        self.log(f"顯示缺地址 {missing:,} 筆")

    def on_select_company(self, _event=None):
        sel = self.result_tree.selection()
        if not sel:
            self._show_details(None)
            return
        self._show_details_for_iid(sel[0])

    def _show_details_for_iid(self, iid):
        self._show_details(self._row_for_iid(iid))

    def _field_text(self, company: dict | None, key: str) -> str:
        if not company:
            return ""
        if key in ("addr_eng", "addr_chi"):
            addr_eng, addr_chi = self._display_addrs(company)
            return addr_eng if key == "addr_eng" else addr_chi
        if key in ("gazette_file", "gazette_date", "gazette_no"):
            gfile, gdate, gno = self._gazette_bits(company)
            return {"gazette_file": gfile, "gazette_date": gdate, "gazette_no": gno}[key]
        return company.get(key) or ""

    def _show_details(self, company: dict | None):
        self._detail_company = company
        for key, label in self._detail_values.items():
            text = self._field_text(company, key)
            if text:
                label.configure(text=text, fg=INK)
                self._detail_buttons[key].configure(state=NORMAL, fg=NAVY)
            else:
                label.configure(text="—", fg="#a0aec0")
                self._detail_buttons[key].configure(state=DISABLED)
        for key, label in self._gazette_values.items():
            text = self._field_text(company, key)
            label.configure(text=text or "—", fg=INK if text else "#a0aec0")
        if self.busy or company is None:
            self.btn_edit.configure(state=DISABLED)
        else:
            self.btn_edit.configure(state=NORMAL)

    def _selected_company(self):
        sel = self.result_tree.selection()
        if not sel:
            return None, -1
        row = self._row_for_iid(sel[0])
        if not row:
            vals = self.result_tree.item(sel[0], "values")
            eng = vals[0] if vals else ""
            chi = vals[1] if vals and len(vals) > 1 else ""
        else:
            eng = row.get("eng") or ""
            chi = row.get("chi") or ""
        data = ml.load_companies()
        idx = ml.find_company_index(data, eng, chi)
        if idx < 0:
            return None, -1
        return data, idx

    def on_add_company(self):
        if not self._ensure_idle():
            return
        self._company_dialog(title="新增公司")

    def on_edit_company(self):
        if not self._ensure_idle():
            return
        data, idx = self._selected_company()
        if data is None or idx < 0:
            messagebox.showinfo("請先選取", "請先在左側列表點選一間公司，再按「編輯」。")
            return
        self._company_dialog(title="編輯公司", data=data, index=idx)

    def on_delete_company(self):
        if not self._ensure_idle():
            return
        data, idx = self._selected_company()
        if data is None or idx < 0:
            messagebox.showinfo("請先選取", "請先在左側列表點選一間公司，再按「刪除選取」。")
            return
        item = data[idx]
        name = item.get("eng") or item.get("chi") or "(無名稱)"
        if not messagebox.askyesno("確認刪除", f"確定刪除？\n\n{name}"):
            return
        data, err = ml.delete_company(data, idx)
        if err:
            messagebox.showerror("錯誤", err)
            return
        ml.save_companies(data)
        self.log(f"已刪除：{name}")
        self._detail_company = None
        self.refresh_stats()

    def _company_dialog(self, title: str, data=None, index: int = -1):
        win = Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.grab_set()
        win.geometry("560x340")
        win.configure(bg=PAPER)

        fields = {}
        labels = [
            ("eng", "英文名稱"),
            ("chi", "中文名稱"),
            ("addr_eng", "英文地址"),
            ("addr_chi", "中文地址"),
            ("gazette_file", "憲報檔名"),
            ("gazette_date", "憲報日期 (YYYY-MM-DD)"),
            ("gazette_no", "G.N. 編號"),
        ]
        existing = data[index] if (data is not None and index >= 0) else {}
        for i, (key, label) in enumerate(labels):
            Label(win, text=label, font=F(9), anchor="w", bg=PAPER).grid(
                row=i, column=0, sticky="w", padx=10, pady=4,
            )
            var = StringVar(value=existing.get(key) or "")
            Entry(win, textvariable=var, font=F(10), width=50).grid(
                row=i, column=1, sticky="ew", padx=10, pady=4,
            )
            fields[key] = var
        win.grid_columnconfigure(1, weight=1)

        def save():
            payload = {k: v.get().strip() for k, v in fields.items()}
            if not payload["eng"] and not payload["chi"]:
                messagebox.showwarning("缺少名稱", "請至少填寫英文或中文名稱", parent=win)
                return
            current = ml.load_companies()
            if index >= 0 and data is not None:
                old = data[index]
                idx = ml.find_company_index(current, old.get("eng"), old.get("chi"))
                if idx < 0:
                    messagebox.showerror("錯誤", "找不到原資料列", parent=win)
                    return
                current, err = ml.update_company(current, idx, payload)
            else:
                current, err = ml.add_company(
                    current,
                    eng=payload["eng"],
                    chi=payload["chi"],
                    addr_eng=payload["addr_eng"],
                    addr_chi=payload["addr_chi"],
                )
                if not err:
                    idx = ml.find_company_index(current, payload["eng"], payload["chi"])
                    if idx >= 0:
                        current, err = ml.update_company(current, idx, payload)
            if err:
                messagebox.showerror("錯誤", err, parent=win)
                return
            ml.save_companies(current)
            self.log(f"✅ {title}：{payload['eng'] or payload['chi']}")
            self._detail_company = {
                "eng": payload["eng"],
                "chi": payload["chi"],
            }
            win.destroy()
            self.refresh_stats()
            messagebox.showinfo("完成", f"{title}成功")

        bf = Frame(win, bg=PAPER)
        bf.grid(row=len(labels), column=0, columnspan=2, pady=12)
        Button(
            bf, text="儲存", command=save, font=F(10),
            bg=NAVY, fg=PAPER, activebackground=NAVY_SOFT, activeforeground=PAPER,
            relief="flat", padx=16, pady=4, cursor="hand2",
        ).pack(side=LEFT, padx=8)
        Button(
            bf, text="取消", command=win.destroy, font=F(10),
            relief="groove", padx=16, pady=4, cursor="hand2",
        ).pack(side=LEFT)

    # ── 連結與說明 ───────────────────────────────

    def open_folder(self):
        folder = str(SCRIPT_DIR)
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            os.system(f'open "{folder}"')
        else:
            os.system(f'xdg-open "{folder}"')

    def open_sheet(self):
        url = ml.load_sheet_url()
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo(
                "尚未設定",
                "找不到 sheet_url.json 或其中沒有 URL。\n請先按「設定 Sheet URL」。",
            )

    def on_help(self):
        messagebox.showinfo(
            "使用說明",
            "在搜尋框輸入中文或英文名稱、地址，列表會即時篩選。\n"
            "點選一列後，右側每個欄位旁可複製該欄文字。\n"
            "「只看缺地址」只顯示尚未有地址的公司。\n"
            "更新名稱、憲報、匯入與匯出在「維護」選單。\n"
            "雙擊儲存格可複製；右鍵可複製整列（以 Tab 分隔）。\n\n"
            "建議：先「更新官方名稱」，再匯入憲報 PDF 補地址，最後匯出 CSV。",
        )

    def on_about(self):
        messagebox.showinfo(
            "關於",
            "香港放債人牌照資料管理工具\n\n"
            "整理公司註冊處公開的持牌人名單，並以政府憲報盡力補上地址。\n"
            "憲報地址是申請或續期當時公布的資料，不一定等於目前登記處所。\n"
            "正式查核請用公司註冊處 e-Search。",
        )

    # ── 複製 ─────────────────────────────────────

    def _on_mousewheel(self, event):
        delta = getattr(event, "delta", 0)
        if delta:
            self.result_tree.yview_scroll(int(-delta / 120) or (-1 if delta > 0 else 1), "units")

    def _cell_under_pointer(self, event):
        row_id = self.result_tree.identify_row(event.y)
        col_id = self.result_tree.identify_column(event.x)
        if not row_id or not col_id:
            return None, None
        return row_id, col_id

    def _value_of_cell(self, row_id, col_id) -> str:
        vals = self.result_tree.item(row_id, "values")
        if not vals:
            return ""
        try:
            idx = int(col_id.replace("#", "")) - 1
        except ValueError:
            return ""
        if 0 <= idx < len(vals):
            return vals[idx] or ""
        return ""

    def on_result_double_click(self, event):
        row_id, col_id = self._cell_under_pointer(event)
        if not row_id:
            return
        self._copy_to_clipboard(self._value_of_cell(row_id, col_id), "儲存格")

    def on_result_right_click(self, event):
        row_id, col_id = self._cell_under_pointer(event)
        if not row_id:
            return
        self.result_tree.selection_set(row_id)
        self.result_tree.focus(row_id)
        self._context_cell = self._value_of_cell(row_id, col_id)
        try:
            self.ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.ctx_menu.grab_release()

    def copy_context_cell(self):
        self._copy_to_clipboard(self._context_cell, "儲存格")

    def copy_selected_cell(self):
        """保留舊的「複製選取儲存格」行為：複製該列第一個非空欄。"""
        sel = self.result_tree.selection()
        if not sel:
            self.set_status("請先點選一列")
            return
        vals = self.result_tree.item(sel[0], "values")
        text = next((v for v in vals if v), "")
        self._copy_to_clipboard(text, "儲存格")

    def copy_selected_row(self):
        sel = self.result_tree.selection()
        if not sel:
            self.set_status("請先在列表中點選一列")
            return
        row = self._row_for_iid(sel[0])
        if row:
            addr_eng, addr_chi = self._display_addrs(row)
            gfile, gdate, gno = self._gazette_bits(row)
            vals = [
                row.get("eng") or "",
                row.get("chi") or "",
                addr_eng,
                addr_chi,
                gfile,
                gdate,
                gno,
            ]
        else:
            vals = list(self.result_tree.item(sel[0], "values"))
        self._copy_to_clipboard("\t".join(vals), "整列")

    def copy_detail_field(self, key: str, label: str):
        text = self._field_text(self._detail_company, key)
        self._copy_to_clipboard(text, label)

    def _copy_to_clipboard(self, text: str, label: str = ""):
        if not text:
            self.set_status("該欄位是空的，沒有可複製的內容")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        preview = text if len(text) <= 60 else text[:57] + "..."
        shown = label or ""
        self.set_status(f"已複製{shown}：{preview}")


# ────────────────────────────────────────────────
# 進入點
# ────────────────────────────────────────────────

def main():
    os.chdir(SCRIPT_DIR)
    root = Tk()
    try:
        family = _pick_font_family()
        root.option_add("*Font", f"{{{family}}} 10")
    except Exception:
        pass

    app = MoneyLendersGUI(root)
    app.log("歡迎使用香港放債人牌照資料管理工具")
    app.log(f"使用字型：{_pick_font_family()}")
    app.log("在上方搜尋公司，於右側複製名稱或地址。")
    app.log("維護功能（更新名稱、憲報、匯入／匯出）在選單列。")
    app.log("建議：先「更新官方名稱」→ 再匯入憲報 PDF 補地址 → 匯出 CSV")
    app.log("─" * 40)
    root.mainloop()


if __name__ == "__main__":
    main()
