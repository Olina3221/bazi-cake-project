# 萊點（Laiten）八字蛋糕系統 — 概覽

> 私人系統，屬於 Olina 個人，離職時帶走。

## 系統定位
八字蛋糕訂單管理系統。師傅透過後台管理訂單、食材、八字分析與文案。
技術架構：Flask + Google Sheets，Claude API 負責 AI 分析。

## 兩個入口

| 入口 | 路徑 | Port | 說明 |
|------|------|------|------|
| 後台 | `back/admin.py` | 5001 | 師傅日常操作，啟動用 `開啟後台.bat` |
| 前台 | `laiten_public/index.html` | — | 客戶入口，Netlify 靜態部署 |

## 兩張 Google Sheets

| 用途 | Sheet ID |
|------|----------|
| 前台（品牌設定、產品、訂單） | `1xtuKyod3lOQUmp_D10AhDDGSD4bVxG3TmZudO2S9AMo` |
| 後台（orders、ingredients、monthly） | `1oYJ7qO4E40aw1RVip-O3NM6X_U-mYxGT1NIn_YvpW2E` |

## Claude 模型設定
- 八字主分析：`claude-opus-4-8`
- JSON 萃取 / 文案 / 食材分類：`claude-sonnet-4-6`

## 憑證
`service_account.json` 在本機（`.gitignore` 內，不進 git）

## 功能模組狀態

| 模組 | 狀態 |
|------|------|
| 八字分析 + 蛋糕設計 | 上線中 |
| 訂單管理 | 上線中 |
| 食材管理 | 上線中 |
| 文案生成 | 上線中 |
| 銷售 / 訂單 / 金流系統 | 規劃中 |
