from __future__ import annotations

from datetime import timedelta

from ad_classifier.db.connection import apply_migrations, open_database
from ad_classifier.db.repositories.brand_profiles import BrandProfileRepository
from ad_classifier.models.ads import utc_now
from ad_classifier.models.brand_profiles import BrandProfile, BrandProfileLookupStep


def test_brand_profile_repository_round_trips_structured_profile(tmp_path):
    db_path = tmp_path / "profiles.db"
    conn = open_database(db_path)
    try:
        apply_migrations(conn)
        now = utc_now()
        profile = BrandProfile(
            normalized_name="jeep",
            query_name="Jeep",
            display_name="Jeep",
            description="American automobile brand",
            wikipedia_title="Jeep",
            wikipedia_url="https://en.wikipedia.org/wiki/Jeep",
            wikidata_qid="Q43193",
            parent_companies=["Stellantis"],
            owners=["Stellantis"],
            corporate_chain=["Stellantis", "Exor"],
            industries=["automotive industry"],
            official_website="https://www.jeep.com/",
            headquarters=["Toledo"],
            countries=["United States"],
            inception="1943",
            founded_by=["Willys-Overland"],
            subsidiaries=["Jeep Europe"],
            key_metrics={"employees": "10,000", "revenue": ["1,000 US dollar (2023)"]},
            lookup_steps=[
                BrandProfileLookupStep(
                    source="wikipedia",
                    action="search",
                    query="Jeep",
                    result_count=3,
                )
            ],
            source_urls=["https://en.wikipedia.org/wiki/Jeep"],
            source_json={"wikidata_claim_counts": {"P749": 1}},
            fetched_at=now,
            expires_at=now + timedelta(days=90),
        )

        repo = BrandProfileRepository(conn)
        repo.upsert(profile)
        conn.commit()

        loaded = repo.get("jeep")

        assert loaded is not None
        assert loaded.display_name == "Jeep"
        assert loaded.parent_companies == ["Stellantis"]
        assert loaded.corporate_chain == ["Stellantis", "Exor"]
        assert loaded.key_metrics["revenue"] == ["1,000 US dollar (2023)"]
        assert loaded.lookup_steps[0].source == "wikipedia"
        assert loaded.source_json["wikidata_claim_counts"] == {"P749": 1}
    finally:
        conn.close()
