# 第三方组件声明（THIRD-PARTY NOTICES）

本仓库的安装包（`Hindsight-*.fpk`）本身只有脚本与元数据，**不含**第三方二进制。
安装时下载的运行时包（`hindsight-runtime-*.tar.zst`，约 620 MB）内含下列组件，
它们各自遵循原许可证，本仓库不对其做任何再许可。

## 主要组件

| 组件 | 版本 | 许可 | 说明 |
|---|---|---|---|
| Hindsight（`hindsight-api` / `hindsight-api-slim`） | 见 `fnpack.json` | MIT · Vectorize AI, Inc. | 上游本体，PyPI 官方发布包，未改动 |
| Hindsight 管理控制台（`@vectorize-io/hindsight-control-plane`） | 0.10.3 | MIT · Vectorize AI, Inc. | 取自上游官方容器镜像 `/app/control-plane`，原样打包，未修改 |
| Next.js（控制台运行框架） | 16.4.0 | MIT | 随控制台一起分发 |
| 控制台前端依赖（React 等，`node_modules`） | 随控制台 | MIT / Apache-2.0 / ISC | 见控制台目录内各包的 `package.json` 与 `LICENSE` |
| Python（python-build-standalone） | 3.12 | PSF-2.0 | 随包自带的解释器 |
| PostgreSQL | 18.1 | PostgreSQL License | 嵌入式数据库二进制 |
| pgvector | — | PostgreSQL License | 向量检索扩展 |
| onnxruntime | 1.31.0 | MIT | 本地推理引擎 |
| transformers / tokenizers / huggingface_hub | 5.15 / 0.22 / 1.33 | Apache-2.0 | 模型加载 |
| flashrank | 0.2.10 | Apache-2.0 | 本地重排 |
| multilingual-e5-small | — | MIT | 语义嵌入模型（intfloat） |
| ms-marco-MiniLM-L-12-v2 | — | Apache-2.0 | 重排模型（prithivida/flashrank 分发） |

## 未随包分发的运行依赖

| 依赖 | 说明 |
|---|---|
| **Node.js（≥ 20，建议 22 / 24）** | 管理控制台需要它执行。**不随包分发**，运行时优先使用飞牛应用中心已安装的 Node.js 应用，其次使用系统 PATH 中的 `node`；两者的许可与版本由使用者自行安装的组件决定 |
| 大模型服务 | 事实抽取需要使用者自行提供的 OpenAI 兼容服务，不在本项目分发范围内 |

## 其余依赖

运行时共约 194 个 Python 包，许可分布大致为
MIT（约 27 个）、Apache-2.0（约 16 个）、BSD-2/3-Clause（约 9 个）、
ISC、PSF-2.0，另有 1 个 LGPL-with-exceptions 组件（动态链接使用，未修改）。

约 123 个包的元数据未声明 `License` 字段，其实际许可以其自身 `METADATA` / `LICENSE`
文件或上游仓库为准。

## 如何自取完整清单

安装后在本机执行：

```bash
SP=/vol1/@appcenter/Hindsight/runtime/venv/lib/python3.12/site-packages
for d in "$SP"/*.dist-info; do
  printf '%-32s %-12s %s\n' \
    "$(grep -m1 -i '^Name:' "$d/METADATA" | cut -d' ' -f2-)" \
    "$(grep -m1 -i '^Version:' "$d/METADATA" | cut -d' ' -f2-)" \
    "$(grep -m1 -i '^License:' "$d/METADATA" | cut -d' ' -f2-)"
done
```

各包完整许可证文本位于对应 `*.dist-info/` 目录内。

## PostgreSQL 与模型的额外说明

- PostgreSQL 与 pgvector 的许可文本随二进制位于
  `runtime/pg0/installation/<版本>/` 目录中。
- 两个 ONNX 模型随包预置，用于离线推理，不再从网络下载。
