"""
SCOT — Gestion des comptes de l'app web (scot-inspection).

Les comptes sont stockés dans le paramètre d'application SCOT_USERS de l'App
Service : identifiant, nom affiché et empreinte du mot de passe (jamais le mot
de passe lui-même). Chaque modification redémarre l'app (~30 s) : les personnes
connectées devront se reconnecter.

Prérequis : Azure CLI + `az login` avec un compte qui a les droits sur l'app.

Exemples (depuis le dossier scot-projet-innovation) :
  .venv\\Scripts\\python scripts\\gerer_comptes.py lister
  .venv\\Scripts\\python scripts\\gerer_comptes.py ajouter prof.dupont --nom "Marie Dupont"
  .venv\\Scripts\\python scripts\\gerer_comptes.py ajouter prof.dupont --nom "Marie Dupont" --choisir-mdp
  .venv\\Scripts\\python scripts\\gerer_comptes.py reinitialiser arthur.col
  .venv\\Scripts\\python scripts\\gerer_comptes.py supprimer prof.dupont
  .venv\\Scripts\\python scripts\\gerer_comptes.py role arthur.col admin       # ou : operateur
  .venv\\Scripts\\python scripts\\gerer_comptes.py ajouter chef.atelier --nom "Chef Atelier" --admin

Par défaut, un mot de passe aléatoire est généré et affiché UNE seule fois :
transmettez-le à la personne (en main propre ou par message privé).
"""

import argparse
import getpass
import json
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "webapp"))
from scot_auth import hash_password  # noqa: E402

RESOURCE_GROUP = "VisualStudioOnline-E84EAA5FD02E457DBDF1D43E9E02F69B"
WEBAPP = "scot-inspection"
SETTING = "SCOT_USERS"
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,59}$")
AZ_PYTHON = Path(r"C:\Program Files\Microsoft SDKs\Azure\CLI2\python.exe")


def az(*args: str) -> str:
    """Appelle Azure CLI. Sous Windows, on passe par son python.exe pour éviter les soucis de az.cmd."""
    if AZ_PYTHON.exists():
        cmd = [str(AZ_PYTHON), "-IBm", "azure.cli", *args]
    else:
        exe = shutil.which("az")
        if not exe:
            sys.exit("Azure CLI introuvable : installez-le puis lancez `az login`.")
        cmd = [exe, *args]
    res = subprocess.run([*cmd, "--only-show-errors"], capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        sys.exit(f"Erreur Azure CLI : {res.stderr.strip() or res.stdout.strip()}")
    return res.stdout.strip()


def load_users() -> dict:
    raw = az("webapp", "config", "appsettings", "list", "-g", RESOURCE_GROUP, "-n", WEBAPP,
             "--query", f"[?name=='{SETTING}'].value | [0]", "-o", "tsv")
    return json.loads(raw) if raw else {}


def save_users(users: dict) -> None:
    payload = [{"name": SETTING, "value": json.dumps(users, ensure_ascii=False, separators=(",", ":")),
                "slotSetting": False}]
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "settings.json"
        f.write_text(json.dumps(payload), encoding="utf-8")
        az("webapp", "config", "appsettings", "set", "-g", RESOURCE_GROUP, "-n", WEBAPP,
           "--settings", f"@{f}", "-o", "none")
    print("✓ Comptes enregistrés sur Azure. L'app redémarre (~30 s).")


def new_password(args) -> str:
    if args.choisir_mdp:
        while True:
            p1 = getpass.getpass("Mot de passe (12 caractères min.) : ")
            p2 = getpass.getpass("Confirmez : ")
            if p1 != p2:
                print("Les deux saisies diffèrent.")
            elif len(p1) < 12:
                print("Trop court : 12 caractères minimum.")
            else:
                return p1
    return secrets.token_urlsafe(12)  # 16 caractères aléatoires


def deliver(identifiant: str, password: str, args) -> None:
    """Affiche le mot de passe, ou l'ajoute à un fichier si --fichier est donné."""
    if args.choisir_mdp:
        return
    line = f"{identifiant}\t{password}"
    if args.fichier:
        with open(args.fichier, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        print(f"  Mot de passe de {identifiant} ajouté à {args.fichier}")
    else:
        print(f"\n  Identifiant : {identifiant}\n  Mot de passe : {password}\n"
              "  (affiché une seule fois : transmettez-le maintenant)\n")


def cmd_lister(args) -> None:
    users = load_users()
    if not users:
        print("Aucun compte.")
    for u, info in sorted(users.items()):
        print(f"{u:<28} {info.get('name', ''):<28} {info.get('role', 'operateur')}")


def cmd_ajouter(args) -> None:
    ident = args.identifiant.strip().lower()
    if not USERNAME_RE.match(ident):
        sys.exit("Identifiant invalide : minuscules, chiffres, . _ - (ex. prenom.nom).")
    users = load_users()
    if ident in users:
        sys.exit(f"Le compte {ident} existe déjà (utilisez « reinitialiser » pour changer son mot de passe).")
    password = new_password(args)
    users[ident] = {"name": args.nom.strip(), "hash": hash_password(password),
                    "role": "admin" if args.admin else "operateur"}
    save_users(users)
    deliver(ident, password, args)


def cmd_role(args) -> None:
    ident = args.identifiant.strip().lower()
    users = load_users()
    if ident not in users:
        sys.exit(f"Compte {ident} introuvable.")
    users[ident]["role"] = args.role
    save_users(users)
    print(f"✓ {ident} a maintenant le rôle « {args.role} ».")


def cmd_reinitialiser(args) -> None:
    ident = args.identifiant.strip().lower()
    users = load_users()
    if ident not in users:
        sys.exit(f"Compte {ident} introuvable.")
    password = new_password(args)
    users[ident]["hash"] = hash_password(password)
    save_users(users)
    deliver(ident, password, args)


def cmd_supprimer(args) -> None:
    ident = args.identifiant.strip().lower()
    users = load_users()
    if ident not in users:
        sys.exit(f"Compte {ident} introuvable.")
    del users[ident]
    save_users(users)
    print(f"✓ Compte {ident} supprimé.")


def main() -> None:
    p = argparse.ArgumentParser(description="Gestion des comptes de l'app SCOT")
    sub = p.add_subparsers(dest="action", required=True)

    sub.add_parser("lister", help="liste les comptes").set_defaults(func=cmd_lister)

    a = sub.add_parser("ajouter", help="crée un compte")
    a.add_argument("identifiant", help="ex. prenom.nom")
    a.add_argument("--nom", required=True, help='nom affiché, ex. "Marie Dupont"')
    a.add_argument("--admin", action="store_true", help="donne accès à la page Administration")
    a.set_defaults(func=cmd_ajouter)

    ro = sub.add_parser("role", help="change le rôle d'un compte (operateur ou admin)")
    ro.add_argument("identifiant")
    ro.add_argument("role", choices=["operateur", "admin"])
    ro.set_defaults(func=cmd_role)

    r = sub.add_parser("reinitialiser", help="donne un nouveau mot de passe")
    r.add_argument("identifiant")
    r.set_defaults(func=cmd_reinitialiser)

    s = sub.add_parser("supprimer", help="supprime un compte")
    s.add_argument("identifiant")
    s.set_defaults(func=cmd_supprimer)

    for sp in (a, r):
        sp.add_argument("--choisir-mdp", action="store_true",
                        help="saisir le mot de passe au clavier au lieu d'en générer un")
        sp.add_argument("--fichier", help="ajoute identifiant + mot de passe à ce fichier au lieu de l'afficher")

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
