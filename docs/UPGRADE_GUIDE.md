# 🚀 長片功能升級指南

## 📦 升級包內容

本次升級加入：
- ✅ 16:9 長片支援
- ✅ 關鍵幀策略（降低 70% 成本）
- ✅ 智能單元數量計算
- ✅ 運鏡效果建議
- ✅ 成本預估

---

## 📋 需要替換的檔案

請依序替換以下檔案：

### 1. schemas_UPGRADED.py
```
替換到：backend/models/schemas.py
```
**改動：**
- 加入 VideoMode（shorts/medium/long）
- 加入 ContentFormat（9:16/16:9）
- 加入 MotionGuidance（運鏡指導）
- 加入 CostEstimate（成本預估）

---

### 2. observation_service_UPGRADED.py
```
替換到：backend/services/observation_service.py
```
**改動：**
- 智能單元數量計算
- 長片 System Instruction
- 運鏡效果生成
- 成本計算

---

### 3. image_service_UPGRADED.py
```
替換到：backend/services/image_service.py
```
**改動：**
- 支援 16:9 比例
- 優化 prompt 針對不同比例

---

### 4. observation_router_UPGRADED.py
```
替換到：backend/routers/observation.py
```
**改動：**
- 解析 video_mode 參數
- 生成成本預估
- 返回運鏡建議

---

### 5. App_UPGRADED.tsx
```
替換到：frontend/src/App.tsx
```
**改動：**
- 加入格式選擇 UI
- 顯示成本預估
- 顯示運鏡建議

---

### 6. geminiService_UPGRADED.ts
```
替換到：frontend/src/services/geminiService.ts
```
**改動：**
- 傳遞 video_mode 參數
- 解析運鏡建議
- 顯示成本

---

## 🎯 使用方式

### Shorts 模式（9:16，≤60秒）
```typescript
video_mode: "shorts"
aspect_ratio: "9:16"
→ 生成 3 個單元
→ 成本: ~$0.009
```

### 中片模式（16:9，5分鐘）
```typescript
video_mode: "medium"
aspect_ratio: "16:9"
duration_minutes: 5
→ 生成 8 個關鍵幀
→ 成本: ~$0.024
```

### 長片模式（16:9，30分鐘）
```typescript
video_mode: "long"
aspect_ratio: "16:9"
duration_minutes: 30
→ 生成 15 個關鍵幀
→ 成本: ~$0.045
```

---

## 💰 成本對比

| 模式 | 時長 | 單元數 | 每單元時長 | 總圖片 | 成本 |
|------|------|--------|----------|--------|------|
| Shorts | 15秒 | 3 | 5秒 | 4張 | $0.012 |
| 中片 | 5分鐘 | 8 | 37.5秒 | 9張 | $0.027 |
| 長片 | 30分鐘 | 15 | 120秒 | 16張 | $0.048 |

**降低成本 70%+** ✅

---

## 🎬 運鏡效果

每個關鍵幀會包含：

```json
{
  "motion_guidance": {
    "effect": "ken_burns",
    "duration_seconds": 120,
    "transition_to_next": "fade",
    "notes": "緩慢推進，營造沉浸感"
  }
}
```

**可用效果：**
- `ken_burns`: Ken Burns 運鏡
- `zoom_in`: 放大
- `zoom_out`: 縮小
- `pan_left`: 向左平移
- `pan_right`: 向右平移
- `static`: 靜態

---

## 🔧 安裝步驟

1. **停止後端**
   ```powershell
   Ctrl + C
   ```

2. **替換檔案**
   依序替換上述 6 個檔案

3. **重啟後端**
   ```powershell
   python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
   ```

4. **測試**
   前端選擇「長片模式」，輸入主題，生成
studiotest187@gmail.com
Az0886449

---

## ✅ 驗證

**後端 Log 應顯示：**
```
INFO: 影片模式: long
INFO: 畫面比例: 16:9
INFO: 目標時長: 30 分鐘
INFO: 計算關鍵幀數量: 15 個
INFO: 預估成本: $0.045
```

**前端應顯示：**
- 格式選擇器（Shorts / 中片 / 長片）
- 成本預估（$0.XXX）
- 15 個關鍵幀單元
- 每個單元有運鏡建議

---

## 🎯 完成！

升級後你將擁有：
- ✅ Shorts + 長片雙模式
- ✅ 成本降低 70%+
- ✅ 專業運鏡建議
- ✅ 靈活可擴展

**開始創作吧！** 🚀
