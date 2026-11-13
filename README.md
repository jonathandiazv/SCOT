# SCOT — Système de Contrôle Optique sur surfaces Transparentes

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![PyTorch](https://img.shields.io/badge/PyTorch-%23EE4C2C.svg?style=flat&logo=PyTorch&logoColor=white)](https://pytorch.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-%23FF4B4B.svg?style=flat&logo=Streamlit&logoColor=white)](https://streamlit.io/)
[![Azure](https://img.shields.io/badge/Azure-0078D4?style=flat&logo=microsoftazure&logoColor=white)](https://azure.microsoft.com/)

Projet innovation de Télécom Saint-Étienne. Objectif : détecter automatiquement des défauts invisibles à l'œil nu sur des plaques de verre, grâce à un **montage optique de strioscopie** et à un **réseau de neurones** qui classe les défauts. Cible : au plus **10 % de défauts non détectés**.

**Application** : https://scot-inspection.azurewebsites.net (un compte par personne, à demander à Jonathan).

## Comment ça marche

```
Caméra + SDK ─► dossier du PC ─► veilleur ─► Azure Blob ─► Azure Function ─► Azure SQL ─► Application web
                                                          (classification)              (résultat + validation)
```

1. Le **SDK caméra** prend la photo, découpe chaque défaut et dépose une image par défaut, nommée `P<plaque>_<défaut>_<YYMMDDHHMMSS>.png` (ex. `P1_2_261113143005.png` = plaque 1, 2e défaut).
2. Le **veilleur** (`camera/`) détecte chaque nouvelle image et l'envoie dans Azure.
3. Une **Azure Function** classe l'image avec le modèle (ResNet18 exporté en ONNX) et enregistre le résultat dans **Azure SQL**.
4. L'**application web** affiche le résultat quelques secondes plus tard (moins de 4 s mesurées). L'opérateur confirme ou corrige la classe ; ses corrections serviront à ré-entraîner le modèle.

Les images peuvent aussi être envoyées à la main depuis l'application.

Classes actuelles : `tache`, `rayure`, `inclusion`, et `sans_defaut`. Cette dernière n'est pour l'instant qu'une règle (image entièrement noire), pas une classe apprise.

> ⚠️ Le modèle actuel a été entraîné sur des **images de simulation**. Ses performances sur les vraies images du montage restent à mesurer.

Détail complet (ressources Azure, tables SQL, droits, flux) : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ([PDF](docs/ARCHITECTURE.pdf)).

## Organisation du dépôt

| Dossier / fichier | Rôle | Tourne sur |
|---|---|---|
| `train.py` | entraînement du modèle (ResNet18, transfer learning) | PC local |
| `export_onnx.py` | conversion du modèle `.pth` → `.onnx` pour Azure, avec vérification | PC local |
| `predict.py`, `app.py` | inférence et application d'origine, 100 % locales | PC local |
| `function/` | Azure Function de classification | Azure (`fn-scot-app`) |
| `webapp/` | application web Streamlit | Azure (`scot-inspection`) |
| `camera/` | veilleur du dossier caméra ([mode d'emploi](camera/README.md)) | PC du montage |
| `scripts/` | gestion des comptes de l'app, pare-feu SQL | PC local |
| `sql/schema.sql` | création de la table `dbo.Predictions` et des droits | base Azure SQL |
| `docs/` | architecture détaillée (Markdown + PDF) | — |
| `dataset/`, `test_images/` | images d'entraînement (simulation) et images de test | — |

## Installation (poste de développement)

Prérequis : **Python 3.12**, **Git**, et l'**[Azure CLI](https://aka.ms/installazurecliwindows)** pour tout ce qui touche à Azure.

```powershell
git clone https://devops.telecomste.fr/diaz-vreys.jonathan/scot-projet-innovation.git
cd scot-projet-innovation
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # sans GPU NVIDIA
pip install -r requirements.txt -r webapp\requirements.txt
az login                                                                          # compte de l'université
```

> Avec un GPU NVIDIA, installer directement `pip install -r requirements.txt`, qui récupère la version CUDA de PyTorch.

## Tâches courantes

**Entraîner puis mettre un nouveau modèle en production**
```powershell
python train.py                                   # → outputs\best_model.pth
python export_onnx.py                             # → outputs\best_model.onnx (vérifie PyTorch = ONNX)
az storage blob upload --account-name projetscot -c models -n best_model.onnx -f outputs\best_model.onnx --auth-mode login --overwrite
```
La Function charge le nouveau modèle automatiquement, sans redéploiement.

**Lancer l'application en local** (connectée aux vraies données Azure)
```powershell
powershell -ExecutionPolicy Bypass -File webapp\run_local.ps1     # → http://localhost:8501
```

**Accéder à la base SQL hors de l'école** (sur le réseau de l'université, c'est automatique)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\sql_firewall_mon_ip.ps1
```

**Gérer les comptes de l'application**
```powershell
python scripts\gerer_comptes.py lister
python scripts\gerer_comptes.py ajouter prenom.nom --nom "Prénom Nom"    # mot de passe affiché une seule fois
python scripts\gerer_comptes.py reinitialiser prenom.nom
python scripts\gerer_comptes.py supprimer prenom.nom
python scripts\gerer_comptes.py role prenom.nom admin                  # accès à la page Administration (ou : operateur)
```

**Installer le veilleur sur le PC du montage** : voir [`camera/README.md`](camera/README.md).

**Redéployer la Function ou l'application** : voir la section « Mettre à jour » de [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Sécurité
- Aucun mot de passe ni aucune clé dans le code. Azure est accessible par les comptes de l'université (`az login`) ou par les identités managées des services.
- Les fichiers sensibles restent locaux et sont exclus de git : `function/local.settings.json`, `camera/config.json`.
- Les mots de passe de l'application ne sont stockés que sous forme d'empreinte chiffrée.

## Équipe
Arthur COL, Enzo GARBI, Tanka JANET-MAITRE, Jonathan DIAZ-VREYS, Hugo SOYSOUVANH — Télécom Saint-Étienne.
