# Inventaire des données accessibles : espace client Ohm Énergie

Généré le 2026-10-24 par `discover.py` (lecture seule). Ce document ne contient que la forme des réponses.

## Garde-fous appliqués

- Une seule connexion (`POST /api/login`), sans nouvelle tentative.
- Uniquement des `GET` de lecture et le `POST` de lecture horaire (`{date, pdl}`), listés en allowlist.
- Pause d'au moins 1 s entre deux requêtes, 60 requêtes au maximum (connexion et rafraîchissement compris).
- Valeurs masquées : `<redacted:id>` pour les identifiants en clé, `<date>` pour les dates en clé. Les chaînes ne sont jamais reproduites ; seules les plages de dates et les minimum/maximum de kWh le sont.
- Aucune réponse brute n'est enregistrée sur disque.

## Connexion

- Statut HTTP : 200, statut `meta` : 200.
- Cookie `_token` : présent.
- Contrat et numéro client : renseignés (valeurs non reproduites).

Forme de la réponse de connexion :

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (1 clés)
    - `user` : objet (12 clés)
      - `id` : chaîne
      - `firstname` : chaîne
      - `lastname` : chaîne
      - `email` : chaîne
      - `avatar` : chaîne
      - `customer_nbr` : chaîne
      - `street` : chaîne
      - `country_code` : chaîne
      - `tel` : chaîne
      - `tel_complementary` : null
      - `elec_contracts` : tableau (longueur 1)
        - `[]` : chaîne
      - `gaz_contracts` : tableau (longueur 0)
        - `[]` : vide

## Résumé

- Requêtes HTTP envoyées : 39 (dont connexion).
- Endpoints réussis : 38 (dont 38 avec des données JSON non vides).
- Endpoints en échec : 0.
- Endpoints ignorés : 38 (voir la section dédiée).

### Informations récupérables (réponses JSON non vides)

- **Compte** : Tableau de bord, Fiche compte du contrat, Liste des contrats, Préférences, Adresses, Fiche info conseil, Assurance CPV client, Affichage Ecojoko (indicateur)
- **Référentiel** : Motifs de demande (référentiel)
- **Facturation** : Factures du contrat, Factures et paiements, Paiements du contrat, Tous les paiements, Toutes les factures, Solde du contrat, Solde total, Détail des soldes, Graphe d'échéancier, Contrôles énergie, Activation du suivi
- **Documents** : CPV (métadonnées), CGV (métadonnées), Liste des grilles tarifaires
- **Assurance Neat** : Échéancier Neat, CPV Neat
- **Conseils** : Conseils personnalisés, DPE, Questionnaire, Avancement du questionnaire
- **Consommation** : Consommation 6 mois, Consommation dernier mois, Résumé du mois précédent, kWh et euros agrégés, Comparaison logements similaires, Seuils de consommation, Usages, Courbe horaire kWh (veille)
- **Production** : Production solaire 6 mois

## Détail par endpoint

### Tableau de bord

`GET user/{number}/dashboard/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 1)
    - `[]` : objet (18 clés)
      - `firstname` : chaîne
      - `lastname` : chaîne
      - `avatar` : chaîne
      - `customer_nbr` : chaîne
      - `contract_nbr` : chaîne
      - `energy_type` : chaîne
      - `next_prelevement_date` : date (du 2026-11-05 au 2026-11-05)
      - `next_prelevement_amount` : chaîne
      - `settlement_periodicity` : nombre
      - `address` : chaîne
      - `status` : chaîne
      - `solde` : chaîne
      - `advice` : chaîne
      - `has_last_invoice` : booléen
      - `access_to_cons_data` : booléen
      - `elec_contracts` : tableau (longueur 1)
        - `[]` : chaîne
      - `gaz_contracts` : tableau (longueur 0)
        - `[]` : vide
      - `adresses_list` : objet (1 clés)
        - `<redacted:id>` : chaîne

### Fiche compte du contrat

`GET user/{number}/account/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 1)
    - `[]` : objet (17 clés)
      - `customer_nbr` : chaîne
      - `email` : chaîne
      - `cocontractant_name` : null
      - `cocontractant_email` : null
      - `tel` : chaîne
      - `tel_secondary` : null
      - `invoicing_street` : chaîne
      - `invoicing_zip_code` : chaîne
      - `invoicing_city` : chaîne
      - `address` : chaîne
      - `elec_contract_nbr` : chaîne
      - `pdl` : chaîne
      - `gaz_contract_nbr` : null
      - `pce` : null
      - `iban` : chaîne
      - `settlement_periodicity` : nombre
      - `prelevement_date` : chaîne

### Liste des contrats

`GET user/{number}/contracts` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 1)
    - `[]` : objet (42 clés)
      - `customer_nbr` : chaîne
      - `firstname` : chaîne
      - `lastname` : chaîne
      - `address` : chaîne
      - `contract_nbr` : chaîne
      - `contractual_start_date` : date
      - `access_to_cons_data` : booléen
      - `linky` : booléen
      - `contract_status` : chaîne
      - `subscribed_power_EL` : chaîne
      - `contract_category_NG` : chaîne
      - `grille_tarifaire` : tableau (longueur 9)
        - `[]` : objet (8 clés)
          - `date` : date (du 2026-10-31 au 2026-10-31)
          - `date_download` : date (du 2023-09-26 au 2026-09-09)
          - `offer_code` : chaîne
          - `grille_offer_code` : chaîne
          - `start_date` : date (du 2026-01-12 au 2026-01-12)
          - `end_date` : date (du 2026-10-31 au 2026-10-31)
          - `offer_name` : chaîne
          - `display_name_grille` : objet (2 clés)
            - `grille_month` : chaîne
            - `grille_file_name` : chaîne
      - `next_prelevement_amount` : null
      - `price_kwh` : tableau (longueur 2)
        - `[]` : tableau (longueur 2)
          - `[]` : chaîne
      - `price_abo` : chaîne
      - `option_tarifaire` : chaîne
      - `option_green` : null
      - `cocontractant_name` : null
      - `cocontractant_email` : null
      - `product_code` : chaîne
      - `pdl` : chaîne
      - `energy_type` : chaîne
      - `street_number` : chaîne
      - `street` : chaîne
      - `zip_code` : chaîne
      - `city` : chaîne
      - `solde` : nombre
      - `settlement_periodicity_code` : nombre
      - `contractual_end_date` : null
      - `token_recouvrement` : chaîne
      - `has_axa` : null
      - `has_neat` : null
      - `contract_termination_request` : null
      - `sponsorship_code` : chaîne
      - `has_parrainage` : null
      - `hc_1` : chaîne
      - `hc_2` : chaîne
      - `hc_3` : null
      - `hc_ete_ohm` : null
      - `hc_hiver_ohm` : null
      - `hc_ohm_date` : null
      - `has_hc_ohm` : booléen

### Préférences

`GET user/{number}/preference/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (1 clés)
    - `access_to_cons_data` : booléen

### Adresses

`GET user/adresses` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 0)
    - `[]` : vide

### Fiche info conseil

`GET user/{number}/fiche-info-conseil` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 0)
    - `[]` : vide

### Assurance CPV client

`GET user/{number}/insurance-cpv-client` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 0)
    - `[]` : vide

### Affichage Ecojoko (indicateur)

`GET user/{number}/display-ecojoko/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (1 clés)
    - `display_ecojoko` : booléen

### Motifs de demande (référentiel)

`GET salesforce-request-questions` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (2 clés)
    - `reasons` : tableau (longueur 12)
      - `[]` : objet (2 clés)
        - `id` : nombre
        - `question` : chaîne
    - `sub_reasons` : tableau (longueur 54)
      - `[]` : objet (3 clés)
        - `id` : nombre
        - `salesforce_question_id` : nombre
        - `sub_question` : chaîne

### Factures du contrat

`GET user/{number}/billing/invoices/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 3)
    - `[]` : nombre ou tableau (longueur 8)
      - `[]` : objet (12 clés)
        - `invoice_nbr` : chaîne
        - `invoice_type_text` : chaîne
        - `invoicing_period` : chaîne
        - `invoice_date` : date
        - `invoice_due_date` : date
        - `amount_ttc` : chaîne
        - `invoice_amount_paid` : chaîne
        - `invoice_amount_due` : chaîne
        - `invoice_id` : chaîne
        - `invoice_type_hgz` : chaîne
        - `contract_nbr` : chaîne
        - `can_download` : booléen

### Factures et paiements

`GET user/{number}/billing/invoices-payments/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (1 clés)
    - `invoices` : objet (1 clés)
      - `<redacted:id>` : tableau (longueur 1)
        - `[]` : objet (6 clés)
          - `payment_date` : date
          - `payment_amount` : chaîne
          - `payment_type` : chaîne
          - `payment_id` : chaîne
          - `energy_type` : chaîne
          - `payment_name` : chaîne

### Paiements du contrat

`GET user/{number}/billing/payments/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 1)
    - `[]` : tableau (longueur 8)
      - `[]` : objet (7 clés)
        - `payment_date` : date
        - `payment_amount` : chaîne
        - `payment_type` : chaîne
        - `payment_id` : chaîne
        - `payment_communication` : chaîne
        - `payment_name` : chaîne
        - `contract_nbr` : chaîne

### Tous les paiements

`GET user/{number}/billing/all-payments` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 1)
    - `[]` : objet (2 clés)
      - `payment_infos` : tableau (longueur 8)
        - `[]` : objet (8 clés)
          - `payment_date` : date
          - `payment_amount` : chaîne
          - `payment_type` : chaîne
          - `payment_id` : chaîne
          - `payment_communication` : chaîne
          - `payment_name` : chaîne
          - `contract_nbr` : chaîne
          - `energy_type` : chaîne
      - `grouped_payments` : objet (8 clés)
        - `2026-10` : tableau (longueur 1)
          - `[]` : objet (8 clés)
            - `payment_date` : date
            - `payment_amount` : chaîne
            - `payment_type` : chaîne
            - `payment_id` : chaîne
            - `payment_communication` : chaîne
            - `payment_name` : chaîne
            - `contract_nbr` : chaîne
            - `energy_type` : chaîne
        - `2026-09` : tableau (longueur 1)
          - `[]` : objet (8 clés)
            - `payment_date` : date
            - `payment_amount` : chaîne
            - `payment_type` : chaîne
            - `payment_id` : chaîne
            - `payment_communication` : chaîne
            - `payment_name` : chaîne
            - `contract_nbr` : chaîne
            - `energy_type` : chaîne
        - `2026-08` : tableau (longueur 1)
          - `[]` : objet (8 clés)
            - `payment_date` : date
            - `payment_amount` : chaîne
            - `payment_type` : chaîne
            - `payment_id` : chaîne
            - `payment_communication` : chaîne
            - `payment_name` : chaîne
            - `contract_nbr` : chaîne
            - `energy_type` : chaîne
        - `2026-07` : tableau (longueur 1)
          - `[]` : objet (8 clés)
            - `payment_date` : date
            - `payment_amount` : chaîne
            - `payment_type` : chaîne
            - `payment_id` : chaîne
            - `payment_communication` : chaîne
            - `payment_name` : chaîne
            - `contract_nbr` : chaîne
            - `energy_type` : chaîne
        - `2026-06` : tableau (longueur 1)
          - `[]` : objet (8 clés)
            - `payment_date` : date
            - `payment_amount` : chaîne
            - `payment_type` : chaîne
            - `payment_id` : chaîne
            - `payment_communication` : chaîne
            - `payment_name` : chaîne
            - `contract_nbr` : chaîne
            - `energy_type` : chaîne
        - `2026-05` : tableau (longueur 1)
          - `[]` : objet (8 clés)
            - `payment_date` : date
            - `payment_amount` : chaîne
            - `payment_type` : chaîne
            - `payment_id` : chaîne
            - `payment_communication` : chaîne
            - `payment_name` : chaîne
            - `contract_nbr` : chaîne
            - `energy_type` : chaîne
        - `2026-04` : tableau (longueur 1)
          - `[]` : objet (8 clés)
            - `payment_date` : date
            - `payment_amount` : chaîne
            - `payment_type` : chaîne
            - `payment_id` : chaîne
            - `payment_communication` : chaîne
            - `payment_name` : chaîne
            - `contract_nbr` : chaîne
            - `energy_type` : chaîne
        - `2026-02` : tableau (longueur 1)
          - `[]` : objet (8 clés)
            - `payment_date` : date
            - `payment_amount` : chaîne
            - `payment_type` : chaîne
            - `payment_id` : chaîne
            - `payment_communication` : chaîne
            - `payment_name` : chaîne
            - `contract_nbr` : chaîne
            - `energy_type` : chaîne

### Toutes les factures

`GET user/{number}/billing/all-invoices` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 3)
    - `[]` : nombre ou tableau (longueur 8)
      - `[]` : objet (13 clés)
        - `invoice_nbr` : chaîne
        - `invoice_type_text` : chaîne
        - `invoicing_period` : chaîne
        - `invoice_date` : date
        - `invoice_due_date` : date
        - `amount_ttc` : chaîne
        - `invoice_amount_paid` : chaîne
        - `invoice_amount_due` : chaîne
        - `invoice_id` : chaîne
        - `invoice_type_hgz` : chaîne
        - `contract_nbr` : chaîne
        - `energy_type` : chaîne
        - `can_download` : booléen

### Solde du contrat

`GET user/{number}/billing/balance/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (4 clés)
    - `status` : nombre
    - `message` : chaîne
    - `file` : chaîne
    - `line` : nombre
  - `body` : tableau (longueur 0)
    - `[]` : vide

### Solde total

`GET user/{number}/billing/balance/total/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (2 clés)
    - `soldes` : objet (1 clés)
      - `<redacted:id>` : nombre
    - `total_sum` : chaîne

### Détail des soldes

`GET user/{number}/billing/balance-details` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 0)
    - `[]` : vide

### Graphe d'échéancier

`GET user/{number}/billing/echeancier/graphe/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 0)
    - `[]` : vide

### Contrôles énergie

`GET user/{number}/billing/energy-checks` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 0)
    - `[]` : vide

### Activation du suivi

`GET user/{number}/billing/tracking-activation/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (4 clés)
    - `first_step` : objet (2 clés)
      - `first_step_green` : booléen
      - `first_step_date` : date (du 2026-01-12 au 2026-01-12)
    - `second_step` : objet (2 clés)
      - `second_step_green` : booléen
      - `second_step_date` : date (du 2026-02-10 au 2026-02-10)
    - `third_step` : objet (2 clés)
      - `third_step_green` : booléen
      - `third_step_date` : date (du 2026-10-24 au 2026-10-24)
    - `fourth_step` : objet (2 clés)
      - `fourth_step_green` : booléen
      - `fourth_step_date` : date (du 2026-02-17 au 2026-02-17)

### CPV (métadonnées)

`GET user/{number}/document/cpv` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (2 clés)
    - `pdf` : chaîne
    - `filename` : chaîne

### CGV (métadonnées)

`GET user/{number}/document/cgv/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (1 clés)
    - `cgv` : chaîne

### Liste des grilles tarifaires

`GET user/{number}/document/list-grilles-tarifaires/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (1 clés)
    - `grilles_tarifaires` : tableau (longueur 10)
      - `[]` : objet (8 clés)
        - `date` : date (du 2026-01-12 au 2026-10-12)
        - `date_download` : date (du 2026-01-01 au 2026-01-01)
        - `offer_code` : chaîne
        - `grille_offer_code` : chaîne
        - `start_date` : date (du 2026-01-12 au 2026-01-12)
        - `end_date` : date (du 2026-10-31 au 2026-10-31)
        - `offer_name` : chaîne
        - `display_name_grille` : objet (2 clés)
          - `grille_month` : chaîne
          - `grille_file_name` : chaîne

### Échéancier Neat

`GET user/{number}/billflow/neat/echeancier` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 0)
    - `[]` : vide

### CPV Neat

`GET user/{number}/billflow/neat/cpv` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 0)
    - `[]` : vide

### Conseils personnalisés

`GET user/{number}/advice/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 6)
    - `[]` : objet (4 clés)
      - `timestamp` : chaîne
      - `code` : chaîne
      - `tag` : chaîne
      - `conseil` : chaîne

### DPE

`GET user/{number}/dpe/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : null

### Questionnaire

`GET user/{number}/questionnary/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (3 clés)
    - `Home` : objet (10 clés)
      - `is_main_residence` : booléen
      - `is_owner` : null
      - `neighborhood` : null
      - `construction_date` : chaîne
      - `is_low_consumption` : null
      - `surface` : chaîne
      - `nb_people` : chaîne
      - `weekly_occupancy` : chaîne
      - `yearly_occupancy` : chaîne
      - `is_PV` : null
    - `Heat` : objet (6 clés)
      - `is_thermostat` : null
      - `heating_period` : chaîne
      - `is_aux_heating` : null
      - `is_aux_wood_heating` : null
      - `is_aux_solar_heating` : null
      - `therm_temp` : null
    - `Equipments` : objet (2 clés)
      - `cooktops` : objet (2 clés)
        - `<redacted:id>` : booléen
        - `is_gas_cooktop` : booléen
      - `cooking_frequency` : null

### Avancement du questionnaire

`GET user/{number}/questionnary-percentage/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (1 clés)
    - `percentage` : nombre

### Consommation 6 mois

`GET user/{number}/consumption/six-months/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 6)
    - `[]` : objet (2 clés)
      - `date` : date (du 2026-05-01 au 2026-10-01)
      - `consumption_kWh` : nombre (min 45.635, max 93.003)

### Consommation dernier mois

`GET user/{number}/consumption/last-month/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (7 clés)
    - `last_month` : date (du 2026-10-01 au 2026-10-01)
    - `last_month_consumption` : nombre (min 78.303, max 78.303)
    - `last_forecast_conso` : nombre (min 235, max 235)
    - `percentage` : nombre
    - `this_month` : booléen
    - `is_linky` : booléen
    - `access_to_cons_data` : booléen

### Résumé du mois précédent

`GET user/{number}/glance-previous-consumption/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (3 clés)
    - `linky` : booléen
    - `allowedConsumptionData` : booléen
    - `threeHouses` : objet (5 clés)
      - `average` : nombre
      - `lowDayDate` : nombre
      - `lowDayValue` : nombre
      - `highDayDate` : nombre
      - `highDayValue` : nombre

### kWh et euros agrégés

`GET user/{number}/consumption/kwh/{ct}/data` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (3 clés)
    - `consumptions` : objet (2 clés)
      - `kwh` : objet (3 clés)
        - `years` : objet (5 clés)
          - `dataYear` : tableau (longueur 5)
            - `[]` : nombre
          - `colorsYear` : tableau (longueur 5)
            - `[]` : chaîne
          - `border_colors` : tableau (longueur 5)
            - `[]` : chaîne
          - `labelsYear` : tableau (longueur 5)
            - `[]` : chaîne ou nombre
          - `dataString` : tableau (longueur 5)
            - `[]` : chaîne
        - `months` : objet (4 clés)
          - `dataMonth` : tableau (longueur 12)
            - `[]` : nombre
          - `colorsMonth` : tableau (longueur 12)
            - `[]` : chaîne
          - `labelsMonth` : tableau (longueur 12)
            - `[]` : chaîne
          - `dataString` : tableau (longueur 12)
            - `[]` : chaîne
        - `days` : objet (4 clés)
          - `labelsDay` : tableau (longueur 273)
            - `[]` : date (du 2026-02-01 au 2026-10-31)
          - `dataDay` : tableau (longueur 273)
            - `[]` : nombre
          - `dataString` : tableau (longueur 273)
            - `[]` : chaîne
          - `colorsDay` : tableau (longueur 273)
            - `[]` : chaîne
      - `euro` : objet (3 clés)
        - `years` : objet (9 clés)
          - `data` : tableau (longueur 5)
            - `[]` : nombre
          - `data_euro` : tableau (longueur 5)
            - `[]` : nombre
          - `data_tax_euro` : tableau (longueur 5)
            - `[]` : nombre
          - `colors` : tableau (longueur 5)
            - `[]` : chaîne
          - `border_colors` : tableau (longueur 5)
            - `[]` : chaîne
          - `labels` : tableau (longueur 5)
            - `[]` : chaîne ou nombre
          - `dataString` : tableau (longueur 5)
            - `[]` : chaîne
          - `dataEuroString` : tableau (longueur 5)
            - `[]` : chaîne
          - `dataFixEuroString` : tableau (longueur 5)
            - `[]` : chaîne
        - `months` : objet (8 clés)
          - `dataEuroMonth` : tableau (longueur 12)
            - `[]` : nombre
          - `data_euroMonth` : tableau (longueur 12)
            - `[]` : nombre
          - `data_tax_euroMonth` : tableau (longueur 12)
            - `[]` : nombre
          - `colorsEuroMonth` : tableau (longueur 12)
            - `[]` : chaîne
          - `labelsEuroMonth` : tableau (longueur 12)
            - `[]` : chaîne
          - `dataString` : tableau (longueur 12)
            - `[]` : chaîne
          - `dataEuroString` : tableau (longueur 12)
            - `[]` : chaîne
          - `dataFixEuroString` : tableau (longueur 12)
            - `[]` : chaîne
        - `days` : objet (8 clés)
          - `dataEuroDay` : tableau (longueur 273)
            - `[]` : nombre
          - `data_euroDay` : tableau (longueur 273)
            - `[]` : nombre
          - `data_tax_euroDay` : tableau (longueur 273)
            - `[]` : nombre
          - `dataString` : tableau (longueur 273)
            - `[]` : chaîne
          - `data_euroString` : tableau (longueur 273)
            - `[]` : chaîne
          - `data_tax_euroString` : tableau (longueur 273)
            - `[]` : chaîne
          - `labelsEuroDay` : tableau (longueur 273)
            - `[]` : date (du 2026-02-01 au 2026-10-31)
          - `colorsEuroDay` : tableau (longueur 273)
            - `[]` : chaîne
    - `forcast` : objet (2 clés)
      - `data` : tableau (longueur 12)
        - `[]` : nombre
      - `labels` : tableau (longueur 12)
        - `[]` : chaîne
    - `others` : objet (7 clés)
      - `contractual_start_date` : date
      - `loopValue` : nombre
      - `linky` : booléen
      - `allowed_consumption_data` : booléen
      - `energy_type` : chaîne
      - `scales` : objet (5 clés)
        - `dayThreshold_1` : nombre
        - `dayThreshold_2` : nombre
        - `<redacted:id>` : nombre
        - `yearThreshold_1` : nombre
        - `yearThreshold_2` : nombre
      - `pdl` : chaîne

### Comparaison logements similaires

`GET user/{number}/house-consumption/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (1 clés)
    - `quantile` : nombre

### Seuils de consommation

`GET user/{number}/consumption/threshold/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (10 clés)
    - `contractual_start_date` : date
    - `contractual_start_year` : nombre
    - `loopValue` : nombre
    - `linky` : booléen
    - `allowed_consumption_data` : booléen
    - `energy_type` : chaîne
    - `scales` : objet (5 clés)
      - `dayThreshold_1` : nombre
      - `dayThreshold_2` : nombre
      - `<redacted:id>` : nombre
      - `yearThreshold_1` : nombre
      - `yearThreshold_2` : nombre
    - `pdl` : chaîne
    - `power_abonnement` : nombre (min 6, max 6)
    - `power_conseillee` : nombre (min 0, max 0)

### Usages

`GET user/{number}/usage-consumption/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (4 clés)
    - `nilmData` : objet (12 clés)
      - `Cooking` : nombre
      - `Light` : nombre
      - `ECS` : nombre
      - `Other` : nombre
      - `Multimedia` : nombre
      - `BigApp` : nombre
      - `EV` : nombre
      - `Pool` : nombre
      - `Heat` : nombre
      - `HVAC` : nombre
      - `StandBy` : nombre
      - `Cold` : nombre
    - `defaultNilm` : booléen
    - `nilmECS` : booléen
    - `alertDhw` : null

### Production solaire 6 mois

`GET user/{number}/solar/six-months/{ct}` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : tableau (longueur 0)
    - `[]` : vide

### Courbe horaire kWh (veille)

`POST user/{number}/consumption/kwh/{ct}/hours` : statut 200, réponse JSON.

- `(racine)` : objet (3 clés)
  - `success` : booléen
  - `meta` : objet (2 clés)
    - `status` : nombre
    - `message` : chaîne
  - `body` : objet (1 clés)
    - `consumptions` : objet (4 clés)
      - `data` : tableau (longueur 48)
        - `[]` : nombre
      - `dataString` : tableau (longueur 48)
        - `[]` : chaîne
      - `time` : tableau (longueur 48)
        - `[]` : chaîne
      - `heuresCreuseColors` : tableau (longueur 48)
        - `[]` : chaîne

## Échecs

Aucun.

## Endpoints ignorés et raisons

| Méthode | Chemin | Raison |
|---|---|---|
| PATCH / DELETE | `tous les endpoints PATCH et DELETE de api_map.md` | mutation (exclusion stricte) |
| DELETE | `logout/{number}` | déconnexion (exclusion stricte) |
| GET | `user/{number}/initparrainage` | parrainage, effet de bord (exclusion stricte) |
| GET | `user/{number}/parrainage` | parrainage (exclusion stricte) |
| GET | `user/{number}/chatbot/url` | chatbot (exclusion stricte) |
| GET | `callback/{provider}` | callback réseau social (exclusion stricte) |
| GET | `user/{number}/send/email/code` | envoie un code par e-mail (effet de bord) |
| GET | `user/{number}/ecojoko-order/{ct}` | commande Ecojoko (mutation) |
| GET | `user/{number}/stripe` | abonnements Stripe : incertain, exclusion « subscription » |
| GET | `user/{number}/stripe/all` | abonnements Stripe : incertain, exclusion « subscription » |
| POST | `user/{number}/stripe/cancel` | résiliation d'abonnement (mutation) |
| POST | `user/{number}/stripe/retract` | rétractation d'abonnement (mutation) |
| POST | `user/{number}/billflow/neat/subscription/retract` | rétractation Neat (mutation) |
| POST | `user/{number}/billflow/neat/subscription/terminate` | résiliation Neat (mutation) |
| POST | `user/{number}/billflow/neat/resiliation/request/{ct}` | demande de résiliation (mutation) |
| POST | `user/{number}/send-request-to-salesforce/{ct}` | crée une demande Salesforce (mutation) |
| GET | `user/{number}/billflow/neat/get-customer-info` | paramètre customerRef non documenté |
| GET | `user/{number}/billflow/neat/invoice` | paramètre invoiceId requis, non disponible |
| POST | `faq` | POST hors consommation (non lecture certifiée) |
| POST | `user/{number}/document/grille-tarifaire/{ct}` | POST hors consommation (corps offer_code) |
| POST | `user/{number}/consumption/co2/{ct}/hours` | POST de lecture, mais corps {date} seul : hors allowlist |
| POST | `user/{number}/consumption/euro/{ct}/hours` | POST de lecture, mais corps {date} seul : hors allowlist |
| POST | `user/{number}/consumption/power/{ct}/years|months|days` | corps inconnu (args non documentés) |
| POST | `user/{number}/period-consumption/{ct}` | corps {startDate, endDate} : hors allowlist |
| GET | `user/{number}/get-conso-cadran/{ct}` | GET utilisé comme mutation côté SPA : incertain |
| GET | `user/{number}/consumption/co2/{ct}/data` | GET utilisé comme mutation côté SPA : incertain |
| GET | `user/{number}/consumption/download/{ct}` | export de fichier, format de dateRange non documenté |
| GET | `contracts-new` | flux SSE, non JSON |
| GET | `user/{number}/document/invoice/{ct}/{id}` | PDF binaire, identifiant requis |
| GET | `user/{number}/document/last-invoice/{ct}` | PDF binaire |
| GET | `user/{number}/document/echeancier/{ct}` | PDF binaire |
| GET | `user/{number}/document/justificatif/{ct}` | PDF binaire |
| POST | `login, register, forget-password, recover-reference, first-connection/*` | authentification / envoi d'e-mails |
| GET | `refresh` | utilisé seulement en cas d'expiration du jeton |
| GET | `get-contracts/{token}, access-ghost/{token}/{email}` | jetons d'authentification / impersonation |
| — | `bo-api (notifications, streaming Socket.IO)` | hors espace client, exclusion stricte |
| — | `cagnotte/*` | fonctionnalité désactivée côté code (aucun appel réseau) |
| — | `documents AXA / Neat statiques` | base d'URL « undefined », non appelés |
