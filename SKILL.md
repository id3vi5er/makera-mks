---
name: makera-mks
description: Liest, entpackt, bearbeitet und schreibt Makera-Studio-Projektdateien (.mks, CNC-CAM für Makera Z1/Carvera) – bytegenau. Verwenden, wenn eine .mks gelesen, analysiert, als JSON/SVG ausgegeben, verändert (Layer, Vektoren, Rohling, Werkzeugweg-Parameter) oder neu erzeugt werden soll, oder wenn nach dem Aufbau von makera.bin / makera.prj / scene_v3 gefragt wird.
---

# Makera Studio `.mks` lesen und schreiben

## Kernfakten

- `.mks` = ZIP mit `makera` (leer), `makera.bin` (Binär-Szenengraph `scene_v3`), `makera.prj`
  (Qt-JSON, CRLF), optional `prjImg.png`. Komplette Spezifikation: `reference/FORMAT.md` (deutsch: `reference/FORMAT.de.md`).
- Das Format stammt aus dem Schreibcode von `MakeraStudio.exe` 0.1.2.0, nicht aus Raten.
  Verifiziert: 36 echte Projekte lesen → schreiben **bytegenau** (bin, prj und über das JSON-Abbild);
  neu erzeugte Dateien laden in Makera Studio korrekt.
- Bibliothek `scripts/mks.py` (nur Python-Standardbibliothek), CLI `scripts/mks_tool.py`.
- Originale des Nutzers **nur lesen**. Immer in eine neue Datei schreiben, nie das Original
  überschreiben.

## CLI

```bash
S=~/.claude/skills/makera-mks/scripts
python $S/mks_tool.py info    datei.mks [--max 5]     # Rohling, Layer, Werkzeugwege, Baum
python $S/mks_tool.py extract datei.mks ordner [--b64] # project.json + scene.json + prjImg.png
python $S/mks_tool.py pack    ordner neu.mks           # zurück zur .mks (warnt bei kaputten uuid-Bezügen)
python $S/mks_tool.py svg     datei.mks bild.svg [--coord 0] [--toolpaths]
python $S/mks_tool.py verify  datei.mks|ordner ...     # Roundtrip-Selbsttest
```

`scene.json` ist der Baum mit Geometrie als Zahlenlisten (`positions [[x,y,z]…]`, `indices`, …);
mit `--b64` kompakt als Base64 (bei großen Dateien, 15 MB bin → sonst ~4× so groß als JSON).
`project.json` ist `makera.prj` unverändert als JSON; `pack` schreibt es wieder im Qt-Stil.

## Python-API

```python
import sys, os; sys.path.insert(0, os.path.expanduser("~/.claude/skills/makera-mks/scripts"))
import mks

p = mks.load("datei.mks")              # Project(prj=dict, scene=Scene, png)
root, pc = mks.coordinate(p, 0)         # bin-Knoten + prj-Eintrag der Aufspannung "0"
for n, m in mks.iter_nodes(root):       # alle Knoten mit akkumulierter Matrix
    segs = mks.segments(n, m)           # Liniensegmente (mode 1) in Werkstück-mm

# neu
p = mks.new_project("demo", stock=(150, 100, 1.5))          # TOP + Layer1, Makera Z1
lay = mks.find_layer(p, "Layer1")
lay.children.append(mks.polyline_node([(10, 10), (60, 10), (60, 40), (10, 40)]))
lay.children.append(mks.polyline_node(mks.circle_points(90, 50, 15)))
lay2 = mks.add_layer(p, "Bohrungen", "#d05ae7")              # trägt bin UND prj ein
mks.save(p, "demo.mks")
```

Koordinaten: Ursprung = linke untere Ecke der Rohling-Oberseite, mm, Z = 0 auf der Oberfläche.
`iter_nodes(root)` liefert für die Kinder bereits die Matrix des Koordinatenknotens
(-L/2, -B/2, H/2) mit – für Werkstückkoordinaten über `root.children` iterieren
(so macht es `svg`).

## Regeln beim Schreiben

1. **Name und uuid nie leer.** Makera schreibt leere Strings ohne Länge; der Leser läuft dann aus dem Takt.
   `mks.save` bricht in dem Fall ab.
2. **bin und prj gemeinsam pflegen.** Layer-uuid steht in `images[].list_meshes_uuids`,
   Koordinatenknoten-uuid in `lstCoordinate[i].uuid`, bearbeitete Vektoren in `path[].selectedmeshes`,
   berechnete Wege in `path[].gcodemeshuuidmap` (Knoten type 4 in `axis_items`).
   Neue Layer daher mit `add_layer`, nicht nur als Knoten.
3. **Werkzeugwege nicht selbst erfinden.** Neue Vektoren ohne Pfad schreiben; Makera berechnet die Wege
   per „Add Toolpath“/„Generate Toolpath“. Bestehende Pfad-Parameter (Tiefe, Werkzeug, Vorschub) in
   `project.json` ändern ist möglich, die zugehörigen type-4-Knoten sind dann aber veraltet → in Makera
   „Recalculate“.
4. Vektoren: `mode=1` (GL_LINES, Segmentpaare), Material `MeshInstanceLineMaterial` in Layerfarbe.
5. Nach dem Schreiben `verify` auf die neue Datei und – wenn möglich – in Makera Studio öffnen:
   `"<Installationsordner>\MakeraStudio.exe" "<pfad>"` (Ordner: `InstallLocation` von „Makera Studio“
   in der Windows-Deinstallationsliste, Standard `%LOCALAPPDATA%\Programs\Makera Studio`)
   (Einzelinstanz: lädt die Datei in das offene Fenster; ungespeicherte Änderungen dort gehen verloren).

## Fallstricke

- Felder `i520` (und `stepOverMM` in der prj) enthalten uninitialisierten Speicher – Zufallswerte sind normal.
- Die bin kann mehr `CoordinateN` enthalten als die prj nennt (alte Aufspannungen); maßgeblich ist die uuid.
- Nur `scene_v3`; `scene`/`scene_v2` (ältere Makera-Versionen) werden abgelehnt.
- Der `group`-Abschnitt war in allen Beispielen leer; der Leser liest den optionalen Schlüssel heuristisch.
- Ändert eine neue Makera-Version das Format, schlägt `verify` fehl. Dann neu ableiten wie in
  `reference/FORMAT.md` beschrieben (Writer über das 8-Byte-Immediate `scene_v3` in der EXE finden,
  fwrite-Aufrufe der Objekt-Serialisierung lesen; RTTI-Namen `.?AV…@@` helfen).
