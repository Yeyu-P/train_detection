# Dropbox 自动上传设置指南

本文档详细说明如何配置 Dropbox 自动上传功能，使火车检测事件数据自动备份到 Dropbox。

**免费存储空间：2GB**

## 目录

1. [前置要求](#前置要求)
2. [创建 Dropbox 应用](#创建-dropbox-应用)
3. [获取访问令牌](#获取访问令牌)
4. [配置系统](#配置系统)
5. [测试上传功能](#测试上传功能)
6. [常见问题排查](#常见问题排查)

---

## 前置要求

- Dropbox 账号（免费注册）
- 浏览器
- Python 3.7 或更高版本
- `requests` 库（`pip install requests`）

---

## 创建 Dropbox 应用

### 步骤 1: 访问 Dropbox App Console

1. 打开浏览器，访问：https://www.dropbox.com/developers/apps
2. 使用你的 Dropbox 账号登录

### 步骤 2: 创建新应用

1. 点击 **Create app** 按钮
2. **Choose an API**: 选择 **Scoped access**
3. **Choose the type of access you need**: 选择 **App folder**
   - 这样应用只能访问自己的文件夹，更安全
   - 文件会上传到 `/Apps/你的应用名称/` 目录
4. **Name your app**: 输入应用名称，例如 `TrainDetectionUploader`
   - 名称必须全局唯一，如果重复会提示修改
5. 勾选 **I agree to Dropbox API Terms and Conditions**
6. 点击 **Create app**

---

## 获取访问令牌

### 步骤 1: 配置权限

1. 在应用设置页面，切换到 **Permissions** 标签
2. 找到 **Files and folders** 部分
3. 勾选以下权限：
   - `files.metadata.write`
   - `files.content.write`
   - `files.content.read`
4. 点击页面底部的 **Submit** 保存权限

### 步骤 2: 生成访问令牌

1. 切换回 **Settings** 标签
2. 向下滚动到 **OAuth 2** 部分
3. 找到 **Generated access token**
4. 点击 **Generate** 按钮
5. **立即复制**显示的访问令牌（长字符串）
6. 保存此令牌，稍后会用到

**重要**：访问令牌只显示一次！如果丢失需要重新生成。

---

## 配置系统

### 编辑 config.json

打开 `/home/user/train_detection/config.json`，找到 `dropbox` 部分：

```json
"dropbox": {
  "enabled": true,
  "access_token": "你刚才复制的访问令牌",
  "upload_folder": "/TrainDetection",
  "upload_delay_seconds": 5
}
```

**参数说明**：
- `enabled`: 设置为 `true` 启用 Dropbox 上传
- `access_token`: 刚才生成的访问令牌
- `upload_folder`: Dropbox 中的上传文件夹路径
  - 如果选择了 **App folder**，路径是相对于 `/Apps/你的应用名称/` 的
  - 例如 `/TrainDetection` 实际路径是 `/Apps/TrainDetectionUploader/TrainDetection/`
- `upload_delay_seconds`: 事件结束后延迟多少秒再上传

**完整示例**：
```json
"dropbox": {
  "enabled": true,
  "access_token": "sl.BxYz...很长的字符串...abc123",
  "upload_folder": "/TrainDetection",
  "upload_delay_seconds": 5
}
```

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
Dropbox uploader enabled: Folder '/TrainDetection'
```

### 步骤 3: 触发火车检测事件

等待真实火车通过，或手动模拟振动触发检测。

### 步骤 4: 检查上传日志

事件结束后约 5 秒，应该看到：

```
[INFO] Created ZIP archive for Dropbox: event_20251226_123456.zip (5 files)
[INFO] Dropbox upload complete: event_20251226_123456.zip
   Uploaded to Dropbox: event_20251226_123456.zip (5 files compressed)
```

### 步骤 5: 验证 Dropbox

1. 打开 Dropbox：https://www.dropbox.com/home
2. 进入 `/Apps/TrainDetectionUploader/TrainDetection/` 文件夹
3. 检查上传的 ZIP 文件

---

## 常见问题排查

### 问题 1: 启动时报错 "No module named 'requests'"

**原因**：未安装 `requests` 库

**解决方法**：
```bash
pip install requests
```

---

### 问题 2: 启动时报错 "Missing access_token"

**原因**：未配置或配置错误

**解决方法**：
1. 检查 `config.json` 中的 `access_token` 是否正确填写
2. 确保令牌没有多余的空格或引号
3. 如果丢失，重新生成（见"获取访问令牌"步骤）

---

### 问题 3: 上传时报错 "401 Unauthorized"

**原因**：访问令牌无效或已撤销

**解决方法**：
1. 访问 Dropbox App Console
2. 进入你的应用设置
3. 撤销旧令牌（如果有）
4. 生成新的访问令牌
5. 更新 `config.json`
6. 重启系统

---

### 问题 4: 上传时报错 "403 Forbidden"

**原因**：权限不足

**解决方法**：
1. 访问 Dropbox App Console
2. 进入你的应用 > Permissions 标签
3. 确保勾选了 `files.content.write` 权限
4. 点击 Submit 保存
5. **重新生成访问令牌**（权限更改后需要重新生成）

---

### 问题 5: 文件夹路径找不到

**原因**：路径配置错误

**解决方法**：
- 如果选择了 **App folder**：
  - 使用相对路径，如 `/TrainDetection`
  - 实际位置是 `/Apps/你的应用名/TrainDetection/`
- 如果选择了 **Full Dropbox**：
  - 可以使用绝对路径
  - 需要更高权限

---

### 问题 6: Access token 会过期吗？

**答案**：
- 通过 "Generate" 按钮生成的令牌**永不过期**
- 除非你手动撤销或删除应用
- 非常方便，设置一次就行

---

### 问题 7: 想要临时禁用上传

**解决方法**：
编辑 `config.json`，将 `enabled` 设置为 `false`：

```json
"dropbox": {
  "enabled": false,
  ...
}
```

重启系统即可。

---

### 问题 8: 存储空间不够用了

**免费用户限制**：
- 免费空间：2GB
- 单个文件最大：2GB

**解决方法**：
1. **定期清理**：下载旧数据后删除
2. **升级到 Plus**：2TB 空间，约 $12/月
3. **同时用多个云**：OneDrive (5GB) + Dropbox (2GB) = 7GB

---

### 问题 9: 上传速度很慢

**原因**：网络带宽限制或文件较大

**解决方法**：
1. 检查网络连接速度
2. 上传是异步的，不会阻塞检测系统
3. Dropbox 在国内访问可能较慢，考虑使用 OneDrive

---

### 问题 10: Access token 泄露了怎么办

**解决方法**：
1. **立即撤销**：
   - 访问 Dropbox App Console
   - 进入应用设置
   - 撤销泄露的令牌
2. **生成新令牌**：
   - 点击 Generate 生成新令牌
3. **更新配置**：
   - 更新 `config.json` 中的 `access_token`
   - 重启系统

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
   ```

3. **定期检查应用授权**：
   - 访问 https://www.dropbox.com/account/connected_apps
   - 检查授权的应用列表
   - 删除不再使用的应用

---

## 多云备份

你可以同时启用 Dropbox、OneDrive 和 Google Drive：

```json
"dropbox": {
  "enabled": true,
  "access_token": "你的_DROPBOX_TOKEN",
  ...
},
"onedrive": {
  "enabled": true,
  "client_id": "你的_ONEDRIVE_CLIENT_ID",
  ...
},
"google_drive": {
  "enabled": false,
  ...
}
```

**推荐组合**：
- **个人用户**：OneDrive (5GB) + Dropbox (2GB) = 7GB 免费空间
- **企业用户**：Google Workspace (无限空间)

每个事件会自动上传到所有启用的云存储，实现多重备份。

---

## Dropbox vs OneDrive vs Google Drive

| 项目 | Dropbox | OneDrive | Google Drive |
|------|---------|----------|--------------|
| 免费空间 | 2GB | **5GB** | 15GB |
| 免费上传 | ✅ | ✅ | ❌ (服务账户受限) |
| 配置难度 | **最简单** | 中等 | 复杂 |
| 国内访问 | 较慢 | 较快 | 较慢 |
| 推荐度 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |

**建议**：
- 首选 **OneDrive**（5GB + 配置相对简单）
- 次选 **Dropbox**（配置最简单，但空间小）
- Google Drive 仅推荐给有 Workspace 订阅的用户

---

**祝你使用愉快！📦**
