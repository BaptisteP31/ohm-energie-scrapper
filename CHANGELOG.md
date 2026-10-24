# Journal des modifications

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
