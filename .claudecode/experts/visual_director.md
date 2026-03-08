# visual_director.md — 視覺與 UI 導演準則
> 最高準則：所有前端組件的視覺決策必須符合本文件定義的藍海引擎色彩系統與風格規範。

---

## 0. V34.0 品牌 DNA 常數（變色龍模式）

視覺基因隨主題自適應，不再強制單一工業/藍圖風格：

```
BRAND_LIGHTING  = "diffused archival illumination"   ← 中性存檔光，適合所有主題
BRAND_AESTHETIC = "archival scan aesthetic"           ← 中性存檔美學，醫療/科技/歷史均適用
```

- prompt 風格由主題類型動態決定（醫療→解剖存檔 / 科技→電路藍圖 / 歷史→文物影像）
- 禁止強制任何單一 Nocturia 或工業主題詞彙

---

## 1. 藍海引擎色彩規範

### 系統色票

| 語義 | Tailwind | 色碼 | CSS 變數 |
|------|----------|------|---------|
| **全局背景** | `zinc-950` | `#09090b` | `--color-bg` |
| **卡片/面板底色** | — | `#121214` | `--color-surface` |
| **邊框** | `zinc-800` | `#27272a` | `--color-border` |
| **主強調** | `emerald-500` | `#10b981` | `--color-accent` |

### 角色色系（Unit Role）

| 角色 | 英文 | 主色 | Badge 邊框 | Badge 背景 | Header 背景 |
|------|------|------|-----------|-----------|------------|
| **定位幕** | Hook | `text-orange-400` | `border-orange-500/30` | `bg-orange-500/10` | `bg-orange-500/5` |
| **解構幕** | Body | `text-yellow-400` | `border-yellow-500/30` | `bg-yellow-500/10` | `bg-yellow-500/5` |
| **影響幕** | Payoff | `text-emerald-400` | `border-emerald-500/30` | `bg-emerald-500/10` | `bg-emerald-500/5` |
| **一般內容** | Content | `text-zinc-500` | `border-zinc-700` | `bg-zinc-800/30` | `bg-zinc-900/40` |

### 功能色系

| 功能 | 色系 | 使用場景 |
|------|------|---------|
| **Veo 推薦** | `violet-400/500`，`bg-violet-500/15`，`border-violet-500/30` | ✦ VEO badge、VEO 展開區塊 |
| **Motion 效果** | `blue-400/500`，`bg-blue-500/10`，`border-blue-500/20` | 運鏡 badge |
| **互動觸發** | 依類型：`blue`（留言）/ `green`（分享）/ `amber`（重播）/ `purple`（收藏） | 互動觸發區塊 |
| **SEO** | `zinc-800/60`，`border-zinc-700/50`，`text-zinc-500` | #hashtag badges |
| **狀態：成功** | `emerald-500` | 圓點指示、CheckCircle、生成完成 |
| **狀態：生成中** | `zinc-700`（animate-pulse/spin） | Loader2 圖示 |
| **狀態：錯誤** | `rose-500`，`bg-rose-500/10`，`border-rose-500/20` | 錯誤面板 |
| **Beat: Hook** | `text-orange-400`，`border-orange-500/30`，`bg-orange-500/10` | UnitPlanBadge |
| **Beat: Body** | `text-zinc-500`，`border-zinc-700`，`bg-zinc-800/20` | UnitPlanBadge |
| **Beat: Payoff** | `text-emerald-400`，`border-emerald-500/30`，`bg-emerald-500/10` | UnitPlanBadge |

---

## 2. 字型規範

| 字型 | 權重 | 載入 | 使用場景 |
|------|------|------|---------|
| **Inter** | 300/400/500/600/700 | Google Fonts CDN | 所有正文、標題、按鈕 |
| **JetBrains Mono** | 400/500/700 | Google Fonts CDN | 時碼、ID、標籤、log、class `.mono` |

**字級規範（ObservationUnitCard.tsx）**：
- Unit ID / 系統標籤：`text-[9px] mono`
- Role Badge：`text-[8px] mono font-black`
- 現象標題：`text-[11px] font-bold text-zinc-200`
- 機制說明：`text-[10px] text-zinc-400`
- 旁白：`text-[12px] text-zinc-100 font-medium tracking-wide`
- 字幕 Badge：`text-[13px] font-black text-white`
- 互動/SEO 標籤：`text-[8px] mono`
- Veo Prompt 展開：`text-[9px] text-zinc-500 font-mono`

---

## 3. 顯示比例元件規範

### 9:16 直向（Shorts 模式）
- 圖片槽：`aspect-[9/16]`
- 卡片格線：`grid-cols-3 gap-6`
- 圖片渲染：`object-contain`（黑色底 `bg-black`）
- 圖片可點擊放大：`cursor-zoom-in`（yet-another-react-lightbox）

### 16:9 橫向（中片/長片模式）
- 圖片槽：`aspect-[16/9]`
- 卡片格線：`grid-cols-2 gap-6`
- 圖片渲染：`object-contain`（黑色底 `bg-black`）

---

## 4. FLUX 圖片生成參數（鎖定規範）

> **核心限制**：FLUX 模型不支援 `negative_prompt`（API 靜默忽略）。
> 所有品質、亮度、清晰度控制**必須**寫進正面 prompt。

### §4.0 主題自適應材質原則（V34.0 變色龍模式）

> **核心原則**：材質選擇隨主題自動匹配，禁止強制單一工業風格。

#### 主題材質對應（Topic-Adaptive Material）

| 主題類型 | 適用材質 | 禁止材質 |
|---------|---------|---------|
| 醫療/生理 | anatomical diagram, clinical specimen, archival medical chart | brass, gear, blueprint |
| 科技/工程 | circuit board detail, optical lens, fiber optic strand | biological tissue, face |
| 歷史/傳記 | aged parchment, manuscript grain, museum specimen label | industrial gear, riveted metal |
| 自然/科學 | crystalline structure, laboratory glass, microscopic structure | warm skin glow, human face |

#### 燈光原則（Lighting Protocol）
- ❌ **嚴禁**：`rim light`、`edge light`、`warm skin glow`、`soft backlight`（觸發人體形態）
- ✅ **推薦**：`diffused overhead studio light`、`flat documentary light`、`archival illumination`、`cool daylight spectrum`

### Keyframe 圖（flux-schnell）
- model：`flux-schnell`
- 比例：`aspect_ratio` 傳入（`9:16` / `16:9`）
- prompt 起頭規則：**第一個 token 必須是英文主體名詞**（禁止動詞/分詞/代名詞開頭）
- 禁止開頭詞：`emphasizing / showing / revealing / its / their / this / that / subject / background / with`

### 封面圖（flux-dev）
- model：`flux-dev`
- guidance：初次 `4.5`，品質重試 `5.0`
- seed：每次請求隨機生成（確保同主題輸出多樣性）
- 三種風格：

```
closeup  → 主體特寫，局部 1/2 出框，上緣出框，高調打光，diffused archival illumination
evidence → 博物館標本卡，局部 1/2 出框，左緣出框，暖色系背景，紅圈圖形
paradox  → 對比悖論，局部 1/2 出框，左緣出框，強打光主體，右側對比元素
```

### 品質閘（亮度/方差校驗）
```
分析方式：64×64 grayscale downsample
threshold：brightness ≥ 45 / variance ≥ 300
不通過 → 自動換 retry_style + guidance=5.0 重試一次
回傳 None（套件不可用）→ 跳過閘，不報錯，直接使用原圖
```

### §4.1 抽象主題視覺實體化規則（Abstract → Physical Mapping）

> **核心原則**：FLUX 只能繪製**可見的物理實體**。抽象概念（誕生、起源、革命、奇蹟）
> **必須強制轉譯為具體物件**，否則模型輸出隨機有機紋理或無意義光效。

| 主題類型 | 抽象詞（禁止直接入 prompt） | 替換為物理實體 |
|---------|--------------------------|--------------|
| 人物傳記 | 誕生、出生、生命、偉大 | 代表性工具/文件（電話機、手稿、專利書、實驗設備） |
| 歷史事件 | 起源、革命、崛起、變革 | 時代實物（機械裝置、書信、地圖、印刷機、齒輪） |
| 科學發現 | 突破、理論、發現、奇蹟 | 關鍵儀器（實驗設備、試管、測量工具、顯微鏡） |
| 技術創新 | 創造、進步、設計、改良 | 核心機件（齒輪、電路板、手繪機械圖紙、比例模型） |

**示例（人物傳記主題）：**
```
❌ 禁止：birth of inventor, miracle of life, origin of sound
✅ 正確：inventor's patent document, period laboratory apparatus,
         hand-drawn technical diagram, representative scientific instrument
```

**強制排除詞（追加至所有 image_prompt 正面 prompt 的 _AVOID 條款）：**
```
skin-like gloss, fleshy shapes, organic tissue, biological bulbs,
fingerprints, cell membranes, flesh texture, amorphous blobs,
liquid organic shapes, biological cross-section
```

### §4.2 物化主體原則（Materialization Principle — V30.0）

> **核心宣言**：系統是一個「非生物觀察者」。所有視覺輸出必須優先鎖定硬材質物件，
> **嚴禁**使用 `face` 或 `faces` 作為微距觀察對象。

**硬材質主體優先規則（所有幕次強制執行）：**

| 主題類型 | ❌ 禁止視覺 | ✅ 必須替換為 |
|---------|-----------|------------|
| 伊斯蘭教 / 清真寺 | 禮拜者面孔、人群 | 幾何阿拉伯花紋、藍色磁磚紋理、星形幾何圖案 |
| 佛教 / 禪宗 | 僧侶面孔、膜拜手勢 | 檀木紋理、青銅蓮花座、寺廟石雕圖案 |
| 人物傳記 | 臉部特寫、皮膚紋理 | 代表性文件、手稿頁面、科學儀器、標本標籤 |
| 任何微距構圖 | face / faces 作為觀察主體 | 材質截面、機械細節、礦物晶體、文件纖維 |

**`face` / `faces` 絕對禁止規則：**
- 這兩個詞在所有 `image_prompt.prompt` 中均屬黑名單詞彙
- 後端偵測到後自動替換為 `identifiable historical artifact`
- Gemini 腳本生成階段禁止以 `face` 或 `faces` 作為微距觀察主體

**具體轉譯示例（強制執行路徑）：**
```
伊斯蘭教  → geometric arabesque pattern, blue mosque tile
電話/通訊  → period patent document, communication device schematic, archival documentation
佛教      → sandalwood wood grain texture, bronze lotus statue surface
任何人物  → 角色代表性工具或文件（永遠不是面孔）
```

---

### §4.3 動態美學牆（Anti-Template Aesthetic — V31.0）

> **核心問題**：AI 量產內容的視覺指紋 = 固定 zoom 速度 + 固定構圖 + 固定色溫。
> 演算法與觀眾都能識別「模板感」，導致頻道 IP 無法成立。

#### 節奏破壞協議（Rhythm Disruption Protocol）

**強制隨機化規則**：同一影片的多個單元，以下參數**嚴禁全部相同**：

| 參數 | 允許值集合 | 隨機化要求 |
|-----|-----------|----------|
| `zoom_speed` | slow / medium / fast / micro | 相鄰單元不可相同 |
| `camera_motion` | push-in / pull-out / drift-left / drift-right / static | 任意 5 幕中至多重複 1 次 |
| `cut_rhythm` | snap / gradual / hold / stutter | 每幕獨立選擇 |

**觸發 `ERR_RHYTHM_CLONE` 的情況**：
```
❌ 3 幕全部使用 slow zoom-in
❌ 所有幕使用相同 camera_motion 類型
❌ 剪輯節奏完全對稱（如 1.5s / 1.5s / 1.5s）
```

#### 視覺差異化協議（Visual Fingerprint Protocol）

**藝術偏移量注入（image_prompt 隨機化選項）**：

每個 `image_prompt` 必須從以下各維度各選一個偏移值，形成唯一的「視覺指紋」：

**色溫偏移（每幕獨立選擇）：**
```
cold: "cool daylight spectrum, 5600K clinical"
neutral: "balanced studio illumination, 4200K"
warm: "warm archival amber, 3200K documentary"
high-contrast: "extreme contrast, crushed blacks, blown highlights"
```

**構圖偏移（每幕獨立選擇，禁止連續兩幕相同）：**
```
center-weighted: "subject centered at exact optical axis"
rule-of-thirds: "subject positioned at left third"
extreme-crop: "subject extends beyond all four edges"
dutch-angle: "5-degree tilt, tension composition"
```

**材質粗糙度（依主題類型選擇）：**
```
pristine: "perfect surface, museum-grade condition"        ← 科技/現代主題
worn: "surface wear, oxidation patina, age cracks"        ← 歷史/傳記主題
damaged: "edge erosion, foxing stains, battle scars"      ← 戰爭/衝突主題
```

---

## 5. 特殊 CSS 元件（鎖定，禁止隨意修改）

```css
/* 玻璃卡片效果 */
.glass-card {
  background: rgba(18, 18, 20, 0.6);
  backdrop-filter: blur(10px);
  border: 1px solid #27272a;
}

/* 右下角切角（dossier 風格） */
.dossier-clip {
  clip-path: polygon(0 0, 100% 0, 100% calc(100% - 10px),
             calc(100% - 10px) 100%, 0 100%);
}

/* 格線背景（全局） */
.grid-bg {
  background-image:
    linear-gradient(to right, rgba(39,39,42,0.2) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(39,39,42,0.2) 1px, transparent 1px);
  background-size: 24px 24px;
}

/* emerald 掃描線動畫 */
.scan-line {
  background: linear-gradient(to right, transparent, #10b981, transparent);
  opacity: 0.3;
  animation: scan 3s linear infinite;
}

/* 細滾動條 */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-thumb { background: #3f3f46; border-radius: 0px; }
```

---

## 6. ObservationUnitCard.tsx 風格一致性準則

### 卡片結構（必須維持）
```
[Card Header]
  ├─ 狀態圓點（emerald/zinc-800 animate-pulse）
  ├─ Unit ID（zinc-600）
  ├─ Role Badge（角色色系）
  ├─ Hook Technique Badge（orange-300/80，定位幕專用）
  └─ Veo Badge（violet-300，veo_recommended=true）

[Visual Slot] — aspect ratio 固定
  ├─ 有圖：<img object-contain> + cursor-zoom-in → Lightbox
  └─ 無圖：ImageIcon + Generate_Asset 按鈕（zinc-100 bg，黑色文字）

[Metadata 區塊]
  ├─ Sparkles（emerald-500/60）+ 現象標題 + 機制說明
  ├─ Mic 旁白區塊（border-t zinc-800/50）
  ├─ PlayCircle 字幕 Badge（zinc-800 bg，font-black）
  ├─ MousePointerClick 互動觸發（條件顯示）
  ├─ Tag SEO 關鍵字（最多顯示 4 個）
  ├─ Video Veo 折疊區塊（ChevronDown/Up）
  ├─ Camera 鏡頭模式 + Film 運鏡 Badge
  └─ Footer：Unit_Ready 標籤 + CheckCircle（有圖時顯示）
```

### 按鈕風格
- 主要操作（Generate_Asset）：`bg-zinc-100 hover:bg-white text-zinc-950 font-black mono uppercase`
- 主要 CTA（INIT_PROTOCOL）：`bg-zinc-100 text-zinc-950 hover:bg-white border border-white`
- Export Pack：`bg-emerald-500/10 text-emerald-400 border border-emerald-500/30`
- 模式選鈕（選中）：`bg-emerald-500 text-zinc-950`
- 比例選鈕（選中）：`bg-blue-500 text-zinc-950`
- 禁用狀態：`bg-zinc-900 text-zinc-700 border border-zinc-800 cursor-not-allowed`

---

## 7. 拖曳排序（@dnd-kit）視覺規範

- 握把圖示：`GripVertical`，`text-zinc-800 hover:text-zinc-500`，`cursor-grab active:cursor-grabbing`
- 拖曳中卡片：`opacity: 0.4`，`zIndex: 50`
- 啟動距離：`8px`（避免誤觸卡片內按鈕）
- 握把位置：卡片左上方，與 UnitPlanBadge 並排

---

## 8. Toast 通知規範（sonner）

```
theme="dark"  position="bottom-right"  richColors  closeButton
```

| 事件 | toast 類型 | 訊息格式 |
|------|-----------|---------|
| 成本預估完成 | `toast.success` | `預估 $X.XXX（N 個 KF）` |
| 生成開始 | `toast.loading` | `Gemini 腳本生成中…`（id='gen'） |
| 腳本就緒 | `toast.loading` | `封面生成中…`（id='gen'） |
| 全部完成 | `toast.success` | `N 個單元就緒 · 封面已生成`（id='gen'） |
| 圖片生成中 | `toast.loading` | `合成 KF001…`（id=`img-${unitId}`） |
| 圖片就緒 | `toast.success` | `KF001 圖片就緒` |
| 打包中 | `toast.loading` | `打包素材包…`（id='export'） |
| 打包完成 | `toast.success` | `ZIP 已下載（封面 + N 張 KF）` |
| 任何錯誤 | `toast.error` | 原始錯誤訊息 |
