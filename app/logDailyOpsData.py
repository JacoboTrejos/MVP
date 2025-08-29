import os
import json
import datetime
import openai
import uuid

from dotenv import load_dotenv
from datetime import date
from openai import OpenAI

from app.db.session import get_session, create_tables
from app.db.models import Transaction, ActivityCategory, TxnType
from app.reporting import build_text_report

load_dotenv()
client = openai.OpenAI(api_key="")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


#  input message 
message = "hoy vendí 2 kilos de café a 5.000 cada uno"

# test messages: 
# "hoy me compré 5 kilos de fertilizante a 50.000"
# "ayer compré 10 litros de agua a 1.000"
# "hoy vendí 2 kilos de café a 5.000 cada uno"
# "hoy compré 1 saco de abono a 30.000"
# "ayer vendí 3 litros de leche a 2.000 cada uno"

today = datetime.date.today()
inferred_date = None
msg_lower = message.lower()
if "hoy" in msg_lower:
    inferred_date = today.isoformat()
elif "ayer" in msg_lower:
    inferred_date = (today - datetime.timedelta(days=1)).isoformat()

# Define the JSON schema for extraction via function calling
functions = [
    {
        "name": "extract_transaction",
        "description": "Extract transaction details from an unstructured Spanish farm message.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": ["string", "null"], "description": "Date of the transaction in YYYY-MM-DD format, or null if not given (use today if 'hoy' is mentioned)."},
                "activitycategory": {"type": "string", "description": "Category of the activity, one of: compras de equipos y maquinaria, pre-siembra, siembra, fertilización, manejo del cultivo, cosecha, venta."},
                "type": {"type": "string", "description": "Transaction type: 'ingreso' (income) or 'gasto' (expense)."},
                "description": {"type": "string", "description": "Description of the transaction (free-form text)."},
                "quantity": {"type": ["number", "null"], "description": "Quantity of items (if any) as a number, or null if not mentioned."},
                "unit": {"type": ["string", "null"], "description": "Unit of the quantity (e.g., 'kilos', 'litros'), or null if not applicable."},
                "unit_price": {"type": ["number", "null"], "description": "Price per unit if calculable, otherwise null."},
                "total_value": {"type": "number", "description": "Total monetary value of the transaction."},
                "currency": {"type": "string", "description": "Currency code, e.g., 'COP'."},
                "farm_id": {"type": "string", "description": "UUID of the farm (hardcoded for now)."},
                "source_message_id": {"type": ["string", "null"], "description": "Source message ID if applicable, else null."},
                "created_at": {"type": ["string", "null"], "description": "Record creation timestamp, or null."}
            },
            "required": ["activitycategory", "type", "description", "total_value", "currency", "farm_id"]
        }
    }
]

system_prompt = (
    "Eres Clara un asistente experto en gestión agrícola que extrae datos de mensajes. "
    "Analiza el mensaje de texto informal de un agricultor colombiano y devuelve un diccionario JSON "
    "con las siguientes claves: date, activitycategory, type, description, quantity, unit, unit_price, total_value, currency, farm_id, source_message_id, created_at. "
    "Usa 'null' para valores desconocidos o no mencionados. "
    "Las categorías deben ser exactamente una de: compras de equipos y maquinaria, pre-siembra, siembra, fertilización, manejo del cultivo, cosecha, venta. "
    "El tipo debe ser 'ingreso' o 'gasto'. El currency siempre 'COP'. "
    "Si el mensaje dice 'hoy' o 'ayer' y no da una fecha exacta, pon date como null (lo llenaremos con fecha actual). "
    "Interpreta 'a [precio]' con cantidad dada como precio total (no unitario), a menos que se indique claramente lo contrario."
)
user_prompt = f"Mensaje: \"{message}\".\nPor favor, extrae la información en formato JSON siguiendo las instrucciones."

response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ],
    functions=functions,
    function_call={"name": "extract_transaction"}
)

func_args = response.choices[0].message.function_call.arguments
result = json.loads(func_args)

if result.get("date") in (None, "", "null"):
    result["date"] = inferred_date if inferred_date is not None else today.isoformat()

qty = result.get("quantity")
total = result.get("total_value")
if result.get("unit_price") in (None, "null") and qty not in (None, 0) and total not in (None, 0):
    try:
        result["unit_price"] = round(total / qty, 2)
    except Exception:
        result["unit_price"] = None

result["currency"] = "COP"
result["farm_id"] = "00000000-0000-0000-0000-000000000001"

print(json.dumps(result, ensure_ascii=False, indent=2))

# 5) Save into PostgreSQL
# ---------------------------
def to_int_or_none(x):
    if x in (None, "null", ""):
        return None
    try:
        return int(round(float(x)))
    except Exception:
        return None

def to_uuid(x):
    if not x:
        return None
    try:
        return uuid.UUID(str(x))
    except Exception:
        return None

def map_activity(s: str) -> ActivityCategory:
    # Trust the exact strings coming from the extractor
    return ActivityCategory(s)

def map_type(s: str) -> TxnType:
    return TxnType(s)

create_tables()  # create enums + table if not present

with get_session() as db:
    tx = Transaction(
        farm_id=to_uuid(result["farm_id"]) or uuid.UUID("00000000-0000-0000-0000-000000000001"),
        date=datetime.date.fromisoformat(result["date"]),
        activitycategory=map_activity(result["activitycategory"]),
        type=map_type(result["type"]),
        description=result.get("description"),
        quantity=to_int_or_none(result.get("quantity")),
        unit=(result.get("unit") or None),
        unit_price=to_int_or_none(result.get("unit_price")),
        total_value=to_int_or_none(result.get("total_value")),
        currency=result.get("currency") or "COP",
        source_message_id=to_uuid(result.get("source_message_id")),
        # created_at is DB-default NOW()
    )
    db.add(tx)
    db.flush()      # get tx.id without an extra commit
    print(f"\nSaved Transaction ID: {tx.id}")

# Print reports to console (you can call any/all you want)
farm_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
with get_session() as db:
    print("\n--- REPORTES ---")
    print(build_text_report(db, farm_id, period="semanal",  ref=date.today()))
    print()
    print(build_text_report(db, farm_id, period="mensual",  ref=date.today()))
    print()
    print(build_text_report(db, farm_id, period="quarter",  ref=date.today()))
    print()
    print(build_text_report(db, farm_id, period="anual",    ref=date.today()))
