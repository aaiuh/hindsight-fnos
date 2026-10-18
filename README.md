# Hindsight 飞牛 fnOS 原生适配版

把 [Hindsight](https://github.com/vectorize-io/hindsight)（Agent 长期记忆系统）打成飞牛 fnOS 的**原生应用**：不依赖 Docker，直接以系统服务运行，支持飞牛「应用备份 / 恢复」。

> [!IMPORTANT]
> **管理界面需要 Node.js 20 及以上（建议 22 / 24），本应用不随包携带，请先在应用中心装好 Node.js 应用。**
> 未装也能安装使用：记忆服务与接口照常工作，只有管理界面会显示提示页；之后补装 Node.js，把本应用「停止」再「启动」即可生效，不用重装、数据不动。
>
> 装完服务就会起来，但默认**不抽取记忆**。Hindsight 靠大模型把内容拆成事实，需要你在 `hindsight.env` 里填一个 OpenAI 兼容的模型地址（本机 Ollama 最省事）。
> 语义嵌入与重排模型已随包内置，不需要下载、不需要 GPU。

## 安装

推荐加到集合源（本应用是其中一员）：

```
https://github.com/aaiuh/fnos-apps
```

也可以只加本仓库：

```
https://github.com/aaiuh/hindsight-fnos
```

两种选一种即可 —— 同时加两个，FnDepot 会提示「外部源内容重叠」。

应用说明、装完要做什么、环境要求，见 **[Hindsight/README.md](Hindsight/README.md)**。

## 这个仓库是什么

| 目录 / 文件 | 作用 |
|---|---|
| `pkg/` | fpk 包内容：manifest、启动脚本、备份联动、安装向导 |
| `build/` | 组装运行时、打 fpk、登记版本的脚本 |
| `.github/workflows/build.yml` | 云端构建：取上游版本 → 装运行时 → 打包 → 冒烟测试 → 发 Release → 改索引 |
| `fnpack.json` | 单应用源索引（集合源由 [fnos-apps](https://github.com/aaiuh/fnos-apps) 汇总） |
| `NOTICE.md` | 完整声明：版权、与上游关系、数据与联网、免责 |
| `LICENSE` | 上游 MIT 全文 + 适配层授权 |
| `THIRD-PARTY-NOTICES.md` | 运行时内第三方组件与许可分布 |

构建全部在 GitHub Actions 完成，本机不需要环境。触发方式：打标签（`v1.0.0-4`）、Actions 页面手动、或每周一自动比对上游。

安装包只有几十 KB，真正的运行时（约 680 MB，含官方管理控制台）作为 Release 资源，安装时自动下载。
管理界面所需的 Node.js **不在包内**，由使用者在应用中心自行安装。

## 与上游的关系

本仓库为**社区适配打包**，不是 Hindsight 官方项目，与 Vectorize AI, Inc. **无隶属、无授权、无背书关系**。
问题请提交到本仓库 [Issues](https://github.com/aaiuh/hindsight-fnos/issues)，不要打扰上游作者。

Hindsight 本体的全部版权归 Vectorize AI, Inc. 所有，依 MIT 协议原样分发。

## 授权

- Hindsight 本体：MIT · Copyright (c) 2025 Vectorize AI, Inc.
- 本仓库适配层（`pkg/`、`build/`、`.github/`）：MIT

详见 [LICENSE](LICENSE)、[NOTICE.md](NOTICE.md)、[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
