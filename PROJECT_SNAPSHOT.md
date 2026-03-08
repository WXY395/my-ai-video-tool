# PROJECT_SNAPSHOT.md
> Shorts Factory React — 開發環境快照
> Generated: 2026-03-05

---

## 1. 專案架構

### 目錄結構

```
shorts_factory_react/
├── backend/                        # FastAPI 後端
│   ├── main.py                     # 應用程式入口，CORS、路由掛載
│   ├── requirements.txt            # Python 依賴
│   ├── .env / .env.example         # 環境變數
│   ├── models/
│   │   └── schemas.py              # Pydantic 資料模型（全部型別定義）
│   ├── routers/
│   │   ├── observation.py          # 核心路由：腳本生成、SSE串流、成本估算
│   │   └── image.py                # 圖片生成路由（keyframe 單張）
│   └── services/
│       ├── observation_service.py  # Gemini 腳本生成邏輯、prompt 工程
│       ├── image_service.py        # Replicate FLUX 圖片生成、prompt 優化
│       └── cover_generator.py      # 封面生成輔助（已整合至 observation.py）
│
├── frontend/                       # React 前端
│   ├── index.html                  # 入口 HTML，Tailwind CDN、字型
│   ├── App.tsx                     # 主應用（所有狀態管理、UI 骨架）
│   ├── types.ts                    # TypeScript 型別定義
│   ├── components/
│   │   ├── ObservationUnitCard.tsx # 單元卡片（圖片/旁白/字幕/SEO/Veo/燈箱）
│   │   └── ObservationNotesInput.tsx # 筆記輸入區
│   ├── services/
│   │   ├── geminiService.ts        # API 呼叫（REST + SSE 串流）
│   │   └── packExportService.ts    # ZIP 素材包組裝（pack_meta_v1）
│   └── config/
│       └── pacingProfiles.ts       # 三種步調 Profile + UnitPlan 工具函式
│
└── docs/
    ├── INSTALLATION_GUIDE.md
    ├── UPGRADE_GUIDE.md
    ├── FEATURES_DEMO.md
    └── constitution_micro_wonder_v2.md
```

### 技術棧

| 層級 | 技術 | 版本 |
|------|------|------|
| **前端框架** | React | 19.2.4 |
| **語言** | TypeScript | ~5.8.2 |
| **建構工具** | Vite | ^6.2.0 |
| **CSS** | Tailwind CSS | CDN（Play CDN） |
| **後端框架** | FastAPI | 0.109.0 |
| **後端伺服器** | uvicorn[standard] | 0.27.0 |
| **資料驗證** | Pydantic | 2.5.3 |
| **圖示** | lucide-react | ^0.563.0 |
| **Toast 通知** | sonner | 2.0.7 |
| **圖片燈箱** | yet-another-react-lightbox | 3.29.1 |
| **拖曳排序** | @dnd-kit/core + sortable | 6.3.1 / 10.0.0 |
| **SSE（後端）** | sse-starlette | 3.3.2 |
| **ZIP 封裝** | jszip | ^3.10.1 |

---

## 2. API 規格

### Base URL
```
http://127.0.0.1:8000
```

---

### `POST /api/observation/generate`
**功能**：生成觀測腳本單元 + 封面圖（一次性 JSON 回應）

**Request Body**
```json
{
  "rawInput": "string",            // 主題或觀測筆記（alias: notes）
  "unitCount": 3,                  // 目標單元數（alias: target_units, ge=1 le=50）
  "video_mode": "shorts",          // "shorts" | "medium" | "long"
  "aspect_ratio": "9:16",          // "9:16" | "16:9" | "1:1"
  "duration_minutes": null         // 目標時長（分鐘），長片用
}
```

**Response**
```json
{
  "success": true,
  "units": [ /* ObservationUnit[] */ ],
  "video_mode": "shorts",
  "aspect_ratio": "9:16",
  "cost_estimate": {
    "image_count": 4,
    "cost_per_image": 0.003,
    "total_cost": 0.034,
    "model_used": "flux-schnell(KF) + flux-dev(cover)"
  },
  "metadata": {
    "cover_url": "https://...",
    "production_notes": { ... }
  },
  "generated_at": "2026-03-05T..."
}
```

---

### `POST /api/observation/generate-stream` ⚡ SSE
**功能**：與 `/generate` 相同邏輯，以 Server-Sent Events 即時串流進度

**Request Body**：同 `/generate`

**SSE 事件流**
```
data: {"type": "step",  "message": "解析輸入中"}
data: {"type": "step",  "message": "Gemini 腳本生成中…"}
data: {"type": "units", "units": [...], "cost_estimate": {...}, "video_mode": "shorts", "aspect_ratio": "9:16"}
data: {"type": "step",  "message": "封面生成中…"}
data: {"type": "cover", "cover_url": "https://..."}
data: {"type": "done",  "production_notes": {...}, "cost_estimate": {...}}
data: {"type": "error", "message": "..."}     // 僅失敗時
```

**前端連線方式**：`fetch + ReadableStream`（非 `EventSource`，因為需 POST）

---

### `POST /api/observation/estimate-cost`
**功能**：預估成本（不實際生成）

**Request Body**：同 `/generate`

**Response**
```json
{
  "success": true,
  "video_mode": "shorts",
  "aspect_ratio": "9:16",
  "keyframe_count": 3,
  "cost_estimate": {
    "image_count": 4,
    "price_per_image": 0.003,
    "kf_cost": 0.009,
    "cover_cost": 0.025,
    "total_cost": 0.034,
    "model_used": "flux-schnell(KF×3) + flux-dev(cover×1)",
    "currency": "USD"
  }
}
```

---

### `POST /api/image/generate`
**功能**：生成單張 keyframe 圖片（由前端按需觸發）

**Request Body**
```json
{
  "prompt": "string",               // 英文圖片提示詞
  "negative_prompt": "string",      // 負面提示詞（FLUX 靜默忽略，保留供切換模型）
  "aspect_ratio": "9:16"            // "9:16" | "16:9" | "1:1"
}
```

**Response**
```json
{
  "success": true,
  "image_url": "https://replicate.delivery/..."
}
```

---

### `GET /api/observation/modes`
返回可用的 video_modes、aspect_ratios、models（含定價）

### `GET /api/observation/health`
回傳服務健康狀態

---

### ObservationUnit 結構（核心資料模型）

```typescript
{
  id: string,                  // "KF001a" 等
  phenomenon: string,          // 現象描述（主標題，≤35字）
  mechanism: string,           // 機制說明（副標題，≤70字）
  voice_over_zh: string,       // 中文旁白（TTS 7字/秒，≤unit秒×7字）
  subtitle_zh: string,         // 字幕（≤8字，旁白的吐槽或補充，非縮短版）
  visual_description: string,  // 視覺場景描述
  image_prompt: {
    prompt: string,            // FLUX prompt（英文，主體名詞開頭）
    negative_prompt: string
  },
  emotional_tone: string,
  start_timecode: string,      // "00:00:00:00"
  duration_seconds: number,    // 秒數（ge=1, le=120）
  camera_mode: string,         // "CLOSE_UP" 等
  motion_guidance: {
    effect: "ken_burns"|"zoom_in"|"zoom_out"|"pan_left"|"pan_right"|"static",
    duration_seconds: number,
    transition_to_next: string
  } | null,
  unit_role: "定位"|"解構"|"影響"|"content",
  hook_technique: "reverse_question"|"shock_fact"|"forbidden_knowledge"|"visual_paradox"|"incomplete_loop" | null,
  seo_keywords: string[],
  interaction_trigger: "comment_bait"|"share_trigger"|"replay_hook"|"save_reminder" | null,
  interaction_bait_text: string | null,  // 影響幕互動誘餌文字（≤30字）
  veo_prompt: string | null,
  veo_recommended: boolean,
  // 前端 UI 狀態
  imageUrl: string,
  isGeneratingImage: boolean,
  imageStatus: "pending"|"generating"|"complete"|"error"
}
```

---

## 3. UI 規範

### 色彩系統

| 變數名 / Tailwind | 色碼 | 用途 |
|-------------------|------|------|
| `--color-bg` / `zinc-950` | `#09090b` | 全局背景 |
| `--color-surface` | `#121214` | 卡片/面板底色 |
| `--color-border` / `zinc-800` | `#27272a` | 邊框 |
| `--color-accent` / `emerald-500` | `#10b981` | 主要強調色（狀態指示、按鈕、成功） |
| `orange-400/500` | — | Hook/定位幕 badge |
| `yellow-400/500` | — | 解構幕 badge |
| `emerald-400/500` | — | 影響幕 badge / 正面狀態 |
| `violet-400/500` | — | Veo 推薦標記 |
| `blue-400/500` | — | Motion 效果標記 / 比例選擇鈕 |
| `rose-500` | — | 錯誤/FATAL |
| `zinc-400` ~ `zinc-700` | — | 次要文字、標籤、圖示 |
| `amber-400` | — | 字幕密度 dense 提示 |

### 字型

| 用途 | 字型 | 載入方式 |
|------|------|---------|
| 主要 UI 文字 | Inter（300/400/500/600/700） | Google Fonts CDN |
| 程式碼/標籤/時碼 | JetBrains Mono（400/500/700） | Google Fonts CDN |
| class 名稱 | `.mono` | index.html 全局定義 |

### 顯示比例元件

**9:16 直向（Shorts）**
- 圖片槽：`aspect-[9/16]`
- 卡片格線：`grid-cols-3`
- 圖片 object-fit：`object-contain`（黑色底）

**16:9 橫向（標準）**
- 圖片槽：`aspect-[16/9]`
- 卡片格線：`grid-cols-2`
- 圖片 object-fit：`object-contain`（黑色底）

### 特殊 CSS 元件

```css
/* 玻璃卡片 */
.glass-card {
  background: rgba(18, 18, 20, 0.6);
  backdrop-filter: blur(10px);
  border: 1px solid #27272a;
}

/* 切角效果（右下角 10px） */
.dossier-clip {
  clip-path: polygon(0 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%);
}

/* 掃描線動畫 */
.scan-line {
  animation: scan 3s linear infinite;
  background: linear-gradient(to right, transparent, #10b981, transparent);
  opacity: 0.3;
}

/* 格線背景 */
.grid-bg {
  background-image: linear-gradient(to right, rgba(39,39,42,0.2) 1px, transparent 1px),
                    linear-gradient(to bottom, rgba(39,39,42,0.2) 1px, transparent 1px);
  background-size: 24px 24px;
}
```

### Pacing Profiles（步調設定）

| Profile | 時長 | Units | Beat 比例 (H/B/P) | Cut | Captions | Veo Budget |
|---------|------|-------|-------------------|-----|----------|------------|
| `shorts` ⚡ | 15–60s | 3–6 | 15/70/15% | fast | dense | 2 |
| `medium` 🎬 | 3–10min | 6–15 | 10/75/15% | medium | normal | 5 |
| `long` 🎞️ | 30–60min | 15–40 | 5/80/15% | slow | sparse | 10 |

### UnitPlan 映射

- `index=0` → `beat=hook`, `keyframe_id=KF001`
- `index=last` → `beat=payoff`, `keyframe_id=KF003`
- `其餘` → `beat=body`, `keyframe_id=KF002`，`variant_goal` 循環 a→b→c→d（BIO/OBJECT/PHENOM 三模式）

---

## 4. 環境變數

### 後端（`backend/.env`）

| 變數 | 範例值 | 用途 |
|------|--------|------|
| `GEMINI_API_KEY` | `AIza...` | Google Gemini API（腳本生成） |
| `REPLICATE_API_TOKEN` | `r8_...` | Replicate API（FLUX 圖片生成） |
| `HOST` | `127.0.0.1` | uvicorn 監聽地址 |
| `PORT` | `8000` | uvicorn 監聽埠 |
| `DEBUG` | `True` | 開啟 uvicorn reload |
| `FRONTEND_URL` | `http://localhost:3000` | CORS allow_origins |

### 前端（`frontend/.env`）

| 變數 | 範例值 | 用途 |
|------|--------|------|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | 後端 API base URL |

---

## 5. 外部 AI 模型

| 模型 | 供應商 | 用途 | 費用 |
|------|--------|------|------|
| `gemini-2.5-flash-lite` | Google Gemini | 觀測腳本生成（JSON 輸出） | 依 token |
| `flux-schnell` | Replicate / Black Forest Labs | Keyframe 圖片生成 | $0.003/張 |
| `flux-dev` | Replicate / Black Forest Labs | 封面圖生成（guidance=4.5~5.0） | $0.025/張 |
| `flux-1.1-pro` | Replicate / Black Forest Labs | 高品質圖片（選用） | $0.04/張 |
| **Veo** | Google | 影片生成（prompt 輸出，尚未串接） | — |

### 重要限制
- **FLUX 不支援 `negative_prompt`**：所有品質/亮度控制必須用正面描述
- **封面亮度品質檢查**：自動抓取封面圖做 64×64 grayscale 分析（brightness ≥ 45, variance ≥ 300），不通過觸發一次自動換風格重試
- **封面風格**：由 KF001 的 `hook_technique` 決定（`visual_paradox→paradox`、`forbidden_knowledge→evidence`、其餘→`closeup`）
- **Gemini 超時設定**：180 秒（SSE）/ 150 秒（REST）

---

## 6. ZIP 素材包規格（pack_meta_v1）

**檔名格式**：`pack_<slug>_<YYYYMMDD_HHMMSS>_<mode>_<aspect>.zip`

**ZIP 內容（依序）**

```
pack_<slug>_<ts>/
├── images/
│   ├── cover.png                   # 封面圖（flux-dev 生成）
│   └── keyframe_001.png            # Keyframe（flux-schnell 生成）
├── meta.json                       # pack_meta_v1 機器可讀元數據
├── README_START_HERE.txt           # 人類可讀說明
├── EDITING_GUIDE_CAPCUT.txt        # 30fps CapCut 剪輯指南
└── run_log.json                    # 本次生成日誌
```

**EDITING_GUIDE_CAPCUT.txt 時間偏移**（相對各段起始）
- VO：+10f in → +98f out（約 0.33s → 3.27s）
- SUB：+15f in → +83f out（約 0.5s → 2.77s）
- SFX：+80f in → +90f out（約 2.67s → 3.0s）
- 閱讀速率：VO 4.5 CPS，SUB 2.2 CPS，每段 5 秒

---

## 7. 既有文件摘要

| 文件 | 核心要點 |
|------|---------|
| `docs/INSTALLATION_GUIDE.md` | 安裝步驟、環境設定 |
| `docs/UPGRADE_GUIDE.md` | 短片→長片升級說明 |
| `docs/FEATURES_DEMO.md` | 功能演示與截圖說明 |
| `docs/constitution_micro_wonder_v2.md` | 微奇觀系列影片製作規範 v2（主題定義、觀測邏輯、旁白風格） |
| `backend/INSTALL_BACKEND.md` | 後端安裝快速指南 |
| `frontend/README.md` | 前端開發說明 |

---

## 8. 開發注意事項

### 已知 TS 編譯警告（不影響 Vite build）
- `exportService.ts`：引用 ObservationUnit 上不存在的欄位（end_timecode、sfx、bgm）
- `geminiService.ts:8`：`import.meta.env`（vite-env.d.ts 未加入 tsconfig）

### Dev Override
```typescript
// config/pacingProfiles.ts
export const DEV_SHORTS_UNIT_OVERRIDE: number | null = 5;
// 設為 5 強制 Shorts 生成 5 個單元以測試 variant_goal a/b/c 全覆蓋
// 設為 null 恢復正常 profile 驅動行為
```

### CORS 設定
後端允許：`localhost:3000`, `127.0.0.1:3000`, `localhost:3001`, `127.0.0.1:3001`

### 啟動指令
```bash
# 後端
cd backend && python main.py

# 前端
cd frontend && npm run dev   # → http://localhost:3000
```
