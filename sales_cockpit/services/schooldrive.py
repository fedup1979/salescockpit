from __future__ import annotations


class SchoolDriveConnector:
    """Read-only placeholder for the V1 SchoolDrive integration."""

    def get_lead_url(self, schooldrive_lead_id: str | None) -> str | None:
        if not schooldrive_lead_id:
            return None
        return f"https://schooldrive.essr.ch/leads/{schooldrive_lead_id}"

    def get_lead(self, schooldrive_lead_id: str) -> dict:
        raise NotImplementedError("SchoolDrive read-only connector is not wired yet.")

    def search_leads(
        self, phone: str | None = None, email: str | None = None, name: str | None = None
    ) -> list[dict]:
        return []
