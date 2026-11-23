---
name: makera-mks
description: Reads, extracts, edits and writes Makera Studio project files (.mks, CNC CAM for Makera Z1/Carvera) byte-exact. Use when a .mks file should be read, analyzed, exported as JSON/SVG, modified (layers, vectors, stock, toolpath parameters) or newly generated, or when asked about the structure of makera.bin / makera.prj / scene_v3.
---

# Reading and writing Makera Studio `.mks` files

**Language:** this skill and its tools are in English. Always answer the user in the language
they use, regardless of the language of this file or of the tool output.

## Key facts

- `.mks` = ZIP containing `makera` (empty), `makera.bin` (binary scene graph `scene_v3`), `makera.prj`
  (Qt JSON, CRLF), optional `prjImg.png`. Full specification: `reference/FORMAT.md`
  (German: `reference/FORMAT.de.md`).
- The format was derived from the write code of `MakeraStudio.exe` 0.1.2.0, not guessed.
  Verified: 36 real projects read → written **byte-exact** (bin, prj and via the JSON representation);
  newly generated files load correctly in Makera Studio.
- Library `scripts/mks.py` (Python standard library only), CLI `scripts/mks_tool.py`.
- Treat the user's original files as **read-only**. Always write to a new file, never overwrite the
  original.

## CLI

```bash
S=~/.claude/skills/makera-mks/scripts
python $S/mks_tool.py info    file.mks [--max 5]       # stock, layers, toolpaths, tree
python $S/mks_tool.py extract file.mks folder [--b64]  # project.json + scene.json + prjImg.png
python $S/mks_tool.py pack    folder new.mks           # back to .mks (warns about broken uuid links)
python $S/mks_tool.py svg     file.mks image.svg [--coord 0] [--toolpaths]
python $S/mks_tool.py verify  file.mks|folder ...      # round-trip self-test
```

`scene.json` is the tree with geometry as number lists (`positions [[x,y,z]…]`, `indices`, …);
with `--b64` compactly as Base64 (for large files: a 15 MB bin is ~4× larger as JSON lists).
`project.json` is `makera.prj` unchanged as JSON; `pack` writes it back in Qt style.

## Python API

```python
import sys, os; sys.path.insert(0, os.path.expanduser("~/.claude/skills/makera-mks/scripts"))
import mks

p = mks.load("file.mks")               # Project(prj=dict, scene=Scene, png)
root, pc = mks.coordinate(p, 0)         # bin node + prj entry of setup "0"
for n, m in mks.iter_nodes(root):       # all nodes with accumulated matrix
    segs = mks.segments(n, m)           # line segments (mode 1)

# new
p = mks.new_project("demo", stock=(150, 100, 1.5))          # TOP + Layer1, Makera Z1
lay = mks.find_layer(p, "Layer1")
lay.children.append(mks.polyline_node([(10, 10), (60, 10), (60, 40), (10, 40)]))
lay.children.append(mks.polyline_node(mks.circle_points(90, 50, 15)))
lay2 = mks.add_layer(p, "Holes", "#d05ae7")                  # registers in bin AND prj
mks.save(p, "demo.mks")
```

Coordinates: origin = lower left corner of the stock's top surface, mm, Z = 0 on the surface.
`iter_nodes(root)` already includes the coordinate node's matrix (-L/2, -W/2, H/2) for its children –
for workpiece coordinates iterate over `root.children` instead (as `svg` does).

## Rules for writing

1. **Name and uuid must never be empty.** Makera writes empty strings without a length; the reader
   then gets out of step. `mks.save` refuses in that case.
2. **Keep bin and prj in sync.** The layer uuid is in `images[].list_meshes_uuids`, the coordinate
   node uuid in `lstCoordinate[i].uuid`, machined vectors in `path[].selectedmeshes`, computed paths in
   `path[].gcodemeshuuidmap` (type 4 nodes in `axis_items`). Create new layers with `add_layer`,
   not just as nodes.
3. **Do not invent toolpaths.** Write new vectors without computed paths; Makera computes them via
   "Add Toolpath" / "Generate Toolpath". Toolpath definitions (depth, tool, feed) can be written or
   changed in `project.json` with an empty `gcodemeshuuidmap`; then use "Recalculate" in Makera.
4. Vectors: `mode=1` (GL_LINES, segment pairs), material `MeshInstanceLineMaterial` in the layer color.
5. After writing, run `verify` on the new file and – if possible – open it in Makera Studio:
   `"<install folder>\MakeraStudio.exe" "<path>"` (folder: `InstallLocation` of "Makera Studio" in the
   Windows uninstall list, default `%LOCALAPPDATA%\Programs\Makera Studio`). It is single-instance:
   the file is loaded into the open window and unsaved changes there are lost.

## Pitfalls

- Fields `i520` (and `stepOverMM` in the prj) contain uninitialized memory – random values are normal.
- The bin may contain more `CoordinateN` nodes than the prj references (old setups); the uuid decides.
- Only `scene_v3`; `scene`/`scene_v2` (older Makera versions) are rejected.
- The `group` section was empty in all samples; the reader parses the optional key heuristically.
- If a new Makera version changes the format, `verify` fails. Re-derive it as described in
  `reference/FORMAT.md` section 5 (find the writer via the 8-byte immediate `scene_v3` in the EXE,
  read the fwrite calls of the object serializer; RTTI names `.?AV…@@` help).
