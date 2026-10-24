# ohm-energie-scrapper

Outil en ligne de commande pour récupérer **vos propres données** depuis l'espace client
Ohm Énergie : factures, soldes, contrats, consommation, production solaire, conseils.

Le projet se connecte avec votre compte (identifiant et mot de passe dans un fichier `.env`
local), appelle uniquement des endpoints de **lecture**, et écrit les réponses en JSON ou CSV.
Il n'existe aucune API publique : ce projet s'appuie sur l'API interne du site
`espace-client.ohm-energie.com`, reconstituée dans `docs/api_map.md`.

## Avertissement

- **API non officielle et non documentée.** Elle peut changer, limiter les appels ou cesser de
  fonctionner sans préavis. Aucune garantie de stabilité n'est fournie.
- **Usage personnel uniquement**, avec votre compte et vos données. Vérifiez les conditions
  d'utilisation d'Ohm Énergie avant toute utilisation.
- **Restez sobre** : quelques requêtes par jour suffisent. Pas d'automatisation agressive,
  pas de partage des données récupérées, pas de contournement des limitations.
- Le dossier `data/` contient des données personnelles (identité, adresse, PDL, factures).
  Il est exclu de Git ; ne le publiez jamais. Ne partagez pas non plus de fichier `.har`
  (il contient jetons et mots de passe).

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Alternative, avec le paquet installable (commande `ohm-scraper` en plus de `python -m`) :

```bash
pip install -e ".[dev]"
```

Prérequis : Python 3.10 ou plus récent.

## Configuration

Renseignez `.env` (jamais versionné) :

| Variable | Rôle |
|---|---|
| `OHM_LOGIN` | Adresse e-mail **ou** référence client (`CM-...`) |
| `OHM_PASSWORD` | Mot de passe de l'espace client |
| `OHM_CUSTOMER_NUMBER` | Facultatif : déduit de la réponse de connexion |
| `OHM_CT` | Facultatif : contrat sélectionné, déduit de la réponse de connexion |

**Guillemets et signe `$`.** `python-dotenv` interprète les guillemets et les variables :

- Un mot de passe contenant un guillemet double doit être entouré de guillemets doubles,
  avec le guillemet échappé : `OHM_PASSWORD="abc\"def"`.
- Le signe `$` déclenche une interpolation (`${VAR}` ou `$VAR`). Évitez-le, échappez-le
  (`OHM_PASSWORD="abc\$def"`) ou utilisez des guillemets simples, qui désactivent
  l'interpolation : `OHM_PASSWORD='abc$def'`.
- Pas d'espace avant ou après le `=`.

## Utilisation

Toutes les commandes s'exécutent depuis la racine du dépôt :

```bash
python -m ohm_scraper <commande> [options]
```

### `dump` — réponses JSON de tous les endpoints de lecture

```bash
# Tous les endpoints GET allowlistés
python -m ohm_scraper dump

# Seulement quelques endpoints
python -m ohm_scraper dump --only invoices,balance_total,consumption_six_months

# Lister les noms disponibles, sans réseau ni lecture de .env
python -m ohm_scraper dump --list

# Choisir le dossier de sortie
python -m ohm_scraper dump --output-dir data/2026-10-24
```

Chaque réponse est écrite dans `data/<horodatage>/<nom>.json` (JSON indenté), par exemple
`data/20261024_183000/invoices.json`. Une seule connexion est faite pour tout le lot.

### `consumption` — série de consommation

```bash
# Courbe horaire de la veille (une requête par jour, plafond 31 jours)
python -m ohm_scraper consumption --granularity hourly --from 22/10/2026 --to 23/10/2026

# Export CSV d'une journée horaire
python -m ohm_scraper consumption --granularity hourly \
  --from 23/10/2026 --to 23/10/2026 --format csv --output conso_horaire.csv

# Totaux journaliers en kWh sur 7 jours (une requête par jour, plafond 31 jours)
python -m ohm_scraper consumption --granularity daily \
  --from 17/10/2026 --to 23/10/2026 --format csv --output conso_jour.csv

# Puissance maximale (kVA) par jour ou par mois : une requête sur la plage
python -m ohm_scraper consumption --granularity power-days --from 2026-10-01 --to 2026-10-23
python -m ohm_scraper consumption --granularity power-months --from 01/11/2025 --to 23/10/2026
```

- Dates acceptées : `jj/mm/aaaa` ou `aaaa-mm-jj`.
- Valeurs par défaut : fin = hier ; début = hier (`hourly`), 7 jours (`daily`),
  31 jours (`power-days`), 12 mois (`power-months`).
- La courbe de charge est en **Wh par demi-heure** (48 points par jour). `hourly` donne chaque
  point (colonnes `wh` et `kwh`) ; `daily` additionne les 48 points en un total par jour
  (`kwh`, `wh`, `points`, `complete`). `complete` vaut `false` si un jour n'a pas ses 48 points.
- `power-days` et `power-months` renvoient la puissance maximale (kVA), pas l'énergie.
  Pour des kWh mensuels, utilisez `dump --only consumption_six_months`.
- Les séries `hourly` et `daily` nécessitent le PDL, lu dans `body.others.pdl` de
  `consumption/kwh/{ct}/data`, comme le fait le site.
- Sortie JSON (défaut) : `granularity`, `from`, `to`, `rows` (lignes mises à plat) et
  `responses` (réponses d'origine). Sortie CSV : uniquement les lignes.
- Sans `--output`, le résultat est écrit sur la sortie standard.
- Le corps des endpoints de puissance (`startDate`/`endDate` en `jj/mm/aaaa`) est déduit de
  `docs/api_map.md`, qui ne documente pas ses paramètres : il peut nécessiter un ajustement
  si l'API évolue. La courbe horaire (`{date, pdl}`) est, elle, vérifiée.

### `discover` — inventaire de la forme des réponses

```bash
python -m ohm_scraper discover
```

Régénère `docs/inventory.md` : uniquement la **forme** des réponses (types, clés, plages de
dates, min/max de kWh), jamais les valeurs personnelles. Un contrôle de fuite bloque
l'écriture si une valeur identifiante apparaît dans le rapport.

L'ancien script `discover.py` reste utilisable directement.

## Données récupérables

D'après `docs/inventory.md` (38 endpoints de lecture vérifiés en HTTP 200, dont 37 GET
couverts par `dump` et la courbe horaire couverte par `consumption`) :

- **Compte** : tableau de bord, fiche compte du contrat, liste des contrats, préférences,
  adresses, fiche info conseil, assurance CPV, indicateur Ecojoko.
- **Référentiel** : motifs de demande (référentiel public).
- **Facturation** : factures du contrat, factures et paiements, paiements, toutes les
  factures, tous les paiements, solde du contrat, solde total, détail des soldes, graphe
  d'échéancier, contrôles énergie, activation du suivi.
- **Documents** : métadonnées CPV, CGV et liste des grilles tarifaires. Les PDF ne sont pas
  téléchargés.
- **Assurance Neat** : échéancier et CPV.
- **Conseils** : conseils personnalisés, DPE, questionnaire et avancement.
- **Consommation** : 6 derniers mois, dernier mois, résumé du mois précédent, kWh et euros
  agrégés, comparaison avec des logements similaires, seuils, usages, courbe horaire.
- **Production** : production solaire sur 6 mois.

Les endpoints de mutation (PATCH, DELETE, POST qui modifient des données, parrainage,
commande Ecojoko, résiliation, etc.) sont volontairement exclus. La liste et les raisons
figurent dans `ohm_scraper/endpoints.py` (`EXCLUDED_ENDPOINTS`).

## Fraîcheur des données

Les données de consommation proviennent d'Enedis et arrivent avec un **délai de 24 à 48 h**.
La veille est donc la dernière journée généralement disponible ; une journée récente peut
être vide ou partielle. Les mois en cours peuvent être incomplets.

## Structure du projet

```
.
├── ohm_scraper/
│   ├── __main__.py      # python -m ohm_scraper
│   ├── cli.py           # argparse, dump, consumption, discover
│   ├── client.py        # session HTTP, connexion, jeton, délais
│   ├── config.py        # lecture de .env
│   ├── consumption.py   # dates, plafond, mise à plat, CSV
│   └── endpoints.py     # catalogue, templating, exclusions
├── discover.py          # inventaire (forme des réponses)
├── docs/
│   ├── api_map.md       # cartographie de l'API
│   └── inventory.md     # inventaire généré
├── tests/               # pytest hors ligne (HTTP simulé)
├── data/                # sorties JSON/CSV (ignoré par Git)
├── .env.example
├── pyproject.toml
└── CHANGELOG.md
```

## Ajouter un endpoint

1. Vérifiez dans `docs/api_map.md` que l'endpoint est bien en lecture seule.
2. Ajoutez un `Endpoint` dans `DUMP_ENDPOINTS` (`ohm_scraper/endpoints.py`) avec :
   un nom court stable (`snake_case`), la méthode, le chemin avec `{number}`/`{ct}`,
   la catégorie et une description.
3. S'il s'agit d'un POST de lecture (comme la courbe horaire), ajoutez-le à
   `CONSUMPTION_ENDPOINTS` avec la description de son corps.
4. Si l'endpoint modifie des données, ne l'ajoutez pas : documentez-le dans
   `EXCLUDED_ENDPOINTS` avec la raison.
5. Lancez les tests : `python -m pytest`.

## Dépannage

| Symptôme | Cause probable |
|---|---|
| `Connexion refusée (HTTP 401)` avec « check your credentials » | Identifiant ou mot de passe incorrect, ou **guillemets/`$` mal échappés dans `.env`**. Vérifiez la section Configuration. |
| `Variable d'environnement manquante : OHM_LOGIN` | `.env` absent ou mal nommé ; la commande doit être lancée depuis la racine du projet. |
| `Connexion impossible` | Réseau, proxy ou site indisponible. Réessayez plus tard, sans boucle automatique. |
| `PDL introuvable` | Le compte n'expose pas `body.others.pdl` (compteur non Linky ou consentement absent). La courbe horaire est indisponible. |
| `plage horaire de N jours : plafond dur de 31 jours` | Réduisez la plage : une requête est faite par jour. |
| Réponse vide sur une date récente | Délai Enedis de 24 à 48 h ; utilisez une date plus ancienne. |
| `HTTP 429` | Trop de requêtes : attendez et réduisez le volume. |

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Les tests sont hors ligne : la session HTTP est simulée et aucune vraie donnée
d'identification n'est utilisée.
