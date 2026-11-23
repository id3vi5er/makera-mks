# Makera Studio `.mks` – file format

*English | [Deutsch](FORMAT.de.md)*

Reconstructed on 2026-11-23 from Makera Studio **0.1.2.0** (`MakeraStudio.exe`, Qt5 plus an in-house
Three.js-like engine "TinyOGL"). The source is the write code inside the EXE (writer `0x1401a8950`,
object serializer `0x140191620`, loader `0x1401a1590`). Verified against 36 real projects
(2D milling, PCB isolation milling, STEP models, SVG/Gerber imports, multiple setups):

* `makera.bin` → parser → writer: **36/36 byte-identical**
* `makera.prj` → JSON → writer: **36/36 byte-identical**
* Through the JSON representation (`mks_tool.py extract` → `pack`): **36/36 byte-identical**
* Newly generated files and repacked copies load correctly in Makera Studio.

Code: `../scripts/mks.py` (library), `../scripts/mks_tool.py` (CLI: info/extract/pack/svg/verify).

## 1. Container

A ZIP file (Deflate). Makera writes it with quazip (Zip64 fields, data descriptors); a plain ZIP
written by Python is read as well. Entries in this order:

| Entry        | Content |
|--------------|---------|
| `makera`     | empty (0 bytes), marker |
| `makera.bin` | scene graph, binary format `scene_v3` (section 3) |
| `makera.prj` | project JSON: stock, machine, layers, toolpaths (section 2) |
| `prjImg.png` | preview image (optional, missing in some files) |

## 2. `makera.prj`

`QJsonDocument::toJson(Indented)`: UTF-8, **CRLF**, 4-space indent, keys sorted alphabetically,
empty objects/arrays written as `{` newline `}`. Integral doubles are written without a fraction,
all others in shortest round-trip form (like Python `repr`). Some fields contain uninitialized
memory (e.g. `stepOverMM: 4.54e-312`, `lastUpdateDate: "\u0000"`).

Important parts below `project`:

* `stStockInfo`: stock (`length`, `width`, `height` in mm, `StockShape`, material, `materialspec`).
* `machine`: machine (Z1: 200×200×100, `maxRPM`, `maxFeedRate`).
* `lstCoordinate`: dict `"0"`, `"1"`, … one per **setup/side** (`name` e.g. `TOP`), containing
  * `uuid`: uuid of the matching `CoordinateN` node in `makera.bin`
  * `images[]`: layers or imported files: `name`, `color` (`#rrggbb`), `type`
    (1 = layer, 2 = imported graphic such as Gerber/SVG), `list_meshes_uuids` (uuid of the layer node
    in the bin), `showState`, `activeState`
  * `path[]`: toolpaths. `type` 0 = 2D pocket, 1 = 2D contour, 2 = drilling, 7 = 3D pocket,
    8 = cutout, 9 = thread. `selectedmeshes` = uuids of the machined vector nodes,
    `gcodemeshuuidmap` = uuids of the computed toolpath nodes (in `axis_items`, see below),
    `tools[]` (tool with spindle speed, feed, step-down …), `depth`, `safe`, `tab`, `ramping`.
* `strProjectName`, `nSaveDate` (YYYYMMDD).

## 3. `makera.bin` (`scene_v3`)

Little-endian, no alignment. Primitive types:

* `u32` / `i32` / `f32`, `u8` (bool, 0/1)
* `str` = `u32 length` + UTF-8 bytes. **Caution:** if a string is empty, Makera writes *nothing at all*
  (not even a length of 0). A node's name and uuid must therefore never be empty.
* `blob` = `u32 byte count` + bytes (array of f32/u32)

### File

```
str   "scene_v3"          (older versions: "scene", "scene_v2")
u32   nRoots
Node  roots[nRoots]       (one CoordinateN per setup)
str   "group"
u32   nGroups
  u32 nMembers
    str key               (only if not empty)
    i32 index             (-1 = not found)
```

### Node (recursive)

```
str   name               layer/object name; for vectors usually = uuid
str   uuid               36 characters, pattern 8-4-4-4-12 from [A-Za-z0-9]
f32   matrix[16]         4×4, column-major (translation in [12..14]), mm
u32   hasGeometry
u32   nChildren
u32   type               node type, see below
[u32  nAxisItems]        only if type == 8
u8    visible
i32   i520               uninitialized (random values) – anything, write 0
u8    b13                (1 for imported files / STEP roots)
i32   i360               (STEP faces: number of faces)
i32   i364               usually -1
u32   nInts, i32 ints[nInts]
if hasGeometry:
  u32  mode              1 = GL_LINES (segment pairs), 4 = GL_TRIANGLES
  blob positions         f32 xyz per vertex
  blob normals           f32 xyz (for lines (0,1,0))
  blob uvs               f32 uv
  blob colors            f32 rgb (may be empty)
  blob indices           u32
  if type == 4:
    str  geoClass        "GCodeGeometry" or "PlaneGeometry"
    if geoClass == "GCodeGeometry":
      blob gcodeData     i32 per vertex (observed: first value 1, rest 0; meaning unknown)
  u8   flag              (1 for STEP faces)
  blob extra             f32 per vertex (STEP faces: face id as float)
  str  materialName      MeshBasicMaterial, MeshInstanceLineMaterial, GCodeMaterial, …
  f32  color[3]          RGB 0..1
  f32  color2[3]         RGB 0..1 (usually equal to color)
  u32  hasTexture
  if hasTexture == 1:
    u32 width, u32 height, u32 channels (=4)
    blob pixels          width*height*4 bytes RGBA
Node  children[nChildren]
Node  axisItems[nAxisItems]   only if type == 8
```

### Node types (`type`)

| type | Meaning | Material | Position in scene |
|------|---------|----------|-------------------|
| 8    | coordinate system `CoordinateN` (AxisNodeMesh), one per setup | – | root |
| 256  | layer / imported file (group) | – | child of 8 |
| 2    | vector path (polyline as line segments) | MeshInstanceLineMaterial / MeshBasicMaterial | child of 256 |
| 128  | vector (e.g. text/fill) | MeshBasicMaterial | child of 256 |
| 4    | computed toolpath `gcode_polyline` | GCodeMaterial | `axisItems` of 8 |
| 64   | mesh (STL etc.) | MeshPhongMaterial | |
| 1024 | STEP model (root without geometry, child "Faces") | MatcapMaterial | |
| 2048 | STEP edges "Edges" | StepBoundaryMaterial | |

The matrix of `CoordinateN` is (-length/2, -width/2, height/2): the workpiece origin is the lower
left corner of the top surface, the scene is centered. Vector coordinates of the children are mm in
this system (Z = 0 on the surface, toolpaths with negative Z).

### Links between bin and prj

* `lstCoordinate[i].uuid` ↔ uuid of the root node `CoordinateN`
* `images[].list_meshes_uuids` ↔ uuid of a layer node (type 256)
* `path[].selectedmeshes` ↔ uuids of vector nodes (type 2/128)
* `path[].gcodemeshuuidmap` ↔ uuids of the toolpath nodes (type 4) in `axisItems`

## 4. Open points

* The meaning of `i360`, `i364`, `ints`, `flag`, `extra` is based on observation only, not on names
  from the engine.
* The `group` section was empty in all files; the reader handles the optional key heuristically.
* The older formats `scene`/`scene_v2` are not read.
* Toolpaths are not computed when writing: new files contain vectors only; Makera computes the paths
  via "Generate Toolpath".

## 5. Re-deriving the format (if a new Makera version changes it)

Procedure used on 2026-11-23, without Ghidra/IDA:

1. A Python venv with `capstone` and `pefile`.
2. Find the writer: `scene_v3` appears in the code as an 8-byte immediate (`48 b8 73 63 65 6e 65 5f 76 33`,
   `movabs rax, 'scene_v3'`). Function bounds come from `.pdata` (exception directory); note that long
   functions are split into several `.pdata` entries → keep disassembling until `ret`.
   The loader compares `scene_v3` via `lea` against the string in `.rdata`.
3. All writes go through `fwrite(ptr, size, count, FILE*)` (IAT slot `0x14149eeb8` in 0.1.2.0):
   `edx` = element size, `r8` = count. The order of these calls is the format.
4. Object serialization hangs off a `std::function` (lambda vtable, slot `+0x10`).
   Recursion over the children goes through the same `std::function`.
5. `__RTDynamicCast` calls carry RTTI type descriptors (`.?AVMesh@@`, `.?AVGCodeGeometry@@`,
   `.?AVMeshBasicMaterial@@` …) – this makes the per-class special cases readable.
6. Always check the result with `mks_tool.py verify` against real files (goal: byte-exact).
