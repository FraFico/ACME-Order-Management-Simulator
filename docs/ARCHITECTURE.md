# Architecture

## End-to-end flow

```
PDF order
   │
   ▼
Agent 1 (Classify) ──► Agent 2 (Validate) ──► Agent 3 (Correct)      ← stage 1: /agents
   │
   ▼
Silver tables:  silver_validation , silver_correction               ← Fabric Lakehouse
   │
   ▼
Gold star schema:  fact_ordini + dim_clienti + dim_articoli + dim_data
   │
   ▼
Power BI (Direct Lake)                                              ← stage 3: /powerbi
```

## Medallion layers

**🥉 Bronze** — raw, untransformed source data in the Lakehouse `Files/Bronze/…`:
- `Customers/clienti.csv`, `Products/articoli.csv`
- `Orders/ordini_storici.csv`, `Orders/righe_ordini_storici.csv` (historical ERP)
- raw agent JSON output

**🥈 Silver** — cleaned/validated agent results as Delta tables `silver_validation` and
`silver_correction`. Only orders with status `VALID`, resolved `WARNING`, or `CORRECTED` move forward.

**🥇 Gold** — the analytical **star schema** written as Delta tables (see below), plus optional
semicolon-separated service CSVs in `Files/Gold/ERP` for file-based refresh.

## The `bronze_to_silver_to_gold` notebook

Built with PySpark inside a Fabric notebook. What each part does:

1. **`dim_clienti` / `dim_articoli`** — near pass-through of the customer and product master data,
   with typed and renamed columns.
2. **`fact_ordini` (agentic)** — reads `silver_validation` + `silver_correction`, keeps VALID/WARNING/
   CORRECTED orders, de-duplicates by `document_id`, and flattens each order into one row per line.
3. **`fact_ordini` (historical)** — deterministic joins between historical order lines, orders,
   customers and products (no LLM). Computes `Scostamento_Prezzo_Pct` (price drift vs. list price).
4. **Union** — agentic + historical rows into a single `fact_ordini`, tagged by `Origine_Dati`
   and `Pipeline`, de-duplicated by `Riga_ID`.
5. **`dim_data`** — a date dimension derived from the order dates (year, quarter, month, `AnnoMese`,
   day, weekday).
6. **Write** — all four tables saved as Delta (`saveAsTable`, overwrite) in a star layout for Power BI.

## Data model (star schema)

```
                     ┌─────────────┐
                     │  dim_data   │
                     │  ◆ Data_ID  │
                     └──────┬──────┘
                            │ 1
                            │
                            ▼ ∞
┌──────────────┐ 1     ∞ ┌───────────────┐ ∞     1 ┌───────────────┐
│ dim_clienti  ├────────►│  fact_ordini  │◄────────┤ dim_articoli  │
│ ◆ Cliente_ID │         │  (order line) │         │ ◆ Codice_Art. │
└──────────────┘         └───────────────┘         └───────────────┘
```

- `fact_ordini` — grain = **one order line**; measures `Quantita`, `Prezzo_Unitario`, `Importo_Riga`.
- Foreign keys `Cliente_ID`, `Codice_Articolo`, `Data_ID` join to the three conformed dimensions.
- Relationships are 1-to-many (dimension → fact), the standard shape for a Power BI Direct Lake model.

## Data quality

- **Completeness:** `Dati_Incompleti` flags order lines whose customer or product could not be matched.
- **Price drift:** `Scostamento_Prezzo_Pct > 5%` highlights historical prices far from the list price.
- **Column sanitisation:** non-ASCII / spaces in column names are replaced with `_` for Delta / SQL
  endpoint / DAX compatibility.
