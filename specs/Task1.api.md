# Task1 Phase 2 — Backend 函式介面 / 路由說明（給 frontend）

> backend 完成於 2026-06-13。Phase 2 後端已落地，inbox.html 為功能完整的基本版，
> frontend 可在此基礎上調整 UX（視覺、互動細節）。**勿改後端路由名 / 表單 field 名 / db 函式簽名**。

## 新增後台路由（admin.py）

| 路由 | 方法 | 用途 | 表單 field |
|------|------|------|-----------|
| `/admin/inbox` | GET | 前台訂單收件匣（八字 / 下午茶分區，只列「已轉入」為空的待轉單） | — |
| `/admin/inbox/convert` | POST | 八字蛋糕單 → orders（複用 create_order） | `row`（來源資料列序，1-based）、`wish_main`（**必填**）、`wish_sub`（選填） |
| `/admin/inbox/convert_tea` | POST | 下午茶單 → 「下午茶管理」tab（狀態固定「待處理」） | `row`（來源資料列序，1-based） |

- 轉單端點處理後一律 **redirect 回 `/admin/inbox`**，帶 query string：`msg`（`ok`/`warn`/`err`）+ `detail`（訊息文字）。
- inbox.html 已用 `flash_status` / `flash_detail` 兩個模板變數呈現轉單結果（template context 由 `admin_inbox` 注入）。
- `/admin/order/<order_id>` 路由型別已由 `<int:order_id>` 改為 `<order_id>`（字串），以接受日期前綴 id（如 `20260613-01`）。前端產生此連結時直接帶字串 id 即可。

## inbox.html 的 template context（frontend 改版時可用的變數）

- `bazi_orders`：list[dict]，每筆 key：`row, created_at, name, phone, birthdate, birth_hour, product, quantity, pickup_date, delivery, notes, converted`
- `tea_orders`：list[dict]，每筆 key：`row, created_at, company, contact, phone, items, event_date, total_qty, notes, converted`
- `err`：讀取收件匣失敗訊息（None 表正常）
- `flash_status` / `flash_detail`：轉單結果（由 redirect query 帶回）

## 業務規則（frontend 改 UX 時不可破壞）

1. 八字轉單表單「心願主項」**必填**（前端 + 後端雙重把關，後端缺值會擋下並回 err）。
2. 八字轉單 → orders；下午茶轉單 → 下午茶管理 tab。**兩條互斥**，UI 不可讓下午茶單走八字轉單端點。
3. 轉單成功後該單即從收件匣消失（後端標記來源「已轉入」欄，下次 GET 不再列出）。

## db.py 變更摘要（frontend 不直接呼叫，僅供理解）

- `create_order(...)` 回傳型別 **由 int 改為 str**（D2 日期前綴 id `YYYYMMDD-NN`），新增選填參數 `created_at, product, quantity, pickup_date, delivery`。
- 新增收件匣資料函式：`load_inbox_bazi / load_inbox_tea / get_inbox_bazi_row / get_inbox_tea_row / mark_inbox_*_converted / add_tea_manage_order`。
- orders 擴至 18 欄（尾端加 品項/數量/取貨日期/外送）。

## Sheet 結構調整（已由 backend 程式執行完成，frontend 無需處理）

- 「八字蛋糕訂單」「下午茶訂單」兩 tab 尾端各加「已轉入」欄。
- 新建「下午茶管理」tab。
- orders 標題列已改為新版 18 欄。
