# Rescue-Mode-Konzept: Generation 0

> Status: Konzeptphase / Zukunftsmusik
> Ersteller: luisek03
> Datum: 2026-09-27
> Bezug: NixOS-Flakes, Eco-System-Repo
> Überarbeitet: Abkehr von "Specialisation" hin zu fester Generation 0

---

## 1. Kerngedanke

Der Rescue-Modus ist keine zusätzliche Generation, die bei jedem
Deploy mitgebaut wird. Er ist eine eigene, feste "Generation 0",
die:

- nicht vom Garbage Collector gelöscht werden kann
- über die flake.lock fest gepinnt ist
- nur manuell aktualisiert wird
- bei Bedarf neu gebaut und installiert wird
- so schlank wie möglich bleibt
- unabhängig vom Hauptsystem funktioniert

Damit ist er kein bewegliches Ziel wie das Hauptsystem, sondern ein
stabiler Anker, der sich nur ändert, wenn der Nutzer es will.

---

## 2. Grundproblem: Warum nicht einfach doppelte Generation?

Der naheliegende Ansatz wäre, bei jedem Deploy eine zweite
Generation oder eine Specialisation mit zweitem Kernel zu bauen.
Das ist aus mehreren Gründen für das Eco-System falsch.

### 2.1 Speicherkosten

Jeder zusätzliche Kernel mit Modulen und initrd belegt etwa 200 MiB
im Store. Bei jedem Deploy entsteht eine neue Generation, jede trägt
diesen Overhead. Nach zehn Deploys hat man zwei Gigabyte nur für
doppelte Kernel, die keiner braucht, solange das System läuft.

Auf einem Laptop mit begrenzter SSD und einem Nutzer, der sein
System bewusst leichtgewichtig halten will, ist das inakzeptabel.

### 2.2 CPU- und Bauzeit-Kosten

Jeder zusätzliche Kernel bedeutet bei jedem Deploy zusätzlichen
Buildaufwand — wenn nicht lokal, dann Downloadzeit und Store-
Wachstum. Auf einem schwachen Laptop summiert sich das. Und der
Nutzer baut sein System häufig um, weil es in aktiver Entwicklung
ist.

### 2.3 GC-Druck

Ein größerer Store bedeutet, dass die automatische GC-Schwelle
(früher getriggert) erreicht wird. Mehr Store = mehr Aufräumen =
mehr gelöschte Generationen = höheres Risiko, dass der Fallback
selbst irgendwann weggeräumt wird.

### 2.4 Config-Komplexität

Zwei Kernel oder zwei Configs bedeuten zwei Dinge, die im Takt
bleiben müssen. Wenn der Hauptkernel auf CachyOS umgestellt wird,
muss die Fallback-Variante mit angepasst werden. Wenn BORE
dazukommt, muss die zweite Variante das auch wissen. Jeder Fehler
hier zeigt sich erst, wenn man den Fallback wirklich braucht — dem
denkbar schlechtesten Moment.

### 2.5 Philosophische Unschärfe

Der Fallback sollte gerade das sein, was sich NICHT verändert.
Ein Fallback, der bei jedem Deploy mitwächst, ist kein Fallback,
sondern eine zweite Version des Hauptsystems. Damit hat man die
Komplexität verdoppelt, ohne die Sicherheit eines stabilen
Rettungspunkts zu gewinnen.

---

## 3. Lösung: Generation 0 als eigenständiger Anker

### 3.1 Eigenschaften

- **Eigene nixosConfiguration** in der flake.nix
- **Nicht Teil des normalen Deploys** — wird nur bei Bedarf gebaut
- **Eigene flake.lock** oder bewusst auf den gleichen Lock wie das
  Hauptsystem bezogen, aber manuell aktualisiert
- **Vom GC ausgenommen** durch Pinning
- **Klein und stabil** — ändert sich nur bei manueller Aktion

### 3.2 Warum "Generation 0"

Der Begriff drückt aus:

- Es ist die "erste" Generation, der Ursprung
- Es ist keine Zählgeneration wie 121, 122, 123
- Sie wird nicht durch Rebuilds ersetzt
- Sie dient als Ausgangspunkt, nicht als Iterationsprodukt

Sie könnte auch "Anker-Generation" oder "Basis-Generation"
heißen. "Generation 0" betont die Rolle als Fundament.

### 3.3 Pinning gegen GC

NixOS-GC arbeitet über Profile. Ein Profil-Symlink ist die Wurzel,
an der Generationen hängen. Der GC löscht alles, was von keiner
Profilwurzel mehr erreichbar ist.

Um Generation 0 zu pinnen:

- **Eigene Profil-Wurzel**: Der Rescue als eigenes Profil, das
  unabhängig vom System-Profil existiert
- **Explizite GC-Roots**: `/nix/var/nix/gcroots/` mit einem Symlink
  auf die Rescue-Generation
- **Store-Pfad pinnen**: Über `nix-store --add-root` oder äquivalent

Praktisch reicht ein Symlink unter `/nix/var/nix/gcroots/` auf den
Rescue-System-Pfad. Damit kann `nix-collect-garbage -d` ihn nicht
antasten, solange der Symlink existiert.

### 3.4 Update-Strategie

Anders als das Hauptsystem:

- Kein automatisches Update
- Kein Mitbauen bei Deploys
- Nur manuell, bewusst, zu einem gewählten Zeitpunkt

Ablauf beim Update:

1. Manuell: `nixos-rebuild switch --flake /etc/nixos#rescue`
2. Neue Rescue-Generation wird gebaut
3. Alter GC-Root-Symlink wird auf die neue Generation gesetzt
4. Alte Rescue-Generation kann beim nächsten GC verschwinden

Der Nutzer entscheidet, wann aktualisiert wird, und behält
dazwischen eine stabile Notfallumgebung.

---

## 4. Inhalt der Generation 0

### 4.1 Kernel

- NixOS-eigener LTS-Kernel (`pkgs.linuxPackages_lts`)
- Kein externer Flake-Input
- Kein CachyOS, kein BORE
- Läuft auf jeder x86_64-CPU
- Keine Cache-Abhängigkeit von Drittanbietern

### 4.2 Init und Basis

- systemd als Init (Standard, kein eigener /sbin/init)
- Kein Display Manager, kein X11, kein Wayland
- Mehrere TTYs für parallele Arbeit
- Eigener User `rescue` mit Autologin auf tty1

### 4.3 Feste Rettungswerkzeuge

Internet:

- NetworkManager
- wpa_supplicant
- curl, wget
- iproute2, iputils
- dnsutils

Speicher:

- parted, gptfdisk
- cryptsetup
- btrfs-progs, e2fsprogs, dosfstools, xfsprogs
- mount, lsblk, blkid, findmnt
- lvm2

Dateiarbeit:

- rsync
- vim, nano
- tar, zstd, gzip, xz, bzip2

Nix:

- nix, nixos-rebuild, git, jq
- nix-tree, nix-diff (optional)

Diagnose:

- htop, btop
- lsof, strace, iotop
- dmesg, journalctl
- smartmontools
- pciutils, usbutils

Sonstiges:

- openssh
- sudo
- man-db

### 4.4 Bewusst NICHT enthalten

- Browser (bei Bedarf per `nix-shell -p firefox`)
- Multimedia, Office
- Desktop-Umgebung
- Spiele
- Exotische oder spezialisierte Werkzeuge

### 4.5 Netzwerk

- Generisches DHCP-Profil
- Ethernet funktioniert ohne Konfiguration
- WLAN über NetworkManager manuell oder vordefiniert
- SSH an, mit dem persönlichen authorized_key
- Kein Passwort-Auth für SSH

### 4.6 User-Trennung

- Eigener User `rescue`
- Eigenes Home, entweder tmpfs (flüchtig) oder Subvolume
- Zugriff auf Hauptuser-Daten nur nach explizitem Mount
- Kein automatisches Durchsuchen der Hauptconfig

---

## 5. Rettungsstrategie im Betrieb

Stufenweise Eskalation:

    Stufe 1 — Alte Generation des Hauptsystems booten
              (systemd-boot, N-1, N-2, ...)

    Stufe 2 — Generation 0 booten
              (minimaler Userspace, Rettungstools)

    Stufe 3 — Live-USB aus Generation 0 bauen
              (falls Generation 0 nicht bootet, von anderem Gerät)

    Stufe 4 — Neuinstallation (letztes Mittel)

Generation 0 ist immer verfügbar, weil:

- Sie nicht durch Deploys ersetzt wird
- Sie nicht vom GC gelöscht wird
- Sie nicht durch Hauptsystem-Änderungen beeinflusst wird

---

## 6. Vorteile gegenüber anderen Methoden

### 6.1 Gegenüber doppelter Generation / Specialisation

| Kriterium | Doppelte Generation | Generation 0 |
|-----------|--------------------|--------------|
| Store-Kosten pro Deploy | +200 MiB | 0 |
| CPU-Kosten pro Deploy | +Build/Download | 0 |
| Config-Aufwand | Zwei Varianten pflegen | Eine Variante |
| GC-Druck | Höher | Neutral |
| Fehleranfälligkeit | Zwei Dinge synchron halten | Eine Sache fest |
| Rettungspunk-Stabilität | Bewegt sich mit | Fest gepinnt |
| Wann verfügbar | Nur solange Generation existiert | Immer |

Generation 0 gewinnt in jeder Kategorie außer der Bequemlichkeit
(manuell aktualisieren statt automatisch).

### 6.2 Gegenüber klassischem Rescue-USB

- Immer aktuell, weil im System gepflegt
- Nicht verlierbar
- Kein separater Stick nötig
- Kann bei Bedarf als USB exportiert werden

### 6.3 Gegenüber chroot von einem Live-System

- Ist selbst ein NixOS mit passender Umgebung
- Store ist direkt nutzbar
- Kein chroot-Chaos
- Nix-Befehle verhalten sich wie erwartet
- Kann das Hauptsystem direkt neu bauen

### 6.4 Gegenüber "nur alte Generation booten"

- Alte Generationen verschwinden irgendwann durch GC
- Alte Generationen teilen die Config-Fehler des Hauptsystems
- Bei Userspace-Problem keine echte Hilfe
- Bei Store-Problem keine Hilfe
- Generation 0 ist unabhängig und robust

### 6.5 Gegenüber Neuinstallation

- Erstversuch ist Reparatur, nicht Neuinstallation
- Config und Store bleiben erhalten
- Reparatur auf Nix-Ebene möglich
- Neuinstallation nur als letztes Mittel

---

## 7. Philosophie: Leichtgewicht als Feature

Das Eco-System ist bewusst leichtgewichtig. Nicht aus Geiz, sondern
weil zukünftige Features Ressourcen brauchen werden.

### 7.1 Warum Leichtgewicht wichtig ist

Geplante Features wie Sandboxing, reproduzierbare Build-Umgebungen,
mehrere parallele Python-Umgebungen, dedizierte Test-Profile oder
Cross-Device-Deployment kosten Speicher, CPU und Store. Ein System,
das bereits durch doppelte Kernel und redundante Fallbacks belastet
ist, hat für diese Features keinen Spielraum.

### 7.2 Leichtgewicht als Designprinzip

- Ein Kernel pro Generation, nicht zwei
- Eine Config pro Rolle, nicht zwei Varianten
- Keine automatischen Doppelbauten
- Pin nur wo nötig (Generation 0 ist der einzige Pin)
- Rettungsfunktionen schlank halten

### 7.3 Konsequenz für die Generation 0

Die Generation 0 ist absichtlich minimalistisch. Sie kostet einmalig
beim Bauen rund 300 MiB im Store. Danach nichts mehr, solange sie
nicht aktualisiert wird. Damit bleibt das Hauptsystem frei für die
Features, die wirklich wichtig sind.

---

## 8. Technische Bausteine (Zukunft)

### 8.1 Eigene nixosConfiguration

In der flake.nix:

    nixosConfigurations = {
      ${hostConfig.name} = ...;    # Hauptsystem
      default = ...;               # Alias
      rescue = nixpkgs.lib.nixosSystem {
        system = "x86_64-linux";
        modules = [ ./modules/rescue/configuration.nix ];
      };
    };

### 8.2 Rescue-Modul als wiederverwendbarer Baustein

Geplanter Pfad: `modules/rescue/`

Inhalt:

- `configuration.nix` — Minimal-Config
- `packages.nix` — Rettungswerkzeuge
- `user.nix` — rescue-User mit Autologin
- `network.nix` — generisches DHCP
- `gcroots.nix` — Pin-Mechanismus

### 8.3 GC-Root pinnen

Nach dem ersten Bau der Rescue-Generation:

    sudo ln -sf /nix/var/nix/profiles/system-rescue \
      /nix/var/nix/gcroots/rescue

Damit ist die Generation 0 fest gegen GC geschützt.

Alternativ über `nix-store --add-root` oder einen systemd-Path-Unit,
der den Symlink nach jedem Rescue-Build neu setzt.

### 8.4 Live-USB erzeugen

Über nixos-generators:

    nix build github:nix-community/nixos-generators -- \
      --flake /etc/nixos#rescue --format iso

Ergebnis: bootfähiges ISO für USB-Stick, unabhängig von jedem
installierten System.

---

## 9. Update-Ablauf der Generation 0

Manueller Vorgang, bewusster Zeitpunkt:

1. Entscheidung: "Ich will die Rescue-Umgebung aktualisieren"
2. Befehl ausführen: `deploy-rescue` (neuer Alias) oder direkt
   `sudo nixos-rebuild switch --flake /etc/nixos#rescue`
3. Neue Rescue-Generation wird gebaut und installiert
4. GC-Root-Symlink zeigt auf die neue Generation
5. Alte Generation kann beim nächsten GC verschwinden

Die Generation 0 wird **nicht** bei normalen Deploys mitgebaut.
Nur bei expliziter Anforderung.

---

## 10. Offene Punkte / zu klären

- [ ] Name des Rescue-Users (rescue, admin, notfall)?
- [ ] Persistenter Home oder tmpfs?
- [ ] Eigene Subvolume für Rescue-Home?
- [ ] Autologin oder Passwort?
- [ ] SSH im Rescue an oder aus?
- [ ] Automatisches Pinning oder manuell?
- [ ] Update-Intervall (jährlich, halbjährlich, bei Bedarf)?
- [ ] Wie wird die flake.lock für die Rescue-Config gehandhabt?
- [ ] Live-USB-Build als optionales Ziel oder als Standardfeature?
- [ ] Was passiert, wenn der Store komplett defekt ist?
- [ ] Soll Rescue-Config im Repo oder separat?
- [ ] Neuer Alias `deploy-rescue` für den manuellen Build?

---

## 11. Nicht-Ziele

- Kein Ersatz für regelmäßige Backups
- Kein vollständiges Zweitsystem
- Kein Desktop-Ersatz
- Kein automatisches Selbst-Repair
- Kein Netzwerk-Boot-Server
- Kein Mitbauen bei jedem Deploy
- Keine zweite Generation pro Rebuild

---

## 12. Philosophie

Die Generation 0 folgt derselben Philosophie wie das Hauptsystem,
aber mit umgekehrtem Fokus:

Hauptsystem:

- ändert sich häufig
- wird aktiv weiterentwickelt
- folgt den aktuellen Wünschen
- lebt

Generation 0:

- ändert sich selten
- wird manuell gepflegt
- bleibt stabil
- wartet

Beide sind deklarativ, im Repo, reproduzierbar. Nur ihre Rolle im
System ist unterschiedlich. Das Hauptsystem ist das bewegliche
Ziel, die Generation 0 ist der Anker.

---

Ende des Konzepts.