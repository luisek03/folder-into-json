# GC-Priority-Konzept: Priorisiertes Store-Aufräumen

> Status: Konzeptphase / Zukunftsmusik
> Ersteller: luisek03
> Datum: 2026-10-03
> Bezug: Eco-System, `docs/CACHE-SERVER-CONCEPT.md`, `modules/features/ops/gc-collect.py`
> Kontext: `nix-collect-garbage` ist ein Alles-oder-Nichts-Werkzeug.
>          Es kennt keine Prioritäten und löscht den nix-shell-Cache
>          genauso wie veraltete Versionen.

---

## 1. Kerngedanke

Der heutige GC (`nix-collect-garbage`) löscht **jeden** Store-Pfad, der
durch keinen Root erreichbar ist. Keine Differenzierung. Keine
Priorität. Kein Schutz für Dinge, die nur selten gebraucht werden.

Das ist für einen Store, der als Cache dienen soll (nix-shell,
wiederkehrende Builds), zu grob.

Die Idee: **Ein priorisierter Löscher, der vor dem klassischen GC
läuft.** Er löscht gezielt die offensichtlich veralteten Versionen —
und schont alles andere. Erst wenn das nicht reicht, übernimmt der
klassische GC.

**Der Vorteil:** Kein Tracking, kein Overhead im Normalbetrieb.
Nur begrenzte, statische Informationen — und die reichen für eine
grobe Schätzung.

---

## 2. Das Modell

### 2.1 Pro-Paket, nicht global

Nicht: „Lösche die ältesten N Store-Pfade."
Sondern: **„Lösche von jedem Paket die älteste Version, wenn eine
neuere existiert."**

Beispiel:

    firefox-140.14.0esr       → löschen (156.0, 156.0.1, 157.0 existieren)
    firefox-156.0             → löschen (156.0.1, 157.0 existieren)
    firefox-156.0.1           → löschen (157.0 existiert)
    firefox-157.0             → behalten (neueste)
    python3.13-requests-2.32.3 → behalten (einzige Version)
    openssl-3.5.0             → behalten (einzige Version)
    openssl-3.4.0             → löschen (3.5.0 existiert)

### 2.2 Warum so

Ohne Zugriffs-Tracking (atime ist deaktiviert, wäre auch unzuverlässig)
haben wir nur eine Handvoll Informationen:

- **Paketname und Version** (aus dem Store-Pfad)
- **Wie viele Versionen** es gibt
- **Wie lange** der Pfad im Store liegt
- **Ob ein Root** darauf zeigt

Aus diesen ableiten wir eine **Priorität**: Was hat die geringste
Wahrscheinlichkeit, noch gebraucht zu werden?

Die Antwort: **Nicht-neueste Versionen eines Pakets, das neuere hat.**

Denn:
- Wenn `firefox-157.0` da ist, wird `firefox-140esr` nicht mehr
  aufgerufen — es sei denn, es ist explizit durch einen Root
  erreichbar (alte Generation).
- Die neueste Version bleibt immer. Wenn sie alt wird, wird sie
  trotzdem nicht gelöscht, weil kein Vergleich zu etwas Neuerem.
- Einzelversionen werden nie priorisiert gelöscht — sie sind der
  Schutz für nix-shell-Pakete, die selten geupdated werden.

---

## 3. Die Heuristik

### 3.1 Pname- und Version-Extraktion

Ein Store-Pfad sieht so aus:

    /nix/store/<hash>-<name>-<version>
    /nix/store/<hash>-<name>-<version>-<output>

Beispiele:

    /nix/store/abc123-firefox-157.0
    /nix/store/def456-firefox-unwrapped-157.0
    /nix/store/ghi789-python3.13-requests-2.32.3
    /nix/store/jkl012-linux-6.18.50

Die Heuristik: **Der letzte Bindestrich, dem eine Ziffer folgt,
trennt Version von Name.**

```
firefox-157.0             → pname=firefox,               version=157.0
firefox-unwrapped-157.0   → pname=firefox-unwrapped,     version=157.0
python3.13-requests-2.32.3 → pname=python3.13-requests,  version=2.32.3
linux-6.18.50             → pname=linux,                 version=6.18.50
```

### 3.2 Grenzen der Heuristik

**Fall 1: Sprachversionen im Pname**

`python3.13-requests` und `python3.12-requests` sind verschiedene
Pnames — sie gruppieren sich nicht. Das ist konservativ, weil sie
unabhängige Abhängigkeitsbäume haben. Kein Problem, nur weniger
Löschpotential.

**Fall 2: Kernel-Varianten**

`linux-6.18.50` und `linux-cachyos-6.18.50` haben verschiedene Pnames.
Gruppieren sich nicht. Auch konservativ.

**Fall 3: Outputs**

`<pkg>-dev`, `<pkg>-bin`, `<pkg>-lib` sind separate Store-Pfade mit
denselben Pname. Sie werden **einzeln** behandelt, nicht als eine
Gruppe. Das führt dazu, dass manchmal `-dev` der neueren Version
wegfällt, aber `-bin` bleibt. Nicht ideal, aber harmlos — das
nächste `nix-collect-garbage` räumt die Reste.

**Fall 4: `.drv`-Dateien und Tarballs**

`firefox-157.0.drv` und `firefox-157.0.source.tar.xz` haben keine
klare Version im Namen. Sie werden als eigene Pnames behandelt
und bleiben am Leben, bis sie unreachable werden.

### 3.3 Fazit

Die Heuristik ist gut genug für **„offensichtlich veraltet zuerst"**.
Sie ist nicht perfekt. Deshalb ist der Fallback auf den klassischen
GC unverzichtbar.

---

## 4. Die Datenbank

### 4.1 Zweck

Speichert `first_seen` pro Store-Pfad — den Zeitpunkt, an dem der
Pfad zum ersten Mal im Store beobachtet wurde.

**Warum nicht `mtime`?**
`mtime` von Store-Pfaden sagt nur, wann der Pfad angelegt wurde.
Das ist meist identisch mit dem Build-Zeitpunkt. Bei einem Store,
der über Jahre wächst, ist die mtime nach Neubau eines Pakets neu —
der Pfad kann schon da sein, bevor der Neubau passierte. `first_seen`
gibt uns die **Beobachtungszeit**, nicht die Bauzeit.

**Wozu brauchen wir es?**
Als **Tiebreaker** bei gleicher Priorität. Zwei `openssl`-Versionen
haben dieselbe Pname-Gruppe, aber unterschiedliche `first_seen` —
die ältere wird zuerst gelöscht.

### 4.2 Schema (SQLite, Skizze)

```sql
CREATE TABLE store_paths (
    path TEXT PRIMARY KEY,
    pname TEXT NOT NULL,
    version TEXT,
    first_seen INTEGER NOT NULL,   -- Unix timestamp
    last_scan INTEGER NOT NULL     -- Unix timestamp
);

CREATE INDEX idx_pname ON store_paths(pname);
CREATE INDEX idx_first_seen ON store_paths(first_seen);
```

**Größenordnung:** ~30.000 Pfade × 100 Byte = **~3 MB**.

### 4.3 Ort

Vorschlag: `/var/lib/eco-gc/store.db`.

Warum nicht `/nix/store`: Der Store ist nicht der richtige Ort für
Verwaltungs-Metadaten. `/var/lib/eco-gc` ist Standard für solche DBs.
Liegt außerhalb des Stores, ist nicht vom GC betroffen.

### 4.4 Scan-Ablauf

Ein Lauf pro Tag (oder bei jedem `eco-gc-collect`-Aufruf):

1. `ls /nix/store` → alle aktuellen Pfade
2. Für jeden Pfad:
   - Pname/Version parsen
   - Wenn nicht in DB: einfügen mit `first_seen = jetzt`
   - Wenn in DB: `last_scan` aktualisieren
3. Pfade in DB, die **nicht mehr im Store** sind → aus DB entfernen
   (wurden durch vorherigen GC gelöscht)

Der Scan dauert 2–5 Sekunden für 30.000 Pfade. Kein `du`, kein
`stat`. Nur Liste + Parsing + SQLite-Schreibvorgänge.

---

## 5. Die Root-Prüfung

### 5.1 Warum

Vor jedem `nix store delete` prüfen wir, ob der Pfad einen Root hat:

```bash
nix-store --query --roots /nix/store/<pfad>
```

Mögliche Roots:

- `/nix/var/nix/profiles/system-<N>-link` (Generation)
- `/nix/var/nix/profiles/per-user/<user>/...` (User-Profile)
- `/tmp/nix-shell-*` (offene nix-shell-Sessions)
- `<cwd>/result` (nix build Symlink)
- `/proc/<pid>/fd/<n>` (laufende Prozesse)

### 5.2 Verhalten

- **Keine Ausgabe** → Pfad löschbar
- **Irgendein Root** → Pfad überspringen, nächster Kandidat

Das ist konservativ. Der klassische GC in Stufe 2 würde den Pfad
sowieso nicht löschen (weil er erreichbar ist), aber wir sparen uns
den Fehler von `nix store delete` und bekommen saubere Logs.

---

## 6. Ablauf in `eco-gc-collect`

Erweiterung der aktuellen Logik. Der priorisierte Löscher läuft
**zwischen** der Disk-Messung und dem klassischen GC.

```
1. Disk messen
   if current < start-percent: return 0

2. Priorisierter Löscher
   a. DB öffnen / initialisieren
   b. Scan durchführen (siehe 4.4)
   c. Kandidaten markieren:
      - Für jeden Pname: alle Versionen außer der neuesten
      - Sortierung innerhalb Kandidaten: ältestes first_seen zuerst
   d. Für jeden Kandidaten:
      - Root-Check
      - Wenn rooted: überspringen
      - Sonst: nix store delete <pfad>
   e. Disk messen
   if current <= target-percent: return 0

3. Klassischer GC
   nix-collect-garbage
   Disk messen
   if current <= target-percent: return 0

4. Iteration
   if iteration < max-iterations: goto 2
   else: return 3 (target nicht erreicht)
```

**Wichtig:** Der priorisierte Löscher (Schritt 2) läuft auch dann,
wenn der klassische GC (Schritt 3) später sowieso nötig ist. Der
Sinn: Die harmlosen, offensichtlich veralteten Pfade zuerst weg,
bevor die aggressivere Methode greift.

---

## 7. Was der priorisierte Löscher schützt

- **Neueste Version jedes Pakets** — egal wie alt
- **Einzelversionen** — keine neuere zum Vergleich
- **Rooted Pfade** — Generationen, nix-shells, aktive Prozesse
- **`/nix/store/*-dev`, `*-bin`, `*-lib`** von der neuesten Version

## Was er löscht

- **Ältere Versionen** eines Pakets, das neuere hat
- **Tarballs und `.drv`-Dateien** älterer Versionen (falls als
  eigene Pnames erkannt)
- **Nicht gerootete Pfade**, die dem Pname-Muster folgen

---

## 8. Bekannte Grenzen

### 8.1 Kein Zugriffs-Tracking

Wir wissen nicht, ob ein Pfad in einer nix-shell aktiv genutzt wird.
Nur der Root-Check fängt offene nix-shells — geschlossene nicht.

**Konsequenz:** Selten genutzte nix-shell-Pakete können beim
priorisierten Löschen wegfallen, wenn eine neuere Version existiert.
Das ist der Preis. Der Nutzer kann einzelne Pakete schützen (siehe
8.4).

### 8.2 Pname-Heuristik nicht perfekt

Python-Sprachversionen, Kernel-Varianten, `-dev`/`-bin`-Suffixe
werden getrennt behandelt. Das ist konservativ, aber nicht optimal.
Für einen ersten Ansatz reicht es.

### 8.3 Kein Wissen über „Was wird gerade gebaut"

Wenn parallel ein Build läuft, dessen Store-Pfade gerade entstehen,
könnte der priorisierte Löscher sie theoretisch als „alt" markieren.
Der Root-Check fängt das ab — solange der Builder den Pfad als
Root registriert hat. Bei `nix build` ja, bei `nix-shell`-Zwischen-
ständen manchmal nicht.

**Mitigation:** Der priorisierte Löscher läuft **nur** wenn
`eco-gc-collect` getriggert wird — was selten ist (Disk über 85 %).
Ein paralleler Build zu diesem Zeitpunkt ist unwahrscheinlich.

### 8.4 Manuelle Ausnahmen

Irgendwann sinnvoll: Eine Whitelist von Pnames, die nie priorisiert
gelöscht werden. Z. B.:

    /etc/eco-gc/protect.chp
    python3.13-numpy
    python3.13-scipy
    openssl

Wird im Konzept nicht implementiert, aber als Option vorgesehen.

---

## 9. Fallback-Logik

### 9.1 Wenn die DB fehlt

Erster Lauf nach Installation:

- DB wird angelegt
- Alle Pfade bekommen `first_seen = jetzt`
- Der priorisierte Löscher hat keine Historie — kann aber anhand
  der Versionen trotzdem arbeiten

Der erste priorisierte Lauf löscht also genauso wie später. Nur
der Tiebreaker (first_seen) fehlt.

### 9.2 Wenn der Algorithmus nicht reicht

Nach Stufe 2 (priorisierter Löscher) und Stufe 3 (klassischer GC)
kann das Target noch immer nicht erreicht sein. Gründe:

- Alle Kandidaten waren rooted (durch Generationen geschützt)
- Der Store hat wenige Pakete mit mehreren Versionen
- Die Disk ist durch andere Daten voll

Dann greift Iteration bis `max-iterations`. Am Ende:

- **Exit 0** — Ziel erreicht
- **Exit 3** — Ziel nicht erreicht, kein Fehler (klassischer Fall)

Konsistent mit der aktuellen `gc-collect.py`-Semantik.

### 9.3 Wenn die DB beschädigt ist

Bei SQLite-Fehler:

- Fehler loggen
- DB umbenennen (`store.db.broken.<timestamp>`)
- Neu anfangen (wie 9.1)
- Nächster Lauf arbeitet mit frischer DB

Der priorisierte Löscher funktioniert auch ohne DB, nur ohne
`first_seen`-Tiebreaker.

---

## 10. Vorteile gegenüber klassischem GC

| Aspekt | Klassisch | Priorisiert |
|--------|-----------|-------------|
| Selektivität | Keine | Pro-Paket |
| nix-shell-Schutz | Keiner | Neuere Versionen bleiben |
| Geschwindigkeit (Aufwand) | Vollständiger Graph-Durchlauf | Pname-Parsing + Root-Check |
| Speicherbedarf | Keine | ~3 MB DB |
| Rechenaufwand | Sekunden bis Minuten | Sekunden bis Minuten |
| Verhalten bei Target-Miss | Endgültig | Iterativ, mit Fallback |
| Zusätzliche Komplexität | Keine | DB + Heuristik |

Der priorisierte Löscher ersetzt den klassischen GC **nicht**.
Er kommt davor, um die harmlosen Fälle abzuräumen, und lässt den
Rest dem Standard-Mechanismus.

---

## 11. Philosophie

Das Konzept folgt der Eco-System-Logik: **Erhaltung was nützlich
ist, Löschung was veraltet ist.** Kein Tracking, weil Tracking
selbst Overhead bedeutet und NixOS keinen atime führt. Nur die
Informationen, die der Store bereits liefert — Pfadname, Version,
Zeitstempel.

Aus diesen rekonstruieren wir eine **Wahrscheinlichkeits-Schätzung**
für die Nutzung. Nicht perfekt, aber ausreichend für eine erste
Sortierung. Was übrig bleibt, geht an den klassischen GC. Die
Kombination ist robuster als jede der beiden Methoden allein.

---

## 12. Offene Punkte

- [ ] **DB-Format:** SQLite oder JSON oder etwas anderes?
- [ ] **DB-Ort:** `/var/lib/eco-gc/` oder woanders?
- [ ] **Scan-Frequenz:** Bei jedem `eco-gc-collect` oder täglicher
      systemd-Timer?
- [ ] **Pname-Heuristik verfeinern:** Python-Versionen, `-dev`,
      `-bin` explizit behandeln?
- [ ] **Whitelist:** Soll es eine Schutzliste geben? Wo?
- [ ] **Integration in `eco-gc-collect`:** Erweiterung der
      `gc-collect.py` oder eigenes Skript, das aufgerufen wird?
- [ ] **Reporting:** Log-Format für gelöschte Pfade — einfach oder
      strukturiert (JSON)?
- [ ] **Migration:** Wenn DB erst später eingeführt wird, wie
      initialisieren wir `first_seen`? (Vorschlag: „jetzt" für alle)
- [ ] **Konflikte mit gleichzeitigem Build:** Lock nutzen oder
      Timing abwarten?
- [ ] **Größenlimitierung:** Wächst die DB unbegrenzt? Soll alte
      Einträge (Pfade, die seit N Tagen nicht im Store sind)
      automatisch gelöscht werden?
- [ ] **`nix store delete`-Performance:** Bei 1000 Aufrufen — kann
      man sie batchen?
- [ ] **Wie umgehen mit `.drv`-Dateien, die zu gelöschten Quellen
      gehören?**

---

## 13. Nicht-Ziele

- Kein Ersatz für `nix-collect-garbage`
- Kein Zugriffs-Tracking (atime, inotify, ...)
- Kein globales „ältestes zuerst"
- Keine aggressive Löschung von Einzelversionen
- Kein Ersatz für manuelle Ausnahmen (Whitelist ist separate Idee)
- Keine Runtime-Messung oder Nutzungsanalyse

---

## 14. Realistische Einschätzung

Die Idee ist **gut genug für einen ersten Ansatz**, aber nicht
perfekt. Sie löst das konkrete Problem: „nix-shell-Cache wird vom
GC ohne Rücksicht gelöscht". Sie löst es nicht für alle Fälle —
selten genutzte Einzelversionen bleiben, häufige alte Versionen
mit neuerer Variante fliegen.

Der Aufwand: **~200–300 Zeilen Python** für die DB-Verwaltung,
den Scan, den priorisierten Löscher und die Integration in
`gc-collect.py`. Plus Tests. Realistisch **1–2 Wochenenden**.

Der Nutzen: **Mittel.** Bei einem System mit einem einzigen Host
ist der Gewinn überschaubar. Bei mehreren Hosts (Laptop, Desktop,
Rescue) mit geteiltem Store-Verhalten wird der Nutzen deutlich.

**Für jetzt:** Konzept festhalten. Umsetzung erst, wenn der
klassische GC tatsächlich an seine Grenzen stößt — z. B. wenn
nix-shell-Pakete verloren gehen, die noch gebraucht würden.

---

Ende des Konzepts.
