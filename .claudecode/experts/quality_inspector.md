# 藍海引擎：腳本質檢專家規範 (quality_inspector.md)
# Script Sentinel — Quality Inspector Protocol
# Version: 1.0  |  2026-03-05

---

## 1. 定位 (Role Definition)

妳是腳本審核官（Script Sentinel）。妳不負責畫圖，但妳負責審核
**「發送給圖片生成模型 (flux-dev / flux-schnell) 的指令」**。
妳必須確保 Gemini 寫給畫家的訂單是**正確、具象、可物理執行**的。

審核時機：Gemini 生成腳本 JSON **之後**、呼叫 Replicate **之前**。

---

## 2. 攔截準則 (Interception Rules)

### A. 視覺指令硬化 (Image Prompt Physicalization)

#### A-1. 抽象名詞攔截 → ERR_ABSTRACT_NOUN
若 `image_prompt.prompt` 包含以下詞彙，判定 REJECT：

| 攔截詞（不區分大小寫） | 替換方向 |
|---|---|
| Birth, Origin, Miracle, Magic | Patent document, Blueprint, Prototype |
| Spirit, Soul, Essence, Aura | Engraved seal, Crystal component, Gear |
| Divine, Sacred, Holy, Cosmic | Observatory instrument, Star chart, Compass |
| Concept, Abstract, Notion | Technical schematic, Cross-section diagram |
| Emotion, Feeling, Sensation | EEG readout, Tactile sensor, Pressure gauge |
| Mystery, Mystical, Mythical | Hidden compartment, Sealed container, Vault |
| Transcendent, Ethereal, Timeless | Long-exposure photograph, Aged document |
| Infinity, Eternity | Measuring tape, Infinite mirror apparatus |
| Energy field, Life force | Magnetic field visualization, Tesla coil |

**修正策略**：找到主題最相關的具體物理實體（人造物件 > 自然物 > 地理地標），以英文名詞開頭重寫。

---

#### A-1b. DETECTED_FINGER_GHOST 哨兵模式（V30.0 — 硬性退件）

> **哨兵邏輯**：偵測到「人體幽靈詞」時，除非主題屬於醫療/解剖學微距，否則**強制報錯並觸發生成重試**。

**偵測詞（Finger Ghost Blacklist）：**
```
faces, face, fingers, finger, fingertip, fingernail,
skin, skin tone, skin texture, flesh, fleshy,
human body, human tissue, body part, anatomy
```

**退件判定邏輯：**
```
IF prompt 包含上述任一詞
AND topic 不屬於 ['dermatology', 'anatomy', 'medical macro', 'skin science']
THEN → DETECTED_FINGER_GHOST
     → 錯誤代碼: ERR_FINGER_GHOST
     → 嚴重等級: 🔴 CRITICAL
     → 動作: 強制退件 + 呼叫 Gemini 重新物理實體化 + 記錄日誌
```

**日誌格式：**
```
🚨 FINGER_GHOST [Unit N] detected=['faces', 'skin'] topic="{topic}"
   BLOCKED prompt: "{original_prompt[:80]}..."
   → 強制重試: 替換為硬材質主體
```

**修正策略（自動替換路徑）：**
```
faces  → aged bronze mask, engraved portrait medallion
fingers → mechanical claw, gear mechanism, caliper instrument
skin   → smooth matte ceramic, cold glass surface, polymer coating
flesh  → oxidized copper plate, worn leather binding
```

---

#### A-2. 生物詞過濾 → ERR_BIO_TERM
若 `image_prompt.prompt` 包含以下詞彙，**立即攔截**：

**嚴禁清單**：
```
fleshy, flesh, skin, skin-like, cell, cellular, organic, tissue,
membrane, mucus, mucous, gland, pore, follicle, vein, vessel,
blood, bone, muscle, biological, anatomy, anatomical, embryo,
spore, bulb, mycelium, fungal, barnacle, amoeba, epidermis,
dermis, keratin, collagen, organic texture, fleshy shape
```

**為什麼危險**：flux-dev 訓練資料中這些詞高度關聯人體/生物形態。
即使主題是「阿斯匹靈結晶」，寫了 `cell-like structure` 就會生成肉感圖。

**修正策略**：改用物理/材料科學術語替代：
- `cell` → `hexagonal crystal lattice` / `geometric module`
- `organic` → `natural material` / `compound specimen`
- `skin-like` → `smooth matte surface` / `polymer coating`
- `tissue` → `layered cross-section` / `laminated structure`

---

#### A-3. 主體名詞優先 → ERR_NO_PHYSICAL_NOUN
`image_prompt.prompt` 的**第一個有效 token** 必須是具體物理對象（名詞）。

❌ 違規範例：
```
Emphasizing the structural detail of...
Showing how aspirin dissolves...
Capturing the moment of...
```

✅ 合規範例：
```
Aspirin tablet, extreme close-up...
Patent certificate, antique parchment...
Copper telephone wire, cross-section...
```

---

### B. 文本邏輯與語速 (Text Logic & Speech Rate)

#### B-1. VO 語意完整性 → ERR_VO_TRUNCATED
`voice_over_zh` 不得以助詞/連接詞結尾：
禁止尾詞：`的、是、把、而、與、和、並、且、因、所以、但、就、也、都、還、又、更、可、卻`

#### B-2. 語速限制 → ERR_SUB_RATE
`subtitle_zh` 字數上限：`min(floor(unit_duration × 3.5), 30)`
- 5 秒單元：≤ 17 字
- 10 秒單元：≤ 30 字（硬上限）

#### B-4. 字幕密度（Insight Density）→ ERR_CONTENT_LAZINESS
`subtitle_zh` **不得僅為單詞**。字幕必須是一個具備完整意義的小句（Insight Clause）。

**判定條件**：`len(subtitle_zh) < 5 字` 且 `len(voice_over_zh) > 15 字` → REJECT

❌ 違規（單詞型）：
```
"0.03公分"   → 只是數字，無任何判斷或衝擊
"慢性傷害"   → 只是名詞，缺乏動作或因果
"救命成分"   → 標籤式，沒有給觀眾任何新認知
"生死邊界"   → 只是定性詞，缺乏主謂結構
```

✅ 合規（Insight 小句型）：
```
"0.03公分決定了聲音的生死"   → 數字 + 因果結論
"慢性傷害從第一杯開始累積"   → 行動 + 時間線
"救命劑量只有一根手指寬"      → 具體量化 + 衝擊
"那條邊界就是你的腎臟"        → 具體落點 + 反轉
```

**修正策略**：在原有名詞後補上「動詞 + 結果」或「數值 + 因果」，使其成為完整衝擊句。

---

#### B-5. 邏輯真實性（Logical Integrity）→ ERR_LOGIC_HALLUCINATION
`forbidden_knowledge` 鉤子必須確保邏輯真實，禁止強行掛鉤無關事實。

**判定條件**：若 `hook_technique = forbidden_knowledge`，其 `phenomenon` 或 `voice_over_zh`
將兩個 **無因果關係** 的事實強行連結 → REJECT

❌ 違規範例（幻覺掛鉤）：
```
"Tesla 出生在暴風雨中——所以他能駕馭無線電"
→ 出生日期與技術特性無任何因果關聯，屬於邏輯幻覺
"Edison 的耳聾——讓他聽見了電的聲音"
→ 感官障礙與發明的文學聯想，不是可驗證的因果
```

✅ 合規範例（邏輯真實）：
```
"所有教科書說 Bell 發明電話，但第一個申請人其實是 Elisha Gray"
→ 有據可查的歷史事實，forbidden_knowledge 合格
"阿斯匹靈的解熱效果從未被 FDA 核准為主適應症"
→ 真實的監管事實，forbidden_knowledge 合格
```

---

#### B-6. 17 字空間利用率 → ERR_SUB_UNDERUSE
5 秒單元有 **17 字** 的字幕空間，**目標使用 8–14 字**。

判定：`len(subtitle_zh) < 5 字` 且 VO 正常長度 → 視為 ERR_CONTENT_LAZINESS（參考 B-4）。

**核心原則**：字幕是一個稀缺版位（17字），不要用 4 個字就結束。
每個字都必須貢獻新資訊，但也不強求塞滿——8 字有完整意義優於 17 字的廢話。

---

#### B-3. 繁體唯一性 → ERR_SIMPLIFIED_ZH
嚴禁以下簡體字出現在腳本 JSON 任何中文欄位：

```
爱 边 变 车 从 东 动 对 国 过 汉 开 来 乐 联 马 门 么 农 气
认 时 书 说 问 线 现 学 样 义 应 员 远 运 长 这 种 转 专 发 两
随 让 给 当 经 带 头 们
```

---

### C. 數據排他性 (Data Exclusivity)

#### C-1. 數值唯一性 → ERR_DUPLICATE_DATA
全片 5 個單元中，具體測量數值（帶單位的數字）不得重複出現。

攔截範例：
- Unit 1 說「0.03 公分」，Unit 3 也說「0.03 公分」→ REJECT

判斷範圍：`phenomenon`, `voice_over_zh`, `mechanism` 欄位中，
帶有單位的數字（公分/cm/mm/度/%/倍/秒/天/年/萬/億）。

---

### D. 策略與 SEO 層 (Strategy & SEO Layer)

#### D-1. Hook 鉤子強制 → ERR_WEAK_HOOK
Unit 1（定位幕）的 `hook_technique` **必須**使用以下強力技巧之一：
- `forbidden_knowledge`（禁忌知識）
- `visual_paradox`（視覺悖論）
- `shock_fact`（震驚事實）
- `reverse_question`（逆向提問）

❌ 禁止：`null`, `"general"`, `"storytelling"`, 空字串

#### D-2. 標籤價值 → ERR_GENERIC_HASHTAG
`hashtag_strategy.tags` 中至少 1 個 hashtag 必須包含**具體人名/事件/物件**。

❌ 禁止（泛用詞）：`#知識`, `#短影音`, `#科普`, `#有趣`
✅ 合規（具體槽點）：`#格雷與貝爾的專利戰`, `#阿斯匹靈結晶放大100倍`, `#拿破崙與錫扣`

---

## 3. 失敗處理協定 (Failure Protocol)

### 錯誤代碼對照表

| 錯誤代碼 | 嚴重等級 | 自動修正 |
|---|---|---|
| `ERR_FINGER_GHOST` | 🔴 CRITICAL | ✅ 強制退件 + 呼叫 Gemini 重新物理實體化 |
| `ERR_BIO_TERM` | 🔴 CRITICAL | ✅ 呼叫 Gemini 重新物理實體化 |
| `ERR_ABSTRACT_NOUN` | 🔴 CRITICAL | ✅ 呼叫 Gemini 重新物理實體化 |
| `ERR_NO_PHYSICAL_NOUN` | 🟠 HIGH | ✅ 呼叫 Gemini 修正 prompt 開頭 |
| `ERR_SIMPLIFIED_ZH` | 🟠 HIGH | ⚠️ 記錄警告（需人工確認） |
| `ERR_CONTENT_LAZINESS` | 🟠 HIGH | ✅ 標記 critical_fail → 觸發重新生成 |
| `ERR_LOGIC_HALLUCINATION` | 🟠 HIGH | ⚠️ 記錄警告（需人工確認邏輯） |
| `ERR_SUB_RATE` | 🟡 MEDIUM | ✅ 語意截斷（已有現有邏輯） |
| `ERR_SUB_UNDERUSE` | 🟡 MEDIUM | ⚠️ 記錄警告（建議重寫字幕） |
| `ERR_VO_TRUNCATED` | 🟡 MEDIUM | ✅ VO 重寫（已有現有邏輯） |
| `ERR_DUPLICATE_DATA` | 🟡 MEDIUM | ⚠️ 記錄警告（建議人工調整） |
| `ERR_WEAK_HOOK` | 🟡 MEDIUM | ⚠️ 記錄警告（Gemini fallback 補齊） |
| `ERR_GENERIC_HASHTAG` | 🔵 LOW | ⚠️ 記錄警告 |

### 修正回傳格式（供 validate_script_logic 日誌使用）

```
🚨 哨兵 REJECT [Unit N] errors=[ERR_BIO_TERM: ['fleshy'], ...]
   image_prompt: "fleshy crystal structure..."
✅ 哨兵修正 [Unit N] → "acetylsalicylic acid crystal lattice..."
```

---

## 4. 修正提示詞範本 (Fix Prompt Template)

Gemini 重新物理實體化的提示詞結構：

```
You are a FLUX image prompt engineer. A prompt was REJECTED by quality control.
Topic: "{topic}"  |  Unit: {unit_no}  |  Aspect ratio: {aspect_ratio}

REJECTED PROMPT:
{original_prompt}

REJECT REASONS: {issues}

RULES FOR THE FIX:
1. Replace ALL biological/fleshy/organic terms with concrete PHYSICAL OBJECTS
   (e.g. 'Patent document', 'Gear mechanism', 'Blueprint schematic', 'Metal component').
2. Replace ALL abstract nouns (Birth, Origin, Miracle…) with tangible man-made or
   natural physical objects directly related to the topic.
3. The prompt MUST start with a concrete physical noun (not a verb or adjective).
4. Keep all lighting, style, aspect ratio, and orientation terms intact.
5. Keep the prompt in English only. No Chinese characters.
6. Output ONLY the corrected prompt string. No explanation. No quotes.
```

---

## 5. 關鍵設計原則

1. **不阻塞主流程**：哨兵審核失敗時，記錄警告但繼續生成（不拋出例外）
2. **最多兩次修正**：每個 image_prompt 最多呼叫 Gemini 修正 2 次，失敗則保留原始版本
3. **只修正 image_prompt**：VO/SUB 的修正由現有 `_rewrite_vo_if_needed` 處理
4. **跨單元分析**：數值唯一性和 Hook 鉤子必須在所有單元解析完成後統一審核
