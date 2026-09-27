#!/usr/bin/env python3
"""
香港放債人牌照資料更新工具
============================
功能：
  1. 自動下載公司註冊處最新「現有放債人牌照持牌人名單」CSV，更新公司名稱
  2. 解析你下載的政府憲報 (Gazette) PDF，提取申請時公布的「名稱 + 地址」
  3. 合併到 companies.json（與 CompanyAddressManager.py 相容）
  4. 輸出乾淨 CSV 方便匯入 Google Sheet

重要說明：
  - 官方免費名單（PDF/CSV）【不包含地址】
  - 地址只會出現在：
      a) 政府憲報的申請／續期通知（申請當下的地址）
      b) 公司註冊處電子查冊（e-Search，每間 HK$17，為目前最準確的現址）
  - 本工具用憲報做「盡力填充」，並保留手動／查冊更新地址的空間

使用方法：
  pip install pdfplumber requests

  # 只更新名稱（推薦每月執行一次）
  python update_money_lenders.py --names

  # 從憲報 PDF 提取地址並合併
  python update_money_lenders.py --gazette path/to/gazette1.pdf path/to/gazette2.pdf

  # 兩者一起做
  python update_money_lenders.py --names --gazette *.pdf
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("❌ 請先安裝 requests：pip install requests")
    sys.exit(1)

try:
    import pdfplumber
except ImportError:
    print("❌ 請先安裝 pdfplumber：pip install pdfplumber")
    sys.exit(1)

# ────────────────────────────────────────────────
# 設定
# ────────────────────────────────────────────────
OFFICIAL_CSV_URL = "https://www.cr.gov.hk/datagovhk/psi/ml_licensees.csv"
COMPANIES_JSON = "companies.json"
OUTPUT_CSV = "ml_licensees_with_addr.csv"
SHEET_URL_FILE = "sheet_url.json"


def _as_text(value) -> str:
    """把任意值安全轉成字串（相容 list / None / 數字）。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return " ".join(_as_text(v) for v in value if v).strip()
    return str(value).strip()


def _pick_addr_fields(item: dict) -> tuple[str, str, str]:
    """
    從多種可能的 JSON 鍵抽出英文／中文地址。
    支援：
      - 新格式 addr_eng / addr_chi
      - 舊格式 addr（自動依語言拆到 eng 或 chi）
      - 其他常見鍵名 Address / address / 地址 等
    """
    addr_eng = _as_text(
        item.get("addr_eng")
        or item.get("English Address")
        or item.get("english_address")
        or item.get("Address_Eng")
    )
    addr_chi = _as_text(
        item.get("addr_chi")
        or item.get("Chinese Address")
        or item.get("chinese_address")
        or item.get("Address_Chi")
        or item.get("地址")
    )
    # 舊版單一 addr / Address
    old_addr = _as_text(
        item.get("addr")
        or item.get("Address")
        or item.get("address")
        or item.get("資訊")
    )
    if old_addr:
        if not addr_eng and not addr_chi:
            if _is_chinese_addr(old_addr):
                addr_chi = old_addr
            else:
                addr_eng = old_addr
        elif not addr_chi and _is_chinese_addr(old_addr):
            addr_chi = old_addr
        elif not addr_eng and not _is_chinese_addr(old_addr):
            addr_eng = old_addr
    addr = addr_chi or addr_eng or old_addr
    return addr_eng, addr_chi, addr


def _normalize_company(item: dict) -> dict:
    """統一公司欄位：eng / chi / addr_eng / addr_chi + 憲報來源（並相容舊的單一 addr）。"""
    if not isinstance(item, dict):
        return empty_company()

    eng = _as_text(item.get("eng") or item.get("English Name") or item.get("Name_Eng") or item.get("name"))
    chi = _as_text(item.get("chi") or item.get("Chinese Name") or item.get("Name_Chi") or item.get("名稱"))
    # 若只有一個 name 欄且含中文
    if eng and not chi and re.search(r"[\u4e00-\u9fff]", eng):
        chi, eng = eng, ""

    addr_eng, addr_chi, addr = _pick_addr_fields(item)

    return {
        "eng": eng,
        "chi": chi,
        "addr_eng": addr_eng,
        "addr_chi": addr_chi,
        "addr": addr,
        "addr_eng_file": _as_text(item.get("addr_eng_file")),
        "addr_eng_date": _as_text(item.get("addr_eng_date")),
        "addr_chi_file": _as_text(item.get("addr_chi_file")),
        "addr_chi_date": _as_text(item.get("addr_chi_date")),
        "gazette_file": _as_text(item.get("gazette_file")),
        "gazette_date": _as_text(item.get("gazette_date")),
        "gazette_no": _as_text(item.get("gazette_no")),
    }


def has_any_address(item: dict) -> bool:
    return bool(_as_text(item.get("addr_eng") or item.get("addr_chi") or item.get("addr")))


def load_companies(path: str = COMPANIES_JSON) -> list[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            print(f"⚠️  {path} 格式不是陣列，已忽略")
            return []
        cleaned = [_normalize_company(item) for item in data if isinstance(item, dict)]
        return cleaned
    except Exception as e:
        print(f"⚠️  讀取 {path} 失敗：{e}")
        return []


def save_companies(data: list[dict], path: str = COMPANIES_JSON) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_sheet_url() -> str:
    if not os.path.exists(SHEET_URL_FILE):
        return ""
    try:
        with open(SHEET_URL_FILE, "r", encoding="utf-8") as f:
            return (json.load(f).get("url") or "").strip()
    except Exception:
        return ""


def save_sheet_url(url: str) -> None:
    with open(SHEET_URL_FILE, "w", encoding="utf-8") as f:
        json.dump({"url": (url or "").strip()}, f, ensure_ascii=False, indent=2)


def empty_company() -> dict:
    return {
        "eng": "",
        "chi": "",
        "addr_eng": "",
        "addr_chi": "",
        "addr": "",
        "addr_eng_file": "",
        "addr_eng_date": "",
        "addr_chi_file": "",
        "addr_chi_date": "",
        "gazette_file": "",
        "gazette_date": "",
        "gazette_no": "",
    }


def add_company(
    data: list[dict],
    eng: str = "",
    chi: str = "",
    addr_eng: str = "",
    addr_chi: str = "",
) -> tuple[list[dict], str]:
    """手動新增一間公司。回傳 (data, error_message)；成功時 error 為空字串。"""
    eng = (eng or "").strip()
    chi = (chi or "").strip()
    if not eng and not chi:
        return data, "至少需要英文或中文名稱其中一個"
    key_eng = eng.lower()
    key_chi = chi.lower()
    for e in data:
        if key_eng and (e.get("eng") or "").lower() == key_eng:
            return data, f"英文名稱已存在：{eng}"
        if key_chi and (e.get("chi") or "").lower() == key_chi:
            return data, f"中文名稱已存在：{chi}"
    item = empty_company()
    item["eng"] = eng
    item["chi"] = chi
    item["addr_eng"] = (addr_eng or "").strip()
    item["addr_chi"] = (addr_chi or "").strip()
    item["addr"] = item["addr_chi"] or item["addr_eng"]
    data.append(item)
    return data, ""


def update_company(data: list[dict], index: int, fields: dict) -> tuple[list[dict], str]:
    """更新 data[index] 的指定欄位。"""
    if index < 0 or index >= len(data):
        return data, "索引無效"
    item = _normalize_company(data[index])
    for k in (
        "eng", "chi", "addr_eng", "addr_chi",
        "addr_eng_file", "addr_eng_date", "addr_chi_file", "addr_chi_date",
        "gazette_file", "gazette_date", "gazette_no",
    ):
        if k in fields:
            item[k] = (fields[k] or "").strip()
    item["addr"] = item.get("addr_chi") or item.get("addr_eng") or ""
    data[index] = item
    return data, ""


def delete_company(data: list[dict], index: int) -> tuple[list[dict], str]:
    if index < 0 or index >= len(data):
        return data, "索引無效"
    data.pop(index)
    return data, ""


def find_company_index(data: list[dict], eng: str = "", chi: str = "") -> int:
    eng_l = (eng or "").lower().strip()
    chi_l = (chi or "").lower().strip()
    for i, e in enumerate(data):
        if eng_l and (e.get("eng") or "").lower() == eng_l:
            return i
        if chi_l and (e.get("chi") or "").lower() == chi_l:
            return i
    return -1


def sheet_export_url(sheet_url: str) -> str:
    if "/d/" in sheet_url:
        sheet_id = sheet_url.split("/d/")[1].split("/")[0]
    else:
        sheet_id = sheet_url.strip("/").split("/")[-1]
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid=0"


def import_from_google_sheet(data: list[dict], url: str = "") -> tuple[list[dict], int, int]:
    """
    從 Google Sheet（公開可檢視）匯入。
    支援欄位：English Name, Chinese Name, English Address, Chinese Address
    或舊格式：Name, Address
    回傳 (data, imported, skipped)
    """
    url = (url or load_sheet_url()).strip()
    if not url:
        raise ValueError("尚未設定 Google Sheet URL")
    if "docs.google.com" not in url:
        raise ValueError("請提供有效的 Google Sheet URL")

    export_url = sheet_export_url(url)
    print(f"正在從 Google Sheet 匯入：{export_url}")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ML-Updater/1.0)"}
    resp = requests.get(export_url, headers=headers, timeout=60)
    resp.raise_for_status()
    text = resp.content.decode("utf-8-sig")
    reader = csv.reader(text.splitlines())
    rows = list(reader)
    if not rows:
        return data, 0, 0

    # 偵測表頭
    header = [c.strip().lower() for c in rows[0]]
    has_header = any(
        k in " ".join(header)
        for k in ("english", "chinese", "name", "address", "英文", "中文", "名稱", "地址")
    )
    start = 1 if has_header else 0

    def col(*names):
        for n in names:
            if n in header:
                return header.index(n)
        return -1

    i_eng = col("english name", "name_eng", "eng", "english", "英文名稱", "英文")
    i_chi = col("chinese name", "name_chi", "chi", "chinese", "中文名稱", "中文")
    i_ae = col("english address", "addr_eng", "英文地址")
    i_ac = col("chinese address", "addr_chi", "中文地址", "address", "地址")
    # 舊格式：col0=name, col1=addr
    if i_eng < 0 and i_chi < 0:
        i_eng = 0
        if i_ac < 0:
            i_ac = 1 if len(rows[0]) > 1 else -1

    imported = skipped = 0
    for row in rows[start:]:
        if not row:
            continue

        def cell(i):
            if i < 0 or i >= len(row):
                return ""
            return (row[i] or "").strip()

        eng = cell(i_eng)
        chi = cell(i_chi)
        # 若只有一欄名稱，依字元判斷中英文
        if eng and not chi and re.search(r"[\u4e00-\u9fff]", eng):
            chi, eng = eng, ""
        addr_eng = cell(i_ae)
        addr_chi = cell(i_ac)
        if not eng and not chi:
            continue

        idx = find_company_index(data, eng, chi)
        if idx >= 0:
            # 只補空白欄位
            item = data[idx]
            if eng and not item.get("eng"):
                item["eng"] = eng
            if chi and not item.get("chi"):
                item["chi"] = chi
            if addr_eng and not item.get("addr_eng"):
                item["addr_eng"] = addr_eng
            if addr_chi and not item.get("addr_chi"):
                item["addr_chi"] = addr_chi
            item["addr"] = item.get("addr_chi") or item.get("addr_eng") or item.get("addr") or ""
            skipped += 1
            continue

        item = empty_company()
        item["eng"] = eng
        item["chi"] = chi
        item["addr_eng"] = addr_eng
        item["addr_chi"] = addr_chi
        item["addr"] = addr_chi or addr_eng
        data.append(item)
        imported += 1

    print(f"✅ Google Sheet 匯入：新增 {imported}，更新／略過 {skipped}")
    return data, imported, skipped


def import_from_csv_file(data: list[dict], path: str) -> tuple[list[dict], int, int]:
    """從本機 CSV 匯入（格式同匯出檔或 Name,Address）。"""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    # 重用 Google Sheet 解析邏輯：寫成假 URL 太麻煩，直接內嵌相同解析
    reader = csv.reader(text.splitlines())
    rows = list(reader)
    if not rows:
        return data, 0, 0

    header = [c.strip().lower() for c in rows[0]]
    has_header = any(
        k in " ".join(header)
        for k in ("english", "chinese", "name", "address", "英文", "中文", "名稱", "地址")
    )
    start = 1 if has_header else 0

    def col(*names):
        for n in names:
            if n in header:
                return header.index(n)
        return -1

    i_eng = col("english name", "name_eng", "eng", "english", "英文名稱", "英文")
    i_chi = col("chinese name", "name_chi", "chi", "chinese", "中文名稱", "中文")
    i_ae = col("english address", "addr_eng", "英文地址")
    i_ac = col("chinese address", "addr_chi", "中文地址", "address", "地址")
    if i_eng < 0 and i_chi < 0:
        i_eng = 0
        if i_ac < 0:
            i_ac = 1 if len(rows[0]) > 1 else -1

    imported = skipped = 0
    for row in rows[start:]:
        if not row:
            continue

        def cell(i):
            if i < 0 or i >= len(row):
                return ""
            return (row[i] or "").strip()

        eng = cell(i_eng)
        chi = cell(i_chi)
        if eng and not chi and re.search(r"[\u4e00-\u9fff]", eng):
            chi, eng = eng, ""
        addr_eng = cell(i_ae)
        addr_chi = cell(i_ac)
        if not eng and not chi:
            continue

        idx = find_company_index(data, eng, chi)
        if idx >= 0:
            item = data[idx]
            if eng and not item.get("eng"):
                item["eng"] = eng
            if chi and not item.get("chi"):
                item["chi"] = chi
            if addr_eng and not item.get("addr_eng"):
                item["addr_eng"] = addr_eng
            if addr_chi and not item.get("addr_chi"):
                item["addr_chi"] = addr_chi
            item["addr"] = item.get("addr_chi") or item.get("addr_eng") or item.get("addr") or ""
            skipped += 1
            continue

        item = empty_company()
        item["eng"] = eng
        item["chi"] = chi
        item["addr_eng"] = addr_eng
        item["addr_chi"] = addr_chi
        item["addr"] = addr_chi or addr_eng
        data.append(item)
        imported += 1

    print(f"✅ CSV 匯入：新增 {imported}，更新／略過 {skipped}")
    return data, imported, skipped


def extract_names_from_licensee_pdf(pdf_path: str) -> list[dict]:
    """
    從公司註冊處「現有放債人牌照持牌人名單」PDF 提取英文／中文名稱。
    （表格欄位通常為 MLR No. / Licence No. / English / Chinese / …）
    """
    companies = []
    seen = set()
    print(f"正在解析持牌人名單 PDF：{pdf_path}")
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for page_num, page in enumerate(pdf.pages, start=1):
            print(f"  → 第 {page_num}/{total} 頁", end="\r")
            for table in page.extract_tables() or []:
                if not table or len(table) < 2:
                    continue
                start = 0
                for i, row in enumerate(table):
                    joined = " ".join(str(c or "") for c in row).lower()
                    if "english" in joined or "英文名稱" in joined or "mlr no" in joined:
                        start = i + 1
                        break
                for row in table[start:]:
                    if not row or len(row) < 4:
                        continue
                    eng = re.sub(r"\(cid:\d+\)", "", str(row[2] or ""))
                    chi = re.sub(r"\(cid:\d+\)", "", str(row[3] or ""))
                    eng = re.sub(r"\s+", " ", eng).strip()
                    chi = re.sub(r"\s+", " ", chi).strip()
                    if not eng:
                        continue
                    key = eng.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    item = empty_company()
                    item["eng"] = eng
                    item["chi"] = chi
                    companies.append(item)
    print(f"\n✅ 從 PDF 提取 {len(companies):,} 間公司（已去重）")
    return companies


# ────────────────────────────────────────────────
# 1. 從官方 CSV 更新名稱
# ────────────────────────────────────────────────

def download_official_csv(url: str = OFFICIAL_CSV_URL) -> list[dict]:
    print(f"正在下載官方名單：{url}")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ML-Updater/1.0)"}
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    # 處理 BOM
    text = resp.content.decode("utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    rows = []
    for row in reader:
        eng = (row.get("Name_Eng") or "").strip()
        chi = (row.get("Name_Chi") or "").strip()
        if eng or chi:
            rows.append({
                "eng": eng,
                "chi": chi,
                "mlr_no": (row.get("MLR_No") or "").strip(),
                "licence_no": (row.get("ML_Lic_No") or "").strip(),
                "expiry": (row.get("Expiry_Date") or "").strip(),
                "remarks": (row.get("Remarks") or "").strip(),
            })
    print(f"✅ 下載完成，共 {len(rows):,} 間現有持牌人")
    return rows


def merge_names(existing: list[dict], official: list[dict]) -> tuple[list[dict], int, int]:
    """
    用官方名單更新／新增公司名稱。
    保留已有的地址（不會被清空）。
    亦保留「只有中文名」的現有記錄（例如僅從中文憲報加入的公司）。
    回傳 (updated_list, added, updated_names)
    """
    by_eng: dict[str, dict] = {}
    chi_only: list[dict] = []

    for item in existing:
        item = _normalize_company(item)
        key = (item.get("eng") or "").lower()
        if key:
            by_eng[key] = item
        else:
            # 沒有英文名的記錄先保留，稍後附在結果後面
            chi_only.append(item)

    added = 0
    updated = 0

    for o in official:
        eng = (o.get("eng") or "").strip()
        chi = (o.get("chi") or "").strip()
        key = eng.lower()
        if not key:
            continue
        if key in by_eng:
            old = by_eng[key]
            if chi and old.get("chi") != chi:
                old["chi"] = chi
                updated += 1
            # 地址與來源欄位保持不動
        else:
            item = empty_company()
            item["eng"] = eng
            item["chi"] = chi
            by_eng[key] = item
            added += 1

    result = list(by_eng.values()) + chi_only
    return result, added, updated


# ────────────────────────────────────────────────
# 2. 從政府憲報 PDF 提取地址（支援中文版 + 英文版）
# ────────────────────────────────────────────────

NAME_END_RE = re.compile(
    r"(有限公司|集團有限公司|Limited|Ltd\.?|Company Limited)\b",
    re.IGNORECASE,
)


def _is_chinese_addr(addr: str) -> bool:
    """判斷地址是否以中文為主。"""
    if not addr:
        return False
    chi = len(re.findall(r"[\u4e00-\u9fff]", addr))
    return chi >= 2


def _title_case_name(name: str) -> str:
    """把 PDF 抽出的怪異大小寫英文名稱整理成 Title Case（保留 Limited 等）。"""
    if not name or re.search(r"[\u4e00-\u9fff]", name):
        return name
    parts = name.split()
    fixed = []
    for p in parts:
        low = p.lower()
        if low in ("limited", "ltd", "ltd.", "company", "co", "co.", "of", "the", "and", "for"):
            fixed.append(p.capitalize() if low not in ("of", "the", "and", "for") else low)
        elif p.isupper() or p.islower() or (p[0].islower() if p else False):
            fixed.append(p.capitalize())
        else:
            fixed.append(p)
    # Limited / Ltd 統一首字大寫
    out = " ".join(fixed)
    out = re.sub(r"\bLimited\b", "Limited", out, flags=re.I)
    out = re.sub(r"\bLtd\.?\b", "Ltd.", out, flags=re.I)
    return out


_ENG_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
    "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def _parse_gazette_meta(full_text: str, pdf_path: str) -> dict:
    """從憲報全文與檔名解析：日期（ISO）、公告編號、檔名。"""
    meta = {
        "file": os.path.basename(pdf_path),
        "date": "",
        "gn": "",
        "lang": "",
    }

    # 中文日期：2026年3月6日
    m = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", full_text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        meta["date"] = f"{y:04d}-{mo:02d}-{d:02d}"
    else:
        # 英文日期：6 March 2026 / 6th March, 2026
        m = re.search(
            r"(\d{1,2})(?:st|nd|rd|th)?\s+"
            r"(January|February|March|April|May|June|July|August|September|October|November|December|"
            r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?,?\s+(\d{4})",
            full_text,
            re.IGNORECASE,
        )
        if m:
            day = int(m.group(1))
            mon = _ENG_MONTHS.get(m.group(2).lower(), 0)
            year = int(m.group(3))
            if mon:
                meta["date"] = f"{year:04d}-{mon:02d}-{day:02d}"

    # 公告編號：第1382號公告 / G.N. 1382
    m = re.search(r"第\s*(\d+)\s*號公告", full_text)
    if not m:
        m = re.search(r"G\.?\s*N\.?\s*(\d+)", full_text, re.IGNORECASE)
    if m:
        meta["gn"] = m.group(1)

    return meta


def extract_one_gazette(pdf_path: str) -> tuple[dict[str, str], dict]:
    """
    解析單一憲報 PDF。

    回傳:
      ( {公司名稱: 地址}, {file, date, gn, lang} )

    同時支援中文版與英文版憲報。
    """
    empty_meta = {
        "file": os.path.basename(pdf_path),
        "date": "",
        "gn": "",
        "lang": "",
    }
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception as e:
        print(f"   ❌ 開啟失敗：{e}")
        return {}, empty_meta

    meta = _parse_gazette_meta(full, pdf_path)

    upper = full.upper()
    is_chi_notice = "放債人條例" in full
    is_eng_notice = "MONEY LENDERS ORDINANCE" in upper or "MONEY LENDER" in upper
    if not is_chi_notice and not is_eng_notice:
        print("   （此 PDF 似乎不含放債人通知，跳過）")
        return {}, meta

    # ── 定位資料區 ──────────────────────────────
    body = None
    lang = None

    # 中文表頭
    m = re.search(r"號碼\s*名稱\s*地址", full)
    if m:
        body = full[m.end():]
        end = re.search(
            r"記載上述申請書|登記冊可於公司註冊處|放債人註冊處處長", body
        )
        if end:
            body = body[: end.start()]
        lang = "chi"

    # 英文表頭（No. Name Address，可能跨行）
    if body is None:
        m = re.search(
            r"No\.?\s*Name\s*Address",
            full,
            re.IGNORECASE,
        )
        if m:
            body = full[m.end():]
            end = re.search(
                r"The register containing particulars|"
                r"Any person wishing to object|"
                r"Registrar of Money Lenders",
                body,
                re.IGNORECASE,
            )
            if end:
                body = body[: end.start()]
            lang = "eng"

    if body is None:
        print("   （找不到「號碼 名稱 地址」或「No. Name Address」表頭）")
        return {}, meta

    meta["lang"] = lang or ""
    date_info = f"，日期 {meta['date']}" if meta.get("date") else ""
    gn_info = f"，G.N. {meta['gn']}" if meta.get("gn") else ""
    print(f"   （偵測為{'中文' if lang == 'chi' else '英文'}版憲報{date_info}{gn_info}）")

    # ── 以「行首的 N. 」切開每一筆 ─────────────
    parts = re.split(r"(?:^|\n)\s*(\d+)\.\s+", body)
    results: dict[str, str] = {}
    i = 1
    while i + 1 < len(parts):
        rest = parts[i + 1]
        i += 2

        rest = re.sub(r"[ \t]+", " ", rest)
        one = re.sub(r"\s*\n\s*", " ", rest).strip()
        if not one:
            continue

        # 特例：英文名稱中間被插入中文地址
        # 例：Equities First Holdings Hong Kong 香港中環... 2903 Limited 至05室
        special = re.match(
            r"^([A-Za-z0-9 &.,'()\-]+?)\s+"
            r"((?:香港|九龍|新界)[^A-Za-z]*?)\s*"
            r"((?:Limited|Ltd\.?|Company Limited)\b.*)$",
            one,
            re.IGNORECASE,
        )
        if special:
            name = (special.group(1).strip() + " " + special.group(3).split()[0]).strip()
            leftover = " ".join(special.group(3).split()[1:])
            addr = re.sub(r"\s+", " ", (special.group(2) + " " + leftover).strip())
            name = _title_case_name(name)
            if name and len(addr) > 5:
                results[name] = addr
            continue

        ends = list(NAME_END_RE.finditer(one))
        if not ends:
            continue

        # 取仍在字串前 75% 的最後一個名稱結尾
        best = ends[0]
        for e in ends:
            if e.end() < len(one) * 0.75:
                best = e

        name = one[: best.end()].strip()
        addr = one[best.end() :].strip()

        # 把「(前稱…)」移入名稱
        former = re.search(r"[\(（](前稱[^\)）]+)[\)）]", addr)
        if former:
            if "前稱" not in name:
                name = f"{name} ({former.group(1).strip()})"
            addr = (addr[: former.start()] + addr[former.end() :]).strip()

        addr = re.sub(r"\s+", " ", addr).strip()
        addr = re.sub(r"^\(?\d+\)?\s*", "", addr)
        addr = re.sub(r"\s*\(\s*(\d+)\s*\)\s*", r"; (\1) ", addr)
        # 去掉英文地址末尾多餘句點
        addr = re.sub(r"\.+$", ".", addr).strip()
        # 英文地址：修正 PDF 抽取造成的全小寫／亂大小寫
        if addr and not _is_chinese_addr(addr):
            addr = _cleanup_eng_address(addr)

        name = _title_case_name(name)

        if name and len(addr) > 5:
            results[name] = addr

    return results, meta


def _cleanup_eng_address(addr: str) -> str:
    """整理英文地址的大小寫（PDF 常抽出全小寫或混亂大小寫）。"""
    # 已知應大寫的詞
    keep_upper = {
        "ncb", "hk", "nt", "tsim", "sha", "tsui", "lai", "chi", "kok",
        "g/f", "1/f", "2/f", "3/f",
    }
    parts = addr.split()
    out = []
    for i, p in enumerate(parts):
        # 保留已有合理大小寫的 token（含數字、縮寫）
        if any(c.isdigit() for c in p) or p.isupper() and len(p) <= 4:
            out.append(p)
            continue
        low = p.lower().strip(".,;")
        if low in keep_upper:
            out.append(p.upper() if len(low) <= 3 else p.title())
        elif i == 0 or low in (
            "office", "shop", "flat", "flats", "unit", "units", "room",
            "floor", "building", "centre", "center", "tower", "plaza",
            "road", "street", "avenue", "lane", "drive", "hong", "kong",
            "kowloon", "new", "territories", "the", "of", "and", "area",
            "hotel", "retail", "commercial", "innovation", "capital",
            "park", "south", "north", "east", "west",
        ):
            out.append(p.capitalize() if low not in ("of", "and", "the") else low)
        else:
            out.append(p.capitalize())
    result = " ".join(out)
    # 常見修正
    result = re.sub(r"\bNcb\b", "NCB", result)
    result = re.sub(r"\bHk\b", "HK", result)
    result = re.sub(r"\bTsim Sha Tsui\b", "Tsim Sha Tsui", result, flags=re.I)
    return result


def extract_addresses_from_gazette(pdf_paths: list[str]) -> dict[str, dict]:
    """
    從一份或多份政府憲報 PDF（中文版或英文版）提取資料。

    回傳:
      {
        公司名稱: {
          "addr": "...",
          "gazette_file": "cgn202630101382.pdf",
          "gazette_date": "2026-03-06",
          "gazette_no": "1382",
        },
        ...
      }

    同一公司若同時有中、英地址，兩邊都會保留在不同 key 下（名稱可能不同）；
    若同一 key 出現兩次，優先中文地址，否則取較長者。
    """
    name_to_info: dict[str, dict] = {}

    for pdf_path in pdf_paths:
        if not os.path.exists(pdf_path):
            print(f"⚠️  找不到檔案：{pdf_path}")
            continue

        print(f"正在解析憲報：{pdf_path}")
        found, meta = extract_one_gazette(pdf_path)
        print(
            f"   → 從本檔提取到 {len(found)} 筆地址"
            + (f"（{meta.get('date') or '日期未知'}）" if found else "")
        )

        for name, addr in found.items():
            entry = {
                "addr": addr,
                "gazette_file": meta.get("file") or os.path.basename(pdf_path),
                "gazette_date": meta.get("date") or "",
                "gazette_no": meta.get("gn") or "",
            }
            key = name.lower()
            existing_key = next((k for k in name_to_info if k.lower() == key), None)

            if existing_key is None:
                name_to_info[name] = entry
                continue

            old = name_to_info[existing_key]
            old_addr = old.get("addr") or ""
            prefer_new = False
            if _is_chinese_addr(addr) and not _is_chinese_addr(old_addr):
                prefer_new = True
            elif _is_chinese_addr(addr) == _is_chinese_addr(old_addr) and len(addr) > len(old_addr):
                prefer_new = True

            if prefer_new:
                if existing_key != name:
                    del name_to_info[existing_key]
                name_to_info[name] = entry

    print(f"✅ 憲報共提取到 {len(name_to_info)} 個不重複公司地址")
    return name_to_info


def _norm(s: str) -> str:
    """簡易正規化，方便中英文名稱對應。"""
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[\(（]前稱.*?[\)）]", "", s)
    return s


def _apply_addr_source(item: dict, field: str, addr: str, info: dict) -> None:
    """寫入地址及其憲報來源（file / date / no）。"""
    item[field] = addr
    prefix = field  # addr_eng or addr_chi
    item[f"{prefix}_file"] = info.get("gazette_file") or ""
    item[f"{prefix}_date"] = info.get("gazette_date") or ""
    item["gazette_file"] = info.get("gazette_file") or item.get("gazette_file") or ""
    item["gazette_date"] = info.get("gazette_date") or item.get("gazette_date") or ""
    item["gazette_no"] = info.get("gazette_no") or item.get("gazette_no") or ""
    item["addr"] = item.get("addr_chi") or item.get("addr_eng") or ""


def merge_addresses(existing: list[dict], name_to_info: dict) -> tuple[list[dict], int]:
    """
    把憲報地址合併進現有資料。
    依語言寫入 addr_eng 或 addr_chi，並一併記錄來源 PDF 檔名與憲報日期。
    只填寫空白欄位，不覆寫已有內容。
    """
    by_eng = {_norm(item.get("eng", "")): i for i, item in enumerate(existing) if item.get("eng")}
    by_chi = {_norm(item.get("chi", "")): i for i, item in enumerate(existing) if item.get("chi")}

    filled = 0
    for name, info in name_to_info.items():
        # 相容舊呼叫：若仍傳 str，包成 dict
        if isinstance(info, str):
            info = {"addr": info, "gazette_file": "", "gazette_date": "", "gazette_no": ""}
        addr = (info.get("addr") or "").strip()
        if not addr:
            continue

        key = _norm(name)
        idx = by_eng.get(key)
        if idx is None:
            idx = by_chi.get(key)

        is_chi = _is_chinese_addr(addr)
        field = "addr_chi" if is_chi else "addr_eng"

        if idx is not None:
            item = existing[idx]
            item.setdefault("addr_eng", "")
            item.setdefault("addr_chi", "")
            if not item.get(field):
                _apply_addr_source(item, field, addr, info)
                filled += 1
        else:
            new_item = {
                "eng": "" if re.search(r"[\u4e00-\u9fff]", name) else name,
                "chi": name if re.search(r"[\u4e00-\u9fff]", name) else "",
                "addr_eng": "",
                "addr_chi": "",
                "addr": "",
                "addr_eng_file": "",
                "addr_eng_date": "",
                "addr_chi_file": "",
                "addr_chi_date": "",
                "gazette_file": "",
                "gazette_date": "",
                "gazette_no": "",
            }
            _apply_addr_source(new_item, field, addr, info)
            existing.append(new_item)
            filled += 1

    return existing, filled


# ────────────────────────────────────────────────
# 輸出
# ────────────────────────────────────────────────

def export_csv(data: list[dict], path: str = OUTPUT_CSV) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "English Name",
            "Chinese Name",
            "English Address",
            "Chinese Address",
            "Eng Addr Gazette File",
            "Eng Addr Gazette Date",
            "Chi Addr Gazette File",
            "Chi Addr Gazette Date",
            "Gazette No",
        ])
        for c in sorted(data, key=lambda x: (x.get("eng") or x.get("chi") or "").lower()):
            c = _normalize_company(c)
            writer.writerow([
                c["eng"],
                c["chi"],
                c["addr_eng"],
                c["addr_chi"],
                c.get("addr_eng_file") or "",
                c.get("addr_eng_date") or "",
                c.get("addr_chi_file") or "",
                c.get("addr_chi_date") or "",
                c.get("gazette_no") or "",
            ])
    print(f"✅ 已輸出 {path}（共 {len(data):,} 筆）")


def print_summary(data: list[dict]) -> None:
    total = len(data)
    with_addr = sum(1 for c in data if has_any_address(c))
    print()
    print("=" * 60)
    print(f"  目前資料庫統計")
    print("=" * 60)
    print(f"  公司總數          : {total:,}")
    print(f"  已有地址          : {with_addr:,}  ({with_addr/total*100:.1f}%)" if total else "")
    print(f"  尚未有地址        : {total - with_addr:,}")
    print("=" * 60)

    sheet = load_sheet_url()
    if sheet:
        print(f"\n📌 Google Sheet：{sheet}")
        print("   可把輸出的 CSV 直接匯入（檔案 → 匯入 → 上傳）")
    print()
    print("【取得準確現址的建議】")
    print("  1. 免費盡力填充：下載最近數月的政府憲報 PDF，用 --gazette 參數解析")
    print("  2. 需要核實的公司：到 https://www.e-services.cr.gov.hk")
    print("     → Search → Licensed Money Lenders → 付 HK$17 查單間現址")
    print("  3. 之後可在 CompanyAddressManager.py 手動修改地址")


# ────────────────────────────────────────────────
# 主程式
# ────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="更新香港放債人牌照持牌人名稱與地址",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  python update_money_lenders.py --names
  python update_money_lenders.py --gazette gazette_2026_03.pdf
  python update_money_lenders.py --names --gazette g1.pdf g2.pdf
        """,
    )
    parser.add_argument("--names", action="store_true", help="從官方 CSV 更新公司名稱")
    parser.add_argument("--gazette", nargs="+", metavar="PDF", help="從政府憲報 PDF 提取地址")
    parser.add_argument("--export-only", action="store_true", help="只輸出目前 companies.json 成 CSV")
    args = parser.parse_args()

    if not (args.names or args.gazette or args.export_only):
        parser.print_help()
        print("\n請至少指定 --names 或 --gazette 或 --export-only")
        sys.exit(1)

    data = load_companies()
    print(f"目前 companies.json 有 {len(data):,} 筆\n")

    if args.names:
        try:
            official = download_official_csv()
            data, added, updated = merge_names(data, official)
            print(f"✅ 名稱更新完成：新增 {added} 間，更新中文名 {updated} 間")
        except Exception as e:
            print(f"❌ 下載／更新官方名單失敗：{e}")
            sys.exit(1)

    if args.gazette:
        name_to_addr = extract_addresses_from_gazette(args.gazette)
        if name_to_addr:
            data, filled = merge_addresses(data, name_to_addr)
            print(f"✅ 地址合併完成：填充／新增了 {filled} 筆地址")

    # 儲存
    save_companies(data)
    print(f"✅ 已寫入 {COMPANIES_JSON}")

    # 輸出 CSV
    export_csv(data)
    print_summary(data)


if __name__ == "__main__":
    main()
