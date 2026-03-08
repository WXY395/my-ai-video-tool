# api_architect.md — 後端與架構專家準則
> 最高準則：任何後端變更必須符合本文件定義的接口規範與 Schema 結構。

---

## 1. API 接口規範

### Base URL
```
http://127.0.0.1:8000
```

### 已實作端點一覽

| Method | Path | 說明 | 回應格式 |
|--------|------|------|---------|
| POST | `/api/observation/generate` | 生成腳本（一次性 JSON） | `ObservationResponse` |
| POST | `/api/observation/generate-stream` | 生成腳本（SSE 串流） | SSE event stream |
| POST | `/api/observation/estimate-cost` | 成本預估（不生成圖片） | 成本 JSON |
| POST | `/api/image/generate` | 單張 keyframe 圖片生成 | `{ success, image_url }` |
| GET  | `/api/observation/modes` | 可用模式與比例清單 | 模式 JSON |
| GET  | `/api/observation/health` | 健康檢查 | `{ status: "healthy" }` |

---

## 2. Request Schema

### ObservationNotesInput（所有生成端點共用）
```python
class ObservationNotesInput(BaseModel):
    notes: str                          # alias="rawInput"，主題或筆記內容
    target_units: int                   # alias="unitCount"，ge=1 le=50，預設 3
    style_preference: str = "default"
    video_mode: VideoMode = "shorts"    # "shorts" | "medium" | "long"
    aspect_ratio: ContentFormat = "9:16"# "9:16" | "16:9" | "1:1"
    duration_minutes: Optional[int]     # 僅長片使用

    class Config:
        populate_by_name = True         # 支援 alias 與原名同時解析
```

**前端送出格式**：
```json
{
  "rawInput": "蜻蜓翅膀",
  "unitCount": 3,
  "video_mode": "shorts",
  "aspect_ratio": "9:16",
  "duration_minutes": null
}
```

### ImageGenerateRequest（/api/image/generate）
```json
{
  "prompt": "dragonfly wing, extreme macro...",
  "negative_prompt": "low quality, blurry",
  "aspect_ratio": "9:16"
}
```

---

## 3. ObservationUnit — Pydantic Schema 完整結構

> **準則**：後端 JSON 輸出必須永遠包含以下所有欄位，缺欄位將導致前端渲染失敗。

```python
class ObservationUnit(BaseModel):
    # === 識別 ===
    id: str                             # "KF001a"、"unit_001" 等

    # === 核心內容 ===
    phenomenon: str                     # 現象描述（主標題），max_length=35
    mechanism: str                      # 機制說明（副標題），max_length=70

    # === 語音與字幕 ===
    voice_over_zh: str                  # 中文旁白，max_length=50
                                        # 速率公式：floor((unit_sec - 1.0) × 7.0) 字
    subtitle_zh: str                    # 字幕，max_length=12（實務≤8字）
                                        # ⚠ 非旁白縮短版，是旁白的「吐槽或補充」

    # === 視覺與圖片 ===
    visual_description: str             # 視覺場景描述，max_length=150
    image_prompt: ImagePrompt           # { prompt: str, negative_prompt: str }
                                        # ⚠ prompt 必須以英文主體名詞開頭

    # === 情緒與氛圍 ===
    emotional_tone: str                 # 如「驚嘆、好奇」

    # === 時間線與鏡頭 ===
    start_timecode: str = "00:00:00:00"
    duration_seconds: int               # ge=1, le=120
    camera_mode: str = "CLOSE_UP"
    in_scene_timeline: List[ActivityEvent] = []

    # === 運鏡指導 ===
    motion_guidance: Optional[MotionGuidance]
    # MotionGuidance: { effect, duration_seconds, transition_to_next, notes }
    # effect 選項: ken_burns | zoom_in | zoom_out | pan_left | pan_right | static
    is_keyframe: bool = True

    # === 剪輯資訊 ===
    editing_notes: Optional[str] = ""

    # === 演算法張力欄位 ===
    unit_role: str                      # "定位" | "解構" | "影響" | "content"
    hook_technique: Optional[str]       # 定位幕專用
                                        # reverse_question | shock_fact |
                                        # forbidden_knowledge | visual_paradox |
                                        # incomplete_loop
    seo_keywords: List[str] = []        # 繁體中文真實搜尋詞
    interaction_trigger: Optional[str]  # comment_bait | share_trigger |
                                        # replay_hook | save_reminder
    interaction_bait_text: Optional[str]# 影響幕互動誘餌文字，max_length=50
    hashtag_strategy: Optional[HashtagStrategy]

    # === Veo 影片生成（手動模式）===
    veo_prompt: Optional[str]           # 英文動態場景描述
    veo_recommended: bool = False       # 解構幕最適合

    # === 舊版相容性（可選）===
    hook: Optional[str]
    core_message: Optional[str]
    script_outline: Optional[List[str]]
```

---

## 4. SSE 串流事件規格

> 使用 `sse-starlette.EventSourceResponse` 包裝 async generator。
> 前端使用 `fetch + ReadableStream`（不能用 EventSource，因為是 POST）。

```
event types（按時序）:
  {"type": "step",  "message": "解析輸入中"}
  {"type": "step",  "message": "Gemini 腳本生成中…"}
  {"type": "units", "units": [...], "cost_estimate": {...},
                    "video_mode": "shorts", "aspect_ratio": "9:16"}
  {"type": "step",  "message": "封面生成中…"}
  {"type": "cover", "cover_url": "https://..."}
  {"type": "done",  "production_notes": {...}, "cost_estimate": {...}}
  {"type": "error", "message": "..."}   ← 僅失敗時
```

**超時設定**：
- SSE 串流：180 秒
- REST 生成：150 秒
- 圖片生成：60 秒
- 成本預估：30 秒

---

## 5. 成本模型

| 模型 | 用途 | 單價 |
|------|------|------|
| `flux-schnell` | Keyframe 圖片 | $0.003/張 |
| `flux-dev` | 封面圖 | $0.025/張 |
| `flux-1.1-pro` | 高品質（選用） | $0.04/張 |
| `gemini-2.5-flash-lite` | 腳本生成 | token 計費 |

**典型 Shorts（3 KF + 1 封面）**：
- `3 × $0.003 + 1 × $0.025 = $0.034`

---

## 6. Veo 採手動生成模式

> **現行決策**：Veo 影片生成**不串接任何 API**，僅優化 prompt 輸出。

- `veo_prompt` 欄位由 Gemini 生成英文動態場景描述
- `veo_recommended: true` 標記哪些幕最適合轉影片（通常為解構幕）
- 使用者自行複製 veo_prompt 到 Google Veo / Sora / Runway 等工具
- 前端 UI 以可展開區塊顯示（紫色 ✦ VEO 標記）
- **不需要**新增任何 Veo API 呼叫代碼

---

## 7. 封面生成邏輯

### 風格選擇（非隨機，依 hook_technique）
```python
_HOOK_TO_STYLE = {
    "visual_paradox":      "paradox",
    "forbidden_knowledge": "evidence",
    # 其他全部 → "closeup"（預設）
}
_STYLE_FALLBACK = {
    "closeup":  ["evidence", "paradox"],
    "evidence": ["closeup",  "paradox"],
    "paradox":  ["closeup",  "evidence"],
}
```

### 品質閘（自動重試一次）
```python
COVER_MIN_BRIGHTNESS = 45   # avg luminance 0-255
COVER_MIN_VARIANCE   = 300  # pixel variance（64×64 grayscale downsample）
# 不通過 → 切換 retry_style，guidance 提高至 5.0 重試
# _check_cover_quality 返回 None → 跳過閘（套件不可用不報錯）
```

### 錨點萃取策略
- 英文主題 → `_extract_topic_subject(topic)` 直接萃取
- 中文主題 → 掃全部 units 的 `image_prompt.prompt`，取最短有效錨點
- 最終 fallback → `"macro specimen"`

---

## 8. CORS 設定
```python
allow_origins = [
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:3001", "http://127.0.0.1:3001",
]
allow_methods = ["*"]
allow_headers = ["*"]
```
