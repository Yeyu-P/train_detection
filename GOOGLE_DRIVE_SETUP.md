# Google Drive 自动上传设置指南

本文档详细说明如何配置 Google Drive 自动上传功能，使火车检测事件数据自动备份到 Google Drive。

## 目录

1. [前置要求](#前置要求)
2. [创建 Google Cloud 项目](#创建-google-cloud-项目)
3. [启用 Google Drive API](#启用-google-drive-api)
4. [创建服务账户](#创建服务账户)
5. [下载凭证文件](#下载凭证文件)
6. [创建并共享 Google Drive 文件夹](#创建并共享-google-drive-文件夹)
7. [安装 Python 依赖](#安装-python-依赖)
8. [配置系统](#配置系统)
9. [测试上传功能](#测试上传功能)
10. [常见问题排查](#常见问题排查)

---

## 前置要求

- Google 账户（Gmail）
- 可以访问 Google Cloud Console
- 运行中的火车检测系统
- Python 3.7 或更高版本

---

## 创建 Google Cloud 项目

### 步骤 1: 访问 Google Cloud Console

1. 打开浏览器，访问：https://console.cloud.google.com/
2. 使用你的 Google 账户登录

### 步骤 2: 创建新项目

1. 点击顶部导航栏的 **项目选择器** 下拉菜单
2. 点击 **新建项目** (NEW PROJECT)
3. 填写项目信息：
   - **项目名称**: `train-detection-backup` (或其他你喜欢的名称)
   - **组织**: 保持默认（如果有）
   - **位置**: 保持默认
4. 点击 **创建** (CREATE)
5. 等待项目创建完成（约 10-30 秒）

---

## 启用 Google Drive API

### 步骤 1: 进入 API 库

1. 在 Google Cloud Console 中，确保你选择了刚才创建的项目
2. 点击左侧菜单 **≡**，选择 **API 和服务** > **库** (APIs & Services > Library)

### 步骤 2: 启用 Drive API

1. 在搜索框中输入 `Google Drive API`
2. 点击搜索结果中的 **Google Drive API**
3. 点击 **启用** (ENABLE) 按钮
4. 等待启用完成（约 5-10 秒）

---

## 创建服务账户

服务账户是一种特殊的账户，用于让程序自动访问 Google 服务，无需人工登录。

### 步骤 1: 进入服务账户页面

1. 点击左侧菜单 **≡**，选择 **API 和服务** > **凭据** (APIs & Services > Credentials)
2. 点击顶部的 **+ 创建凭据** (+ CREATE CREDENTIALS)
3. 选择 **服务账户** (Service account)

### 步骤 2: 填写服务账户详情

**第 1 页：服务账户详细信息**
1. **服务账户名称**: `train-detector-uploader` (或其他描述性名称)
2. **服务账户 ID**: 自动生成（类似 `train-detector-uploader@your-project.iam.gserviceaccount.com`）
3. **描述**: `用于自动上传火车检测数据到 Google Drive`
4. 点击 **创建并继续** (CREATE AND CONTINUE)

**第 2 页：授予服务账户访问权限**
1. 跳过此步骤，直接点击 **继续** (CONTINUE)

**第 3 页：授予用户访问此服务账户的权限**
1. 跳过此步骤，直接点击 **完成** (DONE)

---

## 下载凭证文件

### 步骤 1: 创建密钥

1. 在 **凭据** 页面，找到 **服务账户** 部分
2. 点击你刚创建的服务账户邮箱地址（例如 `train-detector-uploader@...`）
3. 切换到 **密钥** (KEYS) 标签页
4. 点击 **添加密钥** (ADD KEY) > **创建新密钥** (Create new key)
5. 选择密钥类型：**JSON**
6. 点击 **创建** (CREATE)

### 步骤 2: 保存凭证文件

1. 浏览器会自动下载一个 JSON 文件（例如 `your-project-abc123.json`）
2. **重要**：将此文件重命名为 `service_account.json`
3. **重要**：将文件移动到火车检测系统的根目录：
   ```bash
   # 假设下载到了 ~/Downloads/
   mv ~/Downloads/your-project-abc123.json /home/user/train_detection/service_account.json
   ```
4. **安全提示**：此文件包含敏感信息，请妥善保管，不要分享或提交到代码仓库！

### 步骤 3: 记录服务账户邮箱

1. 打开 `service_account.json` 文件，找到 `client_email` 字段
2. 复制邮箱地址（类似 `train-detector-uploader@your-project.iam.gserviceaccount.com`）
3. 此邮箱将在下一步使用

---

## 创建并共享 Google Drive 文件夹

### 步骤 1: 创建专用文件夹

1. 打开 Google Drive：https://drive.google.com/
2. 点击左上角的 **+ 新建** > **文件夹**
3. 输入文件夹名称，例如：`TrainDetectionBackup`
4. 点击 **创建**

### 步骤 2: 共享文件夹给服务账户

1. 右键点击刚创建的文件夹
2. 选择 **共享** (Share)
3. 在 **添加人员和群组** 输入框中，粘贴前面复制的服务账户邮箱地址
4. **重要**：将权限设置为 **编辑者** (Editor)
5. **取消勾选** "通知用户" (如果有此选项)
6. 点击 **共享** 或 **发送**

### 步骤 3: 获取文件夹 ID

1. 在 Google Drive 中打开刚才创建的文件夹
2. 查看浏览器地址栏，URL 格式如下：
   ```
   https://drive.google.com/drive/folders/1a2B3c4D5e6F7g8H9i0J1k2L3m4N5o6P
   ```
3. 复制 `/folders/` 后面的长字符串，即文件夹 ID：
   ```
   1a2B3c4D5e6F7g8H9i0J1k2L3m4N5o6P
   ```
4. 保存此 ID，稍后配置时使用

---

## 安装 Python 依赖

Google Drive 上传功能需要额外的 Python 库。

### 安装命令

在火车检测系统目录中运行：

```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

### 验证安装

```bash
python3 -c "from googleapiclient.discovery import build; print('Google API libraries installed successfully')"
```

如果没有错误输出，表示安装成功。

---

## 配置系统

### 编辑 config.json

打开 `/home/user/train_detection/config.json`，找到 `google_drive` 部分：

```json
"google_drive": {
  "enabled": false,
  "credentials_file": "service_account.json",
  "folder_id": "",
  "upload_delay_seconds": 5
}
```

修改配置：

```json
"google_drive": {
  "enabled": true,
  "credentials_file": "service_account.json",
  "folder_id": "1a2B3c4D5e6F7g8H9i0J1k2L3m4N5o6P",
  "upload_delay_seconds": 5
}
```

**参数说明**：
- `enabled`: 设置为 `true` 启用 Google Drive 上传
- `credentials_file`: 凭证文件路径（相对于项目根目录）
- `folder_id`: 前面获取的 Google Drive 文件夹 ID
- `upload_delay_seconds`: 事件结束后延迟多少秒再上传（默认 5 秒，确保文件已完全写入）

**文件组织方式**：
- 每个事件自动压缩成 ZIP 文件后上传
- 文件名格式：`event_20251226_230829.zip`
- ZIP 文件内包含：
  - `event_20251226_230829/metadata.json`
  - `event_20251226_230829/device_1.csv`
  - `event_20251226_230829/device_2.csv`
  - 等等...
- 本地会保留 ZIP 文件作为备份

---

## 测试上传功能

### 步骤 1: 启动火车检测系统

```bash
cd /home/user/train_detection
python3 train_detector_stable.py
```

### 步骤 2: 检查启动日志

系统启动时应该看到类似的日志：

```
[INFO] Google Drive uploader initialized: folder_id=1a2B3c4D5e...
```

如果看到错误日志，请参考 [常见问题排查](#常见问题排查) 部分。

### 步骤 3: 触发火车检测事件

等待真实火车通过，或手动模拟振动触发检测。

### 步骤 4: 检查上传日志

事件结束后约 5 秒，应该看到上传日志：

```
[INFO] Created ZIP archive: event_20251226_123456.zip (5 files)
[INFO] Google Drive upload complete: event_20251226_123456.zip
```

### 步骤 5: 验证 Google Drive

1. 打开 Google Drive：https://drive.google.com/
2. 进入你创建的备份文件夹
3. 应该看到新上传的 ZIP 文件，例如：
   - `event_20251226_123456.zip`
   - `event_20251226_123501.zip`
   - `event_20251226_123515.zip`
4. 下载并解压任意 ZIP 文件，里面包含：
   - `event_20251226_123456/metadata.json`
   - `event_20251226_123456/device_1.csv`
   - `event_20251226_123456/device_2.csv`
   - 等等...

---

## 常见问题排查

### 问题 1: 启动时报错 "No module named 'googleapiclient'"

**原因**：未安装 Google API 客户端库

**解决方法**：
```bash
pip install google-api-python-client
```

---

### 问题 2: 启动时报错 "service_account.json not found"

**原因**：凭证文件路径不正确

**解决方法**：
1. 检查 `service_account.json` 是否在项目根目录
2. 检查文件名是否正确（区分大小写）
3. 检查 `config.json` 中的 `credentials_file` 路径

```bash
# 验证文件存在
ls -l /home/user/train_detection/service_account.json
```

---

### 问题 3: 上传时报错 "Service Accounts do not have storage quota" 或 "storageQuotaExceeded"

**原因**：共享文件夹不是你创建的，或者文件夹所有权属于服务账户

**解决方法**：

1. **确保文件夹是在你的个人 Google Drive 中创建的**（不是服务账户创建的）

2. **确认文件夹已正确共享给服务账户**：
   - 在 Google Drive 中右键点击文件夹 > 共享
   - 检查服务账户邮箱是否在共享列表中
   - 权限必须是"编辑者"

3. **验证 folder_id 指向的是你自己拥有的文件夹**

4. **重启系统**让配置生效

**工作原理**：
- 文件直接上传到你拥有的共享文件夹中
- 使用你的 Google Drive 存储空间
- 不创建子文件夹，避免所有权转移问题

---

### 问题 4: 上传时报错 "403 Forbidden" 或 "Insufficient Permission"

**原因**：服务账户没有文件夹访问权限

**解决方法**：
1. 重新检查是否正确共享了文件夹给服务账户
2. 确保权限设置为 **编辑者** (Editor)
3. 验证服务账户邮箱地址是否正确：
   ```bash
   grep client_email service_account.json
   ```
4. 在 Google Drive 中检查文件夹的共享设置

---

### 问题 5: 上传时报错 "404 Not Found" 或 "File not found"

**原因**：文件夹 ID 不正确

**解决方法**：
1. 重新检查 `config.json` 中的 `folder_id`
2. 确保 ID 是从 Google Drive URL 中复制的完整字符串
3. 测试文件夹 ID 是否有效：
   ```bash
   # 在 Python 中测试
   python3 -c "
   from google.oauth2 import service_account
   from googleapiclient.discovery import build

   credentials = service_account.Credentials.from_service_account_file(
       'service_account.json',
       scopes=['https://www.googleapis.com/auth/drive.file']
   )
   service = build('drive', 'v3', credentials=credentials)
   folder_id = '1a2B3c4D5e6F7g8H9i0J1k2L3m4N5o6P'  # 替换为你的 folder_id

   try:
       folder = service.files().get(fileId=folder_id).execute()
       print(f'文件夹名称: {folder[\"name\"]}')
       print('测试成功！')
   except Exception as e:
       print(f'测试失败: {e}')
   "
   ```

---

### 问题 6: 上传成功但 Google Drive 中看不到文件

**原因**：可能上传到了服务账户的 Drive，而不是你的个人 Drive

**解决方法**：
1. 确认你正确共享了文件夹给服务账户
2. 检查是否在正确的 Google 账户中查看
3. 检查上传日志中的 folder_id 是否正确
4. 尝试在 Google Drive 中搜索文件名（例如 `event_20251226_123456.zip`）

---

### 问题 7: 上传速度很慢

**原因**：网络带宽限制或文件较大

**解决方法**：
1. 检查网络连接速度
2. 上传是异步的，不会阻塞检测系统，可以耐心等待
3. 如果单个事件文件非常大（>100MB），考虑：
   - 调整检测参数减少采样率
   - 压缩文件后上传（需要修改代码）

---

### 问题 8: 想要临时禁用上传

**解决方法**：
编辑 `config.json`，将 `enabled` 设置为 `false`：

```json
"google_drive": {
  "enabled": false,
  ...
}
```

重启系统即可。

---

### 问题 9: 想要查看详细的上传日志

**解决方法**：
查看系统日志文件：

```bash
tail -f /home/user/train_detection/train_detector.log | grep -i "drive"
```

---

### 问题 10: 服务账户凭证泄露了怎么办

**解决方法**：
1. **立即禁用旧密钥**：
   - 访问 Google Cloud Console
   - 进入 API 和服务 > 凭据 > 服务账户
   - 点击你的服务账户
   - 在 **密钥** 标签页中，删除泄露的密钥
2. **创建新密钥**：
   - 按照 [下载凭证文件](#下载凭证文件) 步骤重新创建
3. **更新系统**：
   - 替换 `service_account.json` 文件
   - 重启火车检测系统

---

## 高级配置

### 自定义凭证文件路径

如果你想将凭证文件放在其他位置（例如 `/etc/train_detector/`），可以修改 `config.json`：

```json
"google_drive": {
  "credentials_file": "/etc/train_detector/service_account.json",
  ...
}
```

### 调整上传延迟

如果你的系统写入文件较慢，可以增加延迟时间：

```json
"google_drive": {
  "upload_delay_seconds": 10,
  ...
}
```

---

## 系统状态显示

启用 Google Drive 上传后，系统状态显示会包含上传统计信息：

```
=== Google Drive Upload Stats ===
  Total Uploads: 15
  Successful: 14
  Failed: 1
```

---

## 安全建议

1. **保护凭证文件**：
   ```bash
   chmod 600 /home/user/train_detection/service_account.json
   ```

2. **不要提交到代码仓库**：
   在 `.gitignore` 中添加：
   ```
   service_account.json
   ```

3. **定期审查权限**：
   - 定期检查 Google Cloud Console 中的服务账户权限
   - 删除不再使用的密钥

4. **监控上传活动**：
   - 定期检查 Google Drive 中的文件
   - 如果发现异常上传，立即禁用并检查系统

---

## 技术支持

如果遇到本文档未涵盖的问题：

1. 检查系统日志：`train_detector.log`
2. 查看 Google Cloud Console 中的 API 使用情况
3. 验证 Google Drive API 配额是否耗尽
4. 参考 Google Drive API 官方文档：https://developers.google.com/drive/api/v3/about-sdk

---

## 版本信息

- 文档版本: 1.0
- 最后更新: 2025-12-26
- 适用系统版本: train_detector_stable.py v2.0+

---

**祝你使用愉快！🚂**
