"""Build Maru's knowledge file (Excel) from the values derived from Maru's own cost workbooks.

Run:  python scripts/build_knowledge.py            (writes drives/maru/knowledge/Maru_knowledge.xlsx)
      python scripts/build_knowledge.py --verify   (also re-reads Maru's workbooks in ../materials
                                                    and checks every derived value against its cell)

Every row has:
  id      – stable row id used as the reference in reports ("kn" ids)
  status  – derived (copied/fitted from a Maru workbook) | assumed (team assumption, to confirm)
            | placeholder (order-of-magnitude value, to replace with real data, e.g. supplier EPDs)
  source  – workbook + sheet + cell for derived values, or the reasoning for assumed values

The two source workbooks:
  AKK = materials/Example 2 .../02 - Cost calculation/HP11109-1/HK111090-01 - 30480 Akkasæter ... .xlsm (offer 24.10.2025)
  KOT = materials/Example 4 .../02 - Cost calculation/HP11257-3/HK11257-03 - Kotka CAM ... .xlsm        (offer 16.07.2026)
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

DEMO = Path(__file__).resolve().parents[1]
OUT = DEMO / "drives" / "maru" / "knowledge" / "Maru_knowledge.xlsx"

AKK = "AKK (HK111090-01 Akkasæter workbook)"
KOT = "KOT (HK11257-03 Kotka workbook)"
AKK_OFFER = "Akkasæter offer HP11109-1 (24.10.2025)"
KOT_OFFER = "Kotka offer HP11257-3 (16.07.2026)"

LABOUR = 46.0  # €/h, derived

# --------------------------------------------------------------------------------------------
# General
GENERAL = [
    # id, key, description, value, unit, status, source, notes
    ("GEN-01", "labour_rate", "Workshop labour rate (all metalwork hours)", LABOUR, "EUR/h", "derived",
     f"{AKK} Koostamine!F5 'töötasu 46 eur/tund' and formula AN=AL*46; same in {KOT}", "Includes overheads (firmakulu)."),
    ("GEN-02", "steel_density", "Steel density", 7850, "kg/m3", "derived",
     f"{AKK_OFFER} §2g 'Steel density for profiles 7,85'; workbook formulas *7.85/10^6", ""),
    ("GEN-03", "margin_material", "Margin coefficient on material", 1.05, "x", "derived",
     f"{AKK} Koostamine!AU2 'Materjali kasum' (Kotka used 1.10 in AU2)", "Estimator can edit per project."),
    ("GEN-04", "margin_production", "Margin coefficient on production + surface + packaging", 1.05, "x", "derived",
     f"{AKK} Koostamine!AV2 'Tootmise kasum' (Kotka used 1.10 in AV2)", "Estimator can edit per project."),
    ("GEN-05", "margin_special", "Special margin coefficient (not applied by default)", 1.08, "x", "derived",
     f"{AKK} Koostamine!AW2 'ERI kasum'", "Kept for reference."),
    ("GEN-06", "packaging_rate", "Packaging cost", 0.03, "EUR/kg", "derived",
     f"{AKK} Koostamine!AV5 (named range 'pakendus'), formula AV=B*pakendus", ""),
    ("GEN-07", "transport_coefficient", "Coefficient on transport cost", 1.15, "x", "derived",
     f"{AKK} Koostamine!BC2 'Transpordikoeff' (Kotka 1.10 in BB2)", "Regional value in sheet Transport wins."),
    ("GEN-08", "welding_min_per_m", "Welding time per metre of a5-equivalent fillet weld", 10, "min/m", "derived",
     f"{AKK} Koostamine!AK7 formula '=AJ7*10/60'", "Basic principles: weld sizes converted to equivalent a5 length."),
    ("GEN-09", "plate_share_reference", "Plate share of the reference project (Akkasæter)", 0.389, "share", "derived",
     f"{AKK} Koostamine!C8 (plates kg / total kg)", "Kotka C8 = 0.624 (plate-heavy)."),
    ("GEN-10", "uncertainty_extracted", "Uncertainty band for extracted quantities", 0.02, "share", "assumed",
     "Team assumption: values read from IFC/lists are within ±2 %", ""),
    ("GEN-11", "uncertainty_calculated", "Uncertainty band for calculated values", 0.06, "share", "assumed",
     "Team assumption: norm-based hours and areas ±6 %", ""),
    ("GEN-12", "uncertainty_predicted", "Uncertainty band for predicted values (scaled by 1 - confidence)", 0.40, "share", "assumed",
     "Team assumption: a 0.5-confidence prediction is ±20 %", ""),
    ("GEN-13", "uncertainty_rates", "Systematic band on rates (steel price, norms)", 0.03, "share", "assumed",
     "Team assumption", ""),
    ("GEN-14", "conflict_tolerance", "Two sources agree when they differ by less than", 0.01, "share", "assumed",
     "Team assumption: 1 % (e.g. IFC total vs material list total)", ""),
    ("GEN-15", "plate_heavy_threshold", "Plate share above which a job is called plate-heavy", 0.5, "share", "assumed",
     "Guide §2: Kotka skybridge 62 % plates has the highest price", ""),
    ("GEN-16", "plate_share_hours_slope", "Extra hours per tonne for each +10 % plate share (quick method)", 3.7, "h/t", "derived",
     f"Fitted from the two projects: {AKK} 12.1 h/t at 38.9 % plates vs {KOT} 20.6 h/t at 62.4 % plates", "Two data points only."),
    ("GEN-17", "price_list_policy", "Steel price list used", "newest list on or before the inquiry date", "", "assumed",
     "Keeps historical projects comparable with Maru's offers; set to 'newest' for live quotes", ""),
    ("GEN-18", "workshop_country", "Workshop country (labour rate row)", "EE", "", "derived", "Maru Metall AS, Ardu, Estonia", ""),
]

LABOUR_RATES = [
    ("LAB-EE", "EE", LABOUR, "Workshop (Maru, Ardu)", "derived", f"{AKK} Koostamine!F5", "Estonian labour: the key cost driver"),
    ("LAB-LV", "LV", 34.0, "Subcontractor option", "assumed", "Placeholder for a Latvian subcontractor rate", "Replace with Maru's subcontractor quotes"),
    ("LAB-LT", "LT", 33.0, "Subcontractor option", "assumed", "Placeholder for a Lithuanian subcontractor rate", "Replace with Maru's subcontractor quotes"),
    ("LAB-PL", "PL", 31.0, "Subcontractor option", "assumed", "Placeholder for a Polish subcontractor rate", "Replace with Maru's subcontractor quotes"),
]

# Steel price lists (item, €/kg, waste factor 'Kulunormid', source cell)
AKK_PRICES = [["CFCHS168.3x4.5", 0.9, 1.1, "Terasehind!A2:C2"], ["CFCHS42.4x3.2", 0.85, 1.1, "Terasehind!A3:C3"], ["CFRHS100x100x6", 0.74, 1.05, "Terasehind!A4:C4"], ["CFRHS120x120x10", 0.79, 1.1, "Terasehind!A5:C5"], ["CFRHS120x120x8", 0.78, 1.1, "Terasehind!A6:C6"], ["CFRHS150x100x6", 0.74, 1.1, "Terasehind!A7:C7"], ["CFRHS150x150x6", 0.74, 1.1, "Terasehind!A8:C8"], ["CFRHS150x150x8", 0.78, 1.1, "Terasehind!A9:C9"], ["CFRHS180x180x10", 0.79, 1.1, "Terasehind!A10:C10"], ["CFRHS180x180x8", 0.78, 1.1, "Terasehind!A11:C11"], ["HEB360", 0.9, 1.05, "Terasehind!A12:C12"], ["IPE120", 0.78, 1.1, "Terasehind!A13:C13"], ["IPE240", 0.78, 1.1, "Terasehind!A14:C14"], ["IPE400", 0.9, 1.1, "Terasehind!A15:C15"], ["IPE600", 1.05, 1.1, "Terasehind!A16:C16"], ["L100x10", 0.98, 1.1, "Terasehind!A17:C17"], ["L120x11", 0.98, 1.1, "Terasehind!A18:C18"], ["L60x40x6", 0.98, 1.1, "Terasehind!A19:C19"], ["leht 4", 0.75, 1.1, "Terasehind!A42:C42"], ["leht 5", 0.74, 1.1, "Terasehind!A43:C43"], ["leht 6", 0.74, 1.1, "Terasehind!A44:C44"], ["leht 8", 0.74, 1.1, "Terasehind!A45:C45"], ["leht 10", 0.74, 1.1, "Terasehind!A46:C46"], ["leht 12", 0.74, 1.1, "Terasehind!A47:C47"], ["leht 15", 0.74, 1.1, "Terasehind!A48:C48"], ["Leht 16", 0.74, 1.1, "Terasehind!A49:C49"], ["Leht 20", 0.74, 1.1, "Terasehind!A50:C50"], ["Leht 22", 0.74, 1.1, "Terasehind!A51:C51"], ["Leht 25", 0.74, 1.1, "Terasehind!A52:C52"], ["Leht 30", 0.74, 1.1, "Terasehind!A53:C53"], ["Leht 35", 1.19, 1.1, "Terasehind!A54:C54"], ["Leht 40", 1.19, 1.1, "Terasehind!A55:C55"], ["leht 45", 1.19, 1.1, "Terasehind!A56:C56"], ["Leht 50", 1.19, 1.1, "Terasehind!A57:C57"]]
KOT_PRICES = [["CFRHS100x100x3", 0.92, 1.1, "Terasehind!A2:C2"], ["CFRHS100x100x4", 0.92, 1.1, "Terasehind!A3:C3"], ["CFRHS100x40x3", 0.92, 1.1, "Terasehind!A4:C4"], ["CFRHS100x50x5", 0.92, 1.1, "Terasehind!A5:C5"], ["CFRHS100x80x3", 0.92, 1.1, "Terasehind!A6:C6"], ["CFRHS120x120x4", 0.92, 1.1, "Terasehind!A7:C7"], ["CFRHS120x120x5", 0.92, 1.1, "Terasehind!A8:C8"], ["CFRHS140x140x5", 0.92, 1.1, "Terasehind!A9:C9"], ["CFRHS150x100x3", 0.92, 1.1, "Terasehind!A10:C10"], ["CFRHS150x150x5", 0.92, 1.1, "Terasehind!A11:C11"], ["CFRHS150x50x3", 0.92, 1.1, "Terasehind!A12:C12"], ["CFRHS160x160x6", 0.94, 1.1, "Terasehind!A13:C13"], ["CFRHS160x160x8", 0.98, 1.1, "Terasehind!A14:C14"], ["CFRHS180x180x8", 0.98, 1.1, "Terasehind!A15:C15"], ["CFRHS200x100x5", 0.94, 1.1, "Terasehind!A16:C16"], ["CFRHS200x200x5", 0.94, 1.1, "Terasehind!A17:C17"], ["CFRHS200x200x6", 0.98, 1.1, "Terasehind!A18:C18"], ["CFRHS200x200x8", 0.98, 1.1, "Terasehind!A19:C19"], ["CFRHS250x150x5", 0.94, 1.1, "Terasehind!A20:C20"], ["CFRHS250x250x8", 0.98, 1.1, "Terasehind!A21:C21"], ["CFRHS300x300x10", 1.08, 1.1, "Terasehind!A22:C22"], ["HEA200", 0.88, 1.1, "Terasehind!A23:C23"], ["HEA240", 0.88, 1.1, "Terasehind!A24:C24"], ["HEA260", 0.88, 1.1, "Terasehind!A25:C25"], ["HEA320", 0.9, 1.1, "Terasehind!A26:C26"], ["HEA340", 0.9, 1.1, "Terasehind!A27:C27"], ["IPE240", 0.88, 1.1, "Terasehind!A28:C28"], ["IPE550", 0.95, 1.13, "Terasehind!A29:C29"], ["L100x10", 1, 1.1, "Terasehind!A30:C30"], ["L150x15", 1, 1.1, "Terasehind!A31:C31"], ["L200x100x10", 1, 1.1, "Terasehind!A32:C32"], ["T120", 1.4, 1.1, "Terasehind!A33:C33"], ["T140", 1.4, 1.1, "Terasehind!A34:C34"], ["T70", 1.4, 1.1, "Terasehind!A35:C35"], ["UNP260", 0.95, 1.1, "Terasehind!A36:C36"], ["UPE200", 0.95, 1.1, "Terasehind!A37:C37"], ["leht 4", 0.92, 1.1, "Terasehind!A44:C44"], ["leht 5", 0.92, 1.1, "Terasehind!A45:C45"], ["leht 6", 0.92, 1.1, "Terasehind!A46:C46"], ["leht 8", 0.92, 1.1, "Terasehind!A47:C47"], ["leht 10", 0.92, 1.1, "Terasehind!A48:C48"], ["leht 12", 0.92, 1.1, "Terasehind!A49:C49"], ["leht 15", 0.92, 1.1, "Terasehind!A50:C50"], ["Leht 16", 0.92, 1.1, "Terasehind!A51:C51"], ["Leht 20", 0.92, 1.1, "Terasehind!A52:C52"], ["Leht 22", 0.92, 1.1, "Terasehind!A53:C53"], ["Leht 25", 0.92, 1.1, "Terasehind!A54:C54"], ["Leht 30", 0.92, 1.1, "Terasehind!A55:C55"], ["Leht 35", 1.37, 1.1, "Terasehind!A56:C56"], ["Leht 40", 1.37, 1.1, "Terasehind!A57:C57"], ["leht 45", 1.37, 1.1, "Terasehind!A58:C58"], ["Leht 50", 1.37, 1.1, "Terasehind!A59:C59"], ["Leht 60", 1.37, 2.1, "Terasehind!A60:C60"], ["Leht 70", 1.37, 3.1, "Terasehind!A61:C61"]]

# Family fallbacks per price list (used when an exact item is not in the list).
# (family, size_from, size_to, €/kg, waste, how derived)
AKK_FAMILY = [
    ("RHS", None, None, 0.76, 1.10, "median of CFRHS items in AKK Terasehind A4:A11"),
    ("CHS", None, None, 0.90, 1.10, "AKK Terasehind A2 CFCHS168.3x4.5"),
    ("IPE", None, None, 0.85, 1.10, "median of IPE items AKK Terasehind A13:A16"),
    ("HEA", None, None, 0.87, 1.10, "AKK Terasehind T8:V16 (Elme list 02.10.2025: HEA 0.855-0.875)"),
    ("HEB", None, None, 0.90, 1.05, "AKK Terasehind A12 HEB360"),
    ("HEM", None, None, 1.10, 1.10, "AKK Terasehind T15:V16 (Elme HEM 1.10-1.12)"),
    ("UPE", None, None, 0.92, 1.10, "AKK Terasehind E31 UPE160 0.92"),
    ("UNP", None, None, 0.90, 1.10, "AKK Terasehind I29 UNP200 0.895"),
    ("L", None, None, 0.98, 1.10, "AKK Terasehind A17:A19"),
    ("T", None, None, 1.10, 1.10, "AKK Terasehind N41 T120 1.1"),
    ("FL", 0, 30, 0.74, 1.10, "flat bars priced as plates, AKK Terasehind A43:A53"),
    ("PL", 0, 30, 0.74, 1.10, "AKK Terasehind A42:A53 'leht 4-30'"),
    ("PL", 31, 50, 1.19, 1.10, "AKK Terasehind A54:A57 'Leht 35-50'"),
    ("PL", 51, 200, 1.19, 1.25, "no AKK price above 50 mm: 50 mm price, waste assumed"),
    ("D", None, None, 0.85, 1.10, "round bars: assumed close to CHS/L (AKK has no D30 price row)"),
    ("WI", None, None, 0.74, 1.10, "welded sections priced as their plates"),
    ("*", None, None, 0.80, 1.10, "fallback: average of the AKK list"),
]
KOT_FAMILY = [
    ("RHS", None, None, 0.94, 1.10, "median of CFRHS items KOT Terasehind A2:A22"),
    ("CHS", None, None, 0.94, 1.10, "assumed equal to RHS (no CHS in KOT list)"),
    ("IPE", None, None, 0.92, 1.10, "KOT Terasehind A28:A29"),
    ("HEA", None, None, 0.89, 1.10, "KOT Terasehind A23:A27"),
    ("HEB", None, None, 0.90, 1.10, "assumed equal to HEA 320-340"),
    ("HEM", None, None, 1.10, 1.10, "assumed (no HEM in KOT list)"),
    ("UPE", None, None, 0.95, 1.10, "KOT Terasehind A37"),
    ("UNP", None, None, 0.95, 1.10, "KOT Terasehind A36"),
    ("L", None, None, 1.00, 1.10, "KOT Terasehind A30:A32"),
    ("T", None, None, 1.40, 1.10, "KOT Terasehind A33:A35"),
    ("FL", 0, 30, 0.92, 1.10, "flat bars priced as plates, KOT Terasehind A44:A55"),
    ("PL", 0, 30, 0.92, 1.10, "KOT Terasehind A44:A55 'leht 4-30'"),
    ("PL", 31, 50, 1.37, 1.10, "KOT Terasehind A56:A59 'Leht 35-50'"),
    ("PL", 51, 200, 1.37, 1.25, "KOT Terasehind A60:A61 (waste 2.1-3.1 there; 1.25 assumed for nesting)"),
    ("D", None, None, 1.00, 1.10, "assumed close to L"),
    ("WI", None, None, 0.92, 1.10, "welded sections priced as their plates"),
    ("*", None, None, 0.95, 1.10, "fallback: average of the KOT list"),
]

WASTE = [
    # id, key, applies_to, t_from, t_to, value, unit, status, source, notes
    ("WST-01", "stock_length", "profiles", None, None, 12000, "mm", "assumed", "Standard mill length 12 m", "Used by the 1D nesting estimate"),
    ("WST-02", "stock_length_long", "profiles longer than 12 m", None, None, 15000, "mm", "assumed", "15 m stock for long members (roof beams 14.9 m in Akkasæter)", ""),
    ("WST-03", "stock_length_xl", "profiles longer than 15 m", None, None, 18000, "mm", "assumed", "18 m stock", ""),
    ("WST-04", "saw_kerf", "profiles", None, None, 5, "mm", "assumed", "Band saw kerf", ""),
    ("WST-05", "min_reusable_offcut", "profiles", None, None, 1000, "mm", "assumed", "Offcuts shorter than 1 m are scrap", "Longer offcuts go to remnant stock"),
    ("WST-06", "profile_waste_floor", "profiles", None, None, 1.03, "x", "assumed", "Minimum profile factor (end cuts, damage)", ""),
    ("WST-07", "profile_waste_cap", "profiles", None, None, 1.15, "x", "assumed", "Maximum factor applied from nesting", ""),
    ("WST-10", "plate_waste", "plates", 0, 10, 1.08, "x", "assumed", "Thin plates nest well (small details, many per sheet)", ""),
    ("WST-11", "plate_waste", "plates", 11, 30, 1.10, "x", "derived", f"{AKK} and {KOT} Terasehind column C 'Kulunormid' = 1.1 for 'leht 4-30'", ""),
    ("WST-12", "plate_waste", "plates", 31, 50, 1.15, "x", "assumed", "Thick plates: fewer parts per sheet; Maru list says 1.1, raised for nesting", "Confirm with Maru"),
    ("WST-13", "plate_waste", "plates", 51, 200, 1.25, "x", "assumed", f"{KOT} Terasehind C60:C61 uses 2.1-3.1 for 60-70 mm (special purchase); 1.25 assumed", ""),
    ("WST-20", "waste_benchmark", "project", None, None, 0.075, "share", "derived", "Guide §5: Maru's workbooks add 5-10 % (1.05-1.10); midpoint", "Flag 'Waste above benchmark' when exceeded"),
]

CUTTING = [
    # thickness, speed mm/min, pierce s, status, source
    (3, 4000, 7.0, "derived", "fitted from KOT plate rows (n=4)"),
    (4, 3800, 7.5, "assumed", "interpolated between 3 and 5 mm"),
    (5, 3600, 8.0, "derived", "fitted from plate rows of both workbooks (n=39)"),
    (6, 3500, 8.0, "derived", "fitted (n=2)"),
    (8, 3000, 8.0, "derived", "fitted (n=19)"),
    (10, 2500, 8.0, "derived", "fitted (n=60)"),
    (12, 2000, 8.5, "derived", "fitted (n=15)"),
    (15, 1800, 9.0, "derived", "fitted (n=77)"),
    (16, 1750, 9.5, "assumed", "interpolated"),
    (20, 1600, 12.0, "derived", "fitted (n=20)"),
    (25, 1400, 18.0, "derived", "fitted (n=19)"),
    (30, 1200, 20.0, "derived", "fitted (n=19)"),
    (35, 900, 20.0, "derived", "fitted (n=2)"),
    (40, 800, 20.0, "derived", "fitted (n=4)"),
    (50, 600, 25.0, "assumed", "extrapolated"),
    (60, 450, 30.0, "assumed", "extrapolated"),
]

TIME_NORMS = [
    # id, operation, applies_to, unit, norm, norm_unit, rule, status, source, notes
    ("TN-CUT", "Plasma cutting", "plates", "m of cut edge", 5, "x pure cutting time",
     "hours = edge_m x 5 / (speed_mm_min x 0.06) + holes x 5 x pierce_s / 3600", "derived",
     f"{AKK} Koostamine!AC22 '=(((H+J)*2/1000)*L*(5/(speed/1000*60)))+(Q*L*(5*pierce)/60/60)'", "Speeds in sheet Cutting_speeds"),
    ("TN-CLN", "Edge cleaning", "plates", "m of cut edge", 0.012, "h/m",
     "hours = edge_m x 0.012", "derived", f"{AKK} Koostamine!AD22 '=0.012*((H+J)*2/1000*L)'", "0.72 min per metre"),
    ("TN-SAW", "Profile sawing", "profiles", "cut", 20, "mm of section height per min",
     "hours = 2 cuts x height_mm / 20 / 60 per piece", "derived", f"{AKK} Koostamine!AE21 '=(H/20/60)*2*L'", ""),
    ("TN-DRL", "Drilling profiles", "profiles", "hole", 0.5, "min/hole",
     "hours = holes x 0.5 / 60", "derived", f"{AKK} Koostamine!AG21 '=Q*L*0.5/60'", ""),
    ("TN-DRP", "Drilling plates >= 35 mm", "plates", "hole", None, "min/hole (sheet Drilling)",
     "plates < 35 mm: holes are plasma cut (pierce time)", "derived", f"{AKK} Koostamine!AG22 thickness bands", ""),
    ("TN-BEV", "Bevels and cut-outs", "profile ends", "m of end perimeter", 20, "min/m",
     "hours = 2 ends x section perimeter_m x 20 / 60 x bevel share of the category", "derived",
     f"{AKK} Koostamine!AF5 '10/20.' min/jm; AF47=9.6 h for 20 pcs CFRHS180x180 (=2 x 0.72 m x 20 min)", "Bevel share per category in sheet Categories"),
    ("TN-FIT", "Fitting / assembly", "every part", "part", None, "min/part (sheet Handling)",
     "plates by weight band and holes; profiles by length band", "derived", f"{AKK} Koostamine!AL22, AL23, AL21", ""),
    ("TN-WLD", "Welding", "a5-equivalent weld", "m", 10, "min/m",
     "hours = weld_m x 10 / 60", "derived", f"{AKK} Koostamine!AK7 '=AJ7*10/60'", ""),
    ("TN-WPE", "Weld length: profile ends", "profiles in assemblies", "m", None, "",
     "hollow / round: 4 x height per end; I/H: 6 x height per end; 2 ends", "derived",
     f"{AKK} Koostamine!AJ21 '=(H*4*AK)*2*L/1000', AJ109 '=(H*6*AK)*2*L/1000'", "AK factor = 1 assumed"),
    ("TN-WEF", "End-weld size factor", "profile ends and welded secondary profiles", "factor", 0.7, "x wall thickness = throat a",
     "a = 0.7 × wall/flange thickness; length × (a/5)², at least 1, at most 12", "derived",
     f"Consistent with the weld multipliers in {AKK} Koostamine column AK: 1 (RHS t6), 3 (RHS t8), 6 (RHS t10), 12 (HEB360)",
     "Full-strength end welds grow with the wall thickness"),
    ("TN-WPL", "Weld length: attached plates", "plates in assemblies (not end plates)", "m", 2, "x plate length",
     "weld_m = 2 x longest side", "derived", f"{AKK} Koostamine!AJ23 '=(J*2*AK)*1*L/1000' with AK=1", "End plates with bolt holes are welded via the profile end weld"),
    ("TN-WBU", "Weld length: built-up sections", "welded I / WQ / HSQ sections", "m", 4, "x member length",
     "weld_m = 4 x length x (a/5)^2 with a = 0.5 x web thickness, between a4 and a8", "assumed",
     f"{AKK_OFFER} §2h 'For built-up profiles we assume fillet welding with <= a6'", "Two fillets per flange; Maru's weld-size table would replace this"),
    ("TN-A5", "a5 equivalence", "weld sizes", "", 2, "exponent",
     "equivalent_length = length x (a / 5)^2", "assumed", "Weld metal volume grows with a²; basic principles row 12", ""),
    ("TN-BLA", "Blasting", "painted area", "m2", 2.4, "min/m2",
     "hours = area x 2.4 / 60 (costed inside the surface treatment rate)", "assumed", "Calibrated with Paint_systems so the bottom-up rate matches Maru's all-in rate", ""),
    ("TN-GAL", "Galvanising handling", "HDG steel", "t", 1.5, "h/t",
     "hours = tonnes x 1.5 (jigging, loading for the galvaniser; costed in the HDG rate)", "assumed", "Team assumption", ""),
    ("TN-PCK", "Packaging", "all steel", "t", 0.4, "h/t",
     "hours = tonnes x 0.4 (costed in the packaging rate 0.03 €/kg)", "assumed", "Team assumption, consistent with 0.03 €/kg", ""),
    ("TN-LOD", "Loading", "trucks", "truck", 1.5, "h/truck",
     "hours = trucks x 1.5 (costed in transport)", "assumed", "Team assumption", ""),
]

HANDLING = [
    # id, part_type, band_from, band_to, unit, with_holes_min, without_holes_min, status, source
    ("HDL-P1", "plate", 0, 3, "kg", 10, 2, "derived", f"{AKK} Koostamine!AL23 rule"),
    ("HDL-P2", "plate", 3, 10, "kg", 15, 5, "derived", f"{AKK} Koostamine!AL23 rule"),
    ("HDL-P3", "plate", 10, 20, "kg", 20, 10, "derived", f"{AKK} Koostamine!AL23 rule"),
    ("HDL-P4", "plate", 20, 500, "kg", 30, 20, "derived", f"{AKK} Koostamine!AL23 rule"),
    ("HDL-P5", "plate", 500, 100000, "kg", 60, 40, "assumed", "Above 500 kg: crane handling, assumed"),
    ("HDL-R1", "profile", 0, 1500, "mm", 5, 5, "derived", "Mode of profile rows in both workbooks (AL column)"),
    ("HDL-R2", "profile", 1500, 3000, "mm", 5, 5, "derived", "Mode of profile rows in both workbooks"),
    ("HDL-R3", "profile", 3000, 6000, "mm", 20, 20, "derived", "Mode of profile rows in both workbooks"),
    ("HDL-R4", "profile", 6000, 10000, "mm", 30, 30, "derived", "Mode of profile rows in both workbooks"),
    ("HDL-R5", "profile", 10000, 100000, "mm", 90, 90, "derived", f"{AKK} HEB360/IPE400 11.9 m rows: 90 min"),
]

DRILLING = [
    ("DRP-1", "plate", 0, 34, 0, "derived", f"{AKK} Koostamine!AG22: < 35 mm -> 0 (holes plasma cut)"),
    ("DRP-2", "plate", 35, 39, 3, "derived", f"{AKK} Koostamine!AG22"),
    ("DRP-3", "plate", 40, 49, 4, "derived", f"{AKK} Koostamine!AG22"),
    ("DRP-4", "plate", 50, 59, 5, "derived", f"{AKK} Koostamine!AG22"),
    ("DRP-5", "plate", 60, 69, 6, "derived", f"{AKK} Koostamine!AG22"),
    ("DRP-6", "plate", 70, 79, 7, "derived", f"{AKK} Koostamine!AG22"),
    ("DRP-7", "plate", 80, 89, 8, "derived", f"{AKK} Koostamine!AG22"),
    ("DRP-8", "plate", 90, 99, 9, "derived", f"{AKK} Koostamine!AG22"),
    ("DRP-9", "plate", 100, 1000, 10, "derived", f"{AKK} Koostamine!AG22"),
]

SURFACE_RATES = [
    ("SUR-NON", "none", 0, "EUR/m2", "derived", f"{AKK} Koostamine!AB1:AB2", ""),
    ("SUR-C1", "C1", 9, "EUR/m2", "derived", f"{AKK} Koostamine!AC1:AC2", "Price does not include Zn(R) primer (AC3)"),
    ("SUR-C2M", "C2M", 13, "EUR/m2", "derived", f"{AKK} Koostamine!AD1:AD2", ""),
    ("SUR-C2H", "C2H", 15.5, "EUR/m2", "derived", f"{AKK} Koostamine!AE1:AE2", ""),
    ("SUR-C3M", "C3M", 15.5, "EUR/m2", "derived", f"{AKK} Koostamine!AF1:AF2", ""),
    ("SUR-C3H", "C3H", 18.5, "EUR/m2", "derived", f"{AKK} Koostamine!AG1:AG2", ""),
    ("SUR-C3VH", "C3VH", 20, "EUR/m2", "derived", f"{KOT} Koostamine!AJ1:AJ2 (system C3.07 EPPUR 240/2)", ""),
    ("SUR-C4M", "C4M", 18.5, "EUR/m2", "derived", f"{AKK} Koostamine!AH1:AH2", ""),
    ("SUR-C4H", "C4H", 21.5, "EUR/m2", "derived", f"{AKK} Koostamine!AI1:AI2", "P3 surface prep from C4H (AL1)"),
    ("SUR-C5M", "C5M", 25, "EUR/m2", "derived", f"{AKK} Koostamine!AJ1:AJ2", ""),
    ("SUR-HDG", "HDG", 0.72, "EUR/kg", "derived", f"{AKK} Koostamine!AK1:AK2 (HDG, priced per kg)", "ISO 1461"),
]

# Paint systems: two products (primer, top coat). DFT per coat in µm.
# ISO 12944-5 style typical systems (assumed) except where the drawings name the system (Kotka).
PAINT_SYSTEMS_BASE = [
    # id, system, corrosivity, durability, p1 name, p1 coats, p1 dft, p2 name, p2 coats, p2 dft, status, source
    ("PS-C1", "C1", "C1", "-", "Epoxy primer (EP)", 1, 60, "", 0, 0, "assumed", "Typical 1-coat primer"),
    ("PS-C2M", "C2M", "C2", "M", "Epoxy primer (EP)", 1, 60, "Polyurethane top coat (PUR)", 1, 60, "assumed", "Typical ISO 12944-5 C2/M, 120 µm"),
    ("PS-C2H", "C2H", "C2", "H", "Epoxy primer (EP)", 1, 80, "Polyurethane top coat (PUR)", 1, 80, "assumed", "Typical C2/H, 160 µm"),
    ("PS-C3M", "C3M", "C3", "M", "Epoxy primer (EP)", 1, 80, "Polyurethane top coat (PUR)", 1, 80, "assumed", "Typical C3/M, 160 µm"),
    ("PS-C3H", "C3H", "C3", "H", "Epoxy primer (EP)", 1, 100, "Polyurethane top coat (PUR)", 1, 100, "assumed", "Typical C3/H, 200 µm"),
    ("PS-C3VH", "C3VH", "C3", "VH", "Epoxy primer (EP)", 1, 120, "Polyurethane top coat (PUR)", 1, 120, "derived",
     "Kotka drawings: 'C3.07, EPPUR 240/2' (240 µm, 2 coats)"),
    ("PS-C4M", "C4M", "C4", "M", "Epoxy primer (EP)", 1, 120, "Polyurethane top coat (PUR)", 1, 80, "assumed", "Typical C4/M, 200 µm"),
    ("PS-C4H", "C4H", "C4", "H", "Epoxy primer (EP)", 2, 80, "Polyurethane top coat (PUR)", 1, 80, "derived",
     "Kotka drawings: 'C4.06 EPPUR 240/3' (240 µm, 3 coats)"),
    ("PS-C5M", "C5M", "C5", "M", "Epoxy primer (EP)", 2, 120, "Polyurethane top coat (PUR)", 1, 80, "assumed", "Typical C5/M, 320 µm"),
]
PAINT_PRODUCTS = {  # name -> (volume solids, €/l)
    "Epoxy primer (EP)": (0.60, 8.5),
    "Polyurethane top coat (PUR)": (0.55, 11.0),
}
PAINT_LOSS = 1.6        # assumed spray loss factor on structural steel
BLAST_MIN = 2.4         # min/m², assumed (TN-BLA)
BLAST_ABRASIVE = 1.0    # €/m², assumed abrasive + energy


def litres_per_m2(product: str, dft: float) -> float:
    vs, _ = PAINT_PRODUCTS[product]
    return dft / (1000.0 * vs) * PAINT_LOSS  # l/m² per coat incl. spray loss


def paint_rows():
    """Calibrate painting minutes per coat so the bottom-up rate equals Maru's all-in rate."""
    all_in = {r[1]: r[2] for r in SURFACE_RATES}
    out = []
    for (pid, system, corr, dur, p1, c1, d1, p2, c2, d2, status, source) in PAINT_SYSTEMS_BASE:
        coats = c1 + c2
        mat = 0.0
        l1 = litres_per_m2(p1, d1) * c1 if c1 else 0.0
        mat += l1 * PAINT_PRODUCTS[p1][1] if c1 else 0.0
        l2 = litres_per_m2(p2, d2) * c2 if c2 else 0.0
        mat += l2 * PAINT_PRODUCTS[p2][1] if c2 else 0.0
        blasting = BLAST_MIN / 60.0 * LABOUR + BLAST_ABRASIVE
        target = all_in[system]
        labour_eur = max(target - blasting - mat, 0.5)
        min_per_coat = round(labour_eur / LABOUR * 60.0 / max(coats, 1), 2)
        bottom_up = blasting + mat + min_per_coat * coats / 60.0 * LABOUR
        out.append(dict(
            id=pid, system=system, corrosivity=corr, durability=dur, coats=coats, dft_total_um=c1 * d1 + c2 * d2,
            p1_name=p1, p1_coats=c1, p1_dft_um=d1, p1_volume_solids=PAINT_PRODUCTS[p1][0], p1_eur_per_l=PAINT_PRODUCTS[p1][1],
            p2_name=p2, p2_coats=c2, p2_dft_um=d2, p2_volume_solids=PAINT_PRODUCTS[p2][0] if p2 else None,
            p2_eur_per_l=PAINT_PRODUCTS[p2][1] if p2 else None, loss_factor=PAINT_LOSS,
            painting_min_per_m2_per_coat=min_per_coat, blasting_min_per_m2=BLAST_MIN, blasting_material_eur_per_m2=BLAST_ABRASIVE,
            maru_all_in_eur_per_m2=target, bottom_up_eur_per_m2=round(bottom_up, 2),
            check_vs_maru=round(bottom_up / target - 1, 4), status=status if status == "derived" else "assumed",
            source=(source + "; products, loss factor and €/l assumed; painting minutes calibrated to Maru's all-in rate "
                    f"(sheet Surface_rates)"),
        ))
    return out


FIRE = [
    # id, rating, layers, material €/m²/layer, labour €/m²/layer, topcoat €/m², margin, µm/layer, status, source
    ("FP-R30", "R30", 1, 15.51, 3.15, 5.3, 1.1, 550, "assumed", f"Rates from {KOT} sheet Tuletõke D3:D7 (FX2007); 1 layer assumed for R30"),
    ("FP-R60", "R60", 2, 15.51, 3.15, 5.3, 1.1, 550, "derived", f"{KOT} sheet Tuletõke D2:D7 and F12 (2 layers for CFRHS200x200x10)"),
    ("FP-R90", "R90", 3, 15.51, 3.15, 5.3, 1.1, 550, "assumed", f"Same rates; 3 layers assumed. {AKK} hidden sheet 'Tuletõkke R90' uses 16-24 €/m² x 1.2"),
]

TRANSPORT = [
    # id, region, countries, keywords, truck_type, max_length_m, €/truck, payload_kg, coefficient, distance_km, status, source
    ("TR-NON-S", "Norway north", "NO", "Målselv;Moen;Bardufoss;Troms;Tromsø;Narvik;Nordland;Finnmark;Akkasæter", "standard", 13.5, 3300, 18500, 1.15, 2400, "derived", f"{AKK} Koostamine!BC3 (13.5 m), BC2 coefficient; '1500 km Oslost'"),
    ("TR-NON-L", "Norway north", "NO", "", "long", 15.0, 4000, 18500, 1.15, 2400, "derived", f"{AKK} Koostamine!BD3 (15 m)"),
    ("TR-NON-X", "Norway north", "NO", "", "special", 20.0, 5000, 18500, 1.15, 2400, "assumed", "No Maru value for 20 m to northern Norway"),
    ("TR-NO-S", "Norway south", "NO", "", "standard", 13.5, 2600, 18500, 1.15, 1300, "assumed", "Placeholder: Oslo area"),
    ("TR-NO-L", "Norway south", "NO", "", "long", 15.0, 3200, 18500, 1.15, 1300, "assumed", "Placeholder"),
    ("TR-NO-X", "Norway south", "NO", "", "special", 20.0, 4200, 18500, 1.15, 1300, "assumed", "Placeholder"),
    ("TR-FI-S", "Finland south", "FI", "Kotka;Helsinki;Espoo;Vantaa;Hamina;Porvoo", "standard", 13.5, 850, 18500, 1.10, 230, "derived", f"{KOT} Koostamine!BB3 and BB2 coefficient 1.1"),
    ("TR-FI-L", "Finland south", "FI", "", "long", 15.0, 2040, 18500, 1.10, 230, "derived", f"{KOT} Koostamine!BC3"),
    ("TR-FI-X", "Finland south", "FI", "", "special", 20.0, 2450, 18500, 1.10, 230, "derived", f"{KOT} Koostamine!BD3"),
    ("TR-SE-S", "Sweden", "SE", "", "standard", 13.5, 2200, 18500, 1.15, 900, "assumed", "Placeholder"),
    ("TR-SE-L", "Sweden", "SE", "", "long", 15.0, 2800, 18500, 1.15, 900, "assumed", "Placeholder"),
    ("TR-SE-X", "Sweden", "SE", "", "special", 20.0, 3800, 18500, 1.15, 900, "assumed", "Placeholder"),
    ("TR-EE-S", "Estonia", "EE", "", "standard", 13.5, 450, 18500, 1.10, 80, "assumed", "Placeholder"),
    ("TR-EE-L", "Estonia", "EE", "", "long", 15.0, 900, 18500, 1.10, 80, "assumed", "Placeholder"),
    ("TR-EE-X", "Estonia", "EE", "", "special", 20.0, 1400, 18500, 1.10, 80, "assumed", "Placeholder"),
]

FASTENERS = [
    ("FAS-01", "Bolts, nuts, washers (steel-to-steel)", "EUR/kg", 6.5, None, 1.1, "derived", f"{AKK} Pakkumistabel!L18 6.5 EUR/kg and Q18 1.1", ""),
    ("FAS-02", "Hilti anchor HUS4-HF", "EUR/pc", 6.23, 16, 1.0, "derived", f"{AKK} Pakkumistabel!H17 935 € / 150 pcs (85 €/pack of 16, L17:O17)", ""),
    ("FAS-03", "Bolt head + nut + 2 washers mass factor", "kg/mm3", 2.5e-5, None, None, "assumed", "mass = 7.85e-6 x pi/4 x d² x L + 2.5e-5 x d³", "Shank from geometry"),
    ("FAS-04", "Welding consumables", "included", 0, None, None, "derived", "Not a separate line in Maru's workbooks: inside the labour rate", ""),
]

# Quick method references per category (from Maru's two workbooks; €/t and h/t)
PRICE_PER_TONNE = [
    # id, category, ref project, plate share, m2/t, h/t, material €/t, production €/t, surface €/t, sale €/t, steel €/kg, margins, surface system, status, source
    ("PPT-COL", "Columns", "Akkasæter", 0.64, 20.4, 15.8, 830, 726, 265, 1944, 0.74, 1.05, "C2M", "derived", f"{AKK} Koostamine row 16 (Columns)"),
    ("PPT-WCOL", "Welded columns", "Kotka", 0.92, 10.0, 23.8, 1373, 1094, 200, 2966, 0.92, 1.10, "C3VH", "derived", f"{KOT} Koostamine row 16 (WI columns)"),
    ("PPT-BEA", "Beams", "Akkasæter", 0.31, 18.2, 9.7, 943, 445, 236, 1737, 0.74, 1.05, "C2M", "derived", f"{AKK} Koostamine row 95 (Beams)"),
    ("PPT-WBEA", "Welded beams", "Akkasæter", 1.00, 14.2, 15.0, 1003, 689, 128, 1989, 0.74, 1.05, "C2M", "derived", f"{AKK} Koostamine row 82 (WQ beams)"),
    ("PPT-BRA", "Bracings", "Akkasæter", 0.13, 20.6, 14.1, 804, 649, 268, 1838, 0.74, 1.05, "C2M", "derived", f"{AKK} Koostamine row 136 (Bracings)"),
    ("PPT-ROD", "Tension rods", "Akkasæter", 0.04, 21.4, 9.8, 1473, 451, 249, 2313, 0.74, 1.05, "HDG", "derived", f"{AKK} Koostamine row 214/217 (D30 with turnbuckles); sale = 17 564 € / 7.59 t"),
    ("PPT-FRA", "Frames", "Akkasæter", 0.08, 22.6, 14.0, 783, 643, 293, 1837, 0.74, 1.05, "C2M", "derived", f"{AKK} Koostamine row 163 (Window- and door frames)"),
    ("PPT-SMA", "Plates and small parts", "Kotka", 0.97, 27.5, 41.5, 1026, 1907, 550, 3865, 0.92, 1.10, "C3VH", "derived", f"{KOT} Koostamine row 428 (Erection plates)"),
    ("PPT-STA", "Stairs and railings", "-", 0.30, 35.0, 35.0, 900, 1610, 455, 3400, 0.74, 1.05, "C2M", "assumed", "No Maru reference: assumed from small-parts productivity"),
    ("PPT-GRA", "Gratings", "-", 0.0, 0.0, 0.0, 0, 0, 0, 3000, 0.74, 1.05, "HDG", "assumed", "Bought-in item, assumed 3.0 €/kg"),
    ("PPT-ANC", "Anchors and embedded parts", "-", 0.5, 20.0, 20.0, 900, 920, 260, 2300, 0.74, 1.05, "C2M", "assumed", "Assumed"),
    ("PPT-OTH", "Other steel", "Akkasæter", 0.39, 18.0, 12.1, 927, 558, 255, 1860, 0.74, 1.05, "C2M", "derived", f"{AKK} project average (Koostamine row 7)"),
]

CATEGORIES = [
    # id, category, offer label, kind, bevel share, holes/t, m2/t, sort, status, source
    ("CAT-01", "Columns", "Columns", "main", 1.0, 25, 20.4, 38.2, 10, "derived", f"bevel share: {AKK} columns AF>0 on all posts; m2/t and weld m/t {AKK} Koostamine row 16"),
    ("CAT-02", "Welded columns", "Welded columns", "main", 1.0, 15, 10.0, 83.7, 15, "derived", f"m2/t and weld m/t {KOT} Koostamine row 16"),
    ("CAT-03", "Beams", "Beams", "main", 0.5, 20, 18.2, 30.3, 20, "derived", f"m2/t and weld m/t {AKK} row 95; bevel share assumed"),
    ("CAT-04", "Welded beams", "Welded beams", "main", 0.3, 15, 14.2, 39.6, 25, "derived", f"m2/t and weld m/t {AKK} row 82; bevel share assumed"),
    ("CAT-05", "Bracings", "Bracings", "secondary", 0.1, 40, 20.6, 18.0, 30, "derived", f"m2/t and weld m/t {AKK} row 136; bevel share assumed"),
    ("CAT-06", "Tension rods", "Tension rods with turnbuckles", "secondary", 0.0, 0, 21.4, 9.1, 35, "derived", f"m2/t and weld m/t {AKK} row 217"),
    ("CAT-07", "Frames", "Frames and secondary steel", "secondary", 0.2, 30, 22.6, 20.0, 40, "derived", f"m2/t and weld m/t {AKK} row 163; bevel share assumed"),
    ("CAT-08", "Stairs and railings", "Stairs and railings", "secondary", 0.2, 50, 35.0, 40.0, 50, "assumed", "Assumed"),
    ("CAT-09", "Gratings", "Gratings", "bought", 0.0, 0, 0.0, 0.0, 55, "assumed", "Bought-in"),
    ("CAT-10", "Plates and small parts", "Plates and small parts", "small", 0.0, 80, 27.5, 11.7, 60, "derived", f"m2/t and weld m/t {KOT} row 428"),
    ("CAT-11", "Anchors and embedded parts", "Anchors and embedded parts", "small", 0.0, 20, 20.0, 10.0, 70, "assumed", "Assumed"),
    ("CAT-12", "Other steel", "Other steel", "secondary", 0.2, 30, 18.0, 30.0, 90, "assumed", f"Project average of {AKK} (weld 30 m/t)"),
]

CATEGORY_MAP = [
    # id, keyword, language, category, match, priority
    ("MAP-001", "søjle", "da", "Columns", "contains", 10), ("MAP-002", "sojle", "da", "Columns", "contains", 10),
    ("MAP-003", "column_wi", "en", "Welded columns", "contains", 20), ("MAP-004", "column", "en", "Columns", "contains", 10),
    ("MAP-005", "stolpe", "no", "Columns", "contains", 10), ("MAP-006", "søyle", "no", "Columns", "contains", 10),
    ("MAP-007", "post", "et/en", "Columns", "word", 5), ("MAP-008", "kolonn", "et", "Columns", "contains", 10),
    ("MAP-009", "pilari", "fi", "Columns", "contains", 10), ("MAP-010", "benkile", "da", "Columns", "contains", 10),
    ("MAP-011", "ramme", "da/no", "Columns", "word", 4),
    ("MAP-020", "beam_wi", "en", "Welded beams", "contains", 20), ("MAP-021", "hsq", "da", "Welded beams", "word", 20),
    ("MAP-022", "wq", "et/en", "Welded beams", "word", 20), ("MAP-023", "welded i", "en", "Welded beams", "contains", 15),
    ("MAP-030", "drager", "da", "Beams", "contains", 10), ("MAP-031", "darger", "da (typo in model)", "Beams", "contains", 10),
    ("MAP-032", "rigle", "da", "Beams", "contains", 10), ("MAP-033", "bjelke", "no", "Beams", "contains", 10),
    ("MAP-034", "tala", "et", "Beams", "word", 8), ("MAP-035", "palkki", "fi", "Beams", "contains", 10),
    ("MAP-036", "beam", "en", "Beams", "contains", 8), ("MAP-037", "purlin", "en", "Beams", "contains", 8),
    ("MAP-038", "tagkile", "da", "Beams", "contains", 6), ("MAP-039", "åsar", "sv", "Beams", "contains", 8),
    ("MAP-040", "vind-x", "da", "Bracings", "contains", 12), ("MAP-041", "vindkryds", "da", "Bracings", "contains", 12),
    ("MAP-042", "afstivning", "da", "Bracings", "contains", 12), ("MAP-043", "brace", "en", "Bracings", "contains", 12),
    ("MAP-044", "bracing", "en", "Bracings", "contains", 12), ("MAP-045", "stag", "no", "Bracings", "word", 8),
    ("MAP-046", "side", "et", "Bracings", "word", 6), ("MAP-047", "jäykiste", "fi", "Bracings", "contains", 10),
    ("MAP-048", "vindförband", "sv", "Bracings", "contains", 10),
    ("MAP-050", "bardunstrammer", "da", "Tension rods", "contains", 15), ("MAP-051", "turnbuckle", "en", "Tension rods", "contains", 15),
    ("MAP-052", "tõmbid", "et", "Tension rods", "contains", 15), ("MAP-053", "tie rod", "en", "Tension rods", "contains", 15),
    ("MAP-060", "portomfatning", "da", "Frames", "contains", 15), ("MAP-061", "window", "en", "Frames", "contains", 10),
    ("MAP-062", "door", "en", "Frames", "contains", 10), ("MAP-063", "aken", "et", "Frames", "contains", 10),
    ("MAP-064", "frame", "en", "Frames", "word", 9), ("MAP-065", "karm", "da/no", "Frames", "contains", 9),
    ("MAP-066", "parapet", "en/et", "Frames", "contains", 9),
    ("MAP-070", "trapp", "no/sv", "Stairs and railings", "contains", 15), ("MAP-071", "stair", "en", "Stairs and railings", "contains", 15),
    ("MAP-072", "trepp", "et", "Stairs and railings", "contains", 15), ("MAP-073", "rekkverk", "no", "Stairs and railings", "contains", 15),
    ("MAP-074", "railing", "en", "Stairs and railings", "contains", 15), ("MAP-075", "handrail", "en", "Stairs and railings", "contains", 15),
    ("MAP-076", "piire", "et", "Stairs and railings", "contains", 12), ("MAP-077", "gelænder", "da", "Stairs and railings", "contains", 15),
    ("MAP-078", "porras", "fi", "Stairs and railings", "contains", 15), ("MAP-079", "kaide", "fi", "Stairs and railings", "contains", 12),
    ("MAP-080", "grating", "en", "Gratings", "contains", 15), ("MAP-081", "rist", "et/da", "Gratings", "word", 10),
    ("MAP-082", "ritilä", "fi", "Gratings", "contains", 15), ("MAP-083", "gitterrist", "da", "Gratings", "contains", 15),
    ("MAP-090", "løsdele", "da", "Plates and small parts", "contains", 10), ("MAP-091", "plade", "da", "Plates and small parts", "word", 8),
    ("MAP-092", "plate", "en", "Plates and small parts", "word", 6), ("MAP-093", "leht", "et", "Plates and small parts", "word", 6),
    ("MAP-094", "fladstål", "da", "Plates and small parts", "contains", 8), ("MAP-095", "cfj", "en", "Plates and small parts", "word", 12),
    ("MAP-096", "erection", "en", "Plates and small parts", "contains", 10), ("MAP-097", "levy", "fi", "Plates and small parts", "word", 8),
    ("MAP-098", "pl15/ø26", "da", "Plates and small parts", "contains", 8),
    ("MAP-100", "sokkeljern", "da", "Anchors and embedded parts", "contains", 12), ("MAP-101", "anchor", "en", "Anchors and embedded parts", "contains", 12),
    ("MAP-102", "ankkuri", "fi", "Anchors and embedded parts", "contains", 12), ("MAP-103", "ankur", "et", "Anchors and embedded parts", "contains", 12),
    ("MAP-104", "embed", "en", "Anchors and embedded parts", "contains", 10), ("MAP-105", "opstik", "da", "Anchors and embedded parts", "contains", 6),
    ("MAP-110", "bollard", "en", "Frames", "contains", 10), ("MAP-111", "pullert", "da/no", "Frames", "contains", 10),
]

PREDICTIONS = [
    # id, key, value, unit, applies_to, status, source, notes
    ("PRD-01", "default_exc", "EXC2", "", "execution class", "assumed", f"Both Maru offers: 'EN1090-2, execution class EXC2'", "Ask the client if not stated"),
    ("PRD-02", "default_grade_rolled", "S355J2", "", "rolled sections", "assumed", "Both Maru offers list S235JR, S355J2, S355J2H", ""),
    ("PRD-03", "default_grade_hollow", "S355J2H", "", "hollow sections", "assumed", "Both Maru offers", ""),
    ("PRD-04", "default_corrosivity_indoor", "C2M", "", "indoor, unheated or heated hall", "assumed", f"{AKK_OFFER}: storage hall painted C2M", ""),
    ("PRD-05", "default_corrosivity_outdoor", "C3M", "", "outdoor, inland", "assumed", "ISO 12944-2 typical", ""),
    ("PRD-06", "default_corrosivity_coastal", "C4M", "", "coastal / industrial", "assumed", "ISO 12944-2 typical", ""),
    ("PRD-07", "default_weld_a", 5, "mm", "fillet welds when not stated", "assumed", f"{AKK_OFFER} §2h '<= a6'", ""),
    ("PRD-08", "holes_per_bolt", 2, "holes", "bolted connections", "assumed", "One hole in each connected part", ""),
    ("PRD-09", "stud_spacing_per_m", 2, "pcs/m", "rebar studs welded to deck beams", "assumed", "Placeholder allowance (1 stud each 500 mm)", "Ask the client"),
    ("PRD-10", "stud_mass", 0.49, "kg/pc", "rebar stud ø20 x 200 mm", "assumed", "7.85e-6 x pi/4 x 20² x 200", ""),
    ("PRD-11", "stud_minutes", 6, "min/pc", "welding one stud incl. handling", "assumed", "Placeholder", ""),
    ("PRD-12", "longest_piece_std_truck", 13.5, "m", "standard truck", "derived", f"{AKK_OFFER} and {KOT_OFFER} truck descriptions", ""),
    ("PRD-13", "anchor_default_qty", 0, "pcs", "anchors when not stated", "assumed", "Never assume anchors are included", ""),
    ("PRD-14", "secondary_steel_share", 0.07, "share", "secondary steel missing from early models", "assumed", "Placeholder for idea-level projects", ""),
    ("PRD-15", "idea_level_t_per_m2", 0.045, "t/m2", "steel per m² of hall floor (idea level)", "assumed", "Typical single-storey steel hall 35-55 kg/m²", ""),
    ("PRD-16", "bolts_kg_per_t", 5.0, "kg/t", "bolts when the model has none", "derived", f"{AKK} Pakkumistabel!N18: 741.6 kg bolts for 148.3 t", ""),
    ("PRD-17", "default_tolerance", "class 1", "", "EN 1090-2 tolerance class", "assumed", "Both Maru offers: 'tolerances acc. class 1'", ""),
    ("PRD-18", "default_fire_rating_option", "R30", "", "fire protection when a requirement has no rating", "assumed", "Lowest common class; priced only as an option", "Ask the client"),
]

CO2 = [
    ("CO2-01", "steel_bf_bof", "Primary steel, blast furnace / BOF route", 2.0, "t CO2e / t steel", "placeholder", "Guide §5: around 2 t CO2e per t", "Replace with supplier EPD (EN 15804, A1-A3)"),
    ("CO2-02", "steel_eaf", "Recycled steel, electric arc furnace (scrap based)", 0.6, "t CO2e / t steel", "placeholder", "Guide §5: well under 1 t", "Replace with supplier EPD"),
    ("CO2-03", "steel_reused", "Reclaimed / reused sections (cleaning, testing, transport)", 0.1, "t CO2e / t steel", "placeholder", "Order of magnitude", ""),
    ("CO2-04", "recycled_content_eaf", "Recycled content of EAF steel", 0.95, "share", "placeholder", "Typical", "Used for the recycled-content check"),
    ("CO2-05", "recycled_content_bf", "Recycled content of BF/BOF steel", 0.15, "share", "placeholder", "Typical", ""),
    ("CO2-06", "eaf_share_rolled", "Market share of EAF steel in rolled sections (no requirement)", 0.6, "share", "placeholder", "Order of magnitude (EU sections mostly EAF)", ""),
    ("CO2-07", "eaf_share_hollow", "Market share of EAF steel in hollow sections", 0.3, "share", "placeholder", "Order of magnitude", ""),
    ("CO2-08", "eaf_share_plates", "Market share of EAF steel in plates", 0.3, "share", "placeholder", "Order of magnitude", ""),
    ("CO2-09", "paint", "Paint (per litre applied)", 3.0, "kg CO2e / l", "placeholder", "Order of magnitude for epoxy / PUR", ""),
    ("CO2-10", "zinc_uptake", "Zinc picked up in hot-dip galvanising", 0.6, "kg zinc / m2", "placeholder", "~85 µm coating", ""),
    ("CO2-11", "zinc", "Zinc + galvanising process", 3.5, "kg CO2e / kg zinc", "placeholder", "Order of magnitude", ""),
    ("CO2-12", "truck_km", "Truck transport (articulated, full load)", 0.9, "kg CO2e / truck-km", "placeholder", "Public databases (e.g. DEFRA HGV) order of magnitude", ""),
    ("CO2-13", "workshop", "Workshop energy (cutting, welding, heating)", 0.03, "t CO2e / t steel", "placeholder", "Order of magnitude", ""),
]

# I-section geometry (h, b, tw, tf in mm) for area/perimeter fallbacks (nominal values)
I_SECTIONS = {
    "IPE80": (80, 46, 3.8, 5.2), "IPE100": (100, 55, 4.1, 5.7), "IPE120": (120, 64, 4.4, 6.3), "IPE140": (140, 73, 4.7, 6.9),
    "IPE160": (160, 82, 5.0, 7.4), "IPE180": (180, 91, 5.3, 8.0), "IPE200": (200, 100, 5.6, 8.5), "IPE220": (220, 110, 5.9, 9.2),
    "IPE240": (240, 120, 6.2, 9.8), "IPE270": (270, 135, 6.6, 10.2), "IPE300": (300, 150, 7.1, 10.7), "IPE330": (330, 160, 7.5, 11.5),
    "IPE360": (360, 170, 8.0, 12.7), "IPE400": (400, 180, 8.6, 13.5), "IPE450": (450, 190, 9.4, 14.6), "IPE500": (500, 200, 10.2, 16.0),
    "IPE550": (550, 210, 11.1, 17.2), "IPE600": (600, 220, 12.0, 19.0),
    "HEA100": (96, 100, 5.0, 8.0), "HEA120": (114, 120, 5.0, 8.0), "HEA140": (133, 140, 5.5, 8.5), "HEA160": (152, 160, 6.0, 9.0),
    "HEA180": (171, 180, 6.0, 9.5), "HEA200": (190, 200, 6.5, 10.0), "HEA220": (210, 220, 7.0, 11.0), "HEA240": (230, 240, 7.5, 12.0),
    "HEA260": (250, 260, 7.5, 12.5), "HEA280": (270, 280, 8.0, 13.0), "HEA300": (290, 300, 8.5, 14.0), "HEA320": (310, 300, 9.0, 15.5),
    "HEA340": (330, 300, 9.5, 16.5), "HEA360": (350, 300, 10.0, 17.5), "HEA400": (390, 300, 11.0, 19.0), "HEA450": (440, 300, 11.5, 21.0),
    "HEA500": (490, 300, 12.0, 23.0), "HEA600": (590, 300, 13.0, 25.0),
    "HEB100": (100, 100, 6.0, 10.0), "HEB120": (120, 120, 6.5, 11.0), "HEB140": (140, 140, 7.0, 12.0), "HEB160": (160, 160, 8.0, 13.0),
    "HEB180": (180, 180, 8.5, 14.0), "HEB200": (200, 200, 9.0, 15.0), "HEB220": (220, 220, 9.5, 16.0), "HEB240": (240, 240, 10.0, 17.0),
    "HEB260": (260, 260, 10.0, 17.5), "HEB280": (280, 280, 10.5, 18.0), "HEB300": (300, 300, 11.0, 19.0), "HEB320": (320, 300, 11.5, 20.5),
    "HEB340": (340, 300, 12.0, 21.5), "HEB360": (360, 300, 12.5, 22.5), "HEB400": (400, 300, 13.5, 24.0), "HEB450": (450, 300, 14.0, 26.0),
    "HEB500": (500, 300, 14.5, 28.0), "HEB600": (600, 300, 15.5, 30.0),
    "HEM200": (220, 206, 15.0, 25.0), "HEM260": (290, 268, 18.0, 32.5), "HEM300": (340, 310, 21.0, 39.0),
}
MATERJALID = [["CFCHS168.3x4.5", 18.2, 0.529, "Materjalid!A7,I7"], ["CFRHS100x100x6", 17, 0.379, "Materjalid!A9,I9"], ["CFRHS120x120x10", 31.8, 0.437, "Materjalid!A10,I10"], ["CFRHS120x120x8", 26.4, 0.446, "Materjalid!A11,I11"], ["CFRHS150x100x6", 21.7, 0.479, "Materjalid!A12,I12"], ["CFRHS150x150x6", 26.4, 0.579, "Materjalid!A13,I13"], ["CFRHS150x150x8", 34, 0.566, "Materjalid!A14,I14"], ["CFRHS180x180x10", 50.7, 0.677, "Materjalid!A15,I15"], ["CFRHS180x180x8", 41.5, 0.686, "Materjalid!A16,I16"], ["D30", 5.6, 0.379, "Materjalid!A17,I17"], ["HEB360", 142, 1.85, "Materjalid!A18,I18"], ["IPE120", 10.4, 0.5, "Materjalid!A19,I19"], ["IPE240", 30.7, 0.9, "Materjalid!A20,I20"], ["IPE400", 66.3, 1.5, "Materjalid!A21,I21"], ["IPE600", 122, 2, "Materjalid!A22,I22"], ["L100x10", 15.1, 0.39, "Materjalid!A24,I24"], ["L120x11", 19.9, 0.469, "Materjalid!A25,I25"], ["L60x40x6", 4.5, 0.195, "Materjalid!A26,I26"], ["CFRHS100x100x3", 9, 0.39, "Materjalid!A7,I7"], ["CFRHS100x100x4", 11.7, 0.386, "Materjalid!A8,I8"], ["CFRHS100x40x3", 6.1, 0.27, "Materjalid!A9,I9"], ["CFRHS100x50x5", 10.5, 0.283, "Materjalid!A10,I10"], ["CFRHS100x80x3", 8, 0.35, "Materjalid!A11,I11"], ["CFRHS120x120x4", 14.3, 0.466, "Materjalid!A12,I12"], ["CFRHS120x120x5", 17.6, 0.463, "Materjalid!A13,I13"], ["CFRHS140x140x5", 20.7, 0.543, "Materjalid!A14,I14"], ["CFRHS150x100x3", 11.3, 0.49, "Materjalid!A15,I15"], ["CFRHS150x150x5", 22.3, 0.583, "Materjalid!A16,I16"], ["CFRHS150x50x3", 9, 0.39, "Materjalid!A17,I17"], ["CFRHS160x160x6", 28.3, 0.619, "Materjalid!A18,I18"], ["CFRHS160x160x8", 36.5, 0.606, "Materjalid!A19,I19"], ["CFRHS200x100x5", 22.3, 0.583, "Materjalid!A21,I21"], ["CFRHS200x200x5", 30.1, 0.783, "Materjalid!A22,I22"], ["CFRHS200x200x6", 35.8, 0.779, "Materjalid!A23,I23"], ["CFRHS200x200x8", 46.5, 0.766, "Materjalid!A24,I24"], ["CFRHS250x150x5", 30.1, 0.783, "Materjalid!A25,I25"], ["CFRHS250x250x8", 59.1, 0.966, "Materjalid!A26,I26"], ["CFRHS300x300x10", 88.4, 1.157, "Materjalid!A27,I27"], ["HEA200", 42.3, 1.14, "Materjalid!A28,I28"], ["HEA240", 60.3, 1.37, "Materjalid!A29,I29"], ["HEA260", 68.2, 1.48, "Materjalid!A30,I30"], ["HEA320", 97.6, 1.76, "Materjalid!A31,I31"], ["HEA340", 105, 1.79, "Materjalid!A32,I32"], ["IPE550", 106, 1.9, "Materjalid!A34,I34"], ["L150x15", 33.8, 0.586, "Materjalid!A36,I36"], ["L200x100x10", 23, 0.587, "Materjalid!A37,I37"], ["T120", 23.2, 0.48, "Materjalid!A53,I53"], ["T140", 31.3, 0.56, "Materjalid!A54,I54"], ["T70", 8.3, 0.28, "Materjalid!A55,I55"], ["UNP260", 37.9, 0.834, "Materjalid!A56,I56"], ["UPE200", 22.8, 0.697, "Materjalid!A57,I57"]]


def profile_rows():
    rows = []
    seen = set()
    for i, (name, kgm, m2m, cell) in enumerate(MATERJALID, 1):
        key = name.upper()
        if key in seen:
            continue
        seen.add(key)
        src = (AKK if i <= 18 else KOT) + " " + cell
        rows.append((f"PRF-{len(rows)+1:03d}", name, kgm, m2m, None, None, None, None, "derived", src, ""))
    for name, (h, b, tw, tf) in I_SECTIONS.items():
        if name.upper() in seen:
            continue
        area_mm2 = 2 * b * tf + (h - 2 * tf) * tw
        kgm = round(area_mm2 * 7.85e-3 * 1.04, 1)  # +4 % for root radii
        m2m = round((2 * h + 4 * b - 2 * tw) / 1000.0, 3)
        rows.append((f"PRF-{len(rows)+1:03d}", name, kgm, m2m, h, b, tw, tf, "calculated",
                     "Nominal EN dimensions; kg/m = area x 7.85 (+4 % root radii); m²/m = 2h + 4b - 2tw", ""))
    return rows


# --------------------------------------------------------------------------------------------
NAVY = "01437D"
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
STATUS_FILL = {"derived": PatternFill("solid", fgColor="E6F0F8"), "assumed": PatternFill("solid", fgColor="FFF4E0"),
               "placeholder": PatternFill("solid", fgColor="FBE9E7"), "calculated": PatternFill("solid", fgColor="EAF5EE")}
THIN = Side(style="thin", color="D0D7DE")


def add_sheet(wb: Workbook, title: str, header: list[str], rows: list, widths: dict[str, int] | None = None,
              intro: str | None = None) -> None:
    ws = wb.create_sheet(title)
    r0 = 1
    if intro:
        ws.cell(row=1, column=1, value=intro).font = Font(italic=True, color="555555")
        r0 = 2
    for c, h in enumerate(header, 1):
        cell = ws.cell(row=r0, column=c, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center")
    status_col = header.index("status") + 1 if "status" in header else None
    for i, row in enumerate(rows, r0 + 1):
        values = [row.get(h) for h in header] if isinstance(row, dict) else list(row)
        for c, v in enumerate(values, 1):
            cell = ws.cell(row=i, column=c, value=v)
            cell.border = Border(bottom=THIN)
        if status_col:
            st = ws.cell(row=i, column=status_col).value
            if st in STATUS_FILL:
                ws.cell(row=i, column=status_col).fill = STATUS_FILL[st]
    ws.freeze_panes = ws.cell(row=r0 + 1, column=2)
    for c, h in enumerate(header, 1):
        w = (widths or {}).get(h) or min(max(len(h) + 2, 10), 40)
        if h in ("source", "notes", "description", "rule"):
            w = (widths or {}).get(h, 60)
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.auto_filter.ref = f"A{r0}:{get_column_letter(len(header))}{r0 + len(rows)}"


def build(out: Path = OUT) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "README"
    readme = [
        "Maru Metall – knowledge file (rates, norms, factors) used by the Takeoff & Quoting Assistant",
        "",
        "The rule engine reads this file at the start of every run. Edit values here; nothing is hard-coded in the app.",
        "Every row has an id (shown next to each number in the report), a status and a source.",
        "",
        "status = derived      copied or fitted from Maru's own cost workbooks (cell given in 'source')",
        "status = assumed      team assumption — please confirm or replace",
        "status = placeholder  order-of-magnitude value (e.g. CO2) — replace with supplier data (EPD, EN 15804)",
        "status = calculated   computed from nominal dimensions",
        "",
        "Sources: AKK = HK111090-01 Akkasæter workbook (offer HP11109-1, 24.10.2025); KOT = HK11257-03 Kotka workbook (offer HP11257-3, 16.07.2026).",
        "Remnant stock: sheet Remnant_stock is empty until Maru provides its warehouse list.",
        "Corrections that point to a wrong rate never change this file automatically: they become calibration suggestions.",
        "",
        "Version: 1.0 (generated by scripts/build_knowledge.py)",
    ]
    for i, line in enumerate(readme, 1):
        ws.cell(row=i, column=1, value=line).font = Font(bold=(i == 1), size=13 if i == 1 else 11, color=NAVY if i == 1 else "000000")
    ws.column_dimensions["A"].width = 130

    add_sheet(wb, "General", ["id", "key", "description", "value", "unit", "status", "source", "notes"], GENERAL)
    add_sheet(wb, "Labour_rates", ["id", "country", "eur_per_hour", "role", "status", "source", "notes"], LABOUR_RATES)

    price_rows = []
    for plist, date, items, fams, offer in (("AKK-2025-10", "2025-10-24", AKK_PRICES, AKK_FAMILY, AKK),
                                             ("KOT-2026-07", "2026-07-16", KOT_PRICES, KOT_FAMILY, KOT)):
        for (item, eur, waste, cell) in items:
            price_rows.append((f"SP-{plist}-{len(price_rows)+1:03d}", plist, date, item, "", None, None, eur, waste,
                               "derived", f"{offer} {cell}", ""))
        for (fam, a, b, eur, waste, how) in fams:
            price_rows.append((f"SP-{plist}-{len(price_rows)+1:03d}", plist, date, "*", fam, a, b, eur, waste,
                               "derived" if "assumed" not in how else "assumed", how, "family fallback"))
    add_sheet(wb, "Steel_prices", ["id", "price_list", "price_date", "item", "family", "size_from", "size_to",
                                   "eur_per_kg", "waste_factor", "status", "source", "notes"], price_rows)
    add_sheet(wb, "Waste", ["id", "key", "applies_to", "thickness_from", "thickness_to", "value", "unit", "status", "source", "notes"], WASTE)
    add_sheet(wb, "Cutting_speeds", ["id", "thickness_mm", "speed_mm_min", "pierce_s", "status", "source"],
              [(f"CUT-{t:03d}", t, s, p, st, src) for (t, s, p, st, src) in CUTTING])
    add_sheet(wb, "Time_norms", ["id", "operation", "applies_to", "unit", "norm", "norm_unit", "rule", "status", "source", "notes"], TIME_NORMS)
    add_sheet(wb, "Handling", ["id", "part_type", "band_from", "band_to", "band_unit", "with_holes_min", "without_holes_min", "status", "source"], HANDLING)
    add_sheet(wb, "Drilling", ["id", "part_type", "thickness_from", "thickness_to", "min_per_hole", "status", "source"], DRILLING)
    ph = ["id", "system", "corrosivity", "durability", "coats", "dft_total_um", "p1_name", "p1_coats", "p1_dft_um",
          "p1_volume_solids", "p1_eur_per_l", "p2_name", "p2_coats", "p2_dft_um", "p2_volume_solids", "p2_eur_per_l",
          "loss_factor", "painting_min_per_m2_per_coat", "blasting_min_per_m2", "blasting_material_eur_per_m2",
          "maru_all_in_eur_per_m2", "bottom_up_eur_per_m2", "check_vs_maru", "status", "source"]
    add_sheet(wb, "Paint_systems", ph, paint_rows())
    add_sheet(wb, "Surface_rates", ["id", "system", "rate", "unit", "status", "source", "notes"], SURFACE_RATES)
    add_sheet(wb, "Fire_protection", ["id", "rating", "layers", "material_eur_m2_layer", "labour_eur_m2_layer",
                                      "topcoat_eur_m2", "margin", "um_per_layer", "status", "source"], FIRE)
    add_sheet(wb, "Transport", ["id", "region", "countries", "keywords", "truck_type", "max_length_m", "eur_per_truck",
                                "payload_kg", "coefficient", "distance_km", "status", "source"], TRANSPORT)
    add_sheet(wb, "Fasteners", ["id", "item", "unit", "value", "pack_size", "margin", "status", "source", "notes"], FASTENERS)
    add_sheet(wb, "Price_per_tonne", ["id", "category", "reference_project", "plate_share", "m2_per_t", "hours_per_t",
                                      "material_eur_t", "production_eur_t", "surface_eur_t", "sale_eur_t", "steel_eur_kg",
                                      "margin", "surface_system", "status", "source"], PRICE_PER_TONNE)
    add_sheet(wb, "Categories", ["id", "category", "offer_label", "kind", "bevel_share", "holes_per_t", "m2_per_t",
                                 "weld_m_per_t", "sort", "status", "source"], CATEGORIES)
    add_sheet(wb, "Category_map", ["id", "keyword", "language", "category", "match", "priority"], CATEGORY_MAP)
    add_sheet(wb, "Predictions", ["id", "key", "value", "unit", "applies_to", "status", "source", "notes"], PREDICTIONS)
    add_sheet(wb, "CO2_factors", ["id", "key", "description", "value", "unit", "status", "source", "notes"], CO2)
    add_sheet(wb, "Profiles", ["id", "profile", "kg_per_m", "m2_per_m", "h_mm", "b_mm", "tw_mm", "tf_mm", "status", "source", "notes"], profile_rows())
    add_sheet(wb, "Remnant_stock", ["id", "profile", "grade", "length_mm", "qty", "location", "notes"], [],
              intro="Empty: Maru's remnant (offcut) stock list has not been provided yet. Add rows to enable the remnant check.")
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out


# --------------------------------------------------------------------------------------------
def verify(materials: Path) -> int:
    """Re-read Maru's workbooks and compare the derived single-cell values."""
    import openpyxl
    import warnings
    warnings.filterwarnings("ignore")
    akk = next(materials.glob("Example 2*/02 - Cost calculation/*/*.xlsm"), None)
    kot = next(materials.glob("Example 4*/02 - Cost calculation/*/*.xlsm"), None)
    if not akk or not kot:
        print("Maru workbooks not found under", materials)
        return 1
    a = openpyxl.load_workbook(akk, data_only=True)
    k = openpyxl.load_workbook(kot, data_only=True)
    checks = [
        ("labour 46 €/h", a["Koostamine"]["F5"].value, "töötasu 46 eur/tund"),
        ("margin material", a["Koostamine"]["AU2"].value, 1.05),
        ("margin production", a["Koostamine"]["AV2"].value, 1.05),
        ("packaging", a["Koostamine"]["AV5"].value, 0.03),
        ("transport coeff", a["Koostamine"]["BC2"].value, 1.15),
        ("truck std NO", a["Koostamine"]["BC3"].value, 3300),
        ("truck long NO", a["Koostamine"]["BD3"].value, 4000),
        ("C2M", a["Koostamine"]["AD2"].value, 13),
        ("HDG", a["Koostamine"]["AK2"].value, 0.72),
        ("C3VH", k["Koostamine"]["AJ2"].value, 20),
        ("truck std FI", k["Koostamine"]["BB3"].value, 850),
        ("fire layer", k["Tuletõke"]["D3"].value, 15.51),
        ("plate share AKK", round(a["Koostamine"]["C8"].value, 3), 0.389),
        ("plate share KOT", round(k["Koostamine"]["C8"].value, 3), 0.624),
        ("bolts €/kg", a["Pakkumistabel"]["L18"].value, 6.5),
    ]
    bad = 0
    for name, got, exp in checks:
        ok = got == exp
        bad += 0 if ok else 1
        print(f"{'OK ' if ok else 'BAD'} {name}: workbook={got!r} knowledge={exp!r}")
    for items, wb in ((AKK_PRICES, a), (KOT_PRICES, k)):
        for item, eur, waste, cell in items:
            r = int(cell.split("!A")[1].split(":")[0])
            got = (wb["Terasehind"][f"A{r}"].value.strip(), wb["Terasehind"][f"B{r}"].value, wb["Terasehind"][f"C{r}"].value)
            if got != (item, eur, waste):
                bad += 1
                print("BAD price", item, got)
    print("price rows checked:", len(AKK_PRICES) + len(KOT_PRICES), "mismatches:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--materials", default=str(DEMO.parent / "materials"))
    args = ap.parse_args()
    path = build()
    print("written", path)
    for r in paint_rows():
        print(f"  paint {r['system']:5} bottom-up {r['bottom_up_eur_per_m2']:6.2f} vs Maru {r['maru_all_in_eur_per_m2']:5.2f} "
              f"(min/coat {r['painting_min_per_m2_per_coat']})")
    if args.verify:
        sys.exit(verify(Path(args.materials)))
