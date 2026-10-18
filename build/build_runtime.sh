#!/bin/bash
### 组装 Hindsight 原生运行时（本机与 GitHub Actions 共用同一份脚本）
### 用法：build_runtime.sh <hindsight-version> <输出目录>
### 产物：<输出目录>/runtime/{python,venv,hf,pg0,flashrank} + runtime-<ver>.tar.zst
set -euo pipefail

VER="${1:?用法: build_runtime.sh <version> <outdir>}"
OUT="${2:?缺少输出目录}"
# PIP_VER：真正要从 PyPI 装的 upstream 版本（打包修订号如 1.0.0-1 时装 1.0.0）
PIP_VER="${PIP_VER:-$VER}"
ZSTD_LEVEL="${ZSTD_LEVEL:-15}"
PY_VER="${PY_VER:-3.12}"

OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
RUNTIME="$OUT/runtime"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

say() { echo "[runtime] $*"; }

rm -rf "$RUNTIME"
mkdir -p "$RUNTIME"

# ── 1. 自带 Python（python-build-standalone，可随包搬迁）────────────────
say "安装 Python $PY_VER 到包内"
uv python install "$PY_VER" --install-dir "$RUNTIME/python" >/dev/null
# uv 会同时建一个不带小版本号的软链，取真正的版本目录
PYREAL="$(find "$RUNTIME/python" -maxdepth 1 -type d -name 'cpython-*' | sort -V | tail -1)"
[ -n "$PYREAL" ] || { echo "找不到 uv 安装的 CPython" >&2; exit 1; }
say "python 目录: $(basename "$PYREAL")"
mv "$PYREAL" "$RUNTIME/.py"
rm -rf "$RUNTIME/python"
mv "$RUNTIME/.py" "$RUNTIME/python"
PYBIN="$RUNTIME/python/bin/python${PY_VER}"
[ -x "$PYBIN" ] || { echo "缺少 $PYBIN" >&2; ls "$RUNTIME/python/bin" >&2; exit 1; }
say "python: $("$PYBIN" -V 2>&1)"

# ── 2. 可重定位 venv（home 在应用启动时改写为包内路径）──────────────────
say "创建 venv"
uv venv --relocatable "$RUNTIME/venv" --python "$PYBIN" >/dev/null
VENV_PY="$RUNTIME/venv/bin/python"

# ── 3. 依赖：hindsight + 嵌入式 pg + onnx 推理 + flashrank 重排 ─────────
say "安装 hindsight-api-slim[embedded-db,local-onnx]==$PIP_VER"
uv pip install --python "$VENV_PY" --quiet \
    "hindsight-api-slim[embedded-db,local-onnx]==$PIP_VER" \
    "flashrank==0.2.10"

say "已装包数：$(uv pip list --python "$VENV_PY" 2>/dev/null | wc -l)"

# ── 4. flashrank 重排模型（33 MB，随包）───────────────────────────────
say "取 flashrank 模型"
mkdir -p "$RUNTIME/flashrank"
FR_ZIP="$WORK/flashrank.zip"
FR_URL="https://huggingface.co/prithivida/flashrank/resolve/main/ms-marco-MiniLM-L-12-v2.zip"
curl -fL --retry 3 --retry-delay 3 -o "$FR_ZIP" "$FR_URL"
mkdir -p "$WORK/fr" && unzip -q "$FR_ZIP" -d "$WORK/fr"
FR_DIR="$(find "$WORK/fr" -maxdepth 2 -name "flashrank-*.onnx" -printf '%h\n' | head -1)"
[ -n "$FR_DIR" ] || { echo "flashrank 模型解压后找不到 onnx" >&2; exit 1; }
mv "$FR_DIR" "$RUNTIME/flashrank/ms-marco-MiniLM-L-12-v2"
ls "$RUNTIME/flashrank/ms-marco-MiniLM-L-12-v2" | sed 's/^/    /'

# ── 4b. 官方管理控制台：从上游镜像原样取出，不做任何改动 ─────────────────
# 控制台是上游发布的 Next.js 产物，随包分发的只是这份产物；
# 运行它需要系统已装 Node.js（见 NOTICE.md「运行依赖」）。
say "取官方管理控制台（upstream 镜像内的 control-plane，原样复制）"
CP_IMAGE="${CP_IMAGE:-ghcr.io/vectorize-io/hindsight:latest}"
if command -v docker >/dev/null 2>&1; then
    docker pull -q "$CP_IMAGE" >/dev/null
    CP_CID="$(docker create "$CP_IMAGE")"
    mkdir -p "$RUNTIME/control-plane"
    docker cp "$CP_CID:/app/control-plane/." "$RUNTIME/control-plane/"
    CP_DIGEST="$(docker inspect "$CP_IMAGE" --format '{{range .RepoDigests}}{{println .}}{{end}}' | head -1)"
    docker rm "$CP_CID" >/dev/null
    {
        echo "image=$CP_IMAGE"
        echo "digest=$CP_DIGEST"
        echo "path=/app/control-plane"
        echo "note=原样复制，未修改任何文件"
    } > "$RUNTIME/control-plane-source.txt"
    say "control-plane: $(du -sh "$RUNTIME/control-plane" | cut -f1)  （$CP_DIGEST）"
else
    say "构建环境没有 docker，跳过 control-plane（安装后管理界面会提示缺少控制台）"
fi

# ── 5. 首次启动：让它自己下嵌入模型、装嵌入式 pg（并当作冒烟测试）──────
say "首次启动（下载嵌入模型 + 安装嵌入式 PostgreSQL，约 5–10 分钟）"
export HOME="$WORK/home"
mkdir -p "$HOME" "$RUNTIME/hf" "$WORK/tmp/ms-marco-MiniLM-L-12-v2"
cp -a "$RUNTIME/flashrank/ms-marco-MiniLM-L-12-v2/." "$WORK/tmp/ms-marco-MiniLM-L-12-v2/"
export TMPDIR="$WORK/tmp"
export HF_HOME="$RUNTIME/hf"
export HF_ENDPOINT="${HF_ENDPOINT:-https://huggingface.co}"
export HF_HUB_DISABLE_XET=1
export TRANSFORMERS_VERBOSITY=error
export HINDSIGHT_API_HOST=127.0.0.1
export HINDSIGHT_API_PORT=18888
export HINDSIGHT_CP_DATAPLANE_API_URL="http://127.0.0.1:18888"
export HINDSIGHT_API_EMBEDDINGS_PROVIDER=onnx
export HINDSIGHT_API_RERANKER_PROVIDER=flashrank
export HINDSIGHT_API_LLM_PROVIDER=openai
export HINDSIGHT_API_LLM_BASE_URL="http://127.0.0.1:1/v1"
export HINDSIGHT_API_LLM_MODEL=dummy
export HINDSIGHT_API_LLM_API_KEY=dummy

"$RUNTIME/venv/bin/hindsight-api" --host 127.0.0.1 --port 18888 > "$WORK/api.log" 2>&1 &
API_PID=$!
trap 'kill -9 "$API_PID" 2>/dev/null || true; rm -rf "$WORK"' EXIT

ready=0
for i in $(seq 1 200); do
    if curl -fsS "http://127.0.0.1:18888/health" >/dev/null 2>&1; then ready=1; break; fi
    kill -0 "$API_PID" 2>/dev/null || break
    sleep 3
done
if [ "$ready" != "1" ]; then
    echo "── 启动失败，日志尾部 ──" >&2
    tail -40 "$WORK/api.log" >&2
    exit 1
fi
say "健康检查通过"
curl -fsS "http://127.0.0.1:18888/health" | head -c 400; echo

kill "$API_PID" 2>/dev/null || true
for i in $(seq 1 30); do kill -0 "$API_PID" 2>/dev/null || break; sleep 1; done
kill -9 "$API_PID" 2>/dev/null || true
pkill -f "instances/hindsight/data" 2>/dev/null || true
sleep 2

# ── 6. 把 pg 二进制收进包里（数据目录不打包）──────────────────────────
if [ -d "$HOME/.pg0/installation" ]; then
    mkdir -p "$RUNTIME/pg0"
    cp -a "$HOME/.pg0/installation" "$RUNTIME/pg0/installation"
    say "嵌入式 pg: $(du -sh "$RUNTIME/pg0/installation" | cut -f1)"
else
    echo "没有生成 .pg0/installation，打包会失败" >&2
    exit 1
fi

# ── 7. 清掉不该进包的东西 ────────────────────────────────────────────
rm -rf "$RUNTIME/venv"/{share/man,include} 2>/dev/null || true
find "$RUNTIME" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$RUNTIME" -name "*.pyc" -delete 2>/dev/null || true

say "包内体积："
du -sh "$RUNTIME"/* | sed 's/^/    /'

# ── 8. 压缩 ─────────────────────────────────────────────────────────
TARBALL="$OUT/hindsight-runtime-${VER}.tar.zst"
rm -f "$TARBALL"
say "压缩（zstd -$ZSTD_LEVEL，约 10–20 分钟）"
tar -C "$RUNTIME" -I "zstd -${ZSTD_LEVEL} -T0" -cf "$TARBALL" .

SHA=$(sha256sum "$TARBALL" | awk '{print $1}')
SIZE=$(stat -c %s "$TARBALL")
{
    echo "version=$VER"
    echo "sha256=$SHA"
    echo "size=$SIZE"
} > "$OUT/runtime-${VER}.meta"
say "完成：$TARBALL"
say "  $(numfmt --to=iec "$SIZE")  sha256=$SHA"
