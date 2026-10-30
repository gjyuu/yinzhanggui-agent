"""离线依赖获取器 (offline dependency fetcher)。

常规环境直接:  pip install -r requirements.txt

若环境禁止 pip 清理临时目录(受限沙箱 / 只读内网机), 可用本脚本:
    python tools/getdeps.py               # 解包到 .pylibs/
    python tools/getdeps.py -d vendor     # 自定义目录

做法: 从镜像站取 simple 索引 → 下载与当前解释器匹配的 wheel →
从 wheel 内的 METADATA 读取 Requires-Dist 递归解析 → 解包。
不产生需要删除的临时目录, 因此可在删除受限的环境里工作。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REQUIREMENTS = ["fastapi", "uvicorn", "pytest", "httpx"]
INDEXES = [
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple",
    "https://pypi.org/simple",
]
UA = {"User-Agent": "yinzhanggui-bootstrap/1.0"}
PY_TAG = f"cp{sys.version_info.major}{sys.version_info.minor}"
PLATFORM_TAG = "win_amd64" if os.name == "nt" else "manylinux"


# ---------------------------------------------------------------- 网络
def fetch(url: str, timeout: int = 120, tries: int = 3) -> bytes:
    last: Optional[Exception] = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"下载失败 {url}: {last}")


def index_page(name: str) -> str:
    norm = name.lower().replace("_", "-")
    for base in INDEXES:
        try:
            return fetch(f"{base}/{norm}/", timeout=60, tries=1).decode("utf-8", "ignore")
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError(f"无法从任何镜像获取 {name} 的索引")


# ---------------------------------------------------------------- 版本与匹配
def ver_key(name: str) -> Tuple:
    m = re.match(r"^[^-]+-(?P<v>[0-9][^-]*)", name)
    if not m:
        return (0,)
    parts = re.findall(r"\d+", m.group("v"))
    return tuple(int(p) for p in parts) if parts else (0,)


def wheel_ok(fname: str) -> bool:
    if not fname.endswith(".whl"):
        return False
    if re.search(r"(rc|a\d|b\d|dev|alpha|beta)", fname, re.I):
        return False
    if re.search(r"cp\d+t-", fname):
        return False        # 排除 free-threaded 构建 (cp314t)
    if re.search(rf"{PY_TAG}-{PY_TAG}(?![0-9a-z])", fname) and PLATFORM_TAG in fname:
        return True
    if "abi3" in fname and PLATFORM_TAG in fname:
        return True
    if fname.endswith("-none-any.whl"):
        return True
    return False


def pick_wheel(html: str, name: str) -> Optional[Tuple[str, str]]:
    """返回 (文件名, 绝对下载地址)。索引按版本升序, 取最新的兼容 wheel。"""
    norm = name.lower().replace("-", "_")
    cands: List[Tuple[Tuple, str, str]] = []
    for href, label in re.findall(r'href="([^"]+)"[^>]*>([^<]+)</a>', html):
        fname = label.strip() or href.rsplit("/", 1)[-1]
        fname = fname.split("#")[0]
        if not wheel_ok(fname):
            continue
        if not fname.lower().startswith(norm + "-"):
            continue
        url = href if href.startswith("http") else None
        if url is None or "#" in href:
            # tuna/aliyun 的 href 通常是相对路径 + #sha256
            base = href.split("#")[0]
            cands.append((ver_key(fname), fname, base))
        else:
            cands.append((ver_key(fname), fname, url))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0])
    _, fname, rel = cands[-1]
    return fname, rel


def resolve_url(name: str, rel: str) -> str:
    if rel.startswith("http"):
        return rel
    norm = name.lower().replace("_", "-")
    for base in INDEXES:
        try:
            fetch(f"{base}/{norm}/", timeout=30, tries=1)
            return base + "/" + norm + "/" + rel
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError(f"无法解析下载地址 {rel}")


# ---------------------------------------------------------------- 元数据
def requires_from_wheel(path: str) -> List[str]:
    reqs: List[str] = []
    with zipfile.ZipFile(path) as zf:
        meta = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")]
        if not meta:
            return reqs
        text = zf.read(meta[0]).decode("utf-8", "ignore")
    for line in text.splitlines():
        if not line.lower().startswith("requires-dist:"):
            continue
        body = line.split(":", 1)[1].strip()
        base, _, marker = body.partition(";")
        if marker.strip() and not marker_ok(marker.strip()):
            continue
        dep = re.sub(r"\[.*?\]", "", base)
        dep = re.split(r"\s*[(<>=!~;]", dep)[0].strip()
        if dep and dep.lower() != "python":
            reqs.append(dep)
    return reqs


def marker_ok(marker: str) -> bool:
    if not marker:
        return True
    if "extra" in marker and "extra ==" not in marker.replace(" ", " "):
        return False
    for clause in marker.split(" or "):
        if _clause_ok(clause):
            return True
    return False


def _clause_ok(clause: str) -> bool:
    clause = clause.strip()
    if clause.startswith("extra"):
        return False
    found = False
    for m in re.finditer(
        r'(python_version|platform_system|sys_platform|os_name)\s*(==|!=|>=|<=|>|<)\s*["\']([^"\']+)["\']',
        clause,
    ):
        found = True
        key, op, want = m.group(1), m.group(2), m.group(3)
        if key == "python_version":
            have = f"{sys.version_info.major}.{sys.version_info.minor}"
        elif key in ("platform_system", "os_name"):
            have = "Windows" if os.name == "nt" else "Linux"
        else:
            have = "win32" if os.name == "nt" else "linux"
        try:
            h = tuple(int(x) for x in have.split("."))
            w = tuple(int(x) for x in want.split("."))
        except ValueError:
            h, w = (have,), (want,)
        if not {"==": h == w, "!=": h != w, ">=": h >= w, "<=": h <= w,
                ">": h > w, "<": h < w}[op]:
            return False
    return True if found or "extra" not in clause else False


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-d", "--dir", default=os.path.join(ROOT, ".pylibs"))
    ap.add_argument("packages", nargs="*", default=DEFAULT_REQUIREMENTS)
    args = ap.parse_args()
    target = args.dir
    os.makedirs(target, exist_ok=True)

    queue: List[str] = list(args.packages)
    seen: Dict[str, str] = {}
    ok, failed = 0, []
    while queue:
        raw = queue.pop(0)
        name = raw.split("==")[0].strip().lower().replace("_", "-")
        if not name or name in seen:
            continue
        try:
            html = index_page(name)
            picked = pick_wheel(html, name)
            if not picked:
                print(f"  !! {name}: 没有与 {sys.version.split()[0]} 匹配的 wheel, 跳过")
                failed.append(name)
                continue
            fname, rel = picked
            url = resolve_url(name, rel)
            print(f"  -> {fname}")
            data = fetch(url)
            path = os.path.join(target, fname)
            with open(path, "wb") as fh:
                fh.write(data)
            seen[name] = fname
            deps = requires_from_wheel(path)
            with zipfile.ZipFile(path) as zf:
                zf.extractall(target)
            ok += 1
            for d in deps:
                dn = d.split("==")[0].strip().lower().replace("_", "-")
                if dn and dn not in seen and dn not in queue:
                    queue.append(d)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! {name}: {exc}")
            failed.append(name)

    print(f"\n完成: {ok} 个包解包到 {target}")
    if failed:
        print("失败: " + ", ".join(failed))
    print('运行前: $env:PYTHONPATH="' + target + '"  (Linux/macOS: export PYTHONPATH=...)')
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
