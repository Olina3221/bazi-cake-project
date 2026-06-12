"""
migrate_sheets.py — Task1 Phase 1 Sheet 合併遷移腳本（可重跑 / 冪等）
=====================================================================
把前台 Sheet「Laiten 系統主檔」的四個 tab 複製進後台 Sheet「八字蛋糕資料庫」，
合併為單一私有 Sheet。

安全規則（絕對遵守）：
  1. 前台 Sheet（1xtuK…）只讀，絕不寫入、絕不刪除任何東西。
  2. 後台 Sheet（1oYJ7…）只動 MIGRATE_TABS 四個 tab；
     orders / ingredients / monthly 受保護，任何路徑都不可觸碰。
  3. 可重跑：目標 tab 已存在時清空重寫（重新同步最新資料）。
     正式切換（GAS 改指向）由 Olina 手動執行，切換當下應再跑一次本腳本
     同步最後一刻的訂單資料。

執行：python migrate_sheets.py            （遷移 + 驗證 + 重新生成 products.js）
      python migrate_sheets.py --no-products （只遷移，不生成 products.js）

需求：專案根目錄有 service_account.json
      （service_account 對前台 Sheet 可讀、對後台 Sheet 可寫，SA 2026-06-13 已實測）
"""

import sys
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

PROJECT_ROOT = Path(__file__).parent

FRONT_SHEET_ID = "1xtuKyod3lOQUmp_D10AhDDGSD4bVxG3TmZudO2S9AMo"  # 前台（只讀）
BACK_SHEET_ID = "1oYJ7qO4E40aw1RVip-O3NM6X_U-mYxGT1NIn_YvpW2E"   # 後台（寫入目標）

MIGRATE_TABS = ["品牌設定", "產品主檔", "八字蛋糕訂單", "下午茶訂單"]
PROTECTED_TABS = {"orders", "ingredients", "monthly"}  # 後台既有 tab，絕不觸碰

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _ensure_not_protected(tab: str):
    """防呆：任何寫入動作前必經此檢查"""
    if tab in PROTECTED_TABS:
        raise RuntimeError(f"受保護 tab 不可寫入：{tab}（orders/ingredients/monthly 絕不觸碰）")


def _norm_rows(rows: list) -> list:
    """正規化列資料供比對：去掉每列尾端空字串、去掉尾端全空列"""
    out = []
    for r in rows:
        r = list(r)
        while r and (r[-1] == "" or r[-1] is None):
            r.pop()
        out.append(tuple(r))
    while out and not out[-1]:
        out.pop()
    return out


def _client():
    creds = Credentials.from_service_account_file(
        str(PROJECT_ROOT / "service_account.json"), scopes=SCOPES
    )
    return gspread.authorize(creds)


def migrate() -> list:
    """執行遷移，回傳逐 tab 報告 list[dict]；任何 tab 驗證失敗即 raise"""
    assert not (set(MIGRATE_TABS) & PROTECTED_TABS), "遷移清單不可包含受保護 tab"

    gc = _client()
    front = gc.open_by_key(FRONT_SHEET_ID)
    back = gc.open_by_key(BACK_SHEET_ID)

    back_titles = {w.title for w in back.worksheets()}
    missing_protected = PROTECTED_TABS - back_titles
    if missing_protected:
        raise RuntimeError(
            f"後台 Sheet 缺少既有 tab {sorted(missing_protected)}，"
            f"可能開錯 Sheet，中止以免誤寫。"
        )

    report = []
    for tab in MIGRATE_TABS:
        _ensure_not_protected(tab)

        src_rows = front.worksheet(tab).get_all_values()
        n_rows = len(src_rows)
        n_cols = max((len(r) for r in src_rows), default=0)

        if tab in back_titles:
            ws = back.worksheet(tab)
            _ensure_not_protected(ws.title)
            ws.clear()
            action = "重寫（已存在，重新同步）"
        else:
            ws = back.add_worksheet(
                title=tab,
                rows=max(n_rows + 200, 500),
                cols=max(n_cols + 2, 12),
            )
            action = "新建"

        if src_rows:
            ws.update(range_name="A1", values=src_rows, value_input_option="RAW")

        # 逐格驗證：讀回後台，與前台來源比對
        dst_rows = ws.get_all_values()
        identical = _norm_rows(src_rows) == _norm_rows(dst_rows)
        report.append({
            "tab": tab,
            "action": action,
            "front_rows": n_rows,
            "back_rows": len(dst_rows),
            "identical": identical,
        })
        if not identical:
            raise RuntimeError(f"tab「{tab}」複製後比對不一致，請人工檢查（前台資料未動）")

    return report


def gen_products():
    """從合併後 Sheet 重新生成 laiten_public/products.js（與 /admin/laiten/sync 同結構）。

    走 gspread（service_account），不依賴 gws CLI——gws OAuth 失效時仍可生成。
    不做 git add/commit/push（推版由 /admin/laiten/sync 或 Olina 手動）。
    """
    import json
    sys.path.insert(0, str(PROJECT_ROOT / "back"))
    import admin  # _parse_laiten 是 products.js 資料結構的唯一來源

    gc = _client()
    back = gc.open_by_key(BACK_SHEET_ID)
    brand_rows = back.worksheet("品牌設定").get_all_values()[1:]   # 跳過標題列（= A2 起）
    prod_rows = back.worksheet("產品主檔").get_all_values()[1:]

    data = admin._parse_laiten(brand_rows, prod_rows)
    if not any(line["products"] for line in data["lines"]):
        raise RuntimeError("產品主檔讀回為空，中止生成（不可產出空的 products.js）")

    out = PROJECT_ROOT / "laiten_public" / "products.js"
    out.write_text(
        "const PRODUCTS_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    return out, data


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=== 遷移：前台 Sheet 四 tab → 後台 Sheet ===")
    report = migrate()
    for r in report:
        print(f"[{'OK' if r['identical'] else 'FAIL'}] {r['tab']}: {r['action']}，"
              f"前台 {r['front_rows']} 列 → 後台 {r['back_rows']} 列，"
              f"逐格比對 {'一致' if r['identical'] else '不一致'}")

    if "--no-products" not in sys.argv:
        print("\n=== 重新生成 laiten_public/products.js（gspread，不經 gws / 不 push）===")
        out, data = gen_products()
        n_prod = sum(len(l["products"]) for l in data["lines"])
        print(f"[OK] {out}（{len(data['lines'])} 條產品線、共 {n_prod} 個產品）")

    print("\n完成。前台 Sheet 未做任何變更；後台 orders/ingredients/monthly 未觸碰。")


if __name__ == "__main__":
    main()
