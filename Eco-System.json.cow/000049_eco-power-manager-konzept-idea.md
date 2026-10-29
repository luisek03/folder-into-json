# Idee: Eco-Power-Manager

> Status: Idee / niedrige Priorität
> Ersteller: luisek03
> Datum: 2026-09-27
> Bezug: Eco-System, zukünftiger Hyprland-Workspace
> Überarbeitet: D-Bus als primärer Ansatz, Race-Condition-Handling, UI-Integration

---

## Kernidee

Ein eigener Userspace-Wrapper für Energieprofile, der beliebig viele,
frei definierbare Profile erlaubt — pro Host oder als Default.

Jedes Profil ist eine Sammlung von Aktionen, die beim Aktivieren
ausgeführt werden. Die Aktionen sind nicht auf einen festen Satz
beschränkt, sondern können alles enthalten, was per Skript steuerbar
ist:

- CPU-Governor ändern
- Scheduler toggeln (z.B. BORE an/aus)
- Lüfterkurven setzen (via CoolerControl o.ä.)
- Backlight / Display-Helligkeit
- Programme starten, beenden oder pausieren
- Netzwerk, Bluetooth, andere Dienste
- Eigene Skripte

## Warum nicht power-profiles-daemon oder tuned

- `power-profiles-daemon`: feste drei Profile, keine Hooks, kein
  Skript-Support
- `tuned`: mächtiger, aber immer noch festes Profilmodell, keine
  freie Logik
- Beide sind für Standardfälle gedacht, nicht für kreative Nutzung

Der Eco-Power-Manager ist bewusst kein Ersatz, sondern eine eigene
Schicht, die auf die Bedürfnisse des Eco-Systems zugeschnitten ist.

## Beispielprofile

- **saver** — CPU auf `powersave`, BORE aus, Lüfter limitiert,
  Hintergrundprogramme pausiert
- **balanced** — Standard, alles normal
- **performance** — CPU auf `performance`, BORE an, Lüfter frei
- **silent** — volle Leistung erlaubt, aber Lüfter-RPM hart
  begrenzt (z.B. nie über 60%)
- **max** — Lüfter permanent 100%, CPU moderat übertaktet
- **custom-<host>** — pro Gerät eigene Profile, z.B. für Laptop
  mit Akku-Schonung oder Desktop mit OC

Die Liste ist offen. Der Nutzer entscheidet, was er braucht.

### Modus-Struktur (Meta-Ebene)

Die Beispielprofile oben sind **Bausteine**, die je nach Modus
kombiniert werden. Die Meta-Ebene besteht aus genau drei statischen
Modi, die exklusiv sind:

- **saver** — alles auf Energiesparen
- **performance** — alles auf maximale Leistung
- **gamemode** — performance + Gaming-Hooks

Ein vierter Modus, **dynamic**, ist ein Container: In ihm können
prozess-gebundene Profile registriert werden, die per Priorität
entscheiden, welcher Zustand gilt. Die Meta-Ebene kann durch die
Dynamik nicht überschrieben werden.

Siehe auch: Abschnitt „Zwei-Ebenen-Modell" weiter unten.

## Zwei-Ebenen-Modell

Der Eco-Power-Manager unterscheidet strikt zwischen einer **Meta-Ebene**
und einer **Dynamik-Ebene**. Diese Trennung stellt sicher, dass die
statischen Modi nicht durch Laufzeit-Profile überschrieben werden können
und umgekehrt die Dynamik nicht aus dem Ruder läuft.

### Meta-Ebene: Statische Modi

Die Meta-Ebene besteht aus drei (optional vier) Modi, die **exklusiv**
sind. Genau einer ist aktiv. Ihre Werte sind fest verdrahtet und können
von nichts überschrieben werden:

| Modus         | Charakter | Werte (Beispiel)                                       |
|---------------|-----------|--------------------------------------------------------|
| `saver`       | statisch  | `sched_bore=0`, Governor `powersave`, Dienste niedrig  |
| `performance` | statisch  | `sched_bore=1`, Governor `performance`, Dienste normal |
| `gamemode`    | statisch  | wie `performance` + Gaming-spezifische Hooks           |
| `dynamic`     | Container | siehe Dynamik-Ebene                                    |

Ein Wechsel zwischen diesen Modi ist ein bewusster globaler Akt. Er
passiert entweder per CLI (`eco-power switch saver`) oder per Keybind.

### Dynamik-Ebene: Prozess-gebundene Profile

Die Dynamik-Ebene ist **nur innerhalb des `dynamic`-Modus aktiv**. Sie
kann die Meta-Ebene nicht überschreiben. Innerhalb von `dynamic` gilt:

- Jedes `eco-power run --profile=X -- cmd` registriert ein Profil mit
  einer **Priorität**.
- Der Dienst berechnet aus allen aktiven Profilen den **effektiven
  Zustand**: Das Profil mit der **höchsten Priorität gewinnt**.
- Wenn das höchste Profil endet, fällt das System auf das nächsthöhere
  zurück.
- Wenn kein Profil aktiv ist, greift der **Default** (`saver` oder
  `balanced`).

### Prioritätslogik

Die Priorität ist eine einfache Ordnungsrelation: **Größere Zahl =
höhere Priorität.** Das ist intuitiver als die umgekehrte nice-Logik,
weil der Nutzer bei der Definition eines Profils sofort sieht, welches
„stärker" ist.

| Profil        | Priorität |
|---------------|-----------|
| `saver`       | 10        |
| `balanced`    | 50        |
| `performance` | 90        |
| `gamemode`    | 100       |

### Kein Diff, sondern vollständiges Anwenden

Bei jeder Neuberechnung wird der Zielzustand des **höchstpriorisierten**
Profils **vollständig** angewendet. Es wird **nicht** die Differenz zum
vorherigen Zustand berechnet. Der Grund: Der Diff-Ansatz erfordert die
korrekte Rekonstruktion des vorherigen Zustands und ist fehleranfällig,
wenn ein einzelner Wert nicht sauber zurückgesetzt wird. Das
vollständige Anwenden ist **idempotent** — der Zielzustand ist
unabhängig von der Vorgeschichte.

### Warum kein Lease-/Refcount-Modell

Ein früherer Entwurf sah vor, dass jedes Profil eine Art „Lease"
erwirbt und der Dienst per Reference-Counting entscheidet, wann ein
Profil deaktiviert wird. Dieses Modell wurde verworfen, weil:

- Die Konflikt-Auflösung bei mehreren gleichzeitig aktiven Profilen
  komplex und fehleranfällig ist.
- Refcounting bei asynchron endenden Prozessen zu schwer
  reproduzierbaren Zuständen führt.
- Die Abhängigkeits-Hölle zwischen Profilen, die sich gegenseitig
  beeinflussen, nicht beherrschbar ist.

Das Zwei-Ebenen-Modell mit fester Priorität ist einfacher, robuster
und leichter zu erklären.

---

## Architektur: D-Bus als Kern

Der Eco-Power-Manager wird als D-Bus-Dienst umgesetzt. Das ist der
sauberste und flexibelste Ansatz aus mehreren Gründen.

### Warum D-Bus

- **Standardisiertes IPC**: Jede Sprache, jedes Tool kann den
  Dienst ansprechen. Kein Lockfile-Handling, kein Socket-Pfad-
  Management, kein State-File-Polling.
- **Signale für UI**: Waybar, Hyprland und andere Clients können
  auf Profilwechsel reagieren, ohne zu pollen.
- **On-Demand-Aktivierung**: Über systemd `Type=dbus` startet der
  Dienst erst, wenn ihn jemand anspricht. Im Leerlauf verbraucht
  er null Ressourcen — kein laufender Prozess, kein Polling.
- **Reihenfolge garantiert**: D-Bus-Methodenaufrufe werden seriali-
  siert. Zwei schnelle Aufrufe hintereinander werden in Reihenfolge
  ausgeführt, nicht parallel. Race Conditions sind damit strukturell
  ausgeschlossen.

### Der Dienst

Ein kleiner Prozess, der auf dem Session-Bus lauscht (User-Level).
Privilegierte Aktionen (Governor, `sched_bore`, Lüfterkurven)
laufen über einen separaten systemd-System-Service mit passenden
Rechten, angesprochen per System-Bus. So bleibt der User-Dienst
schlank und die Privilegien sind sauber getrennt.

Alternativ: ein einziger Dienst auf dem System-Bus, der über
PolicyKit-Autorisierung (polkit) die Erlaubnis einholt. Für ein
Single-User-System ist das meist Overkill — der Split in User- und
System-Dienst ist einfacher.

### D-Bus-API (Skizze)

**Methoden:**

- `ListProfiles() -> as` — Namen aller verfügbaren Profile
- `GetActiveProfile() -> s` — aktuell aktives Profil
- `SwitchProfile(s name) -> ()` — wechselt das Profil
- `ReloadProfiles() -> ()` — Profile aus dem Verzeichnis neu laden

**Signale:**

- `ProfileSwitching(s name)` — Wechsel beginnt (UI kann blockieren)
- `ProfileChanged(s name)` — Wechsel erfolgreich abgeschlossen
- `SwitchFailed(s name, s reason)` — Wechsel fehlgeschlagen

**Properties:**

- `ActiveProfile` (read)
- `Switching` (read) — true während eines Wechsels

### On-Demand über systemd

    [Unit]
    Description=Eco-Power-Manager D-Bus service

    [Service]
    Type=dbus
    BusName=org.eco.PowerManager
    ExecStart=/run/current-system/sw/bin/eco-powerd
    Nice=19
    IOSchedulingClass=idle
    # User-Service, daher keine root-Rechte nötig

    [Install]
    WantedBy=default.target

Der Dienst startet, wenn der erste D-Bus-Aufruf kommt, und beendet
sich nach Inaktivität (Idle-Timeout). Damit ist "läuft im
Hintergrund" nicht mehr als ein Name im D-Bus-Namensraum — keine
CPU, kein RAM, nichts.

---

## Race-Condition-Handling

D-Bus serialisiert Methodenaufrufe bereits. Zwei schnelle
`SwitchProfile`-Aufrufe werden in Reihenfolge ausgeführt. Der
zweite wartet, bis der erste fertig ist.

Trotzdem sind zwei zusätzliche Maßnahmen sinnvoll:

### 1. Expliziter Lock im Dienst

Der Dienst hält während eines Profilwechsels einen `flock` auf
einer Lock-Datei. Falls ein zweiter Prozess (z.B. ein direkt
aufgerufenes Skript) versucht, parallel zu schalten, wird er
entweder:

- **blockiert** (Standardverhalten), oder
- **mit Fehler abgewiesen** (per `LOCK_NB`)

Die Wahl hängt vom Aufrufer ab: Die UI kann warten, ein CLI-Aufruf
kann abweisen, um den Nutzer nicht zu blockieren.

### 2. Idempotenz der Profile

Jedes Profil setzt **alle** Werte, die es braucht — unabhängig
davon, was vorher aktiv war. Es verlässt sich nicht auf einen
bestimmten Ausgangszustand.

Beispiel: Ein `saver`-Profil setzt Governor auf `powersave`,
Scheduler auf `sched_bore=0`, Lüfterlimit auf Wert X, pausiert
Programme Y, Z. Es prüft nicht, ob diese Werte schon gesetzt sind.
Es setzt sie einfach. Dadurch ist es egal, ob vorher `balanced`,
`performance` oder gar nichts aktiv war.

Damit gibt es keinen halbfertigen Zustand, auch wenn ein Wechsel
mittendrin abgebrochen wird. Der nächste Wechsel setzt sauber auf.

## Prozess-Management und Cleanup

Profile werden über `eco-power run --profile=X -- cmd` an einen Prozess
gebunden. Der Lebenszyklus dieses Prozesses bestimmt, wann das Profil
aktiv ist und wann es wieder freigegeben wird.

### Der Wrapper als Elternprozess

Der Wrapper verwendet **fork + wait**, nicht `exec`. Das ist
entscheidend: Nur so gibt es einen Elternprozess, der das Ende des
Kindes bemerkt und sich sauber abmelden kann.

```
┌─────────────────────────────────────────┐
│  eco-power run --profile=X -- blender   │
│  (Wrapper-Prozess, PID 5678)            │
└─────────────────────────────────────────┘
                    │
                    │ fork()
                    ▼
        ┌───────────────────────┐
        │  Kind-Prozess         │
        │  PID 1234             │
        │  exec("blender")      │
        └───────────────────────┘
                    │
                    │ waitpid()
                    ▼
        ┌───────────────────────┐
        │  Wrapper wartet       │
        │  auf Kind-Ende        │
        │  → unregister         │
        └───────────────────────┘
```

Ablauf:

1. Der Wrapper registriert sich beim Dienst mit **beiden PIDs**
   (eigene + Kind-PID) und beiden Startzeiten.
2. Er fork't.
3. Das Kind `exec`t das Zielprogramm.
4. Der Wrapper `waitpid`t auf das Kind.
5. Wenn das Kind endet, meldet der Wrapper sauber ab.

### Signal-Handling

Der Wrapper fängt `SIGTERM` und `SIGINT` ab, um auch bei einem `Ctrl+C`
oder `kill` sauber abmelden zu können:

1. Signal empfangen.
2. `SIGTERM` an das Kind senden.
3. Kurze Frist (z. B. 5 s) auf sauberes Ende warten.
4. Falls nötig: `SIGKILL` an das Kind.
5. In **jedem Fall** `UnregisterProfile` aufrufen, bevor der Wrapper
   sich beendet.

### Der Registry-Eintrag

Der Dienst speichert pro aktivem Profil:

```python
{
    "profile": "performance",
    "priority": 90,
    "child_pid": 1234,
    "child_starttime": "12345678",
    "wrapper_pid": 5678,
    "wrapper_starttime": "12345670",
    "wrapper_failed": False,
}
```

Beide Startzeiten werden aus `/proc/PID/stat` (Feld 22) gelesen. Das
ist der Schutz gegen PID-Reuse: Ein neuer Prozess mit derselben PID hat
praktisch nie dieselbe Startzeit.

### Das zweistufige Cleanup-Modell

| Mechanismus                    | Trigger                    | Geschwindigkeit | Abdeckung                |
|--------------------------------|----------------------------|-----------------|--------------------------|
| **Primär: Sauberes Abmelden**  | Wrapper fängt Kind-Ende ab | Sofort          | Normalfall               |
| **Sekundär: Watchdog**         | systemd-Timer (1 min)      | bis zu 60 s     | `kill -9`, OOM, Absturz  |

Im **Normalzustand** läuft das Cleanup über den Wrapper: Kind endet →
`waitpid` kehrt zurück → D-Bus `UnregisterProfile` → Dienst entfernt
Eintrag sofort. Der Watchdog ist **nicht** beteiligt.

Im **Fehlerzustand** (Wrapper tot, Kind lebt oder umgekehrt) übernimmt
der Watchdog.

### Die Watchdog-Logik

Der Watchdog prüft bei jedem Lauf **beide** Prozesse:

| Kind     | Wrapper  | Bedeutung                       | Aktion                                    |
|----------|----------|---------------------------------|-------------------------------------------|
| ✅ lebt  | ✅ lebt  | Normalzustand                   | Nichts                                    |
| ❌ tot   | ✅ lebt  | Wrapper hat Tod nicht bemerkt   | Unregister                                |
| ✅ lebt  | ❌ tot   | Wrapper abgestürzt/gekillt      | `wrapper_failed = True`, Eintrag behalten |
| ❌ tot   | ❌ tot   | Beide tot                       | Unregister                                |

Das `wrapper_failed`-Flag ist **diagnostisch**: Es protokolliert, dass
ein Wrapper versagt hat, und hilft, Muster zu erkennen. Es ändert nicht
das Verhalten des Watchdogs, weil dieser sowieso beide PIDs prüft.

### PID-Reuse-Schutz

Das Problem: PIDs werden wiederverwendet. Wenn ein Prozess mit `kill -9`
beendet wird und der Watchdog noch nicht gelaufen ist, könnte ein neuer
Prozess zufällig dieselbe PID bekommen. Der Watchdog würde dann
fälschlich annehmen, der alte Prozess lebe noch.

Die Lösung: Beim Registrieren wird die **Startzeit** des Prozesses aus
`/proc/PID/stat` (Feld 22, in Clock-Ticks seit Boot) gespeichert. Beim
Check vergleicht der Watchdog die aktuelle Startzeit mit der
gespeicherten. Wenn sie abweicht, ist es ein anderer Prozess.

```python
def get_starttime(pid):
    with open(f"/proc/{pid}/stat") as f:
        fields = f.read().split()
    return fields[21]  # 22. Feld, 0-indiziert
```

Das ist einfach, in ~10 Zeilen Python implementiert und deckt 99,9 %
der Fälle ab.

### Watchdog-Intervall

Der Timer läuft standardmäßig **jede Minute**. Bei typischerweise 0–3
aktiven Profilen ist der Check trivial. Der Watchdog berechnet den
effektiven Zustand **nur dann neu**, wenn sich die Registry tatsächlich
geändert hat — das vermeidet unnötige Sysctl-Schreibvorgänge.

### Was der Watchdog nicht abdeckt

Der einzige Fall, den kein Mechanismus abdeckt, ist: **Beide Prozesse
leben, aber der Wrapper hat einen Bug und meldet nicht ab, obwohl das
Kind tot ist.** Diesen Fall fängt der Watchdog ab, weil er
`child_alive = False` sieht und aufräumt. Der Wrapper bleibt dann als
Zombie oder läuft weiter, aber das Profil ist korrekt entfernt.

---

## UI-Integration in Hyprland

### Waybar-Modul

Ein Waybar-Modul zeigt das aktive Profil an. Bei Klick öffnet sich
ein Auswahlmenü.

Verhalten während eines Wechsels:

- Empfängt `ProfileSwitching(name)` per D-Bus-Signal
- **Graut den Schalter aus** (disabled state)
- Zeigt optional einen Spinner oder Text "Wechsle zu <name>…"
- Nach `ProfileChanged(name)` wird der neue Zustand angezeigt und
  der Schalter wieder aktiv

Der Nutzer kann während eines laufenden Wechsels keinen neuen
auslösen — die UI blockiert das visuell. Ein Doppelklick auf
verschiedene Profile ist damit ausgeschlossen.

### Keybindings

Statische Keybindings für die häufigsten Profile:

    bind = $mod, F1, exec, eco-power saver
    bind = $mod, F2, exec, eco-power balanced
    bind = $mod, F3, exec, eco-power performance

`eco-power` ist ein dünner CLI-Client, der per D-Bus mit dem Dienst
spricht. Er ist nicht der Dienst selbst — nur ein Wrapper.

### CLI-Client

    eco-power list                # zeigt alle Profile
    eco-power current             # zeigt aktives Profil
    eco-power switch <name>       # wechselt (wartend)
    eco-power switch -f <name>    # wechselt (ohne Wartezeit, Fehler bei busy)
    eco-power watch               # folgt Profilwechseln live

Der CLI-Client ist eine hauchdünne Schicht über D-Bus. Wer will,
kann direkt `busctl` oder `dbus-send` nutzen — der Dienst ist
öffentlich dokumentiert.

---

## Konfiguration der Profile

Jedes Profil ist eine ausführbare Datei (Bash, Python, was auch
immer) in einem festgelegten Verzeichnis:

    ~/.config/eco-power/profiles/
    ├── saver.sh
    ├── balanced.sh
    ├── performance.sh
    ├── silent.sh
    └── max.sh

Der Dienst liest den Dateinamen als Profilnamen und ruft das Skript
bei Aktivierung auf. Das Skript bekommt keine Argumente — es setzt
alles selbst, was es braucht.

Wer will, kann Profile auch in Nix deklarieren und über das
Eco-System-Repo verteilen — die Struktur ist offen.

---

## Priorität

**Niedrig.**

Gründe:

- Der aktuelle `power-profiles-daemon` funktioniert ausreichend
- Kein akutes Problem, das gelöst werden muss
- Der Manager ist ein Komfortfeature, kein Rettungsanker
- Sinnvoll erst, wenn Hyprland als Desktop läuft und der
  Workspace insgesamt steht
- Vorher gibt es wichtigeres: Generation 0 (Rescue), Sandboxing,
  Testprofile, Stabilität des Hauptsystems

Der Manager kann als eigenes kleines Projekt angegangen werden,
wenn die größeren Bausteine des Eco-Systems fertig sind.

## Nicht-Ziele

- Kein Ersatz für `power-profiles-daemon` auf System-Ebene
- Kein Kernel-Modul
- Kein Hardware-Treiber
- Kein dauerhaft laufender Prozess mit Ressourcenverbrauch
  (On-Demand per systemd `Type=dbus`)

---

## Was noch zu klären ist

- [ ] Name des D-Bus-Interface (`org.eco.PowerManager`)
- [ ] Split User-/System-Bus oder nur System-Bus mit polkit?
- [ ] Idle-Timeout des Dienstes (z.B. 5 min)?
- [ ] Format der Profilnamen (frei, mit Prefix, versioniert)?
- [ ] Rückgängig-Mechanismus (was, wenn ein Profilwechsel fehlschlägt)?
- [ ] Logging (journal, eigene Datei, beides)?
- [ ] Waybar-Modul: eigenes Skript oder bestehendes Modul nutzen?
- [ ] Optionale Profile aus Nix generieren, oder alle in `.sh`?
- [ ] Wie werden Profile aktiviert, die anderen Nutzern gehören?
- [ ] Prioritätsrichtung: Größere Zahl = höhere Priorität (empfohlen)
      oder nice-Logik (niedrigere Zahl = höher)?
- [ ] Watchdog-Intervall: 1 min, 2 min, 5 min?
- [ ] Wrapper-Signal-Frist: Wie lange auf sauberes Kind-Ende warten,
      bevor `SIGKILL`?
- [ ] PID-Check: Nur Startzeit, oder zusätzlich Prozessname?
- [ ] `systemd-run --scope` als Alternative zum eigenen Watchdog?
- [ ] Soll der `dynamic`-Modus einen eigenen Namen bekommen
      (z. B. `auto`), um Verwechslung mit „dynamisch" zu vermeiden?

---

Ende der Idee.
