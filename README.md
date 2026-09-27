# Alerte logement Genève 🏠

Toutes les 10 minutes (de 7h à minuit), ce script regarde les nouvelles annonces
de location dans ta zone et t'envoie une notification sur ton téléphone dès
qu'un appartement correspond à tes critères. Ton ordinateur n'a pas besoin
d'être allumé : tout tourne gratuitement sur GitHub.

**Source :** Flatfox. Ses résultats incluent aussi les annonces Homegate et
ImmoScout24, donc ces trois sites sont couverts d'un coup.

---

## Mise en place (≈ 10 minutes)

### 1. Installer ntfy sur ton téléphone
- Télécharge l'app **ntfy** (gratuite, [iPhone](https://apps.apple.com/app/ntfy/id1625396347) / [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)).
- Appuie sur **+** et abonne-toi à un nom de canal **difficile à deviner**,
  par exemple `logement-geneve-8f3k2q`. N'importe qui connaissant ce nom
  peut lire tes alertes, d'où l'intérêt qu'il soit unique.

### 2. Mettre le projet sur GitHub
- Crée un compte sur [github.com](https://github.com) si besoin.
- **New repository** → nom `alerte-logement` → **Public** (les dépôts publics
  ont des minutes d'exécution illimitées ; en privé, passe la fréquence à
  toutes les 30 min pour rester dans le quota gratuit) → **Create**.
- Sur la page du dépôt : **uploading an existing file** → glisse *tout le contenu*
  du dossier (y compris le dossier `.github`) → **Commit changes**.
  Si le dossier `.github` n'est pas pris (dossier caché sur Mac : Cmd+Maj+.),
  crée le fichier à la main : **Add file → Create new file**, nom
  `.github/workflows/alerte.yml`, et colle le contenu.

### 3. Donner le nom du canal au script
- Dans le dépôt : **Settings → Secrets and variables → Actions → New repository secret**
- Nom : `NTFY_TOPIC` — Valeur : ton nom de canal (ex. `logement-geneve-8f3k2q`).

### 4. Lancer
- Onglet **Actions** → accepte l'activation des workflows si demandé
  → **Alerte logement** → **Run workflow**.
- Tu reçois « Alerte logement activée » : les annonces actuelles sont
  mémorisées, et dès maintenant, chaque **nouvelle** annonce te sera envoyée.

---

## Changer les critères

Modifie `config.yaml` directement sur GitHub (icône crayon) :
`loyer_max`, `pieces_min`, `surface_min`, les zones, les codes postaux, les
mots à exclure. C'est pris en compte au passage suivant.

Pour ajouter une zone (ex. Nyon, Terre Sainte), décommente le bloc prévu
ou ajoute un rectangle : clic droit sur Google Maps donne les coordonnées
d'un point.

## Changer la fréquence

Dans `.github/workflows/alerte.yml`, la ligne `cron` (heures en UTC) :
- `*/10 5-22 * * *` : toutes les 10 min de 7h à minuit (actuel)
- `*/15 * * * *` : toutes les 15 min, jour et nuit

GitHub peut retarder les exécutions de quelques minutes aux heures chargées.

## Telegram plutôt que ntfy ?

Crée un bot avec [@BotFather](https://t.me/BotFather), récupère ton chat id
(via [@userinfobot](https://t.me/userinfobot)), puis ajoute les secrets
`TELEGRAM_TOKEN` et `TELEGRAM_CHAT_ID`. Les deux canaux peuvent coexister.

## Tester en local (facultatif)

```bash
pip install -r requirements.txt
python alerte.py --dry-run                 # affiche ce qui serait envoyé
NTFY_TOPIC=ton-canal python alerte.py --test   # notification de test
```

## Bon à savoir
- GitHub met en pause les tâches planifiées d'un dépôt public après 60 jours
  sans activité. Si ça arrive, un clic sur **Enable workflow** dans l'onglet
  Actions suffit.
- Les sites français (Annemasse, Ferney, Saint-Julien…) ne sont pas couverts.
- Reste sur une fréquence raisonnable (10 min minimum) pour ne pas surcharger Flatfox.
