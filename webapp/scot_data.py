"""
SCOT — Accès aux données pour l'app web : Azure SQL (prédictions) et Blob (images).

Authentification Entra ID partout, sans mot de passe :
  - en local : le compte connecté avec `az login`
  - sur App Service : l'identité managée de l'application
"""

import os
import struct
import time
from datetime import datetime, timezone

import pandas as pd
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

SQL_SERVER = os.environ.get("SQL_SERVER", "projectscot.database.windows.net")
SQL_DATABASE = os.environ.get("SQL_DATABASE", "SCOT")
STORAGE_ACCOUNT = os.environ.get("STORAGE_ACCOUNT", "projetscot")
IMAGE_CONTAINER = os.environ.get("IMAGE_CONTAINER", "blob-scot")

_credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)


def _connect(retries: int = 4):
    """La base serverless se met en pause : la 1re connexion expire pendant son réveil (~1 min)."""
    for attempt in range(retries):
        try:
            return _connect_once()
        except Exception as e:  # noqa: BLE001
            if attempt == retries - 1 or not any(s in str(e) for s in ("Timeout", "timeout", "40613", "not currently available")):
                raise
            time.sleep(10)


def _connect_once():
    """pyodbc + ODBC Driver 18 si présent (App Service Linux), sinon mssql-python (pip seul)."""
    try:
        import pyodbc
        has_odbc18 = "ODBC Driver 18 for SQL Server" in pyodbc.drivers()
    except ImportError:
        has_odbc18 = False

    if has_odbc18:
        token = _credential.get_token("https://database.windows.net/.default").token.encode("utf-16-le")
        attrs = {1256: struct.pack(f"<I{len(token)}s", len(token), token)}  # SQL_COPT_SS_ACCESS_TOKEN
        return pyodbc.connect(
            "Driver={ODBC Driver 18 for SQL Server};"
            f"Server=tcp:{SQL_SERVER},1433;Database={SQL_DATABASE};"
            "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=90;",
            attrs_before=attrs,
        )

    import mssql_python
    return mssql_python.connect(
        f"Server=tcp:{SQL_SERVER},1433;Database={SQL_DATABASE};Encrypt=yes;"
        "Authentication=ActiveDirectoryDefault"
    )


COLUMNS = ["Id", "BlobName", "BlobUrl", "PredictedClass", "Confidence", "Probabilities",
           "ModelName", "InferenceMs", "CreatedAt", "ValidatedClass", "ValidatedBy",
           "ValidatedAt", "OperatorComment"]


def fetch_predictions(limit: int = 500) -> pd.DataFrame:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT TOP ({int(limit)}) {', '.join(COLUMNS)} "
                    "FROM dbo.Predictions ORDER BY CreatedAt DESC, Id DESC")
        rows = [tuple(r) for r in cur.fetchall()]
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=COLUMNS)
    if not df.empty:
        df["CreatedAt"] = pd.to_datetime(df["CreatedAt"], utc=True)
        df["Confidence"] = df["Confidence"].astype(float)
        # Colonnes texte facultatives : None (et non NaN) quand elles sont vides
        for c in ("ValidatedClass", "ValidatedBy", "OperatorComment", "ModelName", "BlobUrl"):
            df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df


def save_validation(pred_id: int, validated_class: str, operator: str, comment: str) -> None:
    conn = _connect()
    try:
        conn.cursor().execute(
            "UPDATE dbo.Predictions SET ValidatedClass = ?, ValidatedBy = ?, "
            "ValidatedAt = SYSUTCDATETIME(), OperatorComment = ? WHERE Id = ?",
            validated_class, operator or None, comment or None, int(pred_id),
        )
        conn.commit()
    finally:
        conn.close()


def upload_image(filename: str, data: bytes, content_type: str | None = None) -> str:
    """Dépose l'image dans blob-scot : Event Grid déclenche alors la Function d'inférence."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    name = f"{stamp}_{os.path.basename(filename)}"
    svc = BlobServiceClient(f"https://{STORAGE_ACCOUNT}.blob.core.windows.net", credential=_credential)
    svc.get_blob_client(IMAGE_CONTAINER, name).upload_blob(
        data, overwrite=False,
        content_settings=ContentSettings(content_type=content_type or "image/png"),
    )
    return name
