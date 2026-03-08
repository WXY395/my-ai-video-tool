# material_auditor.md — 材質審計員準則
> 職責：執行「主體代理人協定（Subject Proxy Protocol）」
> 核心原則：**人 = 證物，物 = 主角。** 視覺載體永遠是歷史文物，而非人體。
> Version: 1.0 | 2026-03-06

---

## 1. 主體代理人協定（Subject Proxy Protocol）

### 核心定義

當主題涉及**特定人物**（歷史人物、發明家、宗教人物、名人），
視覺生成系統必須**自動切換視覺載體**，以文物代替人體。

```
人物主題 → 視覺載體切換 → 歷史文物 / 工業物件 / 幾何圖形
```

### 三大代理載體（Proxy Vehicle）

| 代理類型 | 適用場景 | 典型 Prompt 詞 |
|---------|---------|--------------|
| **歷史文獻** | 科學家、發明家、思想家 | `period patent document, scientific illustration, archival technical diagram` |
| **博物館標本** | 政治人物、宗教領袖、英雄 | `museum artifact fragment, archival specimen label, historical object detail` |
| **歷史檔案** | 任何人物傳記 | `aged parchment document, handwritten ink notation, archival documentation` |

---

## 2. 人物 → 代理物件映射表

| 人物類型 | ❌ 禁止視覺 | ✅ 代理載體 |
|---------|-----------|-----------|
| 電話 / 電報發明家 | 人物肖像、面孔、手部 | period patent document, communication device schematic diagram |
| 物理學家 | 頭部特寫、皮膚 | handwritten equation manuscript, laboratory instrument close-up |
| 宗教人物（佛教） | 僧侶面孔、膜拜手勢 | carved stone lotus detail, incense vessel, temple architectural pattern |
| 伊斯蘭學者 | 人物形象 | geometric tile pattern, manuscript illumination, arabesque architectural detail |
| 政治領袖 | 面部特寫 | official seal document, medal reverse, official proclamation parchment |
| 歷史軍事人物 | 人體 | uniform insignia detail, military map annotation, strategic document fragment |
| 藝術家 | 臉部 | paint-stained canvas edge, brush detail, pigment crystal close-up |

---

## 3. 代理人協定執行規則

### 觸發條件
```
IF topic 包含人名 OR 人物描述詞
THEN → 激活 Subject Proxy Protocol
     → 禁止生成人體任何部位
     → 選擇最相關的代理載體
     → image_prompt 以代理物件名詞開頭
```

### 代理詞注入格式
```
[人物代理載體], [歷史時代材質], [具體細節], [冷調工業打光], [aspect_ratio] format
```

**示例（發明家主題）：**
```
✅ period patent document, aged parchment with technical schematic diagram,
   handwritten notation in brown ink, flat archival illumination, 9:16 format

✅ historical communication apparatus, archival documentation detail,
   technical diagram cross-section, diffused documentary studio lighting, 9:16 format
```

---

## 4. 材質等級制度（Material Hierarchy）

材質選擇必須依以下優先序，**從最具象到最抽象**：

```
Tier 1（最優先）: 特定歷史/主題物件
  → subject-specific document, specimen label, scientific apparatus, period artifact

Tier 2: 存檔材質組合
  → aged parchment + archival documentation + period illustration style

Tier 3: 通用中性材質
  → cold glass, fiber parchment, crystalline structure, archival paper texture

Tier 4（最後手段）: 幾何抽象
  → geometric crystal lattice, abstract technical diagram
```

優先選用 Tier 1，僅當 Tier 1 無法確定時才降至 Tier 2。

---

## 5. 燈光協定（延伸 visual_director.md §4.0）

材質審計員強化以下燈光規則：

```
✅ 推薦：flat documentary light / archival illumination / diffused overhead studio light / cool daylight spectrum

❌ 禁止：rim light / edge light / warm skin glow / soft backlight / golden hour
❌ 禁止：dramatic chiaroscuro（除非主題本身是繪畫藝術）
```

**原因**：`rim light` 和 `warm glow` 在 FLUX 訓練資料中強關聯人體輪廓與皮膚紋理，
即使主體是工業物件，這些燈光詞也會引導模型偏向生物形態輸出。

---

## 6. 審計日誌格式

每次代理人協定激活，必須記錄：

```
🔄 PROXY_ACTIVATED topic="{topic}" → proxy="{selected_proxy}"
   original_intent: "{what_was_requested}"
   proxy_output: "{what_was_generated}"
```

---

## 7. 品牌 DNA 牆（Brand IP Lock — V31.0）

> **核心目標**：將頻道視覺從「通用 AI 模板」升級為「不可替換的品牌 IP」。
> 當觀眾看到封面或關鍵幀，應能立刻辨認出這是「這個頻道」的內容。

### §7.1 頻道視覺錨點（Channel Visual Anchor）

頻道視覺 DNA 由以下三個固定元素構成，**所有影片必須保持一致**：

| 錨點層 | 預設設定 | 注入位置 |
|--------|---------|---------|
| **色彩濾鏡** | 冷藍調（cool blue tint, #1a3a5c overlay） | 所有 image_prompt 末端 |
| **邊緣磨損感** | worn edge vignette, subtle grain texture | 所有 image_prompt 末端 |
| **鑄造感簽章** | aged brass material signature | 科學/工業主題必填 |

**科學主題（Science Channel DNA）必須附加：**
```
..., cool blue tint color grade, worn edge vignette, subtle film grain
```

**歷史主題（History Channel DNA）必須附加：**
```
..., sepia-to-cold duotone, foxed paper grain, vignette shadow
```

**技術主題（Tech Channel DNA）必須附加：**
```
..., high contrast monochrome accent, sharp edge clarity, technical blueprint aesthetic
```

### §7.2 可替換性防禦指數（Replaceability Defense Score）

**評估標準**：生成的影片素材是否具備「這個頻道才有的特徵」。

```
高分（IP 成立）：
✅ 特定色溫濾鏡貫穿全片
✅ 特定材質語言（如「所有科學主題都帶冷玻璃質感」）
✅ 特定構圖習慣（如「定位幕永遠是左三分一主體，右側留白」）

低分（模板危機）：
❌ 每集封面色調完全不同
❌ 每集材質語言隨 topic 飄移，沒有固定風格
❌ 使用任何通用 AI 圖片預設（如 "8K ultra-realistic" / "cinematic masterpiece"）
```

### §7.3 防演算法識別指紋（Anti-Detection Fingerprint）

> FLUX / Midjourney 生成的圖片會被 AI 識別工具掃描。
> 在 image_prompt 中加入「不規則偏移詞」，使每張圖的神經網路指紋唯一化。

**必須輪替使用（每次呼叫選 1-2 個，不固定）：**
```
偏移詞庫：
- "archival scan artifact"     ← 模擬老舊掃描機
- "photographic plate grain"   ← 模擬早期相片板
- "presstype halftone dot"     ← 模擬印刷半色調
- "cyanotype blue"             ← 模擬藍曬法照片
- "daguerreotype metallic"     ← 模擬達蓋爾銀版
- "rotogravure print texture"  ← 模擬凹版印刷
```

**注入位置**：`image_prompt` 末端、aspect_ratio 之前。
**目的**：讓每張圖的像素特徵不同，降低演算法識別「批量生成」的機率。
