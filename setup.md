# 香港放債人牌照資料管理工具 — 安裝與使用說明

Setup & User Guide for the Money Lenders Licence Data Tools

---

## 1. 這套工具做什麼？

從**公司註冊處**公開資料，維護一份「現有放債人牌照持牌人」名單，並盡力補上地址。

官方免費名單**不含地址**。本工具用憲報做「盡力填充」。

---

## 2. 檔案一覽

```
your-folder/
├── update_money_lenders.py
├── money_lenders_gui.py
├── import_ml_licensees.py
├── setup.md
├── requirements.txt
├── companies.json          # generated locally, not in git
└── ml_licensees_with_addr.csv
```

---

## 3. 安裝

- Python 3.10+
- Windows / macOS / Linux

```bash
pip install -r requirements.txt
```

Linux may need: `sudo apt install python3-tk`

---

## 4. 執行

```bash
python money_lenders_gui.py
```

CLI:

```bash
python update_money_lenders.py --names
python update_money_lenders.py --gazette gazette1.pdf gazette2.pdf
python update_money_lenders.py --export-only
```

## 5. 典型流程

1. 按「更新官方名稱」下載最新持牌人名單
2. 從 e-Gazette 下載「放債人條例」/「MONEY LENDERS ORDINANCE」PDF
3. 按「憲報 PDF 提取地址」
4. 用「只顯示現有持牌人」篩選（不會刪除歷史記錄）
5. 雙擊一列開啟詳情視窗，每欄可複製
6. 匯出 CSV

## 6. 資料模型

Each company in `companies.json` stores English/Chinese names, addresses, Gazette file/date/G.N., plus:

- `licensed` — on the latest official list
- `licensed_as_of` — date of that comparison

Existing records are never deleted when the official list is refreshed.

## 7. 免責聲明

憲報地址為申請／續期當時資料，不一定等於目前登記處所。正式用途請以公司註冊處 e-Search 為準。
