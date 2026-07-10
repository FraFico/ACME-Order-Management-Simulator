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
AGENT2_NAME      = os.getenv("AGENT2_NAME", "fficobussinesvalidator")
AGENT2_VERSION   = os.getenv("AGENT2_VERSION", "3")

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
# FUNZIONE PRINCIPALE — AGENTE 2
# ---------------------------------------------------------------------------

def valida_ordine(ordine_dict: dict) -> dict:
    """
    Riceve il JSON ordine prodotto dall'agente 1 e lo invia
    all'agente 2 (Business Validation Agent) per la validazione
    contro anagrafica clienti e catalogo articoli.
    """

    catalogo = carica_catalogo()
    clienti  = carica_clienti()

    project_client = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )
    openai_client = project_client.get_openai_client()

    response = openai_client.responses.create(
        input=[
            {
                "type": "message",
                "role": "system",
                "content": (
                    f"Hai accesso al catalogo articoli Acme:\n{catalogo}\n\n"
                    f"Hai accesso all'anagrafica clienti Acme:\n{clienti}\n\n"
                    "Usa questi dati per validare l'ordine ricevuto."
                )
            },
            {
                "type": "message",
                "role": "user",
                "content": json.dumps(ordine_dict, ensure_ascii=False)
            }
        ],
        extra_body={
            "agent_reference": {
                "name":    AGENT2_NAME,
                "version": AGENT2_VERSION,
                "type":    "agent_reference"
            }
        },
    )

    # 5b. Log token usage — chiamata effettiva
    token_log = log_token_usage(response, "Agente 2 - Validazione")

    raw = response.output_text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        risultato = json.loads(raw)
    except json.JSONDecodeError as e:
        risultato = {
            "validation_status": "INVALID",
            "errors": [f"Errore parsing JSON: {e}. Raw: {raw[:300]}"]
        }

    return risultato