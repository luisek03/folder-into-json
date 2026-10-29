#!/usr/bin/env python3
"""
eco-gc-retention — Generationen-Retention ohne echten GC.

Löscht nur Generationen-Links nach festen Regeln. Kein nix-collect-garbage.
Store-Pfade bleiben erhalten (bis zum nächsten Collect-Lauf).

Synchronisiert danach die Boot-Einträge:
  - Entfernt verwaiste .conf-Dateien in /boot/loader/entries/
  - Löscht die LoaderEntries-EFI-Variable (systemd-boot-Cache)

Lock:
  Wenn nicht als Post-Update-Hook von eco-update aufgerufen (erkannt
  an ECO_UPDATE_HOLDING_LOCK=1), wird derselbe Lock wie eco-update
  erworben. So kann eco-gc-retention nicht parallel zu eco-update oder
  einem anderen eco-gc-retention laufen.

Architektur:

  Jede Regel ist eine freie Funktion mit einheitlicher Signatur:

      rule_<name>(generations, current_set, now, <regel-argument>) -> set[int]

    - generations:  Liste der Generationen (dict mit id, timestamp,
                    store_path, current), nach ID sortiert.
    - current_set:  Set der IDs, die aktuell laufen.
    - now:          Einheitlicher Referenzzeitpunkt. Wird einmal in
                    pick_retention_candidates() bestimmt und an alle
                    Regeln durchgereicht. Verhindert Grenzfall-Bugs,
                    wenn das Skript exakt um Mitternacht läuft.
    - Rückgabe:     Set von IDs, die diese Regel behalten möchte.

  Alle Regeln laufen auf der Original-Liste und werden gemergt.
  Kein Dedupe — NixOS handhabt identische Store-Pfade bereits
  effizient beim Rebuild, und der Bootloader zeigt jede Generation
  als eigenen Eintrag, auch wenn der Zustand identisch ist.

Regeln:

  rule_current — Regel 0 (Pflicht)
    Aktive Generationen + höchste Generation.

  rule_safety — Regel 1 (relativ, 24h)
    Alle Generationen der letzten SAFETY_HOURS Stunden.

  rule_keep_day — Regel 2 (kalendarisch)
    Pro Kalendertag die neueste Generation. Tiebreaker (timestamp, id).

  rule_older_anchor — Regel 3 (kalendarisch, erster Fallback)
    Neueste Generation jenseits des Keep-Day-Fensters.

  rule_floor — Regel 4 (zweiter Fallback)
    Mindestens min_generations. Warnt, wenn nicht genug verfügbar.
"""

import argparse
import fcntl
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


PROFILE = "/nix/var/nix/profiles/system"
CURRENT_SYSTEM = "/run/current-system"
BOOTED_SYSTEM = "/run/booted-system"
BOOT_ENTRIES_DIR = "/boot/loader/entries"
LOADER_ENTRIES_EFIVAR = (
    "/sys/firmware/efi/efivars/"
    "LoaderEntries-4a67b082-0a4c-41cf-b6c7-440b29bb8c4f"
)
BOOT_ENTRY_PATTERN = re.compile(r"^nixos-generation-(\d+)(?:-[^.]*)?\.conf$")

LOCKFILE = "/run/lock/eco-update.lock"
HOOK_ENV_VAR = "ECO_UPDATE_HOLDING_LOCK"

SAFETY_HOURS = 24


# ----------------------------------------------------------------------
# Lock
# ----------------------------------------------------------------------

def acquire_lock():
    if os.environ.get(HOOK_ENV_VAR) == "1":
        return None
    try:
        Path("/run/lock").mkdir(exist_ok=True)
        fd = open(LOCKFILE, "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        print("❌ eco-update oder ein anderer eco-gc-retention-Lauf aktiv.")
        print("   Abbruch, um Konflikte zu vermeiden.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Lock konnte nicht erworben werden: {e}")
        print("   Abbruch, um Race-Conditions zu vermeiden.")
        sys.exit(1)


def release_lock(fd):
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
        except Exception:
            pass


# ----------------------------------------------------------------------
# Profile lesen
# ----------------------------------------------------------------------

def _generation_from_link(link):
    """Extrahiert die Generation aus einem Profil-Symlink."""
    try:
        target = os.readlink(link)
    except OSError:
        return None
    m = re.search(r"system-(\d+)-link$", target)
    return int(m.group(1)) if m else None


def get_current_set(generations):
    """Ermittelt das Set der aktuell laufenden Generationen.

    system-Profil: direkt aus dem Symlink-Ziel.
    /run/current-system und /run/booted-system: ihr Ziel ist ein
    Store-Pfad, kein Profil-Link. Matching gegen die store_paths
    der Generationen.
    """
    ids = set()

    # Aus dem system-Profil
    gen_id = _generation_from_link(PROFILE)
    if gen_id is not None:
        ids.add(gen_id)

    # Aus /run/current-system und /run/booted-system
    for link in (CURRENT_SYSTEM, BOOTED_SYSTEM):
        try:
            target = os.readlink(link)
        except OSError:
            continue
        for g in generations:
            if g["store_path"] == target:
                ids.add(g["id"])
                break

    return ids


def get_generations():
    try:
        out = subprocess.check_output(
            ["nix-env", "-p", PROFILE, "--list-generations"],
            text=True,
        )
    except FileNotFoundError:
        print("❌ 'nix-env' nicht im PATH gefunden.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"❌ Konnte Generationen nicht auflisten: {e}")
        sys.exit(1)

    current_id = _generation_from_link(PROFILE)

    generations = []
    for line in out.splitlines():
        m = re.match(
            r"\s*(\d+)\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", line)
        if not m:
            continue
        gen_id = int(m.group(1))
        ts = datetime.strptime(m.group(2), "%Y-%m-%d %H:%M:%S")
        generations.append({
            "id": gen_id,
            "timestamp": ts,
            "store_path": None,
            "current": (gen_id == current_id),
        })

    for gen in generations:
        link = f"{PROFILE}-{gen['id']}-link"
        try:
            gen["store_path"] = subprocess.check_output(
                ["readlink", "-f", link], text=True
            ).strip()
        except subprocess.CalledProcessError:
            gen["store_path"] = f"unknown-{gen['id']}"

    return sorted(generations, key=lambda g: g["id"])


# ----------------------------------------------------------------------
# Regeln — einheitliche Signatur:
#   rule_<name>(generations, current_set, now, <regel-argument>) -> set[int]
# ----------------------------------------------------------------------

def rule_current(generations, current_set, now):
    """Regel 0 (Pflicht): Aktive Generationen + höchste Generation.

    Die höchste Generation ist die neueste, die je erzeugt wurde. Sie
    muss bleiben, auch wenn die aktive Generation nach einem Rollback
    älter ist. Beide werden unabhängig voneinander geschützt.

    `now` wird nicht verwendet, ist aber Teil der einheitlichen
    Regel-Signatur.
    """
    valid_ids = {g["id"] for g in generations}
    keep = {i for i in current_set if i in valid_ids}
    if generations:
        keep.add(generations[-1]["id"])
    return keep


def rule_safety(generations, current_set, now, hours):
    """Regel 1 (relativ): Alle Generationen der letzten `hours` Stunden.

    `hours = 0` deaktiviert die Regel (keine Generation wird
    allein durch die Safety-Regel behalten).

    Bewusst NICHT kalendarisch. Schützt späte Abend-Builds davor,
    nach Mitternacht aus dem Keep-Day-Fenster zu fallen.
    """
    if hours <= 0:
        return set()
    cutoff = now - timedelta(hours=hours)
    return {g["id"] for g in generations if g["timestamp"] >= cutoff}


def rule_max(generations, input_set, now, max_count):
    """Filter: Behalte höchstens `max_count` Generationen aus `input_set`.

    Wählt die neuesten nach (timestamp, id). Anders als die
    Generator-Regeln erzeugt rule_max kein Set aus `generations`,
    sondern reduziert das übergebene `input_set`.

    Die Signatur ist identisch zu allen anderen Regeln — der
    Unterschied liegt nur darin, wie `input_set` verwendet wird:
    als Quelle (Generator) oder als Filter (Filter).

    max_count <= 0 → deaktiviert (gibt input_set unverändert zurück)
    """
    if max_count <= 0 or len(input_set) <= max_count:
        return set(input_set)

    sorted_gens = sorted(
        (g for g in generations if g["id"] in input_set),
        key=lambda g: (g["timestamp"], g["id"]),
        reverse=True,
    )
    return {g["id"] for g in sorted_gens[:max_count]}


def rule_keep_day(generations, current_set, now, keep_days):
    """Regel 2 (kalendarisch): Pro Kalendertag die neueste Generation.

    Abgedeckt: heute + (keep_days - 1) Tage zurück.

    Auswahl nach (timestamp, id) — Tiebreaker ist wichtig, weil nix-env
    Timestamps nur sekundengenau liefert. Zwei Builds in derselben
    Sekunde haben denselben Timestamp; die höhere ID ist dann die
    tatsächlich neuere Generation.
    """
    by_day = defaultdict(list)
    for g in generations:
        by_day[g["timestamp"].date()].append(g)

    today = now.date()
    keep = set()
    for i in range(keep_days):
        day = today - timedelta(days=i)
        if day in by_day:
            newest = max(by_day[day],
                         key=lambda g: (g["timestamp"], g["id"]))
            keep.add(newest["id"])
    return keep


def rule_older_anchor(generations, current_set, now, keep_days):
    """Regel 3 (kalendarisch, erster Fallback): Anker jenseits Keep-Day.

    Die neueste Generation, deren Kalendertag älter ist als der
    älteste durch rule_keep_day abgedeckte Tag. Bildet den Anker für
    Generationen, die älter sind als das Keep-Day-Fenster.

    Kalendarischer Vergleich, nicht 24h-Fenster — Verhalten ist
    unabhängig von der Uhrzeit des Aufrufs.
    """
    oldest_covered = now.date() - timedelta(days=keep_days - 1)
    older = [g for g in generations
             if g["timestamp"].date() < oldest_covered]
    if not older:
        return set()
    newest_older = max(older, key=lambda g: (g["timestamp"], g["id"]))
    return {newest_older["id"]}


def rule_floor(generations, current_set, now, marked, min_generations):
    """Regel 4 (zweiter Fallback): Mindestens `min_generations`.

    Ergänzt bei Bedarf die neuesten Generationen. Arbeitet auf der
    Original-Liste — doppelte Store-Pfade zählen mit, weil der
    Bootloader jede Generation als eigenen Eintrag zeigt.

    Warnt (nicht kritisch), wenn weniger als min_generations verfügbar
    sind (frisch aufgesetztes System, nach regulärem GC, längere
    Nichtnutzung, zu wenige Generationen überhaupt).
    """
    keep = set(marked)
    if len(keep) >= min_generations:
        return keep

    for gen in sorted(generations, key=lambda g: g["timestamp"],
                      reverse=True):
        if len(keep) >= min_generations:
            break
        keep.add(gen["id"])

    if len(keep) < min_generations:
        print(f"⚠️  Warnung: Nur {len(keep)} Generation(en) verfügbar, "
              f"aber min_generations = {min_generations}.")
        print(f"   Mögliche Ursachen: frisch aufgesetztes System, "
              f"kürzlich gelaufener GC, oder längere Nichtnutzung.")
        print(f"   Dies ist keine Fehlermeldung — das Skript läuft "
              f"mit den verfügbaren Generationen weiter.")

    return keep


# ----------------------------------------------------------------------
# Dispatcher
# ----------------------------------------------------------------------

# =============================================================================
# ZUKUNFTSIDEE (Phase 3): Pipeline-as-Data
# =============================================================================
#
# Aktuell ist die Policy (welche Regeln, in welcher Reihenfolge, mit welchen
# Parametern) hier im Python-Code hart verdrahtet. Das reicht für den
# aktuellen Stand und ist leicht zu lesen.
#
# Später soll der Dispatcher durch eine "Compositor-Methode" ersetzt werden,
# die eine Pipeline-Beschreibung aus der NixOS-Konfiguration entgegennimmt.
# Die Python-Seite bleibt dann ein stabiler Executor, die Policy lebt in Nix
# und ist per Git versioniert.
#
# Skizze:
#
#   In modules/system/ops/common.nix:
#
#       mySystem.ops.gc.retention.pipeline = {
#         parallel = [
#           { rule = "current"; }
#           {
#             chain = [
#               { rule = "safety"; params.hours = 24; }
#               { rule = "max";    params.count = 20; }
#             ];
#           }
#           { rule = "keepDay";     params.days = 7; }
#           { rule = "olderAnchor"; params.days = 7; }
#         ];
#         final = [
#           { rule = "floor"; params.minGenerations = 4; }
#         ];
#       };
#
#   In gc.nix wird die Pipeline als JSON an das Skript übergeben:
#
#       --pipeline /nix/store/...-eco-gc-pipeline.json
#
#   Hier im Skript bleibt nur noch:
#
#       RULES = {
#           "current":     rule_current,
#           "safety":      rule_safety,
#           "keepDay":     rule_keep_day,
#           "olderAnchor": rule_older_anchor,
#           "max":         rule_max,
#           "floor":       rule_floor,
#       }
#
#       def execute_pipeline(pipeline, generations, current_set, now):
#           marked = set()
#           for entry in pipeline.get("parallel", []):
#               if "chain" in entry:
#                   result = current_set
#                   for step in entry["chain"]:
#                       result = RULES[step["rule"]](
#                           generations, result, now,
#                           **step.get("params", {}))
#                   marked |= result
#               else:
#                   marked |= RULES[entry["rule"]](
#                       generations, current_set, now,
#                       **entry.get("params", {}))
#           for entry in pipeline.get("final", []):
#               marked = RULES[entry["rule"]](
#                   generations, marked, now,
#                   **entry.get("params", {}))
#           return marked
#
# Voraussetzung für die Umstellung:
#   - rule_floor muss die uniforme Signatur bekommen:
#       (generations, input_set, now, min_generations)
#     statt (generations, current_set, now, marked, min_generations).
#   - Alle Regeln sind bereits uniform: (generations, input_set, now, **params).
#   - `now` wird bereits einmal in pick_retention_candidates() bestimmt und
#     durchgereicht — das bleibt im Executor genauso.
#
# Gewinn:
#   - Policy-Änderungen sind Nix-Commits, kein Python-Editieren.
#   - Pipeline ist Daten und kann gegen synthetische Generationen getestet
#     werden, bevor sie auf echten Daten läuft.
#   - Neue Regeln: in RULES registrieren, schon in der Config nutzbar.
#
# Preis:
#   - Mini-DSL (parallel, chain, final, rule, params), die dokumentiert
#     werden muss.
#   - Fehler in der Pipeline (Tippfehler im Regelnamen, falscher Parameter)
#     fliegen erst beim Lauf, nicht bei der Nix-Evaluation.
#   - Typsicherheit in Nix ist begrenzt (enum für rule-Namen, aber keine
#     Prüfung, ob params.count zu rule=max passt).
#
# Nicht jetzt umsetzen. Erst wenn mehrere Policies ausprobiert werden sollen
# oder wenn jemand anderes die Retention anpassen soll, ohne Python zu lesen.
# Die Architektur trägt die Umstellung ohne Umbau der Regeln.
# =============================================================================

def pick_retention_candidates(generations, current_set,
                               keep_days, min_generations,
                               safety_hours, max_safety_generations,
                               now=None):
    """Führt alle Regeln in der richtigen Reihenfolge aus.

    Regel 0 (current) und Regeln 2–4 (kalendarisch) sind parallel:
    ihre Sets werden gemergt. Regel 1 (safety) wird mit einem Filter
    (rule_max) verkettet, um die Anzahl zu begrenzen.

    `now` wird hier einmal bestimmt und an alle Regeln durchgereicht.
    """
    now = now if now is not None else datetime.now()

    marked = set()

    # Regel 0: aktuell + höchste (parallel, ungefiltert)
    marked |= rule_current(generations, current_set, now)

    # Regel 1: Safety (Generator) → Regel 1b: Cap (Filter), seriell
    safety = rule_safety(generations, current_set, now, safety_hours)
    safety = rule_max(generations, safety, now, max_safety_generations)
    marked |= safety

    # Regeln 2–3: kalendarisch (parallel, ungefiltert)
    marked |= rule_keep_day(generations, current_set, now, keep_days)
    marked |= rule_older_anchor(generations, current_set, now, keep_days)

    # Regel 4: Floor (parallel, letzter Fallback)
    marked = rule_floor(generations, current_set, now, marked, min_generations)
    return marked


# ----------------------------------------------------------------------
# Löschen
# ----------------------------------------------------------------------

def delete_generations(to_delete):
    if not to_delete:
        print("✅ Nichts zu löschen.")
        return
    ids = sorted(to_delete)
    print(f"🗑️  Lösche {len(ids)} Generation(en): "
          f"{', '.join(map(str, ids))}")
    r = subprocess.run(
        ["nix-env", "-p", PROFILE, "--delete-generations",
         *map(str, ids)],
        check=False,
    )
    if r.returncode != 0:
        print(f"⚠️  nix-env --delete-generations rc={r.returncode}. "
              f"Manche Generationen wurden möglicherweise nicht gelöscht.")


def cleanup_boot_entries(remaining_ids):
    entries_dir = Path(BOOT_ENTRIES_DIR)
    if not entries_dir.is_dir():
        print(f"ℹ️  {BOOT_ENTRIES_DIR} nicht gefunden — "
              f"überspringe Boot-Cleanup.")
        return 0

    removed = 0
    for entry in entries_dir.iterdir():
        if not entry.is_file():
            continue
        m = BOOT_ENTRY_PATTERN.match(entry.name)
        if not m:
            continue
        gen_id = int(m.group(1))
        if gen_id not in remaining_ids:
            try:
                entry.unlink()
                print(f"🗑️  Boot-Eintrag entfernt: {entry.name}")
                removed += 1
            except Exception as e:
                print(f"⚠️  {entry.name} konnte nicht gelöscht werden: {e}")

    if removed:
        print(f"🗑️  {removed} verwaiste Boot-Einträge entfernt.")
    else:
        print("✅ Keine verwaisten Boot-Einträge.")
    return removed


def invalidate_loader_entries_efivar():
    """Löscht die LoaderEntries-EFI-Variable (systemd-boot-Cache).

    efivarfs unterstützt keinen Seek und kein Truncate. Deshalb
    os.open() mit O_WRONLY statt Python's open(), das intern einen
    Seek auf Position 0 macht und mit "File or stream is not
    seekable" fehlschlägt.
    """
    var = Path(LOADER_ENTRIES_EFIVAR)
    if not var.exists():
        return

    subprocess.run(["chattr", "-i", str(var)],
                   check=False,
                   stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)

    try:
        fd = os.open(str(var), os.O_WRONLY)
        try:
            os.write(fd, b"\x00\x00\x00\x00")
        finally:
            os.close(fd)
        print("🗑️  LoaderEntries-EFI-Variable invalidiert.")
        return
    except OSError as e:
        if e.errno == 22:
            print("ℹ️  LoaderEntries-EFI-Variable kann auf dieser "
                  "Firmware nicht invalidiert werden.")
            print("    bootctl zeigt ggf. veraltete Einträge bis zum "
                  "nächsten Boot. Kein funktionaler Fehler.")
            return
        print(f"⚠️  EFI-Variable konnte nicht invalidiert werden: {e}")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generation retention.")
    parser.add_argument("--keep-days", type=int, default=7)
    parser.add_argument("--min-generations", type=int, default=4)
    parser.add_argument("--safety-hours", type=int, default=24,
                        help="Generationen der letzten N Stunden immer "
                             "behalten. 0 deaktiviert die Regel.")
    parser.add_argument("--max-safety-generations", type=int, default=20,
                        help="Obergrenze für Generationen aus dem "
                             "Safety-Fenster. 0 deaktiviert den Cap.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-boot-cleanup", action="store_true",
                        help="Boot-Einträge und EFI-Variable nicht anfassen.")
    args = parser.parse_args()

    lock_fd = acquire_lock()
    try:
        generations = get_generations()
        current_set = get_current_set(generations)
        print(f"📊 {len(generations)} Generation(en) gefunden.")
        print(f"🎯 Aktive Generation(en): "
              f"{', '.join(map(str, sorted(current_set))) or '(keine)'}")

        keep = pick_retention_candidates(
            generations, current_set,
            args.keep_days, args.min_generations,
            args.safety_hours, args.max_safety_generations)
        print(f"🔄 Nach Regeln: {len(keep)} behalten.")

        all_ids = {g["id"] for g in generations}
        to_delete = all_ids - keep

        try:
            raw = subprocess.check_output(
                ["nix-env", "-p", PROFILE, "--list-generations"],
                text=True,
            )
            keep_set = set(keep)
            print("✅ Behalten:")
            for line in raw.splitlines():
                m = re.match(r"\s*(\d+)\s", line)
                if m and int(m.group(1)) in keep_set:
                    print(f"   {line}")
        except subprocess.CalledProcessError:
            print(f"✅ Behalte: {', '.join(map(str, sorted(keep)))}")

        if to_delete:
            print("🗑️  Löschen:")
            for line in raw.splitlines():
                m = re.match(r"\s*(\d+)\s", line)
                if m and int(m.group(1)) in to_delete:
                    print(f"   {line}")
        else:
            print("🗑️  Löschen: (nichts)")

        if args.dry_run:
            if not args.skip_boot_cleanup:
                entries_dir = Path(BOOT_ENTRIES_DIR)
                if entries_dir.is_dir():
                    would_remove = [
                        e.name for e in entries_dir.iterdir()
                        if e.is_file()
                        and (m := BOOT_ENTRY_PATTERN.match(e.name))
                        and int(m.group(1)) not in keep
                    ]
                    if would_remove:
                        print(f"🗑️  Boot-Cleanup würde {len(would_remove)} "
                              f"Einträge entfernen.")
                    else:
                        print("✅ Boot-Cleanup: nichts zu tun.")

                if Path(LOADER_ENTRIES_EFIVAR).exists() and to_delete:
                    print("🗑️  LoaderEntries-EFI-Variable würde invalidiert.")

            print("🧪 Dry-run — nichts wird gelöscht.")
            return

        delete_generations(to_delete)

        if args.skip_boot_cleanup:
            return

        if to_delete:
            remaining = get_generations()
            remaining_ids = {g["id"] for g in remaining}
            cleanup_boot_entries(remaining_ids)
            invalidate_loader_entries_efivar()
    finally:
        release_lock(lock_fd)


if __name__ == "__main__":
    main()
