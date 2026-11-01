#!/usr/bin/env python3
"""Check the environment and say what is missing.

Usage:
    python3 doctor.py

Prints one line per check: the Python version (3.10+), the Chrome / Chromium / Edge
used for PNG export, the font cache in ~/.cache/prettier-excalidraw/fonts,
PRETTIER_EXCALIDRAW_ICONS and PRETTIER_EXCALIDRAW_STYLE when they are set, and
quick-look on macOS. Each problem gets a one-line hint.

Exit code 0 = build, lint and SVG export will work; 1 = something they need is
missing (old Python, or an icons/style variable that points at nothing). A missing
Chrome or an empty font cache only warns: PNG export and the real fonts are optional.
Run this first when another script fails. Standard library only.
"""
import glob, json, os, platform, shutil, sys

OK, WARN, FAIL = "ok", "warn", "FAIL"


def check_python():
    v = sys.version_info
    found = f"Python {v[0]}.{v[1]}.{v[2]}"
    if v < (3, 10):
        return FAIL, found, "the scripts need Python 3.10 or newer; run them with a newer python3"
    return OK, found, ""


def check_chrome(find_chrome):
    path = find_chrome()
    if path:
        return OK, f"Chrome/Chromium/Edge: {path}", ""
    return WARN, "Chrome/Chromium/Edge: not found", \
        "PNG export needs one (or quick-look on macOS); install Chrome or Chromium, or export to .svg"


def check_fonts(cache, families):
    missing = [name for name, folder in families.items()
               if not glob.glob(os.path.join(cache, folder, "*.woff2"))]
    if not missing:
        return OK, f"font cache: {cache}", ""
    return WARN, f"font cache: no {' / '.join(missing)} in {cache}", \
        "export.py fetches them on its first run with network access; offline it uses a system font"


def check_icons():
    env = os.environ.get("PRETTIER_EXCALIDRAW_ICONS")
    if not env:
        return OK, "PRETTIER_EXCALIDRAW_ICONS: not set", ""
    dirs = [d for d in env.split(os.pathsep) if d]
    bad = [d for d in dirs if not os.path.isdir(d)]
    if not dirs or bad:
        return FAIL, f"PRETTIER_EXCALIDRAW_ICONS: not a folder: {', '.join(bad) or repr(env)}", \
            f"point it at existing icon folders (separated by {os.pathsep!r}) or unset it"
    return OK, f"PRETTIER_EXCALIDRAW_ICONS: {env}", ""


def check_style():
    path = os.environ.get("PRETTIER_EXCALIDRAW_STYLE")
    if not path:
        return OK, "PRETTIER_EXCALIDRAW_STYLE: not set", ""
    if not os.path.isfile(path):
        return FAIL, f"PRETTIER_EXCALIDRAW_STYLE: no such file: {path}", \
            "point it at a style.json written by profile.py, or unset it"
    try:
        with open(path, encoding="utf-8") as f:
            json.load(f)
    except (OSError, ValueError) as ex:
        return FAIL, f"PRETTIER_EXCALIDRAW_STYLE: cannot read {path} ({ex.__class__.__name__})", \
            "the file must be JSON; regenerate it with profile.py"
    return OK, f"PRETTIER_EXCALIDRAW_STYLE: {path}", ""


def check_quicklook():
    if platform.system() != "Darwin":
        return None
    if shutil.which("qlmanage") and shutil.which("sips"):
        return OK, "quick-look: qlmanage and sips found", ""
    return WARN, "quick-look: qlmanage or sips not found", "PNG export without Chrome needs both (they ship with macOS)"


def checks():
    out = [check_python()]
    if out[0][0] == FAIL:  # the other scripts may not even import on this Python
        return out
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import export
    out += [check_chrome(export.find_chrome), check_fonts(export.CACHE, export.FONT_DIRS),
            check_icons(), check_style()]
    ql = check_quicklook()
    if ql:
        out.append(ql)
    return out


def main():
    results = checks()
    for status, found, hint in results:
        print(f"{status:<4}  {found}")
        if hint:
            print(f"      -> {hint}")
    failed = [r for r in results if r[0] == FAIL]
    print("missing something needed for build, lint or SVG export" if failed else "ready")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
