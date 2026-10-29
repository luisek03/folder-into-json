# Modul-Referenz

Alle Module im Eco-System, ihre Optionen und ihre Rolle.

---

## Übersicht

| Modul | Pfad | Aktivierung |
|-------|------|-------------|
| `profile/base` | `profile/base/default.nix` | vom Host importiert |
| `profile/luis-eco` | `profile/luis-eco/default.nix` | vom Host importiert |
| `init` | `modules/init.nix` | immer |
| `finalized` | `modules/finalized.nix` | immer |
| `kernel` | `modules/system/kernel/` | `mySystem.customKernel.enable` |
| `zram-swap` | `modules/system/zram-swap.nix` | `mySystem.zramSwap.enable` |
| `ops` | `modules/system/ops/` | importiert update + gc |
| `games` | `modules/userland/games/` | importiert `steam` |
| `steam` | `modules/userland/games/steam.nix` | `mySystem.steam.enable` |
| `nixos_ide` | `modules/userland/nixos_ide.nix` | `mySystem.ide.enable` |
| `ssh-agent-keepassxc` | `modules/userland/ssh-agent-keepassxc.nix` | `services.ssh-agent-keepassxc.enable` |

**Domänen:**

- `modules/system/` — Maschinen-Konfiguration
- `modules/userland/` — Nutzer-Anwendungen
- `modules/*.nix` — globale Infrastruktur (init, finalized)

---

## `modules/init.nix` — Globale Options

Deklariert alle `mySystem.*`-Optionen. Setzt **keine** Konfiguration,
definiert nur das Schema.

### Optionen

| Option | Typ | Default | Beschreibung |
|--------|-----|---------|--------------|
| `mySystem.hostName` | str | `"nixos"` | System-Hostname |
| `mySystem.userName` | str | `"luisek03"` | Primärer Benutzer |
| `mySystem.userFullName` | str | `"Luis Fernando Meyer"` | Voller Name (für Git-Commits) |
| `mySystem.locale` | str | `"de_DE.UTF-8"` | System-Locale |
| `mySystem.timeZone` | str | `"Europe/Berlin"` | Zeitzone |
| `mySystem.keyboard` | str | `"de"` | Tastaturlayout |
| `mySystem.paths.repo` | str | `/home/<user>/Projekte/Eco-System` | Repo-Pfad |

---

## `modules/system/kernel/` — Kernel-Auswahl

### Options

| Option | Typ | Default | Beschreibung |
|--------|-----|---------|--------------|
| `mySystem.customKernel.enable` | bool | `false` | Aktiviert den importierten Kernel |
| `mySystem.customKernel.lts` | bool | `false` | LTS-Variante (nur von chaotic.nix ausgewertet) |

### Dateien

- `_options.nix` — Options-Deklaration
- `lts.nix` — NixOS-LTS-Fallback (greift wenn `enable = false`)
- `default.nix` — importiert `_options` + `lts`
- `cachyos/chaotic.nix` — v1 aus Chaotic-Cache (mit LTS-Toggle)
- `cachyos/lto-v3.nix` — v3 + thinlto (lokaler Build via Override)
- `cachyos/lto-zen2.nix` — nicht implementiert

### Nutzung

    # In hosts/<host>/kernel-modules.nix
    imports = [
      ../../modules/system/kernel
      ../../modules/system/kernel/cachyos/lto-v3.nix
    ];
    mySystem.customKernel.enable = true;

**Immer nur eine Kernel-Datei importieren.** Mehrere Zuweisungen
an `boot.kernelPackages` würden kollidieren.

---

## `modules/system/zram-swap.nix` — RAM-Kompression

### Optionen

| Option | Typ | Default | Beschreibung |
|--------|-----|---------|--------------|
| `mySystem.zramSwap.enable` | bool | `false` | Aktiviert zram |
| `mySystem.zramSwap.algorithm` | enum | `"zstd"` | Kompressionsalgorithmus |
| `mySystem.zramSwap.memoryPercent` | int | `50` | Prozent des RAMs für zram |
| `mySystem.zramSwap.priority` | int | `100` | Swap-Priorität (höher als SSD) |

**Algorithmen:** `lzo`, `lz4`, `lz4hc`, `zstd`, `deflate`, `842`.

**Empfehlung:** `zstd` für gute Kompression, `lz4` für maximale
Reaktionsschnelligkeit.

---

## `modules/system/ops/` — Operations

Alles rund um Updates, Retention und Store-Aufräumen.

### `update` — System-Update

**Optionen:**

| Option | Typ | Default | Beschreibung |
|--------|-----|---------|--------------|
| `mySystem.ops.update.enable` | bool | `false` | Aktiviert `eco-update` |
| `mySystem.ops.update.retries` | int | `0` | Max Retries pro Schritt (0 = unendlich) |
| `mySystem.ops.update.retryDelay` | int | `10` | Sekunden zwischen Retries |
| `mySystem.ops.update.cacheCheck.enable` | bool | `true` | Cache-Check vor Kernel-Update |
| `mySystem.ops.update.cacheCheck.caches` | list str | `[]` | Cache-Quellen (vom Kernel-Modul gesetzt) |
| `mySystem.ops.update.flakeLockBackup.enable` | bool | `false` | Lock nach `hosts/<host>/` kopieren |
| `mySystem.ops.update.flakeLockBackup.autoCommit` | bool | `false` | Automatisch committen |
| `mySystem.ops.update.postUpdate.enable` | bool | `false` | Post-Update-Hook |
| `mySystem.ops.update.postUpdate.script` | str | `null` | Shell-Befehl nach Switch |

**Binary:** `eco-update`

**Flags:**

- `--update-force` — alle Inputs updaten, Cache-Check ignoriert
- `--update-all` — alle Inputs + Cache-Check + Rollback
- `--skip-optimise` — optimise überspringen
- `--unsafe` — nur `nixos-rebuild switch`

**Cache-Check:** Wird nur ausgeführt, wenn `cacheCheck.caches` nicht
leer ist. Das jeweilige Kernel-Modul setzt die Caches:
`chaotic.nix` setzt `["https://nyx-cache.chaotic.cx"]`,
`lto-v3.nix` lässt die Liste leer (weil lokal gebaut wird).

### `gc.retention` — Generationen-Retention

**Optionen:**

| Option | Typ | Default | Beschreibung |
|--------|-----|---------|--------------|
| `mySystem.ops.gc.retention.enable` | bool | `false` | Stellt `eco-gc-retention` bereit |
| `mySystem.ops.gc.retention.keepDays` | int | `7` | Pro Tag eine Generation für N Tage |
| `mySystem.ops.gc.retention.minGenerations` | int | `4` | Mindestanzahl Generationen |

**Binary:** `eco-gc-retention`

**Regeln:** Dedup, Floor, letzte 24h, pro Tag eine (letzte N Tage),
neuste ≥ N Tage alte. **Kein** `nix-collect-garbage`.

### `gc.collect` — Store-Aufräumen

**Optionen:**

| Option | Typ | Default | Beschreibung |
|--------|-----|---------|--------------|
| `mySystem.ops.gc.collect.enable` | bool | `false` | Aktiviert `eco-gc-collect` + Timer |
| `mySystem.ops.gc.collect.startPercent` | int | `85` | Ab dieser Auslastung GC starten |
| `mySystem.ops.gc.collect.targetPercent` | int | `80` | Ziel-Auslastung |
| `mySystem.ops.gc.collect.maxIterations` | int | `3` | Max GC-Läufe pro Aufruf |
| `mySystem.ops.gc.collect.checkPath` | str | `"/nix/store"` | Pfad zum Prüfen |
| `mySystem.ops.gc.collect.schedule` | enum | `"daily"` | `daily` / `weekly` / `never` |

**Binary:** `eco-gc-collect`

---

## `modules/userland/games/` — Gaming

### `common.nix` — Gemeinsame Gaming-Basis

Stellt die gemeinsame Basis bereit, die jeder Launcher braucht.
Wirkt nur, wenn mindestens ein Launcher aktiviert ist.

**Optionen:**

| Option | Typ | Default | Beschreibung |
|--------|-----|---------|--------------|
| `mySystem.games.allowedUnfreePrefixes` | list str | `[]` | Erlaubte unfreie Paket-Präfixe |

**Wirkung:**

- 32-Bit-Grafik (`hardware.graphics.enable32Bit`)
- GameMode (`programs.gamemode`)
- `gamemode` + `gamescope` als Systempakete
- `allowUnfreePredicate` aus den Präfixen

### `steam.nix` — Steam

**Optionen:**

| Option | Typ | Default |
|--------|-----|---------|
| `mySystem.steam.enable` | bool | `false` |

Trägt `[ "steam" ]` in `allowedUnfreePrefixes` ein. Installiert
Steam + Proton-GE, öffnet Firewall für Remote Play, fixiert Locale.

---

## `modules/userland/nixos_ide.nix` — IDE und Deploy-Aliase

**Optionen:**

| Option | Typ | Default |
|--------|-----|---------|
| `mySystem.ide.enable` | bool | `false` |
| `mySystem.ide.repoUrl` | str | `https://github.com/deinuser/Eco-System.git` |
| `mySystem.ide.repoPath` | str | `/home/<user>/Projekte/Eco-System` |
| `mySystem.ide.exclude` | list str | siehe Modul |

**Pakete:** `nixd`, `git`, `lazygit`, `gh`, `kate`

**Aliase:** `eco`, `eco-edit`, `eco-status`, `eco-commit`, `eco-push`,
`eco-pull`, `eco-log`, `deploy`, `deploy-dry`, `deploy-copy`

---

## `modules/userland/ssh-agent-keepassxc.nix` — SSH-Agent

**Optionen:**

| Option | Typ | Default |
|--------|-----|---------|
| `services.ssh-agent-keepassxc.enable` | bool | `false` |

**Status:** In Überarbeitung. Aktuell minimal implementiert.

---

## Ein neues Modul schreiben

### Feature-Modul mit Submodulen

    # modules/system/<feature>/common.nix
    { config, lib, ... }:
    {
      options.mySystem.<feature> = {
        enable = lib.mkOption {
          type = lib.types.bool;
          default = false;
          description = "...";
        };
      };
    }

    # modules/system/<feature>/<sub>.nix
    { config, pkgs, lib, ... }:
    let cfg = config.mySystem.<feature>; in
    {
      imports = [ ./common.nix ];
      config = lib.mkIf cfg.enable {
        # ...
      };
    }

    # modules/system/<feature>/default.nix
    { ... }:
    {
      imports = [ ./common.nix ./<sub>.nix ];
    }

### Einzelnes Modul

    # modules/userland/<feature>.nix
    { config, pkgs, lib, ... }:
    let cfg = config.mySystem.<feature>; in
    {
      options.mySystem.<feature>.enable = lib.mkEnableOption "...";
      config = lib.mkIf cfg.enable {
        # ...
      };
    }

### Konventionen

- **Ein Modul, eine Verantwortlichkeit**
- **Options-Deklaration in `common.nix`**, Konfiguration in Submodulen
- **`common.nix` wird von Submodulen selbst importiert**, nicht vom
  `default.nix`
- **Keine `readDir`-Magie** — explizite Import-Listen
- **Prioritäten nach Hierarchie** — siehe `ARCHITECTURE.md`

### Paketlisten-Merge (wichtig!)

`environment.systemPackages` ist eine **gemergte Liste**: Bei gleicher
Priorität werden alle Beiträge addiert. Bei unterschiedlicher Priorität
gewinnt die stärkere komplett.

**Konsequenz:** Alle Module, die `environment.systemPackages` setzen,
müssen **dieselbe Priorität** haben wie die Profile. Der einfachste Weg:

- Alle Beiträge auf normaler Priorität (100) — kein `mkDefault`,
  kein `mkForce`, kein `mkAfter` — dann addieren sich alle.
- Oder alle auf `lib.mkDefault` (1000) — dann addieren sich alle,
  und der Host kann mit normaler Priorität überschreiben.

**Nicht verwenden:**

- `lib.mkAfter [...]` — bleibt Priorität 100, überschreibt
  `mkDefault`-Profile komplett.
- `lib.mkForce [...]` — überschreibt alles, auch andere Module.

**Gleiches gilt für:**

- `environment.shellAliases`
- `nix.settings.extra-substituters` / `extra-trusted-public-keys`
- `systemd.tmpfiles.rules`
- alle `types.listOf`-Optionen, die mehrere Module beitragen

---

Ende der Modul-Referenz.
