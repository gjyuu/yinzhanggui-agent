"""把 GSAP 装进本地 vendor 目录(演示现场不依赖 CDN)。

    python tools/fetch_gsap.py            # 从镜像列表依次尝试
    python tools/fetch_gsap.py --check    # 只看当前是否已装好

装好后无需改任何代码: web/motion.js 会自动检测 window.gsap 并切换为 GSAP 时间轴。
许可证: GSAP 标准"免费"许可 (https://gsap.com/community/standard-license/),
        自 2025-04-30 起商业项目亦免费, 唯一限制是不得用它做与 Webflow 竞争的可视化动画搭建器。
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "web", "vendor", "gsap.min.js")
VERSION = "3.13.0"
MIRRORS = [
    f"https://cdn.jsdelivr.net/npm/gsap@{VERSION}/dist/gsap.min.js",
    f"https://unpkg.com/gsap@{VERSION}/dist/gsap.min.js",
    f"https://cdnjs.cloudflare.com/ajax/libs/gsap/{VERSION}/gsap.min.js",
    f"https://lib.baomitu.com/gsap/{VERSION}/gsap.min.js",
    f"https://registry.npmmirror.com/gsap/{VERSION}/files/dist/gsap.min.js",
]
MIN_SIZE = 40_000          # gsap.min.js 约 70KB, 太小说明被网关拦截返回了错误页


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if os.path.exists(TARGET):
        print(f"已存在: {TARGET} ({os.path.getsize(TARGET)} bytes)")
        return 0
    if args.check:
        print("未安装 GSAP, 当前使用原生 Web Animations API 降级模式")
        return 1

    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    for url in MIRRORS:
        try:
            print(f"尝试 {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "yinzhanggui-bootstrap/1.0"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = resp.read()
            if len(data) < MIN_SIZE:
                print(f"  太小({len(data)} bytes), 跳过")
                continue
            with open(TARGET, "wb") as fh:
                fh.write(data)
            print(f"完成: {TARGET} ({len(data)} bytes)")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"  失败: {exc}")
    print("\n全部镜像不可达。可手动下载 gsap.min.js 放入 web/vendor/ —— 代码无需改动。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
