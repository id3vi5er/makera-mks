# makera-mks

*[English](README.md) | Deutsch*

Lesen, Entpacken, Bearbeiten und Schreiben von **Makera-Studio-Projektdateien (`.mks`)**, dem
CAM-Format für die Makera Z1 / Carvera. Bytegenau: Lesen und Zurückschreiben echter Projekte ergibt
dieselben Bytes; neu erzeugte Dateien öffnet Makera Studio wie eigene.

> Inoffiziell, nicht mit Makera verbunden. Das Format wurde aus Makera Studio 0.1.2.0 abgeleitet
> (Schreibroutine der EXE, siehe [`reference/FORMAT.de.md`](reference/FORMAT.de.md)). Spätere Versionen können es ändern –
> `mks_tool.py verify` zeigt das sofort.

## Inhalt

| Datei | Zweck |
|---|---|
| `scripts/mks.py` | Bibliothek: `load`/`save`, Szenengraph, Hilfen zum Erzeugen (`new_project`, `add_layer`, `polyline_node`, …) |
| `scripts/mks_tool.py` | CLI: `info`, `extract`, `pack`, `svg`, `verify` |
| `reference/FORMAT.de.md` | Formatbeschreibung (`makera.bin` „scene_v3“, `makera.prj`, Container) – [English](reference/FORMAT.md) |
| `SKILL.md` | Anleitung als [Claude-Code-Skill](https://docs.claude.com/en/docs/claude-code/skills) |
| `tests/test_selftest.py` | Selbsttest ohne fremde Dateien |

## Schnellstart

```bash
python scripts/mks_tool.py info    projekt.mks
python scripts/mks_tool.py extract projekt.mks ordner      # project.json, scene.json, prjImg.png
python scripts/mks_tool.py pack    ordner neu.mks
python scripts/mks_tool.py svg     projekt.mks vorschau.svg --toolpaths
python scripts/mks_tool.py verify  ordner_mit_mks_dateien/
```

```python
import sys; sys.path.insert(0, "scripts")
import mks

p = mks.new_project("demo", stock=(150, 100, 1.5))
lay = mks.find_layer(p, "Layer1")
lay.children.append(mks.polyline_node([(10, 10), (60, 10), (60, 40), (10, 40)]))
lay.children.append(mks.polyline_node(mks.circle_points(90, 50, 15)))
mks.save(p, "demo.mks")   # in Makera Studio öffnen, Werkzeugweg anlegen
```

Werkzeugwege berechnet weiterhin Makera Studio; die Bibliothek schreibt Vektoren, Layer, Rohling
und Pfad-Parameter.

## Als Claude-Code-Skill

Ordner nach `~/.claude/skills/makera-mks` klonen:

```bash
git clone https://github.com/id3vi5er/makera-mks ~/.claude/skills/makera-mks
```

## Test

```bash
python tests/test_selftest.py
```

## Lizenz

MIT, siehe `LICENSE`.
