#!/usr/bin/env python3
"""
folder_json.py — Ordner als einzelne JSON-Datei (Alternative zu .tar).

Jede Datei wird als Eintrag gespeichert:
  {"path": "sub/file.nix", "type": "text",   "content": "...", "mode": 420}
  {"path": "logo.png",     "type": "binary", "content": "iVBOR...",
                                              "encoding": "base64", "mode": 420}
  {"path": "link",         "type": "symlink", "target": "../foo"}

- Text wird UTF-8 im Klartext gespeichert (gut lesbar/diffbar).
- Binärdaten werden Base64-kodiert.
- Dateimodus (Ausführbar-Bits) bleibt erhalten.
- Exclude-Patterns im rsync-Stil (Basename/fnmatch auf jede Pfadkomponente).

Aufruf:
  pack:    python folder_json.py pack ./Eco-System Eco-System.json
  unpack:  python folder_json.py unpack Eco-System.json ./restored
  dry:     python folder_json.py pack ./Eco-System Eco-System.json -v
"""

import argparse
import base64
import fnmatch
import json
import os
import sys
from pathlib import Path


DEFAULT_EXCLUDES = [
    # Host-spezifisch — /etc/nixos darf diese NICHT überschreiben
    "host-config.nix",
    "hardware-configuration.nix",

    # flake.lock: /etc/nixos ist die "lebende" Instanz
    "flake.lock",

    # Git & Build-Artefakte
    ".git",
    ".gitignore",
    "result",
    "result-*",
    "*.drv",

    # DOCS
    "docs",
    "README.md",

    # Editor-Kram
    "*.swp",
    "*.kate-swp",
    "*~",
    ".DS_Store",
    ".directory",
]


def matches_exclude(rel_path: Path, excludes) -> bool:
    """rsync-ähnliche Prüfung: Pattern matcht gegen den vollen relativen
    Pfad UND gegen jede einzelne Pfadkomponente."""
    rel_str = rel_path.as_posix()
    parts = rel_path.parts
    for pat in excludes:
        if fnmatch.fnmatch(rel_str, pat):
            return True
        for part in parts:
            if fnmatch.fnmatch(part, pat):
                return True
    return False


def pack(src, out_json, excludes, verbose=False):
    src = Path(src).resolve()
    if not src.is_dir():
        sys.exit(f"Kein Ordner: {src}")

    files = []
    excluded = []

    for root, dirs, fnames in os.walk(src):
        root_p = Path(root)
        rel_root = root_p.relative_to(src)

        # Verzeichnisse prunen, damit os.walk nicht hineinläuft
        keep = []
        for d in dirs:
            rel_d = rel_root / d
            if matches_exclude(rel_d, excludes):
                excluded.append(rel_d.as_posix() + "/")
            else:
                keep.append(d)
        dirs[:] = keep

        for f in fnames:
            rel = rel_root / f
            full = root_p / f

            if matches_exclude(rel, excludes):
                excluded.append(rel.as_posix())
                continue

            if os.path.islink(full):
                files.append({
                    "path": rel.as_posix(),
                    "type": "symlink",
                    "target": os.readlink(full),
                })
                continue

            st = full.lstat()
            data = full.read_bytes()
            entry = {
                "path": rel.as_posix(),
                "mode": st.st_mode & 0o777,
            }
            try:
                entry["type"] = "text"
                entry["content"] = data.decode("utf-8")
            except UnicodeDecodeError:
                entry["type"] = "binary"
                entry["encoding"] = "base64"
                entry["content"] = base64.b64encode(data).decode("ascii")
            files.append(entry)

    # Deterministische Reihenfolge → reproduzierbare JSON-Datei
    files.sort(key=lambda e: e["path"])

    doc = {
        "format": "folder-json",
        "version": 1,
        "source": src.name,
        "excludes": excludes,
        "file_count": len(files),
        "files": files,
    }
    Path(out_json).write_text(
        json.dumps(doc, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return files, excluded


def unpack(in_json, dst, verbose=False):
    doc = json.loads(Path(in_json).read_text(encoding="utf-8"))
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)

    for entry in doc.get("files", []):
        target = dst / entry["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        t = entry["type"]

        if t == "symlink":
            if target.exists() or target.is_symlink():
                target.unlink()
            os.symlink(entry["target"], target)
            if verbose:
                print(f"  L {entry['path']} -> {entry['target']}")
            continue

        if t == "binary":
            data = base64.b64decode(entry["content"])
        else:
            data = entry["content"].encode("utf-8")

        target.write_bytes(data)
        if "mode" in entry:
            os.chmod(target, entry["mode"])

        if verbose:
            print(f"  F {entry['path']}")


def main():
    p = argparse.ArgumentParser(description="Ordner als JSON packen/entpacken.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("pack", help="Ordner → JSON")
    pp.add_argument("src", help="Quellordner")
    pp.add_argument("out", help="Ziel-JSON-Datei")
    pp.add_argument("--exclude", action="append", default=[],
                    help="Zusätzliches Exclude-Pattern (mehrfach möglich)")
    pp.add_argument("--no-default-excludes", action="store_true",
                    help="Die eingebaute Nix-Exclude-Liste deaktivieren")
    pp.add_argument("-v", "--verbose", action="store_true")

    up = sub.add_parser("unpack", help="JSON → Ordner")
    up.add_argument("in_json", help="Quell-JSON-Datei")
    up.add_argument("dst", help="Zielordner")
    up.add_argument("-v", "--verbose", action="store_true")

    args = p.parse_args()

    if args.cmd == "pack":
        excludes = [] if args.no_default_excludes else list(DEFAULT_EXCLUDES)
        excludes += args.exclude
        files, excluded = pack(args.src, args.out, excludes, args.verbose)
        print(f"Gepackt: {len(files)} Dateien → {args.out}")
        if excluded:
            print(f"Ausgeschlossen: {len(excluded)} Einträge")
            if args.verbose:
                for e in excluded:
                    print(f"  - {e}")
    else:
        unpack(args.in_json, args.dst, args.verbose)
        print(f"Entpackt nach: {args.dst}")


if __name__ == "__main__":
    main()
