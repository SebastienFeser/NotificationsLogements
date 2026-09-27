"""Tests hors-ligne : on simule Flatfox et ntfy."""
import json
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import alerte  # noqa: E402

CFG = {
    "loyer_max": 2500, "pieces_min": 3, "surface_min": 0,
    "zones": [{"nom": "GE", "sud": 46.13, "ouest": 5.95, "nord": 46.37, "est": 6.31}],
    "codes_postaux": [], "mots_exclus": ["colocation"],
    "exclure_meubles": False, "exclure_temporaires": True, "exclure_echanges": True,
}

ANNONCES = {
    101: {"pk": 101, "status": "act", "offer_type": "RENT", "object_category": "APARTMENT",
          "number_of_rooms": 4.0, "rent_gross": 2300, "zipcode": 1205, "city": "Genève",
          "public_address": "Rue de Carouge 10, 1205 Genève", "surface_living": 78,
          "description_title": "Bel appartement lumineux", "url": "/fr/flat/x/101/",
          "moving_date_type": "imm"},
    102: {"pk": 102, "status": "act", "offer_type": "RENT", "object_category": "APARTMENT",
          "number_of_rooms": 2.0, "rent_gross": 1500, "zipcode": 1203, "url": "/fr/flat/y/102/"},
    103: {"pk": 103, "status": "act", "offer_type": "RENT", "object_category": "APARTMENT",
          "number_of_rooms": 5.0, "rent_gross": 2400, "zipcode": 1227,
          "description": "Chambre en colocation", "url": "/fr/flat/z/103/"},
    104: {"pk": 104, "status": "act", "offer_type": "RENT", "object_category": "APARTMENT",
          "number_of_rooms": 3.5, "rent_net": 2100, "rent_charges": 250, "zipcode": 1212,
          "url": "/fr/flat/w/104/"},
}


def fake_get_json(url, params=None, essais=3):
    if url.endswith("/pin/"):
        return [{"pk": pk} for pk in ANNONCES]
    pk = params["pk"]
    return {"results": [ANNONCES[pk]] if pk in ANNONCES else []}


def run(tmp_path, vus_initiaux, argv=()):
    envoyes = []
    fichier_vus = tmp_path / "vus.json"
    if vus_initiaux is not None:
        fichier_vus.write_text(json.dumps(vus_initiaux))
    post = mock.Mock(side_effect=lambda url, **kw: (envoyes.append(kw), mock.Mock(ok=True))[1])
    with mock.patch.object(alerte, "FICHIER_VUS", fichier_vus), \
         mock.patch.object(alerte, "charger_config", return_value=CFG), \
         mock.patch.object(alerte, "get_json", side_effect=fake_get_json), \
         mock.patch.object(alerte.requests, "post", post), \
         mock.patch.object(alerte.time, "sleep"), \
         mock.patch.dict("os.environ", {"NTFY_TOPIC": "test-topic"}), \
         mock.patch.object(sys, "argv", ["alerte.py", *argv]):
        code = alerte.main()
    return code, envoyes, json.loads(fichier_vus.read_text()) if fichier_vus.exists() else None


def test_premier_lancement_ne_spamme_pas(tmp_path):
    code, envoyes, vus = run(tmp_path, None)
    assert code == 0
    assert len(envoyes) == 1 and "activée" in envoyes[0]["headers"]["Title"].decode()
    assert sorted(vus) == [101, 102, 103, 104]


def test_filtre_et_notifie_seulement_les_bonnes(tmp_path):
    code, envoyes, vus = run(tmp_path, [])
    titres = [e["headers"]["Title"].decode() for e in envoyes]
    assert titres == ["4 p. · CHF 2'300", "3.5 p. · CHF 2'350"]  # 102 trop petit, 103 colocation
    assert "Click" in envoyes[0]["headers"] and envoyes[0]["headers"]["Click"].endswith("/101/")
    assert sorted(vus) == [101, 102, 103, 104]


def test_deja_vues_pas_renotifiees(tmp_path):
    _, envoyes, _ = run(tmp_path, [101, 102, 103, 104])
    assert envoyes == []


def test_dry_run_n_ecrit_rien(tmp_path):
    code, envoyes, vus = run(tmp_path, [], argv=["--dry-run"])
    assert envoyes == [] and vus == []
