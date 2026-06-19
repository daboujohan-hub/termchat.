#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════╗
║         TERMCHAT v4.1  — SERVEUR                        ║
║         by Aboudev Labs 🇨🇮                              ║
║         Données persistantes via GitHub                  ║
╚══════════════════════════════════════════════════════════╝
"""

import socket, threading, json, os, random, hashlib
import datetime, time, base64, signal, sys
import urllib.request, urllib.error

# ══════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════
PORT         = int(os.environ.get("PORT", 9999))
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "daboujohan-hub/termchat")
GITHUB_FILE  = "data/db.json"
ADMIN_CODE   = os.environ.get("ADMIN_CODE", "aboudev2025")

DATA_DIR  = os.path.join(os.path.expanduser("~"), ".termchat_data")
DATA_FILE = os.path.join(DATA_DIR, "db.json")
FILES_DIR = os.path.join(DATA_DIR, "files")

# SHA du fichier GitHub (nécessaire pour le PUT)
github_sha = None
save_lock  = threading.Lock()

# ══════════════════════════════════════════════════════════
#  PAYS
# ══════════════════════════════════════════════════════════
PAYS = {
    "1":  ("Côte d'Ivoire", "+225"), "2":  ("Sénégal",      "+221"),
    "3":  ("Mali",          "+223"), "4":  ("Burkina Faso",  "+226"),
    "5":  ("Guinée",        "+224"), "6":  ("Togo",          "+228"),
    "7":  ("Bénin",         "+229"), "8":  ("Niger",         "+227"),
    "9":  ("Cameroun",      "+237"), "10": ("Congo",         "+242"),
    "11": ("Gabon",         "+241"), "12": ("Ghana",         "+233"),
    "13": ("Nigeria",       "+234"), "14": ("France",        "+33"),
    "15": ("Belgique",      "+32"),  "16": ("Canada",        "+1"),
    "17": ("USA",           "+1"),   "18": ("Maroc",         "+212"),
    "19": ("Algérie",       "+213"), "20": ("Tunisie",       "+216"),
}

# ══════════════════════════════════════════════════════════
#  UTILITAIRES
# ══════════════════════════════════════════════════════════
def hacher(mdp):    return hashlib.sha256(mdp.encode()).hexdigest()
def horodatage():   return datetime.datetime.now().isoformat()
def heure():        return datetime.datetime.now().strftime("%H:%M")
def fmt(o):
    if o < 1024:      return f"{o} o"
    elif o < 1024**2: return f"{o//1024} Ko"
    else:             return f"{o//1024//1024} Mo"

def chiffrer(texte, cle):
    try:
        octets = texte.encode("utf-8")
        cle_b  = (cle * ((len(octets) // len(cle)) + 1)).encode("utf-8")
        xored  = bytes(a ^ b for a, b in zip(octets, cle_b))
        return base64.b64encode(xored).decode("utf-8")
    except: return texte

def dechiffrer(texte_b64, cle):
    try:
        octets = base64.b64decode(texte_b64.encode("utf-8"))
        cle_b  = (cle * ((len(octets) // len(cle)) + 1)).encode("utf-8")
        xored  = bytes(a ^ b for a, b in zip(octets, cle_b))
        return xored.decode("utf-8")
    except: return texte_b64

# ══════════════════════════════════════════════════════════
#  GITHUB — PERSISTANCE DES DONNÉES
# ══════════════════════════════════════════════════════════
def github_requete(methode, url, body=None):
    """Fait une requête à l'API GitHub."""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github.v3+json",
        "Content-Type":  "application/json",
        "User-Agent":    "TermChat-Server"
    }
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, headers=headers, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404: return None
        raise
    except Exception as e:
        print(f"❌ GitHub API erreur : {e}")
        return None

def telecharger_depuis_github():
    """Télécharge db.json depuis GitHub au démarrage."""
    global github_sha
    if not GITHUB_TOKEN:
        print("⚠️  Pas de GITHUB_TOKEN — mode local uniquement")
        return False
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
    rep = github_requete("GET", url)
    if rep and "content" in rep:
        github_sha = rep.get("sha")
        contenu    = base64.b64decode(rep["content"]).decode("utf-8")
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            f.write(contenu)
        print(f"✅ Données chargées depuis GitHub ({len(contenu)} octets)")
        return True
    else:
        print("📁 Aucun fichier GitHub trouvé — démarrage avec base vide")
        return False

def pousser_sur_github(data):
    """Sauvegarde db.json sur GitHub après chaque changement."""
    global github_sha
    if not GITHUB_TOKEN:
        return
    try:
        contenu_b64 = base64.b64encode(
            json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        ).decode("utf-8")

        url  = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
        body = {
            "message": "TermChat: mise à jour données",
            "content": contenu_b64
        }
        if github_sha:
            body["sha"] = github_sha

        rep = github_requete("PUT", url, body)
        if rep and "content" in rep:
            github_sha = rep["content"].get("sha")
    except Exception as e:
        print(f"⚠️  Erreur sauvegarde GitHub : {e}")

# ══════════════════════════════════════════════════════════
#  BASE DE DONNÉES LOCALE
# ══════════════════════════════════════════════════════════
def db_vide():
    return {
        "users": {}, "historique": {}, "groupes": {},
        "stats": {"messages_total": 0, "fichiers_total": 0, "inscriptions_total": 0}
    }

def charger():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(FILES_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        sauver(db_vide())
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def sauver(data):
    """Sauvegarde localement ET sur GitHub."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # Sauvegarde GitHub en arrière-plan
    if GITHUB_TOKEN:
        t = threading.Thread(target=pousser_sur_github, args=(data,), daemon=True)
        t.start()

def initialiser():
    """Charge les données depuis GitHub ou crée une base vide."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(FILES_DIR, exist_ok=True)
    ok = telecharger_depuis_github()
    if not ok and not os.path.exists(DATA_FILE):
        sauver(db_vide())

def gen_numero(prefixe):
    data = charger()
    nums = {u["numero"] for u in data["users"].values()}
    while True:
        n = prefixe + str(random.randint(1000000000, 9999999999))
        if n not in nums: return n

def sauver_msg(de, vers, texte, type_msg="texte", nom_fich=None, chiffre=False):
    data = charger()
    cle  = "_".join(sorted([de, vers]))
    hist = data.get("historique", {})
    hist.setdefault(cle, [])
    msg  = {"de": de, "vers": vers, "texte": texte,
            "type": type_msg, "heure": horodatage(), "lu": False, "chiffre": chiffre}
    if nom_fich: msg["fichier"] = nom_fich
    hist[cle].append(msg)
    hist[cle] = hist[cle][-500:]
    data["historique"] = hist
    data.setdefault("stats", {})
    data["stats"]["messages_total"] = data["stats"].get("messages_total", 0) + 1
    sauver(data)

def get_hist(n1, n2, limite=50):
    data = charger()
    cle  = "_".join(sorted([n1, n2]))
    return data.get("historique", {}).get(cle, [])[-limite:]

def marquer_lus(destinataire, expediteur):
    data = charger()
    cle  = "_".join(sorted([destinataire, expediteur]))
    hist = data.get("historique", {}).get(cle, [])
    for msg in hist:
        if msg.get("vers") == destinataire and not msg.get("lu"):
            msg["lu"] = True
    data["historique"][cle] = hist
    sauver(data)

def compter_non_lus(numero):
    data  = charger()
    total = 0
    for msgs in data.get("historique", {}).values():
        for msg in msgs:
            if msg.get("vers") == numero and not msg.get("lu"):
                total += 1
    return total

# ══════════════════════════════════════════════════════════
#  CLIENTS CONNECTÉS
# ══════════════════════════════════════════════════════════
clients      = {}
clients_info = {}
lock         = threading.Lock()
TIMEOUT      = 1800  # 30 min

def envoyer_srv(sock, paquet):
    try: sock.sendall((json.dumps(paquet, ensure_ascii=False) + "\n").encode())
    except: pass

def livrer(numero, paquet):
    with lock: s = clients.get(numero)
    if s: envoyer_srv(s, paquet); return True
    return False

def maj_activite(numero):
    with lock:
        if numero in clients_info:
            clients_info[numero]["derniere_activite"] = time.time()

# ══════════════════════════════════════════════════════════
#  GESTION CLIENT
# ══════════════════════════════════════════════════════════
def gerer_client(conn, addr):
    num_co    = None
    buf       = ""
    est_admin = False

    try:
        while True:
            conn.settimeout(TIMEOUT)
            try:
                chunk = conn.recv(8192).decode("utf-8", errors="replace")
            except socket.timeout:
                if num_co:
                    envoyer_srv(conn, {"type": "timeout", "msg": "Déconnecté pour inactivité."})
                break
            if not chunk: break
            buf += chunk

            while "\n" in buf:
                ligne, buf = buf.split("\n", 1)
                ligne = ligne.strip()
                if not ligne: continue
                try:    p = json.loads(ligne)
                except: continue

                act = p.get("action", "")
                if num_co: maj_activite(num_co)

                # ── INSCRIPTION ───────────────────────────
                if act == "inscrire":
                    nom     = p.get("nom", "").strip()
                    mdp     = p.get("mdp", "").strip()
                    prefixe = p.get("prefixe", "+225").strip()
                    couleur = p.get("couleur", "cyan")

                    if not nom or not mdp:
                        envoyer_srv(conn, {"ok": False, "msg": "Nom et mot de passe requis."}); continue
                    if len(nom) < 2 or len(nom) > 20:
                        envoyer_srv(conn, {"ok": False, "msg": "Nom : 2 à 20 caractères."}); continue
                    if len(mdp) < 4:
                        envoyer_srv(conn, {"ok": False, "msg": "Minimum 4 caractères."}); continue

                    data = charger()
                    for u in data["users"].values():
                        if u["nom"].lower() == nom.lower():
                            envoyer_srv(conn, {"ok": False, "msg": f"Nom '{nom}' déjà utilisé."}); break
                    else:
                        numero = gen_numero(prefixe)
                        pays   = next((v[0] for v in PAYS.values() if v[1] == prefixe), "Inconnu")
                        data["users"][nom.lower()] = {
                            "nom": nom, "numero": numero, "mdp": hacher(mdp),
                            "pays": pays, "prefixe": prefixe, "bio": "",
                            "couleur": couleur, "inscription": horodatage(),
                            "est_admin": False, "bloque": []
                        }
                        data["stats"]["inscriptions_total"] = data["stats"].get("inscriptions_total", 0) + 1
                        sauver(data)
                        envoyer_srv(conn, {"ok": True, "numero": numero, "nom": nom, "pays": pays})

                # ── CONNEXION ─────────────────────────────
                elif act == "connecter":
                    nom  = p.get("nom", "").strip().lower()
                    mdp  = p.get("mdp", "").strip()
                    data = charger()
                    user = data["users"].get(nom)

                    if not user:
                        envoyer_srv(conn, {"ok": False, "msg": "Compte introuvable."})
                    elif user["mdp"] != hacher(mdp):
                        envoyer_srv(conn, {"ok": False, "msg": "Mot de passe incorrect."})
                    else:
                        num_co    = user["numero"]
                        est_admin = user.get("est_admin", False)
                        with lock:
                            clients[num_co] = conn
                            clients_info[num_co] = {"nom": user["nom"], "derniere_activite": time.time()}
                        non_lus = compter_non_lus(num_co)
                        envoyer_srv(conn, {
                            "ok": True, "nom": user["nom"], "numero": num_co,
                            "pays": user.get("pays", ""), "bio": user.get("bio", ""),
                            "couleur": user.get("couleur", "cyan"),
                            "est_admin": est_admin, "non_lus": non_lus
                        })
                        _notifier_statut(num_co, True, data)

                # ── TYPING ────────────────────────────────
                elif act == "typing":
                    if not num_co: continue
                    dest = p.get("dest", "").strip()
                    data = charger()
                    exp  = next((u for u in data["users"].values() if u["numero"] == num_co), None)
                    if exp:
                        livrer(dest, {"type": "typing", "de": exp["nom"],
                                      "numero": num_co, "actif": p.get("actif", True)})

                # ── DÉCONNECTER ───────────────────────────
                elif act == "deconnecter": break

                # ── CHERCHER ──────────────────────────────
                elif act == "chercher":
                    numero = p.get("numero", "").strip()
                    data   = charger()
                    trouve = next((u for u in data["users"].values() if u["numero"] == numero), None)
                    if trouve:
                        envoyer_srv(conn, {"ok": True, "user": {
                            "nom": trouve["nom"], "numero": trouve["numero"],
                            "pays": trouve.get("pays", ""), "bio": trouve.get("bio", ""),
                            "en_ligne": numero in clients
                        }})
                    else:
                        envoyer_srv(conn, {"ok": False, "msg": "Utilisateur introuvable."})

                # ── MESSAGE ───────────────────────────────
                elif act == "message":
                    if not num_co: continue
                    dest       = p.get("dest", "").strip()
                    texte      = p.get("texte", "").strip()
                    est_chiffre = p.get("chiffre", False)
                    if not texte or not dest: continue
                    data = charger()
                    exp  = next((u for u in data["users"].values() if u["numero"] == num_co), None)
                    if not any(u["numero"] == dest for u in data["users"].values()):
                        envoyer_srv(conn, {"ok": False, "msg": "Destinataire introuvable."}); continue
                    sauver_msg(num_co, dest, texte, chiffre=est_chiffre)
                    livre = livrer(dest, {
                        "type": "message", "de": exp["nom"],
                        "numero": num_co, "texte": texte,
                        "heure": heure(), "chiffre": est_chiffre
                    })
                    envoyer_srv(conn, {"ok": True, "livre": livre})
                    if livre:
                        livrer(num_co, {"type": "livre", "dest": dest})

                # ── MARQUER LU ────────────────────────────
                elif act == "marquer_lu":
                    if not num_co: continue
                    avec = p.get("avec", "").strip()
                    marquer_lus(num_co, avec)
                    livrer(avec, {"type": "lu", "par": num_co})

                # ── FICHIER ───────────────────────────────
                elif act == "envoyer_fichier":
                    if not num_co: continue
                    dest     = p.get("dest", "").strip()
                    nom_fich = p.get("nom_fichier", "fichier")
                    c64      = p.get("contenu", "")
                    taille   = p.get("taille", 0)
                    if taille > 10*1024*1024:
                        envoyer_srv(conn, {"ok": False, "msg": "Max 10 MB."}); continue
                    data = charger()
                    exp  = next((u for u in data["users"].values() if u["numero"] == num_co), None)
                    if not any(u["numero"] == dest for u in data["users"].values()):
                        envoyer_srv(conn, {"ok": False, "msg": "Introuvable."}); continue
                    safe   = "".join(c for c in nom_fich if c.isalnum() or c in "._-")
                    chemin = os.path.join(FILES_DIR, f"{int(time.time())}_{safe}")
                    try:
                        with open(chemin, "wb") as f: f.write(base64.b64decode(c64))
                    except Exception as e:
                        envoyer_srv(conn, {"ok": False, "msg": str(e)}); continue
                    sauver_msg(num_co, dest, f"[Fichier] {nom_fich}", "fichier", nom_fich)
                    data2 = charger()
                    data2["stats"]["fichiers_total"] = data2["stats"].get("fichiers_total", 0) + 1
                    sauver(data2)
                    livre = livrer(dest, {
                        "type": "fichier", "de": exp["nom"], "numero": num_co,
                        "nom_fichier": nom_fich, "contenu": c64, "taille": taille, "heure": heure()
                    })
                    envoyer_srv(conn, {"ok": True, "livre": livre, "msg": f"'{nom_fich}' envoyé."})

                # ── EFFACER HISTORIQUE ─────────────────────
                elif act == "effacer_historique":
                    if not num_co: continue
                    avec = p.get("avec", "").strip()
                    data = charger()
                    cle  = "_".join(sorted([num_co, avec]))
                    if cle in data.get("historique", {}):
                        data["historique"][cle] = []
                        sauver(data)
                    envoyer_srv(conn, {"ok": True, "msg": "Historique effacé."})

                # ── BLOQUER ───────────────────────────────
                elif act == "bloquer":
                    if not num_co: continue
                    cible  = p.get("numero", "").strip()
                    action = p.get("bloquer", True)
                    data   = charger()
                    for cle, u in data["users"].items():
                        if u["numero"] == num_co:
                            bloque = u.get("bloque", [])
                            if action and cible not in bloque: bloque.append(cible)
                            elif not action and cible in bloque: bloque.remove(cible)
                            data["users"][cle]["bloque"] = bloque
                            sauver(data)
                            envoyer_srv(conn, {"ok": True, "msg": "Bloqué." if action else "Débloqué."}); break

                # ── COULEUR ───────────────────────────────
                elif act == "changer_couleur":
                    if not num_co: continue
                    couleur = p.get("couleur", "cyan")
                    data    = charger()
                    for cle, u in data["users"].items():
                        if u["numero"] == num_co:
                            data["users"][cle]["couleur"] = couleur
                            sauver(data)
                            envoyer_srv(conn, {"ok": True, "msg": "Couleur changée !", "couleur": couleur}); break

                # ── HISTORIQUE ────────────────────────────
                elif act == "historique":
                    if not num_co: continue
                    avec = p.get("avec", "").strip()
                    hist = get_hist(num_co, avec, p.get("limite", 50))
                    data = charger()
                    noms = {u["numero"]: u["nom"] for u in data["users"].values()}
                    for m in hist: m["nom_de"] = noms.get(m["de"], m["de"])
                    marquer_lus(num_co, avec)
                    livrer(avec, {"type": "lu", "par": num_co})
                    envoyer_srv(conn, {"ok": True, "historique": hist})

                # ── BIO ───────────────────────────────────
                elif act == "modifier_bio":
                    if not num_co: continue
                    bio  = p.get("bio", "").strip()[:150]
                    data = charger()
                    for cle, u in data["users"].items():
                        if u["numero"] == num_co:
                            data["users"][cle]["bio"] = bio
                            sauver(data)
                            envoyer_srv(conn, {"ok": True, "msg": "Bio mise à jour !"}); break

                # ── MOT DE PASSE ──────────────────────────
                elif act == "changer_mdp":
                    if not num_co: continue
                    ancien  = p.get("ancien", "").strip()
                    nouveau = p.get("nouveau", "").strip()
                    if len(nouveau) < 4: envoyer_srv(conn, {"ok": False, "msg": "Min 4 caractères."}); continue
                    data = charger()
                    for cle, u in data["users"].items():
                        if u["numero"] == num_co:
                            if u["mdp"] != hacher(ancien):
                                envoyer_srv(conn, {"ok": False, "msg": "Ancien mdp incorrect."}); break
                            data["users"][cle]["mdp"] = hacher(nouveau)
                            sauver(data)
                            envoyer_srv(conn, {"ok": True, "msg": "Mot de passe changé !"}); break

                # ── SUPPRIMER ─────────────────────────────
                elif act == "supprimer_compte":
                    if not num_co: continue
                    mdp  = p.get("mdp", "").strip()
                    data = charger()
                    for cle, u in data["users"].items():
                        if u["numero"] == num_co:
                            if u["mdp"] != hacher(mdp):
                                envoyer_srv(conn, {"ok": False, "msg": "Mdp incorrect."}); break
                            del data["users"][cle]
                            sauver(data)
                            envoyer_srv(conn, {"ok": True, "msg": "Compte supprimé."})
                            num_co = None; break

                # ── GROUPES ───────────────────────────────
                elif act == "creer_groupe":
                    if not num_co: continue
                    nom_g = p.get("nom", "").strip()
                    if not nom_g: continue
                    data  = charger()
                    id_g  = f"grp_{int(time.time())}_{random.randint(1000,9999)}"
                    data.setdefault("groupes", {})[id_g] = {
                        "nom": nom_g, "createur": num_co,
                        "membres": [num_co], "creation": horodatage(), "historique": []
                    }
                    sauver(data)
                    envoyer_srv(conn, {"ok": True, "id_groupe": id_g, "nom": nom_g})

                elif act == "ajouter_groupe":
                    if not num_co: continue
                    id_g   = p.get("id_groupe", "").strip()
                    cible  = p.get("numero", "").strip()
                    data   = charger()
                    groupe = data.get("groupes", {}).get(id_g)
                    if not groupe: envoyer_srv(conn, {"ok": False, "msg": "Groupe introuvable."}); continue
                    if groupe["createur"] != num_co: envoyer_srv(conn, {"ok": False, "msg": "Accès refusé."}); continue
                    if not any(u["numero"] == cible for u in data["users"].values()):
                        envoyer_srv(conn, {"ok": False, "msg": "Utilisateur introuvable."}); continue
                    if cible in groupe["membres"]: envoyer_srv(conn, {"ok": False, "msg": "Déjà membre."}); continue
                    data["groupes"][id_g]["membres"].append(cible)
                    sauver(data)
                    livrer(cible, {"type": "invitation_groupe", "groupe": groupe["nom"],
                                   "id_groupe": id_g, "heure": heure()})
                    envoyer_srv(conn, {"ok": True, "msg": f"Membre ajouté !"})

                elif act == "msg_groupe":
                    if not num_co: continue
                    id_g   = p.get("id_groupe", "").strip()
                    texte  = p.get("texte", "").strip()
                    data   = charger()
                    groupe = data.get("groupes", {}).get(id_g)
                    if not groupe or num_co not in groupe.get("membres", []): continue
                    exp = next((u for u in data["users"].values() if u["numero"] == num_co), None)
                    for membre in groupe["membres"]:
                        if membre != num_co:
                            livrer(membre, {
                                "type": "msg_groupe", "groupe": groupe["nom"],
                                "id_groupe": id_g, "de": exp["nom"],
                                "numero": num_co, "texte": texte, "heure": heure()
                            })
                    data["groupes"][id_g].setdefault("historique", []).append({
                        "de": num_co, "nom": exp["nom"], "texte": texte, "heure": horodatage()
                    })
                    data["groupes"][id_g]["historique"] = data["groupes"][id_g]["historique"][-500:]
                    sauver(data)
                    envoyer_srv(conn, {"ok": True})

                elif act == "mes_groupes":
                    if not num_co: continue
                    data    = charger()
                    groupes = [{"id": gid, "nom": g["nom"], "membres": len(g["membres"]),
                                "createur": g["createur"] == num_co}
                               for gid, g in data.get("groupes", {}).items()
                               if num_co in g.get("membres", [])]
                    envoyer_srv(conn, {"ok": True, "groupes": groupes})

                # ── EN LIGNE ──────────────────────────────
                elif act == "en_ligne":
                    with lock: liste = list(clients.keys())
                    data = charger()
                    noms = {u["numero"]: u["nom"] for u in data["users"].values()}
                    envoyer_srv(conn, {"ok": True, "users": [
                        {"numero": n, "nom": noms.get(n, "?")} for n in liste if n != num_co
                    ]})

                # ── ADMIN ─────────────────────────────────
                elif act == "admin_login":
                    if p.get("code", "") == ADMIN_CODE:
                        est_admin = True
                        envoyer_srv(conn, {"ok": True, "msg": "✅ Accès admin accordé."})
                    else:
                        envoyer_srv(conn, {"ok": False, "msg": "Code incorrect."})

                elif act == "admin_stats":
                    if not est_admin: envoyer_srv(conn, {"ok": False, "msg": "Accès refusé."}); continue
                    data = charger()
                    with lock: en_ligne = len(clients)
                    stats = data.get("stats", {})
                    envoyer_srv(conn, {"ok": True, "stats": {
                        "utilisateurs":       len(data["users"]),
                        "en_ligne":           en_ligne,
                        "messages_total":     stats.get("messages_total", 0),
                        "fichiers_total":     stats.get("fichiers_total", 0),
                        "inscriptions_total": stats.get("inscriptions_total", 0),
                        "groupes":            len(data.get("groupes", {})),
                        "conversations":      len(data.get("historique", {}))
                    }})

                elif act == "admin_broadcast":
                    if not est_admin: envoyer_srv(conn, {"ok": False, "msg": "Accès refusé."}); continue
                    msg = p.get("msg", "").strip()
                    with lock: tous = list(clients.values())
                    for s in tous:
                        envoyer_srv(s, {"type": "annonce", "msg": msg, "heure": heure()})
                    envoyer_srv(conn, {"ok": True, "msg": f"Envoyé à {len(tous)} utilisateurs."})

                elif act == "admin_users":
                    if not est_admin: envoyer_srv(conn, {"ok": False, "msg": "Accès refusé."}); continue
                    data = charger()
                    with lock: en_ligne_set = set(clients.keys())
                    users = [{"nom": u["nom"], "numero": u["numero"], "pays": u.get("pays", ""),
                              "inscription": u.get("inscription", "")[:10],
                              "en_ligne": u["numero"] in en_ligne_set}
                             for u in data["users"].values()]
                    envoyer_srv(conn, {"ok": True, "users": users})

                elif act == "admin_kick":
                    if not est_admin: envoyer_srv(conn, {"ok": False, "msg": "Accès refusé."}); continue
                    cible = p.get("numero", "").strip()
                    with lock: s = clients.get(cible)
                    if s:
                        envoyer_srv(s, {"type": "kick", "msg": "Déconnecté par l'admin."})
                        try: s.close()
                        except: pass
                        envoyer_srv(conn, {"ok": True, "msg": "Utilisateur déconnecté."})
                    else:
                        envoyer_srv(conn, {"ok": False, "msg": "Hors ligne."})

    except Exception as e:
        pass
    finally:
        if num_co:
            with lock:
                clients.pop(num_co, None)
                clients_info.pop(num_co, None)
            try:
                data = charger()
                _notifier_statut(num_co, False, data)
            except: pass
        try: conn.close()
        except: pass

def _notifier_statut(numero, en_ligne, data):
    user = next((u for u in data["users"].values() if u["numero"] == numero), None)
    if not user: return
    with lock:
        for num, sock in list(clients.items()):
            if num != numero:
                envoyer_srv(sock, {"type": "statut", "numero": numero,
                                   "nom": user["nom"], "en_ligne": en_ligne})

# ══════════════════════════════════════════════════════════
#  DÉMARRAGE
# ══════════════════════════════════════════════════════════
def main():
    print("╔══════════════════════════════════════════╗")
    print("║  💬  TERMCHAT v4.1 — SERVEUR             ║")
    print("║  by Aboudev Labs 🇨🇮                     ║")
    print("╚══════════════════════════════════════════╝")

    # Charger les données depuis GitHub
    initialiser()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(200)
    print(f"✅ Serveur actif sur le port {PORT}")
    print(f"📦 GitHub : {GITHUB_REPO}/{GITHUB_FILE}")

    def quitter(sig, frame):
        print("\n🔌 Arrêt..."); srv.close(); sys.exit(0)
    signal.signal(signal.SIGINT, quitter)
    signal.signal(signal.SIGTERM, quitter)

    while True:
        try:
            conn, addr = srv.accept()
            threading.Thread(target=gerer_client, args=(conn, addr), daemon=True).start()
        except: break

if __name__ == "__main__":
    main()
