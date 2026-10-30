"""生成演示字幕稿 / 回归剧本。

    python tools/demo.py                # 重放剧本并打印摘要
    python tools/demo.py --md           # 同时写出 runtime/demo_transcript.md
    python tools/demo.py --quiet        # 只打印通过情况
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, ".pylibs"), ROOT):
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

from app import demo  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", action="store_true", help="写出 runtime/demo_transcript.md")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    result = demo.run()
    if not args.quiet:
        for s in result["steps"]:
            flag = "PASS" if s["ok"] else "FAIL"
            print(f"[{flag}] {s['id']:3s} {s['scene']:14s} "
                  f"{s['initial_status']:17s} → {s['final_status']:17s} "
                  f"tier={s['tier'] or '-':7s} mfa={s['used_mfa'] or '-'}")
            if not s["ok"]:
                print(f"       期望 {s['expect']}, 实际 {s['final_status']}")
                print(f"       回复: {(s['reply'] or '')[:120]}")
    print(f"\n剧本 {result['total']} 步, 通过 {result['passed']}, 失败 {result['failed']} "
          f"({result['elapsed_ms']} ms)")

    if args.md:
        os.makedirs(os.path.join(ROOT, "runtime"), exist_ok=True)
        path = os.path.join(ROOT, "runtime", "demo_transcript.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(demo.transcript_markdown(result))
        print(f"字幕稿已写入 {path}")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
