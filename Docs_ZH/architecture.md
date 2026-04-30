# 架构文档

## 概述

Playlist Administrator 是一个音乐库管理工具，用于从本地音频文件构建和更新 Spotify 播放列表。它使用 Spotify 的嵌入页面进行抓取（无需认证），专注于播放列表的 MP3 文件。

## 核心组件

### 核心模块 (`core/`)

- **`spotify_playlist_fetcher.py`**: 通过嵌入页面获取 Spotify 播放列表
  - `fetch_legacy_embed_playlist()`: 获取播放列表曲目的主要函数
  - `fetch_playlist()`: 统一接口（简化为仅使用嵌入页面）
  - 已移除: `SpotifyWebAPI` 类和 `fetch_via_web_api()` 函数

- **`spotify.py`**: Spotify 抓取和播放列表构建
  - `scrape_via_spotify_embed()`: 主要抓取函数
  - 解析嵌入页面以提取曲目信息
  - 构建 `.m3u8` 播放列表文件
  - 强制仅匹配 MP3 文件用于播放列表

- **`library.py`**: 库管理和文件操作
  - `update_library_logic()`: 主要更新工作流
  - 已移除: M4A 转 MP3 转换函数
  - 已移除: `_resolve_spotube_paths()`, `_has_m4a_files()`, `_get_m4a_cache_key()`, `_m4a_files_from_source()`, `convert_spotube_m4a_to_mp3()`

- **`audio_converter.py`**: 音频格式转换
  - `convert_audio_file()`: 通用音频转换
  - `_migrate_m4a_metadata_to_mp3()`: 元数据迁移（读取 M4A，写入 MP3 - 不修改 M4A）

- **`downloader.py`**: 下载工具（yt-dlp, DAB, spotDL）
  - 默认更新流程中不使用
  - 可手动使用

### GUI (`gui/`)

- **`app.py`**: Tkinter 主应用程序
  - 已移除: `load_playlist_into_player()` 调用（函数不存在）
  - 简化的播放列表加载，仅记录选择

- **`settings.py`**: 设置窗口
  - 已移除: Spotify OAuth 登录部分
  - 已移除: M4A/MP3 子文件夹设置
  - 已移除: 转换工作进程设置
  - 已移除: "优先 MP3" 复选框
  - 保留: 语言、基本路径、ffmpeg 路径

### CLI (`cli.py`)

- **`update`**: 运行完整更新流程
- **`scrape`**: 仅抓取 Spotify URL
- **`fetch-playlist`**: 通过嵌入页面获取播放列表曲目
- **`match`**: 测试本地匹配
- 已移除: `convert-playlist` 命令

### 配置 (`utils/config.py`)

已移除的设置:
- `spotube_m4a_subfolder`
- `spotube_mp3_subfolder`
- `prefer_mp3_playlists`
- `spotube_convert_workers`
- `spotify_client_id`
- `spotify_client_secret`
- `spotify_fetch_method`

保留的设置:
- `base_path`
- `ffmpeg_path`
- `spotube_folder_name`
- `spotube_exact_match`

## 最近变更

### Spotify API 移除
- 移除 Spotify Web API 集成（OAuth、客户端凭证）
- 移除 `SpotifyWebAPI` 类和所有认证逻辑
- 简化为仅使用嵌入页面抓取
- 获取 Spotify 播放列表无需认证

### M4A 转换移除
- 移除 M4A 转 MP3 转换功能
- 移除 M4A 文件夹创建和管理
- 移除转换工作进程设置
- 移除 M4A 缓存系统
- 播放列表现在仅使用 MP3 文件

### GUI 简化
- 移除 Spotify OAuth 登录界面
- 移除 M4A/MP3 子文件夹配置
- 移除转换设置
- 修复缺失的 `load_playlist_into_player` 方法错误

### CLI 清理
- 移除 `convert-playlist` 命令
- 保留核心功能: update, scrape, fetch-playlist, match

## 文件结构

```
Playlist Administrator/
├── main.py                    # Tkinter 入口点
├── streamlit_app.py           # Streamlit UI
├── cli.py                     # 命令行接口
├── core/
│   ├── spotify_playlist_fetcher.py  # Spotify 获取（仅嵌入页面）
│   ├── spotify.py                    # Spotify 抓取和播放列表构建
│   ├── library.py                    # 库管理
│   ├── audio_converter.py            # 音频转换
│   ├── downloader.py                 # 下载工具
│   ├── sync_manager.py              # 同步操作
│   ├── metadata_enricher.py          # 元数据丰富
│   └── file_renamer.py              # 文件重命名
├── gui/
│   ├── app.py                       # Tkinter 主应用
│   └── settings.py                  # 设置窗口
├── utils/
│   ├── config.py                    # 配置
│   ├── helpers.py                   # 辅助函数
│   └── i18n.py                      # 国际化
├── tools/
│   └── fix_flac_names.py            # FLAC 命名工具
├── docs/
│   └── architecture.md              # 本文档（英文）
├── Docs_ZH/
│   └── architecture.md              # 本文档（中文）
├── README.md                        # 英文文档
├── README_ZH.md                     # 中文文档
└── requirements.txt                 # Python 依赖
```

## 工作流程

1. **设置**: 配置基本路径（包含 Music/ 和 Playlists/）
2. **添加 URL**: 添加 Spotify 播放列表/专辑/艺人 URL
3. **更新**: 运行更新流程
   - 通过嵌入页面抓取 Spotify URL
   - 构建本地音频文件库索引
   - 匹配 Spotify 曲目到本地 MP3 文件
   - 创建/更新 `.m3u8` 播放列表文件
   - 从播放列表中移除缺失的条目
   - 将未排序的曲目移动到 `_Unsorted`
4. **导出**: 根据需要导出播放列表到 USB/SD

## 注意事项

- Spotify 抓取需要网络访问但无需认证
- 播放列表仅使用 MP3 文件
- M4A 文件不会被应用程序修改
- 下载工具存在但默认流程中不使用
- FFmpeg 是可选的（仅音频转换时需要）
