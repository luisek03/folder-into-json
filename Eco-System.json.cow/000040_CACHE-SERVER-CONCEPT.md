# Cache-Server-Konzept: Eigenbau-Nix-Cache auf Proxmox

> Status: Konzeptphase / Zukunftsmusik
> Ersteller: luisek03
> Datum: 2026-10-02
> Bezug: Eco-System, `docs/RESCUE-CONCEPT.md`, `docs/IDEA.md`
> Kontext: CachyOS-Caches (`attic`, `xinux.uz`) sind unzuverlässig —
>          Signaturprobleme, 502er, tagelange Ausfälle.

---

## 1. Kerngedanke

Ein eigener kleiner NixOS-Container auf einem Proxmox-Host übernimmt
das Bauen von Paketen, die regelmäßig anfallen (v.a. den CachyOS-Kernel),
und stellt sie als eigenen signierten Binär-Cache bereit.

Der Laptop ist **nicht** der Bauer. Er **wünscht** nur — über eine
Manifest-Datei im Eco-System-Repo. Der Container liest das Manifest,
baut die gewünschten Pakete, signiert sie und legt sie in seinem Cache ab.

Damit ist der langsame Laptop nicht mehr der Flaschenhals für
Kernel-Builds, und die unzuverlässigen Fremd-Caches werden optional.

---

## 2. Problem

### 2.1 Die aktuellen Caches sind unzuverlässig

- **`cache.xinux.uz`**: 502 Bad Gateway seit mehreren Tagen.
- **`attic.xuyh0120.win/lantian`**: liefert Pakete mit ungültiger
  Signatur → Nix ignoriert sie, lokal baut trotzdem.
- Beide sind Single Points of Failure mit unbekanntem Betrieb.

Konsequenz: Wenn ein neuer CachyOS-Kernel im `nix-cachyos-kernel`-Input
auftaucht und nicht in beiden Caches liegt, baut der Laptop lokal.
Ein Kernel-Build dauert 1–2 Stunden und blockiert die Kiste.

### 2.2 Der Laptop ist nicht dafür geeignet

AMD Ryzen 5 7520U, Zen 2, 4 Kerne / 8 Threads. Ein ThinLTO-Kernel
ist auf dieser Hardware ein Nachmittagsprojekt, nicht ein
Nebenbei-Build.

### 2.3 Fehlende Kontrolle

Ein Cache, der von Dritten betrieben wird, hat keinen Einfluss auf:

- Aktualität (wann werden neue Kernel gebaut?)
- Signatur (welcher Key wird genutzt? wird überhaupt signiert?)
- Verfügbarkeit (Wartungsfenster, Ausfälle)

---

## 3. Lösung: Eigener Cache-Container

### 3.1 Eigenschaften

- **Eigene `nixosConfiguration`** im Eco-System-Repo
- **Läuft auf Proxmox** als NixOS-Container (LXC) oder VM
- **Kein permanenter Dienst am Laptop** — der Container läuft autonom
- **Manifest-gesteuert** — was gebaut wird, steht in einer Datei im Repo
- **Repo-verankert** — die Wahrheit liegt im Git, nicht im Container
- **Signiert** — mit eigenem Schlüssel, Public Key auf allen Clients
- **Fallback-freundlich** — Laptop kann weiter lokal bauen, wenn Cache fehlt

### 3.2 Warum Container auf Proxmox

- **Anderer Host** — der Laptop bleibt frei für seine Arbeit
- **Dauerhaft an** — kann in Intervallen prüfen und bauen
- **Isoliert** — Absturz des Containers betrifft den Laptop nicht
- **Günstig** — Proxmox-Hardware ist vorhanden (geplant oder existierend)
- **Sauber trennbar** — eigenes NixOS-System, eigenes Profil

### 3.3 Warum eigenes System im Eco-System-Repo

Der Cache-Container ist **kein Rescue-System** und **kein Hauptsystem**.
Er ist ein eigenes System mit eigener Rolle:

- Braucht kein Desktop, kein Plasma, kein Firefox
- Braucht viel Speicher für den Cache-Store
- Braucht CPU für Kernel-Builds
- Braucht Netzwerk zum Pushen ins Cache-Verzeichnis

Die Trennung folgt dem gleichen Muster wie `hosts/laptop/` und
(später) `hosts/rescue/`:

    Eco-System/
    ├── default/        # gemeinsam für alle Systeme
    ├── hosts/
    │   ├── laptop/     # Hauptsystem
    │   ├── rescue/     # Generation 0 (geplant)
    │   └── cache/      # NEU: Cache-Container
    └── flake-modules/

---

## 4. Manifest

### 4.1 Zweck

Der Laptop sagt dem Cache: **„Diese Pakete möchte ich gecacht haben."**
Der Container liest das Manifest und baut genau diese Pakete.

### 4.2 Format (Vorschlag, nicht final)

Eine Nix-Datei im Repo, weil sie ohnehin aus der Flake-Welt kommt:

    # Eco-System/hosts/cache/manifest.nix
    {
      # Pakete, die aus nixpkgs gecacht werden sollen
      # Format: "<flake-attr-pfad>"
      packages = [
        # CachyOS-Kernel-Varianten für alle Hosts
        "nix-cachyos-kernel#legacyPackages.x86_64-linux.linuxPackages-cachyos-bore-lto-x86_64-v3"
        "nix-cachyos-kernel#legacyPackages.x86_64-linux.linuxPackages-cachyos-bore-lto-zen4"

        # Zukünftige Anwendungsfälle
        # "nixpkgs#blender"
        # "nixpkgs#libreoffice"
      ];

      # Zusätzliche Pins, die der Container beim Bauen respektieren soll
      # (z. B. CachyOS-Overlay-Revision)
      pins = {
        nix-cachyos-kernel = "github:xddxdd/nix-cachyos-kernel/release";
      };
    }

**Warum Nix statt TOML/YAML:**

- Ohne Parser-Abhängigkeit nutzbar (`nix eval`)
- Kann auf Flake-Attribute direkt verweisen
- Kann später um komplexe Logik erweitert werden (Conditionals,
  Host-abhängige Listen, etc.)

**Nachteil:** Auch Menschen, die Nix nicht kennen, müssen es lesen
können. Für ein privates Projekt aber unkritisch.

### 4.3 Wo das Manifest liegt

`hosts/cache/manifest.nix` — im Eco-System-Repo, versioniert mit Git.

Der Laptop ändert das Manifest, wenn er neue Pakete gecacht haben will:

    # Änderung → commit → push
    eco-commit
    eco-push

Der Container zieht das beim nächsten Sync.

---

## 5. Ablauf

### 5.1 Auf dem Laptop

1. Neuen Kernel oder neues Paket im Manifest hinzufügen
2. `eco-commit && eco-push`
3. Fertig — der Rest passiert ohne weiteres Zutun

### 5.2 Auf dem Container

**Trigger-Varianten (eine oder mehrere):**

- **Timer**: stündlich oder zweimal täglich
- **Git-Webhook**: Push auf das Repo löst Build aus
- **Manuell**: `ssh cache-container 'build-manifest'`

**Ablauf pro Lauf:**

1. `git pull` im lokalen Klon des Eco-System-Repos
2. Manifest einlesen (`nix eval -f hosts/cache/manifest.nix`)
3. Für jedes Paket: prüfen, ob es schon im Cache liegt
4. Fehlende Pakete bauen (`nix build`)
5. Ergebnis signieren (`nix store sign --key-file ...`)
6. In den Cache-Store kopieren (`nix copy --to file:///var/cache/nix-serve`)
7. Optional: Status ins Journal schreiben

### 5.3 Auf dem Laptop (beim Deploy)

1. `nixos-rebuild switch --flake /etc/nixos`
2. Nix fragt den eigenen Cache zuerst
3. Bei Treffer: Fetch vom Container
4. Bei Miss: Fallback auf `cache.nixos.org` oder lokal

---

## 6. Signierung

### 6.1 Public-Key-Infrastruktur

- **Auf dem Container:** Private Key, um Cache-Pfade zu signieren
- **Auf dem Laptop:** Public Key in `extra-trusted-public-keys`
- **Key-Generierung:** `nix-store --generate-binary-cache-key <name> <private> <public>`

**Format:**

    nix-store --generate-binary-cache-key eco-cache-1 \
      /root/secrets/eco-cache-1.sec \
      /root/secrets/eco-cache-1.pub

Der Public Key sieht aus wie:

    eco-cache-1:base64-encoded-public-key-data

### 6.2 Verteilung

Der Public Key muss auf den Laptop, in `default/init.nix`:

    nix.settings.extra-trusted-public-keys = [
      "eco-cache-1:<base64>"
      # alte Cache-Keys — bleiben als Fallback
      # "lantian:..."
      # "cache.xinux.uz:..."
    ];

Der Private Key bleibt **nur** auf dem Container. Kein Backup auf
GitHub, keine Kopie auf dem Laptop.

**Backup-Strategie (zu klären):**

- Wenn der Private Key verloren geht, ist der gesamte Cache ungültig
- Optionen: sicherer USB-Stick, KeePassXC mit YubiKey, gedruckter
  Notfall-Zettel, oder Neugenerierung (Cache muss neu gebaut werden)

---

## 7. Speicher-Strategie

### 7.1 Größenordnung

Ein CachyOS-ThinLTO-Kernel belegt ca. 200 MiB im Store. Bei 2–3
Varianten (x86_64-v3, zen4, evtl. v2) und einigen Wochen Historie:

- 3 Varianten × 200 MiB × 4 Wochen = 2.4 GiB
- Zusätzliche Pakete (Blender, etc.): variabel

**Realistisch:** 50–200 GiB für den Cache, um mehrere Wochen
Kernel-Historie und ein paar Anwendungen zu halten.

### 7.2 Retention auf dem Container

Der Cache braucht eine eigene Retention:

- **Regel:** Wenn ein Paket X Wochen nicht angefragt wurde, löschen
- **Einfachste Version:** Nur den aktuellen Kernel + letzte 2 Versionen
- **Cleanup:** `nix-collect-garbage` im Cache-Store

Das ist ein eigenes Skript, kein Teil von `eco-gc-*` (weil der
Container sein eigener Host ist).

### 7.3 Cache-Größe limitieren

Der Cache-Store kann auf einer eigenen Partition oder einem eigenen
Volume liegen, das der Container nicht überschreiten darf.

- LXC: Bind-Mount einer ZFS-Dataset
- VM: eigene virtuelle Disk

---

## 8. Fallback-Strategie

### 8.1 Wenn der Container offline ist

Der Laptop merkt das nicht sofort — Nix versucht den Cache,
Timeout nach einigen Sekunden, fällt zurück auf `cache.nixos.org`.

**Nachteil:** Jeder Fetch-Versuch kostet ein paar Sekunden.

**Lösung:** Cache-Eintrag in `extra-substituters` bleibt, aber
`connect-timeout` reduzieren (z. B. 5 statt 30 Sekunden).

### 8.2 Wenn der Cache das Paket nicht hat

Nix fällt auf den nächsten Substituter zurück, oder baut lokal.

**Kein Fehler, kein Abbruch** — die normale Fallback-Kette greift.

### 8.3 Wenn der Signing-Key abgelehnt wird

Passiert nur, wenn der Public Key am Laptop fehlt oder falsch ist.
Dann ignoriert Nix den Cache — wie aktuell bei `attic`.

**Präventiv:** Test-Trigger nach dem Container-Setup:

    nix store verify --store https://cache.local --sigs-needed 1 <store-pfad>

---

## 9. Technische Bausteine

### 9.1 NixOS-Konfiguration

Geplanter Pfad: `hosts/cache/`

    hosts/cache/
    ├── init.nix              # Host-spezifische Konfiguration
    ├── manifest.nix          # Was gebaut werden soll
    ├── network.nix           # DHCP, SSH, evtl. Tailscale
    ├── storage.nix           # Cache-Volume, fstab
    ├── signing.nix           # Key-Setup
    ├── cache-server.nix      # nix-serve-ng oder attic
    └── build-service.nix     # systemd-Service für Manifest-Build
    └── build-service.py      # Skript für Manifest-Lesen + Build

### 9.2 Cache-Software

**Optionen:**

| Software | Vorteil | Nachteil |
|----------|---------|----------|
| `nix-serve-ng` | Einfach, in Nixpkgs | Wenig Features, nur HTTP |
| `attic` | Gleiche Software wie CachyOS-Caches, Multi-Binary-Cache | Externe Abhängigkeit, mehr Setup |
| `harmonia` | Modern, Rust, aktiv entwickelt | Jünger als die anderen |

**Empfehlung für den Anfang:** `nix-serve-ng` — minimal, versteht Nix
ohne Übersetzungsprobleme, ein Dienst, fertig. Bei Bedarf später auf
`attic` umsteigen.

### 9.3 Build-Service

Ein systemd-Service + Timer, der das Manifest liest und baut:

    systemd.services.eco-cache-build = {
      description = "Baut Pakete aus dem Eco-Cache-Manifest";
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${pkgs.eco-cache-build}/bin/eco-cache-build";
      };
    };

    systemd.timers.eco-cache-build = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnCalendar = "hourly";  # oder täglich, je nach Bedarf
        Persistent = true;
      };
    };

Das Skript ist ähnlich zu `gc-collect.py` — Python, keine
Abhängigkeiten, klare Ausgabe.

### 9.4 Manifest-Lesen

In Python: `subprocess.run(["nix", "eval", "--json", ...])` und
JSON parsen. Oder das Skript in Nix selbst schreiben und als
Ableitung bauen.

### 9.5 Zugriff vom Laptop

Der Cache läuft auf einem internen Netz (z. B. 192.168.178.0/24).
Der Laptop muss den Container über DNS-Namen oder IP erreichen können.

**Optionen:**

- **Lokales Netz:** Container im gleichen LAN wie der Laptop
- **Tailscale:** Wenn der Container nicht im LAN ist (z. B. im
  Rechenzentrum)
- **WireGuard:** Wenn Tailscale nicht gewünscht

Für den Anfang: LAN. Später Tailscale, wenn nötig.

### 9.6 Git-Zugriff vom Container

Der Container braucht **Lesezugriff** auf das Eco-System-Repo.
Reicht ein flacher, read-only Clone per HTTPS:

    git clone https://github.com/luisek03/Eco-System.git /srv/eco-cache/repo

**Kein SSH-Key nötig.** Der Push bleibt am Laptop.

---

## 10. Vorteile gegenüber anderen Methoden

### 10.1 Gegenüber Fremd-Caches

- **Volle Kontrolle:** Aktualität, Signatur, Verfügbarkeit
- **Kann auf die eigenen Bedürfnisse zugeschnitten werden** (Kernel-
  Varianten für Laptop, Desktop, evtl. Rescue)
- **Keine bösen Überraschungen** wie 502 oder ungültige Signaturen

### 10.2 Gegenüber lokalem Bauen

- **Laptop bleibt frei** für die eigentliche Arbeit
- **Build läuft auf dediziertem Host** — mehr Kerne, mehr RAM
- **Stromverbrauch** — der Container läuft sowieso, der Laptop nicht
- **Kann über Nacht laufen**, während der Laptop aus ist

### 10.3 Gegenüber Hydra

- **Keine zwei Tage Verzögerung** — der Container baut sofort, wenn
  im Manifest etwas Neues steht
- **Keine fremde Wartung** — der Container gehört dir
- **Klein und fokussiert** — nicht alle nixpkgs-Pakete, nur was du
  brauchst

---

## 11. Offene Punkte / zu klären

- [ ] **Proxmox-Setup:** Vorhanden oder noch zu beschaffen?
- [ ] **Container-Typ:** LXC oder QEMU-VM?
- [ ] **Speicherplatz:** Eigene Disk/Dataset oder Teil eines Pools?
- [ ] **Netzwerk:** LAN direkt oder Tailscale?
- [ ] **Cache-Software:** nix-serve-ng, attic, harmonia?
- [ ] **Manifest-Format:** Nix-Expression oder TOML/YAML?
- [ ] **Trigger:** Timer, Git-Webhook, oder beides?
- [ ] **Build-Parallelität:** Wie viele Pakete gleichzeitig bauen?
- [ ] **Signing-Key-Backup:** Wo aufbewahren? Physisch oder digital?
- [ ] **Cache-Retention:** Nach welchen Regeln aufräumen?
- [ ] **Fallback-Verhalten am Laptop:** Timeout-Werte anpassen?
- [ ] **Monitoring:** Wie merke ich, dass der Cache steht?
- [ ] **Logs:** Ins Journal oder eigene Datei auf dem Container?
- [ ] **Wann starten?** — wenn Proxmox steht, oder jetzt schon planen?

---

## 12. Nicht-Ziele

- Kein allgemeiner Public-Cache für die NixOS-Community
- Kein Ersatz für `cache.nixos.org` (nur Ergänzung)
- Kein Builder für andere Leute
- Kein Hochverfügbarkeits-Setup (ein Container, kein Cluster)
- Kein CDN (nur lokaler Zugriff oder via VPN)

---

## 13. Philosophie

Der Cache-Container folgt der Eco-System-Logik: **Kontrolle durch
Eigentum**, nicht durch Abhängigkeit von fremden Diensten.

Er ist kein Luxusprojekt. Er löst ein konkretes Problem (CachyOS-
Kernel-Cache-Ausfälle), das jeden Tag auftreten kann. Er ist
gleichzeitig ein **Modell für weitere Auslagerungen** — später
könnten ähnliche Container für andere Aufgaben dienen:

- DNS-Wrapper (`docs/IDEA.md`, Punkt 3)
- KeePassXC-Sync-Hub (`docs/IDEA.md`, Punkt 6, Raspberry Pi)
- Test-Umgebungen für neue Konfigurationen
- Backup-Ziel

Der Cache-Container ist der **erste Schritt** in eine Richtung, in
der der Laptop nur noch ein Client ist und schwere Aufgaben auf
spezialisierte Systeme ausgelagert werden.

---

## 14. Abhängigkeiten

**Muss vorher existieren:**

- [ ] Proxmox-Host (Hardware + OS)
- [ ] Netzwerk zwischen Laptop und Proxmox
- [ ] Eco-System-Repo mit `hosts/`-Struktur (ist vorhanden)

**Kann parallel laufen:**

- [ ] Manifest-Format finalisieren
- [ ] Signing-Key generieren
- [ ] `hosts/cache/`-Struktur anlegen (Konzept → Code)

**Kann danach kommen:**

- [ ] Laptop-Config anpassen (Cache-URL eintragen)
- [ ] Fallback-Test: Container offline
- [ ] Retention-Skript für Cache
- [ ] Monitoring

---

Ende des Konzepts.
