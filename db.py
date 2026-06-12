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
import re
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

# Task1 D4：orders 擴欄 18 欄。新 4 欄（品項/數量/取貨日期/外送）追加在尾端 15-18，
# 不動 1-14，使 update_order_fields 的 col_map（10-14）零影響。
ORDERS_HEADER = [
    "id", "建立時間", "姓名", "電話", "生日", "時辰",
    "心願主項", "心願細項", "備註", "狀態",
    "八字分析", "選用食材", "小卡文案", "五行建議",
    "品項", "數量", "取貨日期", "外送"
]

# Task1 D2：訂單編號日期前綴格式 YYYYMMDD-NN（例 20260613-01）。
_ID_DATE_RE = re.compile(r"^(\d{8})-(\d+)$")


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
        "product":     g(14),
        "quantity":    g(15),
        "pickup_date": g(16),
        "delivery":    g(17),
    }


def load_orders() -> list:
    """讀取所有訂單，回傳 list of dict，最新在前"""
    ws = _get_sheet_safe("orders")
    if ws is None:
        return []
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []
    data_rows = rows[1:]  # 跳過標題列
    result = []
    # Task1 D2：id 改日期前綴 YYYYMMDD-NN（字串），無法再用整數遞增補位。
    # 空 id 列（理論上不該出現）以 row 序號補一個可辨識的 placeholder，
    # 不嘗試解析/遞增前一列 id（新舊格式皆字串，整數遞增不再適用）。
    for idx, r in enumerate(data_rows, start=1):
        if not r:
            continue
        if not r[0]:
            r = list(r)
            r[0] = f"row{idx}"  # 缺 id 的容錯標記，避免空 id 影響顯示/查找
        result.append(_row_to_order(r))
    return list(reversed(result))


def _max_seq_for_date(rows: list, date_str: str) -> int:
    """掃描 orders 既有列，回傳指定日期 YYYYMMDD 的最大序號（無則 0）。

    遇無法解析為 YYYYMMDD-NN 的舊 id（如整數 '1'）一律略過，
    不納入任何日期群組的序號計算（Task1 D2 舊資料相容）。
    """
    max_seq = 0
    for row in rows:
        if not row or not row[0]:
            continue
        m = _ID_DATE_RE.match(str(row[0]).strip())
        if m and m.group(1) == date_str:
            seq = int(m.group(2))
            if seq > max_seq:
                max_seq = seq
    return max_seq


def get_next_order_id_by_date(date_str: str) -> str:
    """Task1 D2：依日期 YYYYMMDD 取下一個訂單編號 YYYYMMDD-NN。

    - date_str：8 碼日期（取前台下單時間之日期，非轉單當下）。
    - 序號 = 該日期既有最大序號 + 1，補零至兩位；超過 99 自然進位成 3 位。
    - 不同日期各自從 01 起算。
    """
    ws = _get_sheet("orders")
    rows = ws.get_all_values()
    data_rows = rows[1:] if len(rows) > 1 else []
    next_seq = _max_seq_for_date(data_rows, date_str) + 1
    return f"{date_str}-{next_seq:02d}"


# 向後相容別名：舊呼叫者若用 get_next_order_id()，以今日日期取號。
def get_next_order_id() -> str:
    """取得下一個訂單編號（Task1 D2 改為日期前綴；預設用今日日期）。"""
    return get_next_order_id_by_date(datetime.now().strftime("%Y%m%d"))


def _date_str_from_created_at(created_at: str) -> str:
    """從建立時間字串萃取 YYYYMMDD；無法解析時 fallback 今日日期。

    支援多種前台格式（GAS 寫入有 '2026/6/6 13:59:22' 單位數、
    亦有 '2026-06-13 23:50' 補零、'2026/06/13 2:32:48' 等）。
    解析「年-月-日」開頭，月/日各 1-2 位皆可，組成補零的 YYYYMMDD。
    """
    if created_at:
        m = re.match(r"\s*(\d{4})\D{1,2}(\d{1,2})\D{1,2}(\d{1,2})", str(created_at))
        if m:
            y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
            return f"{y}{mo:02d}{d:02d}"
    return datetime.now().strftime("%Y%m%d")


def create_order(name, phone, birthday, shichen, wish_main, wish_sub, note,
                 created_at=None, product="", quantity="", pickup_date="",
                 delivery="") -> str:
    """新增一筆訂單，回傳新訂單 id（Task1 D2 起為字串 YYYYMMDD-NN）。

    Task1 連動：
    - created_at（D3）：選填，帶入前台下單時間；未傳則 fallback datetime.now()。
      其日期部分同時是 D2 取號的「當日」依據。
    - product/quantity/pickup_date/delivery（D4）：擴欄 15-18，選填，預設空字串。
    既有呼叫者不傳新參數時行為相容（仍寫 18 欄，新欄為空）。
    """
    ws = _get_sheet("orders")
    if not created_at:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    date_str = _date_str_from_created_at(created_at)
    new_id = get_next_order_id_by_date(date_str)
    ws.append_row([
        new_id, created_at, name, phone, birthday,
        shichen, wish_main, wish_sub, note, "待處理",
        "", "", "", "",
        product, quantity, pickup_date, delivery
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
    ws = _get_sheet("orders")
    rows = ws.get_all_values()

    for i, row in enumerate(rows[1:], start=2):  # start=2 因為第1列是標題
        if row and str(row[0]) == str(order_id):
            for field, value in fields.items():
                col = col_map.get(field)
                if col:
                    ws.update_cell(i, col, value)
            return
    raise ValueError(f"Order {order_id} not found")


# ── 前台訂單收件匣（Task1 Phase 2）─────────────────────────────────
# 合併後 Sheet 內，前台 GAS 寫入的兩張原始收件 tab + 下午茶管理 tab。

# 前台「八字蛋糕訂單」tab 原 10 欄 + 尾端「已轉入」欄（D5）= 11 欄
BAZI_INBOX_HEADER = [
    "時間", "name", "phone", "birthdate", "birth_hour",
    "product", "quantity", "pickup_date", "delivery", "notes", "已轉入"
]
BAZI_INBOX_COLS = len(BAZI_INBOX_HEADER)  # 11
_BAZI_CONVERTED_COL = BAZI_INBOX_COLS     # 1-based：第 11 欄

# 前台「下午茶訂單」tab 原 8 欄 + 尾端「已轉入」欄（D5）= 9 欄
TEA_INBOX_HEADER = [
    "時間", "company", "contact", "phone",
    "items", "event_date", "total_qty", "notes", "已轉入"
]
TEA_INBOX_COLS = len(TEA_INBOX_HEADER)    # 9
_TEA_CONVERTED_COL = TEA_INBOX_COLS       # 1-based：第 9 欄

# 下午茶管理 tab（Task1 D1）：前台 8 欄 + 狀態欄（D8 暫定「待處理」）
TEA_MANAGE_TAB = "下午茶管理"
TEA_MANAGE_HEADER = [
    "時間", "company", "contact", "phone",
    "items", "event_date", "total_qty", "notes", "狀態"
]
TEA_DEFAULT_STATUS = "待處理"  # D8 未拍板，Phase 2 固定單一值


def _bazi_inbox_row_to_dict(idx: int, row: list) -> dict:
    """八字蛋糕訂單列 → dict。idx 為 1-based 資料列序（不含標題列）。"""
    def g(i): return row[i] if i < len(row) else ""
    return {
        "row":         idx,          # Sheet 中的資料列序（標記/查找用）
        "created_at":  g(0),
        "name":        g(1),
        "phone":       g(2),
        "birthdate":   g(3),
        "birth_hour":  g(4),
        "product":     g(5),
        "quantity":    g(6),
        "pickup_date": g(7),
        "delivery":    g(8),
        "notes":       g(9),
        "converted":   g(_BAZI_CONVERTED_COL - 1),
    }


def _tea_inbox_row_to_dict(idx: int, row: list) -> dict:
    """下午茶訂單列 → dict。idx 為 1-based 資料列序（不含標題列）。"""
    def g(i): return row[i] if i < len(row) else ""
    return {
        "row":        idx,
        "created_at": g(0),
        "company":    g(1),
        "contact":    g(2),
        "phone":      g(3),
        "items":      g(4),
        "event_date": g(5),
        "total_qty":  g(6),
        "notes":      g(7),
        "converted":  g(_TEA_CONVERTED_COL - 1),
    }


def load_inbox_bazi(only_unconverted: bool = True) -> list:
    """讀八字蛋糕訂單 tab。only_unconverted=True 只回「已轉入」欄為空的列。"""
    ws = _get_sheet_safe("八字蛋糕訂單")
    if ws is None:
        return []
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []
    out = []
    for idx, r in enumerate(rows[1:], start=1):
        if not r or not any(str(c).strip() for c in r):
            continue
        d = _bazi_inbox_row_to_dict(idx, r)
        if only_unconverted and str(d["converted"]).strip():
            continue
        out.append(d)
    return out


def load_inbox_tea(only_unconverted: bool = True) -> list:
    """讀下午茶訂單 tab。only_unconverted=True 只回「已轉入」欄為空的列。"""
    ws = _get_sheet_safe("下午茶訂單")
    if ws is None:
        return []
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []
    out = []
    for idx, r in enumerate(rows[1:], start=1):
        if not r or not any(str(c).strip() for c in r):
            continue
        d = _tea_inbox_row_to_dict(idx, r)
        if only_unconverted and str(d["converted"]).strip():
            continue
        out.append(d)
    return out


def get_inbox_bazi_row(row_idx: int) -> dict:
    """取單一八字蛋糕訂單列（1-based 資料列序）；找不到回 None。"""
    ws = _get_sheet_safe("八字蛋糕訂單")
    if ws is None:
        return None
    rows = ws.get_all_values()
    data_rows = rows[1:] if len(rows) > 1 else []
    if not (1 <= row_idx <= len(data_rows)):
        return None
    return _bazi_inbox_row_to_dict(row_idx, data_rows[row_idx - 1])


def get_inbox_tea_row(row_idx: int) -> dict:
    """取單一下午茶訂單列（1-based 資料列序）；找不到回 None。"""
    ws = _get_sheet_safe("下午茶訂單")
    if ws is None:
        return None
    rows = ws.get_all_values()
    data_rows = rows[1:] if len(rows) > 1 else []
    if not (1 <= row_idx <= len(data_rows)):
        return None
    return _tea_inbox_row_to_dict(row_idx, data_rows[row_idx - 1])


def mark_inbox_bazi_converted(row_idx: int, mark: str):
    """標記八字蛋糕訂單該列「已轉入」欄（row_idx 為 1-based 資料列序）。
    Sheet 實體列號 = row_idx + 1（跳過標題列）。必須在目標寫入成功後才呼叫。"""
    ws = _get_sheet("八字蛋糕訂單")
    ws.update_cell(row_idx + 1, _BAZI_CONVERTED_COL, mark)


def mark_inbox_tea_converted(row_idx: int, mark: str):
    """標記下午茶訂單該列「已轉入」欄（row_idx 為 1-based 資料列序）。"""
    ws = _get_sheet("下午茶訂單")
    ws.update_cell(row_idx + 1, _TEA_CONVERTED_COL, mark)


def add_tea_manage_order(tea: dict, status: str = None) -> str:
    """把一筆下午茶單寫入「下午茶管理」tab，狀態固定 TEA_DEFAULT_STATUS。
    回傳寫入的狀態值。下午茶一律不得寫入 orders。"""
    if status is None:
        status = TEA_DEFAULT_STATUS
    ws = _get_sheet(TEA_MANAGE_TAB)
    ws.append_row([
        tea.get("created_at", ""),
        tea.get("company", ""),
        tea.get("contact", ""),
        tea.get("phone", ""),
        tea.get("items", ""),
        tea.get("event_date", ""),
        tea.get("total_qty", ""),
        tea.get("notes", ""),
        status,
    ], value_input_option="USER_ENTERED")
    return status


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
    _get_sheet("orders")  # trigger lazy init

    existing = [ws.title for ws in _sh.worksheets()]

    if "orders" not in existing:
        ws = _sh.add_worksheet(title="orders", rows=1000, cols=18)
        ws.append_row(ORDERS_HEADER)

    if "ingredients" not in existing:
        ws = _sh.add_worksheet(title="ingredients", rows=500, cols=9)
        ws.append_row(INGREDIENTS_HEADER)

    # 確保標題列存在
    for tab, header in [("orders", ORDERS_HEADER), ("ingredients", INGREDIENTS_HEADER)]:
        ws = _get_sheet(tab)
        first = ws.row_values(1)
        if not first:
            ws.insert_row(header, 1)

    print("✅ Google Sheets 初始化完成")
