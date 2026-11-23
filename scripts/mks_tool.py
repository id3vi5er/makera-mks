"""Makera-Studio-.mks: entpacken, bearbeiten, wieder packen.

  python mks_tool.py info    datei.mks [--max N]        Baum + Rohling/Werkzeugwege anzeigen
  python mks_tool.py extract datei.mks ordner [--b64]   -> project.json, scene.json, prjImg.png
  python mks_tool.py pack    ordner datei.mks           <- aus diesen Dateien neu bauen
  python mks_tool.py verify  datei.mks|ordner ...       Roundtrip-Test (bytegenau) über Dateien/Ordner
  python mks_tool.py svg     datei.mks bild.svg [--coord 0] [--toolpaths]   Vektor-Vorschau

scene.json (Version 1): {"format":"makera-scene-json","version":1,"scene_version":"scene_v3",
  "roots":[Node...], "groups":[[{"key":..,"index":..}]]}
Node: name, uuid, type, matrix[16] (spaltenweise), visible, i520, b13, i360, i364, ints,
  geometry|null, material|null, children[], axis_items[]
geometry: mode, positions[[x,y,z]], normals[[x,y,z]], uvs[[u,v]], colors[[r,g,b]], indices[],
  class_name|null, gcode_data[]|null, flag, extra[] (float je Vertex)
  Mit --b64 stehen die Felder stattdessen als {"b64": "..."} (Rohbytes, kompakt).
material: name, color[3], color2[3], texture|null {width,height,channels,b64}
float32-Werte werden exakt (über float64-repr) gespeichert -> pack ist bytegenau.
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import struct
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mks  # noqa: E402

# Feld -> (struct-Typ, Elemente pro Eintrag)
GEO_FIELDS = {"positions": ("f", 3), "normals": ("f", 3), "uvs": ("f", 2), "colors": ("f", 3),
              "indices": ("I", 1), "gcode_data": ("i", 1), "extra": ("f", 1)}

# ---------------------------------------------------------------- bin <-> JSON


def blob_to_json(b: bytes, kind: str, per: int, b64: bool):
    if b64:
        return {"b64": base64.b64encode(b).decode()}
    n = len(b) // 4
    if n * 4 != len(b):
        return {"b64": base64.b64encode(b).decode()}  # unerwartete Länge: verlustfrei als Rohdaten
    vals = struct.unpack(f"<{n}{kind}", b)
    if per == 1:
        return list(vals)
    if n % per:
        return {"b64": base64.b64encode(b).decode()}
    return [list(vals[i:i + per]) for i in range(0, n, per)]


def json_to_blob(v, kind: str) -> bytes:
    if v is None:
        return b""
    if isinstance(v, dict):
        return base64.b64decode(v["b64"])
    flat = [x for row in v for x in row] if v and isinstance(v[0], list) else list(v)
    return struct.pack(f"<{len(flat)}{kind}", *flat)


def node_to_json(n: mks.Node, b64=False) -> dict:
    d = {"name": n.name, "uuid": n.uuid, "type": n.type, "matrix": list(n.matrix),
         "visible": n.visible, "i520": n.i520, "b13": n.b13, "i360": n.i360, "i364": n.i364,
         "ints": n.ints, "geometry": None, "material": None}
    if n.geometry:
        g = n.geometry
        gd = {"mode": g.mode}
        for f, (k, per) in GEO_FIELDS.items():
            val = getattr(g, f)
            gd[f] = None if val is None else blob_to_json(val, k, per, b64)
        gd["class_name"] = g.class_name
        gd["flag"] = g.flag
        d["geometry"] = gd
    if n.material:
        m = n.material
        md = {"name": m.name, "color": list(m.color), "color2": list(m.color2), "texture": None}
        if m.texture:
            t = m.texture
            md["texture"] = {"width": t.width, "height": t.height, "channels": t.channels,
                             "b64": base64.b64encode(t.data).decode()}
        d["material"] = md
    d["children"] = [node_to_json(c, b64) for c in n.children]
    d["axis_items"] = [node_to_json(c, b64) for c in n.axis_items]
    return d


def json_to_node(d: dict) -> mks.Node:
    n = mks.Node(name=d["name"], uuid=d["uuid"], matrix=tuple(d["matrix"]), type=d["type"],
                 visible=d.get("visible", True), i520=d.get("i520", 0), b13=d.get("b13", False),
                 i360=d.get("i360", 0), i364=d.get("i364", -1), ints=list(d.get("ints", [])))
    gd = d.get("geometry")
    if gd:
        g = mks.Geometry(mode=gd["mode"])
        for f, (k, _per) in GEO_FIELDS.items():
            if f == "gcode_data":
                g.gcode_data = None if gd.get(f) is None else json_to_blob(gd[f], k)
            else:
                setattr(g, f, json_to_blob(gd.get(f), k))
        g.class_name = gd.get("class_name")
        g.flag = gd.get("flag", False)
        n.geometry = g
        md = d.get("material") or {"name": "MeshBasicMaterial", "color": [1, 1, 1], "color2": [1, 1, 1]}
        tex = None
        if md.get("texture"):
            t = md["texture"]
            tex = mks.Texture(t["width"], t["height"], t["channels"], base64.b64decode(t["b64"]))
        n.material = mks.Material(md["name"], tuple(md["color"]), tuple(md["color2"]), tex)
    n.children = [json_to_node(c) for c in d.get("children", [])]
    n.axis_items = [json_to_node(c) for c in d.get("axis_items", [])]
    return n


def scene_to_json(s: mks.Scene, b64=False) -> dict:
    return {"format": "makera-scene-json", "version": 1, "scene_version": s.version,
            "roots": [node_to_json(r, b64) for r in s.roots],
            "groups": [[{"key": m.key, "index": m.index} for m in g] for g in s.groups]}


def json_to_scene(d: dict) -> mks.Scene:
    if d.get("format") != "makera-scene-json":
        raise ValueError("keine scene.json von mks_tool")
    return mks.Scene(version=d.get("scene_version", "scene_v3"),
                     roots=[json_to_node(r) for r in d["roots"]],
                     groups=[[mks.GroupMember(m["key"], m["index"]) for m in g] for g in d.get("groups", [])])


def dump_compact(obj, ind=0) -> str:
    """JSON mit Einzug für die Struktur, aber Zahlenlisten (Geometrie, Matrix) einzeilig."""
    pad, pad2 = " " * ind, " " * (ind + 1)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        return "{\n" + ",\n".join(f"{pad2}{json.dumps(k)}: {dump_compact(v, ind + 1)}"
                                  for k, v in obj.items()) + "\n" + pad + "}"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        if all(not isinstance(x, (dict, list)) or (isinstance(x, list) and all(not isinstance(y, (dict, list)) for y in x))
               for x in obj):
            return json.dumps(obj, separators=(",", ":"))
        return "[\n" + ",\n".join(pad2 + dump_compact(x, ind + 1) for x in obj) + "\n" + pad + "]"
    return json.dumps(obj, ensure_ascii=False)

# ---------------------------------------------------------------- Befehle


def cmd_extract(a):
    p = mks.load(a.mks)
    os.makedirs(a.ordner, exist_ok=True)
    with open(os.path.join(a.ordner, "project.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(p.prj, f, indent=2, ensure_ascii=False)
    with open(os.path.join(a.ordner, "scene.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(dump_compact(scene_to_json(p.scene, a.b64)))
    if p.png:
        with open(os.path.join(a.ordner, "prjImg.png"), "wb") as f:
            f.write(p.png)
    print(f"entpackt nach {a.ordner}: project.json, scene.json" + (", prjImg.png" if p.png else ""))


def load_folder(ordner) -> mks.Project:
    with open(os.path.join(ordner, "project.json"), encoding="utf-8") as f:
        prj = json.load(f)
    with open(os.path.join(ordner, "scene.json"), encoding="utf-8") as f:
        scene = json_to_scene(json.load(f))
    png_path = os.path.join(ordner, "prjImg.png")
    png = open(png_path, "rb").read() if os.path.exists(png_path) else None
    return mks.Project(prj=prj, scene=scene, png=png)


def check_links(p: mks.Project):
    """Warnungen, wenn prj-uuids nicht in der Szene vorkommen."""
    uu = set()
    for r in p.scene.roots:
        for n, _ in mks.iter_nodes(r):
            uu.add(n.uuid)
    warn = []
    for key, c in p.prj["project"]["lstCoordinate"].items():
        if c["uuid"] not in uu:
            warn.append(f"Aufspannung {key}: uuid {c['uuid']} fehlt in der Szene")
        for img in c["images"]:
            for u in img["list_meshes_uuids"]:
                if u not in uu:
                    warn.append(f"Layer {img['name']!r}: uuid {u} fehlt in der Szene")
        for pa in c["path"]:
            missing = [u for u in pa.get("selectedmeshes", []) if u not in uu]
            if missing:
                warn.append(f"Pfad {pa.get('pathName')!r}: {len(missing)} selectedmeshes fehlen")
    return warn


def cmd_pack(a):
    p = load_folder(a.ordner)
    for w in check_links(p):
        print("WARNUNG:", w)
    mks.save(p, a.mks)
    print("geschrieben:", a.mks)


def type_name(t):
    return {8: "Aufspannung", 256: "Layer", 2: "Vektor", 128: "Vektor128", 4: "Werkzeugweg",
            64: "Mesh", 1024: "STEP", 2048: "STEP-Kanten"}.get(t, f"type{t}")


def cmd_info(a):
    p = mks.load(a.mks)
    pr = p.prj["project"]
    st = pr["stStockInfo"]
    print(f"Projekt {pr.get('strProjectName')!r}, gespeichert {pr.get('nSaveDate')}, "
          f"Maschine {pr['machine'].get('model')}")
    print(f"Rohling {st['length']} x {st['width']} x {st['height']} mm, Material {st['material'].get('name')}")
    for key, c in sorted(pr["lstCoordinate"].items()):
        print(f"\nAufspannung {key} {c['name']} (uuid {c['uuid']})")
        for img in c["images"]:
            print(f"  Layer {img['name']!r} {img['color']} type={img['type']}")
        for pa in c["path"]:
            t = pa["tools"][0] if pa.get("tools") else {}
            print(f"  Pfad {pa['pathName']!r} type={pa['type']} Objekte={len(pa.get('selectedmeshes', []))} "
                  f"Tiefe {pa['depth']['startDepth']}..{pa['depth']['endDepth']} "
                  f"Werkzeug {t.get('toolName')!r} {t.get('spindleSpeed')} U/min F{t.get('feedrate')}")

    def walk(n, d):
        g = n.geometry
        s = f"{'  ' * d}{type_name(n.type)} {n.name!r}"
        if n.name != n.uuid and n.type in (8, 256):
            s += f" [{n.uuid}]"
        if g:
            s += f" mode={g.mode} vtx={len(g.positions) // 12} {n.material.name}"
        print(s)
        for i, c in enumerate(n.children):
            if i == a.max:
                print(f"{'  ' * (d + 1)}... +{len(n.children) - a.max}")
                break
            walk(c, d + 1)
        if n.axis_items:
            print(f"{'  ' * (d + 1)}[{len(n.axis_items)} Werkzeugweg-Objekte]")
    print("\nSzene:")
    for r in p.scene.roots:
        walk(r, 1)


def cmd_verify(a):
    files = []
    for x in a.pfade:
        files += sorted(glob.glob(os.path.join(x, "**", "*.mks"), recursive=True)) if os.path.isdir(x) else [x]
    ok = 0
    for f in files:
        with zipfile.ZipFile(f) as z:
            b, j = z.read("makera.bin"), z.read("makera.prj")
        try:
            s = mks.read_scene(b)
            r1 = mks.write_scene(s) == b
            r2 = mks.dump_prj(json.loads(j)) == j
            # zusätzlich über das JSON-Abbild
            r3 = mks.write_scene(json_to_scene(json.loads(dump_compact(scene_to_json(s))))) == b
            good = r1 and r2 and r3
            ok += good
            print(f"{'OK  ' if good else 'DIFF'} bin={r1} prj={r2} json={r3}  {f}")
        except Exception as e:  # noqa: BLE001
            print(f"FEHLER {f}: {e}")
    print(f"\n{ok}/{len(files)} bytegenau")
    return 0 if ok == len(files) else 1


def cmd_svg(a):
    p = mks.load(a.mks)
    root, _ = mks.coordinate(p, a.coord)
    st = p.prj["project"]["stStockInfo"]
    L, W = float(st["length"]), float(st["width"])
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-5 -5 {L + 10} {W + 10}" '
           f'width="{(L + 10) * 4}" height="{(W + 10) * 4}">',
           f'<g transform="translate(0 {W}) scale(1 -1)" fill="none" stroke-width="0.15">',
           f'<rect x="0" y="0" width="{L}" height="{W}" stroke="#999"/>']
    items = list(root.children) + (list(root.axis_items) if a.toolpaths else [])
    for top in items:
        for n, m in mks.iter_nodes(top):
            segs = mks.segments(n, m)
            if not segs:
                continue
            col = "#" + "".join(f"{round(c * 255):02x}" for c in n.material.color) if n.material else "#000"
            if n.type == 4:
                col = "#3070ff"
            d = " ".join(f"M{p[0]:.3f} {p[1]:.3f}L{q[0]:.3f} {q[1]:.3f}" for p, q in segs)
            out.append(f'<path d="{d}" stroke="{col}"/>')
    out.append("</g></svg>")
    with open(a.svg, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("geschrieben:", a.svg)


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    ap =argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("info"); s.add_argument("mks"); s.add_argument("--max", type=int, default=5)
    s = sp.add_parser("extract"); s.add_argument("mks"); s.add_argument("ordner")
    s.add_argument("--b64", action="store_true", help="Geometrie als Base64 statt Zahlenlisten")
    s = sp.add_parser("pack"); s.add_argument("ordner"); s.add_argument("mks")
    s = sp.add_parser("verify"); s.add_argument("pfade", nargs="+")
    s = sp.add_parser("svg"); s.add_argument("mks"); s.add_argument("svg")
    s.add_argument("--coord", type=int, default=0); s.add_argument("--toolpaths", action="store_true")
    a = ap.parse_args(argv)
    return {"info": cmd_info, "extract": cmd_extract, "pack": cmd_pack, "verify": cmd_verify,
            "svg": cmd_svg}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
