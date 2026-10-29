# P2P-Cache-Konzept: Transport-Schicht für Nix

> Status: Konzeptphase / Zukunftsmusik
> Ersteller: luisek03
> Datum: 2026-10-03
> Bezug: Eco-System, `docs/CACHE-SERVER-CONCEPT.md`
> Kontext: Nix vermischt Transport und Vertrauen. Diese Trennung ist
>          für dezentrale Verteilung hinderlich.

---

## 1. Kerngedanke

Nix' Binär-Cache-Modell vermischt zwei Dinge:

- **Transport** — die Bytes eines Pakets von A nach B bringen
- **Vertrauen** — sicher sein, dass die Bytes echt sind

In `cache.nixos.org` kommen Narinfo (Signatur) und NAR (Bytes) vom
selben Server. Wer die Bytes liefert, sagt auch, was sie sind. Das ist
bequem, aber verhindert dezentrale Verteilung.

Die Beobachtung: **NAR-Dateien sind bereits inhaltsadressiert.**
Der Store-Pfad ist ein SHA-256-Hash des Inhalts. Diese Eigenschaft
macht sie von Natur aus verteilbar — genau wie BitTorrent-Chunks.

Der P2P-Cache nutzt das aus: **Narinfos kommen aus vertrauenswürdigen
Quellen. NAR-Bytes können von überall kommen.** Die Verifikation
macht Nix — gestützt auf die signierte Narinfo.

---

## 2. Die entscheidende Mechanik

Nix lädt Pakete in zwei Schritten:

1. **GET `<cache>/<hash>.narinfo`** — signierte Metadaten
   (NarHash, NarSize, References, Signatur)
2. **GET `<cache>/nar/<nar-hash>.nar`** — die eigentlichen Bytes

**Verifikation:**
- Nix prüft die Signatur der Narinfo gegen `trusted-public-keys`.
- Nix berechnet den Hash der NAR und vergleicht mit `NarHash` aus der
  signierten Narinfo.
- Erst bei Übereinstimmung wird die NAR in `/nix/store` entpackt.

**Konsequenz:** Die Narinfo muss aus einer vertrauenswürdigen Quelle
kommen. Die NAR kann aus jeder Quelle kommen, deren Bytes zum Hash
passen. Nix verwirft falsche Bytes automatisch.

**Das ist die ganze Idee.** Der P2P-Cache muss die Narinfo durchreichen
und die NAR aus dem P2P-Netz ziehen. Nix macht den Rest.

---

## 3. Architektur

Der P2P-Cache ist ein **HTTP-Server, der sich als Binary-Cache ausgibt**.
Nix merkt nicht, dass das Backend P2P ist.

    [Nix auf dem Laptop]
           │
           │ GET /<hash>.narinfo   ← direkte Weiterleitung
           │ GET /nar/<hash>.nar   ← aus P2P
           ▼
    [P2P-Proxy auf 127.0.0.1:8080 oder LAN-IP]
           │
           ├─ narinfo → Upstream (cache.nixos.org o.ä.)
           │
           └─ nar → P2P-Netzwerk
                     (BitTorrent, IPFS, eigenes Protokoll)
                     Bytes holen, Hash prüfen, liefern

**Zwei Betriebsmodi:**

| Modus | Wo | Zweck |
|-------|-----|-------|
| `local` | 127.0.0.1 | Nur dieses System. Bytes werden aus dem lokalen Store geteilt, ohne Netzwerk. Spart nichts, macht aber den Proxy einfach testbar. |
| `lan` | LAN-IP | Mehrere Rechner im LAN teilen ihren Store. Klassischer Anwendungsfall. |
| `internet` | öffentliche IP | Peers über das Internet. Benötigt NAT-Traversal, DHT, etc. |
| `hybrid` | beides | Peers aus LAN und Internet parallel. |

**Rekursion:** Ein P2P-Cache kann andere P2P-Caches als Peers nutzen.
So entsteht eine Hierarchie: kleiner Cache im Laptop → Cache im LAN
→ Cache im Internet → offizielle Quellen.

---

## 4. Vertrauensmodell

**Der P2P-Layer ist nicht vertrauenswürdig.** Er ist Transport.

Die Vertrauenskette bleibt intakt:

    Signierter Key (aus cache.nixos.org o.ä.)
        ↓
    Signierte Narinfo
        ↓
    NarHash in der Narinfo
        ↓
    NAR-Bytes (egal woher)
        ↓
    Nix prüft Hash → Store

**Kein unverifizierter Zustand in `/nix/store`.** Was dort liegt, wurde
entweder lokal gebaut oder aus einer verifizierten Narinfo bezogen.

Der P2P-Layer hat einen eigenen Zwischenspeicher **außerhalb** des
Nix-Stores. Was dort liegt, ist „pending" — wartend auf Verifikation
durch Nix. Wenn der Hash nicht passt, wird es verworfen.

**Damit ist der P2P-Cache kein Sicherheitsrisiko.** Er kann falsche
Bytes liefern, Nix erkennt es und bricht ab. Er kann schadhafte
Narinfos liefern, Nix erkennt es an der Signatur.

---

## 5. Netzwerkprofile

Der P2P-Cache kennt verschiedene Umgebungen und verhält sich
unterschiedlich.

| Umgebung | Erlaubte Quellen | Upload-Limit | Download-Limit |
|----------|------------------|--------------|----------------|
| Heimnetz | LAN + Internet | 10 MB/s | unbegrenzt |
| Arbeit | LAN + Internet | 1 MB/s | 10 MB/s |
| Mobiles Netz | Internet (gedrosselt) | 100 KB/s | 1 MB/s |
| Offline | nur lokaler Store | — | — |
| 127.0.0.1 | nur lokaler Store | — | — |

**Profilauswahl:** automatisch per Interface-Erkennung (SSID, Gateway)
oder manuell per Config.

**Fallback-Kette im Proxy selbst:** wenn P2P nichts liefert → direkter
Upstream-Cache (cache.nixos.org etc.). Der Proxy ist transparent für
Nix, aber er entscheidet, woher er die Bytes holt.

---

## 6. Heuristischer Cache

Der P2P-Cache soll **selbst entscheiden**, was er lokal vorhält.

**Regeln (konfigurierbar):**

- **Speicherlimit:** Wenn der Cache-Store über 80 % ist, werden die
  am seltensten angefragten Pakete gelöscht.
- **Timer:** Tägliche Bereinigung, unabhängig von Speicherdruck.
- **Häufigkeit:** Pakete mit hoher Anfragefrequenz werden bevorzugt
  behalten.
- **Alter:** Pakete, die seit N Tagen nicht angefragt wurden, werden
  gelöscht.
- **Ausnahmen:** Manuell markierte Pakete werden nie gelöscht.

**Caching komplett deaktivieren:** Im `local`-Modus (127.0.0.1) kann
Caching abgeschaltet werden. Das System weiß am besten, was es
braucht, und der P2P-Cache dient nur als Proxy ohne eigenen Store.

**GC-Verantwortung:** Der Nix-GC bleibt beim System. Der P2P-Cache
hat seinen eigenen GC-Mechanismus für seinen **eigenen** Speicher,
greift aber nie in `/nix/store` ein. Was das System nicht mehr
braucht, räumt das System selbst weg.

---

## 7. Was fehlt in Nix und warum es trotzdem geht

**Was Nix nicht hat:**
- Keinen expliziten „unverifizierten" Zustand im Store
- Keine P2P-Transport-Schicht
- Keine Trennung von „Narinfo-Quelle" und „NAR-Quelle"

**Warum der Proxy-Ansatz funktioniert:**

Weil Nix bereits verifiziert — nur nicht, wenn die Bytes vom selben
Server kommen. Der Proxy nutzt die bestehende Verifikationslogik,
indem er Narinfo und NAR aus verschiedenen Quellen liefert.

Nix' Vertrag lautet: „Wenn du mir eine signierte Narinfo gibst und
die Bytes dazu passen, akzeptiere ich sie." Der Proxy hält diesen
Vertrag ein — er liefert nur Narinfos, deren Signatur stimmt, und
NARs, deren Hash passt.

**Der Preis:** Der Proxy muss selbst sicherstellen, dass er keine
falschen NARs weitergibt — nicht wegen Nix, sondern weil Nix die
schlechten sonst abweist und die Anfrage neu startet. Der Proxy
verwirft falsche Chunks, bevor er sie ausliefert.

---

## 8. Langfristige Vision

Das P2P-Cache-Projekt ist ein eigenes Vorhaben, das in Eco-System
integriert wird, sobald es stabil ist.

**Stufe 1 — Konzept und Prototyp**
- Proxy in Python
- Narinfo-Weiterleitung + NAR-Passthrough zum offiziellen Cache
- Test: Proxy läuft auf 127.0.0.1, Nix nutzt ihn transparent

**Stufe 2 — Eigenes P2P-Protokoll**
- Peer-Discovery im LAN (mDNS)
- Chunk-basiertes Teilen (BitTorrent-inspiriert)
- Eigener P2P-Daemon (Rust oder Python)

**Stufe 3 — Internet-Peers**
- DHT für Peer-Discovery
- NAT-Traversal
- Verschlüsselung (optional, da Bytes ohnehin verifiziert werden)

**Stufe 4 — Heuristischer Cache**
- Speicherverwaltung
- Frequenz-basierte Retention
- Netzwerkprofile

**Stufe 5 — Integration in Eco-System**
- Als Default-Substituter in `nix.settings`
- Zusammen mit `cachyos-kernel.nix` und `nyx-cache`
- Fallback auf offizielle Caches bleibt

---

## 9. Beziehung zu anderen Eco-System-Konzepten

| Konzept | Verhältnis |
|---------|-----------|
| [`CACHE-SERVER-CONCEPT.md`](CACHE-SERVER-CONCEPT.md) | Der P2P-Cache kann ein Cache-Server-Peer sein oder selbst einer. |
| [`RESCUE-CONCEPT.md`](RESCUE-CONCEPT.md) | Der Rescue-Mode könnte den P2P-Cache im LAN nutzen, um Kernel-Pakete zu beziehen. |
| `cachyos-kernel.nix` | Kann den P2P-Cache als Fallback nutzen, wenn Nyx/Mic92 den Kernel nicht haben. |
| `features/ops` | Keine direkte Kopplung. `eco-update` nutzt, was in `nix.settings` steht. |

---

## 10. Offene Punkte

- [ ] Sprache: Rust oder Python? (Rust wegen Performance und
  BitTorrent-Bibliotheken; Python wegen schneller Entwicklung)
- [ ] Protokoll: BitTorrent (libtorrent) oder eigenes?
- [ ] Peer-Discovery: mDNS im LAN, DHT im Internet, oder beides?
- [ ] Verschlüsselung: nötig oder redundant, da Nix ohnehin verifiziert?
- [ ] Speicherort: `/var/cache/p2p-nix/` oder eigener Pfad?
- [ ] Umgang mit Peer-Ausfällen: Timeout, Blacklist, oder automatischer
  Fallback?
- [ ] Wie wird der Proxy beendet? systemd-Unit mit Watchdog?
- [ ] Konfiguration: Nix-Modul oder eigene TOML/YAML?
- [ ] Integration in Nix: reiner Substituter oder spezieller
  `--option`-Pfad?
- [ ] Sicherheitsmodell: Angriffe auf Peer-Discovery, Traffic-Analyse?
- [ ] Wie verhält sich der Proxy bei mehreren Stores auf demselben
  System?

---

## 11. Nicht-Ziele

- Kein Ersatz für offizielle Caches
- Kein Public-P2P-Netz für die NixOS-Community
- Kein Fork von Nix
- Keine Änderung an `/nix/store`
- Keine Änderung an Nix' Vertrauensmodell

---

## 12. Philosophie

Der P2P-Cache folgt der Eco-System-Logik: **Kontrolle durch
Eigentum**, kombiniert mit **Flexibilität durch Dezentralität**.

Er löst ein konkretes Problem (Build-Zeit sparen, Pakete
wiederverwenden), ohne die Sicherheit zu opfern. Die
Vertrauenskette bleibt intakt, weil Nix weiterhin die Wahrheit
prüft. Der P2P-Layer ist reiner Transport.

**Das ist die richtige Trennung:** Transport ist ein Problem der
Netzwerktopologie. Vertrauen ist ein Problem der Kryptographie.
Nix sollte nur eines davon lösen müssen.

---

## 13. Realistische Einschätzung

Das ist **kein Wochenendprojekt**. Realistisch:

- Konzept und Prototyp: mehrere Wochen
- Stabiler Daemon: Monate
- Internet-fähig: Monate mehr
- Integration in Eco-System: danach

**Der Nutzen** ist hoch, sobald mehrere Geräte im Spiel sind.
Für einen einzelnen Laptop ist der Nutzen gering — der Store
hat ohnehin alles, was er zuletzt gebraucht hat.

**Der eigentliche Wert** entsteht, wenn:
- Mehrere Geräte denselben Kernel brauchen
- Häufig neu gebaut wird (Rust-Toolchain, Kernel-Updates)
- Bandbreite knapp ist oder mehrere Nutzer parallel bauen
- Vertrauenswürdige Peers im LAN existieren

Für das Eco-System ist das ein **späterer Baustein**. Nicht jetzt,
nicht dieses Jahr. Aber wert, festgehalten zu werden.

---

Ende des Konzepts.
