# Operations

Betrieb, Fehlerbehebung, häufige Szenarien.

---

## Diagnose

### System-Status

    # Aktuelle Generation
    sudo nixos-rebuild list-generations | head -3

    # Fehlerhafte Services
    systemctl --failed

    # Auslastung
    df -h /

    # Store-Größe
    du -sh /nix/store

    # Boot-Einträge
    sudo bootctl list | grep -c "title:"

    # Timer-Status
    systemctl list-timers | grep eco-gc

### Verfügbare Binaries

    which eco-update eco-gc-retention eco-gc-collect

---

## Häufige Probleme

### Fehler: `attribute 'nix.settings' already defined`

**Symptom:**

    error: attribute 'nix.settings' already defined at profile/base/default.nix:112:5

**Ursache:** Zwei Zuweisungen an denselben Attributpfad in einer Datei.
In Nix darf ein Attributname pro Attrset nur einmal vorkommen —
auch wenn die zweite Zuweisung eine andere Priorität hat.

**Falsch:**

    nix.settings.experimental-features = lib.mkForce [...];
    nix.settings = lib.mkDefault { ... };

**Richtig — `lib.mkMerge`:**

    nix.settings = lib.mkMerge [
      { experimental-features = lib.mkForce [ "nix-command" "flakes" ]; }
      (lib.mkDefault { ... })
    ];

### Fehler: `experimental Nix feature 'nix-command' is disabled`

**Symptom:** `eco-update` bricht mit

    error: experimental Nix feature 'nix-command' is disabled

**Ursache:** `experimental-features` fehlt in `/etc/nix/nix.conf`. Meist
weil ein leerer `nix.settings = { };`-Block im Host die Definition aus
`profile/base` überschrieben hat (Priorität 100 vs. 1000).

**Sofort-Fix:**

    sudo nix --extra-experimental-features "nix-command flakes" \
      flake update --flake /etc/nixos

**Dauer-Fix:** In `profile/base`:

    nix.settings.experimental-features = lib.mkForce [ "nix-command" "flakes" ];

Damit kann es von keinem leeren Block mehr überschrieben werden.

### Fehler: Boot scheitert mit „Failed to start Find NixOS closure"

**Symptom:** Nach einem `deploy` bootet das System nicht mehr, landet
in der Emergency-Shell oder im Boot-Menü. Log zeigt:

    Failed to start Find NixOS closure.
    Dependency failed for Initrd Default Target.

**Ursache:** `lib.mkForce` auf einer initrd-Liste
(`boot.initrd.kernelModules = lib.mkForce [ ]`) hat die von NixOS
automatisch hinzugefügten LUKS-Module (`dm-crypt`, `dm-mod`, `aes`,
`sha256`) überschrieben. Ohne diese Module kann die initrd die
verschlüsselte Root-Partition nicht öffnen.

**Sofort-Fix:** Reboot in die vorherige Generation (Boot-Menü).
Im laufenden alten System:

    sudo nix-env -p /nix/var/nix/profiles/system --switch-generation <N-1>

**Dauer-Fix:** In `hosts/<host>/kernel-modules.nix` das `mkForce` von
allen `boot.initrd.*`- und `boot.kernelModules`-Zeilen entfernen.

### Fehler: Pakete aus Profilen fehlen nach dem Switch

**Symptom:** Nach dem Wechsel auf Profile fehlen `keepassxc`, `btop`,
`samba` etc. — obwohl sie in `profile/luis-eco` stehen.

**Ursache:** Ein Modul setzt `environment.systemPackages` mit **stärkerer
Priorität** als die Profile. Bei unterschiedlichen Prioritäten gewinnt
die stärkere komplett — die Profil-Pakete fallen weg.

Typische Kandidaten:

- `modules/userland/nixos_ide.nix` (setzt Pakete bei normaler Prio 100)
- `modules/userland/games/steam.nix`
- `modules/userland/games/common.nix`
- `lib.mkAfter` (bleibt Prio 100, überschreibt `mkDefault`-Profile)

**Diagnose:**

    grep -rn "systemPackages" /etc/nixos/

**Fix:** Alle Beiträge auf **dieselbe** Priorität bringen —
entweder überall `lib.mkDefault` oder überall normale Zuweisung
(kein `mkForce`, kein `mkAfter`).

### Boot-Anzeige: Build-Zeit vs. Switch-Zeit

**Symptom:** In `nixos-rebuild list-generations` und im systemd-boot-Menü
haben zwei Generationen oft denselben Tag und dieselbe Uhrzeit, obwohl
sie zu unterschiedlichen Zeiten aktiviert wurden. Ein Tag fehlt, ein
anderer Tag hat doppelt.

**Ursache:** NixOS zeigt den **Build-Zeitpunkt** einer Generation, nicht
den **Aktivierungszeitpunkt**. Bei `deploy`-Workflows liegen beide nah
beieinander. Bei manuellen Builds oder wenn eine Generation erst später
geschwitct wird, können sie Stunden oder Tage auseinanderliegen.

Die **echte Aktivierungszeit** steht in der mtime des Profil-Symlinks:

    stat -c '%n  %y' /nix/var/nix/profiles/system-<N>-link

**Auswirkung:** Keine. Die Retention arbeitet mit den Daten aus
`nix-env --list-generations`, die mit der Symlink-mtime übereinstimmen.
Die Boot-Anzeige ist irreführend, die Auswahl-Logik aber korrekt.

**Workaround bei Verwirrung:** `sudo eco-gc-retention --dry-run` zeigt,
welche Generationen an welchem Tag die Retention sieht (basierend auf
`nix-env`-Daten).

**Nicht-Ziel:** Keine automatische Korrektur der Boot-Anzeige. Das
wäre ein eigener Patch, der bei jedem Rebuild die .conf-Dateien
umschreiben müsste — mehr Komplexität als Nutzen.

### `deploy` hängt in Cache-Retries

**Symptom:** Build hängt minutenlang, viele `502 Bad Gateway`-Warnungen
von `cache.xinux.uz`.

**Ursache:** `cache.xinux.uz` ist down (Server-Fehler). Nix retryt
10× pro Paket mit exponentiellem Backoff.

**Sofort-Fix:** Cache temporär auskommentieren in
`Eco-System/profile/base/default.nix`:

    extra-substituters = [
      "https://cache.nixos.org"
      "https://nix-community.cachix.org"
      # "https://attic.xuyh0120.win/lantian"
      # "https://cache.xinux.uz"
    ];

    deploy

**Nach dem Fix:** Zeilen wieder aktivieren, wenn der Cache zurück ist.

### Kernel wird lokal gebaut (1–2 Stunden)

**Symptom:** `eco-update` baut den Kernel statt ihn zu fetchen.

**Ursache:** Kein Cache liefert den neuen Kernel mit gültiger Signatur.

**Sofort-Fix:** `--skip-cache-check` verwenden — nixpkgs wird
aktualisiert, Kernel bleibt auf alter Revision.

    sudo eco-update --skip-cache-check

**Später:** Wenn Cache wieder liefert, normaler `eco-update`.

### `nixos-rebuild switch` scheitert mit „path not tracked by Git"

**Ursache:** Neue Datei (z.B. neues Modul) ist nicht in Git gestaged.

**Fix:**

    cd ~/Projekte/Eco-System
    git add <pfad>
    deploy

Nix liest nur Dateien, die in Git getrackt sind. Ein `git add` reicht —
kein Commit nötig für den Build.

### Permission denied bei `nix-env --list-generations`

**Symptom:**

    error: opening lock file "/nix/var/nix/profiles/system.lock": Permission denied

**Ursache:** Nur root darf System-Profile anfassen.

**Fix:** `sudo` verwenden.

    sudo eco-gc-retention

### Git: „Unzureichende Berechtigung zum Hinzufügen eines Objektes"

**Ursache:** `eco-update` läuft als root und schreibt in `.git/`. Danach
kann der User nicht mehr committen.

**Fix:**

    cd ~/Projekte/Eco-System
    sudo chown -R $USER:users .git

### Boot-Einträge zeigen veraltete Generationen

**Symptom:** `bootctl list` zeigt Einträge, deren Generation nicht mehr
im Profil existiert.

**Ursache:** `LoaderEntries`-EFI-Variable ist veraltet.

**Fix:** `eco-gc-retention` räumt das auf:

    sudo eco-gc-retention

**Manueller Notfall-Fix:**

    sudo rm /sys/firmware/efi/efivars/LoaderEntries-4a67b082-0a4c-41cf-b6c7-440b29bb8c4f
    sudo reboot

### `eco-update` committet flake.lock nicht

**Symptom:** „Nichts zu committen oder Commit fehlgeschlagen."

**Ursachen:**

- Lock hat sich nicht geändert (normal, wenn Cache-Rollback passiert ist)
- Kein Git-Repo in `repoPath`
- Git-Autor-Identität fehlt

**Diagnose:**

    cd ~/Projekte/Eco-System
    git status
    git log --oneline -3

---

## Häufige Szenarien

### Neue Generation testen

1. Config ändern
2. `deploy-dry` — prüft, was gebaut würde
3. `deploy` — scharf
4. Prüfen: `systemctl --failed`
5. Bei Problemen: `sudo nixos-rebuild switch --rollback`

### Neuen Host hinzufügen

1. Ordner anlegen:

       mkdir -p Eco-System/hosts/<name>

2. `init.nix` schreiben (ähnlich wie `hosts/laptop/init.nix`)

3. In `/etc/nixos/host-config.nix` den neuen Host eintragen:

       {
         name = "<name>";
         host = "<name>";
       }

4. `deploy`

### Neues Modul hinzufügen

1. Ordner-Struktur anlegen (siehe [`MODULES.md`](MODULES.md))

2. Im Host importieren:

       imports = [ ../../modules/features/<name> ];

3. Aktivieren in der Host-Config

4. `deploy`

### Nach einem kaputten Update

1. **Reboot** in die alte Generation (Bootloader-Menü)

2. **Im laufenden alten System:**

       sudo nixos-rebuild switch --rollback

3. **Lock zurückrollen** (falls nötig):

       cd ~/Projekte/Eco-System
       git log --oneline Eco-System/hosts/laptop/flake.lock
       git checkout <letzter-guter> -- Eco-System/hosts/laptop/flake.lock
       sudo cp Eco-System/hosts/laptop/flake.lock /etc/nixos/flake.lock
       sudo nixos-rebuild switch --flake /etc/nixos

---

## Manuelle Cache-Kontrolle

### Prüfen, ob Paket in Cache

    nix store verify --store https://cache.xinux.uz --sigs-needed 1 \
      /nix/store/<pfad>

Exit 0 = im Cache und signiert. Exit 2 = im Cache, aber untrusted.
Andere = nicht im Cache oder Fehler.

### Prüfen, ob Cache erreichbar

    curl -sI https://cache.xinux.uz/nix-cache-info | head -1

- `HTTP/2 200` — erreichbar
- `HTTP/2 502` — Server down

---

## Logs

### eco-update

    sudo journalctl -u eco-gc-collect.service -n 50 --no-pager

### Post-Update-Hook

Der Hook schreibt in den normalen `eco-update`-Output. Kein
separates Journal.

### Build-Logs

    sudo journalctl -xe

---

## Notfall-Rettung

**Stufe 1:** Alte Generation booten (Bootloader-Menü).

**Stufe 2:** Von einem Live-USB booten, `/etc/nixos` inspizieren,
Lock wiederherstellen.

**Stufe 3:** Neuinstallation. `/home` und `/nix` sind auf eigenen
Subvolumes, bleiben erhalten.

**Nicht vergessen:** Vor jedem riskanten Schritt (`eco-update`,
Kernel-Update) die aktuelle `hosts/<host>/flake.lock` committen.
Das ist das Sicherheitsnetz.

---

Ende der Operations.
