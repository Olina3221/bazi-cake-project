"""
db.py ── Google Sheets adapter
=====================================
所有讀寫資料庫的邏輯都在這裡。
app.py / admin.py 只呼叫這裡的函式，完全不碰 gspread。

未來換成 PostgreSQL / SQLite，只要改這個檔案。

環境變數（部署時設定）：
  GOOGLE_SHEETS_ID          ── Spreadsheet ID（網址中間那串）
  GOOGLE_SERVICE_ACCOUNT    ── Service Account JSON 內容（整個 JSON 字串）

本機開發：
  把 service account JSON 存成 service_account.json 放在同層，
  或設定環境變數 GOOGLE_SERVICE_ACCOUNT。
"""

import os
import json
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# ── 連線 ──────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_gc = None  # gspread client（lazy init）
_sh = None  # spreadsheet（lazy init）


def _get_sheet(tab_name: str):
    """取得指定 tab 的 worksheet，lazy 初始化連線"""
    global _gc, _sh

    if _sh is None:
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT")
        if sa_json:
            info = json.loads(sa_json)
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        else:
            creds = Credentials.from_service_account_file(
                "service_account.json", scopes=SCOPES
            )
        _gc = gspread.authorize(creds)
        sheet_id = os.environ.get("GOOGLE_SHEETS_ID", "")
        _sh = _gc.open_by_key(sheet_id)

    return _sh.worksheet(tab_name)


def _get_sheet_safe(tab_name: str):
    """同 _get_sheet，但連線失敗時回傳 None 而非拋出例外"""
    try:
        return _get_sheet(tab_name)
    except Exception:
        return None


# ── Orders ────────────────────────────────────────────────────────

ORDERS_HEADER = [
    "id", "建立時間", "姓名", "電話", "生日", "時辰",
    "心願主項", "心願細項", "備註", "狀態",
    "八字分析", "選用食材", "小卡文案", "五行建議"
]


def _row_to_order(row: list) -> dict:
    """把一列資料轉成 order dict，欄位不足時補空字串"""
    def g(i): return row[i] if i < len(row) else ""
    return {
        "id":          g(0),
        "created_at":  g(1),
        "name":        g(2),
        "phone":       g(3),
        "birthday":    g(4),
        "shichen":     g(5),
        "wish_main":   g(6),
        "wish_sub":    g(7),
        "note":        g(8),
        "status":      g(9)  or "待處理",
        "bazi_result": g(10),
        "ingredients": g(11),
        "card_text":   g(12),
        "suggestion":  g(13),
    }


def load_orders() -> list:
    """讀取所有訂單，回傳 list of dict，最新在前"""
    ws = _get_sheet_safe("八字蛋糕訂單")
    if ws is None:
        return []
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []
    data_rows = rows[1:]  # 跳過標題列
    result = []
    auto_id = 1
    for r in data_rows:
        if not r:
            continue
        if not r[0]:
            r = list(r)
            r[0] = str(auto_id)
        else:
            try:
                auto_id = int(r[0]) + 1
            except ValueError:
                pass
        result.append(_row_to_order(r))
    return list(reversed(result))


def get_next_order_id() -> int:
    """取得下一個訂單流水號"""
    ws = _get_sheet("八字蛋糕訂單")
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return 1
    # 找最後一列有效 id
    for row in reversed(rows[1:]):
        if row and row[0]:
            try:
                return int(row[0]) + 1
            except ValueError:
                pass
    return 1


def create_order(name, phone, birthday, shichen, wish_main, wish_sub, note) -> int:
    """新增一筆訂單，回傳新訂單 id"""
    ws = _get_sheet("八字蛋糕訂單")
    new_id = get_next_order_id()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.append_row([
        new_id, created_at, name, phone, birthday,
        shichen, wish_main, wish_sub, note, "待處理",
        "", "", "", ""
    ], value_input_option="USER_ENTERED")
    return new_id


def update_order_fields(order_id, fields: dict):
    """
    更新訂單指定欄位。
    fields 可包含：status, bazi_result, ingredients, card_text, suggestion
    """
    col_map = {
        "status": 10, "bazi_result": 11, "ingredients": 12,
        "card_text": 13, "suggestion": 14
    }
    ws = _get_sheet("八字蛋糕訂單")
    rows = ws.get_all_values()

    for i, row in enumerate(rows[1:], start=2):  # start=2 因為第1列是標題
        if row and str(row[0]) == str(order_id):
            for field, value in fields.items():
                col = col_map.get(field)
                if col:
                    ws.update_cell(i, col, value)
            return
    raise ValueError(f"Order {order_id} not found")


# ── Ingredients ───────────────────────────────────────────────────

INGREDIENTS_HEADER = [
    "食材名稱", "主五行", "副五行", "用途", "季節",
    "顏色分析", "氣味分析", "屬性分析", "備注"
]


def load_ingredients() -> list:
    """回傳所有食材，每筆是長度 9 的 list"""
    ws = _get_sheet("ingredients")
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []
    return [list(r[:9]) for r in rows[1:] if r and r[0]]


def ingredient_exists(name: str) -> bool:
    ws = _get_sheet("ingredients")
    col = ws.col_values(1)  # 第一欄：食材名稱
    return name in col[1:]  # 跳過標題


def save_ingredient(data: dict) -> str:
    """
    新增食材。
    回傳 "saved" 或 "already_exists"
    """
    name = data.get("食材名稱", "").strip()
    if ingredient_exists(name):
        return "already_exists"
    ws = _get_sheet("ingredients")
    ws.append_row([
        name,
        data.get("主五行", ""),
        data.get("副五行", ""),
        data.get("用途", ""),
        data.get("季節", ""),
        data.get("顏色分析", ""),
        data.get("氣味分析", ""),
        data.get("屬性分析", ""),
        data.get("備注", ""),
    ], value_input_option="USER_ENTERED")
    return "saved"


def update_ingredient(data: dict) -> str:
    """
    更新現有食材所有欄位（名稱不可改）。
    回傳 "updated" 或 "not_found"
    """
    name = data.get("食材名稱", "").strip()
    ws = _get_sheet("ingredients")
    rows = ws.get_all_values()

    col_order = ["食材名稱", "主五行", "副五行", "用途", "季節",
                 "顏色分析", "氣味分析", "屬性分析", "備注"]

    for i, row in enumerate(rows[1:], start=2):
        if row and row[0] == name:
            new_row = [data.get(k, "") for k in col_order]
            # 更新整列（col 1~9）
            ws.update(f"A{i}:I{i}", [new_row], value_input_option="USER_ENTERED")
            return "updated"
    return "not_found"


def delete_ingredient(name: str) -> str:
    """
    刪除食材。
    回傳 "deleted" 或 "not_found"
    """
    ws = _get_sheet("ingredients")
    rows = ws.get_all_values()
    for i, row in enumerate(rows[1:], start=2):
        if row and row[0] == name:
            ws.delete_rows(i)
            return "deleted"
    return "not_found"


# ── 初始化 Sheets（第一次使用時建標題列）────────────────────────────

def init_sheets():
    """
    確保 orders / ingredients 工作表存在且有標題列。
    第一次部署時呼叫一次即可。
    """
    sh = _sh  # 先確保連線
    _get_sheet("八字蛋糕訂單")  # trigger lazy init

    existing = [ws.title for ws in _sh.worksheets()]

    if "八字蛋糕訂單" not in existing:
        ws = _sh.add_worksheet(title="八字蛋糕訂單", rows=1000, cols=14)
        ws.append_row(ORDERS_HEADER)

    if "ingredients" not in existing:
        ws = _sh.add_worksheet(title="ingredients", rows=500, cols=9)
        ws.append_row(INGREDIENTS_HEADER)

    # 確保標題列存在
    for tab, header in [("八字蛋糕訂單", ORDERS_HEADER), ("ingredients", INGREDIENTS_HEADER)]:
        ws = _get_sheet(tab)
        first = ws.row_values(1)
        if not first:
            ws.insert_row(header, 1)

    print("✅ Google Sheets 初始化完成")
