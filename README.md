# Pipeline Intelligente per la Gestione Ordini — Acme Manufacturing

Sistema multi-agente basato su **Azure AI Foundry** che automatizza la ricezione, classificazione,
validazione e correzione degli ordini commerciali ricevuti in formato PDF, con esportazione
automatica verso ERP.

Progetto realizzato come project work per la valutazione di una figura **AI Engineer**.

---

## Indice

- [Architettura](#architettura)
- [I tre agenti](#i-tre-agenti)
- [Struttura del repository](#struttura-del-repository)
- [Setup](#setup)
- [Esecuzione](#esecuzione)
- [Formato dati di input](#formato-dati-di-input)
- [Output generati](#output-generati)
- [Principio di design](#principio-di-design)

---

## Architettura

```
PDF ordine
    │
    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Agente 1   │────▶│  Agente 2   │────▶│  Agente 3   │
│Classificazione│    │ Validazione │◀────│ Correzione  │
└─────────────┘     └─────────────┘     └─────────────┘
                            │                (max 2 tentativi)
                            ▼
                     ┌─────────────┐
                     │  CSV → ERP  │
                     └─────────────┘
```

Il flusso è orchestrato interamente in Python (`src/main.py`). Nessuna chiamata LLM
viene usata per instradamento, calcoli, validazioni logiche o esportazione dati —
solo per i compiti che richiedono comprensione del linguaggio naturale.

## I tre agenti

| Agente | Modello | Ruolo | Input | Output |
|---|---|---|---|---|
| **1 — Classificazione** | GPT-4.1 mini | Legge il PDF, classifica il documento, mappa articoli/clienti | PDF + catalogo/clienti aggiornati | JSON (`tipo`: ordine / quotazione / info / umano) |
| **2 — Validazione** | GPT-4.1 mini | Verifica l'ordine contro anagrafica e catalogo, non lo modifica mai | JSON ordine + master data | JSON di validazione (VALID / WARNING / INVALID) |
| **3 — Correzione** | GPT-4.1 mini | Corregge solo errori di formato/mappatura deducibili con certezza | Ordine + esito validazione | Ordine corretto + flag `correggibile` |

I prompt completi configurati su Azure AI Foundry per ciascun agente sono in [`prompts/`](prompts/).

### Loop di validazione/correzione

```
Agente 2 valida ordine originale (tentativo 0)
    │
    ├── VALID / WARNING ──────────────────────▶ fine, nessuna correzione necessaria
    │
    └── INVALID
            │
            ▼
        Agente 3 valuta l'errore
            │
            ├── correggibile = false (errore grande, non recuperabile)
            │     └──▶ STOP immediato, non consuma altri tentativi, va a operatore umano
            │
            └── correggibile = true
                    │
                    ▼
                Applica correzione ──▶ Agente 2 rivalida
                    │
                    ├── VALID / WARNING ───────▶ fine, successo
                    └── ancora INVALID e tentativi < 2 ──▶ riprova, altrimenti STOP
```

Il limite di **2 tentativi massimi** è una scelta di design deliberata: bilancia
la resilienza automatica con il controllo dei costi (ogni tentativo = una chiamata LLM)
ed evita loop infiniti su errori strutturalmente non correggibili (es. un cliente o un
articolo che semplicemente non esiste — l'agente 3 non inventa mai dati).

Ogni esecuzione produce uno **storico completo** di tutti i tentativi, salvato in
`storico_ordine.json`, utile sia per audit sia per il debug.

## Struttura del repository

```
.
├── src/
│   ├── main.py                      # Entry point — orchestratore della pipeline
│   ├── step_1_classificazione.py    # Agente 1 — lettura PDF e classificazione
│   ├── step_2_validazione.py        # Agente 2 — validazione business
│   ├── step_3_correzione.py         # Agente 3 — correzione automatica + loop
│   ├── step_info_quotazione.py      # Gestione casi INFO e QUOTAZIONE (no LLM)
│   └── step_export_csv.py           # Esportazione ordine validato in CSV per ERP
│
├── prompts/
│   ├── agente1_classificazione.txt  # System prompt configurato su Foundry
│   ├── agente2_validazione.txt
│   └── agente3_correzione.txt
│
├── data/
│   ├── articoli.csv                 # Catalogo prodotti (esempio)
│   ├── clienti.csv                  # Anagrafica clienti (esempio)
│   └── pdf_input/                   # PDF di esempio da processare
│
├── docs/
│   └── traccia_progetto.docx        # Traccia originale del project work
│
├── .env.example                     # Template variabili d'ambiente (senza credenziali)
├── .gitignore
├── requirements.txt
└── README.md
```

## Setup

**1. Clona il repository e crea un ambiente virtuale**

```bash
git clone <url-repo>
cd <nome-repo>
python -m venv venv
source venv/bin/activate   # su Windows: venv\Scripts\activate
```

**2. Installa le dipendenze**

```bash
pip install -r requirements.txt
```

**3. Configura le credenziali**

```bash
cp .env.example .env
```

Compila `.env` con l'endpoint del tuo progetto Azure AI Foundry e i nomi/versioni
dei tre agenti (vedi [Prerequisiti Azure](#prerequisiti-azure) sotto).

**4. Autenticati su Azure**

Il progetto usa `DefaultAzureCredential`, quindi è sufficiente essere loggati via CLI:

```bash
az login
```

### Prerequisiti Azure

Prima di eseguire la pipeline è necessario aver creato su **Azure AI Foundry**:

- Un progetto AI Foundry con un deployment del modello (es. `gpt-4.1-mini`)
- Tre agenti configurati con i prompt in [`prompts/`](prompts/):
  - Agente di classificazione (usato da `step_1_classificazione.py`)
  - Agente di validazione business (usato da `step_2_validazione.py`)
  - Agente di correzione ordini (usato da `step_3_correzione.py`)

## Esecuzione

```bash
cd src
python main.py ../data/pdf_input/ordine_cliente_A.pdf
```

Se non specifichi un path, viene usato il PDF di esempio incluso nel repository.

Output a schermo: tipo di documento rilevato, esito di ogni tentativo di
validazione/correzione, stato finale, e — se l'ordine è valido — il path del
CSV generato per l'import in ERP.

## Formato dati di input

**`data/articoli.csv`** — colonne attese: `codice, descrizione, categoria, unita_misura, prezzo_listino`

**`data/clienti.csv`** — colonne attese: `id, ragione_sociale, partita_iva, indirizzo, cap, citta, provincia, email, telefono`

Questi due file vengono **ricaricati ad ogni esecuzione**: aggiornare il catalogo
o l'anagrafica non richiede modifiche al codice né un nuovo deploy.

## Output generati

| File | Quando | Contenuto |
|---|---|---|
| `order.json` | sempre | Ultimo JSON prodotto dall'agente 1 |
| `storico_ordine.json` | se tipo = ordine | Storico completo di validazione/correzione, tentativo per tentativo |
| `output_csv/ERP_ORDINE_*.csv` | se ordine VALID | Ordine pronto per import in ERP, con metadati di tracciabilità |
| Email operatore | per INFO / QUOTAZIONE | Bozza di risposta o preventivo, inoltrata via API |

## Principio di design

> L'LLM fa solo le cose che solo l'LLM sa fare. Il codice Python fa tutto il resto.

Ogni chiamata a un modello linguistico introduce latenza, costo e non-determinismo.
Per questo la pipeline è progettata per usare gli agenti **esclusivamente** per compiti
di comprensione del linguaggio naturale — classificare un documento, mappare una
descrizione libera a un codice catalogo, dedurre una correzione plausibile — mentre
tutto ciò che è calcolabile in modo deterministico (lookup su CSV, calcoli di
totali/prezzi, instradamento, esportazione file) resta puro Python.

Risultato: **una sola chiamata LLM** per classificare un documento, e al massimo
altre 2-4 chiamate nel caso di un ordine che richiede validazione e correzione —
contro le 8-10+ chiamate di un'architettura ad agenti gerarchici meno mirata.
