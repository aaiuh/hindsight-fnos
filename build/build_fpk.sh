#!/bin/bash
### 打 fpk（轻量包：只有脚本与元数据，运行时由 install_callback 下载）
### 用法：build_fpk.sh <version> <运行时 tar.zst> <输出目录>
set -euo pipefail

VER="${1:?用法: build_fpk.sh <version> <runtime.tar.zst> <outdir>}"
RUNTIME_TAR="${2:?缺少运行时包}"
OUT="${3:?缺少输出目录}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="$ROOT/pkg"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
mkdir -p "$OUT"

[ -f "$RUNTIME_TAR" ] || { echo "运行时包不存在: $RUNTIME_TAR" >&2; exit 1; }
META="$(dirname "$RUNTIME_TAR")/runtime-${VER}.meta"
SHA=$(grep '^sha256=' "$META" | cut -d= -f2)
SIZE=$(grep '^size=' "$META" | cut -d= -f2)
echo "[fpk] 运行时 $(numfmt --to=iec "$SIZE") sha256=$SHA"

# 用临时副本打，避免把替换过的占位符留在仓库里
STAGE="$OUT/.stage-$$"
rm -rf "$STAGE"
cp -a "$PKG" "$STAGE"
trap 'rm -rf "$STAGE"' EXIT

sed -i "s|__VERSION__|$VER|g"        "$STAGE/manifest"
sed -i "s|__VERSION__|$VER|g"        "$STAGE/cmd/install_callback"
sed -i "s|__SHA256__|$SHA|g"         "$STAGE/cmd/install_callback"
sed -i "s|__SIZE__|$SIZE|g"          "$STAGE/cmd/install_callback"
chmod +x "$STAGE/cmd/"*

grep -q "__SHA256__" "$STAGE/cmd/install_callback" && { echo "占位符未替换" >&2; exit 1; }

# app.tgz：安装说明 + 默认参数 + 许可证与声明（MIT 要求随分发附带）
APP="$OUT/.app-$$"
rm -rf "$APP"; mkdir -p "$APP/defaults"
cp "$PKG/defaults/hindsight.env" "$APP/defaults/" 2>/dev/null || true
for f in LICENSE NOTICE.md THIRD-PARTY-NOTICES.md; do
    [ -f "$ROOT/$f" ] && cp "$ROOT/$f" "$APP/"
done
cat > "$APP/INSTALL-NOTES.txt" <<'EOS'
Hindsight 飞牛原生版
====================

程序运行时约 1.5 GB（自带 Python、语义模型、嵌入式 PostgreSQL），
安装时由 install_callback 从下载源拉取到本目录的 runtime/。

数据目录 /vol1/@appdata/Hindsight
  .pg0/instances/hindsight/   记忆库本体（PostgreSQL 数据）
  .pg0/installation           指向包内 pg 二进制（启动时自动重建软链）
  tmp/                        重排模型运行副本
  hindsight.env               LLM 地址、端口等运行参数

备份：「应用中心 → 创建备份」勾选本应用。
备份前会自动停服务，保证 PostgreSQL 数据一致。
EOS
tar -C "$APP" -czf "$STAGE/app.tgz" .
rm -rf "$APP"

# fnOS 校验：manifest 的 checksum 必须是 app.tgz 的 md5，否则安装报 10111
TGZ_MD5=$(md5sum "$STAGE/app.tgz" | awk '{print $1}')
if grep -q '^checksum' "$STAGE/manifest"; then
    sed -i "s|^checksum=.*|checksum=\"${TGZ_MD5}\"|" "$STAGE/manifest"
else
    printf 'checksum="%s"\n' "$TGZ_MD5" >> "$STAGE/manifest"
fi
echo "[fpk] app.tgz md5=$TGZ_MD5"

FPK="$OUT/Hindsight-${VER}-x86.fpk"
rm -f "$FPK"
( cd "$STAGE" && tar --owner=0 --group=0 -cf "$FPK" \
    manifest ICON.PNG ICON_256.PNG app.tgz cmd config defaults wizard )

FPK_SHA=$(sha256sum "$FPK" | awk '{print $1}')
echo "[fpk] 产物 $FPK"
echo "[fpk]   $(numfmt --to=iec "$(stat -c %s "$FPK")")  sha256=$FPK_SHA"
tar -tf "$FPK" | sed 's/^/    /'
