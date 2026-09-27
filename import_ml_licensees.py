#!/usr/bin/env python3
"""
香港放債人牌照持牌人名單 PDF 解析工具
------------------------------------
從 ml_licensees1-7.pdf 提取每間公司的英文名稱與中文名稱，
產生可直接匯入 Google Sheet 的 CSV，並同步更新 companies.json
（與 CompanyAddressManager.py 完全相容）。

使用方法：
    1. pip install pdfplumber
    2. 把 ml_licensees1-7.pdf 與 sheet_url.json 放在同一目錄
    3. python import_ml_licensees.py
"""

import csv
import json
import os
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("❌ 請先安裝 pdfplumber：")
    print("   pip install pdfplumber")
    sys.exit(1)

# ────────────────────────────────────────────────
# 檔案路徑（可依實際情況修改）
# ────────────────────────────────────────────────
PDF_FILE = "ml_licensees1-7.pdf"
SHEET_URL_FILE = "sheet_url.json"
OUTPUT_CSV = "ml_licensees_names.csv"
COMPANIES_JSON = "companies.json"


def clean_name(text: str) -> str:
    """清理 PDF 提取出的名稱（移除 (cid:xx) 編碼殘留與多餘空白）"""
    if not text:
        return ""
    text = re.sub(r"\(cid:\d+\)", "", str(text))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_sheet_url() -> str:
    """讀取 sheet_url.json 中的 Google Sheet 網址"""
    if not os.path.exists(SHEET_URL_FILE):
        return ""
    try:
        with open(SHEET_URL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return (data.get("url") or "").strip()
    except Exception:
        return ""


def extract_from_pdf(pdf_path: str) -> list[dict]:
    """
    解析整個 PDF，回傳 list of dict：
        {"eng": "...", "chi": "...", "addr": ""}
    """
    companies = []
    seen = set()  # 以英文名稱去重

    print(f"正在開啟 PDF：{pdf_path}")
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        print(f"共 {total_pages} 頁，開始逐頁提取表格...\n")

        for page_num, page in enumerate(pdf.pages, start=1):
            print(f"  → 處理第 {page_num:2d}/{total_pages} 頁", end="\r")

            tables = page.extract_tables() or []
            for table in tables:
                if not table or len(table) < 2:
                    continue

                # 跳過表頭列（通常第一列含有 "English Name" 或 "英文名稱"）
                start = 0
                for i, row in enumerate(table):
                    joined = " ".join(str(c or "") for c in row).lower()
                    if "english" in joined or "英文名稱" in joined or "mlr no" in joined:
                        start = i + 1
                        break

                for row in table[start:]:
                    if not row or len(row) < 4:
                        continue

                    eng = clean_name(row[2] if len(row) > 2 else "")
                    chi = clean_name(row[3] if len(row) > 3 else "")

                    # 必須至少有英文名稱
                    if not eng:
                        continue

                    key = eng.lower()
                    if key in seen:
                        continue
                    seen.add(key)

                    companies.append({
                        "eng": eng,
                        "chi": chi,
                        "addr": ""          # 地址留空，之後可用管理工具補上
                    })

    print(f"\n✅ 成功提取 {len(companies):,} 間公司（已去重）")
    return companies


def save_csv(companies: list[dict], path: str) -> None:
    """輸出乾淨的 CSV，方便直接匯入 Google Sheet"""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["English Name", "Chinese Name"])
        for c in companies:
            writer.writerow([c["eng"], c["chi"]])
    print(f"✅ 已產生 CSV：{path}")


def merge_into_companies_json(companies: list[dict], path: str) -> None:
    """
    合併到 companies.json（與 CompanyAddressManager.py 格式相容）
    只新增尚未存在的公司，不會覆蓋已有地址資料。
    """
    existing = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []

    existing_keys = set()
    for item in existing:
        if isinstance(item, dict):
            key = (item.get("eng") or item.get("chi") or "").lower()
            if key:
                existing_keys.add(key)

    added = 0
    for c in companies:
        key = (c["eng"] or c["chi"]).lower()
        if key and key not in existing_keys:
            existing.append(c)
            existing_keys.add(key)
            added += 1

    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"✅ 已更新 {path}（新增 {added} 筆，總計 {len(existing):,} 筆）")


def main() -> None:
    print("=" * 65)
    print("  香港放債人牌照持牌人名單 PDF → Google Sheet 匯入工具")
    print("=" * 65)
    print()

    # 檢查 PDF 是否存在
    if not os.path.exists(PDF_FILE):
        print(f"❌ 找不到 {PDF_FILE}")
        print("   請把 PDF 檔案放在與此腳本相同的目錄後再執行。")
        sys.exit(1)

    # 1. 解析 PDF
    companies = extract_from_pdf(PDF_FILE)
    if not companies:
        print("❌ 未能從 PDF 提取到任何公司資料")
        sys.exit(1)

    # 2. 輸出 CSV（給 Google Sheet 使用）
    save_csv(companies, OUTPUT_CSV)

    # 3. 同步更新本機 companies.json
    merge_into_companies_json(companies, COMPANIES_JSON)

    # 4. 顯示 Google Sheet 指引
    sheet_url = load_sheet_url()
    print()
    print("-" * 65)
    if sheet_url:
        print("📌 你的 Google Sheet：")
        print(f"   {sheet_url}")
        print()
        print("建議操作步驟：")
        print("  1. 開啟上面的 Google Sheet")
        print("  2. 選單 → 檔案 → 匯入 → 上傳")
        print(f"  3. 選擇本目錄產生的 {OUTPUT_CSV}")
        print("  4. 匯入位置建議選「取代目前工作表」或「附加到目前工作表」")
        print("  5. 確認後即可在 Sheet 看到所有英文名稱 + 中文名稱")
    else:
        print("⚠️  尚未找到 sheet_url.json")
        print("   你可以先執行 CompanyAddressManager.py 的選項 6 設定 Google Sheet URL")
        print(f"   或直接手動把 {OUTPUT_CSV} 匯入任何 Google Sheet")
    print("-" * 65)
    print()
    print("🎉 完成！資料已準備好匯入 Google Sheet。")


if __name__ == "__main__":
    main()
