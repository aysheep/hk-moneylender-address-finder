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


# ────────────────────────────────────────────────
# 跨平台安全字型
# ────────────────────────────────────────────────

_FONT_FAMILY = None


def _pick_font_family() -> str:
    global _FONT_FAMILY
    if _FONT_FAMILY:
        return _FONT_FAMILY
    candidates = [
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Segoe UI",
        "PingFang HK",
        "PingFang TC",
        "Noto Sans CJK TC",
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
        self.root.geometry("1000x720")
        self.root.minsize(860, 580)

        self.busy = False
        self.companies: list[dict] = []
        self._result_rows: list[dict] = []
        self._action_buttons: list = []

        self._build_ui()
        self.refresh_stats()

    def _btn(self, parent, text, command, bg: str):
        b = Button(
            parent,
            text=text,
            command=command,
            font=F(9),
            bg=bg,
            fg="white",
            activebackground=bg,
            relief="flat",
            padx=10,
            pady=5,
            cursor="hand2",
        )
        b.pack(side=LEFT, padx=3)
        return b

    def _link(self, parent, text, command):
        Button(
            parent,
            text=text,
            command=command,
            font=F(8),
            relief="flat",
            fg="#2b6cb0",
            cursor="hand2",
        ).pack(side=LEFT, padx=6)

    def _build_ui(self):
        # 標題列（padding 放在 Label，避免 Frame pady tuple 在 Windows Tcl 出錯）
        header = Frame(self.root, bg="#1a365d")
        header.pack(fill=X)
        Label(
            header,
            text="香港放債人牌照資料管理工具",
            font=F(16, "bold"),
            fg="white",
            bg="#1a365d",
            padx=12,
            pady=10,
        ).pack(side=LEFT)
        Label(
            header,
            text="Companies Registry · Gazette",
            font=F(9),
            fg="#a0aec0",
            bg="#1a365d",
            padx=12,
            pady=10,
        ).pack(side=RIGHT)

        # 統計列
        stats_frame = Frame(self.root, bg="#edf2f7")
        stats_frame.pack(fill=X)
        self.var_total = StringVar(value="—")
        self.var_with_addr = StringVar(value="—")
        self.var_no_addr = StringVar(value="—")

        for text, var, color in [
            ("公司總數", self.var_total, "#2b6cb0"),
            ("已有地址", self.var_with_addr, "#276749"),
            ("尚未有地址", self.var_no_addr, "#c53030"),
        ]:
            box = Frame(stats_frame, bg="#edf2f7")
            box.pack(side=LEFT, expand=True, padx=8, pady=8)
            Label(box, text=text, font=F(9), bg="#edf2f7", fg="#718096").pack()
            Label(box, textvariable=var, font=F(18, "bold"), bg="#edf2f7", fg=color).pack()

        # 第一列：更新
        row1 = Frame(self.root)
        row1.pack(fill=X, padx=12, pady=4)
        Label(row1, text="更新", font=F(8), fg="#718096").pack(side=LEFT, padx=4)
        self.btn_names = self._btn(row1, "更新官方名稱", self.on_update_names, "#2b6cb0")
        self.btn_gazette = self._btn(row1, "憲報 PDF 提取地址", self.on_gazette, "#276749")
        self.btn_local_pdf = self._btn(row1, "本地持牌人 PDF", self.on_import_licensee_pdf, "#2c5282")
        self.btn_export = self._btn(row1, "匯出 CSV", self.on_export, "#744210")

        # 第二列：匯入
        row2 = Frame(self.root)
        row2.pack(fill=X, padx=12, pady=2)
        Label(row2, text="匯入", font=F(8), fg="#718096").pack(side=LEFT, padx=4)
        self.btn_sheet_import = self._btn(row2, "從 Google Sheet 匯入", self.on_import_sheet, "#553c9a")
        self.btn_set_sheet = self._btn(row2, "設定 Sheet URL", self.on_set_sheet_url, "#6b46c1")
        self.btn_csv_import = self._btn(row2, "從 CSV 匯入", self.on_import_csv, "#553c9a")

        # 第三列：管理
        row3 = Frame(self.root)
        row3.pack(fill=X, padx=12, pady=2)
        Label(row3, text="管理", font=F(8), fg="#718096").pack(side=LEFT, padx=4)
        self.btn_show_all = self._btn(row3, "顯示全部", self.on_show_all, "#4a5568")
        self.btn_show_missing = self._btn(row3, "只看缺地址", self.on_show_missing, "#c53030")
        self.btn_add = self._btn(row3, "新增", self.on_add_company, "#2b6cb0")
        self.btn_edit = self._btn(row3, "編輯選取", self.on_edit_company, "#2b6cb0")
        self.btn_delete = self._btn(row3, "刪除選取", self.on_delete_company, "#c53030")
        self.btn_refresh = self._btn(row3, "重新整理", self.refresh_stats, "#4a5568")

        self._action_buttons = [
            self.btn_names, self.btn_gazette, self.btn_local_pdf, self.btn_export,
            self.btn_sheet_import, self.btn_set_sheet, self.btn_csv_import,
            self.btn_show_all, self.btn_show_missing, self.btn_add, self.btn_edit,
            self.btn_delete, self.btn_refresh,
        ]

        # 連結
        link_frame = Frame(self.root)
        link_frame.pack(fill=X, padx=12, pady=2)
        self._link(link_frame, "開啟資料夾", self.open_folder)
        self._link(link_frame, "開啟 Google Sheet", self.open_sheet)
        self._link(link_frame, "e-Search 官方查冊", lambda: webbrowser.open("https://www.e-services.cr.gov.hk"))
        self._link(link_frame, "政府憲報", lambda: webbrowser.open("https://www.gld.gov.hk/egazette/"))
        self._link(
            link_frame,
            "data.gov.hk 放債人",
            lambda: webbrowser.open("https://data.gov.hk/tc-data/dataset/hk-cr-crdata-list-of-licensed-money-lenders"),
        )

        # 進度條
        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill=X, padx=12, pady=4)

        # 日誌
        Label(self.root, text="執行日誌", font=F(9), anchor="w").pack(fill=X, padx=12)
        log_frame = Frame(self.root)
        log_frame.pack(fill=BOTH, expand=True, padx=12, pady=4)
        self.log_text = Text(
            log_frame,
            height=8,
            wrap=WORD,
            font=F_mono(9),
            bg="#1a202c",
            fg="#e2e8f0",
            insertbackground="white",
            relief="flat",
            padx=8,
            pady=6,
        )
        scroll = Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)
        self.log_text.configure(state=DISABLED)

        # 搜尋
        search_frame = Frame(self.root)
        search_frame.pack(fill=X, padx=12, pady=4)
        Label(search_frame, text="搜尋：", font=F(9)).pack(side=LEFT)
        self.search_var = StringVar()
        self.search_entry = Entry(search_frame, textvariable=self.search_var, font=F(10), width=36)
        self.search_entry.pack(side=LEFT, padx=4)
        self.search_entry.bind("<Return>", lambda e: self.on_search())
        Button(search_frame, text="搜尋", command=self.on_search, font=F(9), relief="groove", padx=10, cursor="hand2").pack(side=LEFT, padx=4)
        Button(search_frame, text="複製選取儲存格", command=self.copy_selected_cell, font=F(9), relief="groove", padx=8, cursor="hand2").pack(side=LEFT, padx=4)
        Button(search_frame, text="複製整列", command=self.copy_selected_row, font=F(9), relief="groove", padx=8, cursor="hand2").pack(side=LEFT, padx=4)

        # 結果表
        result_frame = Frame(self.root)
        result_frame.pack(fill=BOTH, expand=True, padx=12, pady=4)

        cols = ("eng", "chi", "addr_eng", "addr_chi", "gazette_file", "gazette_date", "gazette_no")
        self.result_tree = ttk.Treeview(
            result_frame,
            columns=cols,
            show="headings",
            height=8,
            selectmode="browse",
        )
        headings = {
            "eng": "English Name",
            "chi": "Chinese Name",
            "addr_eng": "English Address",
            "addr_chi": "Chinese Address",
            "gazette_file": "Gazette PDF",
            "gazette_date": "Gazette Date",
            "gazette_no": "G.N.",
        }
        widths = {
            "eng": 160, "chi": 120, "addr_eng": 180, "addr_chi": 180,
            "gazette_file": 140, "gazette_date": 90, "gazette_no": 60,
        }
        for c in cols:
            self.result_tree.heading(c, text=headings[c], anchor="w")
            self.result_tree.column(c, width=widths[c], minwidth=50, anchor="w", stretch=True)

        yscroll = Scrollbar(result_frame, orient="vertical", command=self.result_tree.yview)
        xscroll = Scrollbar(result_frame, orient="horizontal", command=self.result_tree.xview)
        self.result_tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.result_tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        result_frame.grid_rowconfigure(0, weight=1)
        result_frame.grid_columnconfigure(0, weight=1)

        self.result_tree.bind("<Double-1>", self.on_result_double_click)
        self.result_tree.bind("<Button-3>", self.on_result_right_click)

        Label(
            self.root,
            text="提示：雙擊／右鍵複製儲存格｜「複製整列」以 Tab 分隔各欄，方便貼到試算表",
            font=F(8),
            fg="#718096",
            anchor="w",
        ).pack(fill=X, padx=12)

        # 狀態列
        self.status_var = StringVar(value="就緒")
        Label(
            self.root,
            textvariable=self.status_var,
            font=F(8),
            anchor="w",
            bg="#e2e8f0",
            fg="#4a5568",
            padx=10,
            pady=3,
        ).pack(fill=X, side="bottom")

    # ── 日誌與狀態 ───────────────────────────────

    def log(self, msg: str):
        self.log_text.configure(state=NORMAL)
        self.log_text.insert(END, msg + "\n")
        self.log_text.see(END)
        self.log_text.configure(state=DISABLED)

    def set_status(self, text: str):
        self.status_var.set(text)

    def set_busy(self, busy: bool):
        self.busy = busy
        state = DISABLED if busy else NORMAL
        for btn in self._action_buttons:
            try:
                btn.configure(state=state)
            except Exception:
                pass
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def refresh_stats(self):
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
            self.set_status(f"已載入 companies.json（{total:,} 筆，其中 {with_addr:,} 筆有地址）")
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
                self.root.after(0, lambda: self._on_thread_done(e, None, on_done))

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

    # ── 管理 ─────────────────────────────────────

    def _display_addrs(self, c: dict) -> tuple[str, str]:
        """保證英文／中文地址欄都盡量有值（相容舊的單一 addr）。"""
        c = ml._normalize_company(c)
        return (c.get("addr_eng") or "", c.get("addr_chi") or "")

    def _fill_tree(self, rows: list[dict], status: str):
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self._result_rows = []
        shown_with_addr = 0
        for c in rows[:500]:
            c = ml._normalize_company(c)
            addr_eng, addr_chi = self._display_addrs(c)
            if addr_eng or addr_chi:
                shown_with_addr += 1
            gfile = c.get("gazette_file") or c.get("addr_chi_file") or c.get("addr_eng_file") or ""
            gdate = c.get("gazette_date") or c.get("addr_chi_date") or c.get("addr_eng_date") or ""
            self.result_tree.insert(
                "",
                END,
                values=(
                    c.get("eng") or "",
                    c.get("chi") or "",
                    addr_eng,
                    addr_chi,
                    gfile,
                    gdate,
                    c.get("gazette_no") or "",
                ),
            )
            self._result_rows.append(c)
        extra = "（只顯示前 500）" if len(rows) > 500 else ""
        self.set_status(f"{status}：{len(rows)} 筆{extra}｜本頁有地址 {shown_with_addr} 筆")

    def on_show_all(self):
        if not self.companies:
            self.companies = ml.load_companies()
        rows = sorted(self.companies, key=lambda x: (x.get("eng") or x.get("chi") or "").lower())
        self._fill_tree(rows, "全部資料")
        self.log(f"顯示全部 {len(rows):,} 筆")

    def on_show_missing(self):
        if not self.companies:
            self.companies = ml.load_companies()
        missing = [c for c in self.companies if not ml.has_any_address(c)]
        missing = sorted(missing, key=lambda x: (x.get("eng") or x.get("chi") or "").lower())
        self._fill_tree(missing, "缺地址")
        self.log(f"顯示缺地址 {len(missing):,} 筆")

    def _selected_company(self):
        sel = self.result_tree.selection()
        if not sel:
            return None, -1
        vals = self.result_tree.item(sel[0], "values")
        eng = vals[0] if vals else ""
        chi = vals[1] if vals and len(vals) > 1 else ""
        data = ml.load_companies()
        idx = ml.find_company_index(data, eng, chi)
        if idx < 0:
            return None, -1
        return data, idx

    def on_add_company(self):
        self._company_dialog(title="新增公司")

    def on_edit_company(self):
        data, idx = self._selected_company()
        if data is None or idx < 0:
            messagebox.showinfo("請先選取", "請先在下方結果表中點選一列，再按「編輯選取」。")
            return
        self._company_dialog(title="編輯公司", data=data, index=idx)

    def on_delete_company(self):
        data, idx = self._selected_company()
        if data is None or idx < 0:
            messagebox.showinfo("請先選取", "請先在下方結果表中點選一列，再按「刪除選取」。")
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
        self.refresh_stats()
        if self.search_var.get().strip():
            self.on_search()
        else:
            self.on_show_all()

    def _company_dialog(self, title: str, data=None, index: int = -1):
        win = Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.grab_set()
        win.geometry("560x340")

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
            Label(win, text=label, font=F(9), anchor="w").grid(row=i, column=0, sticky="w", padx=10, pady=4)
            var = StringVar(value=existing.get(key) or "")
            Entry(win, textvariable=var, font=F(10), width=50).grid(row=i, column=1, sticky="ew", padx=10, pady=4)
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
            self.refresh_stats()
            win.destroy()
            messagebox.showinfo("完成", f"{title}成功")

        bf = Frame(win)
        bf.grid(row=len(labels), column=0, columnspan=2, pady=12)
        Button(bf, text="儲存", command=save, font=F(10), bg="#2b6cb0", fg="white", relief="flat", padx=16, pady=4, cursor="hand2").pack(side=LEFT, padx=8)
        Button(bf, text="取消", command=win.destroy, font=F(10), relief="groove", padx=16, pady=4, cursor="hand2").pack(side=LEFT)

    # ── 連結 ─────────────────────────────────────

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

    # ── 搜尋與複製 ───────────────────────────────

    def on_search(self):
        q = self.search_var.get().strip().lower()
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self._result_rows = []
        if not q:
            return
        if not self.companies:
            self.companies = ml.load_companies()

        matches = []
        for c in self.companies:
            hay = " ".join([
                c.get("eng") or "",
                c.get("chi") or "",
                c.get("addr_eng") or "",
                c.get("addr_chi") or "",
                c.get("addr") or "",
                c.get("gazette_file") or "",
                c.get("gazette_date") or "",
                c.get("gazette_no") or "",
                c.get("addr_eng_file") or "",
                c.get("addr_chi_file") or "",
            ]).lower()
            if q in hay:
                matches.append(c)

        if not matches:
            self.set_status("搜尋無結果")
            return
        self._fill_tree(matches, "搜尋結果")

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
        self._copy_to_clipboard(self._value_of_cell(row_id, col_id), "儲存格")

    def copy_selected_cell(self):
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
            self.set_status("請先在結果表中點選一列")
            return
        vals = self.result_tree.item(sel[0], "values")
        self._copy_to_clipboard("\t".join(vals), "整列")

    def _copy_to_clipboard(self, text: str, label: str = ""):
        if not text:
            self.set_status("該欄位是空的，沒有可複製的內容")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        preview = text if len(text) <= 60 else text[:57] + "..."
        self.set_status(f"已複製{label}：{preview}")


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
    app.log("功能一覽：")
    app.log("  更新：官方名稱｜憲報地址｜本地持牌人 PDF｜匯出 CSV")
    app.log("  匯入：Google Sheet｜設定 URL｜本機 CSV")
    app.log("  管理：顯示全部｜缺地址｜新增｜編輯｜刪除｜搜尋")
    app.log("建議：先「更新官方名稱」→ 再匯入憲報 PDF 補地址 → 匯出 CSV")
    app.log("─" * 40)
    root.mainloop()


if __name__ == "__main__":
    main()
