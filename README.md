# 🧩 OpenList for Home Assistant

**OpenList** 是一个 Home Assistant 自定义集成，用于文件列表、移动、任务查询等自动化文件操作。

---

## 📦 安装（通过 HACS）

1. 打开 Home Assistant → HACS → 集成 → 右上角 “自定义仓库”
2. 添加仓库地址：
   ```
   https://github.com/你的GitHub用户名/openlist-ha
   ```
3. 类别选择：**Integration**
4. 搜索 **OpenList** → 安装
5. 重启 Home Assistant

---

## ⚙️ 配置

在 Home Assistant `配置` → `集成` → 添加集成 → 搜索 **OpenList**

或在 `configuration.yaml` 中手动添加：
```yaml
openlist:
  api_key: your_api_key
  base_url: http://your-server
```

---

## 🧰 可用服务

| 服务 | 说明 |
|------|------|
| `openlist.list_files` | 获取指定路径文件列表 |
| `openlist.move_files` | 移动文件 |
| `openlist.clear_succeeded_tasks` | 清除已完成任务 |
| `openlist.get_tasks` | 获取任务状态 |

详见 `services.yaml`

---

## 🧠 作者与支持

- 作者: [你的名字或GitHub用户名](https://github.com/你的GitHub用户名)
- 问题反馈: [GitHub Issues](https://github.com/你的GitHub用户名/openlist-ha/issues)

---

## 🪪 License
MIT License
