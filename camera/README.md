# Veilleur caméra SCOT

Programme qui tourne en continu sur le PC du montage optique. Il surveille le dossier où le SDK caméra dépose les **images traitées** (une image par défaut détecté) et envoie chaque nouvelle image dans le conteneur Azure `blob-scot`. L'envoi déclenche toute la chaîne : Event Grid → Function (ONNX) → SQL → app web. Il faut compter **environ 7 s** entre le dépôt dans le dossier et l'affichage dans l'app.

Les images brutes, avant traitement, ne sont pas concernées : elles sont rangées par le SDK dans un autre dossier.

## Ce que fait le veilleur
- Il surveille le dossier racine **et tous ses sous-dossiers** (année / mois / jour), grâce aux notifications de Windows, avec en plus un balayage complet toutes les 30 s par sécurité.
- Il n'envoie que les noms au format `P<plaque>_<défaut>_<YYMMDDHHMMSS>.<png|jpg|bmp|tif>`, par exemple `P1_2_261113143005.png` (plaque 1, 2e défaut). Les autres fichiers sont ignorés, avec un avertissement dans le log.
- Il ignore les fichiers `.tmp` et attend qu'une image soit complètement écrite avant de l'envoyer.
- **Il n'envoie jamais une image deux fois** : un journal local (`camera_envoyees.db`) garde les noms déjà envoyés, et Azure refuse de toute façon de remplacer une image existante.
- Il **rattrape au démarrage** les images arrivées pendant qu'il était arrêté.
- En cas de **coupure réseau**, il réessaie automatiquement (2 s, 4 s, 8 s… jusqu'à 5 min).
- Il **garde la Function éveillée** en l'appelant toutes les 5 min, pour éviter 10 à 20 s d'attente sur la première image.
- Il **ne modifie, ne déplace et ne supprime aucun fichier** du SDK.

## Installation sur le PC du montage
1. Récupérer le repo et créer l'environnement Python 3.12 :
   ```powershell
   py -3.12 -m venv .venv
   .venv\Scripts\python -m pip install -r camera\requirements.txt
   ```
2. Créer le jeton d'accès. Il faut avoir l'[Azure CLI](https://aka.ms/installazurecliwindows) et avoir fait `az login` avec un compte Owner ou Contributor :
   ```powershell
   powershell -ExecutionPolicy Bypass -File camera\creer_jeton_camera.ps1
   ```
   Le script crée `camera\config.json` avec un jeton qui ne permet **que d'ajouter** des images dans `blob-scot`. Ce jeton est valable 12 mois, et le fichier `config.json` est exclu de git. Une fois ce jeton créé, le PC du montage n'a plus besoin de `az login`.
3. Dans `camera\config.json`, mettre dans `dossier_images` le dossier racine des images **traitées** du SDK.
4. Tester à la main, avec Ctrl+C pour arrêter :
   ```powershell
   .venv\Scripts\python camera\scot_camera.py
   ```
5. Installer le lancement automatique à l'ouverture de session, sans fenêtre, avec relance automatique en cas d'arrêt :
   ```powershell
   powershell -ExecutionPolicy Bypass -File camera\installer_tache.ps1
   ```

## Au quotidien
| Besoin | Commande |
|---|---|
| Voir ce qui se passe | ouvrir `camera\logs\scot_camera.log` |
| Arrêter / désinstaller le lancement auto | `powershell -ExecutionPolicy Bypass -File camera\installer_tache.ps1 -Desinstaller` |
| Renouveler le jeton (avant expiration) | `powershell -ExecutionPolicy Bypass -File camera\creer_jeton_camera.ps1` |
| Couper l'accès du PC caméra (PC perdu, jeton divulgué) | `powershell -ExecutionPolicy Bypass -File camera\creer_jeton_camera.ps1 -Revoquer` |
| Renvoyer une image | impossible par conception : une image envoyée n'est jamais remplacée. Il faut la reprendre avec un nouvel horodatage. |

## Paramètres (`config.json`)
| Clé | Défaut | Rôle |
|---|---|---|
| `dossier_images` | — | dossier racine des images traitées (sous-dossiers inclus) |
| `url_sas_conteneur` | — | URL du conteneur + jeton, écrite par `creer_jeton_camera.ps1` |
| `url_sante_function` | `…/api/health` | pour garder la Function éveillée |
| `balayage_secondes` | 30 | intervalle du balayage complet de sécurité |
| `stabilite_secondes` | 1.0 | délai sans changement de taille avant d'envoyer |
| `reveil_function_secondes` | 300 | intervalle de réveil de la Function (0 = désactivé) |
| `journal` | `camera_envoyees.db` | journal des images envoyées |
| `fichier_log` | `logs/scot_camera.log` | log (5 fichiers de 2 Mo en rotation) |

## À convenir avec le SDK
- Écrire chaque image sous un nom temporaire (`….png.tmp`), puis la renommer une fois terminée. Le veilleur sait aussi attendre la fin d'écriture sans ça, mais le renommage est plus sûr.
- Garder le format de nom `P<plaque>_<défaut>_<YYMMDDHHMMSS>`, en précisant si l'heure est locale ou UTC.
