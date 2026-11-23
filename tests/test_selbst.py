"""Selbsttest ohne fremde Dateien: Projekt erzeugen, speichern, laden, Roundtrip prüfen.

    python tests/test_selbst.py
"""
import json
import os
import struct
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import mks  # noqa: E402
import mks_tool  # noqa: E402


def main():
    p = mks.new_project("test", stock=(120, 80, 1.6))
    lay = mks.find_layer(p, "Layer1")
    lay.children.append(mks.polyline_node([(10, 10), (60, 10), (60, 40), (10, 40)]))
    lay.children.append(mks.polyline_node(mks.circle_points(90, 50, 15)))
    lay2 = mks.add_layer(p, "Zweiter", "#ff8800")
    lay2.children.append(mks.polyline_node([(5, 70), (115, 70)], "#ff8800", closed=False))

    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "t.mks")
        mks.save(p, f)
        with zipfile.ZipFile(f) as z:
            assert z.namelist() == ["makera", "makera.bin", "makera.prj"], z.namelist()
            b, j = z.read("makera.bin"), z.read("makera.prj")
        assert b.startswith(struct.pack("<I", 8) + b"scene_v3")
        assert b"\r\n" in j

        q = mks.load(f)
        assert mks.write_scene(q.scene) == b, "bin-Roundtrip"
        assert mks.dump_prj(json.loads(j)) == j, "prj-Roundtrip"
        sj = json.loads(mks_tool.dump_compact(mks_tool.scene_to_json(q.scene)))
        assert mks.write_scene(mks_tool.json_to_scene(sj)) == b, "JSON-Roundtrip"
        sb = json.loads(mks_tool.dump_compact(mks_tool.scene_to_json(q.scene, b64=True)))
        assert mks.write_scene(mks_tool.json_to_scene(sb)) == b, "Base64-Roundtrip"

        # extract -> pack über die CLI
        out = os.path.join(d, "x")
        mks_tool.main(["extract", f, out])
        mks_tool.main(["pack", out, os.path.join(d, "t2.mks")])
        with zipfile.ZipFile(os.path.join(d, "t2.mks")) as z2:
            assert z2.read("makera.bin") == b and z2.read("makera.prj") == j, "extract/pack"

        # Geometrie und Bezüge
        root, pc = mks.coordinate(q, 0)
        assert [img["name"] for img in pc["images"]] == ["Layer1", "Zweiter"]
        assert mks_tool.check_links(q) == []
        segs = [s for c in root.children for n, m in mks.iter_nodes(c) for s in mks.segments(n, m)]
        assert len(segs) == 4 + 64 + 1, len(segs)
        assert segs[0][0][:2] == (10.0, 10.0)
        mks_tool.main(["svg", f, os.path.join(d, "t.svg")])

    # leerer Name muss abgelehnt werden
    try:
        mks.write_scene(mks.Scene(roots=[mks.Node(name="", uuid="x", matrix=mks.IDENTITY, type=8)]))
        raise AssertionError("leerer Name nicht abgelehnt")
    except ValueError:
        pass
    print("alle Tests bestanden")


if __name__ == "__main__":
    main()
