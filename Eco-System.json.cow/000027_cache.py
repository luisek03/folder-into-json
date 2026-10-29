#!/usr/bin/env python3
"""
Cache-Prüfung für eco-update: Store-Pfad-Eval, Verify, Pin-Check.
"""

import os
import subprocess
from pathlib import Path

from manifest import (
    CachePinError,
    load_file,
    merge,
    parse_line,
    resolve_expr,
)


FLAKE = "/etc/nixos"
HOST_CONFIG = "/etc/nixos/host-config.nix"

KERNEL_EXPR = (
    "nixosConfigurations.default.config."
    "boot.kernelPackages.kernel.outPath"
)


# ----------------------------------------------------------------------
# Store-Pfad-Auflösung
# ----------------------------------------------------------------------

def eval_store_path(expr):
    """Evaluiert einen Nix-Ausdruck relativ zur Flake zu einem Store-Pfad."""
    try:
        out = subprocess.check_output(
            ["nix", "eval", "--raw", f"{FLAKE}#{expr}"],
            stderr=subprocess.PIPE, text=True, timeout=300,
        )
        return out.strip()
    except subprocess.CalledProcessError as e:
        err = (e.stderr or "").strip()
        print(f"⚠️  Evaluation von '{expr}' fehlgeschlagen (rc={e.returncode}).")
        if err:
            lines = err.splitlines()
            for line in (lines[-20:] if len(lines) > 20 else lines):
                print(f"    {line}")
        return None
    except subprocess.TimeoutExpired:
        print(f"⚠️  Evaluation von '{expr}': Timeout nach 300 s.")
        return None
    except FileNotFoundError:
        print("⚠️  'nix' nicht im PATH gefunden.")
        return None


def cache_has_path(store_path, urls):
    """Prüft, ob der Pfad in einem der Caches mit gültiger Signatur liegt."""
    if not store_path or not store_path.startswith("/nix/store/"):
        return False
    for url in urls:
        try:
            r = subprocess.run(
                ["nix", "store", "verify",
                 "--store", url, "--sigs-needed", "1", store_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=30,
            )
            if r.returncode == 0:
                return True
        except Exception:
            continue
    return False


# ----------------------------------------------------------------------
# Manifest-Laden aus festen Pfaden
# ----------------------------------------------------------------------

def _read_host():
    import re
    try:
        m = re.search(r'\bhost\s*=\s*"([^"]+)"',
                      Path(HOST_CONFIG).read_text())
        return m.group(1) if m else None
    except FileNotFoundError:
        return None


def collect_pins(user_pins):
    """
    Sammelt alle Pins.
    Reihenfolge: Kernel → default → host → user_pins.
    Kernel ist fix und kann nicht überschrieben werden.

    user_pins: Liste von Strings (Manifest-Zeilen oder Include-Pfade).
    Rückgabe: dict[name] = {"expr": ..., "params": {...}}
    """

    pins = {}
    seen = set()

    # Kernel — fix
    pins["kernel"] = {
        "expr": KERNEL_EXPR,
        "params": {"pin-on-cache": "true"},
    }

    entry_lists = []

    # Host-Manifest
    host = _read_host()
    if host:
        host_path = Path(FLAKE) / "hosts" / host / "cache-manifest" / "init.chp"
        if host_path.is_file():
            entries = load_file(host_path, seen)
            entry_lists.append(entries)
            print(f"📄 Host-Manifest: {host_path} ({len(entries)} Einträge)")

    # User-Pins
    if user_pins:
        entries = []
        for i, arg in enumerate(user_pins):
            kind, payload = parse_line(arg, source=f"--cache-pin[{i}]")
            if kind == "empty":
                continue
            if kind == "include":
                p = Path(payload)
                if not p.is_absolute():
                    p = Path.cwd() / p
                entries.extend(load_file(p, seen))
            elif kind == "package":
                entries.append(payload)
        entry_lists.append(entries)
        print(f"📄 --cache-pin: {len(entries)} Einträge")

    manifests = merge(entry_lists)
    for name, params in manifests.items():
        if name == "kernel":
            print("⚠️  Manifest-Eintrag 'kernel' ignoriert.")
            continue
        pins[name] = {
            "expr": resolve_expr(name),
            "params": params,
        }

    return pins


def check_all_pins(user_pins, urls):
    """
    Prüft alle Pins mit pin-on-cache=true.
    Rückgabe: True wenn alle im Cache, sonst False.
    """
    pins = collect_pins(user_pins)
    total = len(pins)
    all_ok = True
    checked = 0
    skipped = 0

    for name, info in pins.items():
        params = info["params"]
        if params.get("pin-on-cache", "true") != "true":
            print(f"⏭️  {name}: pin-on-cache=false — ignoriert.")
            skipped += 1
            continue

        expr = info["expr"]
        if expr.startswith("/nix/store/"):
            path = expr
        else:
            path = eval_store_path(expr)

        if not path:
            print(f"❌ {name}: Store-Pfad nicht ermittelbar.")
            all_ok = False
            continue

        checked += 1
        if cache_has_path(path, urls):
            print(f"✅ {name} im Cache.")
        else:
            print(f"❌ {name} nicht im Cache.")
            all_ok = False

    print(f"\n📊 {total} Pins gesamt, {checked} geprüft, "
          f"{skipped} übersprungen.")
    return all_ok
