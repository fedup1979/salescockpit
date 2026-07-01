from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.db import init_db
from sales_cockpit.services.front_import import (
    import_front_message_attachments,
    reconcile_front_transition_names,
    repair_front_imported_message_bodies,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Maintenance des conversations Front importées : nettoyage HTML, "
            "pièces jointes, réconciliation de noms."
        )
    )
    parser.add_argument(
        "--import-run-id",
        default="",
        help="Limiter à un import run Front précis. Par défaut : tous les imports Front.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Écrit en base et télécharge les pièces jointes. Par défaut : dry-run.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Limiter chaque étape aux N premières lignes.")
    parser.add_argument("--skip-body-repair", action="store_true", help="Ne pas nettoyer les corps HTML.")
    parser.add_argument("--skip-attachments", action="store_true", help="Ne pas importer les pièces jointes.")
    parser.add_argument("--skip-names", action="store_true", help="Ne pas réconcilier les noms.")
    args = parser.parse_args()

    init_db()
    import_run_id = args.import_run_id.strip() or None
    dry_run = not args.execute
    output: dict[str, Any] = {
        "dry_run": dry_run,
        "import_run_id": import_run_id,
        "limit": args.limit,
        "steps": {},
    }
    if not args.skip_body_repair:
        output["steps"]["body_repair"] = repair_front_imported_message_bodies(
            import_run_id,
            dry_run=dry_run,
            limit=args.limit,
        )
    if not args.skip_attachments:
        output["steps"]["attachments"] = import_front_message_attachments(
            import_run_id,
            dry_run=dry_run,
            limit=args.limit,
        )
    if not args.skip_names:
        output["steps"]["names"] = reconcile_front_transition_names(
            import_run_id,
            dry_run=dry_run,
            limit=args.limit,
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
