#!/usr/bin/env python3
"""把一次构建产物登记进 fnpack.json（FnDepot 外部源 V2 格式）

用法：publish.py <version> <fpk 文件> [--base <下载前缀>]
"""
import datetime
import hashlib
import json
import os
import sys

KEEP_VERSIONS = 10


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    ver = sys.argv[1]
    fpk = sys.argv[2]
    base = f"https://github.com/aaiuh/hindsight-fnos/releases/download/v{ver}"
    if "--base" in sys.argv:
        base = sys.argv[sys.argv.index("--base") + 1].rstrip("/")

    with open(fpk, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    size = os.path.getsize(fpk)

    with open("fnpack.json", encoding="utf-8") as fh:
        doc = json.load(fh)

    # FnDepot 强制要求字符串 "2"，写成数字会直接同步失败
    doc["schema_version"] = "2"

    app = doc["apps"]["hindsight"]
    app["releases"][ver] = {
        "changelog": (
            f"跟随上游 Hindsight {ver}。原生运行，不依赖 Docker；"
            "内置 PostgreSQL 与向量检索，onnx 语义嵌入 + flashrank 重排；"
            "支持飞牛应用备份与恢复。"
        ),
        "updated_at": datetime.date.today().isoformat(),
        "os_min_version": "1.1.0",
        "packages": {
            "x86": {
                "download_url": f"{base}/Hindsight-{ver}-x86.fpk",
                "sha256": sha,
                "size": size,
            }
        },
    }

    # 按版本号排序，只留最近的若干个
    def key(v: str):
        parts = []
        for p in v.replace("-", ".").split("."):
            parts.append(int(p) if p.isdigit() else 0)
        return parts

    ordered = sorted(app["releases"], key=key, reverse=True)
    for old in ordered[KEEP_VERSIONS:]:
        del app["releases"][old]

    with open("fnpack.json", "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    print(f"[publish] {ver} -> {base}/Hindsight-{ver}-x86.fpk")
    print(f"[publish]   sha256={sha}  size={size} ({size / 1048576:.1f} MB)")
    print(f"[publish]   已登记版本：{', '.join(sorted(app['releases'], key=key, reverse=True))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
