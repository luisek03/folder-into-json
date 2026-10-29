# Workflow

Die täglichen Befehle und der typische Arbeitsablauf.

---

## Kurzreferenz

| Befehl | Zweck | sudo? |
|--------|-------|-------|
| `eco` | Ins Repo wechseln | nein |
| `eco-edit` | Repo in Kate öffnen | nein |
| `eco-status` | `git status` | nein |
| `eco-commit` | `git add . && git commit` | nein |
| `eco-push` | `git push` | nein |
| `eco-pull` | `git pull --rebase` (nur wenn sauber) | nein |
| `eco-log` | `git log --oneline --graph --all` | nein |
| `deploy-dry` | rsync + Dry-Run | ja |
| `deploy` | rsync + Switch | ja |
| `deploy-copy` | nur rsync | ja |
| `eco-update` | flake update + switch + Backup | ja |
| `eco-gc-retention` | Nur Generationen aufräumen | ja |
| `eco-gc-collect` | Store aufräumen bei Platzmangel | ja |

---

## Typischer Tagesablauf

### Änderung an der Konfiguration

1. **Bearbeiten:**

       eco-edit

2. **Committen:**

       eco-commit

3. **Deployen:**

       deploy-dry    # zur Kontrolle
       deploy        # scharf

Der `deploy`-Befehl:

1. rsync vom Repo nach `/etc/nixos` (mit Excludes)
2. `nixos-rebuild switch --flake /etc/nixos`
3. Neue Generation aktiv

**Kein Reboot nötig**, außer bei Kernel- oder Bootloader-Änderungen.

### System-Update

    sudo eco-update

Ablauf:

1. `nix flake update` — alle Inputs aktualisieren
2. Cache-Check für Kernel — wenn nicht im Cache, Lock-Rollback
3. `nix build` — System bauen
4. `nixos-rebuild switch` — scharf schalten
5. flake.lock → `hosts/<host>/flake.lock` + Commit
6. Post-Update-Hook (standardmäßig `eco-gc-retention`)
7. `nix store optimise`

**Kein Reboot nötig**, außer bei Kernel-Änderung.

### Nach dem Update

Wenn die Änderung im Repo sichtbar sein soll:

    eco-push

Damit wird die neue `hosts/<host>/flake.lock` auf GitHub gesichert.

### Strukturelle Änderungen: `boot` statt `switch`

Bei Änderungen, die viele Services, User oder Boot-relevante Listen
betreffen (Profil-Umbau, `boot.initrd.*`, `users.users.*`), statt
`deploy` besser:

    deploy-copy
    sudo nixos-rebuild boot --flake /etc/nixos
    sudo reboot

Das baut die neue Generation und trägt sie in den Bootloader ein,
**ohne** Services neuzustarten. Beim nächsten Boot startet alles
frisch — kein D-Bus-Race, kein polkit-Problem.

**Faustregel:**
- Kleine Config-Änderungen (Aliase, Pakete, Desktop-Einstellungen)
  → `deploy` (switch)
- Alles, was Boot, User, initrd oder Dienste-Struktur betrifft
  → `deploy-copy` + `nixos-rebuild boot` + Reboot

---

## Kernel-Update

Ein Kernel-Update passiert **automatisch** mit `eco-update`, wenn der
neue Kernel im konfigurierten Cache liegt.

**Wenn der Cache nicht liefert:**

- `eco-update` erkennt das, rollt die Lock zurück auf die alte
  Kernel-Revision
- nixpkgs wird trotzdem aktualisiert
- Nächster `eco-update`-Lauf versucht es erneut

**Wenn du den Kernel trotzdem updaten willst:**

    sudo eco-update --ignore-cache-check

Das lädt die neue Kernel-Revision, auch wenn kein Cache sie hat. Der
Laptop baut dann lokal (1–2 Stunden).

**Nach einem Kernel-Update ist Reboot Pflicht.**

---

## Store-Aufräumen

### Nur Retention (Generationen-Links)

Läuft automatisch nach jedem `eco-update`.

Manuell:

    sudo eco-gc-retention --dry-run    # Vorschau
    sudo eco-gc-retention              # scharf

Löscht **keine** Store-Pfade — nur Profil-Symlinks. Die Pakete bleiben
im Store verfügbar (für Rollback, nix-shell).

### Store-GC (echtes Aufräumen)

Läuft nur, wenn:

- `/` über 85 % Auslastung ist (Default), **oder**
- manuell getriggert

Manuell:

    sudo eco-gc-collect                  # prüft Auslastung, tut ggf. nichts
    sudo eco-gc-collect --start-percent 0 --target-percent 0    # forciert

**Warnung:** Läuft `nix-collect-garbage`. Alle unbenutzten Store-Pfade
werden gelöscht — inklusive nix-shell-Cache.

---

## Rollback

### Vor einem Reboot

Wenn der Build sauber durchläuft, aber die Änderung problematisch ist:

    sudo nixos-rebuild switch --rollback

Wechselt zur vorherigen Generation. Schnell, sicher.

### Nach einem Reboot

Im systemd-boot-Menü:

- Pfeiltasten zum gewünschten Eintrag
- Enter

Die Generation muss noch existieren (Retention könnte sie gelöscht
haben).

### Lock-Rollback

Wenn ein Update ein Paket kaputt gemacht hat:

    cd ~/Projekte/Eco-System
    git log --oneline Eco-System/hosts/laptop/flake.lock
    git checkout <alter-commit> -- Eco-System/hosts/laptop/flake.lock

    sudo cp Eco-System/hosts/laptop/flake.lock /etc/nixos/flake.lock
    sudo nixos-rebuild switch --flake /etc/nixos

---

## Notfall

Bei schweren Problemen siehe [`OPERATIONS.md`](OPERATIONS.md).

Bei Bootversagen: Alter Generation auswählen. Wenn das nicht hilft:
Rescue-Mode (geplant, siehe [`RESCUE-CONCEPT.md`](RESCUE-CONCEPT.md)).
Letztes Mittel: Live-USB + Neuinstallation.

---

Ende des Workflows.
