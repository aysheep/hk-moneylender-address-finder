# HK Money Lender Address Finder

Desktop tool for managing Hong Kong licensed money lenders:

- Update names from the Companies Registry official CSV
- Extract addresses from English and Chinese Government Gazette PDFs
- Keep a local `companies.json` database
- Filter **currently licensed** companies without deleting historical records
- Export CSV for Google Sheets

Official free lists contain **names only**. Addresses come from Gazette application notices (best-effort) or paid e-Search (HK$17 per company).

## Requirements

- Python 3.10+
- Windows / macOS / Linux

```bash
pip install pdfplumber requests
```

On Linux you may also need: `sudo apt install python3-tk`

## Run

Put these files in the same folder:

- `money_lenders_gui.py`
- `update_money_lenders.py`
- `import_ml_licensees.py` (optional, local PDF name import)

```bash
python money_lenders_gui.py
```

Command line:

```bash
python update_money_lenders.py --names
python update_money_lenders.py --gazette gazette1.pdf gazette2.pdf
python update_money_lenders.py --names --gazette *.pdf
python update_money_lenders.py --export-only
```

## Typical workflow

1. Click **更新官方名稱** (downloads the latest licensee list)
2. Download Gazette PDFs from [e-Gazette](https://www.gld.gov.hk/egazette/) (`放債人條例` / `MONEY LENDERS ORDINANCE`)
3. Click **憲報 PDF 提取地址** and select Chinese and/or English PDFs
4. Use **只顯示現有持牌人** to hide companies no longer on the official list
5. Double-click a row for a read-only detail window with per-field copy buttons
6. Export CSV when needed

## Data model (`companies.json`)

Each company stores English/Chinese names, English/Chinese addresses, Gazette source file/date/G.N., and:

- `licensed` — on the latest official list
- `licensed_as_of` — date of that comparison

Existing records are **never deleted** when the official list is refreshed. They are only marked licensed / not licensed.

## Disclaimer

This tool organises public government data. Gazette addresses are those published at application/renewal time and may not match the current registered office. For formal checks use [Companies Registry e-Search](https://www.e-services.cr.gov.hk).
