import json
import sys

from step_1_classificazione import leggi_pdf_con_llm
from step_2_validazione import valida_ordine
from step_3_correzione import processa_ordine_con_correzione
from step_info_quotazione import gestisci_info, gestisci_quotazione
from step_export_csv import esporta_csv

# ---------------------------------------------------------------------------
# CONFIG — path del PDF da processare
# Passalo come argomento da linea di comando, es:
#   python main.py data/pdf_input/ordine_cliente_A.pdf
# Se non specificato, usa il file di esempio incluso nel repo.
# ---------------------------------------------------------------------------
PATH_PDF_DEFAULT = "data/pdf_input/ordine_cliente_A.pdf"


# ---------------------------------------------------------------------------
# STAMPA STORICO — leggibile a schermo, passaggio per passaggio
# ---------------------------------------------------------------------------

def stampa_storico(storico: list) -> None:
    print("\n" + "=" * 60)
    print("  📜 STORICO VALIDAZIONE / CORREZIONE")
    print("=" * 60)

    for step in storico:
        tentativo = step["tentativo"]
        validazione = step.get("validazione")
        correzione  = step.get("correzione")

        print(f"\n--- Tentativo {tentativo} ---")

        if validazione is not None:
            stato = validazione.get("validation_status", "N/D")
            errori = validazione.get("errors", [])
            warning = validazione.get("warnings", [])
            print(f"  Validazione agente 2 → stato: {stato}")
            if errori:
                print(f"  Errori: {errori}")
            if warning:
                print(f"  Warning: {warning}")
        else:
            print("  Validazione agente 2 → non eseguita (correzione non applicata)")

        if correzione is not None:
            correggibile = correzione.get("correggibile")
            print(f"  Correzione agente 3 → correggibile: {correggibile}")
            if correggibile:
                print(f"  Modifiche applicate: {correzione.get('correzioni_applicate', [])}")
            else:
                print(f"  Motivo non correggibile: {correzione.get('motivo_non_correggibile', 'N/D')}")
        else:
            print("  Correzione agente 3 → non necessaria a questo step")

    print("\n" + "=" * 60)


# ---------------------------------------------------------------------------
# GESTIONE ORDINE — agente 2 (validazione) + agente 3 (correzione)
# ---------------------------------------------------------------------------

def gestisci_ordine(risultato: dict) -> dict:
    print("\n✅ ORDINE RICONOSCIUTO — avvio validazione con correzione automatica")

    esito = processa_ordine_con_correzione(risultato, valida_ordine)

    stampa_storico(esito["storico"])

    print(f"\n📌 STATO FINALE: {esito['stato_finale']}")

    # Esporta il CSV solo se l'ordine è valido
    if esito["stato_finale"] == "VALID":

        percorso_csv = esporta_csv(esito["ordine_finale"])

        esito["csv_generato"] = percorso_csv

    else:
        print("\n📄 Nessun CSV generato.")

    return esito


# ---------------------------------------------------------------------------
# GESTIONE CASO "UMANO"
# ---------------------------------------------------------------------------

def gestisci_umano(risultato: dict) -> dict:
    print("\n⚠️  INOLTRO A OPERATORE UMANO")
    print(f"Motivo: {risultato.get('motivo', 'non specificato')}")
    return risultato


# ---------------------------------------------------------------------------
# ROUTER PRINCIPALE
# ---------------------------------------------------------------------------

def gestisci_risposta(risultato: dict) -> dict:
    tipo = risultato.get("tipo")

    if tipo == "info":
        return gestisci_info(risultato)

    elif tipo == "quotazione":
        return gestisci_quotazione(risultato)

    elif tipo == "ordine":
        return gestisci_ordine(risultato)

    elif tipo == "umano":
        return gestisci_umano(risultato)

    else:
        print(f"\n❓ Tipo sconosciuto: {tipo}")
        return risultato


# ---------------------------------------------------------------------------
# ENTRY POINT — pipeline completa
# ---------------------------------------------------------------------------

def esegui_pipeline(pdf_path: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  ACME MANUFACTURING — Pipeline Ordini")
    print(f"  File: {pdf_path}")
    print(f"{'='*60}")

    print("\n📄 Step 1: lettura e classificazione documento (agente 1)...")
    risultato = leggi_pdf_con_llm(pdf_path)
    print(f"   Tipo rilevato: {risultato.get('tipo')} "
          f"(confidenza: {risultato.get('confidenza', '?')})")

    esito = gestisci_risposta(risultato)

    # Salva sempre il JSON dell'ultimo ordine processato, utile per debug/test
    with open("order.json", "w", encoding="utf-8") as f:
        json.dump(risultato, f, ensure_ascii=False, indent=4)

    # Se è un ordine, salva anche lo storico completo per audit/dimostrazione
    if risultato.get("tipo") == "ordine":
        with open("storico_ordine.json", "w", encoding="utf-8") as f:
            json.dump(esito, f, ensure_ascii=False, indent=4)

    return esito


if __name__ == "__main__":
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else PATH_PDF_DEFAULT
    esegui_pipeline(pdf_path)