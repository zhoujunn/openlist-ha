OpenList Home Assistant Integration
https://img.shields.io/badge/HACS-Custom-orange.svg
https://img.shields.io/badge/version-0.3.0-blue.svg
https://img.shields.io/badge/license-MIT-green.svg
V1.0.1
添加进度传感器，删除部分传感器不必要属性。

一个用于集成 OpenList/Alist 文件管理系统的 Home Assistant 自定义组件，提供文件监控、任务管理和自动化控制功能。

功能特点
📊 传感器监控
根目录文件数：监控 OpenList 根目录下的文件数量

任务状态监控：为每种任务类型提供三个独立的传感器：

已完成任务（成功完成的任务）

未完成任务（正在进行的任务）

已失败任务（已完成但失败的任务）

目录跟踪：可配置多个跟踪目录，实时监控文件数量变化

🔧 丰富的服务
任务管理服务：

获取任务信息、已完成/未完成任务

删除、取消、重试任务

批量操作任务

清除已完成/成功任务

文件操作服务：

创建目录、重命名文件

移动、复制、删除文件

批量重命名、正则重命名

离线下载、压缩文件操作

🎯 支持的任务类型
上传 (upload)

复制 (copy)

离线下载 (offline_download)

离线下载转存 (offline_download_transfer)

解压 (decompress)

解压转存 (decompress_upload)

移动 (move)

安装
方法一：通过 HACS 安装（推荐）
确保已安装 HACS

在 HACS 中点击「集成」

点击右下角「浏览并下载仓库」

搜索「OpenList」

点击「下载」

重启 Home Assistant

方法二：手动安装
将 openlist 文件夹复制到你的 custom_components 目录

重启 Home Assistant

在集成页面添加 OpenList

配置
通过 UI 配置（推荐）
进入 Home Assistant → 设置 → 设备与服务

点击「添加集成」

搜索「OpenList」

按照提示填写以下信息：

主机地址：你的 OpenList 服务器地址（如：https://your-openlist-server.com）

用户名：OpenList 登录用户名

密码：OpenList 登录密码

跟踪目录（可选）：要监控文件数量的目录路径，多个目录用英文逗号分隔

通过 configuration.yaml 配置
yaml
# 示例配置
openlist:
  host: "https://your-openlist-server.com"
  username: "your_username"
  password: "your_password"
  track_dirs:
    - "/downloads"
    - "/movies"
    - "/backup"
传感器
集成安装后会自动创建以下传感器：

文件数量传感器
sensor.openlist_root_files - 根目录文件数量

任务数量传感器（每种任务类型都有）
sensor.[任务名称]_已完成任务 - 成功完成的任务数量

sensor.[任务名称]_未完成任务 - 正在进行的任务数量

sensor.[任务名称]_已失败任务 - 失败的任务数量

例如：

sensor.移动_已完成任务

sensor.上传_未完成任务

sensor.复制_已失败任务

跟踪目录传感器
sensor.目录文件数_[目录路径] - 指定跟踪目录的文件数量

服务
任务管理服务
服务名称	描述	必需参数
openlist.get_task_info	获取任务信息	task_type
openlist.get_task_done	获取已完成任务	task_type
openlist.get_task_undone	获取未完成任务	task_type
openlist.delete_task	删除任务	task_type, tid
openlist.cancel_task	取消任务	task_type, tid
openlist.clear_done_tasks	清除已完成任务	task_type
openlist.clear_succeeded_tasks	清除成功任务	task_type
openlist.retry_task	重试任务	task_type, tid
openlist.retry_failed_tasks	重试失败任务	task_type
openlist.delete_some_tasks	批量删除任务	task_type, tids
openlist.cancel_some_tasks	批量取消任务	task_type, tids
openlist.retry_some_tasks	批量重试任务	task_type, tids
文件操作服务
服务名称	描述	必需参数
openlist.mkdir	创建文件夹	path
openlist.rename	重命名文件/文件夹	path, name
openlist.list_files	列出文件	-
openlist.get_file_info	获取文件信息	path
openlist.search_files	搜索文件	parent, keywords, scope
openlist.get_dirs	获取目录列表	-
openlist.batch_rename	批量重命名	src_dir, rename_objects
openlist.regex_rename	正则重命名	src_dir, src_name_regex, new_name_regex
openlist.move_files	移动文件	src_dir, dst_dir, names
openlist.recursive_move	递归移动文件	src_dir, dst_dir
openlist.copy_files	复制文件	src_dir, dst_dir, names
openlist.remove_files	删除文件	dir_path, names
openlist.remove_empty_dir	删除空文件夹	src_dir
openlist.add_offline_download	新建离线下载	path, urls, tool, delete_policy
openlist.get_archive_meta	获取压缩文件元信息	path
openlist.list_archive	列出压缩包内容	path, inner_path
openlist.decompress_archive	解压缩文件	src_dir, dst_dir, name, inner_path
