-- SCOT — Schéma de la base SCOT (Azure SQL, auth Entra ID uniquement)
-- À exécuter par l'administrateur Entra du serveur. Idempotent.

IF OBJECT_ID('dbo.Predictions') IS NULL
CREATE TABLE dbo.Predictions (
    Id              INT IDENTITY(1,1) PRIMARY KEY,
    BlobName        NVARCHAR(400)  NOT NULL,      -- nom du fichier dans blob-scot
    BlobUrl         NVARCHAR(1000) NULL,
    PredictedClass  NVARCHAR(50)   NOT NULL,      -- tache | rayure | inclusion | sans_defaut
    Confidence      FLOAT          NOT NULL,      -- 0..1
    Probabilities   NVARCHAR(MAX)  NULL,          -- JSON {classe: proba}
    ModelName       NVARCHAR(200)  NULL,
    InferenceMs     INT            NULL,
    ImageWidth      INT            NULL,
    ImageHeight     INT            NULL,
    CreatedAt       DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
    -- Correction experte (remplie depuis l'app Streamlit)
    ValidatedClass  NVARCHAR(50)   NULL,
    ValidatedBy     NVARCHAR(200)  NULL,
    ValidatedAt     DATETIME2      NULL,
    OperatorComment NVARCHAR(1000) NULL
);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_Predictions_CreatedAt')
CREATE INDEX IX_Predictions_CreatedAt ON dbo.Predictions (CreatedAt DESC);

-- Identité managée de la Function : écrit les prédictions
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'fn-scot-app')
CREATE USER [fn-scot-app] FROM EXTERNAL PROVIDER;
GRANT SELECT, INSERT ON dbo.Predictions TO [fn-scot-app];

-- Identité managée de l'app Streamlit : lit et enregistre la correction experte
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'scot-inspection')
CREATE USER [scot-inspection] FROM EXTERNAL PROVIDER;
GRANT SELECT ON dbo.Predictions TO [scot-inspection];
GRANT UPDATE (ValidatedClass, ValidatedBy, ValidatedAt, OperatorComment) ON dbo.Predictions TO [scot-inspection];
