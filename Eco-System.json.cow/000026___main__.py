#!/usr/bin/env python3
"""
eco-update — NixOS-Update in separaten, retry-fähigen Schritten.

Ablauf:
  1. flake update (Verhalten je nach Flag)
  2. nixos-rebuild build
  3. nixos-rebuild switch
  4. flake.lock → repo/hosts/<host>/flake.lock (+ optional git commit)
  5. post-update Hook (optional)
  6. nix store optimise

Flags:
  (kein Flag)         Nur nixpkgs wird aktualisiert.
  --update-all        Alle Inputs + Cache-Check + Rollback.
  --update-force      Alle Inputs, Cache-Check ignoriert.
  --skip-optimise     optimise überspringen.
  --cache-pin <spec>  Manifest-Zeile oder Datei (mehrfach).
  --without-monitor   Klassische Nix-Ausgabe statt nom-Baum-Ansicht.

Laufzeit-Overrides für spezielle Situationen:
  --cores N           Kerne pro Build.
  --jobs N            Maximale parallele Builds.
  --show-trace        Vollen Nix-Stacktrace bei Fehlern anzeigen.
  --add-cache URL     Zusätzlicher Cache (mehrfach).
  --add-key KEY       Zusätzlicher Trusted-Key (mehrfach).
"""

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from cache import check_all_pins
from lock import acquire_lock, release_lock
from manifest import CachePinError
from channel_check import start_channel_check, evaluate_channel_check


FLAKE = "/etc/nixos"
HOST_CONFIG = "/etc/nixos/host-config.nix"
BUILD_RESULT = "/run/eco-update-result"


class EcoUpdate:
    def __init__(self):
        p = argparse.ArgumentParser(description="eco-update")
        p.add_argument("--user", required=True)
        p.add_argument("--retries", type=int, default=0)
        p.add_argument("--delay", type=int, default=10)
        p.add_argument("--unsafe", action="store_true")
        p.add_argument("--cache-check", default="1")
        p.add_argument("--cache-urls", default="")
        p.add_argument("--cache-pin", action="append", default=[],
                       help="Cache-Manifest-Zeile oder Datei (mehrfach)")
        p.add_argument("--backup", default="0")
        p.add_argument("--backup-repo", default="")
        p.add_argument("--backup-commit", default="0")
        p.add_argument("--backup-msg",
                       default="eco-update: flake.lock für %HOST% (%DATE%)")
        p.add_argument("--git-author-name", default="eco-update")
        p.add_argument("--git-author-email", default="eco-update@localhost")
        p.add_argument("--hook", default="0")
        p.add_argument("--hook-script", default="")
        p.add_argument("--skip-optimise", action="store_true",
                       help="Überspringt den 'nix store optimise'-Schritt.")
        p.add_argument("--update-all", action="store_true",
                       help="Alle Inputs aktualisieren + Cache-Check + "
                            "Rollback bei Cache-Miss.")
        p.add_argument("--update-force", action="store_true",
                       help="Alle Inputs aktualisieren, Cache-Check "
                            "ignoriert. Nicht gecachte Pakete werden "
                            "lokal gebaut.")

        # Laufzeit-Overrides für spezielle Situationen
        p.add_argument("--cores", type=int, default=None,
                       help="Kerne pro Build. 0 = alle Kerne. "
                            "Nützlich bei OOM oder Systemlast.")
        p.add_argument("--jobs", type=int, default=None,
                       help="Maximale parallele Builds.")
        p.add_argument("--show-trace", action="store_true",
                       help="Nix-Stacktrace bei Evaluierungsfehlern.")
        p.add_argument("--add-cache", action="append", default=[],
                       metavar="URL",
                       help="Zusätzlicher Cache für diesen Lauf. "
                            "Mehrfach möglich.")
        p.add_argument("--add-key", action="append", default=[],
                       metavar="KEY",
                       help="Zusätzlicher Trusted-Key für diesen Lauf. "
                            "Mehrfach möglich.")
        p.add_argument("--without-monitor", action="store_true",
                       help="Klassische Nix-Ausgabe statt nom-Baum-Ansicht.")
        self.args = p.parse_args()
        self.lock_fd = None

    # ------------------------------------------------------------------
    def _sep(self, title):
        print(f"\n{'='*60}\n🔄 {title}\n{'='*60}\n")

    def _run(self, cmd, **kw):
        return subprocess.run(cmd, **kw)

    def _with_retries(self, name, fn):
        attempt = 0
        while True:
            attempt += 1
            if self.args.retries > 0 and attempt > self.args.retries:
                print(f"❌ {name}: max. Retries ({self.args.retries}) erreicht.")
                return False
            total = self.args.retries if self.args.retries > 0 else "∞"
            self._sep(f"{name} — Versuch {attempt}/{total}")
            if fn():
                return True
            if self.args.retries == 0 or attempt < self.args.retries:
                print(f"⏳ Nächster Versuch in {self.args.delay}s ...")
                time.sleep(self.args.delay)

    def _read_host(self):
        try:
            m = re.search(r'\bhost\s*=\s*"([^"]+)"',
                          Path(HOST_CONFIG).read_text())
            return m.group(1) if m else None
        except FileNotFoundError:
            return None

    # ------------------------------------------------------------------
    # Schritt 1: flake update
    # ------------------------------------------------------------------
    def _do_flake_update(self):
        lock = Path(f"{FLAKE}/flake.lock")
        backup = Path(f"{FLAKE}/flake.lock.pre-cache-check")

        # ----------------------------------------------------------
        # --update-force: alles, Cache egal
        # ----------------------------------------------------------
        if self.args.update_force:
            backup.write_bytes(lock.read_bytes())
            print("⏭️  Cache-Check ignoriert (--update-force).")
            print("   Alle Inputs werden aktualisiert, notfalls lokal gebaut.")
            print("🔄 nix flake update ...")
            if self._run(["nix", "flake", "update",
                          "--flake", FLAKE]).returncode != 0:
                print("❌ flake update fehlgeschlagen.")
                lock.write_bytes(backup.read_bytes())
                backup.unlink(missing_ok=True)
                return False
            backup.unlink(missing_ok=True)
            return True

        # ----------------------------------------------------------
        # Default: nur nixpkgs. Kein Cache-Check nötig.
        # ----------------------------------------------------------
        if not self.args.update_all:
            print("ℹ️  Default: nur nixpkgs wird aktualisiert.")
            print("   Andere Inputs bleiben auf ihrer gepinnten Revision.")
            print("🔄 nix flake update nixpkgs ...")
            if self._run(["nix", "flake", "update", "nixpkgs",
                          "--flake", FLAKE]).returncode != 0:
                print("❌ flake update fehlgeschlagen.")
                return False
            return True

        # ----------------------------------------------------------
        # --update-all: alles + Cache-Check + Rollback
        # ----------------------------------------------------------
        backup.write_bytes(lock.read_bytes())
        print("🔄 nix flake update (alle Inputs) ...")
        if self._run(["nix", "flake", "update",
                      "--flake", FLAKE]).returncode != 0:
            print("❌ flake update fehlgeschlagen.")
            lock.write_bytes(backup.read_bytes())
            backup.unlink(missing_ok=True)
            return False

        if self.args.cache_check != "1":
            print("ℹ️  Cache-Check deaktiviert (cache-check=0).")
            backup.unlink(missing_ok=True)
            return True

        urls = [u.strip() for u in self.args.cache_urls.split(",") if u.strip()]
        if not urls:
            print("ℹ️  Keine Cache-URLs konfiguriert — überspringe Cache-Check.")
            backup.unlink(missing_ok=True)
            return True

        print("🔄 Cache-Check für Kernel und gepinnte Pakete ...")
        try:
            all_ok = check_all_pins(self.args.cache_pin, urls)
        except CachePinError as e:
            print(f"\n❌ Manifest-Fehler: {e}")
            print("   Lock wird zurückgerollt. Bitte Manifest korrigieren.")
            lock.write_bytes(backup.read_bytes())
            backup.unlink(missing_ok=True)
            return False

        if all_ok:
            print("\n✅ Alle Pins im Cache. Neue Lock behalten.")
            backup.unlink(missing_ok=True)
            return True

        print("\n❌ Nicht alle Pins im Cache. Rolle Lock zurück, "
              "update nur nixpkgs.")
        lock.write_bytes(backup.read_bytes())
        backup.unlink(missing_ok=True)
        r = self._run(["nix", "flake", "update", "nixpkgs", "--flake", FLAKE])
        return r.returncode == 0

    # ------------------------------------------------------------------
    def _common_options(self):
        """
        Baut die Liste der Laufzeit-Override-Flags für nix und
        nixos-rebuild aus den CLI-Argumenten.
        """
        opts = []
        if self.args.cores is not None:
            opts += ["--cores", str(self.args.cores)]
        if self.args.jobs is not None:
            opts += ["--max-jobs", str(self.args.jobs)]
        if self.args.show_trace:
            opts += ["--show-trace"]
        if self.args.add_cache:
            opts += ["--option", "extra-substituters",
                     " ".join(self.args.add_cache)]
        if self.args.add_key:
            opts += ["--option", "extra-trusted-public-keys",
                     " ".join(self.args.add_key)]
        return opts

    # ------------------------------------------------------------------
    def _do_build(self):
        # nom ist Default — außer explizit deaktiviert.
        use_nom = not self.args.without_monitor
        builder = "nom" if use_nom else "nix"
        cmd = [
            builder, "build",
            f"{FLAKE}#nixosConfigurations.default.config.system.build.toplevel",
            "--out-link", BUILD_RESULT,
            "--print-out-paths",
        ] + self._common_options()
        return self._run(cmd).returncode == 0

    def _do_switch(self):
        cmd_parts = [
            "nixos-rebuild", "switch",
            "--flake", FLAKE,
        ] + self._common_options()

        if self.args.without_monitor:
            return self._run(cmd_parts).returncode == 0

        # Mit nom: Pipe durch bash, exit code via pipefail propagieren.
        import shlex
        cmd_str = " ".join(shlex.quote(c) for c in cmd_parts)
        wrapped = f"set -o pipefail; {cmd_str} 2>&1 | nom"
        return self._run(["bash", "-c", wrapped]).returncode == 0

    def _do_cleanup_outlink(self):
        """Entfernt den --out-link nach erfolgreichem Switch.

        Der aktuelle Systemzustand ist über /run/current-system
        referenziert. Der Build-Out-Link war nur für den Build-Schritt
        nötig und ist danach ein unnötiger GC-Root in
        /nix/var/nix/gcroots/auto/.
        """
        outlink = Path(BUILD_RESULT)
        if outlink.is_symlink():
            try:
                outlink.unlink()
                print(f"🗑️  Out-Link entfernt: {BUILD_RESULT}")
            except Exception as e:
                print(f"⚠️  Out-Link konnte nicht entfernt werden: {e}")

    def _do_backup(self):
        if self.args.backup != "1":
            return
        self._sep("FLAKE.LOCK-BACKUP")
        host = self._read_host()
        if not host:
            print("⚠️  host-config.nix nicht gelesen.")
            return

        repo = Path(self.args.backup_repo)
        os_root = repo / "Eco-System"
        dst = os_root / "hosts" / host / "flake.lock"
        if not dst.parent.is_dir():
            print(f"⚠️  Zielordner {dst.parent} existiert nicht.")
            return

        self._run(["cp", f"{FLAKE}/flake.lock", str(dst)])
        self._run(["chown", f"{self.args.user}:users", str(dst)])
        print(f"✅ Kopiert nach {dst}")

        if self.args.backup_commit != "1":
            return
        if not (repo / ".git").is_dir():
            print(f"⚠️  {repo}/.git nicht gefunden. Überspringe commit.")
            return

        msg = (self.args.backup_msg
               .replace("%HOST%", host)
               .replace("%DATE%", time.strftime("%Y-%m-%d %H:%M")))

        rel_path = f"Eco-System/hosts/{host}/flake.lock"
        self._run(["git", "-C", str(repo), "add", rel_path])
        r = self._run([
            "git", "-C", str(repo),
            "-c", f"user.name={self.args.git_author_name}",
            "-c", f"user.email={self.args.git_author_email}",
            "commit", "-m", msg,
        ])
        self._run(["chown", "-R", f"{self.args.user}:users", str(repo / ".git")])

        if r.returncode == 0:
            print(f"✅ Commit: {msg}")
            print("ℹ️  Push manuell mit: eco-push")
        else:
            print("⚠️  Nichts zu committen oder Commit fehlgeschlagen.")

    def _do_hook(self):
        if self.args.hook != "1" or not self.args.hook_script.strip():
            return
        self._sep("POST-UPDATE HOOK")
        print(f"$ {self.args.hook_script}")
        env = os.environ.copy()
        env["ECO_UPDATE_HOLDING_LOCK"] = "1"
        subprocess.run(["bash", "-c", self.args.hook_script],
                       env=env, check=False)

    def _do_optimise(self):
        if self.args.skip_optimise:
            print("\n⏭️  nix store optimise übersprungen (--skip-optimise).")
            return
        self._sep("NIX STORE OPTIMISE")
        print("ℹ️  Ctrl+C überspringt die Optimierung.\n")
        try:
            self._run(["nix", "store", "optimise"])
        except KeyboardInterrupt:
            print("\n⏭️  Optimise abgebrochen.")

    # ------------------------------------------------------------------
    def run(self):
        if os.geteuid() != 0:
            print("❌ eco-update muss als root laufen (sudo eco-update).")
            return 1

        self.lock_fd = acquire_lock()
        if self.lock_fd is None:
            print("❌ eco-update läuft bereits.")
            return 1

        # Future: Channel-Check im Hintergrund starten.
        # Läuft parallel zu flake update / build / switch.
        channel_future = start_channel_check()

        if self.args.unsafe:
            self._sep("UNSAFE — nur switch")
            self._run(["nixos-rebuild", "switch", "--flake", FLAKE])
            evaluate_channel_check(channel_future)
            self._do_optimise()
            release_lock(self.lock_fd)
            return 0

        try:
            if not self._with_retries("flake-update", self._do_flake_update):
                release_lock(self.lock_fd); return 1
            if not self._with_retries("build", self._do_build):
                release_lock(self.lock_fd); return 1
            if not self._with_retries("switch", self._do_switch):
                release_lock(self.lock_fd); return 1

            # ----------------------------------------------------------
            # Out-Link aufräumen
            # ----------------------------------------------------------
            # Der --out-link aus _do_build() (/run/eco-update-result)
            # dient während des Builds und des Switch als GC-Lock, damit
            # ein parallel laufender nix-collect-garbage den frisch
            # gebauten Toplevel nicht wegräumt, bevor er über
            # /run/current-system verankert ist.
            #
            # Nach erfolgreichem Switch ist der Toplevel über
            # /run/current-system abgesichert. Der Out-Link hat seinen
            # Zweck erfüllt und wird still entfernt. Ein dangling
            # gcroots/auto-Eintrag bleibt bis zum nächsten regulären GC
            # und wird dort als stale link entfernt.
            #
            # Bei fehlgeschlagenem Switch oder Ctrl+C wird hier nicht
            # aufgeräumt — der Out-Link bleibt dann für Diagnose
            # (readlink /run/eco-update-result) erhalten.
            # ----------------------------------------------------------
            outlink = Path(BUILD_RESULT)
            if outlink.is_symlink():
                try:
                    outlink.unlink()
                except OSError as e:
                    print(f"⚠️  Out-Link ({BUILD_RESULT}) konnte nicht entfernt werden: {e}")

            # Future: Channel-Check auswerten, bevor Hooks laufen.
            evaluate_channel_check(channel_future)

            self._do_backup()
            self._do_hook()
            self._do_optimise()

            self._sep("✅ FERTIG")
            release_lock(self.lock_fd)
            return 0
        except KeyboardInterrupt:
            self._sep("⚠️  ABGEBROCHEN")
            release_lock(self.lock_fd)
            return 0
        except Exception as e:
            self._sep(f"❌ UNERWARTETER FEHLER: {e}")
            release_lock(self.lock_fd)
            return 1


if __name__ == "__main__":
    sys.exit(EcoUpdate().run())
