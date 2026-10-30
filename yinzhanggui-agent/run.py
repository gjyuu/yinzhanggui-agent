"""本地启动入口。

    python run.py            # 默认 http://127.0.0.1:8000
    python run.py 8080       # 指定端口
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PYLIBS = os.path.join(ROOT, ".pylibs")
if os.path.isdir(PYLIBS) and PYLIBS not in sys.path:
    sys.path.insert(0, PYLIBS)          # 兼容无 pip 权限的环境 (见 tools/getdeps.py)

import uvicorn  # noqa: E402

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    print(f"银掌柜 · 银行 AI 智能体  →  http://{host}:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
