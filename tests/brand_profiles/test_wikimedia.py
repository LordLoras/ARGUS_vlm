from __future__ import annotations

import httpx
import pytest

from ad_classifier.brand_profiles.wikimedia import (
    WikimediaBrandProfileClient,
    normalize_profile_name,
)


def test_normalize_profile_name_removes_legal_suffixes_and_symbols():
    assert normalize_profile_name("Acme, Inc.™") == "acme"


def test_wikimedia_client_builds_company_context_from_wikipedia_and_wikidata():
    transport = httpx.MockTransport(_wikimedia_handler)
    http_client = httpx.Client(transport=transport, base_url="https://example.test")
    client = WikimediaBrandProfileClient(
        user_agent="ARGUS tests",
        http_client=http_client,
        cache_days=30,
        max_parent_depth=2,
    )

    profile = client.fetch("Jeep")

    assert profile.normalized_name == "jeep"
    assert profile.display_name == "Jeep"
    assert profile.wikidata_qid == "Q43193"
    assert profile.parent_companies == ["Stellantis"]
    assert profile.corporate_chain == ["Stellantis", "Exor"]
    assert profile.industries == ["automotive industry"]
    assert profile.official_website == "https://www.jeep.com/"
    assert profile.key_metrics["employees"] == "10,000"
    assert profile.key_metrics["revenue"] == "189,000,000 US dollar (2023)"
    assert any(step.action == "candidate" for step in profile.lookup_steps)
    assert profile.source_json["wikidata_claim_counts"]["P749"] == 1

    http_client.close()


def test_wikimedia_client_rejects_snippet_only_name_matches():
    transport = httpx.MockTransport(_snippet_only_handler)
    http_client = httpx.Client(transport=transport, base_url="https://example.test")
    client = WikimediaBrandProfileClient(
        user_agent="ARGUS tests",
        http_client=http_client,
    )

    with pytest.raises(ValueError, match="no relevant Wikimedia profile"):
        client.fetch("Prillaman")

    http_client.close()


def _wikimedia_handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "en.wikipedia.org" and request.url.path == "/w/api.php":
        if request.url.params.get("list") == "search":
            return _json(
                request,
                {
                    "query": {
                        "search": [
                            {
                                "title": "Jeep",
                                "pageid": 123,
                                "snippet": "Jeep is an American automobile brand.",
                            },
                            {
                                "title": "Jeep (song)",
                                "pageid": 999,
                                "snippet": "song",
                            },
                        ]
                    }
                },
            )
        return _json(
            request,
            {
                "query": {
                    "pages": {
                        "123": {
                            "title": "Jeep",
                            "pageid": 123,
                            "fullurl": "https://en.wikipedia.org/wiki/Jeep",
                            "pageprops": {"wikibase_item": "Q43193"},
                        }
                    }
                }
            },
        )
    if request.url.host == "en.wikipedia.org" and request.url.path.endswith("/summary/Jeep"):
        return _json(
            request,
            {
                "title": "Jeep",
                "description": "American automobile brand",
                "extract": "Jeep is an American automobile brand now owned by Stellantis.",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Jeep"}},
            },
        )
    if request.url.host == "www.wikidata.org" and request.url.path.endswith("/Q43193.json"):
        return _json(request, _entity("Q43193", "Jeep", "American automobile brand", _jeep_claims()))
    if request.url.host == "www.wikidata.org" and request.url.path.endswith("/Q9730.json"):
        return _json(
            request,
            _entity("Q9730", "Stellantis", "multinational automotive manufacturing corporation", {
                "P127": [_item_claim("Q900")],
            }),
        )
    if request.url.host == "www.wikidata.org" and request.url.path.endswith("/Q900.json"):
        return _json(request, _entity("Q900", "Exor", "holding company", {}))
    if request.url.host == "www.wikidata.org" and request.url.path == "/w/api.php":
        ids = request.url.params.get("ids", "").split("|")
        labels = {
            "Q9730": "Stellantis",
            "Q190117": "automotive industry",
            "Q49239": "Toledo",
            "Q30": "United States",
            "Q81965": "Willys-Overland",
            "Q900": "Exor",
            "Q4917": "US dollar",
        }
        return _json(
            request,
            {
                "entities": {
                    qid: {"labels": {"en": {"value": labels.get(qid, qid)}}}
                    for qid in ids
                    if qid
                }
            },
        )
    return httpx.Response(404, request=request, json={"error": "not mocked"})


def _snippet_only_handler(request: httpx.Request) -> httpx.Response:
    if (
        request.url.host == "en.wikipedia.org"
        and request.url.path == "/w/api.php"
        and request.url.params.get("list") == "search"
    ):
        return _json(
            request,
            {
                "query": {
                    "search": [
                        {
                            "title": "Star Wars: Episode I - The Phantom Menace",
                            "pageid": 50793,
                            "snippet": "News and Past Events - Prillaman.net.",
                        },
                        {
                            "title": "Stanley Furniture",
                            "pageid": 25058748,
                            "snippet": "Glenn Prillaman resigned from his role as CEO.",
                        },
                    ]
                }
            },
        )
    if (
        request.url.host == "www.wikidata.org"
        and request.url.path == "/w/api.php"
        and request.url.params.get("action") == "wbsearchentities"
    ):
        return _json(
            request,
            {
                "search": [
                    {
                        "id": "Q165713",
                        "label": "Star Wars: Episode I - The Phantom Menace",
                        "description": "1999 film directed by George Lucas",
                    }
                ]
            },
        )
    return httpx.Response(404, request=request, json={"error": "not mocked"})


def _jeep_claims() -> dict:
    return {
        "P749": [_item_claim("Q9730")],
        "P452": [_item_claim("Q190117")],
        "P159": [_item_claim("Q49239")],
        "P17": [_item_claim("Q30")],
        "P112": [_item_claim("Q81965")],
        "P856": [_string_claim("https://www.jeep.com/")],
        "P571": [_time_claim("+1943-01-01T00:00:00Z")],
        "P1128": [_quantity_claim("+10000")],
        "P2139": [_quantity_claim("+189000000", unit="Q4917", year="+2023-01-01T00:00:00Z")],
    }


def _entity(qid: str, label: str, description: str, claims: dict) -> dict:
    return {
        "entities": {
            qid: {
                "id": qid,
                "labels": {"en": {"value": label}},
                "descriptions": {"en": {"value": description}},
                "claims": claims,
            }
        }
    }


def _item_claim(qid: str) -> dict:
    return {
        "mainsnak": {
            "datavalue": {
                "value": {"entity-type": "item", "id": qid},
            }
        }
    }


def _string_claim(value: str) -> dict:
    return {"mainsnak": {"datavalue": {"value": value}}}


def _time_claim(value: str) -> dict:
    return {"mainsnak": {"datavalue": {"value": {"time": value}}}}


def _quantity_claim(amount: str, *, unit: str | None = None, year: str | None = None) -> dict:
    claim = {
        "mainsnak": {
            "datavalue": {
                "value": {
                    "amount": amount,
                    "unit": f"http://www.wikidata.org/entity/{unit}" if unit else "1",
                }
            }
        }
    }
    if year:
        claim["qualifiers"] = {"P585": [_time_claim(year)["mainsnak"]]}
    return claim


def _json(request: httpx.Request, payload: dict) -> httpx.Response:
    return httpx.Response(200, request=request, json=payload)
