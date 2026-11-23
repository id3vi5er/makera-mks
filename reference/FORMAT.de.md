# Makera Studio `.mks` – Dateiformat

*[English](FORMAT.md) | Deutsch*

Rekonstruiert am 23.11.2026 aus Makera Studio **0.1.2.0** (`MakeraStudio.exe`, Qt5 + eigene
Three.js-artige Engine „TinyOGL“). Die Quelle ist der Schreibcode in der EXE (Writer `0x1401a8950`,
Objekt-Serializer `0x140191620`, Loader `0x1401a1590`). Geprüft an 36 echten Projekten
(2D-Fräsen, PCB-Isolationsfräsen, STEP-Modelle, SVG-/Gerber-Importe, mehrere Aufspannungen):

* `makera.bin` → Parser → Writer: **36/36 byte-identisch**
* `makera.prj` → JSON → Writer: **36/36 byte-identisch**
* Über das JSON-Abbild (`mks_tool.py extract` → `pack`): **36/36 byte-identisch**
* Neu erzeugte Datei und neu verpackte Kopie laden in Makera Studio korrekt.

Code: `../scripts/mks.py` (Bibliothek), `../scripts/mks_tool.py` (CLI: info/extract/pack/svg/verify).

## 1. Container

Eine ZIP-Datei (Deflate). Makera schreibt sie mit quazip (Zip64-Felder, Data Descriptor);
ein normales ZIP aus Python wird ebenfalls gelesen. Einträge in dieser Reihenfolge:

| Eintrag      | Inhalt |
|--------------|--------|
| `makera`     | leer (0 Byte), Kennung |
| `makera.bin` | Szenengraph, Binärformat `scene_v3` (Abschnitt 3) |
| `makera.prj` | Projekt-JSON: Rohling, Maschine, Layer, Werkzeugwege (Abschnitt 2) |
| `prjImg.png` | Vorschaubild (optional, fehlt in manchen Dateien) |

## 2. `makera.prj`

`QJsonDocument::toJson(Indented)`: UTF-8, **CRLF**, 4 Leerzeichen Einzug, Schlüssel
alphabetisch, leere Objekte/Listen als `{` Zeilenumbruch `}`. Ganzzahlige Doubles stehen
ohne Nachkommastellen, andere in kürzester Darstellung (wie Python `repr`). Einige Felder
enthalten uninitialisierten Speicher (z. B. `stepOverMM: 4.54e-312`, `lastUpdateDate: "\u0000"`).

Wichtige Teile unter `project`:

* `stStockInfo`: Rohling (`length`, `width`, `height` in mm, `StockShape`, Material, `materialspec`).
* `machine`: Maschine (Z1: 200×200×100, `maxRPM`, `maxFeedRate`).
* `lstCoordinate`: Dict `"0"`, `"1"`, … je **Aufspannung/Seite** (`name` z. B. `TOP`), mit
  * `uuid`: uuid des passenden Knotens `CoordinateN` in `makera.bin`
  * `images[]`: Layer bzw. importierte Dateien: `name`, `color` (`#rrggbb`), `type`
    (1 = Layer, 2 = importierte Grafik wie Gerber/SVG), `list_meshes_uuids` (uuid des Layer-Knotens
    in der bin), `showState`, `activeState`
  * `path[]`: Werkzeugwege. `type` 0 = 2D-Tasche, 1 = 2D-Kontur, 2 = Bohren, 7 = 3D-Tasche,
    8 = Ausschnitt, 9 = Gewinde. `selectedmeshes` = uuids der bearbeiteten Vektor-Knoten,
    `gcodemeshuuidmap` = uuids der berechneten Werkzeugweg-Knoten (in `axis_items`, siehe unten),
    `tools[]` (Werkzeug mit Drehzahl, Vorschub, Zustellung …), `depth`, `safe`, `tab`, `ramping`.
* `strProjectName`, `nSaveDate` (JJJJMMTT).

## 3. `makera.bin` (`scene_v3`)

Little-Endian, keine Ausrichtung. Grundtypen:

* `u32` / `i32` / `f32`, `u8` (bool, 0/1)
* `str` = `u32 länge` + UTF-8-Bytes. **Achtung:** Ist ein String leer, schreibt Makera *gar nichts*
  (auch keine Länge 0). Name und uuid eines Knotens dürfen also nie leer sein.
* `blob` = `u32 byteanzahl` + Bytes (Feld von f32/u32)

### Datei

```
str   "scene_v3"          (ältere Versionen: "scene", "scene_v2")
u32   nRoots
Node  roots[nRoots]       (je Aufspannung ein CoordinateN)
str   "group"
u32   nGroups
  u32 nMembers
    str key               (nur wenn nicht leer)
    i32 index             (-1 = nicht gefunden)
```

### Node (rekursiv)

```
str   name               Layer-/Objektname; bei Vektoren meist = uuid
str   uuid               36 Zeichen, Muster 8-4-4-4-12 aus [A-Za-z0-9]
f32   matrix[16]         4×4, spaltenweise (Translation in [12..14]), mm
u32   hasGeometry
u32   nChildren
u32   type               Knotentyp, siehe unten
[u32  nAxisItems]        nur bei type == 8
u8    visible
i32   i520               uninitialisiert (Zufallswerte) – beliebig, 0 schreiben
u8    b13                (1 bei importierten Dateien/STEP-Wurzeln)
i32   i360               (STEP-Faces: Anzahl Flächen)
i32   i364               meist -1
u32   nInts, i32 ints[nInts]
if hasGeometry:
  u32  mode              1 = GL_LINES (Segmentpaare), 4 = GL_TRIANGLES
  blob positions         f32 xyz je Vertex
  blob normals           f32 xyz (bei Linien (0,1,0))
  blob uvs               f32 uv
  blob colors            f32 rgb (darf leer sein)
  blob indices           u32
  if type == 4:
    str  geoClass        "GCodeGeometry" oder "PlaneGeometry"
    if geoClass == "GCodeGeometry":
      blob gcodeData     i32 je Vertex (beobachtet: erster Wert 1, Rest 0; Bedeutung ungeklärt)
  u8   flag              (1 bei STEP-Faces)
  blob extra             f32 je Vertex (STEP-Faces: Flächen-ID als float)
  str  materialName      MeshBasicMaterial, MeshInstanceLineMaterial, GCodeMaterial, …
  f32  color[3]          RGB 0..1
  f32  color2[3]         RGB 0..1 (meist gleich color)
  u32  hasTexture
  if hasTexture == 1:
    u32 width, u32 height, u32 channels (=4)
    blob pixels          width*height*4 Bytes RGBA
Node  children[nChildren]
Node  axisItems[nAxisItems]   nur bei type == 8
```

### Knotentypen (`type`)

| type | Bedeutung | Material | in der Szene |
|------|-----------|----------|--------------|
| 8    | Koordinatensystem `CoordinateN` (AxisNodeMesh), eines je Aufspannung | – | Wurzel |
| 256  | Layer / importierte Datei (Gruppe) | – | Kind von 8 |
| 2    | Vektorpfad (Polylinie als Liniensegmente) | MeshInstanceLineMaterial / MeshBasicMaterial | Kind von 256 |
| 128  | Vektor (z. B. Text/Füllung) | MeshBasicMaterial | Kind von 256 |
| 4    | berechneter Werkzeugweg `gcode_polyline` | GCodeMaterial | `axisItems` von 8 |
| 64   | Mesh (STL o. ä.) | MeshPhongMaterial | |
| 1024 | STEP-Modell (Wurzel ohne Geometrie, Kind „Faces“) | MatcapMaterial | |
| 2048 | STEP-Kanten „Edges“ | StepBoundaryMaterial | |

Die Matrix von `CoordinateN` ist (-Länge/2, -Breite/2, Höhe/2): Ursprung des Werkstücks
links unten auf der Oberseite, die Szene liegt mittig. Vektor-Koordinaten in den Kindern sind mm
in diesem System (Z = 0 auf der Oberfläche, Werkzeugwege mit negativem Z).

### Zusammenhang bin ↔ prj

* `lstCoordinate[i].uuid` ↔ uuid des Wurzelknotens `CoordinateN`
* `images[].list_meshes_uuids` ↔ uuid eines Layer-Knotens (type 256)
* `path[].selectedmeshes` ↔ uuids von Vektor-Knoten (type 2/128)
* `path[].gcodemeshuuidmap` ↔ uuids der Werkzeugweg-Knoten (type 4) in `axisItems`

## 4. Offene Punkte

* Bedeutung von `i360`, `i364`, `ints`, `flag`, `extra` nur aus Beobachtung, nicht aus der Engine benannt.
* `group`-Abschnitt war in allen Dateien leer; der Leser behandelt den optionalen Schlüssel heuristisch.
* Ältere Formate `scene`/`scene_v2` werden nicht gelesen.
* Werkzeugwege werden beim Schreiben nicht berechnet: neue Dateien enthalten nur Vektoren; Makera
  berechnet die Wege per „Generate Toolpath“.

## 5. Format neu ableiten (falls eine neue Makera-Version es ändert)

Vorgehen vom 23.11.2026, ohne Ghidra/IDA:

1. Python-venv mit `capstone` und `pefile`.
2. Writer finden: `scene_v3` steht im Code als 8-Byte-Immediate (`48 b8 73 63 65 6e 65 5f 76 33`,
   `movabs rax, 'scene_v3'`). Funktionsgrenzen über `.pdata` (Exception-Directory); Achtung,
   lange Funktionen sind in mehrere `.pdata`-Einträge zerlegt → weiter disassemblieren bis `ret`.
   Der Loader vergleicht `scene_v3` per `lea` auf den String in `.rdata`.
3. Alle Schreibzugriffe gehen über `fwrite(ptr, size, count, FILE*)` (IAT-Slot `0x14149eeb8` in 0.1.2.0):
   `edx` = Elementgröße, `r8` = Anzahl. Die Reihenfolge dieser Aufrufe ist das Format.
4. Die Objekt-Serialisierung hängt an einer `std::function` (Lambda-vtable, Slot `+0x10`).
   Rekursion über die Kinder läuft über dieselbe `std::function`.
5. `__RTDynamicCast`-Aufrufe tragen RTTI-Typdeskriptoren (`.?AVMesh@@`, `.?AVGCodeGeometry@@`,
   `.?AVMeshBasicMaterial@@` …) – damit sind Sonderfälle je Klasse lesbar.
6. Ergebnis immer mit `mks_tool.py verify` gegen echte Dateien prüfen (Ziel: bytegenau).
