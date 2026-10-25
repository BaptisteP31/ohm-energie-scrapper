# Journal des modifications

## 0.3.0 — 2026-10-24

API v1 en lecture seule, décrite par un contrat OpenAPI.

- **API v1 (`/v1`)** : routes `GET` pour les compteurs, les relevés demi-heure, la consommation
  (série, résumé, comparaison, profil, veille, anomalies, répartition), les contrats, les factures,
  les soldes et les métadonnées des grilles tarifaires. Aucune route d'écriture.
- **Contrat OpenAPI 3.1 (`docs/openapi.yaml`)** : référence des routes, des paramètres, des réponses
  et des erreurs. Les erreurs suivent la norme RFC 9457 (`application/problem+json`).
- **Identifiants opaques** : `meterId` et `contractId` remplacent le PDL et le numéro de contrat dans
  les URL.
- **Routes legacy** : `/endpoints`, `/data`, `/data/{name}` et `/consumption` sont conservées à
  l'identique et marquées comme dépréciées.
- **Collection Bruno générée depuis le contrat** : une requête par opération, rangée par tag, avec
  l'environnement `local` et la capture automatique de `meterId`, `contractId` et `invoiceId`. Elle
  remplace la collection 0.2.0. `tests/test_bruno_sync.py` échoue si la collection ne correspond plus
  au contrat.

## 0.2.0 — 2026-10-24

Service HTTP REST, conteneurisation Docker durcie et collection Bruno.

- **Service HTTP (`ohm_scraper/server.py`)** :
  - Démarrage via `python -m ohm_scraper serve` (options `--host`, `--port`).
  - Routes disponibles en lecture seule : `/health`, `/endpoints`, `/data`, `/data/{name}`, `/consumption`.
  - Format de réponse JSON structuré et réponses d'erreur explicites (`{"error": ...}`).
  - Export CSV disponible sur `/consumption` via `format=csv`.
  - Gestion de session paresseuse (*lazy login*) avec re-connexion unique sur expiration de jeton (401).
  - Sérialisation des requêtes amont via un verrou (`threading.Lock`) et maintien du délai minimal de 1 s.
  - Cache en mémoire avec TTL configurable (`OHM_CACHE_TTL`, 900 s par défaut).
  - Contournement du cache via `?refresh=1`, limité à un appel toutes les 60 secondes par endpoint (HTTP 429).
  - Authentification optionnelle par jeton Bearer (`OHM_API_TOKEN`) avec comparaison en temps constant (`hmac.compare_digest`).
- **Configuration étendue (`ohm_scraper/config.py`, `.env.example`)** :
  - Nouvelles variables : `SERVICE_HOST`, `SERVICE_PORT`, `OHM_PUBLISH_ADDRESS`, `OHM_API_TOKEN`, `OHM_CACHE_TTL`.
  - Documentation complète en français de chaque paramètre.
- **Conteneurisation (`Dockerfile`, `compose.yml`, `.dockerignore`)** :
  - Image basée sur `python:3.14-slim`, utilisateur non-root (`appuser`, UID 1000).
  - Racine en lecture seule (`read_only: true`), `tmpfs` sur `/tmp`, suppression de toutes les capacités Linux (`cap_drop: ALL`), `no-new-privileges`.
  - Healthcheck Docker intégré testant `/health`.
  - Publication sécurisée par défaut sur l'interface de bouclage locale (`127.0.0.1`).
- **Collection Bruno (`bruno/`) & générateur (`scripts/gen_bruno.py`)** :
  - 50 fichiers de requête couvrant `/health`, `/endpoints`, `/data`, chaque endpoint allowlisté, et les séries `/consumption` (JSON et CSV).
  - Environnement `local` préconfiguré avec gestion du secret `token`.
  - Script automatisé de génération et de vérification de synchronisation (`--check`).
- **Tests (59 tests hors ligne)** :
  - Nouveaux tests pour le serveur HTTP, la gestion du cache et du refresh, la validation des plages, l'authentification Bearer, et la synchronisation Bruno.

## 0.1.0 — 2026-10-24

Première version fonctionnelle et documentée.

- CLI `python -m ohm_scraper` avec les sous-commandes `dump`, `consumption` et `discover`.
- `dump` : une seule connexion, 37 endpoints GET de lecture allowlistés, écriture JSON
  dans `data/<horodatage>/<nom>.json`, options `--only` et `--list`.
- `consumption` : séries `hourly` (points de 30 minutes, en Wh et kWh) et `daily` (total
  journalier en kWh calculé depuis la courbe de charge), une requête par jour avec un plafond
  de 31 jours ; séries `power-days` et `power-months` (puissance maximale en kVA) ; plage de
  dates `jj/mm/aaaa` ou ISO, sortie JSON ou CSV.
- Catalogue d'endpoints partagé (`ohm_scraper/endpoints.py`) : noms courts stables,
  templating `{number}`/`{ct}`, endpoints de mutation exclus avec leur raison.
- Garde-fous communs : délai d'attente, 1 s minimum entre requêtes, connexion unique,
  un seul rafraîchissement de jeton, appels strictement en lecture.
- Configuration `.env` (`OHM_LOGIN`, `OHM_PASSWORD`) documentée, notamment les règles
  d'échappement de python-dotenv (`\"` et `$`).
- Tests pytest hors ligne (client HTTP simulé) : connexion, rafraîchissement, catalogue
  d'endpoints, dates et plafond horaire, conversion CSV, contrôle de fuite.
- README en français : installation, configuration, exemples, données disponibles,
  fraîcheur Enedis, dépannage.
- `discover.py` conservé et branché sur le catalogue partagé ; `docs/api_map.md` et
  `docs/inventory.md` inchangés.
