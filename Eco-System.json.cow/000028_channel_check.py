#!/usr/bin/env python3
"""Asynchroner Check: Läuft der aktuelle stabile NixOS-Kanal noch?

Startet einen Hintergrund-Thread, der die Prometheus-API von NixOS
abfragt. Das Future wird erst vor dem Post-Hook ausgewertet — bis
dahin sind flake update / build / switch längst durch, also kein
zusätzlicher Zeitverlust.
"""

import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

from colors import Color


FLAKE_NIX     = "/etc/nixos/flake.nix"
PROMETHEUS_URL = "https://prometheus.nixos.org/api/v1/query?query=channel_revision"
CHANNEL_RE    = re.compile(r'nixpkgs\.url\s*=\s*"github:NixOS/nixpkgs/(nixos-\d{2}\.\d{2})"')
STABLE_RE     = re.compile(r"^nixos-\d{2}\.\d{2}$")
TIMEOUT_SECONDS = 15

_executor = None


def _read_current_channel():
    try:
        content = Path(FLAKE_NIX).read_text()
    except OSError:
        return None
    m = CHANNEL_RE.search(content)
    return m.group(1) if m else None


def _fetch_latest_stable():
    req = urllib.request.Request(
        PROMETHEUS_URL,
        headers={"User-Agent": "eco-update/1.0"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        data = json.loads(resp.read().decode())
    channels = [
        r["metric"]["channel"]
        for r in data["data"]["result"]
        if "channel" in r["metric"]
    ]
    stable = sorted(c for c in channels if STABLE_RE.match(c))
    if not stable:
        raise RuntimeError("Keine stabilen Kanaele in der API-Antwort.")
    return stable[-1]


def _check():
    current = _read_current_channel()
    if current is None:
        return ("error", "Konnte aktuellen Kanal nicht aus flake.nix lesen.")
    try:
        latest = _fetch_latest_stable()
    except Exception as e:
        return ("error", f"API-Check fehlgeschlagen: {e}")
    return ("ok", current, latest)


def start_channel_check():
    """Startet den Check im Hintergrund. Rueckgabe: Future."""
    global _executor
    _executor = ThreadPoolExecutor(max_workers=1)
    return _executor.submit(_check)


def _shutdown_executor():
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)


def evaluate_channel_check(future):
    """Wertet das Future aus und gibt die farbliche Meldung aus."""
    c = Color(no_color=not sys.stdout.isatty())
    try:
        try:
            result = future.result(timeout=TIMEOUT_SECONDS)
        except FutureTimeout:
            print(c.yellow(
                "⚠️  Kanal-Check: Timeout — konnte nicht abgeschlossen werden."
            ))
            return
        except Exception as e:
            print(c.red(f"❌ Kanal-Check fehlgeschlagen: {e}"))
            return

        if result[0] == "error":
            print(c.red(f"❌ Kanal-Check: {result[1]}"))
            return

        _, current, latest = result
        if current == latest:
            print(c.green(f"✅ Stabiler Kanal aktuell: {current}"))
        else:
            print(c.yellow(
                f"⚠️  Kanal-Update verfuegbar: {current} → {latest}\n"
                f"   In flake.nix anpassen:\n"
                f"   nixpkgs.url = \"github:NixOS/nixpkgs/{latest}\";"
            ))
    finally:
        _shutdown_executor()
