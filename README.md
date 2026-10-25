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

| Variable | Rôle | Défaut |
|---|---|---|
| `OHM_LOGIN` | Adresse e-mail **ou** référence client (`CM-...`) | *(obligatoire)* |
| `OHM_PASSWORD` | Mot de passe de l'espace client | *(obligatoire)* |
| `OHM_CUSTOMER_NUMBER` | Facultatif : déduit de la réponse de connexion | *(auto)* |
| `OHM_CT` | Facultatif : contrat sélectionné, déduit de la réponse de connexion | *(auto)* |
| `SERVICE_HOST` | Adresse d'écoute du serveur HTTP (0.0.0.0 dans Docker) | `127.0.0.1` |
| `SERVICE_PORT` | Port d'écoute du service HTTP | `8080` |
| `OHM_PUBLISH_ADDRESS` | Interface hôte sur laquelle Docker Compose publie le port | `127.0.0.1` |
| `OHM_API_TOKEN` | Jeton Bearer secret pour protéger l'accès HTTP | *(aucun)* |
| `OHM_CACHE_TTL` | Durée de vie du cache mémoire en secondes | `900` (15 min) |

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

### `serve` — service HTTP REST local

```bash
# Lancement local avec la configuration de .env
python -m ohm_scraper serve

# Spécifier l'hôte ou le port
python -m ohm_scraper serve --host 127.0.0.1 --port 8080
```

Le service expose les données de l'espace client en **lecture seule** : seules les requêtes `GET` sont
exposées. Le contrat complet est dans [`docs/openapi.yaml`](docs/openapi.yaml) (OpenAPI 3.1). Il fait
référence pour les paramètres, les réponses et les erreurs.

Toutes les routes sont sous `/v1`, sauf `GET /health`. Les routes `legacy` sont conservées à
l'identique. Elles sont dépréciées et remplacées par les routes `/v1`.

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/health` | Vérifier que le service répond (sans authentification) |
| `GET` | `/v1/status` | Lire l'état du service et de la connexion amont |
| `GET` | `/v1/meters` | Lister les compteurs |
| `GET` | `/v1/meters/{meterId}` | Lire un compteur |
| `GET` | `/v1/meters/{meterId}/readings` | Lister les relevés demi-heure |
| `GET` | `/v1/meters/{meterId}/consumption` | Lire la consommation agrégée (`granularity` : hour, day, week, month) |
| `GET` | `/v1/meters/{meterId}/consumption/summary` | Résumer la consommation d'une période prédéfinie |
| `GET` | `/v1/meters/{meterId}/consumption/comparison` | Comparer la consommation à la période précédente |
| `GET` | `/v1/meters/{meterId}/consumption/profile` | Calculer le profil moyen (`by` : hour-of-day, day-of-week) |
| `GET` | `/v1/meters/{meterId}/consumption/baseline` | Estimer la consommation de veille |
| `GET` | `/v1/meters/{meterId}/consumption/anomalies` | Détecter les jours anormaux |
| `GET` | `/v1/meters/{meterId}/consumption/breakdown` | Lire la répartition estimée par usage |
| `GET` | `/v1/contracts` | Lister les contrats |
| `GET` | `/v1/contracts/{contractId}/invoices` | Lister les factures d'un contrat |
| `GET` | `/v1/contracts/{contractId}/invoices/{invoiceId}` | Lire une facture |
| `GET` | `/v1/contracts/{contractId}/balance` | Lire le solde du contrat |
| `GET` | `/v1/contracts/{contractId}/tariffs` | Lister les métadonnées des grilles tarifaires (sans prix) |
| `GET` | `/endpoints` | *Legacy, déprécié* : catalogue des endpoints |
| `GET` | `/data` | *Legacy, déprécié* : liste des endpoints de données |
| `GET` | `/data/{name}` | *Legacy, déprécié* : données brutes d'un endpoint |
| `GET` | `/consumption` | *Legacy, déprécié* : séries de consommation (`granularity`, `format`, `from`, `to`) |

Exemple :

```bash
curl -H "Authorization: Bearer $OHM_API_TOKEN" "http://127.0.0.1:8080/v1/meters"
```

#### Identifiants opaques

`meterId` et `contractId` sont les 12 premiers caractères hexadécimaux du SHA-256 du PDL ou du
numéro de contrat. Obtenez-les avec `GET /v1/meters` et `GET /v1/contracts`. Le PDL n'apparaît jamais
dans une URL : il reste dans le corps de la réponse de `/v1/meters`. Le numéro de contrat n'est pas exposé.

#### Paramètres, limites et délais

- Dates au format `YYYY-MM-DD`. Les bornes `from` et `to` sont incluses.
- Plage de 31 jours au maximum pour les relevés, la consommation (`hour`, `day`, `week`), le profil
  et la veille. Les anomalies demandent entre 7 et 31 jours.
- `granularity=month` ne couvre que les 6 derniers mois. Une plage plus ancienne donne une erreur 422.
- Pagination des relevés et des factures : `page` (à partir de 1) et `limit` (1 à 500, 100 par défaut).
  L'en-tête `Link` donne les pages précédente et suivante.
- Relevés au format CSV : en-tête `Accept: text/csv` sur `listMeterReadings`. Sur la route legacy
  `/consumption`, utilisez `format=csv`.
- `against` accepte uniquement `previous`. La valeur `last-year` donne une erreur 422.
- **Délai des données : 24 à 48 h.** Le champ `meta.delay_notice` le rappelle. Une période récente
  peut être incomplète (`complete: false`).

#### Authentification

Si `OHM_API_TOKEN` est défini, chaque requête (sauf `/health`) doit contenir l'en-tête
`Authorization: Bearer <jeton>`. Si la variable n'est pas définie, aucune authentification n'est exigée.

#### Erreurs

Les erreurs des routes `/v1` suivent la norme RFC 9457 (`application/problem+json`), avec les champs
`type`, `title`, `status` et `detail` :

| Code | Cas |
|---|---|
| 400 | Paramètre mal formé (date, entier, valeur d'énumération inconnue) |
| 401 | Jeton absent ou invalide |
| 404 | Identifiant inconnu pour ce compte |
| 422 | Paramètres bien formés mais non traitables (plage trop longue, `from` après `to`, valeur non supportée) |
| 429 | Trop de requêtes ; l'en-tête `Retry-After` indique le délai d'attente |
| 502 | Erreur de l'espace client Ohm Énergie ou réponse invalide |
| 503 | Connexion à Ohm Énergie non établie, ou service en cours de démarrage |

Les routes `legacy` répondent avec le format historique `{"error": "..."}`.

#### Déploiement avec Docker Compose

Le projet fournit un conteneur durci (`Dockerfile`) et un fichier `compose.yml` :

```bash
# Lancement en arrière-plan
docker compose up -d

# Vérification de l'état
docker compose ps
curl http://127.0.0.1:8080/health

# Arrêt
docker compose down
```

#### Sécurité et courtoisie réseau

- **Écoute restreinte par défaut** : le service s'écoute sur `127.0.0.1` en local et via `OHM_PUBLISH_ADDRESS=127.0.0.1` dans Docker Compose.
- **Authentification par jeton Bearer** : définissez `OHM_API_TOKEN` dans votre `.env` dès que le service est accessible au-delà de la machine locale. Chaque requête (hors `/health`) devra contenir l'en-tête `Authorization: Bearer <votre_jeton>`.
- **Cache mémoire & politesse** : un cache mémoire TTL (`OHM_CACHE_TTL`, 900 s par défaut) évite de solliciter l'espace client Ohm lors de requêtes répétées.
- **Bypass de cache sécurisé** : le paramètre `?refresh=1` force un rafraîchissement amont, mais est limité à un seul appel toutes les 60 secondes par endpoint (HTTP 429 au-delà).
- **Verrouillage amont** : tous les appels amont sont sérialisés (`Lock`) et espacés d'au moins 1 seconde.
- **Conteneur non privilégié** : système de fichiers racine en lecture seule (`read_only: true`), utilisateur non-root (UID 1000), capacités Linux révoquées (`cap_drop: ALL`), `no-new-privileges`.

### Collection Bruno (`bruno/`)

La collection pour le client d'API open source [Bruno](https://usebruno.com) est générée depuis
`docs/openapi.yaml`. Elle contient une requête par opération, rangée dans un dossier par tag :
`system`, `meters`, `contracts`, `readings`, `consumption`, `billing` et `legacy`. Les variantes
(format CSV, granularité, période, regroupement) ont leur propre requête. Chaque requête contient
une documentation en français et des assertions de réponse.

Pour l'ouvrir :

1. Ouvrez Bruno et cliquez sur **Open Collection**.
2. Sélectionnez le dossier `bruno/` du dépôt.
3. Choisissez l'environnement **local** (`127.0.0.1`, port `8080`).
4. Si `OHM_API_TOKEN` est défini, renseignez la variable secrète `token` dans l'environnement local.
5. Lancez d'abord `listMeters` (dossier `meters`) puis `listContracts` (dossier `contracts`). Leurs
   scripts enregistrent le premier `meterId` et le premier `contractId`. `listContractInvoices`
   enregistre aussi le premier `invoiceId`. Les autres requêtes utilisent ces valeurs.

Ne modifiez pas les fichiers `.bru` à la main : ils sont régénérés. Pour régénérer la collection
après une évolution du contrat (PyYAML requis, inclus dans `requirements-dev.txt`) :

```bash
python scripts/gen_bruno.py          # régénère bruno/ et supprime les fichiers obsolètes
python scripts/gen_bruno.py --check  # échoue si bruno/ ne correspond plus au contrat
```


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
│   ├── cli.py           # argparse, dump, consumption, discover, serve
│   ├── client.py        # session HTTP, connexion, jeton, délais
│   ├── config.py        # lecture de .env
│   ├── consumption.py   # dates, plafond, mise à plat, CSV
│   ├── endpoints.py     # catalogue, templating, exclusions
│   └── server.py        # service HTTP REST (ThreadingHTTPServer)
├── bruno/               # collection Bruno, générée depuis docs/openapi.yaml
├── scripts/
│   └── gen_bruno.py     # génération et vérification Bruno depuis le contrat
├── Dockerfile           # conteneur Python 3.14-slim non-root sécurisé
├── compose.yml          # déploiement Docker Compose durci
├── .dockerignore
├── discover.py          # inventaire (forme des réponses)
├── docs/
│   ├── api_map.md       # cartographie de l'API
│   ├── openapi.yaml     # contrat de l'API v1 (OpenAPI 3.1)
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
