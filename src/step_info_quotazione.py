import requests

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
MAIL_ENDPOINT   = "http://ja.4labs.it:8080/api/mail/to-rfc822"
EMAIL_OPERATORE = "operatore@acme.it"


# ---------------------------------------------------------------------------
# HELPER — invio email
# ---------------------------------------------------------------------------

def invia_email(to: str, subject: str, body_html: str) -> None:
    """
    Invia una email tramite l'endpoint POST /api/mail/to-rfc822.
    """
    payload = {
        "to": [to],
        "subject": subject,
        "bodyHtml": body_html
    }
    response = requests.post(MAIL_ENDPOINT, json=payload)
    response.raise_for_status()


# ---------------------------------------------------------------------------
# GESTIONE INFO
# ---------------------------------------------------------------------------

def gestisci_info(risultato: dict) -> dict:
    """
    Riceve il JSON prodotto dall'agente 1 (tipo="info"),
    prepara una bozza di risposta e la inoltra all'operatore via email.
    """
    cliente = risultato.get("cliente_raw", "N/D")
    fonte   = risultato.get("fonte", "N/D")
    risposta_bozza = risultato.get("risposta", "")

    print("\n📋 RICHIESTA INFO")
    print(f"Cliente: {cliente}")
    print(risposta_bozza)

    body = f"""
    <h2>Richiesta informazioni — {fonte}</h2>
    <p><b>Cliente:</b> {cliente}</p>
    <p><b>Bozza risposta generata dall'agente:</b></p>
    <p>{risposta_bozza}</p>
    <p><i>Verificare e inviare al cliente.</i></p>
    """

    try:
        invia_email(EMAIL_OPERATORE, f"[Acme] Bozza risposta info — {fonte}", body)
        print("📧 Bozza inoltrata all'operatore")
        esito = "ok"
    except requests.RequestException as e:
        print(f"❌ Errore invio email: {e}")
        esito = "errore_invio"

    return {
        "tipo": "info",
        "cliente": cliente,
        "fonte": fonte,
        "esito": esito
    }


# ---------------------------------------------------------------------------
# GESTIONE QUOTAZIONE
# ---------------------------------------------------------------------------

def gestisci_quotazione(risultato: dict) -> dict:
    """
    Riceve il JSON prodotto dall'agente 1 (tipo="quotazione"),
    prepara il riepilogo da listino e lo inoltra all'operatore via email.
    """
    cliente = risultato.get("cliente_raw", "N/D")
    fonte   = risultato.get("fonte", "N/D")
    righe   = risultato.get("righe", [])
    totale  = risultato.get("totale", 0.0)

    print("\n💰 QUOTAZIONE")
    print(f"Cliente: {cliente}")
    for r in righe:
        print(f"  {r['codice']} | {r['descrizione']} | {r['quantita']} {r['unita']} | €{r['importo']:.2f}")
    print(f"Totale: €{totale:.2f}")

    righe_html = "".join(
        f"<tr><td>{r['codice']}</td><td>{r['descrizione']}</td>"
        f"<td>{r['quantita']}</td><td>€{r['prezzo_unitario']:.2f}</td>"
        f"<td>€{r['importo']:.2f}</td></tr>"
        for r in righe
    )

    body = f"""
    <h2>Quotazione preparata — {fonte}</h2>
    <p><b>Cliente:</b> {cliente}</p>
    <table border="1" cellpadding="6">
      <tr><th>Codice</th><th>Descrizione</th><th>Qta</th><th>Prezzo</th><th>Importo</th></tr>
      {righe_html}
    </table>
    <p><b>Totale: €{totale:.2f}</b></p>
    """

    try:
        invia_email(EMAIL_OPERATORE, f"[Acme] Quotazione — {cliente}", body)
        print("📧 Quotazione inoltrata all'operatore")
        esito = "ok"
    except requests.RequestException as e:
        print(f"❌ Errore invio email: {e}")
        esito = "errore_invio"

    return {
        "tipo": "quotazione",
        "cliente": cliente,
        "fonte": fonte,
        "totale": totale,
        "esito": esito
    }