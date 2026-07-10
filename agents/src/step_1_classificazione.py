import base64
import json
import os
import pandas as pd
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
load_dotenv(override=True)  # cerca .env nella cartella corrente o superiori

PROJECT_ENDPOINT = os.getenv("PROJECT_ENDPOINT")
AGENT_NAME       = os.getenv("AGENT1_NAME", "agentefficocatalogazione")
AGENT_VERSION    = os.getenv("AGENT1_VERSION", "3")

PATH_ARTICOLI = "data/articoli.csv"
PATH_CLIENTI  = "data/clienti.csv"


# ---------------------------------------------------------------------------
# CARICAMENTO DATI DA CSV
# ---------------------------------------------------------------------------

def carica_catalogo() -> str:
    df = pd.read_csv(PATH_ARTICOLI)
    righe = []
    for _, row in df.iterrows():
        righe.append(
            f"{row['codice']} | {row['descrizione']} | "
            f"{row['categoria']} | {row['unita_misura']} | {row['prezzo_listino']}"
        )
    return "\n".join(righe)


def carica_clienti() -> str:
    df = pd.read_csv(PATH_CLIENTI)
    righe = []
    for _, row in df.iterrows():
        righe.append(
            f"{row['id']} | {row['ragione_sociale']} | "
            f"{row['partita_iva']} | {row['citta']} | {row['email']}"
        )
    return "\n".join(righe)

def log_token_usage(response, agent_name: str) -> dict:
    usage = response.usage
    log = {
        "agente": agent_name,
        "input_tokens": usage.input_tokens,
        "costo input $":usage.input_tokens*0.00000044,
        "output_tokens": usage.output_tokens,
        "costo output $":usage.output_tokens*0.00000176,
        "total_tokens": usage.total_tokens,
        "costo totale $": usage.input_tokens*0.00000044 + usage.output_tokens*0.00000176,
    }
    print(f"💰 {agent_name}: {log['total_tokens']} token "
          f"(in: {log['input_tokens']}, out: {log['output_tokens']})"
          f"({log["costo input $"]} $ + {log['costo output $']} $={log['costo totale $']} $")
    return log

# ---------------------------------------------------------------------------
# FUNZIONE PRINCIPALE — AGENTE 1
# ---------------------------------------------------------------------------

def leggi_pdf_con_llm(pdf_path: str) -> dict:
    """
    Riceve il path di un PDF, lo invia all'agente 1 (LLM) insieme a
    catalogo e anagrafica clienti aggiornati, e restituisce il JSON
    classificato (tipo: info / quotazione / ordine / umano).
    """

    # 1. Leggi il PDF e convertilo in base64 (nessuna conversione in immagine)
    with open(pdf_path, "rb") as f:
        pdf_base64 = base64.b64encode(f.read()).decode("utf-8")

    fonte = os.path.basename(pdf_path)

    # 2. Carica i dati aggiornati dai CSV
    catalogo = carica_catalogo()
    clienti  = carica_clienti()

    # 3. Inizializza il client
    project_client = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )
    openai_client = project_client.get_openai_client()

    # 4. Contenuto utente con il PDF come file nativo
    contenuto_utente = [
        {
            "type": "input_text",
            "text": "Analizza questo documento e classificalo seguendo le istruzioni."
        },
        {
            "type": "input_file",
            "filename": fonte,
            "file_data": f"data:application/pdf;base64,{pdf_base64}"
        }
    ]

    # 5. Chiama l'agente 1
    response = openai_client.responses.create(
        input=[
            {
                "type": "message",
                "role": "system",
                "content": (
                    f"Hai accesso al catalogo articoli Acme:\n{catalogo}\n\n"
                    f"Hai accesso all'anagrafica clienti Acme:\n{clienti}\n\n"
                    "Usa questi dati per classificare il documento e rispondere."
                )
            },
            {
                "type": "message",
                "role": "user",
                "content": contenuto_utente
            }
        ],
        extra_body={
            "agent_reference": {
                "name":    AGENT_NAME,
                "version": AGENT_VERSION,
                "type":    "agent_reference"
            }
        },
    )

    # 5b. Log token usage — chiamata effettiva
    token_log = log_token_usage(response, "Agente 1 - Catalogazione")

    # 6. Estrai e pulisci la risposta
    raw = response.output_text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    # 7. Parsa il JSON
    try:
        risultato = json.loads(raw)
    except json.JSONDecodeError as e:
        risultato = {
            "tipo": "umano",
            "confidenza": 0.0,
            "motivo": f"Errore parsing JSON: {e}. Risposta raw: {raw[:300]}"
        }

    risultato["fonte"] = fonte
    return risultato
