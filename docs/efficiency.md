# efficiency.md — 踩坑經驗與效率規則
> 最後更新：2026-03-11 (V35.9.6)
> 性質：本檔為活文件，每次踩坑後即時追加。
> 上位法參照：`docs/constitution_honest_observer.md`
> 靜默治理參照：`skills/silence_governance.skill`

---

## 核心定錨原則

### P-0：唯一輸出點
```
bridge/official_core/outputs/<topic>/
```
- 舊路徑 `shorts_factory_react/outputs/` 已廢棄，永不使用
- 舊路徑 `bridge/outputs/` 已廢棄，永不使用
- 所有 pipeline 產物只能落在 `bridge/official_core/outputs/`

### P-1：唯一 .env 點
```
bridge/official_core/.env
```
- 根目錄 `.env` 已刪除
- `bridge/.env` 已刪除
- **任何新 API key 只能寫入 `bridge/official_core/.env`**

---

## 踩坑紀錄

### [PITFALL-001] API Key 遺失導致 Phase 1 崩潰
- **症狀**：`Error: API key must be set when using the Gemini API.` — 程式在 PHASE 1 就崩潰
- **根因**：`bridge/official_core/.env` 不存在或 GEMINI_API_KEY 未設定
- **修復**：確認 `.env` 存在且包含以下三金鑰
  ```
  OPENAI_API_KEY=...
  REPLICATE_API_TOKEN=...
  GEMINI_API_KEY=...
  ```
- **預防**：執行前先 `cat bridge/official_core/.env | grep -c "KEY\|TOKEN"` 確認輸出為 3

---

### [PITFALL-002] .env 單引號導致金鑰解析錯誤
- **症狀**：`.env` 看起來正確，但 API 回傳 401 Unauthorized
- **根因**：`echo "GEMINI_API_KEY='AIza...'"` 寫入時包含單引號，dotenv 將引號納入值
- **正確格式**：
  ```
  GEMINI_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXX
  ```
  （無引號、無空格）
- **預防**：用 Write 工具直接寫入，避免 echo 命令的 shell 引號行為

---

### [PITFALL-003] 舊輸出路徑與新路徑混用
- **症狀**：執行 pipeline 後找不到輸出檔；或兩個路徑都有同名 topic 資料夾造成混亂
- **根因**：V35.7 之前 pipeline 輸出到 `outputs/`，V35.7 之後改為 `bridge/official_core/outputs/`
- **修復**：手動刪除 `outputs/<topic>/` 舊資料夾，確認只剩新路徑
- **預防**：每次執行前先 `ls bridge/official_core/outputs/` 確認輸出目錄正確

---

### [PITFALL-004] --force-overwrite 不強制重新生成圖片
- **症狀**：加了 `--force-overwrite` 但 scene_002–012 仍顯示 `exists — skipping`
- **根因**：`bridge_adapter.ts` 的 skip 邏輯以「檔案是否存在」為判斷，不受旗標影響
- **修復**：手動刪除目標 topic 的 outputs 資料夾再執行
- **預防**：需要完整重跑時，先 `rm -rf bridge/official_core/outputs/<topic>/`

---

## 標準執行流程（SOP）

### 執行前 Checklist
```bash
# 1. 確認 .env 三金鑰存在
grep -c "OPENAI_API_KEY\|REPLICATE_API_TOKEN\|GEMINI_API_KEY" bridge/official_core/.env
# → 應輸出 3

# 2. 若需全量重跑，先清空舊輸出
rm -rf bridge/official_core/outputs/<topic>/

# 3. 確認工作目錄正確
cd bridge/official_core
```

### 標準執行指令
```bash
# 方式 A：npm script（推薦）
npm run gen "<topic>"

# 方式 B：直接 tsx
npx tsx src/cli.ts "<topic>" --full-pipeline --skip-veo --vo-engine edge-tts --image-model mixed --force-overwrite
```

### 執行後驗證
```bash
ls bridge/official_core/outputs/<topic>/
# 應包含：cover.png, scene_001.png ... scene_NNN.png, draft_vo.srt, subtitles.srt, seo.txt, runbook.md, final_manifest.json
```

---

## 絕對路徑鎖定（強制執行）

任何 AI 對話、任何 script，都必須使用以下絕對路徑，禁止相對路徑或舊路徑：

| 項目 | 鎖定路徑 |
|---|---|
| 輸出目錄 | `C:/Projects/shorts_factory_react/bridge/official_core/outputs/` |
| 環境變數 | `C:/Projects/shorts_factory_react/bridge/official_core/.env` |
| CLI 入口 | `C:/Projects/shorts_factory_react/bridge/official_core/src/cli.ts` |
| 憲法文件 | `C:/Projects/shorts_factory_react/docs/constitution_honest_observer.md` |
| 靜默治理 | `C:/Projects/shorts_factory_react/skills/silence_governance.skill` |

**違反路徑鎖定 = 對話浪費**。執行前必先確認路徑，不得假設。

---

## 技能狀態（V35.9.6 更新）

| 技能 | 狀態 | 位置 |
|---|---|---|
| HONEST OBSERVER CONSTITUTION | ✅ 已建立 | `docs/constitution_honest_observer.md` |
| Silence 上位法 + Token 節流 | ✅ 已建立 | `skills/silence_governance.skill` |
| Prompt Agent 規格 | ⚠️ 部分（分散在 cli.ts / bridge_adapter.ts） | — |
| 踩坑自動追加 Hook | ❌ 尚未自動化 | 手動維護本檔 |
