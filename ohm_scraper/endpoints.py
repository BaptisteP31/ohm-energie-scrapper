"""Catalogue des endpoints de l'espace client Ohm Énergie.

Toutes les routes sont relatives à ``https://espace-client.ohm-energie.com/api``.
Seuls des endpoints de lecture sont décrits ici. Les endpoints qui modifient des
données sont listés séparément dans :data:`EXCLUDED_ENDPOINTS`, avec la raison de
leur exclusion : ils ne doivent jamais être appelés par ce projet.

``{number}`` est le numéro client (``body.user.customer_nbr``) et ``{ct}`` le
numéro de contrat sélectionné (``body.user.currentContract``).
"""

from __future__ import annotations

from dataclasses import dataclass


class EndpointError(ValueError):
    """Endpoint inconnu ou paramètre de chemin manquant."""


@dataclass(frozen=True)
class Endpoint:
    """Description d'un endpoint de lecture.

    ``name`` est le nom court et stable utilisé par la CLI (``--only``) et comme
    nom de fichier dans ``data/<horodatage>/<name>.json``.
    """

    name: str
    method: str
    template: str
    category: str
    description: str
    body: str = ""

    def path(self, number: str | None, ct: str | None) -> str:
        """Construit le chemin concret, en vérifiant que les paramètres existent."""
        if "{number}" in self.template and not number:
            raise EndpointError(
                f"{self.name} : numéro client inconnu (OHM_CUSTOMER_NUMBER ou réponse de /login)."
            )
        if "{ct}" in self.template and not ct:
            raise EndpointError(
                f"{self.name} : numéro de contrat inconnu (OHM_CT ou réponse de /login)."
            )
        return self.template.replace("{number}", number or "").replace("{ct}", ct or "")


# Endpoints GET appelés par `dump` et par `discover` (38 routes vérifiées HTTP 200).
DUMP_ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint("dashboard", "GET", "user/{number}/dashboard/{ct}", "Compte", "Tableau de bord"),
    Endpoint("account", "GET", "user/{number}/account/{ct}", "Compte", "Fiche compte du contrat"),
    Endpoint("contracts", "GET", "user/{number}/contracts", "Compte", "Liste des contrats"),
    Endpoint("preferences", "GET", "user/{number}/preference/{ct}", "Compte", "Préférences"),
    Endpoint("addresses", "GET", "user/adresses", "Compte", "Adresses"),
    Endpoint(
        "advice_sheet", "GET", "user/{number}/fiche-info-conseil", "Compte", "Fiche info conseil"
    ),
    Endpoint(
        "insurance_cpv",
        "GET",
        "user/{number}/insurance-cpv-client",
        "Compte",
        "Assurance CPV client",
    ),
    Endpoint(
        "ecojoko_display",
        "GET",
        "user/{number}/display-ecojoko/{ct}",
        "Compte",
        "Affichage Ecojoko (indicateur)",
    ),
    Endpoint(
        "salesforce_questions",
        "GET",
        "salesforce-request-questions",
        "Référentiel",
        "Motifs de demande (référentiel)",
    ),
    Endpoint(
        "invoices", "GET", "user/{number}/billing/invoices/{ct}", "Facturation", "Factures du contrat"
    ),
    Endpoint(
        "invoices_payments",
        "GET",
        "user/{number}/billing/invoices-payments/{ct}",
        "Facturation",
        "Factures et paiements",
    ),
    Endpoint(
        "payments", "GET", "user/{number}/billing/payments/{ct}", "Facturation", "Paiements du contrat"
    ),
    Endpoint(
        "all_payments", "GET", "user/{number}/billing/all-payments", "Facturation", "Tous les paiements"
    ),
    Endpoint(
        "all_invoices", "GET", "user/{number}/billing/all-invoices", "Facturation", "Toutes les factures"
    ),
    Endpoint(
        "balance", "GET", "user/{number}/billing/balance/{ct}", "Facturation", "Solde du contrat"
    ),
    Endpoint(
        "balance_total",
        "GET",
        "user/{number}/billing/balance/total/{ct}",
        "Facturation",
        "Solde total",
    ),
    Endpoint(
        "balance_details", "GET", "user/{number}/billing/balance-details", "Facturation", "Détail des soldes"
    ),
    Endpoint(
        "payment_schedule_graph",
        "GET",
        "user/{number}/billing/echeancier/graphe/{ct}",
        "Facturation",
        "Graphe d'échéancier",
    ),
    Endpoint(
        "energy_checks", "GET", "user/{number}/billing/energy-checks", "Facturation", "Contrôles énergie"
    ),
    Endpoint(
        "tracking_activation",
        "GET",
        "user/{number}/billing/tracking-activation/{ct}",
        "Facturation",
        "Activation du suivi",
    ),
    Endpoint("cpv_document", "GET", "user/{number}/document/cpv", "Documents", "CPV (métadonnées)"),
    Endpoint(
        "cgv_document", "GET", "user/{number}/document/cgv/{ct}", "Documents", "CGV (métadonnées)"
    ),
    Endpoint(
        "price_sheets",
        "GET",
        "user/{number}/document/list-grilles-tarifaires/{ct}",
        "Documents",
        "Liste des grilles tarifaires",
    ),
    Endpoint(
        "neat_schedule", "GET", "user/{number}/billflow/neat/echeancier", "Assurance Neat", "Échéancier Neat"
    ),
    Endpoint("neat_cpv", "GET", "user/{number}/billflow/neat/cpv", "Assurance Neat", "CPV Neat"),
    Endpoint("advice", "GET", "user/{number}/advice/{ct}", "Conseils", "Conseils personnalisés"),
    Endpoint("dpe", "GET", "user/{number}/dpe/{ct}", "Conseils", "DPE"),
    Endpoint("questionnaire", "GET", "user/{number}/questionnary/{ct}", "Conseils", "Questionnaire"),
    Endpoint(
        "questionnaire_percentage",
        "GET",
        "user/{number}/questionnary-percentage/{ct}",
        "Conseils",
        "Avancement du questionnaire",
    ),
    Endpoint(
        "consumption_six_months",
        "GET",
        "user/{number}/consumption/six-months/{ct}",
        "Consommation",
        "Consommation 6 mois",
    ),
    Endpoint(
        "consumption_last_month",
        "GET",
        "user/{number}/consumption/last-month/{ct}",
        "Consommation",
        "Consommation dernier mois",
    ),
    Endpoint(
        "consumption_glance",
        "GET",
        "user/{number}/glance-previous-consumption/{ct}",
        "Consommation",
        "Résumé du mois précédent",
    ),
    Endpoint(
        "consumption_kwh_data",
        "GET",
        "user/{number}/consumption/kwh/{ct}/data",
        "Consommation",
        "kWh et euros agrégés",
    ),
    Endpoint(
        "house_consumption",
        "GET",
        "user/{number}/house-consumption/{ct}",
        "Consommation",
        "Comparaison logements similaires",
    ),
    Endpoint(
        "consumption_threshold",
        "GET",
        "user/{number}/consumption/threshold/{ct}",
        "Consommation",
        "Seuils de consommation",
    ),
    Endpoint(
        "usage_consumption",
        "GET",
        "user/{number}/usage-consumption/{ct}",
        "Consommation",
        "Usages",
    ),
    Endpoint(
        "solar_six_months",
        "GET",
        "user/{number}/solar/six-months/{ct}",
        "Production",
        "Production solaire 6 mois",
    ),
)

# Endpoints de lecture supplémentaires utilisés par la commande `consumption`.
# Ce sont des POST mais ils ne modifient rien : le corps ne transporte que des dates
# (et le PDL pour la courbe horaire).
CONSUMPTION_ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint(
        "consumption_hourly",
        "POST",
        "user/{number}/consumption/kwh/{ct}/hours",
        "Consommation",
        "Courbe horaire kWh pour une date",
        body="{date: dd/mm/yyyy, pdl}",
    ),
    Endpoint(
        "consumption_power_days",
        "POST",
        "user/{number}/consumption/power/{ct}/days",
        "Consommation",
        "Puissance par jour sur une période",
        body="{startDate, endDate}",
    ),
    Endpoint(
        "consumption_power_months",
        "POST",
        "user/{number}/consumption/power/{ct}/months",
        "Consommation",
        "Puissance par mois sur une période",
        body="{startDate, endDate}",
    ),
    Endpoint(
        "consumption_power_years",
        "POST",
        "user/{number}/consumption/power/{ct}/years",
        "Consommation",
        "Puissance par an sur une période",
        body="{startDate, endDate}",
    ),
    Endpoint(
        "consumption_period",
        "POST",
        "user/{number}/period-consumption/{ct}",
        "Consommation",
        "Consommation sur une période",
        body="{startDate, endDate}",
    ),
)

# Ancien nom utilisé par discover.py (une seule route POST de lecture).
HOURLY_ENDPOINT = CONSUMPTION_ENDPOINTS[0]

ALL_ENDPOINTS: tuple[Endpoint, ...] = DUMP_ENDPOINTS + CONSUMPTION_ENDPOINTS
ENDPOINTS_BY_NAME: dict[str, Endpoint] = {endpoint.name: endpoint for endpoint in ALL_ENDPOINTS}

# Endpoints volontairement non appelés : (méthode, chemin, raison).
EXCLUDED_ENDPOINTS: tuple[tuple[str, str, str], ...] = (
    ("PATCH / DELETE", "tous les endpoints PATCH et DELETE de api_map.md", "mutation (exclusion stricte)"),
    ("DELETE", "logout/{number}", "déconnexion (exclusion stricte)"),
    ("GET", "user/{number}/initparrainage", "parrainage, effet de bord (exclusion stricte)"),
    ("GET", "user/{number}/parrainage", "parrainage (exclusion stricte)"),
    ("GET", "user/{number}/chatbot/url", "chatbot (exclusion stricte)"),
    ("GET", "callback/{provider}", "callback réseau social (exclusion stricte)"),
    ("GET", "user/{number}/send/email/code", "envoie un code par e-mail (effet de bord)"),
    ("GET", "user/{number}/ecojoko-order/{ct}", "commande Ecojoko (mutation)"),
    ("GET", "user/{number}/stripe", "abonnements Stripe : incertain, exclusion « subscription »"),
    ("GET", "user/{number}/stripe/all", "abonnements Stripe : incertain, exclusion « subscription »"),
    ("POST", "user/{number}/stripe/cancel", "résiliation d'abonnement (mutation)"),
    ("POST", "user/{number}/stripe/retract", "rétractation d'abonnement (mutation)"),
    ("POST", "user/{number}/billflow/neat/subscription/retract", "rétractation Neat (mutation)"),
    ("POST", "user/{number}/billflow/neat/subscription/terminate", "résiliation Neat (mutation)"),
    ("POST", "user/{number}/billflow/neat/resiliation/request/{ct}", "demande de résiliation (mutation)"),
    ("POST", "user/{number}/send-request-to-salesforce/{ct}", "crée une demande Salesforce (mutation)"),
    ("GET", "user/{number}/billflow/neat/get-customer-info", "paramètre customerRef non documenté"),
    ("GET", "user/{number}/billflow/neat/invoice", "paramètre invoiceId requis, non disponible"),
    ("POST", "faq", "POST hors consommation (non lecture certifiée)"),
    ("POST", "user/{number}/document/grille-tarifaire/{ct}", "POST hors consommation (corps offer_code)"),
    (
        "POST",
        "user/{number}/consumption/co2/{ct}/hours",
        "POST de lecture, mais corps {date} seul : hors allowlist",
    ),
    (
        "POST",
        "user/{number}/consumption/euro/{ct}/hours",
        "POST de lecture, mais corps {date} seul : hors allowlist",
    ),
    ("GET", "user/{number}/get-conso-cadran/{ct}", "GET utilisé comme mutation côté SPA : incertain"),
    ("GET", "user/{number}/consumption/co2/{ct}/data", "GET utilisé comme mutation côté SPA : incertain"),
    ("GET", "user/{number}/consumption/download/{ct}", "export de fichier, format de dateRange non documenté"),
    ("GET", "contracts-new", "flux SSE, non JSON"),
    ("GET", "user/{number}/document/invoice/{ct}/{id}", "PDF binaire, identifiant requis"),
    ("GET", "user/{number}/document/last-invoice/{ct}", "PDF binaire"),
    ("GET", "user/{number}/document/echeancier/{ct}", "PDF binaire"),
    ("GET", "user/{number}/document/justificatif/{ct}", "PDF binaire"),
    (
        "POST",
        "login, register, forget-password, recover-reference, first-connection/*",
        "authentification / envoi d'e-mails",
    ),
    ("GET", "refresh", "utilisé seulement en cas d'expiration du jeton"),
    ("GET", "get-contracts/{token}, access-ghost/{token}/{email}", "jetons d'authentification / impersonation"),
    ("—", "bo-api (notifications, streaming Socket.IO)", "hors espace client, exclusion stricte"),
    ("—", "cagnotte/*", "fonctionnalité désactivée côté code (aucun appel réseau)"),
    ("—", "documents AXA / Neat statiques", "base d'URL « undefined », non appelés"),
)


def get_endpoint(name: str) -> Endpoint:
    """Retourne l'endpoint portant ce nom, ou lève :class:`EndpointError`."""
    try:
        return ENDPOINTS_BY_NAME[name]
    except KeyError as exc:
        known = ", ".join(sorted(ENDPOINTS_BY_NAME))
        raise EndpointError(f"endpoint inconnu : {name!r}. Noms disponibles : {known}") from exc


def render_endpoint_list(endpoints: tuple[Endpoint, ...] = DUMP_ENDPOINTS) -> str:
    """Rendu texte stable pour ``dump --list`` (aucun accès réseau, aucun .env)."""
    lines = []
    for endpoint in endpoints:
        lines.append(f"{endpoint.name:<28} {endpoint.category:<16} {endpoint.description}")
    return "\n".join(lines)
