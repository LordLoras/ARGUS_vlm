from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from ad_classifier.db.repositories.base import db_value, row_to_dict
from ad_classifier.models.campaigns import AdCampaignRecord, CampaignRecord

_UNSET = object()


def _campaign_from_row(row: sqlite3.Row) -> CampaignRecord:
    data = row_to_dict(row)
    assert data is not None
    return CampaignRecord.model_validate(data)


def _assignment_from_row(row: sqlite3.Row) -> AdCampaignRecord:
    data = row_to_dict(row)
    assert data is not None
    return AdCampaignRecord.model_validate(data)


class CampaignRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, campaign: CampaignRecord) -> None:
        data = campaign.model_dump()
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        values = [db_value(value) for value in data.values()]
        self.conn.execute(
            f"INSERT INTO campaigns ({columns}) VALUES ({placeholders})",
            values,
        )

    def upsert_user(self, campaign: CampaignRecord) -> None:
        if campaign.created_by != "user":
            raise ValueError("upsert_user only accepts user-created campaigns")

        self.conn.execute(
            """
            INSERT INTO campaigns (
              id, name, advertiser, brand, theme, start_date, end_date,
              created_by, description, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              name = excluded.name,
              advertiser = excluded.advertiser,
              brand = excluded.brand,
              theme = excluded.theme,
              start_date = excluded.start_date,
              end_date = excluded.end_date,
              created_by = 'user',
              description = excluded.description
            """,
            (
                campaign.id,
                campaign.name,
                campaign.advertiser,
                campaign.brand,
                campaign.theme,
                db_value(campaign.start_date),
                db_value(campaign.end_date),
                campaign.created_by,
                campaign.description,
                db_value(campaign.created_at),
            ),
        )

    def upsert_auto(self, campaign: CampaignRecord) -> bool:
        """Insert/update an auto campaign unless a user campaign owns the same id."""
        if campaign.created_by != "auto":
            raise ValueError("upsert_auto only accepts auto-created campaigns")

        existing = self.get(campaign.id)
        if existing is not None and existing.created_by == "user":
            return False

        self.conn.execute(
            """
            INSERT INTO campaigns (
              id, name, advertiser, brand, theme, start_date, end_date,
              created_by, description, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
              name = excluded.name,
              advertiser = excluded.advertiser,
              brand = excluded.brand,
              theme = excluded.theme,
              start_date = excluded.start_date,
              end_date = excluded.end_date,
              description = excluded.description
            WHERE campaigns.created_by = 'auto'
            """,
            (
                campaign.id,
                campaign.name,
                campaign.advertiser,
                campaign.brand,
                campaign.theme,
                db_value(campaign.start_date),
                db_value(campaign.end_date),
                campaign.created_by,
                campaign.description,
                db_value(campaign.created_at),
            ),
        )
        return True

    def get(self, campaign_id: str) -> CampaignRecord | None:
        row = self.conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        return _campaign_from_row(row) if row is not None else None

    def get_by_name(self, name: str) -> CampaignRecord | None:
        row = self.conn.execute(
            "SELECT * FROM campaigns WHERE lower(name) = lower(?) ORDER BY created_at LIMIT 1",
            (name,),
        ).fetchone()
        return _campaign_from_row(row) if row is not None else None

    def list(
        self,
        *,
        brand: str | None = None,
        created_by: str | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[CampaignRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if brand:
            clauses.append("brand = ?")
            params.append(brand)
        if created_by:
            clauses.append("created_by = ?")
            params.append(created_by)
        if q:
            clauses.append("(name LIKE ? OR description LIKE ? OR theme LIKE ?)")
            pattern = f"%{q}%"
            params.extend([pattern, pattern, pattern])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM campaigns
            {where}
            ORDER BY created_at DESC, id
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
        return [_campaign_from_row(row) for row in rows]

    def update(
        self,
        campaign_id: str,
        *,
        name: object = _UNSET,
        advertiser: object = _UNSET,
        brand: object = _UNSET,
        theme: object = _UNSET,
        start_date: object = _UNSET,
        end_date: object = _UNSET,
        description: object = _UNSET,
    ) -> CampaignRecord | None:
        existing = self.get(campaign_id)
        if existing is None:
            return None

        values = {
            "name": existing.name if name is _UNSET else name,
            "advertiser": existing.advertiser if advertiser is _UNSET else advertiser,
            "brand": existing.brand if brand is _UNSET else brand,
            "theme": existing.theme if theme is _UNSET else theme,
            "start_date": existing.start_date if start_date is _UNSET else start_date,
            "end_date": existing.end_date if end_date is _UNSET else end_date,
            "description": existing.description if description is _UNSET else description,
        }
        self.conn.execute(
            """
            UPDATE campaigns
            SET name = ?,
                advertiser = ?,
                brand = ?,
                theme = ?,
                start_date = ?,
                end_date = ?,
                description = ?
            WHERE id = ?
            """,
            (
                values["name"],
                values["advertiser"],
                values["brand"],
                values["theme"],
                db_value(values["start_date"]),
                db_value(values["end_date"]),
                values["description"],
                campaign_id,
            ),
        )
        return self.get(campaign_id)

    def promote_to_user(self, campaign_id: str) -> CampaignRecord | None:
        self.conn.execute(
            "UPDATE campaigns SET created_by = 'user' WHERE id = ?",
            (campaign_id,),
        )
        self.conn.execute(
            "UPDATE ad_campaigns SET assigned_by = 'user' WHERE campaign_id = ?",
            (campaign_id,),
        )
        return self.get(campaign_id)

    def delete(self, campaign_id: str) -> None:
        self.conn.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))


class AdCampaignRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def assign(self, assignment: AdCampaignRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO ad_campaigns (
              ad_id, campaign_id, similarity_score, assigned_by, assigned_at
            ) VALUES (?,?,?,?,?)
            ON CONFLICT(ad_id, campaign_id) DO UPDATE SET
              similarity_score = excluded.similarity_score,
              assigned_by = excluded.assigned_by,
              assigned_at = excluded.assigned_at
            """,
            (
                assignment.ad_id,
                assignment.campaign_id,
                assignment.similarity_score,
                assignment.assigned_by,
                db_value(assignment.assigned_at),
            ),
        )

    def assign_many(
        self,
        campaign_id: str,
        ad_ids: list[str],
        *,
        assigned_by: str = "user",
    ) -> None:
        now = datetime.now(UTC)
        for ad_id in ad_ids:
            self.assign(
                AdCampaignRecord(
                    ad_id=ad_id,
                    campaign_id=campaign_id,
                    assigned_by=assigned_by,
                    assigned_at=now,
                )
            )

    def unassign(self, campaign_id: str, ad_id: str) -> None:
        self.conn.execute(
            "DELETE FROM ad_campaigns WHERE campaign_id = ? AND ad_id = ?",
            (campaign_id, ad_id),
        )

    def list_for_campaign(self, campaign_id: str) -> list[AdCampaignRecord]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM ad_campaigns
            WHERE campaign_id = ?
            ORDER BY assigned_at DESC, ad_id
            """,
            (campaign_id,),
        ).fetchall()
        return [_assignment_from_row(row) for row in rows]

    def list_for_ad(self, ad_id: str) -> list[AdCampaignRecord]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM ad_campaigns
            WHERE ad_id = ?
            ORDER BY assigned_at DESC, campaign_id
            """,
            (ad_id,),
        ).fetchall()
        return [_assignment_from_row(row) for row in rows]

    def ads_with_user_assignments(self) -> set[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT ad_id FROM ad_campaigns WHERE assigned_by = 'user'"
        ).fetchall()
        return {str(row["ad_id"]) for row in rows}

    def has_user_assignment(self, ad_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM ad_campaigns
            WHERE ad_id = ? AND assigned_by = 'user'
            LIMIT 1
            """,
            (ad_id,),
        ).fetchone()
        return row is not None
