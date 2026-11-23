"""Lesen und Schreiben von Makera-Studio-Projektdateien (.mks).

Format rekonstruiert aus Makera Studio 0.1.2.0 (MakeraStudio.exe, Writer bei
0x1401a8950 / Objekt-Serializer bei 0x140191620). Details: ../reference/FORMAT.md.

    proj = load("datei.mks")          # -> Project(prj=dict, scene=Scene, png=bytes|None)
    save(proj, "kopie.mks")

    p = new_project("demo", stock=(150, 100, 1.5))
    lay = find_layer(p, "Layer1")
    lay.children.append(polyline_node([(10, 10), (60, 10), (60, 40), (10, 40)]))
    lay.children.append(polyline_node(circle_points(90, 50, 15)))
    save(p, "demo.mks")
"""
from __future__ import annotations

import io
import json
import struct
import zipfile
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------- Datenmodell


@dataclass
class Texture:
    width: int
    height: int
    channels: int  # immer 4 (RGBA)
    data: bytes    # width*height*channels Bytes


@dataclass
class Material:
    name: str                       # z.B. "MeshBasicMaterial", "GCodeMaterial"
    color: tuple                    # 3 x float32 (Material+0x44)
    color2: tuple                   # 3 x float32 (Material+0x14)
    texture: Optional[Texture] = None


@dataclass
class Geometry:
    mode: int                       # Geometry+0x1a4 (1 = Linien, 4 = Dreiecke ...)
    positions: bytes = b""          # float32 xyz
    normals: bytes = b""            # float32 xyz
    uvs: bytes = b""                # float32 uv
    colors: bytes = b""             # float32 rgb
    indices: bytes = b""            # uint32
    class_name: Optional[str] = None  # nur bei type==4: "GCodeGeometry"/"PlaneGeometry"
    gcode_data: Optional[bytes] = None  # nur GCodeGeometry: 4-Byte-Elemente
    flag: bool = False              # Geometry+0x120
    extra: bytes = b""              # Geometry+0xf8, 4-Byte-Elemente


@dataclass
class Node:
    name: str
    uuid: str
    matrix: tuple                   # 16 x float32, spaltenweise (OpenGL)
    type: int                       # Object3D+0x260
    visible: bool = True            # Object3D+0x12
    i520: int = 0                   # Object3D+0x520
    b13: bool = False               # Object3D+0x13
    i360: int = 0
    i364: int = -1
    ints: list = field(default_factory=list)   # Object3D+0x370 (int32)
    geometry: Optional[Geometry] = None
    material: Optional[Material] = None
    children: list = field(default_factory=list)
    axis_items: list = field(default_factory=list)  # nur type==8 (AxisNodeMesh)


@dataclass
class GroupMember:
    key: str        # Schlüssel der Objektliste ("" = nicht gefunden)
    index: int      # Index in dieser Liste, -1 = nicht gefunden


@dataclass
class Scene:
    version: str = "scene_v3"
    roots: list = field(default_factory=list)
    groups: list = field(default_factory=list)  # list[list[GroupMember]]


@dataclass
class Project:
    prj: dict
    scene: Scene
    png: Optional[bytes] = None
    prj_raw: Optional[bytes] = None   # Originaltext von makera.prj (für bitgenaues Zurückschreiben)

# ---------------------------------------------------------------- Lesen


class _R:
    def __init__(self, b: bytes):
        self.b, self.o = b, 0

    def u32(self):
        v = struct.unpack_from("<I", self.b, self.o)[0]; self.o += 4; return v

    def i32(self):
        v = struct.unpack_from("<i", self.b, self.o)[0]; self.o += 4; return v

    def u8(self):
        v = self.b[self.o]; self.o += 1; return v

    def raw(self, n):
        v = self.b[self.o:self.o + n]
        if len(v) != n:
            raise EOFError(f"{n} Bytes an 0x{self.o:x} erwartet")
        self.o += n; return v

    def floats(self, n):
        v = struct.unpack_from(f"<{n}f", self.b, self.o); self.o += 4 * n; return v

    def blob(self):
        return self.raw(self.u32())

    def str(self):
        # Leere Strings schreibt Makera gar nicht (auch keine Länge) -> nicht eindeutig lesbar.
        return self.raw(self.u32()).decode("utf-8")


def _read_node(r: _R) -> Node:
    name = r.str()
    uuid = r.str()
    matrix = r.floats(16)
    has_geom = r.u32()
    n_children = r.u32()
    typ = r.u32()
    n_axis = r.u32() if typ == 8 else 0
    n = Node(name=name, uuid=uuid, matrix=matrix, type=typ)
    n.visible = bool(r.u8())
    n.i520 = r.i32()
    n.b13 = bool(r.u8())
    n.i360 = r.i32()
    n.i364 = r.i32()
    n.ints = [r.i32() for _ in range(r.u32())]
    if has_geom:
        g = Geometry(mode=r.u32())
        g.positions, g.normals, g.uvs, g.colors, g.indices = (r.blob() for _ in range(5))
        if typ == 4:
            g.class_name = r.str()
            if g.class_name == "GCodeGeometry":
                g.gcode_data = r.blob()
        g.flag = bool(r.u8())
        g.extra = r.blob()
        n.geometry = g
        mname = r.str()
        c1 = r.floats(3)
        c2 = r.floats(3)
        tex = None
        if r.u32() == 1:
            w, h, ch = r.u32(), r.u32(), r.u32()
            tex = Texture(w, h, ch, r.blob())
        n.material = Material(mname, c1, c2, tex)
    n.children = [_read_node(r) for _ in range(n_children)]
    n.axis_items = [_read_node(r) for _ in range(n_axis)]
    return n


def read_scene(b: bytes) -> Scene:
    r = _R(b)
    s = Scene(version=r.str())
    if s.version != "scene_v3":
        raise ValueError(f"nur scene_v3 unterstützt, gefunden {s.version!r}")
    s.roots = [_read_node(r) for _ in range(r.u32())]
    tag = r.str()
    if tag != "group":
        raise ValueError(f"'group' erwartet, gefunden {tag!r}")
    for _ in range(r.u32()):
        members = []
        for _ in range(r.u32()):
            # Schlüssel steht nur da, wenn nicht leer; Index -1 bedeutet "nicht gefunden".
            save = r.o
            key = ""
            ln = r.u32()
            if ln != 0xFFFFFFFF and 0 < ln < 4096 and r.o + ln + 4 <= len(b):
                key = r.raw(ln).decode("utf-8")
            else:
                r.o = save
            members.append(GroupMember(key, r.i32()))
        s.groups.append(members)
    if r.o != len(b):
        raise ValueError(f"{len(b) - r.o} Restbytes nach Szene")
    return s

# ---------------------------------------------------------------- Schreiben


class _W:
    def __init__(self):
        self.f = io.BytesIO()

    def u32(self, v): self.f.write(struct.pack("<I", v & 0xFFFFFFFF))
    def i32(self, v): self.f.write(struct.pack("<i", v))
    def u8(self, v): self.f.write(bytes([1 if v else 0]))
    def floats(self, v): self.f.write(struct.pack(f"<{len(v)}f", *v))

    def blob(self, b):
        self.u32(len(b)); self.f.write(b)

    def str(self, s):
        b = s.encode("utf-8")
        if b:  # wie Makera: leere Strings komplett weglassen
            self.blob(b)


def _write_node(w: _W, n: Node):
    if not n.name or not n.uuid:
        raise ValueError("name und uuid dürfen nicht leer sein (Makera liest sie sonst falsch)")
    w.str(n.name)
    w.str(n.uuid)
    w.floats(n.matrix)
    w.u32(1 if n.geometry else 0)
    w.u32(len(n.children))
    w.u32(n.type)
    if n.type == 8:
        w.u32(len(n.axis_items))
    w.u8(n.visible)
    w.i32(n.i520)
    w.u8(n.b13)
    w.i32(n.i360)
    w.i32(n.i364)
    w.u32(len(n.ints))
    for v in n.ints:
        w.i32(v)
    if n.geometry:
        g = n.geometry
        w.u32(g.mode)
        for b in (g.positions, g.normals, g.uvs, g.colors, g.indices):
            w.blob(b)
        if n.type == 4:
            w.str(g.class_name or "PlaneGeometry")
            if g.class_name == "GCodeGeometry":
                w.blob(g.gcode_data or b"")
        w.u8(g.flag)
        w.blob(g.extra)
        m = n.material or Material("MeshBasicMaterial", (1, 1, 1), (1, 1, 1))
        w.str(m.name)
        w.floats(m.color)
        w.floats(m.color2)
        if m.texture:
            t = m.texture
            w.u32(1); w.u32(t.width); w.u32(t.height); w.u32(t.channels); w.blob(t.data)
        else:
            w.u32(0)
    for c in n.children:
        _write_node(w, c)
    if n.type == 8:
        for c in n.axis_items:
            _write_node(w, c)


def write_scene(s: Scene) -> bytes:
    w = _W()
    w.str(s.version)
    w.u32(len(s.roots))
    for n in s.roots:
        _write_node(w, n)
    w.str("group")
    w.u32(len(s.groups))
    for members in s.groups:
        w.u32(len(members))
        for m in members:
            w.str(m.key)
            w.i32(m.index)
    return w.f.getvalue()

# ---------------------------------------------------------------- prj (Qt-JSON)


def dump_prj(obj) -> bytes:
    """JSON wie QJsonDocument::toJson(Indented): 4 Leerzeichen, Schlüssel sortiert,
    leere Container als '{\\n    }' / '[\\n    ]', Zeilenende CRLF."""
    def enc(v, ind):
        pad, pad2 = " " * ind, " " * (ind + 4)
        if isinstance(v, dict):
            if not v:
                return "{\n" + pad + "}"
            items = [pad2 + json.dumps(k, ensure_ascii=False) + ": " + enc(v[k], ind + 4) for k in sorted(v)]
            return "{\n" + ",\n".join(items) + "\n" + pad + "}"
        if isinstance(v, list):
            if not v:
                return "[\n" + pad + "]"
            return "[\n" + ",\n".join(pad2 + enc(x, ind + 4) for x in v) + "\n" + pad + "]"
        if v is True: return "true"
        if v is False: return "false"
        if v is None: return "null"
        if isinstance(v, float):
            if v == int(v) and abs(v) < 1e15:
                return str(int(v))
            return repr(v)
        if isinstance(v, int): return str(v)
        return json.dumps(v, ensure_ascii=False)
    return (enc(obj, 0) + "\n").replace("\n", "\r\n").encode("utf-8")

# ---------------------------------------------------------------- Erzeugen / Bearbeiten

IDENTITY = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def new_uuid() -> str:
    """uuid im Makera-Stil: 8-4-4-4-12 aus [A-Za-z0-9]."""
    import secrets
    import string
    a = string.ascii_letters + string.digits
    return "-".join("".join(secrets.choice(a) for _ in range(k)) for k in (8, 4, 4, 4, 12))


def hex2rgb(h: str) -> tuple:
    return tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))


def polyline_node(points, color_hex="#11a230", closed=True, z=0.0) -> Node:
    """Polylinie [(x,y) oder (x,y,z), ...] in mm -> Vektor-Knoten (type 2, GL_LINES-Segmentpaare)."""
    pts = [tuple(p) for p in points]
    if closed and pts[0] != pts[-1]:
        pts.append(pts[0])
    verts = []
    for p, q in zip(pts, pts[1:]):
        verts += [p, q]
    n = len(verts)
    g = Geometry(
        mode=1,
        positions=b"".join(struct.pack("<3f", p[0], p[1], p[2] if len(p) > 2 else z) for p in verts),
        normals=struct.pack("<3f", 0, 1, 0) * n,
        uvs=struct.pack("<2f", 0, 0) * n,
        colors=struct.pack("<3f", 1, 0, 0) * n,
        indices=struct.pack(f"<{n}I", *range(n)),
    )
    u = new_uuid()
    c = hex2rgb(color_hex)
    return Node(name=u, uuid=u, matrix=IDENTITY, type=2, geometry=g,
                material=Material("MeshInstanceLineMaterial", c, c))


def circle_points(cx, cy, r, segments=64):
    import math
    return [(cx + r * math.cos(2 * math.pi * i / segments), cy + r * math.sin(2 * math.pi * i / segments))
            for i in range(segments)]


def coordinate(p: "Project", index: int = 0):
    """(bin-Knoten, prj-Eintrag) der Aufspannung `index` (0 = TOP)."""
    pc = p.prj["project"]["lstCoordinate"][str(index)]
    for r in p.scene.roots:
        if r.uuid == pc["uuid"]:
            return r, pc
    raise KeyError(f"Koordinatenknoten zu uuid {pc['uuid']} fehlt in makera.bin")


def add_layer(p: "Project", name: str, color_hex: str = "#11a230", coord: int = 0) -> Node:
    """Neuen Layer (type 256) anlegen, in bin UND prj eintragen. Gibt den Layer-Knoten zurück."""
    root, pc = coordinate(p, coord)
    layer = Node(name=name, uuid=new_uuid(), matrix=IDENTITY, type=256)
    root.children.append(layer)
    ids = [img["id"] for img in pc["images"]]
    pc["images"].append({"activeState": False, "color": color_hex, "id": (max(ids) + 1) if ids else 0,
                         "list_meshes_uuids": [layer.uuid], "name": name, "showState": True, "type": 1})
    prj = p.prj["project"]
    prj["nGraphihcessMaxNum"] = max(prj.get("nGraphihcessMaxNum", 0), len(pc["images"]))
    return layer


def find_layer(p: "Project", name: str, coord: int = 0) -> Node:
    root, _ = coordinate(p, coord)
    for c in root.children:
        if c.type == 256 and c.name == name:
            return c
    raise KeyError(f"Layer {name!r} nicht gefunden")


def mat_mul(a, b):
    """4x4 spaltenweise: a*b."""
    return tuple(sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4)) for c in range(4) for r in range(4))


def transform(m, x, y, z):
    return (m[0] * x + m[4] * y + m[8] * z + m[12],
            m[1] * x + m[5] * y + m[9] * z + m[13],
            m[2] * x + m[6] * y + m[10] * z + m[14])


def iter_nodes(n: Node, parent_matrix=None):
    """(Knoten, Matrix relativ zum Startknoten-Elternteil) für alle Knoten, Tiefensuche.
    Für Werkstückkoordinaten mit parent_matrix=None an den Kindern eines CoordinateN starten."""
    m = n.matrix if parent_matrix is None else mat_mul(parent_matrix, n.matrix)
    yield n, m
    for c in n.children:
        yield from iter_nodes(c, m)
    for c in n.axis_items:
        yield from iter_nodes(c, m)


def segments(n: Node, m=None):
    """Liniensegmente [(p, q), ...] eines Knotens mit mode==1 (über die Indizes), optional transformiert."""
    g = n.geometry
    if not g or g.mode != 1 or not g.positions:
        return []
    pos = [struct.unpack_from("<3f", g.positions, i) for i in range(0, len(g.positions), 12)]
    idx = struct.unpack(f"<{len(g.indices) // 4}I", g.indices) if g.indices else range(len(pos))
    if m is not None:
        pos = [transform(m, *p) for p in pos]
    return [(pos[idx[i]], pos[idx[i + 1]]) for i in range(0, len(idx) - 1, 2)]


def new_project(name="neu", stock=(150.0, 100.0, 1.5), material="PCB", layer="Layer1",
                color_hex="#11a230") -> "Project":
    """Leeres Projekt: Aufspannung TOP mit einem Layer, Makera Z1, Rohling L×B×H in mm.
    Ursprung = linke untere Ecke der Rohling-Oberseite."""
    import time
    L, W, H = stock
    coord = Node(name="Coordinate0", uuid=new_uuid(), type=8,
                 matrix=(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -L / 2, -W / 2, H / 2, 1))
    prj = {"project": {
        "SchemeInfo": {k: {} for k in ("SchemeInfo2DCNC", "SchemeInfo2DLaser", "SchemeInfo3DCNC",
                                       "SchemeInfo3DRelief", "SchemeInfo4DRelief")},
        "arrPrjImage": None, "b4DType": False, "bCurSchemeWidget": False, "bEnableArcFit": False,
        "bEnableTailTop": True, "bShow3DModels": True, "dClampLength": 0,
        "em3DBasePosition": 0, "em4DBasePosition": 0, "emCurMachiningAngle": 0,
        "emMachineType": 2, "emOriginPoint": 0, "emSchemeType": 30, "emUnit": 0,
        "lst3DModels": [], "lstClamDiameter": [3.175],
        "lstCoordinate": {"0": {"active": True, "fileName": "", "graphicsshow": True, "id": 0, "images": [],
                                "name": "TOP", "originPoint": 0, "path": [], "pathsshow": True,
                                "uuid": coord.uuid}},
        "machine": {"ATC_Number": 0, "company": "Makera", "description": "", "g_ID": "Z1",
                    "id": "019c04c6-9e06-7655-a2ae-5654503300da", "isATC": True, "lastUpdateDate": "",
                    "maxFeedRate": 1200, "maxRPM": 13000, "model": "Makera Z1",
                    "range_A_Diameter": 80, "range_A_Length": 150, "range_x": 200, "range_y": 200,
                    "range_z": 100},
        "nGraphihcessMaxNum": 0, "nSaveDate": int(time.strftime("%Y%m%d")),
        "nSchemePageIndex": 1, "nToolPathesMaxNum": 0,
        "stModelInfo": {"modelHeight": 0, "modelLength": 0, "modelWidth": 0, "requiredCutDepth": 0},
        "stStockInfo": {"StockShape": 1, "bUsingMaterialSize": False, "diameter": 50,
                        "height": H, "length": L, "width": W,
                        "material": {"id": "019bfadc-e599-776d-b16b-b8b7e5a7b4ad", "lastUpdateDate": "",
                                     "metalDuty": 1, "name": material}},
        "strProjectName": name, "strSchemeName": "", "vecClamDiameter": [1],
    }}
    p = Project(prj=prj, scene=Scene(roots=[coord]))
    add_layer(p, layer, color_hex)
    p.prj["project"]["lstCoordinate"]["0"]["images"][0]["activeState"] = True
    return p

# ---------------------------------------------------------------- Container


def load(path) -> Project:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        raw = z.read("makera.prj")
        scene = read_scene(z.read("makera.bin"))
        png = z.read("prjImg.png") if "prjImg.png" in names else None
    return Project(prj=json.loads(raw), scene=scene, png=png, prj_raw=raw)


def save(p: Project, path, keep_prj_raw: bool = False):
    """Schreibt eine .mks. Reihenfolge und Einträge wie Makera Studio:
    'makera' (leer), 'makera.bin', 'makera.prj', optional 'prjImg.png', alle Deflate."""
    prj = p.prj_raw if (keep_prj_raw and p.prj_raw) else dump_prj(p.prj)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("makera", b"")
        z.writestr("makera.bin", write_scene(p.scene))
        z.writestr("makera.prj", prj)
        if p.png:
            z.writestr("prjImg.png", p.png)
