"""Erreurs de l'API v1, au format RFC 9457 (application/problem+json)."""

from __future__ import annotations

from typing import Any

PROBLEM_TYPE_PREFIX = "urn:ohm-scraper:problem:"


class ApiProblem(Exception):
    """Erreur HTTP à renvoyer au client. ``detail`` ne contient jamais de donnée personnelle."""

    def __init__(
        self,
        status: int,
        slug: str,
        title: str,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.slug = slug
        self.title = title
        self.detail = detail
        self.headers = dict(headers or {})

    def body(self) -> dict[str, Any]:
        return {
            "type": PROBLEM_TYPE_PREFIX + self.slug,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
        }


def invalid_parameter(detail: str) -> ApiProblem:
    return ApiProblem(400, "invalid-parameter", "Paramètre invalide", detail)


def unprocessable(slug: str, title: str, detail: str) -> ApiProblem:
    return ApiProblem(422, slug, title, detail)


def not_found(detail: str) -> ApiProblem:
    return ApiProblem(404, "not-found", "Ressource introuvable", detail)


def upstream_error(detail: str) -> ApiProblem:
    return ApiProblem(502, "upstream-error", "Erreur amont", detail)


def unavailable(detail: str) -> ApiProblem:
    return ApiProblem(503, "unavailable", "Service indisponible", detail)
