# OpenList for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/v/release/zhoujunn/openlist-ha?include_prereleases)](https://github.com/zhoujunn/openlist-ha/releases)
[![License](https://img.shields.io/github/license/zhoujunn/openlist-ha)](LICENSE)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2023.7%2B-blue)](https://www.home-assistant.io/)

> 将 [OpenList](https://github.com/OpenListTeam/OpenList) 网盘挂载服务集成到 Home Assistant，实时监控文件、任务、存储状态，并通过服务或按钮远程操作。

---

## ✨ 功能特性

### 📊 传感器（Sensors）

| 实体 | 说明 |
|---|---|
| `sensor.根目录文件数` | 根目录下的文件/文件夹总数 |
| `sensor.<任务类型>_已完成任务` | 各任务类型（上传/复制/离线下载等）的已完成数量 |
| `sensor.<任务类型>_未完成任务` | 正在运行或排队的任务数 |
| `sensor.<任务类型>_已失败任务` | 失败的任务数 |
| `sensor.<任务类型>_已完成进度` | 进度百分比（基于成功 / 总任务数） |
| `sensor.目录文件数_<路径>` | 跟踪目录的文件数（可配置多个） |
| `sensor.存储状态_<挂载点>` | 每个存储挂载点的在线/离线状态 |
| `sensor.存储数量` | 存储挂载点总数 |

### 🔘 二进制传感器（Binary Sensors）

| 实体 | 说明 |
|---|---|
| `binary_sensor.服务器在线` | OpenList 服务是否可访问 |
| `binary_sensor.有失败任务` | 任一任务类型存在失败任务 |
| `binary_sensor.有正在运行的任务` | 存在未完成的任务 |

### 🔘 按钮（Buttons）

每个任务类型生成 2 个按钮，共 12 个：

- **`<任务类型> 清除已完成任务`** —— 一键清理已完成列表
- **`<任务类型> 重试失败任务`** —— 一键重试所有失败任务

### 🎯 服务（Services）

支持 OpenList 全部核心操作，共 **29 个服务**：

#### 任务类（12 个）

```yaml
openlist.get_task_info               # 获取任务信息
openlist.get_task_done               # 获取已完成任务
openlist.get_task_undone             # 获取未完成任务
openlist.delete_task                 # 删除单个任务
openlist.cancel_task                 # 取消单个任务
openlist.clear_done_tasks            # 清除已完成任务
openlist.clear_succeeded_tasks       # 清除成功任务
openlist.retry_task                  # 重试单个任务
openlist.retry_failed_tasks          # 重试所有失败任务
openlist.delete_some_tasks           # 批量删除任务
openlist.cancel_some_tasks           # 批量取消任务
openlist.retry_some_tasks            # 批量重试任务
```

#### 文件类（17 个）

```yaml
openlist.mkdir                       # 创建目录
openlist.rename                      # 重命名
openlist.list_files                  # 列出文件
openlist.get_file_info               # 获取文件信息
openlist.search_files                # 搜索文件
openlist.get_dirs                    # 获取目录列表
openlist.batch_rename                # 批量重命名
openlist.regex_rename                # 正则重命名
openlist.move_files                  # 移动文件
openlist.recursive_move              # 聚合移动
openlist.copy_files                  # 复制文件
openlist.remove_files                # 删除文件
openlist.remove_empty_dir            # 删除空目录
openlist.add_offline_download        # 新建离线下载
openlist.get_archive_meta            # 获取压缩包元信息
openlist.list_archive                # 列出压缩包内容
openlist.decompress_archive          # 解压压缩包
```

### 🔔 事件（Events）

| 事件名 | 触发时机 |
|---|---|
| `openlist_task_completed` | 任意任务从"进行中"变为"已完成"或"已失败"时触发 |

**事件数据**：

```yaml
task_type:       "offline_download"   # 任务类型
task_type_name:  "离线下载"            # 中文名
task_id:         "abc123"             # 任务 ID
task_name:       "ubuntu.iso"         # 任务名
state:           2                    # 2=成功, 其他=失败
success:         true                 # 是否成功
error:           ""                   # 失败原因
start_time:      "2026-09-24T10:00:00Z"
end_time:        "2026-09-24T10:05:00Z"
```

### 🎁 其他特性

- ✅ **设备归组** —— 所有实体自动归入同一个「设备」，管理更清爽
- ✅ **令牌自动刷新** —— 48 小时令牌智能续期，无感知保持登录
- ✅ **并发保护** —— `asyncio.Lock` 防止多请求重复登录
- ✅ **诊断信息** —— 一键导出集成状态（含令牌剩余有效期）
- ✅ **Options Flow** —— 运行时修改跟踪目录和轮询间隔，无需重建集成
- ✅ **持久通知** —— 异步任务提交后自动发送 HA 通知
- ✅ **全中文界面** —— 所有实体、服务、错误提示本地化

---

## 📦 安装

### 方式 1：HACS（推荐）

1. 打开 HACS → **集成**
2. 点击右上角 ⋮ → **自定义存储库**
3. 填入 `https://github.com/zhoujunn/openlist-ha`，类别选 **Integration**
4. 搜索 **OpenList** → 安装
5. **重启 Home Assistant**

### 方式 2：手动安装

```bash
# 进入 HA 配置目录
cd /config

# 克隆仓库
git clone https://github.com/zhoujunn/openlist-ha.git \
  custom_components/openlist

# 或直接下载 ZIP 解压到 custom_components/openlist/
```

最终目录结构：

```
config/
└── custom_components/
    └── openlist/
        ├── __init__.py
        ├── api.py
        ├── button.py
        ├── config_flow.py
        ├── const.py
        ├── diagnostics.py
        ├── manifest.json
        ├── sensor.py
        ├── services.yaml
        ├── strings.json
        └──brand/
          |-icon.png
          |-logo.png
```

重启 Home Assistant 生效。

---

## ⚙️ 配置

### 添加集成

1. **设置 → 设备与服务 → 添加集成**
2. 搜索 **OpenList**
3. 填写表单：

| 字段 | 说明 | 示例 |
|---|---|---|
| **服务器地址** | 完整 URL（含协议） | `http://10.0.0.19:5244` |
| **用户名** | OpenList 登录账号 | `admin` |
| **密码** | OpenList 登录密码 | `your_password` |
| **跟踪目录** | 可选，英文逗号分隔 | `/download, /media` |

4. 点击**提交**，成功后会创建集成项。

### 修改选项

**设置 → 设备与服务 → OpenList → 配置**：

- **跟踪目录** —— 增删或修改（英文逗号分隔，留空则清空）
- **轮询间隔** —— 1~60 分钟（默认 5 分钟）

修改后集成会自动重新加载，无需手动重启。

---

## 🔧 使用示例

### 示例 1：离线下载完成自动通知

```yaml
alias: 离线下载完成通知
trigger:
  - platform: event
    event_type: openlist_task_completed
    event_data:
      task_type: offline_download
      success: true
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "✅ 离线下载完成"
      message: "{{ trigger.event.data.task_name }} 已下载完成"
mode: single
```

### 示例 2：有失败任务时告警

```yaml
alias: OpenList 失败任务告警
trigger:
  - platform: state
    entity_id: binary_sensor.openlist_有失败任务
    from: "off"
    to: "on"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "⚠️ OpenList 有失败任务"
      message: >-
        {% set stats = state_attr('binary_sensor.openlist_有失败任务', '失败任务统计') %}
        {% for name, count in stats.items() %}
        {{ name }}: {{ count }} 个
        {% endfor %}
mode: single
```

### 示例 3：每天凌晨自动清理已完成任务

```yaml
alias: 每天清理 OpenList 已完成任务
trigger:
  - platform: time
    at: "03:00:00"
action:
  - service: openlist.clear_done_tasks
    data:
      task_type: offline_download
  - service: openlist.clear_done_tasks
    data:
      task_type: upload
  - service: openlist.clear_done_tasks
    data:
      task_type: decompress
mode: single
```

### 示例 4：一键离线下载

```yaml
alias: 添加离线下载任务
sequence:
  - service: openlist.add_offline_download
    data:
      path: /download
      urls:
        - "https://releases.ubuntu.com/24.04/ubuntu-24.04-desktop-amd64.iso"
      tool: aria2
      delete_policy: delete_on_upload_succeed
mode: single
```

### 示例 5：磁盘空间告警（结合存储传感器）

```yaml
alias: 存储挂载掉线告警
trigger:
  - platform: state
    entity_id:
      - sensor.存储状态_download
      - sensor.存储状态_media
    to: "offline"
    for: "00:05:00"
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "🔴 存储挂载掉线"
      message: "{{ trigger.to_state.name }} 已离线超过 5 分钟"
mode: single
```

---

## 🎨 前端卡片推荐

### 用 Markdown 卡片汇总

```yaml
type: markdown
content: |
  ## 📁 OpenList 状态

  **服务器**: {{ states('binary_sensor.openlist_服务器在线') }}
  **根目录文件**: {{ states('sensor.openlist_根目录文件数') }}

  ### 任务统计
  | 类型 | 运行中 | 已完成 | 失败 |
  |---|---|---|---|
  | 离线下载 | {{ states('sensor.离线下载_未完成任务') }} | {{ states('sensor.离线下载_已完成任务') }} | {{ states('sensor.离线下载_已失败任务') }} |
  | 上传 | {{ states('sensor.上传_未完成任务') }} | {{ states('sensor.上传_已完成任务') }} | {{ states('sensor.上传_已失败任务') }} |

  ### 存储状态
  {% for s in states.sensor | selectattr('entity_id', 'match', 'sensor.存储状态_*') %}
  - {{ s.name }}: **{{ s.state }}**
  {% endfor %}
```

### 用自动实体卡片

```yaml
type: entities
title: OpenList
entities:
  - binary_sensor.openlist_服务器在线
  - sensor.openlist_根目录文件数
  - sensor.openlist_存储数量
  - type: divider
  - sensor.离线下载_未完成任务
  - sensor.离线下载_已完成任务
  - sensor.离线下载_已失败任务
  - sensor.离线下载_已完成进度
  - type: divider
  - button.离线下载_重试失败任务
  - button.离线下载_清除已完成任务
```

---

## 📊 传感器属性详解

### `sensor.离线下载_已完成任务`

```yaml
state: 12
属性:
  任务类型: offline_download
  任务名称: 离线下载
  传感器类型: done
  任务列表:                    # 最近 10 条
    - id: "abc123"
      name: "ubuntu.iso"
      progress: "100.0%"
      state: 2
      start_time: "2026-09-24T10:00:00Z"
      end_time: "2026-09-24T10:05:00Z"
  任务数量: 12
  最后更新时间: "2026-09-24 10:05:30"
```

### `sensor.存储状态_download`

```yaml
state: online
属性:
  挂载路径: /download
  驱动类型: Local
  状态: work
  禁用: false
  排序: 0
  最后更新时间: "2026-09-24 10:05:30"
```

### `sensor.目录文件数_/media`

```yaml
state: 25
属性:
  目录路径: /media
  文件列表: ["movie1.mkv", "movie2.mp4", ...]   # 最多 50 条
  文件总数: 25
  最新修改时间: "2026-09-24T09:30:00Z"
  最后更新时间: "2026-09-24 10:05:30"
```

---

## 🐛 故障排除

### 集成添加失败（`auth_failed`）

**原因**：地址、账号或密码错误。

**排查**：

```bash
# 在 HA 主机上测试登录
curl -X POST http://your-server:5244/api/auth/login/hash \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<sha256_hash>"}'
```

### 存储传感器不出现

**原因**：账号不是 **admin** 组，无法访问 `/api/admin/storage/list`。

**方案**：

- 用 **admin** 账号重新添加集成
- 或查看 `sensor.存储数量` 的属性中是否有错误提示

### 跟踪目录传感器不出现

**检查清单**：

1. **Options 里填了吗？** —— 设置 → 设备与服务 → OpenList → 配置
2. **路径对吗？** —— 必须以 `/` 开头，且**在 OpenList 里真实存在**
3. **有隐藏字符吗？** —— 从网页复制路径时可能带入 ZWNJ（U+200C）等不可见字符，**建议手动输入**
4. **看日志**：搜索 `OpenList 读取跟踪目录` 确认解析结果

### 令牌频繁重新登录

**原因**：刷新失败降级为登录。

**排查**：查看诊断信息：

**设置 → 设备与服务 → OpenList → ⋮ → 下载诊断** → 查看 `API 状态` 段：

```json
{
  "已登录": true,
  "令牌剩余有效期(小时)": 47.66,
  "已过刷新阈值": false
}
```

如果剩余时间持续偏低，说明刷新接口有问题。

### 日志刷屏 `object not found`

**原因**：跟踪目录不存在。

**修复**：修改配置移除无效路径，或应用[容错补丁](https://github.com/zhoujunn/openlist-ha/issues)把 500 当作空目录处理。

---

## 🔐 权限说明

| 功能 | 需要的角色 |
|---|---|
| 文件列表、上传、下载 | **普通用户** |
| 任务管理（上传/复制等） | **普通用户** |
| 存储状态传感器 | **管理员** |
| 用户/驱动/索引管理 | **管理员** |

**建议**：如果只需要文件和任务功能，用普通用户即可；想要完整存储监控，用 admin 账号。

---

## 🛠 开发

### 环境要求

- Home Assistant **2023.7+**
- Python **3.11+**
- OpenList **v3.6+**

### 本地调试

```bash
# 克隆仓库
git clone https://github.com/zhoujunn/openlist-ha.git
cd openlist-ha

# 在 HA 开发容器中挂载
# 把 custom_components/openlist 软链接到 config 目录
```

### 日志调试

在 `configuration.yaml` 中启用详细日志：

```yaml
logger:
  default: warning
  logs:
    custom_components.openlist: debug
```

重启后可在 **设置 → 系统 → 日志** 中查看完整请求/响应。

---

## 📝 更新日志

### v1.2.1 (2026-09-24)

- ✨ 新增**令牌自动刷新**，无感知延长登录状态
- ✨ 新增**存储状态传感器**，实时监控挂载点
- ✨ 新增**设备归组**，所有实体归入同一设备
- ✨ 新增 **Options Flow**，运行时修改配置
- 🐛 修复 Options 中跟踪目录不生效的问题
- 🐛 兼容 `data.content` 响应格式
- 🎨 代码重构，减少约 60% 冗余

### v1.2.0 (2026-09-20)

- ✨ 新增按钮实体（重试/清除）
- ✨ 新增任务完成事件
- ✨ 新增诊断模式
- ✨ 新增服务结果通知

### v1.1.0 (2026-09-15)

- ✨ 首次发布

---

## 🤝 贡献

欢迎提交 Issue 和 PR！

- **Bug 报告**：[新建 Issue](https://github.com/zhoujunn/openlist-ha/issues/new)
- **功能建议**：[新建 Discussion](https://github.com/zhoujunn/openlist-ha/discussions)
- **贡献代码**：Fork → 修改 → 提交 PR

**PR 规范**：

- 遵循 HA 官方[开发规范](https://developers.home-assistant.io/)
- 提交前运行 `python -m compileall custom_components/openlist/`
- 提供测试用例或截图

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源。

---

## 🙏 致谢

- [OpenList](https://github.com/OpenListTeam/OpenList) —— 优秀的网盘挂载服务
- [Home Assistant](https://www.home-assistant.io/) —— 开源智能家居平台
- [AList](https://github.com/alist-org/alist) —— OpenList 的上游项目
- 所有提交 Issue 和 PR 的贡献者

---

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=zhoujunn/openlist-ha&type=Date)](https://star-history.com/#zhoujunn/openlist-ha&Date)

---

<div align="center">

**如果这个项目对你有帮助，请给个 ⭐ Star 支持一下！**

[报告问题](https://github.com/zhoujunn/openlist-ha/issues) ·
[功能建议](https://github.com/zhoujunn/openlist-ha/discussions) ·
[查看文档](https://github.com/zhoujunn/openlist-ha/wiki)

</div>
