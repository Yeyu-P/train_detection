# OneDrive 自动上传设置指南

本文档详细说明如何配置 OneDrive 自动上传功能，使火车检测事件数据自动备份到 OneDrive。

**免费存储空间：5GB**

## 目录

1. [前置要求](#前置要求)
2. [注册 Azure 应用](#注册-azure-应用)
3. [获取授权码](#获取授权码)
4. [获取刷新令牌](#获取刷新令牌)
5. [配置系统](#配置系统)
6. [测试上传功能](#测试上传功能)
7. [常见问题排查](#常见问题排查)

---

## 前置要求

- Microsoft 账号（免费注册）
- 浏览器
- Python 3.7 或更高版本
- `requests` 库（`pip install requests`）

---

## 注册 Azure 应用

### 步骤 1: 访问 Azure Portal

1. 打开浏览器，访问：https://portal.azure.com/
2. 使用你的 Microsoft 账号登录

### 步骤 2: 注册新应用

1. 在搜索框中输入 **"Azure Active Directory"** 或 **"Microsoft Entra ID"**
2. 点击左侧菜单的 **应用注册** (App registrations)
3. 点击 **+ 新注册** (+ New registration)

### 步骤 3: 填写应用信息

1. **名称**: `Train Detection Uploader`（或其他你喜欢的名称）
2. **支持的账户类型**: 选择 **仅限此组织目录中的帐户**
3. **重定向 URI**:
   - 类型选择 **Web**
   - 输入：`http://localhost:8080`
4. 点击 **注册**

### 步骤 4: 记录 Client ID

1. 注册完成后，会显示应用概述页面
2. 复制 **应用程序(客户端) ID**（Application (client) ID）
3. 保存此 ID，稍后会用到

### 步骤 5: 创建 Client Secret

1. 点击左侧菜单的 **证书和密码** (Certificates & secrets)
2. 点击 **+ 新客户端密码** (+ New client secret)
3. **说明**: `Train Detection Secret`
4. **过期**: 选择 **24 个月**（或根据需要选择）
5. 点击 **添加**
6. **立即复制**显示的 **值**（Value）- 这个密码只显示一次！
7. 保存此密钥，稍后会用到

### 步骤 6: 配置 API 权限

1. 点击左侧菜单的 **API 权限** (API permissions)
2. 点击 **+ 添加权限** (+ Add a permission)
3. 选择 **Microsoft Graph**
4. 选择 **委托的权限** (Delegated permissions)
5. 搜索并勾选以下权限：
   - `Files.ReadWrite`
   - `offline_access`
6. 点击 **添加权限**
7. **不需要**管理员同意（个人账号）

---

## 获取授权码

### 步骤 1: 构造授权 URL

使用你的 **Client ID** 替换下面 URL 中的 `YOUR_CLIENT_ID`：

```
https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http://localhost:8080&response_mode=query&scope=files.readwrite%20offline_access
```

### 步骤 2: 访问授权 URL

1. 在浏览器中打开上面的 URL
2. 登录你的 Microsoft 账号（如果还没登录）
3. 点击 **接受** (Accept) 授权应用访问你的文件

### 步骤 3: 获取授权码

1. 授权后，浏览器会跳转到 `http://localhost:8080/?code=...`
2. 复制 URL 中 `code=` 后面的整个字符串
3. 这就是**授权码** (Authorization Code)

**示例**：
```
http://localhost:8080/?code=M.R3_BAY.abcd1234-efgh-5678-ijkl-9012mnop3456
```
复制 `M.R3_BAY.abcd1234-efgh-5678-ijkl-9012mnop3456` 这部分。

---

## 获取刷新令牌

### 步骤 1: 使用 Python 脚本

创建一个临时 Python 脚本 `get_refresh_token.py`：

```python
import requests

# 替换为你的信息
CLIENT_ID = "你的_CLIENT_ID"
CLIENT_SECRET = "你的_CLIENT_SECRET"
AUTHORIZATION_CODE = "上一步获取的授权码"

response = requests.post(
    'https://login.microsoftonline.com/common/oauth2/v2.0/token',
    data={
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': AUTHORIZATION_CODE,
        'redirect_uri': 'http://localhost:8080',
        'grant_type': 'authorization_code',
        'scope': 'files.readwrite offline_access'
    }
)

if response.status_code == 200:
    token_data = response.json()
    print("✓ 成功获取令牌！")
    print("\n请复制以下 refresh_token：")
    print(token_data['refresh_token'])
else:
    print(f"✗ 错误：{response.status_code}")
    print(response.text)
```

### 步骤 2: 运行脚本

```bash
python3 get_refresh_token.py
```

### 步骤 3: 保存 Refresh Token

复制输出的 `refresh_token`，这是一个长字符串，类似：
```
M.R3_BAY.CfD...很长的字符串...xyz
```

保存此令牌，并**删除** `get_refresh_token.py` 脚本（安全起见）。

---

## 配置系统

### 编辑 config.json

打开 `/home/user/train_detection/config.json`，找到 `onedrive` 部分：

```json
"onedrive": {
  "enabled": true,
  "client_id": "你的_CLIENT_ID",
  "client_secret": "你的_CLIENT_SECRET",
  "refresh_token": "上一步获取的_REFRESH_TOKEN",
  "upload_folder": "TrainDetection",
  "upload_delay_seconds": 5
}
```

**参数说明**：
- `enabled`: 设置为 `true` 启用 OneDrive 上传
- `client_id`: Azure 应用的 Client ID
- `client_secret`: Azure 应用的 Client Secret
- `refresh_token`: 刚才获取的 Refresh Token
- `upload_folder`: OneDrive 中的上传文件夹名称
- `upload_delay_seconds`: 事件结束后延迟多少秒再上传

---

## 测试上传功能

### 步骤 1: 启动火车检测系统

```bash
cd /home/user/train_detection
python3 train_detector_stable.py
```

### 步骤 2: 检查启动日志

系统启动时应该看到：

```
OneDrive uploader enabled: Folder 'TrainDetection'
```

### 步骤 3: 触发火车检测事件

等待真实火车通过，或手动模拟振动触发检测。

### 步骤 4: 检查上传日志

事件结束后约 5 秒，应该看到：

```
[INFO] Created ZIP archive for OneDrive: event_20251226_123456.zip (5 files)
[INFO] OneDrive upload complete: event_20251226_123456.zip
   Uploaded to OneDrive: event_20251226_123456.zip (5 files compressed)
```

### 步骤 5: 验证 OneDrive

1. 打开 OneDrive：https://onedrive.live.com/
2. 在根目录应该看到 `TrainDetection` 文件夹
3. 打开文件夹，检查上传的 ZIP 文件

---

## 常见问题排查

### 问题 1: 启动时报错 "No module named 'requests'"

**原因**：未安装 `requests` 库

**解决方法**：
```bash
pip install requests
```

---

### 问题 2: 上传时报错 "Failed to get access token"

**原因**：Token 配置错误或已过期

**解决方法**：
1. 检查 `config.json` 中的 `client_id`, `client_secret`, `refresh_token` 是否正确
2. 确保没有多余的空格或引号
3. 重新获取 refresh_token（重复"获取刷新令牌"步骤）

---

### 问题 3: 上传时报错 "401 Unauthorized"

**原因**：Refresh token 失效

**解决方法**：
重新执行 "获取授权码" 和 "获取刷新令牌" 步骤，获取新的 refresh_token。

---

### 问题 4: 上传时报错 "404 Not Found"

**原因**：文件夹路径不存在或权限不足

**解决方法**：
1. OneDrive 会自动创建文件夹，检查 `upload_folder` 配置
2. 确保 API 权限包含 `Files.ReadWrite`

---

### 问题 5: Refresh token 会过期吗？

**答案**：
- Refresh token 通常有效期很长（数月到数年）
- 只要定期使用（自动刷新），不会过期
- 如果长时间不用（>90天），可能需要重新授权

---

### 问题 6: Client Secret 过期了怎么办？

**解决方法**：
1. 访问 Azure Portal
2. 进入你的应用 > 证书和密码
3. 创建新的客户端密码
4. 更新 `config.json` 中的 `client_secret`

---

### 问题 7: 想要临时禁用上传

**解决方法**：
编辑 `config.json`，将 `enabled` 设置为 `false`：

```json
"onedrive": {
  "enabled": false,
  ...
}
```

重启系统即可。

---

### 问题 8: 上传速度很慢

**原因**：网络带宽限制或文件较大

**解决方法**：
1. 检查网络连接速度
2. 上传是异步的，不会阻塞检测系统
3. OneDrive 上传通常比 Google Drive 快

---

## 安全建议

1. **保护配置文件**：
   ```bash
   chmod 600 /home/user/train_detection/config.json
   ```

2. **不要提交到代码仓库**：
   在 `.gitignore` 中添加：
   ```
   config.json
   get_refresh_token.py
   ```

3. **定期更换密钥**：
   每 6-12 个月更换一次 Client Secret

---

## 多云备份

你可以同时启用 OneDrive、Dropbox 和 Google Drive：

```json
"onedrive": {
  "enabled": true,
  ...
},
"dropbox": {
  "enabled": true,
  ...
},
"google_drive": {
  "enabled": true,
  ...
}
```

每个事件会自动上传到所有启用的云存储，实现多重备份。

---

**祝你使用愉快！☁️**
