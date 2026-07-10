#!/usr/bin/env python
# coding: utf-8

# ## bronze to silver to gold
# 
# null

# In[1]:


# In[1]:

from pyspark.sql.functions import (
    col,
    lit,
    round as spark_round,
    to_date,
    date_format,
    year,
    month,
    quarter,
    dayofmonth,
    concat,
    lpad,
)
from pyspark.sql.types import *
import json
import os
import re
from datetime import datetime

# ==========================================================
# CONFIG
# ==========================================================

PATH_ARTICOLI = "Files/Bronze/Products/articoli.csv"
PATH_CLIENTI  = "Files/Bronze/Customers/clienti.csv"

PATH_STORICO_ORDINI = "Files/Bronze/Orders/ordini_storici.csv"
PATH_STORICO_RIGHE  = "Files/Bronze/Orders/righe_ordini_storici.csv"

GOLD_DIR = "Files/Gold/ERP"

TABLE_DIM_CLIENTI  = "dim_clienti"
TABLE_DIM_ARTICOLI = "dim_articoli"
TABLE_FACT_ORDINI  = "fact_ordini"
TABLE_DIM_DATA = "dim_data"

SOGLIA_DRIFT_PREZZO_PCT = 5.0


def sanitizza_colonne(df):
    """Rinomina le colonne con caratteri non ASCII/spazi -> underscore,
    necessario per compatibilità Delta/SQL endpoint e per DAX più pulito."""
    for c in df.columns:
        nuovo = re.sub(r'[^A-Za-z0-9_]', '_', c)
        if nuovo != c:
            df = df.withColumnRenamed(c, nuovo)
    return df


# In[2]:

# ==========================================================
# DIM_CLIENTI — quasi un pass-through di clienti.csv
# ==========================================================

clienti_raw = spark.read.option("header", True).option("inferSchema", True).csv(PATH_CLIENTI)

dim_clienti = clienti_raw.select(
    col("id").alias("Cliente_ID"),
    col("ragione_sociale").alias("Cliente"),
    col("partita_iva").alias("Partita_IVA"),
    col("indirizzo").alias("Indirizzo"),
    col("cap").cast("string").alias("CAP"),
    col("citta").alias("Citta"),
    col("provincia").alias("Provincia"),
    col("email").alias("Email"),
    col("telefono").cast("string").alias("Telefono"),
)

print(f"👥 dim_clienti: {dim_clienti.count()} righe")
display(dim_clienti)


# In[3]:

# ==========================================================
# DIM_ARTICOLI — quasi un pass-through di articoli.csv
# ==========================================================

articoli_raw = spark.read.option("header", True).option("inferSchema", True).csv(PATH_ARTICOLI)

dim_articoli = articoli_raw.select(
    col("codice").alias("Codice_Articolo"),
    col("descrizione").alias("Descrizione"),
    col("categoria").alias("Categoria"),
    col("unita_misura").alias("Unita_Misura"),
    col("prezzo_listino").cast("double").alias("Prezzo_Listino"),
)

print(f"📦 dim_articoli: {dim_articoli.count()} righe")
display(dim_articoli)


# In[4]:

# ==========================================================
# FACT_ORDINI — pipeline agentica (solo chiavi + misure, NON attributi
# descrittivi: quelli vivono nelle dimensioni)
# ==========================================================

SCHEMA_FACT = StructType([
    StructField("Riga_ID",               StringType(),  True),
    StructField("Numero_Ordine",         StringType(),  True),
    StructField("Data_Ordine",           StringType(),  True),
    StructField("Data_ID", IntegerType(), True),
    StructField("Cliente_ID",            StringType(),  True),
    StructField("Codice_Articolo",       StringType(),  True),
    StructField("Descrizione_Riga",      StringType(),  True),  # come scritto nel documento originale
    StructField("Quantita",              DoubleType(),  True),
    StructField("Prezzo_Unitario",       DoubleType(),  True),  # prezzo EFFETTIVO applicato (può differire dal listino)
    StructField("Importo_Riga",          DoubleType(),  True),
    StructField("Stato_Validazione",     StringType(),  True),
    StructField("Origine_Dati",          StringType(),  True),  # "Pipeline Agentica" | "Storico"
    StructField("Dati_Incompleti",       BooleanType(), True),
    StructField("Scostamento_Prezzo_Pct",DoubleType(),  True),
    StructField("Data_Elaborazione",     StringType(),  True),
    StructField("Documento_Origine",     StringType(),  True),
    StructField("Pipeline",              StringType(),  True),
    StructField("Versione",              StringType(),  True),
])

validation_df = spark.read.table("silver_validation")
correction_df = spark.read.table("silver_correction")

valid_orders = validation_df.filter(
    col("validation_status").isin("VALID", "WARNING")
).select("document_id", "file_name", "order_json", "validation_json")

corrected_orders = correction_df.filter(
    col("correction_status") == "CORRECTED"
).select(
    "document_id", "file_name",
    col("corrected_order_json").alias("order_json"),
    "validation_json"
)

final_orders = (
    valid_orders if corrected_orders.count() == 0
    else valid_orders.unionByName(corrected_orders)
).dropDuplicates(["document_id"])

categorie_dict = {r["Codice_Articolo"]: r["Categoria"] for r in dim_articoli.collect()}
piva_per_id     = {r["Cliente_ID"]: r["Partita_IVA"] for r in dim_clienti.collect()}

timestamp = datetime.now()
records_pipeline = []

for row in final_orders.collect():

    ordine = json.loads(row.order_json)
    validazione = json.loads(row.validation_json) if row.validation_json else {}

    customer_val = validazione.get("customer_validation", {})
    cliente_id = customer_val.get("matched_customer_id", "")
    categoria_trovata = None

    numero_ordine = ordine.get("riferimento_cliente") or f"ACME-{timestamp.strftime('%Y%m%d%H%M%S')}"
    data_ordine = ordine.get("data_ordine", "")
    stato = validazione.get("validation_status", "VALID")

    for idx, r in enumerate(ordine.get("righe", [])):
        codice = r.get("codice", "")
        categoria_trovata = categorie_dict.get(codice)

        records_pipeline.append({
            "Riga_ID":                f"{row.document_id}-{idx}",
            "Numero_Ordine":          numero_ordine,
            "Data_Ordine":            data_ordine,
            "Data_ID":
                        int(data_ordine.replace("-", ""))
                        if data_ordine else None,
            "Cliente_ID":             cliente_id,
            "Codice_Articolo":        codice,
            "Descrizione_Riga":       r.get("descrizione_raw") or r.get("descrizione", ""),
            "Quantita":               float(r["quantita"]) if r.get("quantita") is not None else None,
            "Prezzo_Unitario":        float(r["prezzo_unitario"]) if r.get("prezzo_unitario") is not None else None,
            "Importo_Riga":           float(r["importo"]) if r.get("importo") is not None else None,
            "Stato_Validazione":      stato,
            "Origine_Dati":           "Pipeline Agentica",
            "Dati_Incompleti":        (cliente_id == "") or (categoria_trovata is None),
            "Scostamento_Prezzo_Pct": None,  # non applicabile: qui il prezzo è già dal listino
            "Data_Elaborazione":      timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "Documento_Origine":      ordine.get("fonte", row.file_name),
            "Pipeline":               "Agent1->Agent2->Agent3",
            "Versione":               "1.2",
        })

print(f"🧾 Righe fact dalla pipeline agentica: {len(records_pipeline)}")
fact_pipeline = spark.createDataFrame(records_pipeline, schema=SCHEMA_FACT)


# In[5]:

# ==========================================================
# FACT_ORDINI — storico ERP (join deterministici, no agenti)
# ==========================================================

storico_disponibile = False

try:
    righe_df  = spark.read.option("header", True).option("inferSchema", True).csv(PATH_STORICO_RIGHE)
    ordini_df = spark.read.option("header", True).option("inferSchema", True).csv(PATH_STORICO_ORDINI)
    storico_disponibile = True
except Exception as e:
    print(f"ℹ️ Storico non disponibile ({e}) — solo pipeline agentica nel fact finale.")

if storico_disponibile:

    articoli_join = dim_articoli.select(
        col("Codice_Articolo").alias("_cod_match"),
        col("Categoria").alias("_categoria_match"),
        col("Prezzo_Listino").alias("_listino_match"),
    )
    clienti_join = dim_clienti.select(col("Cliente_ID").alias("_cli_match"))

    storico_join = (
        righe_df
        .join(ordini_df, "id_ordine", "left")
        .join(clienti_join, col("id_cliente") == col("_cli_match"), "left")
        .join(articoli_join, col("codice_articolo") == col("_cod_match"), "left")
        .withColumn(
            "_scostamento_pct",
            spark_round(
                (col("prezzo_unitario") - col("_listino_match")) / col("_listino_match") * 100, 1
            )
        )
    )

    fact_storico = storico_join.select(
        col("id_riga").cast("string").alias("Riga_ID"),
        col("riferimento_cliente").alias("Numero_Ordine"),
        col("data_ordine").cast("string").alias("Data_Ordine"),
        date_format(to_date(col("data_ordine")),"yyyyMMdd").cast("int").alias("Data_ID"),
        col("id_cliente").cast("string").alias("Cliente_ID"),
        col("codice_articolo").alias("Codice_Articolo"),
        col("descrizione_articolo").alias("Descrizione_Riga"),
        col("quantita").cast("double").alias("Quantita"),
        col("prezzo_unitario").cast("double").alias("Prezzo_Unitario"),
        col("importo_riga").cast("double").alias("Importo_Riga"),
        lit("STORICO").alias("Stato_Validazione"),
        lit("Storico").alias("Origine_Dati"),
        (col("_categoria_match").isNull() | col("_cli_match").isNull()).alias("Dati_Incompleti"),
        col("_scostamento_pct").alias("Scostamento_Prezzo_Pct"),
        lit(None).cast("string").alias("Data_Elaborazione"),
        lit("Storico ERP").alias("Documento_Origine"),
        lit("Storico").alias("Pipeline"),
        lit("Pre-Pipeline").alias("Versione"),
    )

    n_incompleti = fact_storico.filter(col("Dati_Incompleti") == True).count()
    n_drift = fact_storico.filter(
        col("Scostamento_Prezzo_Pct").isNotNull() &
        (col("Scostamento_Prezzo_Pct") > SOGLIA_DRIFT_PREZZO_PCT)
    ).count()
    print(f"📜 Righe storiche: {fact_storico.count()}  |  incomplete: {n_incompleti}  |  drift prezzo: {n_drift}")

    fact_ordini = fact_pipeline.unionByName(fact_storico).dropDuplicates(["Riga_ID"])

else:
    fact_ordini = fact_pipeline

print(f"✅ fact_ordini totale: {fact_ordini.count()} righe")
display(fact_ordini)


# ==========================================================
# DIM_DATA
# ==========================================================


dim_data = (

    fact_ordini

    .select(
        to_date(col("Data_Ordine")).alias("Data")
    )

    .filter(
        col("Data").isNotNull()
    )

    .distinct()

    .withColumn(
        "Data_ID",
        date_format(col("Data"), "yyyyMMdd").cast("int")
    )

    .withColumn(
        "Anno",
        year(col("Data"))
    )

    .withColumn(
        "Trimestre",
        concat(
            lit("Q"),
            quarter(col("Data"))
        )
    )

    .withColumn(
        "NumeroMese",
        month(col("Data"))
    )

    .withColumn(
        "Mese",
        date_format(col("Data"), "MMMM")
    )

    .withColumn(
        "AnnoMese",
        concat(
            year(col("Data")),
            lit("-"),
            lpad(month(col("Data")),2,"0")
        )
    )

    .withColumn(
        "Giorno",
        dayofmonth(col("Data"))
    )

    .withColumn(
        "NomeGiorno",
        date_format(col("Data"),"EEEE")
    )

)

print(
    f"📅 dim_data: {dim_data.count()} righe"
)

display(dim_data)


# In[6]:

# ==========================================================
# SCRITTURA DELTA TABLES — modello a stella per Power BI
# ==========================================================

dim_clienti  = sanitizza_colonne(dim_clienti)
dim_articoli = sanitizza_colonne(dim_articoli)
dim_data = sanitizza_colonne(dim_data)
fact_ordini  = sanitizza_colonne(fact_ordini)

for tabella, df in [

    (TABLE_DIM_CLIENTI, dim_clienti),

    (TABLE_DIM_ARTICOLI, dim_articoli),

    (TABLE_DIM_DATA, dim_data),

    (TABLE_FACT_ORDINI, fact_ordini),

]:
    spark.sql(f"DROP TABLE IF EXISTS {tabella}")
    df.write.mode("overwrite").format("delta").saveAsTable(tabella)
    print(f"✅ Tabella Delta '{tabella}' scritta — {df.count()} righe")


# In[7]:

# ==========================================================
# CSV DI SERVIZIO (facoltativi — utili se Power BI legge da file
# invece che dalla tabella Delta / Direct Lake)
# ==========================================================

os.makedirs(GOLD_DIR, exist_ok=True)

dim_clienti.toPandas().to_csv(f"{GOLD_DIR}/dim_clienti.csv", sep=";", index=False, encoding="utf-8-sig")
dim_data.toPandas().to_csv(f"{GOLD_DIR}/dim_data.csv",sep=";",index=False,encoding="utf-8-sig")
dim_articoli.toPandas().to_csv(f"{GOLD_DIR}/dim_articoli.csv", sep=";", index=False, encoding="utf-8-sig")
fact_ordini.toPandas().to_csv(f"{GOLD_DIR}/fact_ordini.csv", sep=";", index=False, encoding="utf-8-sig")

print(
    f"✅ CSV scritti in {GOLD_DIR}: "
    "dim_clienti.csv, "
    "dim_articoli.csv, "
    "dim_data.csv, "
    "fact_ordini.csv"
)

