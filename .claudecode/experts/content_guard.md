# content_guard.md — 內容與語言守衛準則
> 最高準則：本文件定義的語言與節奏規範具有最高優先權，任何 AI 生成內容或代碼輸出皆必須遵守。

---

## 1. 語言守衛：絕對禁止簡體中文

### 核心規則
> ⛔ **任何情況下絕對禁止出現簡體中文字元。**
> ✅ 所有中文輸出一律使用**繁體中文（ZH-TW）**。

### 適用範圍
- `voice_over_zh`（旁白）
- `subtitle_zh`（字幕）
- `phenomenon`（現象描述）
- `mechanism`（機制說明）
- `interaction_bait_text`（互動誘餌文字）
- `seo_keywords`（SEO 關鍵字）
- UI 介面標籤、錯誤訊息、toast 通知
- meta.json、EDITING_GUIDE_CAPCUT.txt、README 等所有輸出文件
- 系統 prompt、schema 範例、示範句

### 常見簡繁對照（容易混淆的詞）
| 簡體（禁用） | 繁體（正確） |
|------------|------------|
| 视频 | 影片 |
| 镜头 | 鏡頭 |
| 观测 | 觀測 |
| 单元 | 單元 |
| 旁白 | 旁白 ✓ |
| 字幕 | 字幕 ✓ |
| 节奏 | 節奏 |
| 规范 | 規範 |
| 参数 | 參數 |
| 输出 | 輸出 |
| 关键字 | 關鍵字 |
| 专家 | 專家 |
| 图片 | 圖片 |
| 时间 | 時間 |
| 动态 | 動態 |
| 长片 | 長片 ✓ |
| 短片 | 短片 ✓ |

### Image Prompt 語言規則
- `image_prompt.prompt`：**必須全英文**（FLUX 模型僅接受英文）
- `veo_prompt`：**必須全英文**（Veo/Runway 模型輸入要求）
- `negative_prompt`：**必須全英文**（即使 FLUX 靜默忽略）
- 所有其他中文欄位：ZH-TW

---

## 2. 腳本節奏鎖定

### 語速公式
```
VO  速率：4.5 CPS（Chinese chars per second）
SUB 速率：3.5 CPS（Chinese chars per second）
        實測基準：8 字 ÷ 2.3 秒 ≈ 3.48 → 取 3.5 CPS（2026-03 實測更新）
每段基準時長：5 秒

VO  最大字數 = floor(5 × 4.5) = 22 字
SUB 最大字數 = floor(5 × 3.5) = 17 字
```

### 動態字數計算（unit_seconds 變動時）
```
VO  max = floor((unit_seconds - 1.0) × 7.0)
          （保留 1 秒呼吸空間，7字/秒為 TTS 最高速）
SUB max = min(floor(unit_seconds × 3.5), 30)
          5 秒單元 → floor(5 × 3.5) = 17 字（建議 16–18 字）
          動態調整，確保語意完整；單元再長也不超過 30 字上限
```

### 語義壓縮規則（超出字數時）
優先在以下位置截斷（依優先序）：
1. 句號 `。` / 驚嘆號 `！` / 問號 `？`（完整句子邊界）
2. 逗號 `，` / 頓號 `、`（子句邊界）
3. 重新構思精煉短句（參見第 4 條）
4. 硬截斷（絕對最後手段，標記 `[COMPRESSED]`）

### 語法強制校驗（禁止語義截斷）
> ❌ **嚴禁為了字數限制而刪除句末名詞或動詞。**
> ✅ 字數超標時，必須**重新構思語意更精煉的短句**，而非隨機刪減尾字。

```
❌ 無效截斷（句意殘缺）：
   「0.03公分的奇蹟，決定了聲音能否跨越時」   ← 刪掉「空」，語意破碎
   「每天一顆的人，可能比你多活」              ← 刪掉「十年」，資訊殘缺

✅ 正確做法（重構短句，保留語意完整）：
   「0.03公分，決定聲音跨越時空」              ← 17字，重構後語意完整
   「每天一顆，多活十年」                      ← 9字，精煉有力
```

判斷標準：截斷後能否獨立成一個完整的中文短句？
- 能 → 允許
- 不能 → 必須重構，不得截斷

---

## 3. 字幕（subtitle_zh）專項規範

> **核心定義**：字幕是旁白的「第二聲音」——吐槽或補充，**不是旁白的縮短版**。

### 字幕規則
- **上限**：≤ 17 字（5 秒單元；動態公式 `min(floor(unit_seconds × 3.5), 30)`）
- **目標範圍**：8–17 字（避免過度壓縮；語意完整優先於字數精簡）
- **禁止**：直接複製旁白的前 N 字
- **禁止**：為達字數限制而截斷句末名詞或動詞（見 §2 語法強制校驗）
- **正確方式**：說旁白「沒說的那一面」、反諷、數據化、強調重點；若需壓縮則重構短句

### 字幕範例（阿斯匹靈主題）
| 旁白（VO） | 字幕（SUB）❌ 錯誤 | 字幕（SUB）✅ 正確 |
|-----------|-----------------|-----------------|
| `你以為它是退燒藥——它從沒退過燒。` | `你以為退燒藥` | `從沒退燒` |
| `一片 0.3 克，剛好卡在救命和致命之間。` | `0.3克救命致命` | `0.3克刀刃` |
| `那個每天一顆的人，可能比你多活十年。` | `每天一顆多活` | `多活十年` |

---

## 4. 旁白（voice_over_zh）敘事規範

### 三幕連貫性
- **同一個敘事者**說同一個故事，三幕之間有情緒進展
- 禁止每幕獨立成段、使用模板套語
- 情緒進展方向：`好奇 → 懸念 → 恍然大悟`

### 禁止模板句型
```
❌ "你知道嗎？..." （開場套語）
❌ "首先...其次...最後..." （條列格式）
❌ "讓我們來看看..." （旁白視角跳出）
❌ "這就是..." （payoff 模板）
❌ 每幕都以疑問句收尾
```

### 正確敘事節奏
```
定位幕（Hook）：顛覆預設認知的第一句，引爆好奇心
解構幕（Body）：機制揭露，遞進懸念，保持旁白的「一口氣」感
影響幕（Payoff）：情緒落點，可以是「啊哈」或「不安」，但不能是廢話
```

---

## 5. Shorts 模式單元數與結構規範

### 單元數量
```
最小：3 單元（hook × 1 + body × 1 + payoff × 1）
最大：6 單元
預設：3 單元
DEV Override：DEV_SHORTS_UNIT_OVERRIDE = 5（測試用，上線前還原為 null）
```

### Beat 結構（KF 映射）
```
index = 0        → beat=hook,   KF001,  variant_id=a
index = 1 ~ n-2  → beat=body,   KF002,  variant_id 依序 b/c/...
                   variant_goal 循環 a→b→c→d（每個 body 不同觀測任務）
index = n-1      → beat=payoff, KF003,  variant_id=a
```

### Beat 比例（shorts）
```
hook:   15%  （最小 1 幕）
body:   70%  （主要內容）
payoff: 15%  （最小 1 幕）
```

---

## 6. 演算法張力欄位規範

### unit_role 使用規則
| 角色 | 指派位置 | 主要任務 |
|------|---------|---------|
| `定位` | index=0 | 設置懸念，hook_technique 必填 |
| `解構` | index=1~n-2 | 機制拆解，veo_recommended 優先考慮 |
| `影響` | index=n-1 | 情緒落點，interaction_bait_text 必填 |

### hook_technique 選擇指南
| 主題類型 | 建議技術 |
|---------|---------|
| 反常識知識 | `reverse_question` |
| 震驚數據/事實 | `shock_fact` |
| 被隱瞞的資訊 | `forbidden_knowledge` |
| 視覺矛盾現象 | `visual_paradox` |
| 未解決的懸念 | `incomplete_loop` |

### interaction_bait_text 規範
- **僅影響幕**（index=n-1）必填
- 對應 `interaction_trigger` 類型：
  - `comment_bait`：提問引發評論（「你身邊有人...嗎？」）
  - `share_trigger`：讓人想分享的感嘆（「原來如此！」）
  - `replay_hook`：需重看才懂的細節提示
  - `save_reminder`：實用資訊提醒收藏
- 字數：≤ 30 字（max_length=50）

---

## 7. SEO 關鍵字規範

- 一律使用**繁體中文**真實搜尋詞（使用者在 YouTube / TikTok 實際搜尋的詞）
- 數量：3–5 個
- 禁止英文關鍵字混入 seo_keywords 陣列（英文 hashtag 由 hashtag_strategy 處理）
- 避免過於泛用詞（如「科學」「知識」），優先具體描述詞（如「蜻蜓翅膀顯微」）

---

## 8. 封面文字疊層規範（EDITING_GUIDE_CAPCUT.txt）

> 封面文字**不寫入圖片**，由剪輯師在 CapCut 手動疊加。

### 字型建議
- **ZH 主標**：粗黑體 / Impact，字級 ≥ 60px，白字 + 黑色描邊 2px
- **ZH 副標**：細明體 / Noto Sans TC，字級 ≥ 36px，白字 + 半透明底條

### 位置建議
- **主標**：畫面垂直 28–35%，水平置中
- **副標**：畫面垂直 42–48%，水平置中

### 字數規則
- 總字數 ≤ 10 字
- 禁止超出畫面邊距
- 禁止覆蓋主體特徵或臉部

### ZH/EN 雙語建議（由 buildCoverHooks 自動生成）
```
title_zh   = subtitle_zh 前 8 字（最精煉 hook）
subtitle_zh = voice_over_zh 首子句，≤ 12 字
title_en    = hook_technique 對應的英文 hook 句
subtitle_en = "Discover what's inside"（固定）
```

---

## 9. 內容安全守衛

### 主題禁止詞（TOPIC_BANNED_TERMS）
以下詞彙為舊會話（眼球/鏡片主題）洩漏詞，**任何主題的 image_prompt 都禁止出現**：
```
crystallin / lens cortex / cataract / protein strand /
refraction anomaly / optical aberration /
photorealistic microscopy style / crystallin fiber /
crystallin layer / crystallin deposit /
lens deposit / cortex surface / microscopy style
```
（packExportService.ts 的 sanitizeImagePrompt() 自動清除）

### Topic Guard（VO/SUB 主題一致性檢查）
- 邏輯：VO 或 SUB 與主題+現象之間，至少共享一個中文雙字（bigram）
- 不通過：標記 `⚠ TOPIC_GUARD: may contain off-topic content — review`
- 位置：EDITING_GUIDE_CAPCUT.txt 各段旁白欄位旁

---

## 10. 語意牆（Semantic Wall — V30.0）

### §10.1 人體部位比喻禁止令

> **核心規則**：嚴禁在腳本任何欄位中，以「人體部位」作為抽象概念的比喻載體。

**禁止範例（使用人體比喻）：**
```
❌ "就像嬰兒第一次呼吸般的誕生"   → 人體比喻
❌ "如皮膚感受陽光的溫度"          → 人體感官比喻
❌ "貝爾的誕生，像一個嬰兒的哭聲" → 人體比喻
❌ "用指尖感受歷史的重量"          → 人體部位比喻
```

**強制替換路徑：**
```
✅ "貝爾誕生" → "專利文書的墨跡"（物件化）
✅ "起源的溫度" → "熔爐的溫度計讀數"（儀器化）
✅ "感受歷史" → "銅版印刷的壓紋痕跡"（材質化）
```

適用欄位：`voice_over_zh` / `subtitle_zh` / `phenomenon` / `mechanism`

---

### §10.2 抽象主題強制三材質規則

> 凡主題屬於以下類別，腳本**至少必須包含三種實體材質描述**：
> 宗教 / 主義 / 哲學 / 情感 / 抽象概念

**觸發類型：**
- 宗教：伊斯蘭教、佛教、基督教、道教、神道教…
- 主義：民主、共產、自由主義、存在主義…
- 哲學：意識、靈魂、自由意志、道德…
- 情感：愛、恨、悲傷、喜悅…

**強制三材質要求（image_prompt 必須包含）：**

| 抽象主題 | 材質 1 | 材質 2 | 材質 3 |
|--------|--------|--------|--------|
| 伊斯蘭教 | blue glazed tile | geometric brass inlay | star-polygon sandstone |
| 佛教 | sandalwood grain | oxidized bronze | incense ash residue |
| 自由主義 | printing press lead type | aged declaration parchment | ink stamp impression |
| 情感（愛/恨） | engraved stone tablet | wax seal | hand-pressed letterpress |

**驗證標準**：`image_prompt.prompt` 中可識別的材質名詞 ≥ 3 個，否則觸發 `ERR_ABSTRACT_NO_MATERIAL`。

---

## 11. 2026 YouTube 生存協議（Survival Protocol V31.0）

> **核心問題**：頻道同質化 = 演算法懲罰 + 觀眾流失。
> AI 量產內容的最大死因：百科全書腔調 + 零立場 + 視覺複製。

### §11.1 人味注入（Anti-Factory Voice Mandate）

**強制規定**：每個完整腳本（3 幕）**至少必須包含 1 個**以下任一元素：

| 元素類型 | 定義 | 示範 |
|---------|------|------|
| **反直覺觀點** | 顛覆主流認知的判斷，有具體依據 | "大部分人以為 X，但實際上 Y 才是關鍵" |
| **主觀評價** | 敘事者的明確立場，而非中性陳述 | "這個設計決策很蠢，但它改變了世界" |
| **矛盾承認** | 主動說出主題的缺陷或爭議 | "這個發明拯救了百萬人，也害死了同樣多人" |
| **時代視角** | 用現代眼光評估歷史決策的荒謬或偉大 | "用今天的標準看，這根本是犯罪" |

**觸發 `ERR_FACTORY_VOICE` 的情況：**
```
❌ 純事實堆疊：只有 who/what/when/where，缺乏 why/so what
❌ 中立敘述：「A 是 B 的重要組成部分」（誰說不重要？）
❌ 零立場收尾：影響幕旁白沒有任何評價性語言，只有事實陳述
```

**ERR_FACTORY_VOICE 嚴重等級**：🟠 HIGH — 觸發 VO 重寫

---

### §11.2 核心立場宣言（Central Thesis Mandate）

**強制規定**：每個腳本必須圍繞**一個明確的「核心立場」**展開。

**核心立場** = 一句話可以概括的、可被反駁的觀點（而非事實描述）。

**生成格式（system prompt 中必須產出）：**
```
central_thesis: 一句具有明確立場的判斷句，≤ 20 字
（此欄位在 JSON 最頂層，不屬於任何 unit）
```

**示例（貝爾主題）：**
```
✅ "貝爾不是發明家，他是歷史上最成功的專利搶奪者"  ← 有立場，可被反駁
✅ "電話不是溝通工具，它是人類第一個焦慮製造機"    ← 有立場，有衝擊
❌ "貝爾在 1876 年發明了電話，改變了人類通訊方式"  ← 純事實，無立場
```

**規則**：三幕旁白的邏輯發展必須服務於 `central_thesis`，而非隨機揭露知識點。
