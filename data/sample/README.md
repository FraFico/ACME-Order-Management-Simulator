# Sample data

Put **small, anonymised** sample files here so anyone can run the notebook without real data.
Never commit real customer data — the `.gitignore` blocks everything under `data/` except this folder.

The notebook expects these Bronze inputs (upload them to the Fabric Lakehouse under `Files/Bronze/…`):

| File | Path in Lakehouse | Columns |
|------|-------------------|---------|
| `clienti.csv` | `Files/Bronze/Customers/` | `id, ragione_sociale, partita_iva, indirizzo, cap, citta, provincia, email, telefono` |
| `articoli.csv` | `Files/Bronze/Products/` | `codice, descrizione, categoria, unita_misura, prezzo_listino` |
| `ordini_storici.csv` | `Files/Bronze/Orders/` | `id_ordine, riferimento_cliente, id_cliente, data_ordine` |
| `righe_ordini_storici.csv` | `Files/Bronze/Orders/` | `id_riga, id_ordine, codice_articolo, descrizione_articolo, quantita, prezzo_unitario, importo_riga` |

Use fake company names and VAT numbers (e.g. `ACME S.r.l.`, `IT00000000000`).
