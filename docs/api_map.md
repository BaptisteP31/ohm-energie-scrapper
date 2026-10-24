# Cartographie de l'API Ohm Énergie (espace client)

Analyse statique du bundle principal `/tmp/ohm_bundle/index.js` (SPA Vite/React, minifiée, ~5 Mo).
Aucun appel réseau effectué, aucun fichier `.env` lu, bundle non exécuté.
Les noms de composants marqués « (heuristique) » sont déduits de la position dans le code minifié et peuvent être inexacts.

## Hôtes et base URL

| Rôle | URL | Source |
|---|---|---|
| API principale RTK Query | `https://espace-client.ohm-energie.com/api` | `API_URL$1` dans `baseQuery = fetchBaseQuery({baseUrl: API_URL$1, credentials: "include", ...})` |
| Back-office (notifications, streaming) | `https://bo-api.ohm-energie.com` | `logoutUser`, `fetch(\`${Ht}/notifications\`)`, `lookup(\`${qt}/streaming\`)` |
| Documents AXA / Neat (statiques) | `baseUrl: API_URL_DOC = "undefined"` (chaîne littérale) | `baseAxaDocQuery`, probablement une erreur de build |
| Auth réseaux sociaux | `https://espace-client.ohm-energie.com/api/callback/{provider}` | `authenticateUserViaProvider` |

Le bundle ne contient que 4 occurrences de `bo-api.ohm-energie.com`. Tous les endpoints métier passent par `espace-client.../api`.

## 1. Flux d'authentification

### 1.1 Connexion (login)

**Endpoint** : `POST https://espace-client.ohm-energie.com/api/login`, `Content-Type: application/json`, `credentials: "include"`.

Définition RTK :
```js
login:_.mutation({query:j=>({url:"/login",method:"POST",body:{...j},header:{"Content-Type":"application/json"}})})
```

**Payload** (construit dans le handler du formulaire, composant `Login`) :
- `email` : adresse e-mail en minuscules si elle matche `/^[^\s@]+@[^\s@]+\.[^\s@]+$/`, sinon la référence client brute (format validé par le schéma `/^CM-\d+$/`, message « CM-000000000000 »). Le même champ sert donc d'identifiant e-mail ou de référence client.
- `password` : mot de passe saisi.

Code (minifié, simplifié) :
```js
Sr=Mr=>/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(Mr)
...
let dn; Sr(zr) ? dn=zr.toLowerCase() : dn=zr;
Ar({email:dn, password:Yr})
```

**Connexion via réseau social** : le SPA appelle d'abord `GET /api/callback/{provider}?token={access_token}` (`fetch`, `credentials: "include"`), puis envoie `{email, provider_id, provider}` à `/login` (même handler `Ar`). Les champs `token` et `provider` viennent du fournisseur OAuth.

**Champs de réponse utilisés** :
- `success` (bool), `meta.status` (200 attendu), `meta.message`.
- `body.user` : objet utilisateur, avec notamment `customer_nbr`, `currentContract`, `elec_contracts`, `gaz_contracts`, `email`, `is_eveler`, `contractStatus`, `pdl`, `linky`, `access_to_cons_data`, `has_virtual_battery`, `is_soho`, `balance`, `sponsorship_code`, `contractStartDate`.
- `body.reauthenticate` + `body[0]` : compte à réauthentifier (cas multi-comptes).
- `is_eveler` (niveau racine) : cas particulier qui redirige vers un autre parcours.
- Codes d'erreur mappés en français : 400, 401, 403, 404, 500, 502, 503, 504, 0 (réseau).

Extrait du traitement de la réponse :
```js
const zr = await vt(Mr).unwrap();   // vt = useLoginMutation
if (zr.meta.status != 200 && qt.length == 0) { /* message d'erreur */ }
if (zr.body.reauthenticate) { /* sélection du compte */ }
let Yr = zr.body.user;
await ot(!0, Yr);                    // setAuth(true, user)
tn || (tn = Yr.currentContract || Yr.elec_contracts[0] || Yr.gaz_contracts[0]);
tn && pt(tn);                        // setSelectedContract
await Lr(Yr?.customer_nbr, tn);      // chargement des contrats
```

### 1.2 Où est stocké le jeton

- **Cookie `_token`** : le jeton de session est lu par `getEcSessionToken()` via `document.cookie`:
  ```js
  const _=document.cookie.match(/(?:^|;\s*)_token=([^;]*)/);
  ```
  Aucune écriture de ce cookie n'existe dans le bundle (`document.cookie=` n'apparaît que pour la sidebar). Le cookie est donc posé par le serveur (`Set-Cookie` sur `/api/login` ou `/api/callback`). Il ne doit pas être `HttpOnly`, sinon `getEcSessionToken()` renverrait `null`.
- **Redux (`auth`)** : `setToken(!0)` stocke un **booléen**, pas le jeton. `auth.user` contient l'objet utilisateur. Le store est persisté dans IndexedDB (`createIndexedDBStorage("espace_client")`) et chiffré avec `encryptTransform` (clé en dur dans le bundle, voir section 5).
- **localStorage** : `fcmToken` (notifications push uniquement). **sessionStorage** : `dashboardModalOpened`, `dashboard-notice-opened-after-login`.

### 1.3 Envoi du jeton sur les requêtes suivantes

- **espace-client (`/api/...`)** : pas d'en-tête `Authorization`. Le `baseQuery` n'ajoute que `Content-Type` et `Accept`, et envoie les cookies via `credentials: "include"`. L'authentification repose donc sur le cookie.
- **bo-api (`getBoApiAuthHeaders`)** : `Authorization: Bearer <valeur du cookie _token>` plus `credentials: "include"`.
- **Socket.IO `/streaming` (bo-api)** : `auth: {token}` et `extraHeaders: {Authorization: "Bearer ..."}`, `withCredentials: true`.

### 1.4 Rafraîchissement et expiration

Réaction dans `baseQueryWithReauth` :
- Si la réponse contient `meta.status === 401` et `meta.message === "token expired"`, le SPA appelle `GET /refresh` puis rejoue la requête. Les requêtes concurrentes attendent dans `pendingRequestsQueue`.
- Si `/refresh` renvoie `meta.message === "refresh token expired"`, le SPA déclenche `logoutUser`.
- Si `success === false`, `meta.status === 401` et `meta.message === "Unauthorized!"` hors page `/login`, le SPA déclenche `logoutUser`.

### 1.5 Déconnexion

- `DELETE /api/logout/{number}` (`logout`, appelé par `AccountOption` avec `{number: customer_nbr}`).
- Puis le thunk `logoutUser` :
  - `DELETE https://bo-api.ohm-energie.com/notifications/unregister` avec `{deviceId, fcmToken}` si `fcmToken` existe ;
  - suppression de `localStorage.fcmToken`, `RESET_STORE`, purge de la persistance ;
  - redirection vers `/login` (avec `?redirect=` si `ghost`).
- Le thunk ne supprime pas le cookie `_token` côté client. Ce point dépend donc du serveur.

### 1.6 Autres endpoints d'authentification

| Nom | Méthode | Chemin | Corps | Rôle |
|---|---|---|---|---|
| `register` | POST | `/register` | `{...j}` | inscription (non vérifié dans l'UI) |
| `refreshToken` | GET | `/refresh` | – | rafraîchissement |
| `recoverReference` | POST | `/recover-reference` | `{email}` | retrouver la référence client |
| `recoverPassword` | POST | `/forget-password` | `{email, first_connection}` | mot de passe oublié |
| `sendTokenForValidation` | GET | `/get-contracts/{token}` | – | vérifier un token de réinitialisation |
| `resetPassword` | PATCH | `/reset-password-new` | `{number, password, password_confirmation, token}` | réinitialisation |
| `firstConnection` | POST | `/first-connection/send-password-link` | `{number}` | première connexion |
| `setFirstConnectionPassword` | POST | `/first-connection/{token}` | `{password, password_confirmation}` | définir le mot de passe |
| `getAccessToken` | GET | `/access-ghost/{token}/{email}` | – | mode « fantôme » (impersonation, page `/fantom`) |

Les paramètres `token` et `email` des pages `/premiere-connexion`, `/recuperation-mdp` et `/fantom` viennent de la query string (`URLSearchParams`).

## 2. Endpoints de l'API

Conventions :
- `number` = `state.auth.user.customer_nbr` (référence client, ex. `CM-…`).
- `ct` = `state.auth.user.currentContract` (numéro de contrat sélectionné). Initialisé au login depuis `body.user.currentContract`, sinon premier contrat électricité, sinon premier gaz. Mis à jour par `setCurrentContract` quand l'utilisateur change de contrat. Certains composants utilisent aussi `state.selectedContractNumber.contract_nbr`, qui contient la même valeur.
- Chemins relatifs à `https://espace-client.ohm-energie.com/api/` sauf mention contraire.
- Type : **L** = lecture (GET, ou POST utilisé en lecture), **E** = écriture (PATCH, DELETE, ou POST qui modifie des données).
- Les composants sont donnés par heuristique (voir avertissement en tête).

### 2.1 Compte, préférences et contacts

| Endpoint (hook) | Méthode | Chemin | Corps | Composant (heuristique) | Type |
|---|---|---|---|---|---|
| `dashboard` | GET | `user/{number}/dashboard/{ct}` | – | Dashboard | L |
| `getContract` | GET | `user/{number}/account/{ct}` | – | AccountInfo | L |
| `getContracts` (SSE) | EventSource GET | `user/{number}/contracts-new?ct={ct}` | – | Login, Dashboard, Fantom | L |
| `getUserContractsInfo` | GET | `user/{number}/contracts` | – | non utilisé (défini) | L |
| `getPreferences` | GET | `/user/{number}/preference/{ct}` | – | Compte, MyPreferences | L |
| `setCommPreferences` | PATCH | `/user/{number}/preference/communication` | `{...args}` | MyPreferences | E |
| `setAlertPreferences` | PATCH | `/user/{number}/preference/alert` | `{...args}` | MyPreferences | E |
| `setMobilePreferences` | PATCH | `/user/{number}/preference/mobile-app` | `{...args}` | MyPreferences | E |
| `setConsPreferences` | PATCH | `/user/{number}/preference/access-to-cons-data` | `{...args}` | MyPreferences | E |
| `allowDataConsumption` | PATCH | `user/{number}/preference/access-to-cons-data/{ct}` | `{access_to_cons_data}` | Dashboard, MyPreferences, SuiviWidget | E |
| `getSponsorship` / `getParrainage` | GET | `/user/{number}/parrainage` | – | ParrainageContent | L |
| `storeParrainage` | **GET** (mutation) | `/user/{number}/initparrainage` | – | useInitParrainage | E (effet de bord) |
| `changePassword` | PATCH | `user/{number}/info/password` | `{oldPassword, password, password_confirmation}` | LoginInfoWidget | E |
| `updateEmail` | PATCH | `user/{number}/info/email` | `{email, code}` | UpdateEmailWidget | E |
| `sendEmailOtp` | GET | `user/{number}/send/email/code?email={email}` | – | UpdateEmailWidget | L (envoi de code) |
| `updateAdditionalPhone` | PATCH | `user/{number}/info/additional-phone` | `{additional_phone}` | PersoInfoWidget | E |
| `addUpdateCoContractant` | PATCH | `user/{number}/add-cocontractant` | `{co_name, co_email}` | PersoInfoWidget | E |
| `deleteCoContractant` | DELETE | `user/{number}/remove-cocontractant` | `{co_name, co_email}` | PersoInfoWidget | E |
| `getAdresses` | GET | `/user/adresses` | – | adresseService (non vérifié) | L |
| `getFicheInfoConseil` | GET | `/user/{number}/fiche-info-conseil` | – | AssuranceWidget, DownloadPaymentProofWidget | L |
| `getInsuranceCpvClient` | GET | `/user/{number}/insurance-cpv-client` | – | AssuranceWidget | L |
| `getSalesforceRequestQuestions` | GET | `salesforce-request-questions` (sans `{number}`) | – | ContactUs, Textarea | L |
| `getFaq` | **POST** | `faq` (sans corps) | – | SearchBar, Textarea, Layout | L |
| `faqSearch` | POST | `/faq` | `{keyword}` | SearchBar | L |
| `sendSalesforceRequest` | POST | `user/{number}/send-request-to-salesforce/{ct}` | `{reason_id, sub_reason_id, description}` | ContactUs, EnergyContract | E |
| `SendRequestToSalesforce` | POST | `/user/{number}/send-request-to-salesforce/{ct}` | `{reason_id, sub_reason_id, description, contract_termination_request, contract_termination_date, contract_termination_reason}` | Contact, EnergyContract | E |
| `changePower` | POST | `user/{number}/send-request-to-salesforce/{ct}` | `{reason_id: 11, sub_reason_id: 49, description: "Changement puissance", power_old, power_new}` | PowerChangeWidget | E |
| `getAdvice` | GET | `/user/{number}/advice/{ct}` | – | MesConseils | L |
| `getDPE` | GET | `user/{number}/dpe/{ct}` | – | DpeWidget | L |
| `getQuestionnary` | GET | `user/{number}/questionnary/{ct}` | – | QuestionsWidget, SuiviWidget | L |
| `getQuestionnaryPercentage` | GET | `user/{number}/questionnary-percentage/{ct}` | – | DpeWidget, QuestionsWidget, SuiviWidget | L |
| `UpdateQuestionnary` | PATCH | `user/{number}/questionnary/{ct}` | `{...args}` | QuestionsWidget | E |
| `isDisplayEcojoko` | GET (`mathod` typo) | `user/{number}/display-ecojoko/{ct}` | – | ServicesEco, Fantom, Login | L |
| `createEcojokoOrder` | GET (`mathod` typo) | `user/{number}/ecojoko-order/{ct}` | – | Ecojoko, Services | E (commande) |
| `chatbotUrl` | GET | `user/{number}/chatbot/url` | – | ChatbotWidget | L |

### 2.2 Résiliation et services Stripe / Neat

| Endpoint (hook) | Méthode | Chemin | Corps | Composant (heuristique) | Type |
|---|---|---|---|---|---|
| `getStripe` | GET | `/user/{number}/stripe` | – | non vérifié | L |
| `allStripe` | GET | `/user/{number}/stripe/all` | – | MesContrats, Contact | L |
| `CancelStripe` | POST | `/user/{number}/stripe/cancel` | `{sub_sched, reason, status, id_subscription, end_behavior, proration_behavior, ref_partner, phases, ...}` | StripeContracts | E |
| `RetractStripe` | POST | `/user/{number}/stripe/retract` | `{sub_sched, ref_partner, start_date, end_date, reason}` | StripeContracts, Contact | E |
| `getNeatCustomer` | GET | `user/{number}/billflow/neat/get-customer-info?customerRef=` | – | AssuranceWidget, NeatAssuranceWidget | L |
| `retractNeatSubscription` | POST | `user/{number}/billflow/neat/subscription/retract` | `{subscriptionId, reason, terminationDate}` | AssuranceWidget | E |
| `terminateNeatSubscription` | POST | `user/{number}/billflow/neat/subscription/terminate` | `{subscriptionId, reason, terminationDate}` | AssuranceWidget | E |
| `getNeatInvoice` | GET | `user/{number}/billflow/neat/invoice?invoiceId=` | – | AssuranceWidget | L |
| `getNeatEcheancier` | GET | `user/{number}/billflow/neat/echeancier` | – | NeatAssuranceWidget | L |
| `getNeatCpv` | GET | `user/{number}/billflow/neat/cpv` | – | AssuranceWidget | L |
| `sendNeatResiliationRequest` | POST | `user/{number}/billflow/neat/resiliation/request/{ct}` | `{description}` | Zt (heuristique) | E |

### 2.3 Facturation et paiements

| Endpoint (hook) | Méthode | Chemin | Corps | Composant (heuristique) | Type |
|---|---|---|---|---|---|
| `changeBillingAddress` | PATCH | `user/{number}/billing/billing-address/{ct}` | `{firstname, lastname, street_number, street, zip_code, city}` | PersoInfoWidget | E |
| `changeIban` | PATCH | `user/{number}/billing/iban/{ct}` | `{iban}` | BankInfoWidget | E |
| `changeBillingDay` | PATCH | `user/{number}/billing/billing-day` | `{billing_day}` | PaymentInfoWidget | E |
| `changeBillingSettlement` | PATCH | `user/{number}/billing/settlement-periodicity` | `{settlement_periodicity}` | PaymentInfoWidget | E |
| `setBillingAdress`, `setBillingDay`, `setIban`, `setSettlementPeriodicity` | PATCH | mêmes chemins que ci-dessus | `{...args}` | non utilisés (doublons) | E |
| `getEnergyChecks` | GET | `/user/{number}/billing/energy-checks` | – | Paiement | L |
| `getInvoices` | GET | `/user/{number}/billing/invoices/{ct}` | – | non utilisé (défini) | L |
| `getPayments` | GET | `/user/{number}/billing/payments/{ct}` | – | non utilisé (défini) | L |
| `getInvoicesPayments` | GET | `/user/{number}/billing/invoices-payments/{ct}` | – | Paiement | L |
| `getContractBallance` | GET | `/user/{number}/billing/balance/{ct}` | – | non utilisé (défini) | L |
| `getTotalBalance` | GET | `/user/{number}/billing/balance/total/{ct}` | – | Paiement | L |
| `getPaymentGraph` | GET | `/user/{number}/billing/echeancier/graphe/{ct}` | – | EcheancierWidget | L |
| `getAllPayments` | GET | `/user/{number}/billing/all-payments` | – | non utilisé (défini) | L |
| `getAllInvoices` | GET | `/user/{number}/billing/all-invoices` | – | RelevesWidget | L |
| `getBalanceDetails` | GET | `/user/{number}/billing/balance-details` | – | RelevesWidget | L |
| `TrackingActivation` | GET | `user/{number}/billing/tracking-activation/{ct}` | – | Dashboard, PercentageConsumptionWidget | L |
| `invoice` | GET (PDF) | `user/{number}/document/invoice/{ct}/{invoiceNbr}` | – | non utilisé (défini) | L |
| `downloadInvoice` | GET | `/user/{number}/document/invoice/{ct}/{invoice_id}` | – | RelevesWidget, DownloadPaymentProofWidget | L |
| `lastInvoice` | GET (PDF) | `user/{number}/document/last-invoice/{ct}` | – | DownloadPaymentProofWidget | L |
| `echeancier` / `downloadEcheancier` | GET (PDF) | `user/{number}/document/echeancier/{ct}` | – | Paiement, DownloadPaymentProofWidget | L |
| `justificatif` / `getJustificatifDocument` | GET (PDF) | `user/{number}/document/justificatif/{ct}` | – | JustificationWidget, DownloadAddressProofWidget | L |
| `getCpvDocument` | GET | `/user/{number}/document/cpv` | – | CpvWidget | L |
| `getCgvDocument` | GET | `/user/{number}/document/cgv/{ct}` | – | CgvWidget | L |
| `getPriceListSheet` | GET | `/user/{number}/document/list-grilles-tarifaires/{ct}` | – | PriceSheetWidget | L |
| `downloadPriceListSheet` | **POST** | `/user/{number}/document/grille-tarifaire/{ct}` | `{offer_code, date}` | PriceSheetWidget, EnergyContract | L (POST en lecture) |

### 2.4 Consommation et production (voir section 4)

| Endpoint (hook) | Méthode | Chemin | Corps | Composant (heuristique) | Type |
|---|---|---|---|---|---|
| `lastSixConsumption` | GET | `user/{number}/consumption/six-months/{ct}` | – | LastConsumptionWidget | L |
| `percentageConsumption` | GET | `user/{number}/consumption/last-month/{ct}` | – | PercentageConsumptionWidget | L |
| `getGlanceConsumption` | GET | `user/{number}/glance-previous-consumption/{ct}` | – | LastMonthStatsWidget | L |
| `getKwhEuroDataConsumption` | GET | `user/{number}/consumption/kwh/{ct}/data` | – | KwhConsumptionWidget, ComparaisonWidget | L |
| `getKwhHoursConsumption` | **POST** | `user/{number}/consumption/kwh/{ct}/hours` | `{date, pdl}` | KwhConsumptionWidget | L (POST en lecture) |
| `getCo2DataConsumption` | **GET** (mutation) | `user/{number}/consumption/co2/{ct}/data` | – | KwhConsumptionWidget | L |
| `getCo2HoursConsumption` | POST | `user/{number}/consumption/co2/{ct}/hours` | `{date}` | KwhConsumptionWidget | L |
| `getEuroHoursConsumption` | POST | `user/{number}/consumption/euro/{ct}/hours` | `{date}` | KwhConsumptionWidget | L |
| `getHouseConsumption` | GET | `user/{number}/house-consumption/{ct}` | – | ConsumptionLevelWidget | L |
| `getThreshold` | GET | `user/{number}/consumption/threshold/{ct}` | – | ConsumptionGraphWidgt | L |
| `getPowerYearsConsumption` | POST | `user/{number}/consumption/power/{ct}/years` | `{...args}` | PowerConsumptionWidget | L (POST en lecture) |
| `getPowerMonthsConsumption` | POST | `user/{number}/consumption/power/{ct}/months` | `{...args}` | PowerConsumptionWidget | L (POST en lecture) |
| `getPowerDaysConsumption` | POST | `user/{number}/consumption/power/{ct}/days` | `{...args}` | PowerConsumptionWidget | L (POST en lecture) |
| `getUsageConsumption` | GET | `user/{number}/usage-consumption/{ct}` | – | UsageWidget | L |
| `getPeriodConsumption` | **POST** (query) | `user/{number}/period-consumption/{ct}` | – | CadranWidget | L (POST en lecture) |
| `getPeriodConsumptionByDate` | POST | `user/{number}/period-consumption/{ct}` | `{startDate, endDate}` | CadranWidget | L (POST en lecture) |
| `getConsoCadran` | **GET** (mutation) | `user/{number}/get-conso-cadran/{ct}?date_debut={from}&date_fin={to}` | – | CadranWidget (dates dd/mm/yyyy) | L |
| `downloadConsumption` | GET | `user/{number}/consumption/download/{ct}?dateRange={from}-{to}` | – | DownloadConsumptionWidget | L |
| `lastSixProduction` | GET | `user/{number}/solar/six-months/{ct}` | – | SolarProductionWidget (Dashboard) | L |

### 2.5 Endpoints définis mais inactifs ou sans effet

- Cagnotte : `activeCagnotteOperation`, `cagnotteClientInfo`, `cagnotteUnlockAmount`, `cagnotteParticipate` utilisent `queryFn: cagnotteDisabled`, qui renvoie « Cagnotte désactivée » sans appel réseau.
- Documents AXA et Neat statiques : `DocAxaStatic`, `downloadAxadoc`, `DocNeatIpid`, `DocNeatFic`, `DocNeatCgv` pointent vers des PDF `/documents/...` ou `/public_document/...` servis par l'hôte. Leur base est `"undefined"` (voir section 0).
- Endpoints de `billingService` marqués « doublons » (`setBillingAdress`, etc.) : ils ont le même chemin que les `change*`.
- `getContract` : le hook `useGetContractQuery` est utilisé dans `AccountInfo`.

### 2.6 Appels directs hors RTK

| Appel | Méthode | URL | Source |
|---|---|---|---|
| Désenregistrement notifications | DELETE | `https://bo-api.ohm-energie.com/notifications/unregister` | `logoutUser`, hook de notifications |
| Enregistrement notifications (3 essais avec backoff) | POST | `https://bo-api.ohm-energie.com/notifications` | `{email, deviceId, fcmToken, clientReferences}` |
| Streaming temps réel | WebSocket / polling | `https://bo-api.ohm-energie.com/streaming` (Socket.IO) | événement `register` avec `{userId, userType: "customer"}` |
| Callback réseau social | GET | `https://espace-client.ohm-energie.com/api/callback/{provider}?token=` | `authenticateUserViaProvider` |
| Notifications Firebase | (Google) | `getEndpoint(appConfig)` | non lié à Ohm |

## 3. Routes du SPA (react-router)

| Chemin | Composant | Ce que la page montre (hypothèse) |
|---|---|---|
| `/` | Dashboard (titre « Accueil ») | Tableau de bord : consommation récente, solde, production solaire, notifications |
| `/mon-compte` | Compte | Informations personnelles, mot de passe, préférences de communication et alertes, co-contractant, téléphone |
| `/mes-contrats` | MesContrats (« Documents & Contrats ») | Contrats, documents (CGV, CPV, grilles tarifaires, justificatifs), abonnements Stripe et Neat |
| `/mes-paiements` | Paiement (« Mes factures & paiements ») | Factures, paiements, échéancier, solde, RIB et périodicité de règlement |
| `/suivi-consommation` | Consumption (« Mon suivi conso ») | Graphiques kWh, €, CO2, puissance, cadran horaire, téléchargement des données |
| `/cagnotte` | CagnottePage | Cagnotte énergie (fonctionnalité désactivée côté code) |
| `/parrainage` | ParrainagePage | Parrainage (code, filleuls) |
| `/je-demenage` | DemenagePage | Démarche de déménagement |
| `/services-economies` | ServicesEco (« Services & équipements ») | Services : Ecojoko, changement de puissance, équipements |
| `/mes-conseils` | MesConseils | Conseils personnalisés (`advice`) |
| `/contacts` (alias `/demande`) | Contact (« Besoin d'aide? ») | Formulaire de demande Salesforce, résiliation, FAQ |
| `/login` | Login | Connexion (e-mail ou référence client + mot de passe, réseaux sociaux) |
| `/recuperation-mdp` | RecuperationMdp | Réinitialisation du mot de passe via token |
| `/premiere-connexion` | PremiereConnexion | Définir le mot de passe à la première connexion (token en query) |
| `/fantom` | Fantom | Mode impersonation (`token` et `email` en query, appel `access-ghost`) |
| `/mentions-legales` | MentionLegale | Mentions légales |
| `/politique-de-confidentialite` | PolitiqueConf | Politique de confidentialité |
| `*` | NotFoundPage | Page 404 |

Les routes `/` à `/contacts` sont listées dans le tableau de navigation (`routes`) avec `isSidebar: true`.

## 4. Endpoints les plus pertinents pour les données de consommation

1. `GET user/{number}/consumption/six-months/{ct}` (`lastSixConsumption`) : historique 6 mois, utilisé sur le tableau de bord.
2. `GET user/{number}/consumption/last-month/{ct}` (`percentageConsumption`) : part du mois en cours.
3. `GET user/{number}/glance-previous-consumption/{ct}` (`getGlanceConsumption`) : résumé du mois précédent.
4. `GET user/{number}/consumption/kwh/{ct}/data` (`getKwhEuroDataConsumption`) : données kWh et € agrégées.
5. `POST user/{number}/consumption/kwh/{ct}/hours` (`getKwhHoursConsumption`), corps `{date, pdl}` où `date` est au format `dd/mm/yyyy` (veille, `getTodayMinusOne()`) : courbe horaire.
6. `POST user/{number}/consumption/{euro,co2}/{ct}/hours` et `GET .../co2/{ct}/data` : euros et CO2 horaires.
7. `POST user/{number}/consumption/power/{ct}/{years,months,days}` (corps `{...args}`) : puissance par année, mois ou jour.
8. `POST user/{number}/period-consumption/{ct}` (corps `{startDate, endDate}`) : consommation sur une période.
9. `GET user/{number}/get-conso-cadran/{ct}?date_debut=dd/mm/yyyy&date_fin=dd/mm/yyyy` : cadran (heures creuses/pleines).
10. `GET user/{number}/consumption/download/{ct}?dateRange=from-to` : export des données.
11. `GET user/{number}/consumption/threshold/{ct}`, `house-consumption/{ct}`, `usage-consumption/{ct}` : seuils, comparaison avec des logements similaires, usages.
12. `PATCH user/{number}/preference/access-to-cons-data/{ct}` (`allowDataConsumption`) : consentement à l'accès aux données de consommation (prérequis du compteur Linky).

Les appels `consumption/*` et `period-consumption` sont exemptés de la règle « mutation bloquée en mode fantôme » dans `baseQueryWithReauth`.

## 5. Points incertains et remarques

- **Cookie `_token`** : son attribut `HttpOnly` et son domaine ne sont pas visibles dans le bundle. Si le cookie était `HttpOnly`, `getEcSessionToken()` renverrait `null` et l'en-tête `Authorization` ne serait pas envoyé à bo-api. La version déployée doit être vérifiée (réponse réelle de `/api/login`).
- **Format exact des réponses** : seules les propriétés lues par le code sont connues. Aucune réponse réelle n'a été observée.
- **Valeur de `ct`** : le format du numéro de contrat (`contract_nbr`) n'est pas déterminé statiquement. Il vient de `body.user.currentContract` ou de `elec_contracts`/`gaz_contracts`.
- **Requêtes POST en lecture** : plusieurs endpoints de consommation sont POST alors qu'ils semblent en lecture seule (`hours`, `power`, `period-consumption`, `faq`, `grille-tarifaire`). Probablement pour transmettre des dates dans le corps.
- **Mutations en GET** : `storeParrainage` (`/initparrainage`), `getCo2DataConsumption`, `getConsoCadran`, `getContracts` (SSE). `storeParrainage` a un effet de bord ; il est appelé par le hook `useInitParrainage` (point d'appel dans l'UI non vérifié).
- **Typos** : `mathod:"GET"` au lieu de `method` (`isDisplayEcojoko`, `createEcojokoOrder`) ; `header:` au lieu de `headers:` dans la plupart des endpoints. Ces erreurs sont sans effet connu car la méthode GET est la valeur par défaut.
- **Contrôle `auth/login`** : la liste d'exemptions de `baseQueryWithReauth` contient `"auth/login"` et `"auth/logout"`, mais la vérification se fait sur les segments d'URL (`url.split("/")`). Ces valeurs à deux segments ne correspondent donc jamais. Le blocage en mode fantôme s'applique peut-être à `/login` et `/logout/{number}`. Comportement à vérifier.
- **Base `"undefined"`** pour les documents AXA et Neat (`API_URL_DOC = "undefined"`) : URL relative probablement cassée. Non vérifié.
- **Clé de chiffrement en dur** : `encryptTransform({secretKey: "<clé masquée>"})` pour la persistance Redux (IndexedDB). Cette clé est publique puisque livrée au navigateur. Elle n'apporte donc pas de confidentialité réelle.
- **Mode fantôme (impersonation)** : `/fantom` reçoit `token` et `email` dans l'URL, puis appelle `/access-ghost/{token}/{email}`. Le SPA bloque les mutations en mode fantôme, mais ce blocage est uniquement côté client.
- **Endpoints non utilisés** : plusieurs hooks sont définis sans composant identifié (`getInvoices`, `getPayments`, `getAllPayments`, `invoice`, `getContractBallance`, `getUserContractsInfo`, `getStripe`). Ils peuvent servir à des pages non trouvées par l'analyse.
- **Composants** : les noms de composants sont déduits par heuristique à partir du code minifié. Ils sont à confirmer dans le code source non minifié si disponible.
- **Fichiers non téléchargés** : les chunks lazy (`/assets/...`) n'ont pas été récupérés. Ils peuvent contenir d'autres endpoints ou composants.
