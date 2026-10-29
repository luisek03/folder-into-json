# Architektur

Wie das Eco-System aufgebaut ist, warum es so aufgebaut ist, und wie
die Teile zusammenspielen.

---

## 1. Das große Bild

Eco-System ist eine **deklarative NixOS-Konfiguration**, die mehrere
Hosts mit gemeinsamer Basis und individuellen Anpassungen unterstützt.

Drei Designziele prägen jede Entscheidung:

1. **Reproduzierbarkeit** — derselbe Commit baut dasselbe System
2. **Modularität** — ein Modul, eine Verantwortlichkeit
3. **Leichtgewicht** — keine Redundanz, kein unnötiger Speicherverbrauch

---

## 2. Repo-Struktur

    Eco-System/                        # Git-Repo (Projekt-Root)
    ├── README.md
    ├── docs/                          # Diese Dokumentation
    └── Eco-System/                    # NixOS-Konfiguration
        ├── configuration.nix          # Einstiegspunkt
        ├── flake.nix                  # Flake-Definition
        ├── flake.lock                 # Gepinnte Inputs (Template)
        ├── host-config.nix            # Host-Auswahl (Template)
        │
        ├── profile/                   # Politik (Zwischenebene Module↔Host)
        │   ├── base/                  # Distro-Fundament (user-agnostisch)
        │   │   └── default.nix
        │   └── luis-eco/              # Nutzer-Wunsch
        │       └── default.nix
        │
        ├── hosts/                     # Host-spezifisch
        │   └── laptop/
        │       ├── default.nix        # Importiert Profile + Host-Module
        │       ├── fstab.nix
        │       ├── kernel-modules.nix
        │       ├── wifi-hardware.nix
        │       ├── state-version.nix
        │       └── flake.lock         # Backup der lebenden Lock
        │
        └── modules/                   # Wiederverwendbar
            ├── init.nix               # Globale Options
            ├── finalized.nix          # Abschluss-Modul
            │
            ├── system/                # Maschinen-Konfiguration
            │   ├── kernel/            # Kernel-Auswahl
            │   │   ├── default.nix
            │   │   ├── _options.nix
            │   │   ├── lts.nix        # NixOS-LTS-Fallback
            │   │   └── cachyos/
            │   │       ├── default.nix
            │   │       ├── common.nix
            │   │       ├── chaotic.nix    # v1 aus Cache
            │   │       └── lto-v3.nix     # v3 lokal
            │   ├── zram-swap.nix      # RAM-Kompression
            │   └── ops/               # Update + GC
            │       ├── default.nix
            │       ├── common.nix
            │       ├── update.nix
            │       ├── update/        # Python-Module
            │       ├── gc.nix
            │       ├── gc-retention.py
            │       └── gc-collect.py
            │
            └── userland/              # Nutzer-Anwendungen
                ├── games/             # Steam + Launcher
                │   ├── default.nix
                │   ├── common.nix
                │   └── steam.nix
                ├── nixos_ide.nix      # Kate, Git, Deploy-Aliase
                └── ssh-agent-keepassxc.nix

### Warum zwei `Eco-System/`-Ebenen?

- **Äußere Ebene:** Projekt-Root mit Git, `docs/`, künftigen weiteren
  Systemen (Rescue, Cache)
- **Innere Ebene:** Die eigentliche NixOS-Konfiguration

Diese Trennung erlaubt es, in Zukunft **mehrere Systeme** unter einem
Projekt zu verwalten:

    Eco-System/
    ├── Eco-System/          # Hauptsystem (aktuell)
    ├── Rescue-System/       # Generation 0 (geplant)
    └── Cache-System/        # Cache-Container (geplant)

Jedes System hat eigene `flake.nix`, `configuration.nix`, `hosts/`.

### Warum `system/` und `userland/`?

Die Module sind nach **Zielgruppe** sortiert, nicht nach „Feature".

- **`system/`** — Konfiguriert die Maschine selbst. Läuft auch ohne
  angemeldeten Nutzer. Kernel, zram, SSH-Server, Update-Werkzeuge.
- **`userland/`** — Setzt einen angemeldeten Nutzer voraus. Ohne ihn
  sinnlos. Steam, IDE, SSH-Agent.

Der Name `userland/` ist an den OS-Begriff angelehnt (Gegensatz zu
Kernel-Space). Er kollidiert nicht mit dem geplanten `system/desktop/`,
das später die Desktop-Umgebung (Plasma, SDDM) enthalten soll.

### Warum `profile/` als eigene Ebene?

`profile/` liegt **zwischen** Modulen und Hosts. Es enthält **Politik**,
keine Mechanik:

- `profile/base/` — das user-agnostische Fundament (Plasma, Pipewire,
  Bootloader, Default-Locale `en_US`, Default-Keyboard `us`).
- `profile/luis-eco/` — Luis' persönlicher Wunsch (Locale `de_DE`,
  Keyboard `de`, persönliche Pakete, SSH-Keys).

Ein Host importiert beide Profile und ergänzt host-spezifische Module
(`fstab.nix`, `kernel-modules.nix`, …).

## 3. Der Build-Fluss

### Manuell (via `deploy`)

    Repo (Git)
       │
       │  rsync --delete (mit Excludes)
       ▼
    /etc/nixos/             ← lebende Instanz
       │
       │  nixos-rebuild switch --flake /etc/nixos
       ▼
    Neue Generation im System-Profil

### Warum rsync statt direktem Build aus dem Repo?

Die **lebende Instanz** liegt in `/etc/nixos`. Der Repo-Stand wird
dorthin kopiert, das System baut von dort. Das hat Vorteile:

- **Host-spezifische Dateien** (`host-config.nix`, `flake.lock`)
  bleiben in `/etc/nixos` erhalten — der rsync überschreibt sie nicht
- **Kein `.git`** in `/etc/nixos` nötig → Nix baut ohne Git-Awareness
- **Kein `--impure`** nötig → reproduzierbare Builds

### Was wird ausgeschlossen (rsync-Excludes)

- `host-config.nix` — host-spezifisch, lebend in `/etc/nixos`
- `flake.lock` — lebende Instanz in `/etc/nixos`, nicht aus Repo
- `.git`, `.gitignore` — Git-Metadaten
- `result`, `result-*`, `*.drv` — Build-Artefakte
- `docs`, `README.md` — nicht für Build nötig
- Editor-Kram (`*.swp`, `*.kate-swp`, `*~`)

### `switch` vs. `boot` — wann was

- **`nixos-rebuild switch`** — baut und aktiviert **live**. Für
  alltägliche Config-Änderungen. Riskant bei strukturellen Umbauten,
  weil Dienste neugestartet werden und D-Bus-Races auftreten können
  (polkit, accounts-daemon, dbus-broker).
- **`nixos-rebuild boot`** — baut und trägt in den Bootloader ein,
  **aktiviert nichts**. Für strukturelle Änderungen (Profil-Umbau,
  Service-Änderungen, User-Änderungen). Beim nächsten Reboot startet
  die neue Generation frisch — kein Live-Race.

**Praxis:** `deploy` nutzt `switch`. Bei größeren Umbauten stattdessen:

    deploy-copy
    sudo nixos-rebuild boot --flake /etc/nixos
    sudo reboot

---

## 4. Modul-Konzept

### Drei Ebenen

1. **Globale Options** — `modules/init.nix` deklariert alle
   `mySystem.*`-Optionen. Keine Konfiguration, nur Schema.
2. **Feature-Module** — `modules/system/*` und `modules/userland/*`.
   Setzen Konfiguration abhängig von Optionen.
3. **Host-Konfiguration** — `hosts/<host>/init.nix`. Importiert
   Module und überschreibt Optionen.

### Prioritäts-Hierarchie

NixOS-Module kennen keine eingebaute Reihenfolge zwischen Dateien.
Die Reihenfolge entsteht über **Prioritäten** in den Zuweisungen.
Das Eco-System nutzt dafür folgende Stufen:

| Ebene | Mechanik | Priorität | Gewinnt gegen |
|-------|----------|-----------|---------------|
| `hosts/<host>` hart | `lib.mkForce` | 50 | alles |
| `hosts/<host>` normal | normale Zuweisung | 100 | `mkDefault`, `mkOverride` |
| `profile/luis-eco` | `lib.mkDefault` | 1000 | `mkOverride 1200` |
| `profile/base` | `lib.mkOverride 1200` | 1200 | nur Option-Default |
| Option-Default (`mkOption`) | `default = …` | 1500 | niemanden |
| `profile/base` (Listen) | `lib.mkDefault` | 1000 | Option-Default |

**Merkregel:** Kleinere Zahl = stärkere Priorität.

**Wichtig:** `mkOverride 2000` funktioniert **nicht** — die Option-Defaults
liegen bei 1500, also muss `profile/base` **1200** nutzen, um den
Distro-Standard zu überschreiben, aber von `mkDefault` (1000) überstimmt
werden zu können.

**`mkForce` sparsam nutzen.** Es überschreibt alles — auch automatische
Ergänzungen durch NixOS. Das führt zu subtilen Bugs:

- `boot.initrd.kernelModules = lib.mkForce [ ]` → LUKS-Module
  (`dm-crypt`, `aes`, …) fehlen in der initrd → Root-Partition nicht
  entschlüsselbar → Boot scheitert mit „Find NixOS closure".
- `nix.settings = lib.mkForce { … }` → alle nicht genannten Keys
  (z. B. `experimental-features`) fallen weg.

**`mkForce` nur für echte Skalare** (z. B. `networking.hostName`) und
**nie für Listen**, die NixOS intern erweitert.

### Listen vs. Skalare — unterschiedliche Merge-Regeln

- **Skalare** (`time.timeZone`, `console.keyMap`, `services.xserver.enable`):
  Stärkste Priorität gewinnt — die Hierarchie oben greift.
- **Listen/Attrsets** (`environment.systemPackages`,
  `environment.shellAliases`, `nix.settings`):
  **Bei gleicher Priorität wird gemergt.** Bei unterschiedlicher
  Priorität gewinnt die stärkere komplett (die schwächere fällt weg).

**Konsequenz für Paketlisten:** Alle Beiträge (Profile, Module, Host)
müssen **dieselbe Priorität** haben, damit sie sich addieren. Der
einfachste Weg: **normale Priorität (100)** überall — dann kann der
Host nur mit `mkForce` überschreiben, was für Pakete fast nie nötig ist.

`lib.mkAfter` / `lib.mkBefore` ändern **nur die Position** in der Liste,
**nicht die Priorität** — sie gewinnen weiterhin gegen `mkDefault`.
Für additive Beiträge ist `lib.mkDefault` oder normale Priorität
richtig, nicht `mkAfter`.

### Profile-Konzept (implementiert)

Die **Module** sind der passive Baukasten. Was tatsächlich aktiv
ist, entscheiden **Profile**:

    profile/base         → Distro-Fundament (mkOverride 1200 für Skalare)
    profile/luis-eco     → Nutzer-Wunsch (mkDefault)
    hosts/<host>         → Maschine (normal oder mkForce)

Ein Host importiert:

    imports = [
      ../../profile/base
      ../../profile/luis-eco
      ./kernel-modules.nix          # host-spezifisch
      # ...
    ];

**`configuration.nix` importiert `profile/` NICHT direkt.** Nur der
Host entscheidet, welche Profile gelten. So kann ein zweiter Host
später andere Profile importieren, ohne dass `configuration.nix`
angefasst werden muss.

**Sub-Profile** (z. B. `profile/battery`, `profile/mesh`) sind
vorgesehen, aber noch nicht implementiert. Sie würden mit
`lib.mkOverride 500` zwischen `luis-eco` (1000) und Host (100) liegen.

### Feature-Ordner-Struktur

    modules/<domäne>/<feature>/
    ├── default.nix       # importiert Submodule
    ├── common.nix        # Options-Deklaration + Basiskonfiguration
    └── <sub>.nix         # konkrete Implementierungen

**Regeln:**

- `common.nix` deklariert Options und wird von den Submodulen selbst
  importiert — nicht zentral vom `default.nix`.
- Submodule mit `enable`-Bedingung: `config = lib.mkIf cfg.enable { ... }`.
- Kein `readDir`-Magie — explizite Import-Listen.

---

## 5. Host-Auswahl

`host-config.nix` in `/etc/nixos` wählt den Host:

    {
      name = "Luis-Laptop";
      host = "laptop";
    }

`configuration.nix` importiert dann `hosts/${host}/init.nix`.

**Der Repo-Stand ist ein Template.** Das rsync überschreibt
`host-config.nix` nicht — die lebende Version bestimmt, welcher Host
gebaut wird.

---

## 6. flake.lock-Strategie

**Zwei Locks, zwei Rollen:**

| Ort | Rolle | Aktualisiert von |
|-----|-------|------------------|
| Repo `Eco-System/flake.lock` | Template für neue Systeme | `nix flake update` (manuell, selten) |
| `/etc/nixos/flake.lock` | Lebende Instanz, bestimmt den Build | `eco-update` (regelmäßig) |
| `hosts/<host>/flake.lock` | Backup der lebenden Lock | `eco-update` (automatisch) |

**Warum?**

- Die lebende Instanz in `/etc/nixos` muss unabhängig vom Repo-Stand
  gepflegt werden können. Der rsync schließt sie aus.
- Der Host-Backup in `hosts/<host>/flake.lock` wird per Git
  versioniert. So bleibt nachvollziehbar, welche Revision wann und
  warum aktiv war.
- Bei einem kaputten Update kann die Lock aus dem Backup
  wiederhergestellt werden.

**`eco-update` kopiert nach jedem erfolgreichen Update die lebende
Lock nach `hosts/<host>/flake.lock` und committet sie (ohne push).**
Der manuelle Push aktiviert die Versionierung auf GitHub.

---

## 7. Kernel-Auswahl (aktuell)

Der Kernel wird über **Import** gewählt, nicht über Options:

    imports = [
      ../../modules/system/kernel                    # Options + LTS-Fallback
      ../../modules/system/kernel/cachyos/lto-v3.nix # v3 thinlto bore
    ];

    mySystem.customKernel.enable = true;

**Verfügbare Varianten:**

- `kernel` (nur Options + LTS-Fallback, wenn `enable = false`)
- `kernel/cachyos` (v1 aus Chaotic-Cache)
- `kernel/cachyos/lto-v3.nix` (v3 + thinlto, lokal gebaut)
- `kernel/cachyos/lto-zen2.nix` (nicht implementiert — CachyOS
  unterstützt `ZEN2` nicht als `_processor_opt`)

**Cache-Verhalten:**

| Variante | Cache-Hit? | Build-Zeit |
|----------|-----------|-----------|
| LTS (NixOS) | ✅ Immer | 0 |
| Chaotic v1 | ⚠️ Oft | 0 oder 1–3 h |
| `lto-v3` | ❌ Nie | 1–3 h lokal |
| Custom (`cachyOverride`) | ❌ Nie | 1–3 h lokal |

Mehr zur Cache-Problematik: [`CACHE-SERVER-CONCEPT.md`](CACHE-SERVER-CONCEPT.md).

---

## 8. Designprinzipien

### Deklarativ statt imperativ

Alles, was das System ausmacht, steht in der Konfiguration. Keine
manuellen Tweaks nach dem Boot. Wenn es nicht in Nix steht, existiert
es nicht.

### Modular statt monolithisch

Ein Modul, eine Verantwortlichkeit. `update` kümmert sich um Updates,
`gc-retention` um Generationen, `gc-collect` um den Store.

### Leichtgewicht als Feature

Ressourcen sind begrenzt. Jede Redundanz kostet Speicher, CPU, Zeit.
Ein Kernel pro Generation, keine doppelten Fallbacks, Pin nur wo nötig.

### Kein automatisches Update

Das System ändert sich nur, wenn der Nutzer es will. `eco-update` läuft
manuell. Keine Hintergrund-Updates.

### Rettung vor Neuinstallation

Eskalationsstufen bei Problemen: alte Generation → Generation 0 →
Live-USB → Neuinstallation (letztes Mittel). Siehe
[`RESCUE-CONCEPT.md`](RESCUE-CONCEPT.md).

---

Ende der Architektur.
