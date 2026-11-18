"""Pack corner_stop.stl into fixture/plate.3mf (opens in Bambu Studio)."""
import struct, zipfile
data = open("fixture/corner_stop.stl", "rb").read()
n = struct.unpack("<I", data[80:84])[0]
verts, idx, tris = {}, [], []
for i in range(n):
    f = struct.unpack("<12fH", data[84 + i * 50: 134 + i * 50])
    t = []
    for k in range(3):
        v = tuple(round(c, 4) for c in f[3 + 3 * k: 6 + 3 * k])
        t.append(verts.setdefault(v, len(verts)))
    tris.append(t)
vx = "".join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x, y, z in verts)
tx = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in tris)
model = f'''<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">
<resources><object id="1" name="paper corner stop" type="model"><mesh><vertices>{vx}</vertices><triangles>{tx}</triangles></mesh></object></resources>
<build><item objectid="1" transform="1 0 0 0 1 0 0 0 1 20 20 0"/></build></model>'''
with zipfile.ZipFile("fixture/plate.3mf", "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    z.writestr("3D/3dmodel.model", model)
print("wrote fixture/plate.3mf:", len(verts), "vertices,", len(tris), "triangles")
