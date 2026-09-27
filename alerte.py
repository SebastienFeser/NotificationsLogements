#!/usr/bin/env python3
"""
Alerte logement – surveille les nouvelles annonces de location et envoie une
notification push (ntfy et/ou Telegram) dès qu'une annonce correspond aux critères.

Source : Flatfox (flatfox.ch). Ses résultats incluent aussi les annonces publiées
sur Homegate et ImmoScout24 (même groupe, SMG).

Usage :
    python alerte.py            # vérifie et notifie
    python alerte.py --test     # envoie une notification de test
    python alerte.py --dry-run  # affiche ce qui serait envoyé, sans rien envoyer ni enregistrer
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
import yaml

BASE = "https://flatfox.ch"
ICI = Path(__file__).resolve().parent
FICHIER_VUS = ICI / "vus.json"
FICHIER_CONFIG = ICI / "config.yaml"
MAX_VUS = 5000  # on garde les 5000 derniers identifiants, largement suffisant

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "alerte-logement/1.0 (usage personnel, 1 requete / 10 min)",
    "Accept": "application/json",
    "Accept-Language": "fr-CH,fr;q=0.9",
})


# ───────────────────────── configuration & état ─────────────────────────

def charger_config(chemin: Path = FICHIER_CONFIG) -> dict:
    with open(chemin, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.setdefault("loyer_max", 0)
    cfg.setdefault("pieces_min", 0)
    cfg.setdefault("surface_min", 0)
    cfg.setdefault("zones", [])
    cfg.setdefault("codes_postaux", [])
    cfg.setdefault("mots_exclus", [])
    cfg.setdefault("exclure_meubles", False)
    cfg.setdefault("exclure_temporaires", True)
    cfg.setdefault("exclure_echanges", True)
    if not cfg["zones"]:
        sys.exit("config.yaml : il faut au moins une zone.")
    return cfg


def charger_vus() -> tuple[list[int], bool]:
    """Renvoie (identifiants déjà vus, premier_lancement)."""
    if not FICHIER_VUS.exists():
        return [], True
    try:
        return json.loads(FICHIER_VUS.read_text()), False
    except (json.JSONDecodeError, OSError):
        return [], True


def enregistrer_vus(vus: list[int]) -> None:
    FICHIER_VUS.write_text(json.dumps(vus[-MAX_VUS:]))


# ───────────────────────────── Flatfox ─────────────────────────────

def get_json(url: str, params=None, essais: int = 3):
    for i in range(essais):
        try:
            r = SESSION.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            print(f"  ! HTTP {r.status_code} sur {r.url}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  ! erreur réseau : {e}", file=sys.stderr)
        time.sleep(3 * (i + 1))
    return None


def chercher_pins(zone: dict, cfg: dict) -> list[dict]:
    """Liste légère (id, prix, coordonnées) des annonces d'une zone."""
    params = {
        "south": zone["sud"], "west": zone["ouest"],
        "north": zone["nord"], "east": zone["est"],
        "offer_type": "RENT",
        "object_category": "APARTMENT",
        "max_count": 400,
    }
    if cfg["loyer_max"]:
        params["max_price"] = cfg["loyer_max"]
    if cfg["pieces_min"]:
        params["min_rooms"] = cfg["pieces_min"]
    data = get_json(f"{BASE}/api/v1/pin/", params)
    if data is None:
        raise RuntimeError(f"Flatfox ne répond pas pour la zone « {zone.get('nom', '?')} »")
    return data if isinstance(data, list) else data.get("results", [])


RETIREE = {}  # marqueur : l'annonce n'existe plus


def details(pk: int) -> dict | None:
    """L'annonce complète, RETIREE si elle n'existe plus, None si erreur réseau."""
    data = get_json(f"{BASE}/api/v1/public-listing/", {"pk": pk, "expand": "cover_image"})
    if data is None:
        return None
    for a in data.get("results", []):
        if a.get("pk") == pk:
            return a
    return RETIREE


# ───────────────────────────── filtres ─────────────────────────────

def loyer(a: dict) -> float | None:
    for champ in ("rent_gross", "price_display"):
        v = a.get(champ)
        if v:
            return float(v)
    if a.get("rent_net"):
        return float(a["rent_net"]) + float(a.get("rent_charges") or 0)
    return None


def surface(a: dict) -> float | None:
    for champ in ("surface_living", "livingspace", "surface_usable"):
        if a.get(champ):
            return float(a[champ])
    return None


def raison_exclusion(a: dict, cfg: dict) -> str | None:
    """None si l'annonce correspond, sinon la raison du rejet."""
    if a.get("offer_type") not in (None, "RENT"):
        return "pas une location"
    if a.get("object_category") not in (None, "APARTMENT", "HOUSE"):
        return f"catégorie {a.get('object_category')}"
    if a.get("status") not in (None, "act") or a.get("reserved"):
        return "plus disponible"

    prix = loyer(a)
    if cfg["loyer_max"] and prix and prix > cfg["loyer_max"]:
        return f"trop cher ({prix:.0f})"
    if cfg["loyer_max"] and prix is not None and prix < 200:
        return "prix fantaisiste / sur demande"

    pieces = a.get("number_of_rooms")
    if cfg["pieces_min"] and (pieces is None or float(pieces) < cfg["pieces_min"]):
        return f"pas assez de pièces ({pieces})"

    m2 = surface(a)
    if cfg["surface_min"] and m2 is not None and m2 < cfg["surface_min"]:
        return f"trop petit ({m2:.0f} m²)"

    if cfg["codes_postaux"] and str(a.get("zipcode")) not in {str(z) for z in cfg["codes_postaux"]}:
        return f"code postal {a.get('zipcode')}"

    if cfg["exclure_meubles"] and a.get("is_furnished"):
        return "meublé"
    if cfg["exclure_temporaires"] and a.get("is_temporary"):
        return "temporaire"
    if cfg["exclure_echanges"] and a.get("is_swap"):
        return "échange"

    texte = " ".join(str(a.get(c) or "") for c in
                     ("short_title", "description_title", "pitch_title", "description")).lower()
    for mot in cfg["mots_exclus"]:
        if mot.lower() in texte:
            return f"mot exclu « {mot} »"
    return None


# ─────────────────────────── notifications ───────────────────────────

def fmt_pieces(p) -> str:
    if p is None:
        return "? p."
    p = float(p)
    return f"{p:g} p."


def message(a: dict) -> tuple[str, str, str, str | None]:
    """(titre, corps, lien, image)"""
    prix = loyer(a)
    m2 = surface(a)
    lieu = a.get("public_address") or f"{a.get('zipcode', '')} {a.get('city', '')}".strip()
    titre = f"{fmt_pieces(a.get('number_of_rooms'))} · CHF {prix:,.0f}".replace(",", "'") if prix else \
        f"{fmt_pieces(a.get('number_of_rooms'))} · prix sur demande"
    lignes = [lieu]
    if m2:
        lignes[0] += f" · {m2:.0f} m²"
    accroche = a.get("description_title") or a.get("short_title")
    if accroche:
        lignes.append(accroche)
    if a.get("moving_date"):
        lignes.append(f"Dispo : {a['moving_date']}")
    elif a.get("moving_date_type") == "imm":
        lignes.append("Dispo : de suite")
    lien = BASE + (a.get("url") or f"/{a.get('pk')}/")
    image = None
    cover = a.get("cover_image")
    if isinstance(cover, dict):
        image = cover.get("url_thumb_m") or cover.get("url")
        if image and image.startswith("/"):
            image = BASE + image
    return titre, "\n".join(lignes), lien, image


def envoyer_ntfy(titre: str, corps: str, lien: str, image: str | None) -> bool:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    serveur = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {
        "Title": titre.encode("utf-8"),
        "Click": lien,
        "Tags": "house",
        "Priority": "high",
        "Actions": f"view, Voir l'annonce, {lien}",
    }
    if image:
        headers["Attach"] = image
    try:
        r = requests.post(f"{serveur}/{topic}", data=corps.encode("utf-8"), headers=headers, timeout=20)
        return r.ok
    except requests.RequestException as e:
        print(f"  ! ntfy : {e}", file=sys.stderr)
        return False


def envoyer_telegram(titre: str, corps: str, lien: str, image: str | None) -> bool:
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    texte = f"🏠 {titre}\n{corps}\n{lien}"
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": texte}, timeout=20)
        return r.ok
    except requests.RequestException as e:
        print(f"  ! telegram : {e}", file=sys.stderr)
        return False


def notifier(titre: str, corps: str, lien: str, image: str | None = None) -> bool:
    ok_ntfy = envoyer_ntfy(titre, corps, lien, image)
    ok_tg = envoyer_telegram(titre, corps, lien, image)
    return ok_ntfy or ok_tg


# ─────────────────────────────── main ───────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="envoie une notification de test")
    ap.add_argument("--dry-run", action="store_true", help="n'envoie rien, n'enregistre rien")
    args = ap.parse_args()

    if not args.dry_run and not (os.environ.get("NTFY_TOPIC") or os.environ.get("TELEGRAM_TOKEN")):
        print("Aucun canal configuré : définis NTFY_TOPIC (ou TELEGRAM_TOKEN + TELEGRAM_CHAT_ID).",
              file=sys.stderr)
        return 1

    if args.test:
        ok = notifier("Test alerte logement ✅", "Si tu lis ceci, les notifications marchent.",
                      "https://flatfox.ch/fr/search/")
        print("Notification envoyée." if ok else "Échec de l'envoi.")
        return 0 if ok else 1

    cfg = charger_config()
    vus, premier = charger_vus()
    deja = set(vus)

    pins: dict[int, dict] = {}
    for zone in cfg["zones"]:
        for p in chercher_pins(zone, cfg):
            if p.get("pk"):
                pins[int(p["pk"])] = p
    print(f"{len(pins)} annonces dans les zones, {len(deja)} déjà connues.")

    nouveaux = sorted(pk for pk in pins if pk not in deja)
    if premier and not args.dry_run:
        # Premier lancement : on mémorise l'existant sans spammer.
        enregistrer_vus(vus + nouveaux)
        notifier("Alerte logement activée 🏠",
                 f"{len(nouveaux)} annonces actuelles enregistrées. "
                 f"Tu seras prévenu pour chaque nouvelle.\n"
                 f"Critères : ≥ {cfg['pieces_min']} p., ≤ CHF {cfg['loyer_max']}",
                 "https://flatfox.ch/fr/search/")
        print(f"Premier lancement : {len(nouveaux)} annonces mémorisées, pas de notification.")
        return 0

    envoyees = 0
    for pk in nouveaux:
        a = details(pk)
        if a is None:
            continue  # erreur réseau : on réessaiera au prochain passage
        if a is RETIREE:
            vus.append(pk)
            continue
        raison = raison_exclusion(a, cfg)
        if raison:
            print(f"  – {pk} ignorée : {raison}")
            vus.append(pk)
            continue
        titre, corps, lien, image = message(a)
        print(f"  + {titre} | {corps.splitlines()[0]} | {lien}")
        if args.dry_run or notifier(titre, corps, lien, image):
            vus.append(pk)
            envoyees += 1
        # sinon : pas mémorisée, on réessaiera au prochain passage
        time.sleep(1)

    if not args.dry_run:
        enregistrer_vus(vus)
    print(f"{envoyees} notification(s) {'(simulées) ' if args.dry_run else ''}envoyée(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
