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

RAM-Verhalten:
  Beim Packen wird der Datei-Inhalt chunkweise (1 MiB) gelesen und direkt
  JSON-escaped in die Zieldatei geschrieben. Peak-RAM pro Datei bleibt
  konstant, unabhängig von der Dateigröße (auch bei 200-MB-Textdateien).

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


TEXT_SAMPLE = 8192                    # Bytes für Text/Binär-Erkennung
TEXT_CHUNK   = 1024 * 1024            # 1 MiB Zeichen pro Lesevorgang
B64_CHUNK    = 3 * 1024 * 1024        # Vielfaches von 3 → kein Padding-Drift


DEFAULT_EXCLUDES = [
    # flake.lock: /etc/nixos ist die "lebende" Instanz
    "flake.lock",

    # Git & Build-Artefakte
    ".git",
    ".gitignore",
    "result",
    "result-*",
    "*.drv",

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


def _looks_like_text(sample: bytes) -> bool:
    """Heuristik: Null-Bytes → binär. Sonst UTF-8-Probe. Toleriert ein
    Sample-Ende mitten in einem Multi-Byte-Zeichen (trim 1–3 Bytes)."""
    if not sample:
        return True
    if b"\x00" in sample:
        return False
    for trim in range(0, 4):
        try:
            sample[:len(sample) - trim].decode("utf-8")
            return True
        except UnicodeDecodeError:
            continue
    return False


def _stream_text_into_json(f_out, full_path: Path):
    """Schreibt den Dateiinhalt als JSON-String (inkl. Quotes) chunkweise.
    - newline="" erhält \\r\\n exakt wie im Original
    - Textmodus + utf-8 → Python puffert unvollständige UTF-8-Sequenzen,
      daher keine Zeichen-Boundary-Probleme beim Chunking
    - json.dumps ist kontextfrei pro Zeichen → Escaping je Chunk ergibt
      dasselbe Resultat wie Escaping des ganzen Strings
    """
    f_out.write('"')
    with open(full_path, "r", encoding="utf-8", errors="strict", newline="") as fs:
        while True:
            chunk = fs.read(TEXT_CHUNK)
            if not chunk:
                break
            esc = json.dumps(chunk, ensure_ascii=False)
            f_out.write(esc[1:-1])
    f_out.write('"')


def _stream_binary_into_json(f_out, full_path: Path):
    """Schreibt Base64 der Datei als JSON-String (inkl. Quotes) chunkweise."""
    f_out.write('"')
    with open(full_path, "rb") as fs:
        while True:
            chunk = fs.read(B64_CHUNK)
            if not chunk:
                break
            f_out.write(base64.b64encode(chunk).decode("ascii"))
    f_out.write('"')


def pack(src, out_json, excludes, verbose=False):
    src = Path(src).resolve()
    out_json = Path(out_json).resolve()
    if not src.is_dir():
        sys.exit(f"Kein Ordner: {src}")

    # -------- Phase 1: Katalog aufbauen --------
    # Nur Pfade + Metadaten, KEIN Datei-Inhalt im RAM.
    entries = []
    excluded = []

    for root, dirs, fnames in os.walk(src):
        root_p = Path(root)
        rel_root = root_p.relative_to(src)

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
                entries.append({
                    "rel": rel.as_posix(),
                    "full": full,
                    "type": "symlink",
                    "target": os.readlink(full),
                })
                continue

            st = full.lstat()
            try:
                with open(full, "rb") as fs:
                    sample = fs.read(TEXT_SAMPLE)
                is_text = _looks_like_text(sample)
            except OSError as e:
                print(f"WARN: '{rel}' nicht lesbar ({e}), als binär.",
                      file=sys.stderr)
                is_text = False

            entries.append({
                "rel": rel.as_posix(),
                "full": full,
                "type": "text" if is_text else "binary",
                "mode": st.st_mode & 0o777,
            })

    # Gleiche Sortierung wie im Original: nach Pfad-String.
    entries.sort(key=lambda e: e["rel"])

    # -------- Phase 2: JSON streamen --------
    # In eine .tmp schreiben und erst am Ende atomar umbenennen, damit
    # ein Abbruch während des Streamings keine halbe JSON-Datei hinterlässt.
    tmp_json = out_json.with_name(out_json.name + ".tmp")

    try:
        with open(tmp_json, "w", encoding="utf-8", newline="\n") as f:
            # --- Kopf (identisch zu json.dumps(..., indent=2)) ---
            f.write("{\n")
            f.write('  "format": "folder-json",\n')
            f.write('  "version": 1,\n')
            f.write(f'  "source": {json.dumps(src.name, ensure_ascii=False)},\n')

            f.write('  "excludes": [\n')
            for i, pat in enumerate(excludes):
                comma = "," if i < len(excludes) - 1 else ""
                f.write(f'    {json.dumps(pat, ensure_ascii=False)}{comma}\n')
            f.write('  ],\n')

            f.write(f'  "file_count": {len(entries)},\n')
            f.write('  "files": [\n')

            # --- Einträge ---
            for i, e in enumerate(entries):
                if i > 0:
                    f.write(",\n")

                rel_json = json.dumps(e["rel"], ensure_ascii=False)
                t = e["type"]

                if t == "symlink":
                    target_json = json.dumps(e["target"], ensure_ascii=False)
                    f.write('    {\n')
                    f.write(f'      "path": {rel_json},\n')
                    f.write('      "type": "symlink",\n')
                    f.write(f'      "target": {target_json}\n')
                    f.write('    }')
                    if verbose:
                        print(f"  L {e['rel']} -> {e['target']}")
                    continue

                if t == "binary":
                    f.write('    {\n')
                    f.write(f'      "path": {rel_json},\n')
                    f.write(f'      "mode": {e["mode"]},\n')
                    f.write('      "type": "binary",\n')
                    f.write('      "encoding": "base64",\n')
                    f.write('      "content": ')
                    try:
                        _stream_binary_into_json(f, e["full"])
                    except OSError as ex:
                        raise RuntimeError(
                            f"Fehler beim Lesen von '{e['rel']}': {ex}"
                        )
                    f.write('\n    }')
                    if verbose:
                        print(f"  B {e['rel']}")
                    continue

                # text
                f.write('    {\n')
                f.write(f'      "path": {rel_json},\n')
                f.write(f'      "mode": {e["mode"]},\n')
                f.write('      "type": "text",\n')
                f.write('      "content": ')
                try:
                    _stream_text_into_json(f, e["full"])
                except UnicodeDecodeError:
                    raise RuntimeError(
                        f"'{e['rel']}' enthält ungültiges UTF-8 außerhalb "
                        f"der ersten {TEXT_SAMPLE} Bytes. Bitte ausschließen "
                        f"oder als binär behandeln."
                    )
                except OSError as ex:
                    raise RuntimeError(
                        f"Fehler beim Lesen von '{e['rel']}': {ex}"
                    )
                f.write('\n    }')
                if verbose:
                    print(f"  F {e['rel']}")

            # --- Fuß ---
            f.write("\n  ]\n")
            f.write("}\n")

        os.replace(tmp_json, out_json)
    except Exception:
        if tmp_json.exists():
            tmp_json.unlink()
        raise

    return entries, excluded


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
            # newline="" damit \r\n aus dem JSON 1:1 zurückgeschrieben wird
            with open(target, "w", encoding="utf-8", newline="") as f:
                f.write(entry["content"])
            if "mode" in entry:
                os.chmod(target, entry["mode"])
            if verbose:
                print(f"  F {entry['path']}")
            continue

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
