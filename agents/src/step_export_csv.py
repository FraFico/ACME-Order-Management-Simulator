import os
import pandas as pd
from datetime import datetime

OUTPUT_DIR = "output_csv"


def esporta_csv(ordine: dict, validazione: dict = None) -> str:
    """
    Converte l'ordine validato nel CSV di importazione ERP.

    Il CSV contiene sia i dati dell'ordine sia alcune informazioni
    di tracciabilità utili per audit e import nei sistemi gestionali.
    """

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    timestamp = datetime.now()

    numero_ordine = ordine.get("numero_ordine", "")
    data_ordine = ordine.get("data_ordine", "")

    cliente = ordine.get("cliente", "")
    cliente_id = ordine.get("cliente_id", "")
    partita_iva = ordine.get("partita_iva", "")

    fonte = ordine.get("fonte", "")
    righe = ordine.get("righe", [])

    stato = "VALID"

    if validazione:
        stato = validazione.get("validation_status", "VALID")

    records = []

    for r in righe:

        records.append({

            # ------------------------------
            # HEADER ERP
            # ------------------------------
            "Numero Ordine": numero_ordine,
            "Data Ordine": data_ordine,

            "Cliente ID": cliente_id,
            "Cliente": cliente,
            "Partita IVA": partita_iva,

            # ------------------------------
            # RIGA ORDINE
            # ------------------------------
            "Codice Articolo": r.get("codice", ""),
            "Descrizione": r.get("descrizione", ""),
            "Categoria": r.get("categoria", ""),

            "Quantità": r.get("quantita", ""),
            "UM": r.get("unita", ""),

            "Prezzo Unitario": r.get("prezzo_unitario", ""),
            "Importo Riga": r.get("importo", ""),

            # ------------------------------
            # METADATI ERP
            # ------------------------------
            "Stato Validazione": stato,

            "Data Elaborazione":
                timestamp.strftime("%Y-%m-%d %H:%M:%S"),

            "Documento Origine": fonte,

            "Pipeline":
                "Agent1->Agent2->Agent3->Agent2",

            "Versione":
                "1.0"

        })

    df = pd.DataFrame(records)

    nome_file = (
        f"ERP_ORDINE_{numero_ordine}_"
        f"{timestamp.strftime('%Y%m%d_%H%M%S')}.csv"
    )

    path = os.path.join(OUTPUT_DIR, nome_file)

    df.to_csv(
        path,
        index=False,
        sep=";",
        encoding="utf-8-sig"
    )

    print("\n===================================")
    print("✅ FILE ERP GENERATO")
    print(path)
    print("===================================\n")

    return path