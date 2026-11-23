# makera-mks

*English | [Deutsch](README.de.md)*

Read, extract, edit and write **Makera Studio project files (`.mks`)**, the CAM format of the
Makera Z1 / Carvera – byte-exact. Reading and re-writing real projects yields identical bytes;
newly generated files open in Makera Studio like its own. Pure Python 3 standard library, no
dependencies.

> Unofficial, not affiliated with Makera. The format was derived from Makera Studio 0.1.2.0
> (the EXE's write routine, see [`reference/FORMAT.md`](reference/FORMAT.md)). Later versions may
> change it – `mks_tool.py verify` shows that immediately.

## Contents

| File | Purpose |
|---|---|
| `scripts/mks.py` | library: `load`/`save`, scene graph, helpers for creating content (`new_project`, `add_layer`, `polyline_node`, …) |
| `scripts/mks_tool.py` | CLI: `info`, `extract`, `pack`, `svg`, `verify` |
| `reference/FORMAT.md` | format specification (`makera.bin` "scene_v3", `makera.prj`, container) – [Deutsch](reference/FORMAT.de.md) |
| `SKILL.md` | instructions as a [Claude Code skill](https://docs.claude.com/en/docs/claude-code/skills) |
| `tests/test_selftest.py` | self-test without external files |

## Quick start

```bash
python scripts/mks_tool.py info    project.mks
python scripts/mks_tool.py extract project.mks folder       # project.json, scene.json, prjImg.png
python scripts/mks_tool.py pack    folder new.mks
python scripts/mks_tool.py svg     project.mks preview.svg --toolpaths
python scripts/mks_tool.py verify  folder_with_mks_files/
```

`extract` writes `scene.json` with geometry as number lists (`positions [[x,y,z]…]`, `indices`, …);
`--b64` stores it compactly as Base64 instead. `pack` writes `project.json` back in Qt style and
warns if uuid links between project and scene no longer match.

```python
import sys; sys.path.insert(0, "scripts")
import mks

p = mks.new_project("demo", stock=(150, 100, 1.5))
lay = mks.find_layer(p, "Layer1")
lay.children.append(mks.polyline_node([(10, 10), (60, 10), (60, 40), (10, 40)]))
lay.children.append(mks.polyline_node(mks.circle_points(90, 50, 15)))
mks.save(p, "demo.mks")   # open in Makera Studio, add a toolpath
```

Coordinates are mm with the origin at the lower left corner of the stock's top surface.
Toolpaths are still computed by Makera Studio; the library writes vectors, layers, stock and
toolpath parameters (after changes, use "Generate Toolpath" / "Recalculate" in Makera).

## As a Claude Code skill

Clone the folder to `~/.claude/skills/makera-mks`:

```bash
git clone https://github.com/id3vi5er/makera-mks ~/.claude/skills/makera-mks
```

## Test

```bash
python tests/test_selftest.py
```

## License

MIT, see `LICENSE`.
