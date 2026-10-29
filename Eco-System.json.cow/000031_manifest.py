#!/usr/bin/env python3
"""
Manifest-Parser und Pin-Merge für eco-update.

Format (.chp):
  # Kommentar
  firefox
  chromium:pin-on-cache=true
  thunderbird:{pin-on-cache=true; note="mail"}
  include /pfad/zu/anderer.chp
  nixosConfigurations.default.pkgs.blender.outPath

Regeln:
  - Letzter Eintrag gewinnt (innerhalb Datei und über Ebenen hinweg).
  - include expandiert inline (rekursiv).
  - Dieselbe absolute Datei darf nur einmal vorkommen → Fehler.
"""

import re
from pathlib import Path


PARAM_DEFAULTS = {
    "pin-on-cache": "true",
}


class CachePinError(Exception):
    """Fehler beim Parsen oder Auswerten von Cache-Manifesten."""
    pass


def parse_line(line, source="<arg>"):
    """
    Parst eine Zeile.
    Rückgabe: ("empty", None) | ("include", pfad) | ("package", (name, params))
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return ("empty", None)

    if line == "include" or line.startswith("include "):
        path = line[len("include"):].strip()
        if not path:
            raise CachePinError(f"{source}: 'include' ohne Pfad")
        return ("include", path)

    name = line
    params = {}

    if ":" in line:
        name, _, rest = line.partition(":")
        name = name.strip()
        rest = rest.strip()

        if rest.startswith("{"):
            if not rest.endswith("}"):
                raise CachePinError(
                    f"{source}: Fehlende schließende Klammer: {line}")
            inner = rest[1:-1]
            for pair in inner.split(";"):
                pair = pair.strip()
                if not pair:
                    continue
                if "=" not in pair:
                    raise CachePinError(
                        f"{source}: Ungültiger Parameter '{pair}'")
                k, v = pair.split("=", 1)
                params[k.strip()] = v.strip().strip('"').strip("'")
        else:
            if "=" not in rest:
                raise CachePinError(
                    f"{source}: Ungültiger Parameter '{rest}'")
            k, v = rest.split("=", 1)
            params[k.strip()] = v.strip().strip('"').strip("'")

    if not name:
        raise CachePinError(f"{source}: Leerer Paketname in: {line}")

    for k, v in PARAM_DEFAULTS.items():
        params.setdefault(k, v)

    return ("package", (name, params))


def load_file(path, seen, base_dir=None):
    """
    Lädt eine Manifest-Datei und expandiert Includes inline.
    seen: globales Set absoluter Pfade → zweiter Auftritt ist Fehler.
    """
    p = Path(path)
    if not p.is_absolute():
        p = (Path(base_dir) / p) if base_dir else p
    abs_path = p.resolve()

    if abs_path in seen:
        raise CachePinError(f"Doppelter/zirkulärer Include: {abs_path}")
    seen.add(abs_path)

    if not abs_path.is_file():
        raise CachePinError(f"Manifest nicht gefunden: {abs_path}")

    entries = []
    for lineno, raw in enumerate(abs_path.read_text().splitlines(), 1):
        kind, payload = parse_line(raw, source=f"{abs_path}:{lineno}")
        if kind == "empty":
            continue
        if kind == "include":
            entries.extend(load_file(payload, seen, base_dir=abs_path.parent))
        elif kind == "package":
            entries.append(payload)
    return entries


def merge(entry_lists):
    """Liste von (name, params)-Listen → dict. Letzter gewinnt."""
    result = {}
    for entries in entry_lists:
        for name, params in entries:
            result[name] = params
    return result


def resolve_expr(name):
    """
    Paket-Name → Nix-Ausdruck.
    - /nix/store/... → unverändert
    - enthält "." oder "#" → voller Ausdruck
    - sonst → nixosConfigurations.default.pkgs.<name>.outPath
    """
    name = name.strip()
    if name.startswith("/nix/store/"):
        return name
    if "." in name or "#" in name:
        return name
    return f"nixosConfigurations.default.pkgs.{name}.outPath"
