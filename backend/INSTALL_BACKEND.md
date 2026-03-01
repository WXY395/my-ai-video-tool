# 🚀 Shorts Factory v2 - Backend 安裝指南

**預計時間：** 15-20 分鐘  
**難度：** ⭐⭐☆☆☆（簡單）

---

## 📋 前置確認

請確認以下項目已完成：
- ✅ Python 3.11.9（已確認）
- ✅ pip 24.0（已確認）
- ✅ PowerShell 可使用

---

## 🗂️ 步驟 1：建立專案資料夾（1 分鐘）

### 在 PowerShell 執行：

```powershell
# 切換到專案目錄
cd C:\Projects\shorts_factory_react

# 建立 backend 資料夾
mkdir backend

# 進入 backend 資料夾
cd backend
```

**預期結果：**
```
你應該看到路徑變成：
PS C:\Projects\shorts_factory_react\backend>
```

---

## 📦 步驟 2：放置後端檔案（3 分鐘）

### 你會收到一個 `backend.zip` 檔案，請：

1. 下載 `backend.zip` 到電腦（任意位置）
2. 解壓縮 `backend.zip`
3. 把所有檔案複製到 `C:\Projects\shorts_factory_react\backend\`

### 檔案結構應該是：

```
C:\Projects\shorts_factory_react\backend\
├── main.py
├── requirements.txt
├── .env.example
├── routers\
│   ├── __init__.py
│   └── observation.py
├── services\
│   ├── __init__.py
│   └── observation_service.py
└── models\
    ├── __init__.py
    └── schemas.py
```

---

## 🔑 步驟 3：設定環境變數（2 分鐘）

### 在 PowerShell 執行：

```powershell
# 複製環境變數範本
copy .env.example .env

# 用記事本開啟 .env 檔案
notepad .env
```

### 在記事本中編輯：

```env
# 把你的 API Keys 填入（替換掉範例值）
GEMINI_API_KEY=你的_Gemini_API_Key
REPLICATE_API_TOKEN=你的_Replicate_Token

# 以下保持不變
HOST=127.0.0.1
PORT=8000
DEBUG=True
FRONTEND_URL=http://localhost:3000
```

**儲存並關閉記事本**

---

## 📥 步驟 4：安裝 Python 套件（5-10 分鐘）

### 在 PowerShell 執行：

```powershell
# 安裝所有依賴套件
pip install -r requirements.txt
```

**這會安裝：**
- FastAPI（Web 框架）
- Uvicorn（伺服器）
- Google Gemini API
- Replicate API
- 其他工具

**預期輸出：**
```
Successfully installed fastapi-0.109.0 uvicorn-0.27.0 ...
```

---

## 🚀 步驟 5：啟動後端伺服器（1 分鐘）

### 在 PowerShell 執行：

```powershell
# 啟動後端
python main.py
```

**成功的話，你會看到：**

```
INFO:     🚀 Shorts Factory v2 Backend 啟動中...
INFO:     📍 API 文檔: http://127.0.0.1:8000/docs
INFO:     🌐 前端位置: http://localhost:3000
INFO:     ✅ 環境變數檢查通過
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

**如果看到警告：**
```
⚠️  缺少環境變數: GEMINI_API_KEY
```
→ 請回到步驟 3，確認 `.env` 檔案中的 API Key 是否正確填寫

---

## ✅ 步驟 6：測試 API（2 分鐘）

### 方法 1：開啟瀏覽器測試

1. **保持 PowerShell 視窗開啟**（伺服器運行中）
2. 開啟瀏覽器，前往：
   ```
   http://127.0.0.1:8000
   ```

**應該看到：**
```json
{
  "message": "Shorts Factory v2 API",
  "version": "2.0.0",
  "status": "running",
  "docs": "/docs",
  "redoc": "/redoc"
}
```

3. 前往 Swagger UI：
   ```
   http://127.0.0.1:8000/docs
   ```

**應該看到：**
- 漂亮的 API 文檔介面
- 可以測試 `/api/observation/generate` 端點

### 方法 2：健康檢查

前往：
```
http://127.0.0.1:8000/health
```

**應該看到：**
```json
{
  "status": "healthy",
  "services": {
    "api": true,
    "observation": true
  }
}
```

---

## 🎯 步驟 7：測試觀測單元生成（選配）

### 在 Swagger UI 中測試：

1. 前往 `http://127.0.0.1:8000/docs`
2. 展開 `POST /api/observation/generate`
3. 點擊 `Try it out`
4. 輸入測試資料：

```json
{
  "notes": "今天在公園看到一隻松鼠在樹上跳來跳去，牠似乎在找松果。突然下起小雨，松鼠迅速躲到樹洞裡。這讓我想到，動物對天氣的感知能力其實比人類還敏銳。",
  "target_units": 3,
  "style_preference": "default"
}
```

5. 點擊 `Execute`
6. 查看回應（應該包含 3 個觀測單元）

---

## 🎊 完成！

如果你看到了以上所有成功訊息，恭喜！後端已經完全運行起來了！

### 現在你有：
- ✅ FastAPI 後端運行在 `http://127.0.0.1:8000`
- ✅ Swagger API 文檔在 `http://127.0.0.1:8000/docs`
- ✅ 觀測單元生成 API 正常運作
- ✅ Gemini API 整合完成

---

## 🐛 常見問題

### 問題 1：`ModuleNotFoundError: No module named 'fastapi'`

**原因：** 套件安裝失敗

**解決：**
```powershell
pip install -r requirements.txt --force-reinstall
```

### 問題 2：`ValueError: GEMINI_API_KEY not found in environment`

**原因：** `.env` 檔案未設定或 API Key 錯誤

**解決：**
1. 確認 `.env` 檔案存在
2. 確認 API Key 正確（沒有多餘空格）
3. 重新啟動伺服器：`python main.py`

### 問題 3：`Address already in use`

**原因：** 8000 port 被佔用

**解決：**
```powershell
# 停止現有程序
Ctrl + C

# 或改用其他 port
# 編輯 .env 檔案，改成：
PORT=8001
```

### 問題 4：伺服器啟動後立即關閉

**原因：** Python 程式有錯誤

**解決：**
```powershell
# 查看完整錯誤訊息
python main.py 2>&1 | Out-File error.log
notepad error.log
```
把錯誤訊息截圖給我

---

## 🔄 如何停止伺服器

在 PowerShell 中按：
```
Ctrl + C
```

---

## 📝 下一步

當後端確認運作正常後，我們就可以開始建置前端了！

**準備好後，回報：**
```
✅ 後端啟動成功
✅ API 測試通過
✅ 準備進入 Day 2（前端建置）
```

---

**有任何問題，隨時截圖給我！** 🚀
