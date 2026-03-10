# Grok Veo Prompt Guide — 埃及的由來
> V35.9.8 動態手冊 | 2026-03-11
> 來源：`bridge/official_core/outputs/埃及的由來/runbook.md`
> 規則：`skills/absurd_logic.skill` + `docs/constitution_honest_observer.md`
> 模式：6 幕 > 3 幕 → **極簡物理動作**（保障 Veo 生成成功率）

---

## 使用說明

1. 直接複製「Grok Copy-Paste Prompt」欄位全文貼入 Veo / Grok 介面
2. 每個 prompt 已內建具體物理數值（憲法 R-4 要求），不需補充
3. 禁止在提交前加入情緒詞（funny / amazing / breathtaking 等）
4. 建議生成 6 秒 raw footage，剪輯區間參照「Cut」欄

---

## Veo 提示詞總表

| CH | 秒數 | 模組 | VO / SUB | Cut | Grok Copy-Paste Prompt |
|----|------|------|----------|-----|------------------------|
| 01 | 3.13s | MODULE 02 比例失衡 | 撒哈拉沙漠超缺水！ / 史上最乾旱地區 | 01:00→04:00 | Surreal miniature diorama, 3D clay texture, macro lens, tilt-shift bokeh. A 0.7cm clay figurine stands at the base of an 18cm sand dune — scale ratio 1:25.7, label visible in lower frame. Figurine takes one step forward at normal walking pace. Does not look up. Camera fixed at ground level, figurine anchored lower-left. 9:16 vertical, clay stop-motion, studio lighting. |
| 07 | 2.17s | MODULE 01 重心崩壞 | 當年埃及還分南北 / 戰區伺服器 | 01:00→04:00 | Surreal miniature diorama, 3D clay texture, macro lens, tilt-shift bokeh. Two 1.2cm clay figurines — white bowling-pin crown (0.8cm) and red basket crown (0.6cm) — face each other at 3cm distance. At t=0.8s both simultaneously exceed center-of-gravity threshold in opposite directions, falling at identical 47° angles. White crown arcs 4.2cm, red crown 3.8cm. Both figurines remain fallen. Camera fixed. 9:16 vertical, clay stop-motion, studio lighting. |
| 09 | 2.67s | MODULE 10 莊嚴崩潰 | 戴上雙冠就變老大 / 霸氣側漏的帽子 | 01:00→04:00 | Surreal miniature diorama, 3D clay texture, macro lens, tilt-shift bokeh. A 1.1cm clay figurine initiates crown placement ceremony — posture upright, both arms raised to receive a 1.4cm double crown (127% of figurine head diameter). At t=1.2s crown weight exceeds neck support threshold. Head tilts 34° forward. Crown continues to table surface. Figurine maintains ceremonial arm position throughout. Camera fixed. 9:16 vertical, clay stop-motion, studio lighting. |
| 11 | 2.33s | MODULE 06 微型自尊 | 算數觀星全都自己來 / 數學不會就真不會 | 01:00→04:00 | Surreal miniature diorama, 3D clay texture, macro lens, tilt-shift bokeh. A 0.9cm clay scholar arranges papyrus scrolls each 2.7cm tall — 3x figurine height. Head-to-body ratio 1.8:1. Examines star chart using reed stick 1.4x arm length. Head does not tilt upward despite scroll height. Movement deliberate, unhurried. Camera fixed 45° overhead. 9:16 vertical, clay stop-motion, studio lighting. |
| 14 | 2.83s | MODULE 10 莊嚴崩潰 | 其實是為了穩固江山 / 高端洗腦術 | 01:00→04:00 | Surreal miniature diorama, 3D clay texture, macro lens, tilt-shift bokeh. A 1.0cm clay pharaoh figurine extends arm holding a 1.8cm scepter (180% body height) in official decree posture. At t=1.4s scepter-to-body torque ratio exceeds base friction threshold. Figurine rotates 90° forward at uniform speed. Scepter lands 5.1cm from figurine. Figurine remains at 90° from vertical. Camera fixed. 9:16 vertical, clay stop-motion, studio lighting. |
| 18 | 3.03s | MODULE 09 冠軍噴濺協定 | 感謝尼羅河的打賞！ / 感謝大哥抖內 | 01:00→04:00 | Surreal miniature diorama, 3D clay texture, macro lens, tilt-shift bokeh. Water droplet 8mm diameter impacts miniature Nile delta surface (22cm × 8cm) at 3.2m/s. Crown splash: 12 symmetric jets each 14mm tall, arc angle 62°. Crown duration 47ms. Two 0.8cm clay figurines visible at delta edge. Camera macro fixed. 9:16 vertical, clay stop-motion, studio lighting. |

---

## 模組分配總覽

| 模組 | 使用次數 | 套用場景 |
|---|---|---|
| MODULE 01 重心崩壞 | 1 | CH07 |
| MODULE 02 比例失衡 | 1 | CH01 |
| MODULE 06 微型自尊 | 1 | CH11 |
| MODULE 09 冠軍噴濺協定 | 1 | CH18 |
| MODULE 10 莊嚴崩潰 | 2 | CH09, CH14 |

---

## Zero Emotion 驗證

以下詞彙已從所有 prompt 中驗證移除：

| 違規詞 | 原文出現位置 | 處理 |
|---|---|---|
| `breathtaking` | 舊 CH01 Veo | 已刪除，替換為 scale ratio 1:25.7 |
| `magnificent` | 舊 CH09 Veo | 已刪除，替換為 127% head diameter |
| `charmingly` | 舊 CH14 Veo | 已刪除，替換為 torque ratio 數值 |
| `generous` | 舊 CH18 Veo | 已刪除，替換為 crown splash 47ms |

---

## 物理數值錨點清單（R-4 合規確認）

| CH | 數值錨點 |
|---|---|
| 01 | scale ratio 1:25.7，dune height 18cm，figurine 0.7cm |
| 07 | fall angle 47°，crown arc 4.2cm / 3.8cm，t=0.8s |
| 09 | crown 127% head diameter，tilt 34°，t=1.2s |
| 11 | scroll height 2.7cm = 3x，head-body ratio 1.8:1，reed 1.4x arm |
| 14 | scepter 180% body height，rotation 90°，landing distance 5.1cm |
| 18 | droplet 8mm，velocity 3.2m/s，12 jets × 14mm，47ms |

全部 6 幕均包含 ≥ 2 個具體物理數值。✅

---

> 總計：**6 幕已優化**
> 生成時間：2026-03-11 V35.9.8
> 下次更新：新增 topic 後執行同一掃描流程
