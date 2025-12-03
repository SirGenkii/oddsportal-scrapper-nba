# OddsPortal Multi-Sport Scraper

Scraper asynchrone basé sur Playwright pour récupérer les résultats et cotes de matchs publiés sur [OddsPortal](https://www.oddsportal.com/). Le projet est désormais pensé pour supporter plusieurs sports : la NBA (basketball) et les tournois ATP (tennis) via un simple paramètre.

## Fonctionnalités

- 📅 Parcourt automatiquement toutes les saisons disponibles pour chaque compétition.
- 📄 Récupère l'ensemble des pages de résultats (pagination incluse).
- 🧹 Nettoie les dates et scores pour des exports prêts à l'emploi.
- 🗂️ Génère une arborescence d'exports structurée par sport → tournoi → saison.
- 🔌 Architecture extensible pour ajouter facilement un nouveau sport ou tournoi.

## Installation

```bash
python -m venv .venv
source venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install --with-deps
```

Pour ubuntu erreur playwright : 
``` bash
sudo apt update

sudo apt install \
  libasound2t64 \
  libicu74 \
  libffi8 \
  libx264-164



```

```bash
echo 'deb [arch=amd64] http://archive.ubuntu.com/ubuntu jammy main universe' | sudo tee /etc/apt/sources.list.d/jammy-compat.list

sudo tee /etc/apt/preferences.d/jammy-compat <<'EOF'
Package: *
Pin: release n=jammy
Pin-Priority: 100
EOF

sudo apt update

```

```
sudo apt install libicu70 libvpx7

```

```
pip install -U playwright
playwright install --with-deps

```


## Sources de données

- **NBA** : URL déclarée directement dans `src/config.py`.
- **ATP** : liste de tournois déclarée dans `data/tennis/oddsportal_atp_results_urls.csv`. Ajoutez, modifiez ou supprimez des lignes pour contrôler les tournois scrappés.

## Utilisation

```bash
python main.py --sport nba        # Scraper la NBA (comportement par défaut)
python main.py --sport atp        # Scraper tous les tournois ATP listés dans le CSV
python main.py --sport atp --headless  # Lancer Playwright sans interface graphique
python main.py --repair --sport atp        # Relance le run précedent avec --repair pour reprendre ou on en était si crash
python main.py --sport nba --over_under    # Ajoute le scraping over/under (colonne handicap)
python main.py --sport nba --over_under --start_minimized  # Idem mais minimise la fenêtre pour ne pas prendre le focus
python main.py --sport nba --over_under --over_under_same_window  # Force l'ouverture des onglets over/under dans la même fenêtre (peut prendre le focus). Par défaut ils s'ouvrent en headless.
python repair_over_under.py --sport nba  # Répare les lignes avec handicap vide en rechargeant les URLs stockées dans le dernier run
python harvest_over_under_urls.py --sport nba  # Étape 1: collecte les URLs over/under sans ouvrir les pages détail
python enrich_over_under_odds.py --sport nba    # Étape 2: enrichit les CSV d'URLs avec la colonne handicap

```

Chaque exécution crée un sous-dossier horodaté dans `output/` contenant :

```
output/
 └── 2024-05-21_10-30-00/
     ├── nba/
     │   └── nba_2023_2024.csv
     └── atp/
         └── australian_open/
             └── 2024.csv
```

Chaque fichier CSV inclut les colonnes suivantes :

- `date`
- `home_team`
- `away_team`
- `home_score`
- `away_score`
- `home_odds`
- `away_odds`
- `handicap` (uniquement si `--over_under` est actif, JSON des pivots/odds over-under)
- `url` (uniquement si `--over_under` est actif, lien direct vers l'onglet over/under du match)

## Script de réparation over/under

- Commande: `python repair_over_under.py --sport nba`
- Comportement: cherche le dernier dossier `output/` contenant le sport, parcourt tous les CSV, et pour chaque ligne dont `handicap` est vide (`{}` ou champ vide), recharge l'URL stockée pour récupérer les odds over/under, met à jour la ligne, et enregistre un log `over_under_repair.log` dans le dossier du run.
- Options: `--run_dir <chemin>` pour cibler un dossier d'output précis (par défaut: le plus récent pour le sport donné).

## Pipeline en 2 étapes (over/under)
- Étape 1: `python harvest_over_under_urls.py --sport nba`  
  Scrape les pages de résultats, collecte les URLs over/under et enregistre un CSV par saison avec les colonnes `date,home_team,away_team,home_score,away_score,home_odds,away_odds,url,sport,tournament,season`.
- Étape 2: `python enrich_over_under_odds.py --sport nba`  
  Lit les CSV générés à l'étape 1 (dans le dernier dossier `output/<horodatage>/...`), ouvre chaque URL en headless, applique les règles de parsing over/under, ajoute la colonne `handicap`, et logge dans `over_under_enrich.log`.
- Option `--run_dir <chemin>` (étape 2) pour cibler un dossier spécifique si besoin.
- `sport`
- `tournament`
- `season`

## Ajouter un nouveau sport

1. Déclarez le sport dans `src/config.py` en lui donnant une URL unique ou un CSV de tournois.
2. Relancez `python main.py --sport <nouveau_sport>` pour vérifier.

## Notes

- Le scraper ouvre un seul onglet et réutilise la session pour limiter la charge.
- Utilisez l'option `--headless` pour exécuter le scraping sur un serveur ou dans un pipeline CI.
- Si OddsPortal change son HTML, adaptez les sélecteurs dans `src/extract.py`.

Bon scraping !
