"""
SCOT — Azure Function d'inférence.

Déclencheur : une image déposée dans le conteneur Blob `blob-scot`
(via Event Grid, obligatoire sur le plan Flex Consumption).
Traitement  : classification ONNX, puis écriture du résultat dans SQL (dbo.Predictions).

Paramètres d'application (App Settings) :
  AzureWebJobsStorage   connexion au compte de stockage (déjà présent)
  MODEL_CONTAINER       conteneur du modèle (défaut : models)
  MODEL_BLOB            nom du modèle actif (défaut : best_model.onnx)
  SQL_SERVER            ex. projectscot.database.windows.net
  SQL_DATABASE          ex. SCOT
L'accès SQL se fait par l'identité managée de la Function : aucun mot de passe.
"""

import json
import logging
import os
import struct
import threading

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

from scot_inference import OnnxClassifier

app = func.FunctionApp()

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")

_lock = threading.Lock()
_model: OnnxClassifier | None = None
_model_etag: str | None = None
_credential = DefaultAzureCredential()


def _blob_service() -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])


def get_model() -> OnnxClassifier:
    """Charge le modèle depuis le Blob, et le recharge si le fichier a changé (etag)."""
    global _model, _model_etag
    container = os.environ.get("MODEL_CONTAINER", "models")
    name = os.environ.get("MODEL_BLOB", "best_model.onnx")
    blob = _blob_service().get_blob_client(container, name)
    etag = blob.get_blob_properties().etag
    with _lock:
        if _model is None or etag != _model_etag:
            logging.info("Chargement du modèle %s/%s (etag %s)", container, name, etag)
            _model = OnnxClassifier(blob.download_blob().readall(), model_name=name)
            _model_etag = etag
        return _model


def sql_connect():
    import pyodbc  # ODBC Driver 18 est préinstallé sur les images Python d'Azure Functions

    token = _credential.get_token("https://database.windows.net/.default").token.encode("utf-16-le")
    token_struct = struct.pack(f"<I{len(token)}s", len(token), token)
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server=tcp:{os.environ['SQL_SERVER']},1433;Database={os.environ['SQL_DATABASE']};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=60;"
    )
    return pyodbc.connect(conn_str, attrs_before={1256: token_struct})  # 1256 = SQL_COPT_SS_ACCESS_TOKEN


def save_prediction(blob_name: str, blob_url: str, res: dict) -> None:
    with sql_connect() as conn:
        conn.cursor().execute(
            """INSERT INTO dbo.Predictions
               (BlobName, BlobUrl, PredictedClass, Confidence, Probabilities, ModelName,
                InferenceMs, ImageWidth, ImageHeight)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            blob_name, blob_url, res["predicted_class"], res["confidence"],
            json.dumps(res["probabilities"]), res["model_name"], res["inference_ms"],
            res["width"], res["height"],
        )
        conn.commit()


@app.blob_trigger(arg_name="blob", path="blob-scot/{name}",
                  connection="AzureWebJobsStorage", source="EventGrid")
def classify_image(blob: func.InputStream):
    name = blob.name.split("/", 1)[-1]
    if not name.lower().endswith(IMAGE_EXTS):
        logging.info("Ignoré (pas une image) : %s", name)
        return

    res = get_model().predict_bytes(blob.read())
    logging.info("%s → %s (%.1f %%) en %d ms", name, res["predicted_class"],
                 res["confidence"] * 100, res["inference_ms"])
    save_prediction(name, blob.uri, res)


@app.route(route="health", auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    """Vérifie que le modèle se charge : GET /api/health"""
    try:
        m = get_model()
        body = {"status": "ok", "model": m.model_name, "classes": m.display_classes}
        return func.HttpResponse(json.dumps(body), mimetype="application/json")
    except Exception as e:  # noqa: BLE001
        logging.exception("health")
        return func.HttpResponse(json.dumps({"status": "error", "detail": str(e)}),
                                 status_code=500, mimetype="application/json")
