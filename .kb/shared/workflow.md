# Sentinel 協作流程（信號流唯一完整定義）

> 本檔是 pipeline 信號流的**唯一完整定義**。CLAUDE.md 與各 agent 設定只放摘要，
> 流程細節以本檔為準。修改流程時只改這裡。

五個 agent（pm / sa / backend / frontend / qa）透過 sentinel 檔案交接任務。
所有 sentinel 檔案統一放在 `specs/` 目錄下；除 `.impact.md` 與 `.qa_failed.md`
有內容外，其餘為空白檔。

## 信號流

```
PM 建立 specs/TaskN.ready
  → SA 影響分析（讀 specs/SYSTEM_MAP.md），輸出 TaskN.impact.md，
    刪 .ready，建 TaskN.sa_done
  → Backend 實作（觸發條件是 .sa_done，絕不是 .ready），刪 .sa_done：
      - spec 涉及 UI：建 TaskN.backend_done → Frontend 實作，
        刪 .backend_done，建 TaskN.done
      - spec 純後端：直接建 TaskN.done
  → QA 測試，刪 .done：
      - 通過：建 TaskN.tested → 回報 PM 驗收
      - 失敗：建 TaskN.qa_failed.md（標明歸屬 backend/frontend）
        → 負責 agent 修復，刪 .qa_failed.md，重建 TaskN.done → QA 完整重測
```

## 各階段職責（萊點專案）

| 階段 | 觸發信號 | 工作 | 完成動作 |
|------|---------|------|---------|
| **PM** | Olina 的需求 | 撰寫/更新 spec（`overview.md` 與 `specs/`） | 建 `TaskN.ready` |
| **SA** | `TaskN.ready` | 比對 `specs/SYSTEM_MAP.md` 做影響分析，輸出 `TaskN.impact.md` | 刪 `.ready`，建 `TaskN.sa_done` |
| **Backend** | `TaskN.sa_done`（**絕不是 `.ready`**） | Flask 路由（`back/`）、Google Sheets 讀寫、AI 分析（八字/文案）、維護 qa_smoke_test.py | 刪 `.sa_done`；涉及 UI → 建 `TaskN.backend_done`；純後端 → 直接建 `TaskN.done` |
| **Frontend** | `TaskN.backend_done` | 後台模板（`templates/`）與前台靜態頁（`laiten_public/`，Netlify 部署），遵循 `DESIGN.md` 品牌規範 | 刪 `.backend_done`，建 `TaskN.done` |
| **QA** | `TaskN.done` | 全系統迴歸冒煙 + 本次 spec 冒煙 + Sheets 寫入驗證（不可污染正式資料） | 刪 `.done`；通過 → 建 `TaskN.tested` 回報 PM 驗收；失敗 → 建 `TaskN.qa_failed.md`（標明歸屬） |
| **修復迴圈** | `TaskN.qa_failed.md` | 歸屬的 agent（backend 或 frontend）修復 | 刪 `.qa_failed.md`，重建 `TaskN.done` → QA **完整重測** |

## 信號檔一覽

| 信號檔 | 建立者 | 消費者（刪除者） | 意義 |
|--------|--------|----------------|------|
| `TaskN.ready` | pm | sa | spec 完成，待影響分析 |
| `TaskN.sa_done` | sa | backend | 影響分析完成，backend 可開工 |
| `TaskN.backend_done` | backend | frontend | 後端完成，待 UI 實作（僅含 UI 的任務） |
| `TaskN.done` | backend 或 frontend | qa | 實作完成，待測試 |
| `TaskN.tested` | qa | pm（驗收後刪除） | 測試通過，待 PM 驗收 |
| `TaskN.qa_failed.md` | qa | 歸屬的 backend/frontend | 測試失敗，含問題描述與歸屬 |
| `TaskN.impact.md` | sa | （保留，不刪） | 影響分析報告 |
