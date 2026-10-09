"""IFC models with IfcOpenShell: steel elements with quantities, assemblies, bolts and a light plan geometry."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional

import numpy as np

METAL_ENTITIES = ("IfcBeam", "IfcColumn", "IfcMember", "IfcPlate", "IfcFastener", "IfcMechanicalFastener",
                  "IfcElementAssembly", "IfcDiscreteAccessory", "IfcRailing", "IfcStair", "IfcStairFlight")
NON_METAL_ENTITIES = ("IfcWall", "IfcWallStandardCase", "IfcSlab", "IfcFooting", "IfcPile", "IfcWindow", "IfcDoor",
                      "IfcRoof", "IfcCovering", "IfcDuctSegment", "IfcPipeSegment", "IfcFlowTerminal", "IfcSpace",
                      "IfcFurnishingElement", "IfcReinforcingBar", "IfcCurtainWall", "IfcBuildingElementProxy")
STEEL_RE = re.compile(r"steel|stål|staal|teras|teräs|s\s?235|s\s?275|s\s?355|s\s?420|s\s?460|8\.8|10\.9", re.I)
NONSTEEL_RE = re.compile(r"concrete|betong|betoon|beton|timber|wood|tre|puit|glass|lasi|gypsum|gips|insulation|isolasjon|brick", re.I)


def quick_scan(path: Path) -> dict[str, Any]:
    """Count entities and materials from the STEP text without building the model (fast, for the file map)."""
    counts: Counter[str] = Counter()
    materials: Counter[str] = Counter()
    schema = None
    app = None
    ent_re = re.compile(rb"^#\d+\s*=\s*(IFC[A-Z0-9]+)\(", re.M)
    mat_re = re.compile(rb"IFCMATERIAL\('([^']*)'")
    with open(path, "rb") as fh:
        data = fh.read()
    m = re.search(rb"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", data)
    if m:
        schema = m.group(1).decode(errors="ignore")
    m = re.search(rb"IFCAPPLICATION\([^,]*,'([^']*)','([^']*)'", data)
    if m:
        app = f"{m.group(2).decode(errors='ignore')} {m.group(1).decode(errors='ignore')}"
    for mm in ent_re.finditer(data):
        counts[mm.group(1).decode()] += 1
    for mm in mat_re.finditer(data):
        materials[_decode_ifc_str(mm.group(1).decode("latin-1"))] += 1
    norm = {k.upper(): v for k, v in counts.items()}
    metal = sum(norm.get(e.upper(), 0) for e in ("IfcBeam", "IfcColumn", "IfcMember", "IfcPlate"))
    nonmetal = sum(norm.get(e.upper(), 0) for e in NON_METAL_ENTITIES)
    steel_mats = [k for k in materials if STEEL_RE.search(k)]
    other_mats = [k for k in materials if NONSTEEL_RE.search(k)]
    return {"schema": schema, "application": app, "entity_counts": {k: v for k, v in counts.most_common(40)},
            "metal_elements": metal, "nonmetal_elements": nonmetal, "materials": dict(materials),
            "steel_materials": steel_mats, "other_materials": other_mats,
            "elements": metal + nonmetal}


def _decode_ifc_str(s: str) -> str:
    # IFC STEP encodes non-ASCII as \X2\00E5\X0\ or \S\e
    def x2(m: re.Match) -> str:
        h = m.group(1)
        return "".join(chr(int(h[i:i + 4], 16)) for i in range(0, len(h), 4))
    s = re.sub(r"\\X2\\([0-9A-Fa-f]+)\\X0\\", x2, s)
    s = re.sub(r"\\S\\(.)", lambda m: chr(ord(m.group(1)) + 128), s)
    return s


def _psets(el) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for rel in getattr(el, "IsDefinedBy", None) or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pdef = rel.RelatingPropertyDefinition
        if pdef.is_a("IfcPropertySet"):
            d = out.setdefault(pdef.Name or "", {})
            for p in pdef.HasProperties or []:
                if p.is_a("IfcPropertySingleValue"):
                    v = p.NominalValue.wrappedValue if p.NominalValue is not None else None
                    d[p.Name] = v
        elif pdef.is_a("IfcElementQuantity"):
            d = out.setdefault(pdef.Name or "", {})
            for q in pdef.Quantities or []:
                for attr in ("LengthValue", "AreaValue", "VolumeValue", "WeightValue", "CountValue"):
                    if hasattr(q, attr):
                        d[q.Name] = getattr(q, attr)
                        break
    return out


def _material_name(el) -> Optional[str]:
    for rel in getattr(el, "HasAssociations", None) or []:
        if rel.is_a("IfcRelAssociatesMaterial"):
            m = rel.RelatingMaterial
            if m.is_a("IfcMaterial"):
                return m.Name
            if m.is_a("IfcMaterialLayerSetUsage"):
                try:
                    return m.ForLayerSet.MaterialLayers[0].Material.Name
                except Exception:
                    return None
            if hasattr(m, "Materials") and m.Materials:
                return m.Materials[0].Name
            if m.is_a("IfcMaterialProfileSetUsage"):
                try:
                    return m.ForProfileSet.MaterialProfiles[0].Material.Name
                except Exception:
                    return None
    return None


def _placement_matrix(placement) -> np.ndarray:
    try:
        import ifcopenshell.util.placement as up
        return np.array(up.get_local_placement(placement), dtype=float)
    except Exception:
        return np.eye(4)


def _axis_points(el, M: np.ndarray) -> Optional[list[list[float]]]:
    """Start/end of the member axis in world coordinates (mm), from the extruded solid."""
    try:
        import ifcopenshell.util.placement as up
        rep = el.Representation
        if rep is None:
            return None
        for r in rep.Representations:
            for it in r.Items:
                solid = it
                Mi = np.eye(4)
                if it.is_a("IfcMappedItem"):
                    items = it.MappingSource.MappedRepresentation.Items
                    solid = next((x for x in items if x.is_a("IfcExtrudedAreaSolid")), None)
                    if solid is None:
                        continue
                if solid.is_a("IfcExtrudedAreaSolid"):
                    P = np.array(up.get_axis2placement(solid.Position), dtype=float) if solid.Position else np.eye(4)
                    d = np.array(solid.ExtrudedDirection.DirectionRatios, dtype=float)
                    d = d / (np.linalg.norm(d) or 1.0)
                    a = M @ Mi @ P @ np.array([0, 0, 0, 1.0])
                    b = M @ Mi @ P @ np.append(d * float(solid.Depth), 1.0)
                    return [[round(float(a[i]), 1) for i in range(3)], [round(float(b[i]), 1) for i in range(3)]]
    except Exception:
        return None
    return None


def parse(path: Path, with_geometry: bool = True) -> dict[str, Any]:
    """Full parse: every steel element with its quantities and assembly; non-steel elements counted as excluded."""
    import ifcopenshell

    model = ifcopenshell.open(str(path))
    project = model.by_type("IfcProject")
    project_name = project[0].Name if project else None
    app = None
    try:
        a = model.by_type("IfcApplication")
        if a:
            app = f"{a[0].ApplicationFullName} {a[0].Version}"
    except Exception:
        pass

    part_asm: dict[str, Any] = {}
    for asm in model.by_type("IfcElementAssembly"):
        for rel in asm.IsDecomposedBy or []:
            for p in rel.RelatedObjects:
                part_asm[p.GlobalId] = asm

    assemblies: dict[str, dict[str, Any]] = {}
    for asm in model.by_type("IfcElementAssembly"):
        ps = _psets(asm)
        ta = ps.get("Tekla Assembly", {})
        tc = ps.get("Tekla Common", {})
        assemblies[asm.GlobalId] = {
            "guid": asm.GlobalId, "name": asm.Name, "mark": ta.get("Assembly/Cast unit Mark") or asm.Tag,
            "weight": ta.get("Assembly/Cast unit weight"), "position": ta.get("Assembly/Cast unit position code"),
            "phase": tc.get("Phase"), "class": tc.get("Class"),
        }

    elements: list[dict[str, Any]] = []
    excluded: Counter[str] = Counter()
    excluded_materials: Counter[str] = Counter()
    for el in model.by_type("IfcElement"):
        t = el.is_a()
        if t in ("IfcElementAssembly",):
            continue
        if t in ("IfcMechanicalFastener", "IfcFastener"):
            continue
        mat = _material_name(el) or ""
        is_metal_type = t in ("IfcBeam", "IfcColumn", "IfcMember", "IfcPlate", "IfcRailing", "IfcStair",
                              "IfcStairFlight", "IfcDiscreteAccessory", "IfcBuildingElementProxy")
        steel = bool(STEEL_RE.search(mat)) or (not mat and t in ("IfcBeam", "IfcColumn", "IfcMember", "IfcPlate"))
        if NONSTEEL_RE.search(mat):
            steel = False
        if not (is_metal_type and steel):
            excluded[t] += 1
            if mat:
                excluded_materials[mat] += 1
            continue
        ps = _psets(el)
        tq = ps.get("Tekla Quantity", {})
        tc = ps.get("Tekla Common", {})
        bq = ps.get("BaseQuantities", {}) or ps.get("Qto_BeamBaseQuantities", {}) or ps.get("Qto_ColumnBaseQuantities", {})
        weight = tq.get("Weight") or bq.get("NetWeight") or bq.get("GrossWeight")
        if not weight and bq.get("NetVolume"):
            weight = float(bq["NetVolume"]) * 7850
        area = tq.get("Net surface area") or bq.get("OuterSurfaceArea") or bq.get("NetSurfaceArea") or bq.get("GrossSurfaceArea")
        length = tq.get("Length") or bq.get("Length")
        asm = part_asm.get(el.GlobalId)
        rec: dict[str, Any] = {
            "guid": el.GlobalId, "entity": t, "name": el.Name, "profile": (el.Description or el.ObjectType or "").strip(),
            "tag": el.Tag, "material": mat, "grade": re.sub(r"^STEEL/", "", mat, flags=re.I) if mat else None,
            "weight": float(weight) if weight else 0.0, "area": float(area) if area else None,
            "length": float(length) if length else None, "width": tq.get("Width"), "height": tq.get("Height"),
            "phase": tc.get("Phase"), "class": tc.get("Class"),
            "assembly": asm.GlobalId if asm else None,
            "assembly_name": asm.Name if asm else None,
            "assembly_mark": assemblies.get(asm.GlobalId, {}).get("mark") if asm else None,
        }
        if with_geometry:
            M = _placement_matrix(el.ObjectPlacement)
            ax = _axis_points(el, M)
            rec["axis"] = ax
            if ax is None:
                rec["point"] = [round(float(M[i, 3]), 1) for i in range(3)]
        elements.append(rec)

    bolts: list[dict[str, Any]] = []
    fasteners = {f.id(): f for f in model.by_type("IfcMechanicalFastener")}
    try:
        fasteners.update({f.id(): f for f in model.by_type("IfcFastener")})
    except RuntimeError:
        pass
    for f in fasteners.values():
        ps = _psets(f)
        tb = ps.get("Tekla Bolt", {})
        asm = None
        for rel in f.Decomposes or []:
            asm = rel.RelatingObject
        count = tb.get("Bolt count") or 1
        size = tb.get("Bolt size") or getattr(f, "NominalDiameter", None)
        blen = tb.get("Bolt length") or getattr(f, "NominalLength", None)
        bolts.append({"guid": f.GlobalId, "count": int(count or 1), "size": float(size) if size else None,
                      "length": float(blen) if blen else None, "location": tb.get("Location"),
                      "hole": tb.get("Bolt hole diameter"), "standard": tb.get("Bolt standard"),
                      "name": tb.get("Bolt Name") or f.Name, "assembly": asm.GlobalId if asm else None,
                      "washers": tb.get("Washer count"), "nuts": tb.get("Nut count")})

    return {"project_name": project_name, "application": app, "schema": model.schema,
            "elements": elements, "assemblies": assemblies, "bolts": bolts,
            "excluded": dict(excluded), "excluded_materials": dict(excluded_materials)}


def guid_set(path: Path) -> set[str]:
    """GlobalIds of steel parts, read from the STEP text (fast) for version comparison."""
    ids: set[str] = set()
    pat = re.compile(rb"^#\d+\s*=\s*IFC(?:BEAM|COLUMN|MEMBER|PLATE)\('([^']{22})'", re.M)
    with open(path, "rb") as fh:
        for m in pat.finditer(fh.read()):
            ids.add(m.group(1).decode())
    return ids
