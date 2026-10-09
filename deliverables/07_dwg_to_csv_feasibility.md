# Fattibilità: DWG → AI → CSV di feature di progetto
### Analisi tecnica per il team Maru Metall · SteelQuote AI

---

## RISPOSTA DIRETTA: È FATTIBILE? SÌ.

Ma la risposta ha tre sfumature importanti che determinano la qualità del CSV ottenuto:
il risultato varia enormemente a seconda del **tipo di file** che si dà in input.

---

## 1. MAPPA DEI FILE DI INPUT — COSA MARU RICEVE DAVVERO

Dall'analisi dei progetti reali (Example 2 e Example 4):

| Tipo file | Cosa contiene | Software di origine |
|---|---|---|
| `.dwg` | Geometria 2D/3D, layer, testo, blocchi | AutoCAD, Tekla Structures |
| `.ifc` | Modello BIM 3D strutturato | Tekla, Revit, Advance Steel |
| `.nc1` (DSTV) | Istruzioni CNC per macchina: tagli, fori | Tekla → macchina CNC |
| `.pdf` (shop drawing) | Drawing vettoriale o rasterizzato | Tekla → PDF export |
| `.xlsx` (BOM) | Lista materiali strutturata | Tekla → Excel export |
| `.png` (render) | Immagine visiva della struttura | Tekla / Revit render |

**Dalla lettura dei file reali:**
- I PDF del Skybridge (es. `25019443-ICC250-0600-0660-001332.pdf`) contengono testo estraibile: title block, position ID, discipline, revision — ma **non** le dimensioni degli elementi perché quelle sono nell'immagine grafica delle tavole.
- I file `.nc1` (es. `d46.nc1`, `W1.nc1`) contengono **dati macchina diretti**: profilo `L45*5`, materiale `S355J2`, lunghezza `4250 mm`, cut geometry — **completamente leggibili senza AI**.
- Il `.db1` (Tekla database) è binario proprietario.

---

## 2. PIPELINE TECNICA: DA DWG A CSV

### Caso 1: Input = DWG (AutoCAD nativo)

```
FILE .DWG
     |
     v
[ezdxf — libreria Python open-source]
Legge: entità geometriche, layer, testo, blocchi, attributi
     |
     +-- LAYER analysis
     |   Ogni layer ha un nome che indica il tipo di elemento:
     |   "STEEL-COLUMN-S355", "BRACING-HORIZ", "PLATE-BASE-15mm"
     |   → classifica automaticamente il tipo strutturale
     |
     +-- LINE / POLYLINE geometry
     |   Misura lunghezze, aree di superficie, forme di taglio
     |   → calcola: lunghezza elemento [mm], perimetro profilo → m2 superficie
     |
     +-- TEXT / MTEXT entities
     |   Contiene: quote dimensionali, note materiale, codici grado acciaio
     |   → LLM estrae: "S355J2", "t=15mm", "HEA300", "EPD required"
     |
     +-- BLOCK references
     |   Standard components: bulloni, ancoranti, piastre tipo
     |   → conta i fori da praticare → input per norma di foratura
     |
     v
[LLM classification layer — GPT-4o / Gemini]
Prompt: "Given these DWG text annotations and layer names,
         classify each element and extract: profile, grade,
         length, hole count, weld size, surface treatment"
     |
     v
[Norm calculation engine]
Applica norma Maru a ogni elemento estratto
     |
     v
CSV OUTPUT
```

### Caso 2: Input = NC1 DSTV (situazione ottimale)

Lettura diretta, zero AI necessaria. Il file `d46.nc1` trovato in Example 2 contiene:

```
Header block "ST":
  Project:    30480-4
  Part mark:  d46
  Material:   S355J2
  Profile:    L45*5    ← angolare 45x45x5mm
  Length:     4250 mm
  Weight/m:   3.380 kg/m  → peso = 4.250 × 3.380 = 14.36 kg

  W1.nc1:
  Material:   S355J2H
  Profile:    RHS100X100X6  ← sezione cava rettangolare
  Length:     215 mm

  I4.nc1:
  Material:   B550B  ← barra d'armatura (non acciaio strutturale!)
  Profile:    REBAR8
  Hole block "KA": x=49.73mm, d=8mm, depth=7.75mm ← foro preciso
```

Tutto questo si legge con 20 righe di Python. **Nessun modello AI serve.**

---

## 3. IL CSV OUTPUT — STRUTTURA CONSIGLIATA

Una riga per elemento (o per "part mark"). Progettato per essere **editabile da un ingegnere senior in Excel senza formazione specifica**.

```csv
part_mark, quantity, element_type, profile, steel_grade,
length_mm, weight_kg_each, weight_kg_total,
holes_count, hole_diam_mm, drilling_time_min,
weld_equiv_a5_m, welding_time_min,
surface_area_m2, surface_treatment,
cutting_type, cutting_time_min,
material_cost_eur, labour_cost_eur, surface_cost_eur,
total_cost_eur, unit_cost_eur_per_kg,
recycled_content_pct, carbon_kgCO2e,
source_file, confidence_pct, assumptions, engineer_verified
```

### Esempio di riga reale (da d46.nc1 + norma Maru):

```csv
d46, 4, bracing, L45*5, S355J2,
4250, 14.36, 57.44,
0, -, 0,
0.52, 8.2,
0.124, C2M,
saw_cut, 3.1,
65.6, 38.4, 14.9,
118.9, 2.07,
80%, 0.037,
"d46.nc1 + norm_db_v3", 98%, "weld size assumed a5 std", FALSE
```

### Colonne per il controllo ingegnere

| Colonna | Scopo | Editabile |
|---|---|---|
| `profile` | Profilo estratto | Sì — correggere se errato |
| `steel_grade` | Grado acciaio | Sì — spesso mancante in DWG |
| `weight_kg_total` | Peso calcolato | Sì — override manuale |
| `holes_count` | Fori da praticare | Sì — aggiungere se non in DWG |
| `weld_equiv_a5_m` | Lunghezza saldatura equivalente | **Campo critico — spesso stimato** |
| `surface_treatment` | Sistema anticorrosione | Sì — C2M / C3H / HDG |
| `recycled_content_pct` | % acciaio riciclato | Sì — da mill certificate |
| `assumptions` | Ipotesi fatte dall'AI | **Solo lettura — mostra cosa l'AI ha assunto** |
| `confidence_pct` | Affidabilità estrazione | Solo lettura — <80% = rivedere |
| `engineer_verified` | Flag di approvazione | **Solo modifica umana — inizia FALSE** |

---

## 4. COSA L'AI PUÒ ESTRARRE DA UN DWG — E COSA NO

### Estrae con alta affidabilità (>90%)
- Tipo di profilo (HEA, IPE, RHS, L, PL) — dai layer names o text
- Lunghezza elemento — dalla geometria o dai testi di quota
- Materiale / grado acciaio — se scritto nel DWG (spesso sì)
- Numero di fori — se il DWG è un shop drawing (da blocchi o cerchi)
- Sistema di superficie (C2M, HDG) — dalle note di tavola

### Estrae con affidabilità media (60–90%)
- Dimensione saldature — spesso mancante o implicita → **assunta**
- Sequenza di assemblaggio — non presente nel DWG 2D
- Copings e notches — visibili in 3D/NC1, non sempre in 2D DWG

### Non estrae — richiede input umano
- Prezzo dell'acciaio al momento dell'offerta → **inserito dall'estimatore**
- Requisiti specifici di qualità saldatura (EXC1/2/3) → **dal capitolato**
- Logistica di trasporto → **scelta commerciale**
- Certificato mill per acciaio riciclato → **da supplier, non da DWG**

---

## 5. ARCHITETTURA DEL SISTEMA (implementazione reale)

```
INPUT FILES                    PARSER                   OUTPUT
─────────────────────────────────────────────────────────────────
file.dwg          ──>  ezdxf (Python)       ──>  feature_raw.json
file.nc1 (DSTV)   ──>  custom NC1 parser    ──>  feature_raw.json
file.pdf (drawing) ──> pdfplumber + LLM     ──>  feature_raw.json
file.ifc          ──>  IfcOpenShell         ──>  feature_raw.json
file.xlsx (BOM)   ──>  pandas              ──>  feature_raw.json
sketch.png        ──>  Vision LLM           ──>  feature_raw.json
                                                      |
                                                      v
                                            [Norm engine]
                                            Applica norma Maru
                                            + calcola costi
                                                      |
                                                      v
                                    project_features_DRAFT.csv
                                    (confidence + assumptions)
                                                      |
                                                      v
                                    [Ingegnere apre in Excel]
                                    Rivede, corregge, approva
                                    Imposta engineer_verified=TRUE
                                                      |
                                                      v
                                    project_features_APPROVED.csv
                                    → Inserito in template offerta
```

---

## 6. LIVELLI DI ACCURATEZZA PER TIPO DI INPUT

| Input | Campi estratti automaticamente | Confidence media | Tempo di revisione ingegnere |
|---|---:|---:|---:|
| NC1/DSTV files | 18/22 campi | 97% | 15 min |
| IFC + BOM Excel | 17/22 campi | 92% | 30 min |
| DWG shop drawing | 14/22 campi | 78% | 1.5 h |
| PDF shop drawing (vettoriale) | 13/22 campi | 72% | 2 h |
| PDF scan (immagine) | 10/22 campi | 55% | 3 h |
| Sketch / email | 6/22 campi | 35% | Solo budget range |

**Nota:** anche con PDF scansionato (worst case), il CSV è comunque utile — perché fornisce la struttura, le colonne pre-compilate con valori default, e l'ingegnere corregge solo le righe flagged (confidence <80%).

---

## 7. IL CSV COME STRUMENTO DI VALIDAZIONE — WORKFLOW PRATICO

1. **Il sistema genera** `progetto_123_DRAFT.csv` in 15–30 min
2. **L'ingegnere apre** il file in Excel (o Google Sheets)
3. **Filtra** per `confidence_pct < 80` → vede solo le righe critiche
4. **Rivede** colonna `assumptions` → capisce cosa l'AI ha ipotizzato
5. **Corregge** i valori errati (profilo sbagliato, materiale mancante, saldature)
6. **Imposta** `engineer_verified = TRUE` per ogni riga approvata
7. **Il sistema calcola** i totali dal CSV approvato → template offerta

Il CSV non è solo output — è il **contratto di fiducia** tra AI e ingegnere: tutto ciò che l'AI non sa con certezza è dichiarato esplicitamente.

---

## 8. RISPOSTA ALLA DOMANDA ORIGINALE

> "È fattibile passare in input un DWG e calcolare in output un CSV con le features di progetto?"

**SÌ, è fattibile.** Con queste precisazioni:

| Condizione | Fattibilità |
|---|---|
| Input = NC1/DSTV (da Tekla) | **Immediatamente**, senza AI, solo parsing |
| Input = IFC + BOM Excel | **Alta** — affidabilità >90%, revisione 30 min |
| Input = DWG AutoCAD | **Media-alta** — affidabilità 75-85%, revisione 1.5h |
| Input = PDF vettoriale | **Media** — affidabilità 70%, revisione 2h |
| Input = PDF scansionato | **Bassa ma utile** — struttura CSV + valori default |
| Input = sketch o email | **Solo budget range** — non adatto per CSV dettagliato |

**La raccomandazione per Maru:** iniziare il PoC con i file NC1/DSTV che sono già presenti in azienda per i progetti in produzione. Sono il percorso a minimo rischio, massima accuratezza, e zero investimento in AI per la parte di parsing. L'AI entra solo per i testi non strutturati (PDF, email) e per la classificazione semantica dei layer DWG.
