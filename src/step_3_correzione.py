#agente 3 per il controllo degli errori

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
AGENT3_NAME      = os.getenv("AGENT3_NAME", "fficoorderfixer")
AGENT3_VERSION   = os.getenv("AGENT3_VERSION", "3")

PATH_ARTICOLI = "data/articoli.csv"
PATH_CLIENTI  = "data/clienti.csv"

MAX_TENTATIVI = 2  # tetto massimo, non un numero fisso da esaurire sempre


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


# ---------------------------------------------------------------------------
# HELPER — log token usage
# ---------------------------------------------------------------------------

def log_token_usage(response, agent_name: str) -> dict:
    usage = response.usage
    log = {
        "agente": agent_name,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens
    }
    print(f"💰 {agent_name}: {log['total_tokens']} token "
          f"(in: {log['input_tokens']}, out: {log['output_tokens']})")
    return log


# ---------------------------------------------------------------------------
# AGENTE 3 — correzione ordine (collegamento a Foundry)
# ---------------------------------------------------------------------------

def correggi_ordine(ordine_dict: dict, validazione: dict) -> dict:
    """
    Riceve l'ordine corrente e l'esito di validazione dell'agente 2.
    Corregge SOLO errori di formato/mappatura (prezzo, unità di misura,
    quantità deducibile). Non inventa mai clienti o articoli inesistenti.

    Se l'errore è grande / non recuperabile, l'agente deve dichiarare
    "correggibile": false — il loop a monte si ferma subito.
    """

    catalogo = carica_catalogo()
    clienti  = carica_clienti()

    project_client = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )
    openai_client = project_client.get_openai_client()

    payload_input = {
        "ordine": ordine_dict,
        "validazione": validazione
    }

    response = openai_client.responses.create(
        input=[
            {
                "type": "message",
                "role": "system",
                "content": (
                    f"Hai accesso al catalogo articoli Acme:\n{catalogo}\n\n"
                    f"Hai accesso all'anagrafica clienti Acme:\n{clienti}\n\n"
                    "Riceverai un ordine e il relativo esito di validazione "
                    "(errori e warning). Correggi SOLO gli errori di formato, "
                    "unità di misura, prezzo errato rispetto al listino, o "
                    "quantità deducibili dal contesto. NON inventare mai codici "
                    "articolo o clienti che non esistono nei dati forniti. "
                    "Se l'errore è grande o i dati mancanti non sono recuperabili "
                    "(es. cliente inesistente, articolo non a catalogo), dichiara "
                    "esplicitamente correggibile=false."
                )
            },
            {
                "type": "message",
                "role": "user",
                "content": json.dumps(payload_input, ensure_ascii=False)
            }
        ],
        extra_body={
            "agent_reference": {
                "name":    AGENT3_NAME,
                "version": AGENT3_VERSION,
                "type":    "agent_reference"
            }
        },
    )

    token_log = log_token_usage(response, "Agente 3 - Correzione")

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
            "ordine_corretto": ordine_dict,
            "correzioni_applicate": [],
            "correggibile": False,
            "motivo_non_correggibile": f"Errore parsing JSON agente 3: {e}. Raw: {raw[:300]}"
        }

    risultato["token_usage"] = token_log
    return risultato


# ---------------------------------------------------------------------------
# LOOP AGENTE 2 <-> AGENTE 3, con storico completo
# ---------------------------------------------------------------------------

def processa_ordine_con_correzione(ordine: dict, valida_ordine_fn, max_tentativi: int = MAX_TENTATIVI) -> dict:
    """
    Tentativo 0 — Agente 2 valida ordine originale
        -> VALID/WARNING: fine, nessuna correzione necessaria
        -> INVALID: Agente 3 valuta
              -> correggibile=False: STOP immediato, niente altri tentativi
              -> correggibile=True: applica correzione -> Agente 2 rivalida
                    -> VALID/WARNING: fine, successo
                    -> ancora INVALID e tentativi < max: riprova, altrimenti STOP

    Restituisce SEMPRE lo storico completo, indipendentemente dall'esito.
    """
    storico = []
    ordine_corrente = ordine

    # Tentativo 0 — validazione iniziale
    validazione = valida_ordine_fn(ordine_corrente)
    storico.append({
        "tentativo": 0,
        "validazione": validazione,
        "correzione": None
    })

    tentativo = 0
    while validazione.get("validation_status") == "INVALID" and tentativo < max_tentativi:
        tentativo += 1
        print(f"\n🔧 Tentativo di correzione {tentativo}/{max_tentativi}")

        correzione = correggi_ordine(ordine_corrente, validazione)

        if not correzione.get("correggibile", False):
            print("⛔ Errore non correggibile automaticamente — stop immediato")
            storico.append({
                "tentativo": tentativo,
                "validazione": None,
                "correzione": correzione
            })
            break

        ordine_corrente = correzione.get("ordine_corretto", ordine_corrente)
        print(f"✏️  Correzioni applicate: {correzione.get('correzioni_applicate', [])}")

        validazione = valida_ordine_fn(ordine_corrente)
        storico.append({
            "tentativo": tentativo,
            "validazione": validazione,
            "correzione": correzione
        })

    stato_finale = validazione.get("validation_status", "INVALID")

    if stato_finale == "VALID":
        print("\n🎉 Ordine validato con successo dopo correzione automatica")
    elif stato_finale == "WARNING":
        print("\n⚠️  Ordine accettato con warning — richiede revisione umana")
    else:
        print("\n❌ Ordine non correggibile entro i tentativi previsti — inoltro a operatore umano")

    return {
        "ordine_finale": ordine_corrente,
        "validazione_finale": validazione,
        "stato_finale": stato_finale,
        "storico": storico
    }