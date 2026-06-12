"""
migrate_phase2.py — Task1 Phase 2 Sheet 結構調整（可重跑 / 冪等）
=================================================================
在合併後的後台 Sheet（1oYJ7…）上做 Phase 2 需要的結構調整：

  1. 「八字蛋糕訂單」tab 尾端加「已轉入」欄（D5）。
  2. 「下午茶訂單」tab 尾端加「已轉入」欄（D5）。
  3. 新建「下午茶管理」tab（D1，欄位依 db.TEA_MANAGE_HEADER）。
  4. orders tab 標題列（第 1 列）改成新版 18 欄 ORDERS_HEADER（D4 / Phase 4.4 提前）。

安全規則（絕對遵守）：
  - 只動標題列 / 追加欄 / 新建 tab，不動任何既有「資料列」。
  - 前台 Sheet 完全不碰。
  - 受保護 tab（ingredients / monthly）不觸碰。
  - 可重跑：已加過的欄 / 已建的 tab 偵測後跳過。

執行：python migrate_phase2.py
需求：專案根有 service_account.json（對後台 Sheet 可寫，SA 2026-06-13 已實測）
"""

import sys
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
import db  # ORDERS_HEADER / TEA_MANAGE_HEADER 等唯一來源

BACK_SHEET_ID = "1oYJ7qO4E40aw1RVip-O3NM6X_U-mYxGT1NIn_YvpW2E"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
PROTECTED_TABS = {"ingredients", "monthly"}  # 本 Phase 不觸碰


def _client():
    creds = Credentials.from_service_account_file(
        str(PROJECT_ROOT / "service_account.json"), scopes=SCOPES
    )
    return gspread.authorize(creds)


def _add_converted_column(ws, expected_header: list, label: str = "已轉入") -> str:
    """在 tab 尾端確保有「已轉入」欄。冪等：標題列已含 label 則跳過。
    只寫標題格，不動任何資料列（GAS append 按固定欄數，新欄在右側不影響對位）。"""
    header = ws.row_values(1)
    if label in header:
        return f"已存在「{label}」欄（第 {header.index(label) + 1} 欄），跳過"
    # 「已轉入」欄為 expected_header 的最後一欄（1-based）
    col = len(expected_header)
    ws.update_cell(1, col, label)
    return f"已新增「{label}」欄於第 {col} 欄（僅標題列）"


def fix_orders_header(ws) -> str:
    """把 orders 標題列改成新版 18 欄 ORDERS_HEADER（只動第 1 列）。"""
    current = ws.row_values(1)
    target = db.ORDERS_HEADER
    if current == target:
        return "orders 標題列已是新版 18 欄，跳過"
    ws.update(range_name="A1:R1", values=[target], value_input_option="RAW")
    return f"orders 標題列已改為新版 18 欄（原 {len(current)} 欄 → {len(target)} 欄），資料列未動"


def ensure_tea_manage_tab(sh) -> str:
    """確保「下午茶管理」tab 存在且有標題列。冪等。"""
    titles = {w.title for w in sh.worksheets()}
    if db.TEA_MANAGE_TAB in titles:
        ws = sh.worksheet(db.TEA_MANAGE_TAB)
        if ws.row_values(1) != db.TEA_MANAGE_HEADER:
            ws.update(range_name="A1", values=[db.TEA_MANAGE_HEADER],
                      value_input_option="RAW")
            return f"「{db.TEA_MANAGE_TAB}」已存在，標題列已校正"
        return f"「{db.TEA_MANAGE_TAB}」已存在且標題正確，跳過"
    ws = sh.add_worksheet(title=db.TEA_MANAGE_TAB, rows=500,
                          cols=max(len(db.TEA_MANAGE_HEADER) + 2, 12))
    ws.update(range_name="A1", values=[db.TEA_MANAGE_HEADER], value_input_option="RAW")
    return f"已新建「{db.TEA_MANAGE_TAB}」tab（{len(db.TEA_MANAGE_HEADER)} 欄）"


def run() -> list:
    gc = _client()
    sh = gc.open_by_key(BACK_SHEET_ID)
    titles = {w.title for w in sh.worksheets()}
    for t in ("orders", "八字蛋糕訂單", "下午茶訂單"):
        if t not in titles:
            raise RuntimeError(f"後台 Sheet 缺少 tab「{t}」，可能 Phase 1 未完成或開錯 Sheet，中止。")

    report = []
    report.append(("八字蛋糕訂單 已轉入欄",
                   _add_converted_column(sh.worksheet("八字蛋糕訂單"), db.BAZI_INBOX_HEADER)))
    report.append(("下午茶訂單 已轉入欄",
                   _add_converted_column(sh.worksheet("下午茶訂單"), db.TEA_INBOX_HEADER)))
    report.append(("下午茶管理 tab", ensure_tea_manage_tab(sh)))
    report.append(("orders 標題列", fix_orders_header(sh.worksheet("orders"))))
    return report


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("=== Task1 Phase 2 Sheet 結構調整 ===")
    for name, msg in run():
        print(f"[OK] {name}：{msg}")
    print("\n完成。只動了標題列 / 新欄 / 新 tab，未觸碰任何既有資料列、未碰前台 Sheet。")


if __name__ == "__main__":
    main()
