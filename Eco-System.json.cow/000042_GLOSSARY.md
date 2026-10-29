# Glossar

Begriffe, die im Eco-System und in NixOS häufig vorkommen.

---

## NixOS-Konzepte

### Flake

Eine `flake.nix`-Datei, die Eingaben (`inputs`) und Ausgaben (`outputs`)
eines Nix-Projekts deklariert. Der `flake.lock` pinnt alle Inputs auf
konkrete Revisionen — reproduzierbare Builds.

### Generation

Ein Snapshot des System-Zustands. Jeder `nixos-rebuild switch` erzeugt
eine neue Generation. Alte Generationen bleiben im Bootloader
auswählbar (bis sie gelöscht werden).

### Profil

Die Sammlung aller Generationen. Unter `/nix/var/nix/profiles/system`
liegt ein Symlink auf die aktuelle Generation.

**Achtung:** Nicht zu verwechseln mit „Profile" im Eco-System-Sinn
(siehe unten).

### Store

`/nix/store/` — der zentrale Speicher für alle Pakete. Jedes Paket
liegt unter einem inhaltsbasierten Hash. Mehrere Generationen können
denselben Store-Pfad nutzen.

### Derivation (.drv)

Die Bauanleitung für ein Paket. Wird beim Evaluieren der Konfiguration
erzeugt, dann gebaut (oder aus dem Cache geholt).

### Substituter

Ein Binär-Cache. Nix kann fertige Pakete von dort holen, statt lokal
zu bauen. Konfiguriert in `nix.settings.substituters`.

### GC-Root

Ein Symlink unter `/nix/var/nix/gcroots/`. Alles, was von einem GC-Root
erreichbar ist, wird vom Garbage Collector **nicht** gelöscht.

### Closure

Alle Store-Pfade, die ein Paket braucht (inklusive transitiver
Abhängigkeiten).

### `mkDefault` / `mkForce`

NixOS-Modul-System für Overrides:

- `mkDefault` — Priorität 1000, überschreibbar
- `mkForce` — Priorität 50, überschreibt alles
- Normale Zuweisung — Priorität 100
- `mkOverride N` — beliebige Priorität (kleiner = stärker)

### `--impure`

Ein Nix-Flag, das Zugriff auf nicht-reine Quellen erlaubt (Umgebung,
Dateisystem außerhalb des Stores). Sollte vermieden werden.

---

## Eco-System-spezifisch

### Domäne

Eine Kategorie für Module. Das Eco-System nutzt drei:

- **`system/`** — Maschinen-Konfiguration (Kernel, zram, ops)
- **`userland/`** — Nutzer-Anwendungen (gaming, ide, ssh-agent)
- **Top-Level** — Infrastruktur (init, finalized)

### Profile (implementiert)

Eine Ebene zwischen Modulen und Hosts. Profile legen fest, **welche**
Module aktiviert werden und **mit welchen Werten**:

- **`profile/base`** — Distro-Fundament (mkOverride 1200 für Skalare)
- **`profile/luis-eco`** — Nutzer-Wunsch (mkDefault)
- **`profile/<sub>`** — Sub-Profil, z. B. akku, mesh (mkOverride 500, geplant)
- **`hosts/<host>`** — Maschine (normal oder mkForce)

### Prioritäts-Hierarchie

Die Reihenfolge, in der Werte einander überschreiben:

| Ebene | Priorität |
|-------|-----------|
| `hosts/<host>` (`mkForce`) | 50 |
| `hosts/<host>` (normal) | 100 |
| `profile/luis-eco` (`mkDefault`) | 1000 |
| `profile/base` (`mkOverride 1200`) | 1200 |
| Option-Default (`mkOption`) | 1500 |

**Merkregel:** Kleinere Zahl = stärkere Priorität.

**`mkOverride 2000` funktioniert nicht** — die Option-Defaults liegen bei
1500. `profile/base` nutzt deshalb `1200`.

### Generation 0

Ein geplantes Rettungssystem, das unabhängig vom Hauptsystem läuft und
nie vom GC gelöscht wird. Siehe [`RESCUE-CONCEPT.md`](RESCUE-CONCEPT.md).

### Host

Eine konkrete Maschine. Konfiguriert unter `hosts/<name>/`. Der aktive
Host wird durch `host-config.nix` ausgewählt.

### Repo

Das Git-Repository. Enthält sowohl `docs/` als auch die
NixOS-Konfiguration in `Eco-System/`.

### Lebende Instanz

`/etc/nixos` auf dem laufenden System. Wird per rsync aus dem Repo
aktualisiert. Host-spezifische Dateien (`host-config.nix`,
`flake.lock`) werden **nicht** überschrieben.

### Repo-Root vs. OS-Root

- **Repo-Root:** `~/Projekte/Eco-System/` — Git-Repo
- **OS-Root:** `~/Projekte/Eco-System/Eco-System/` — NixOS-Konfiguration

### `eco-update`

Das zentrale System-Update-Tool. Führt `nix flake update` und
`nixos-rebuild switch` in separaten Schritten mit Retry-Logik aus.

### `eco-gc-retention`

Löscht **nur Generationen-Links** nach festen Regeln. **Kein**
`nix-collect-garbage`. Räumt Boot-Einträge auf.

### `eco-gc-collect`

Führt `nix-collect-garbage` aus, **wenn** die Auslastung über dem
Schwellwert liegt. Löscht **keine Generationen**.

### Retention

Die Auswahl-Regeln für `eco-gc-retention`:

1. Deduplizieren (gleicher Store-Pfad → eine Generation)
2. Mindestens `minGenerations` behalten
3. Alle der letzten 24 Stunden behalten
4. Pro Tag eine (neuste) für die letzten `keepDays` Tage
5. Neuste Generation, die ≥ `keepDays` alt ist

### Cache-Check

Prüfung in `eco-update`, ob der aktuelle Kernel in einem der
konfigurierten Caches liegt. Wird nur ausgeführt, wenn
`cacheCheck.caches` nicht leer ist. Die Caches werden vom jeweiligen
Kernel-Modul gesetzt.

### Post-Update-Hook

Ein Shell-Befehl, der nach erfolgreichem `eco-update`-Switch läuft.
Standard: `eco-gc-retention`.

### Custom Kernel

Ein Kernel, der nicht aus `nixpkgs` oder dem Chaotic-Cache stammt,
sondern über `cachyOverride` lokal gebaut wird (z. B. `lto-v3.nix`).
Custom Kernel haben **nie** einen Cache-Hit und brauchen immer einen
lokalen Build (1–3 h).

### BORE

**Burst-Oriented Response Enhancer** — ein CPU-Scheduler, der für
bessere Interaktivität sorgt. Im CachyOS-Kernel enthalten.

### Bootstrap-Switch

Der **erste Switch** von einer alten Struktur auf eine neue (z. B.
flach → Profile) löst oft mehr Service-Restarts aus als spätere
Switches. Das ist ein **einmaliges** Ereignis, kein Dauerzustand.
Nach dem ersten erfolgreichen Boot in die neue Generation sind
GID, D-Bus-Policy und initrd-Module konsistent — spätere Switches
sind unauffällig.

Bei strukturellen Änderungen deshalb `nixos-rebuild boot` + Reboot
statt `switch`.

### mkForce-Sparsamkeit

`mkForce` (Priorität 50) überschreibt alles — auch automatische
Ergänzungen durch NixOS. **Nie für Listen verwenden**, die NixOS
intern erweitert (`boot.initrd.kernelModules`, `boot.kernelModules`).
Sonst fehlen sicherheitskritische Module (z. B. LUKS) in der initrd.

**Erlaubte Anwendungen:** echte Skalare, die der Host bewusst anders
will als jedes Profil (`networking.hostName`, `system.stateVersion`).

---

## Befehle

### `deploy`

rsync vom Repo nach `/etc/nixos`, dann `nixos-rebuild switch`.

### `deploy-dry`

Wie `deploy`, aber nur Dry-Run — kein scharfer Switch.

### `deploy-copy`

Nur rsync, kein Build. Für manuelle Kontrolle.

### `eco-update`

System-Update mit Cache-Check und Retry-Logik.

### `eco-gc-retention`

Generationen-Retention + Boot-Cleanup.

### `eco-gc-collect`

Store-GC bei Platzmangel.

---

Ende des Glossars.
