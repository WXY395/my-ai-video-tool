# V35.12.0 六將分工協議 — The Six-Pillar Protocol

> 版本：V35.12.0 | 生效日期：2026-03-12
> 任何新任務啟動前，所有代理必須先讀取本文件確認角色邊界。

---

## 第一柱：Google Antigravity（IDE 環境）

**角色**：Agent-first 開發平台 / 資源管理中心

**職責**：
- 跨代理協作環境的提供與協調
- 任務資源調度（GPU、API 配額追蹤）
- 可視化監控面板（任務進度、冷卻狀態）

**禁止越界**：
- 不直接執行終端指令
- 不修改 bridge/official_core/ 以下任何檔案

---

## 第二柱：Claude Code（本地執行指揮官）

**角色**：本地終端執行代理

**職責**：
- 終端機操作唯一入口：`npx tsx src/cli.ts "[主題名稱]"`（於 bridge/official_core/ 下執行）
- 路徑鎖定：所有輸出必須在 `bridge/official_core/outputs/[主題名稱]/`
- `.env` 金鑰巡檢（OPENAI / GEMINI / REPLICATE 三鍵必須全數存在）
- Git 存檔：每幕完成後執行 `git commit`
- Replicate Flux 冷卻監控：每 5 張觸發 120s 等待，不得跳過

**禁止越界**：
- 不自行創作劇本（語意層交由 OpenAI）
- 不修改 `services/gemini.ts`（神聖文件，NEVER MODIFY）
- 不產生輸出路徑以外的冗餘資料夾

---

## 第三柱：OpenAI（總導演 / 審計師）

**角色**：核心語意與物理大腦

**職責**：
- 「荒謬物理精算」：每幕必須簽發具體物理參數包（例：倒角 47°、彈跳高度 15cm、重力係數偏移 0.03）
- 反諷對白優化：台詞零情感，僅保留物理數值與荒謬邏輯
- 劇本審計：生成前簽發，不通過則阻斷生圖

**硬性規則**：
- 所有劇本生成前，必須由 OpenAI 先簽發物理參數包
- 禁止使用「驚訝」「啟發」「震撼」等情感詞彙
- absurd_logic.skill 適用於所有場景描述

**禁止越界**：
- 不直接呼叫 API（交由 Claude Code 執行）
- 不修改 SRT 時間軸（交由 Gemini）

---

## 第四柱：Gemini（架構師 / 工廠）

**角色**：架構與門面生成

**職責**：
- SSOT 大綱生成（目標 18 幕；prompt 中須明確注入 `"Generate exactly 18 chapters"`）
- SRT 時間軸處理（draft_vo.srt / subtitles.srt）
- Cover 生成：Nano Banana 2（gemini-3.1-flash-image-preview + aspectRatio 9:16 + imageSize 1K）
- Scene 001 生成：gemini-2.5-flash-image（神聖路徑，不可替換）

**禁止越界**：
- Scene 002 以後不得使用 Gemini 生圖（交由 Flux-Schnell）
- 不自行決定章節數量（必須接受 OpenAI 的幕數規格）

---

## 第五柱：Flux-Schnell（首席畫師）

**角色**：批量場景渲染

**職責**：
- Scene 002 以後所有場景圖像生成（via Replicate black-forest-labs/flux-schnell）
- 嚴格執行 OpenAI 提供的物理參數（倒角、材質、尺寸）
- 雙重無文字屏障（FLUX_NO_TEXT 前綴 × 2）
- 每 5 張暫停 120s 冷卻

**禁止越界**：
- 禁止隨機發揮（所有 prompt 必須基於 OpenAI 簽發的物理參數包）
- 禁止生成含文字的圖像

---

## 執行硬性規範

### 唯一入口
```bash
cd bridge/official_core
npx tsx src/cli.ts "[主題名稱]"
```

### 輸出路徑唯一性
```
bridge/official_core/outputs/[主題名稱]/
├── cover.png
├── scene_001.png … scene_NNN.png
├── draft_vo.srt
├── subtitles.srt
├── seo.txt
├── runbook.md
└── final_manifest.json
```

### 生圖前置檢查清單
- [ ] OpenAI 物理參數包已簽發
- [ ] `.env` 三鍵（OPENAI / GEMINI / REPLICATE）巡檢通過
- [ ] 輸出目錄已建立（mkdirSync recursive）
- [ ] SSOT 幕數 = 18（或已記錄例外原因）

### Git 節律
每幕圖像落地後執行：
```bash
git add bridge/official_core/outputs/[主題名稱]/
git commit -m "feat([主題名稱]): scene_NNN 落地"
```

---

## 越界處罰規則

| 違規行為 | 處置 |
|----------|------|
| 劇本缺乏物理數值即啟動生圖 | 立即中止，回退至 OpenAI 精算 |
| 輸出至非鎖定路徑 | 刪除冗餘資料夾，重新執行 |
| 修改 services/gemini.ts | 強制 git checkout 還原 |
| 跳過 Flux 冷卻 120s | 任務標記為違規，補冷卻後繼續 |

---

*本文件為 V35.12.0 六將分工協議正本，任何更新須標記版本號與日期。*
