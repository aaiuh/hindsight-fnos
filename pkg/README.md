# Hindsight 飞牛原生版

Hindsight 是一个 **Agent 长期记忆系统**（语义记忆、事实抽取、时间线、关系图）。
本仓库把它做成**飞牛 fnOS 原生应用**：不依赖 Docker，直接以系统服务方式运行。

> [!IMPORTANT]
> **装完服务就会起来，但默认不抽取记忆。**
> Hindsight 靠大模型把内容拆成事实，需要你自己填一个 OpenAI 兼容的模型地址
> （本机 Ollama 最省事）。详见 [装完要做什么](#装完要做什么)。
> 语义嵌入与重排模型已随包内置，不需要下载、不需要 GPU。

## 为什么做原生版

官方只提供 Docker 镜像（`ghcr.io/vectorize-io/hindsight`）。对飞牛用户来说：

| | Docker 版 | 本原生版 |
|---|---|---|
| 依赖 | 需要 Docker 服务 | 无需 Docker |
| 安装 | 手动 `docker run` + 写 compose | 应用中心一键安装 |
| 数据目录 | docker volume（藏在 `/vol1/docker/volumes`）| `@appdata/Hindsight`，飞牛统一管理 |
| 备份 | 自己写脚本 | **飞牛「创建备份」原生支持** |
| 升级 | 手动 pull | 应用商店检测更新 |

## 技术形态

```
Python 3.12（python-build-standalone，随包自带）
└── venv（可重定位，启动时自动改写路径）
    ├── hindsight-api            官方 PyPI 包
    ├── 嵌入式 PostgreSQL 18     随包二进制，数据在 @appdata/Hindsight/.pg0
    ├── 语义嵌入 onnx            multilingual-e5-small（无需 torch）
    └── 重排 flashrank           ms-marco-MiniLM-L-12-v2（ONNX）
```

- 后端 API：`8888`（REST + MCP）
- 控制台：`9999`（由 API 一并提供）
- 数据：`/vol1/@appdata/Hindsight`

## 构建方式

**全部在 GitHub Actions 上构建**，不需要本地环境：

| 文件 | 作用 |
|---|---|
| `.github/workflows/build.yml` | 取上游版本 → 组装运行时 → 打 fpk → 冒烟测试 → 发布 Release → 登记索引 |
| `build/build_runtime.sh` | 组装自带 python + venv + 模型 + 嵌入式 pg，压缩成运行时包 |
| `build/build_fpk.sh` | 打轻量 fpk（脚本 + 元数据，运行时安装时下载） |
| `build/publish.py` | 把版本写进 `fnpack.json` |

触发方式：

- **自动**：每周一 02:00（北京时间）比对 PyPI 上游版本，有新版就构建
- **手动**：Actions → 构建 Hindsight 原生版 → Run workflow（可指定版本或强制重建）
- **打标签**：`git tag v1.0.1 && git push --tags`

安装包只有几十 KB，真正的运行时（约 620 MB）作为 Release 资源发布，安装时由
`install_callback` 按「国内镜像（gh-proxy → ghfast）→ GitHub 直连」的顺序尝试下载。
除 GitHub 以外不依赖任何第三方分发站。

## 安装

在飞牛「应用中心 → FnDepot → 源管理 → 添加源」里填**仓库地址**：

```
https://github.com/aaiuh/hindsight-fnos
```

FnDepot 会自己去找仓库里的 `fnpack.json`。若它取不到，再填完整文件地址：

```
https://raw.githubusercontent.com/aaiuh/hindsight-fnos/main/fnpack.json
```

同步后即可在应用中心看到「Hindsight 记忆库」，支持安装、升级、备份、恢复。

安装时下载运行时（约 620 MB），按以下顺序自动尝试，实测国内可达：

1. `gh-proxy.com` 镜像（约 8–9 MB/s）
2. `ghfast.top` 镜像（约 5 MB/s）
3. GitHub 直连

## 装完要做什么

装完服务会自己起来，`http://<NAS地址>:8888/docs` 能打开接口文档。
但**要用起来还差一步：给 Hindsight 一个能用的大模型**，否则只存不抽。

思路是改 `hindsight.env` 里的四行，然后重启应用：

```ini
HINDSIGHT_API_LLM_PROVIDER=openai        # 或 ollama / litellm
HINDSIGHT_API_LLM_BASE_URL=http://127.0.0.1:11434/v1
HINDSIGHT_API_LLM_MODEL=qwen2.5:7b
HINDSIGHT_API_LLM_API_KEY=               # 本地服务一般留空
```

- 文件位置：`/vol1/@appdata/Hindsight/hindsight.env`
- 改完在应用中心点「停止」再「启动」（或 `systemctl restart hindsight-native`）
- 任何 OpenAI 兼容服务都行：Ollama、llama.cpp、vLLM、LM Studio、各家云 API
- 语义嵌入与重排模型随包内置，**不需要额外下载，也不需要 GPU**

## 给别人装的环境要求

| 项 | 要求 |
|---|---|
| 平台 | x86_64（本包不含 ARM 版） |
| fnOS | ≥ 1.1.0 |
| 磁盘 | 程序 + 运行时约 1.8 GB（装到 `/vol1/@appcenter`），数据另算 |
| 内存 | 启动后常驻约 1.2–1.5 GB |
| 端口 | 8888（可在安装向导里改） |
| 网络 | 仅安装时需要访问 GitHub；日常运行完全离线 |

## 备份

应用中心「创建备份」勾选本应用即可。备份时会：

1. 停掉服务，保证 PostgreSQL 数据一致
2. 打包 `.pg0/instances/hindsight`（记忆库本体）与 `hindsight.env`
3. 恢复服务

恢复时反向操作，写回数据后重新拉服务。

## 授权与声明

| 内容 | 说明 |
|---|---|
| Hindsight 本体 | MIT · Copyright (c) 2025 Vectorize AI, Inc.，见 [LICENSE](LICENSE) |
| 本仓库适配层 | 同样以 MIT 发布（`pkg/`、`build/`、`.github/`） |
| 运行时第三方组件 | 各有其许可，见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) |
| 完整声明（含免责、数据说明、与上游关系） | [NOTICE.md](NOTICE.md) |

本仓库为社区适配打包，与 Vectorize AI, Inc. 无隶属、无授权、无背书关系。
问题请提交到本仓库 Issues，不要打扰上游作者。
