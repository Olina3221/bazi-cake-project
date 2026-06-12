# 萊點（Laiten）規格文件總索引

> 本檔由 PM 維護，是所有規格性質文件的入口。文件留在原位置，本索引只記錄位置與狀態。
> 盤點日期：2026-06-13。本次為純盤點，未改寫任何既有文件。

## 規格 / 設計文件

| 文件 | 位置 | 說明 | 狀態 |
|------|------|------|------|
| 系統概覽 | `overview.md` | 系統定位、入口、兩張 Sheet、模組狀態表 | 既有，與程式現況有落差（見下方落差清單） |
| 品牌設計規範 | `DESIGN.md` | 色彩、字體、元件、排版、風格守則 | 既有，僅描述前台視覺，未涵蓋後台 UI |
| 主規則 | `CLAUDE.md` | Orchestrator 角色、pipeline 摘要、職責邊界 | 既有 |
| 信號流定義 | `.kb/shared/workflow.md` | pipeline v2 信號流唯一完整定義 | 既有 |
| 系統依賴地圖 | `specs/SYSTEM_MAP.md` | CLAUDE.md 引用，供 SA 影響分析使用 | **尚未建立**（待 SA 首次分析時產出） |

## 程式現況對照（非規格文件，盤點時記錄，供查閱）

| 區塊 | 檔案 | 角色 |
|------|------|------|
| 後台主程式 | `back/admin.py` | Flask，port 5001，訂單/食材/八字分析/文案/Laiten 品牌與產品管理 |
| Sheets 存取層 | `db.py` | orders / ingredients 兩張表的讀寫（後台 Sheet） |
| 前台靜態頁 | `laiten_public/index.html` + `products.js` | Netlify 部署，八字蛋糕 + 下午茶詢問表單 |
| 前台訂單接收 | `gas_order_handler.js` | Google Apps Script，接收前台表單寫入前台 Sheet 並寄信 |
| 後台模板 | `templates/admin/*.html` | index/detail/print/ingredients/laiten_* |

## 規格涵蓋缺口（目前無對應 spec 文件的模組）

下列功能已在程式中實作或半實作，但 `overview.md` 未列入模組表、亦無獨立 spec：

- Laiten 品牌設定管理（`/admin/laiten/brand`）
- Laiten 產品主檔管理（`/admin/laiten/products/<line_id>`）
- 前台圖片管理（`/admin/laiten/images`）
- 前台同步 / 推版（`/admin/laiten/sync`，產生 products.js 並 git 推送）
- 前台詢問表單 → GAS → 前台 Sheet 的訂單流（與後台 orders 表為兩套獨立資料）
- 列印小卡（`/admin/print`）

> 這些缺口僅做記錄，不在本次盤點處理範圍。是否補寫 spec 由 Olina 決定。
