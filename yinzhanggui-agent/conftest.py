"""pytest 全局引导: 优先使用本地 .pylibs (见 tools/getdeps.py)。"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PYLIBS = os.path.join(ROOT, ".pylibs")
if os.path.isdir(PYLIBS) and PYLIBS not in sys.path:
    sys.path.insert(0, PYLIBS)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
