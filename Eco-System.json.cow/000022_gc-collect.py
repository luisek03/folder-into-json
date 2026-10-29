#!/usr/bin/env python3
"""
eco-gc-collect — Nix-Store aufräumen bei Platzmangel.

Löscht keine Generationen. Nur `nix-collect-garbage` (ohne -d).
Iteriert bis Speicher <= target_percent oder max_iterations erreicht.

Exit-Codes:
  0 — Ziel erreicht, oder Auslastung war bereits unter start-percent
  1 — Echter Fehler (GC rc≠0, df-Fehler, unexpected output)
  2 — Validierungsfehler (start-percent < target-percent)
  3 — Ziel nach max-iterations nicht erreicht (kein Fehler)
"""

import argparse
import subprocess
import sys


# Exit-Codes als Konstanten für Lesbarkeit.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_VALIDATION = 2
EXIT_TARGET_NOT_REACHED = 3


def get_usage_percent(path):
    """
    Liefert die Auslastung in Prozent — selbst berechnet aus Rohbytes.
    Vermeidet die Rundungs-Diskrepanz von df -P.

    Formel: round(used * 100 / (used + available))
    Das entspricht der df-Konvention und ignoriert Reserven.
    """
    try:
        out = subprocess.check_output(
            ["df", "-B1", "--output=used,avail", path],
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ df auf {path} fehlgeschlagen: {e}")
        sys.exit(EXIT_ERROR)
    except FileNotFoundError:
        print("❌ 'df' nicht im PATH gefunden.")
        sys.exit(EXIT_ERROR)

    lines = out.strip().splitlines()
    if len(lines) < 2:
        print("❌ df-Ausgabe unerwartet.")
        sys.exit(EXIT_ERROR)

    fields = lines[1].split()
    try:
        used = int(fields[0])
        avail = int(fields[1])
    except (IndexError, ValueError):
        print(f"❌ df-Ausgabe nicht lesbar: {fields}")
        sys.exit(EXIT_ERROR)

    total = used + avail
    if total == 0:
        return 0
    return round(used * 100 / total)


def run_gc():
    """
    Führt nix-collect-garbage aus.
    Rückgabe: Returncode (0 = OK).
    """
    print("🧹 nix-collect-garbage ...")
    try:
        r = subprocess.run(["nix-collect-garbage"], check=False)
    except FileNotFoundError:
        print("❌ 'nix-collect-garbage' nicht im PATH gefunden.")
        return 1
    if r.returncode != 0:
        print(f"⚠️  nix-collect-garbage rc={r.returncode}")
    return r.returncode


def main():
    parser = argparse.ArgumentParser(description="eco-gc-collect")
    parser.add_argument("--start-percent", type=int, default=85)
    parser.add_argument("--target-percent", type=int, default=80)
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument("--path", default="/nix/store",
                        help="Pfad, dessen Partition geprüft wird. "
                             "Default /nix/store — dort wirkt der GC.")
    args = parser.parse_args()

    # Validierung: start >= target, sonst ist die Zielsetzung widersprüchlich
    if args.start_percent < args.target_percent:
        print(f"❌ --start-percent ({args.start_percent}) "
              f"< --target-percent ({args.target_percent}).")
        print("   Start muss >= Target sein, sonst ist die Zielsetzung "
              "widersprüchlich.")
        sys.exit(EXIT_VALIDATION)

    current = get_usage_percent(args.path)
    print(f"📊 Auslastung {args.path}: {current}% "
          f"(start: {args.start_percent}%, target: {args.target_percent}%)")

    if current < args.start_percent:
        print("✅ Auslastung unter Schwellwert — nichts zu tun.")
        sys.exit(EXIT_OK)

    any_failure = False
    last_rc = 0
    for i in range(1, args.max_iterations + 1):
        print(f"\n🔄 Iteration {i}/{args.max_iterations}")
        try:
            last_rc = run_gc()
            if last_rc != 0:
                any_failure = True
        except KeyboardInterrupt:
            print("\n⚠️  GC durch Benutzer abgebrochen.")
            current = get_usage_percent(args.path)
            print(f"📊 Auslastung jetzt: {current}%")
            # Benutzerabbruch ist kein Fehler und kein Zielerreichen.
            # Wir nehmen 3, damit es von "Ziel erreicht" unterscheidbar ist.
            sys.exit(EXIT_TARGET_NOT_REACHED)

        current = get_usage_percent(args.path)
        print(f"📊 Auslastung jetzt: {current}%")

        if current <= args.target_percent:
            print("✅ Ziel erreicht.")
            sys.exit(EXIT_OK)

    # Loop beendet ohne Zielerreichung
    if any_failure:
        print(f"❌ GC mindestens einmal fehlgeschlagen "
              f"(letzter rc={last_rc}). Manuell prüfen:")
        print(f"   - journalctl -xe")
        print(f"   - Laufende nix-Prozesse: pgrep -a nix")
        print(f"   - Store-DB: ls -la /nix/var/nix/db/")
        sys.exit(EXIT_ERROR)

    print(f"⚠️  Ziel nicht erreicht nach {args.max_iterations} Iterationen. "
          f"Auslastung: {current}%. "
          f"Möglicherweise ist der Platz durch andere Daten belegt.")
    sys.exit(EXIT_TARGET_NOT_REACHED)


if __name__ == "__main__":
    main()
