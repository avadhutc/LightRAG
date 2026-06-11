"""
Apply patches to venv site-packages required for process_document.py.

Run once after `uv sync --extra api && uv pip install docling`:
    .venv\\Scripts\\python.exe patch_packages.py

Patches applied
---------------
1. raganything/modalprocessors.py — two bugs in raganything 1.3.x:
   - asdict(lightrag) misses runtime-computed role_llm_funcs key
     → use lightrag._build_global_config() instead
   - processor fallback returns 2-tuple but caller unpacks 3 values
     → return (content, entity, [])

2. huggingface_hub/file_download.py — Windows only:
   - os.symlink() raises WinError 1314 without Developer Mode
     → fall back to shutil.copy2 on winerror == 1314
"""

import sys
import importlib.util
from pathlib import Path


def find_package_file(package: str, relative: str) -> Path:
    spec = importlib.util.find_spec(package)
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError(f"Package '{package}' not found — run `uv pip install {package}` first")
    pkg_root = Path(spec.submodule_search_locations[0])
    target = pkg_root / relative
    if not target.exists():
        raise FileNotFoundError(f"Expected file not found: {target}")
    return target


def patch_raganything(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    changed = False

    old1 = "self.global_config = asdict(lightrag)"
    new1 = "self.global_config = lightrag._build_global_config()"
    if old1 in text:
        text = text.replace(old1, new1)
        changed = True
        print("  [+] asdict(lightrag) → _build_global_config()")
    elif new1 in text:
        print("  [=] already patched: _build_global_config()")
    else:
        print("  [!] WARNING: asdict(lightrag) not found — check file manually")

    old2 = "return str(modal_content), fallback_entity"
    new2 = "return str(modal_content), fallback_entity, []"
    count = text.count(old2)
    if count:
        text = text.replace(old2, new2)
        changed = True
        print(f"  [+] {count} fallback return(s): 2-tuple → 3-tuple")
    elif new2 in text:
        print("  [=] already patched: 3-tuple fallback returns")
    else:
        print("  [!] WARNING: 2-tuple fallback returns not found — check file manually")

    if changed:
        path.write_text(text, encoding="utf-8")


def patch_huggingface_hub(path: Path) -> None:
    if sys.platform != "win32":
        print("  [skip] not Windows — WinError 1314 patch not needed")
        return

    text = path.read_text(encoding="utf-8")

    if "winerror == 1314" in text:
        print("  [=] already patched: WinError 1314 symlink fallback")
        return

    old = "            os.symlink(src_rel_or_abs, abs_dst)\n            return"
    new = (
        "            try:\n"
        "                os.symlink(src_rel_or_abs, abs_dst)\n"
        "                return\n"
        "            except OSError as _symlink_err:\n"
        "                if getattr(_symlink_err, 'winerror', None) == 1314:\n"
        "                    import shutil as _shutil\n"
        "                    _shutil.copy2(abs_src, abs_dst)\n"
        "                    return\n"
        "                raise"
    )

    if old not in text:
        print("  [!] WARNING: symlink target not found — huggingface_hub structure may have changed")
        return

    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    print("  [+] WinError 1314 symlink → shutil.copy2 fallback")


def main():
    print(f"Python: {sys.executable}\n")

    print("Patching raganything/modalprocessors.py ...")
    try:
        p = find_package_file("raganything", "modalprocessors.py")
        print(f"  {p}")
        patch_raganything(p)
    except Exception as e:
        print(f"  [ERROR] {e}")

    print("\nPatching huggingface_hub/file_download.py ...")
    try:
        p = find_package_file("huggingface_hub", "file_download.py")
        print(f"  {p}")
        patch_huggingface_hub(p)
    except Exception as e:
        print(f"  [ERROR] {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
