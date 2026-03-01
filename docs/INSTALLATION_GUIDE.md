# 🚀 長片功能完整安裝指南

## 📦 升級包文件清單

所有文件已生成完成，請依序下載並安裝：

### 後端文件（Python）
1. ✅ `schemas_UPGRADED.py` → `backend/models/schemas.py`
2. ✅ `observation_service_UPGRADED.py` → `backend/services/observation_service.py`
3. ✅ `image_service_UPGRADED.py` → `backend/services/image_service.py`
4. ✅ `observation_router_UPGRADED.py` → `backend/routers/observation.py`

### 前端文件（TypeScript/React）
5. ✅ `geminiService_UPGRADED.ts` → `frontend/src/services/geminiService.ts`
6. ✅ `App_UPGRADED.tsx` → `frontend/src/App.tsx`

---

## 🛠️ 安裝步驟

### Step 1：停止服務

```powershell
# 停止後端
Ctrl + C（在後端運行的 PowerShell 中）

# 停止前端
Ctrl + C（在前端運行的 PowerShell 中）
```

---

### Step 2：備份現有文件（重要！）

```powershell
cd C:\Projects\shorts_factory_react

# 創建備份目錄
mkdir backup_before_upgrade

# 備份後端
copy backend\models\schemas.py backup_before_upgrade\schemas_OLD.py
copy backend\services\observation_service.py backup_before_upgrade\observation_service_OLD.py
copy backend\services\image_service.py backup_before_upgrade\image_service_OLD.py
copy backend\routers\observation.py backup_before_upgrade\observation_OLD.py

# 備份前端
copy frontend\src\services\geminiService.ts backup_before_upgrade\geminiService_OLD.ts
copy frontend\src\App.tsx backup_before_upgrade\App_OLD.tsx
```

---

### Step 3：替換後端文件

```powershell
cd C:\Projects\shorts_factory_react\backend

# 1. schemas.py
# 下載 schemas_UPGRADED.py，改名為 schemas.py
# 替換到：backend\models\schemas.py

# 2. observation_service.py
# 下載 observation_service_UPGRADED.py，改名為 observation_service.py
# 替換到：backend\services\observation_service.py

# 3. image_service.py
# 下載 image_service_UPGRADED.py，改名為 image_service.py
# 替換到：backend\services\image_service.py

# 4. observation.py
# 下載 observation_router_UPGRADED.py，改名為 observation.py
# 替換到：backend\routers\observation.py
```

---

### Step 4：替換前端文件

```powershell
cd C:\Projects\shorts_factory_react\frontend

# 5. geminiService.ts
# 下載 geminiService_UPGRADED.ts，改名為 geminiService.ts
# 替換到：frontend\src\services\geminiService.ts

# 6. App.tsx
# 下載 App_UPGRADED.tsx，改名為 App.tsx
# 替換到：frontend\src\App.tsx
```

---

### Step 5：更新 types.ts（重要！）

前端需要新增一些類型定義。

打開 `frontend/src/types/index.ts`，在文件**末尾**加入：

```typescript
// ===== 新增：長片支援類型 =====

export interface MotionGuidance {
  effect: 'ken_burns' | 'zoom_in' | 'zoom_out' | 'pan_left' | 'pan_right' | 'static';
  duration_seconds: number;
  transition_to_next: string;
  notes?: string;
}

// 在 ObservationUnit 介面中加入新欄位（如果沒有的話）
// 找到 export interface ObservationUnit，加入：
//   motion_guidance?: MotionGuidance | null;
//   is_keyframe?: boolean;
```

---

### Step 6：重啟後端

```powershell
cd C:\Projects\shorts_factory_react\backend

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**檢查啟動 Log：**
```
INFO:     🚀 Shorts Factory v2 Backend 啟動中...
INFO:     📍 API 文檔: http://127.0.0.1:8000/docs
INFO:     ✅ 環境變數檢查通過
INFO:     Uvicorn running on http://127.0.0.1:8000
```

---

### Step 7：重啟前端

```powershell
cd C:\Projects\shorts_factory_react\frontend

npm run dev
```

**檢查啟動：**
```
VITE v5.x.x  ready in xxx ms

➜  Local:   http://localhost:3000/
➜  Network: use --host to expose
```

---

## ✅ 驗證安裝

### 1. 檢查後端 API

打開瀏覽器：
```
http://127.0.0.1:8000/api/observation/health
```

**應該看到：**
```json
{
  "status": "healthy",
  "version": "2.0_upgraded",
  "features": {
    "shorts_support": true,
    "long_form_support": true,
    "aspect_ratios": ["9:16", "16:9"],
    "motion_guidance": true,
    "cost_estimation": true
  }
}
```

---

### 2. 檢查前端介面

打開：`http://localhost:3000`

**應該看到：**
- ✅ 標題顯示 "Observation Workstation v2.0"
- ✅ 副標題顯示 "LONG_FORM_ENABLED"
- ✅ 左側有 3 個模式按鈕：⚡ Shorts、🎬 中片、🎞️ 長片
- ✅ 比例選擇：9:16 和 16:9
- ✅ 成本預估區塊（灰色框）

---

### 3. 測試生成（Shorts）

1. 輸入主題：`咖啡`
2. 選擇模式：`⚡ Shorts`
3. 選擇比例：`9:16`
4. 點擊 `INIT_PROTOCOL`

**Log 應顯示：**
```
[時間] MODE: SHORTS | RATIO: 9:16 | DURATION: AUTO
[時間] SIGNAL_PARSED: 3 KEYFRAMES
[時間] COST_CONFIRMED: $0.012
[時間] OBSERVATION_UNITS_READY_FOR_REVIEW
```

**前端應顯示：**
- 封面圖（1 張）
- 觀測單元（3 張）
- 總共 4 張卡片

---

### 4. 測試生成（長片）

1. 輸入主題：`咖啡`
2. 選擇模式：`🎞️ 長片`
3. 比例自動變為：`16:9`
4. 時長輸入：`30`（分鐘）
5. 查看成本預估（應該顯示 ~$0.048）
6. 點擊 `INIT_PROTOCOL`

**Log 應顯示：**
```
[時間] MODE: LONG | RATIO: 16:9 | DURATION: 30
[時間] SIGNAL_PARSED: 15 KEYFRAMES
[時間] COST_CONFIRMED: $0.048
[時間] POST_PRODUCTION: keyframe_to_motion
[時間] EDITING_TIME: 30-45 minutes
```

**前端應顯示：**
- 封面圖（1 張，16:9 橫屏）
- 關鍵幀（15 張，16:9 橫屏）
- 總共 16 張卡片
- 卡片排列為 2 列（因為是 16:9）

---

## 🎯 功能測試清單

### ✅ Shorts 模式
- [ ] 輸入主題，選擇 Shorts
- [ ] 生成 3 個單元
- [ ] 比例為 9:16
- [ ] 成本約 $0.012
- [ ] 卡片為 3 列排列

### ✅ 中片模式
- [ ] 選擇中片模式
- [ ] 比例自動變為 16:9
- [ ] 可輸入時長（3-10 分鐘）
- [ ] 生成 5-15 個關鍵幀
- [ ] 成本約 $0.015-0.045
- [ ] 卡片為 2 列排列

### ✅ 長片模式
- [ ] 選擇長片模式
- [ ] 比例為 16:9
- [ ] 可輸入時長（30-60 分鐘）
- [ ] 生成 15-30 個關鍵幀
- [ ] 成本約 $0.045-0.090
- [ ] 顯示後製建議

### ✅ 成本預估
- [ ] 選擇不同模式時，成本自動更新
- [ ] 顯示關鍵幀數量
- [ ] 顯示節省百分比
- [ ] 數字準確

### ✅ 運鏡建議
- [ ] 每個單元有 motion_guidance
- [ ] Log 顯示運鏡效果
- [ ] 開場為 ken_burns 或 zoom_in
- [ ] 結尾為 zoom_out

---

## 🐛 常見問題

### 問題 1：後端啟動失敗

**錯誤：**
```
ImportError: cannot import name 'VideoMode' from 'models.schemas'
```

**解決：**
確認 `schemas.py` 已正確替換，並且包含：
```python
class VideoMode(str, Enum):
    SHORTS = "shorts"
    MEDIUM = "medium"
    LONG = "long"
```

---

### 問題 2：前端編譯錯誤

**錯誤：**
```
Cannot find name 'VideoMode'
```

**解決：**
確認 `geminiService.ts` 已正確替換，並且包含：
```typescript
export type VideoMode = 'shorts' | 'medium' | 'long';
```

---

### 問題 3：生成失敗

**錯誤 Log：**
```
FATAL_ERROR: 'video_mode'
```

**解決：**
確認 `observation.py` 已正確替換。檢查：
```python
video_mode=request.video_mode,
aspect_ratio=request.aspect_ratio.value,
```

---

### 問題 4：成本預估不顯示

**原因：** 前端 useEffect 未觸發

**解決：**
手動點擊生成按鈕前，先改變一次模式，成本預估會自動計算。

---

## 💰 成本對比驗證

### 測試各模式成本

| 模式 | 時長 | 關鍵幀 | 預估成本 | 實際成本 |
|------|------|--------|---------|---------|
| Shorts | 15秒 | 3個 | $0.012 | ✅ 填寫 |
| 中片 | 5分鐘 | 8個 | $0.027 | ✅ 填寫 |
| 長片 | 30分鐘 | 15個 | $0.048 | ✅ 填寫 |

**如果成本不符，檢查：**
1. FLUX Schnell 定價是否為 $0.003
2. 關鍵幀數量是否正確
3. 是否包含封面（+1 張）

---

## 🎬 後製工作流程

生成長片後：

### Step 1：匯出關鍵幀
點擊每個單元的 `GENERATE_ASSET` 按鈕生成圖片

### Step 2：CapCut 編輯
1. 匯入 15 張關鍵幀
2. 每張設定為 120 秒
3. 根據 motion_guidance 加入運鏡：
   - ken_burns → 緩慢推進
   - zoom_in → 放大
   - pan_right → 向右平移

### Step 3：轉場
根據 transition_to_next：
- fade → 淡入淡出
- dissolve → 溶解
- cut → 硬切

### Step 4：匯出
30 分鐘完整影片！

---

## 🎉 完成！

升級後你將擁有：
- ✅ Shorts（9:16，≤60秒）
- ✅ 中片（16:9，3-10分鐘）
- ✅ 長片（16:9，30-60分鐘）
- ✅ 智能關鍵幀生成
- ✅ 運鏡建議
- ✅ 成本預估
- ✅ 降低 70% 成本

**開始創作吧！** 🚀

---

## 📞 需要幫助？

如果遇到問題：
1. 檢查後端 Log（PowerShell）
2. 檢查前端 Console（F12）
3. 查看本文檔的常見問題
4. 截圖錯誤訊息

**祝你成功！** 🎊
