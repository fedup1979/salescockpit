from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sales_cockpit.db import connect, init_db
from sales_cockpit.store import (
    list_sequence_steps,
    list_sequence_template_mappings,
    list_templates,
    upsert_sequence_template_mapping,
)


NOTE = "Pré-mapping IA à valider avec Laura."


# Best-effort initial commercial mapping from currently approved ESSR Twilio templates.
# These choices are intentionally editable in Pilotage and are a starting point, not final truth.
PREMAPPING: dict[str, dict[str, list[str | None]]] = {
    "FSM": {
        "lead_no_reply": [
            "mkt_fsm_ln_subs_02",
            "relance_temoignage_fsm",
            "fsm_1_relecture_cv",
            "fsm_2_article_blog",
            "fsm_3_echeance_offre_1440",
            "relance_abandon",
        ],
        "setter_no_next_step": [
            "relance_all_aide",
            "relance_temoignage_fsm",
            "relance_places_fsm",
            "fsm_3_echeance_offre_1440",
            "fsm_4_presque_complet",
            "relance_abandon_projet",
        ],
        "setting_call_not_reached": [None, None, "relance_all_aide"],
        "closing_call_not_reached": [None, None, "all_2_closing_sans_etiquette"],
        "post_call_undecided": ["all_2_closing_sans_etiquette"],
        "closer_will_sign": [
            "tous_1_closing_va_signer",
            "mkt_fsm_ln_ac_02",
            "mkt_fsm_ln_ap_02",
            "fsm_3_echeance_offre_1440",
            "fsm_4_presque_complet",
            "relance_abandon_projet",
        ],
        "course_start": [
            "relance_places_fsm",
            "mkt_fsm_ln_at_02",
            "fsm_3_echeance_offre_1440",
            "fsm_4_presque_complet",
        ],
    },
    "APP": {
        "lead_no_reply": [
            "mkt_app_ln_subs_02",
            "app_1_garantie_remboursement",
            "app_2_feuille_route",
            "app_4_blog_asca_rme",
            "app_5_dernieres_places",
            "relance_abandon",
        ],
        "setter_no_next_step": [
            "relance_all_aide",
            "app_2_feuille_route",
            "relance_temoignage_app",
            "app_1_garantie_remboursement",
            "app_5_dernieres_places",
            "relance_abandon_projet",
        ],
        "setting_call_not_reached": [None, None, "relance_all_aide"],
        "closing_call_not_reached": [None, None, "all_2_closing_sans_etiquette"],
        "post_call_undecided": ["all_2_closing_sans_etiquette"],
        "closer_will_sign": [
            "tous_1_closing_va_signer",
            "mkt_app_ln_ac_02",
            "mkt_app_ln_ap_02",
            "app_1_garantie_remboursement",
            "app_5_dernieres_places",
            "relance_abandon_projet",
        ],
        "course_start": [
            "relance_places_app",
            "mkt_app_ln_at_03",
            "app_5_dernieres_places",
            "all_2_closing_sans_etiquette",
        ],
    },
    "AS": {
        "lead_no_reply": [
            "mkt_as_ln_subs_02",
            "as_1_insertion_emploi",
            "relance_temoignage_as_3",
            "as_3_echeance_offre_450_francs",
            "as_4_presque_complet",
            "relance_abandon",
        ],
        "setter_no_next_step": [
            "relance_all_aide",
            "as_1_insertion_emploi",
            "relance_temoignage_as_3",
            "as_3_echeance_offre_450_francs",
            "as_4_presque_complet",
            "relance_abandon_projet",
        ],
        "setting_call_not_reached": [None, None, "relance_all_aide"],
        "closing_call_not_reached": [None, None, "all_2_closing_sans_etiquette"],
        "post_call_undecided": ["all_2_closing_sans_etiquette"],
        "closer_will_sign": [
            "tous_1_closing_va_signer",
            "mkt_as_ln_ac_02",
            "mkt_as_ln_ap_02",
            "mkt_as_ln_at_02",
            "as_reserve_place_2",
            "relance_abandon_projet",
        ],
        "course_start": [
            "relance_places_as",
            "mkt_as_ln_at_02",
            "as_3_echeance_offre_450_francs",
            "as_reserve_place",
        ],
    },
}


@dataclass(frozen=True)
class DesiredMapping:
    course_category: str
    sequence_code: str
    step_index: int
    template_name: str

    @property
    def key(self) -> tuple[str, int, str, str]:
        return (self.sequence_code, self.step_index, "all", self.course_category)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply the initial ESSR sequence-to-template premapping."
    )
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing.")
    parser.add_argument(
        "--categories",
        nargs="+",
        default=sorted(PREMAPPING),
        help="Course categories to map. Defaults to FSM APP AS.",
    )
    args = parser.parse_args()

    init_db()
    categories = [category.strip().upper() for category in args.categories]
    desired = list(iter_desired_mappings(categories))

    admin_id = find_admin_user_id()
    if admin_id is None:
        raise SystemExit("No active admin user found.")

    template_index = build_template_index()
    step_index = build_step_index()
    existing = build_existing_mapping_index()

    errors = validate_desired_mappings(desired, template_index, step_index)
    if errors:
        print("Cannot apply premapping:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    planned = []
    for item in desired:
        template = template_index[item.template_name]
        current = existing.get(item.key)
        planned.append((item, template, current))

    print(
        f"Sequence template premapping: {len(planned)} mappings "
        f"for categories {', '.join(categories)}."
    )
    for item, template, current in planned:
        action = "unchanged" if current and current["template_id"] == template["id"] else "upsert"
        current_name = current["template_name"] if current else "none"
        print(
            f"- {item.course_category} | {item.sequence_code} #{item.step_index}: "
            f"{item.template_name} (id={template['id']}, sid={template['twilio_content_sid']}) "
            f"[current={current_name}; {action}]"
        )

    if args.dry_run:
        print("Dry run only. No database changes were written.")
        return

    applied = 0
    for item, template, _current in planned:
        ok, message = upsert_sequence_template_mapping(
            admin_id,
            item.sequence_code,
            item.step_index,
            "all",
            item.course_category,
            int(template["id"]),
            NOTE,
        )
        if not ok:
            raise SystemExit(
                f"Failed on {item.course_category} {item.sequence_code} "
                f"#{item.step_index}: {message}"
            )
        applied += 1

    print(f"Applied {applied} sequence template mappings.")


def iter_desired_mappings(categories: Iterable[str]) -> Iterable[DesiredMapping]:
    for category in categories:
        if category not in PREMAPPING:
            raise SystemExit(f"Unsupported category for premapping: {category}")
        for sequence_code, template_names in PREMAPPING[category].items():
            for step_index, template_name in enumerate(template_names, start=1):
                if template_name is None:
                    continue
                yield DesiredMapping(category, sequence_code, step_index, template_name)


def find_admin_user_id() -> int | None:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id FROM users
            WHERE email = 'francois.dupuis@essr.ch' AND role = 'admin' AND active = 1
            UNION ALL
            SELECT id FROM users
            WHERE role = 'admin' AND active = 1
            ORDER BY id
            LIMIT 1
            """
        ).fetchone()
    return int(row["id"]) if row else None


def build_template_index() -> dict[str, dict]:
    approved_real = [
        template
        for template in list_templates()
        if is_approved_real_twilio_template(template)
    ]
    by_name: dict[str, dict] = {}
    for template in approved_real:
        name = template["name"]
        existing = by_name.get(name)
        if existing is None or int(template["id"]) > int(existing["id"]):
            by_name[name] = template
    return by_name


def is_approved_real_twilio_template(template: dict) -> bool:
    status = template.get("status") or ""
    sid = str(template.get("twilio_content_sid") or "")
    return status == "approved" and sid.startswith("HX") and not sid.startswith("HX_MOCK_")


def build_step_index() -> dict[tuple[str, int], dict]:
    return {
        (step["sequence_code"], int(step["step_index"])): step
        for step in list_sequence_steps(active_only=True)
    }


def build_existing_mapping_index() -> dict[tuple[str, int, str, str], dict]:
    existing = {}
    for mapping in list_sequence_template_mappings():
        key = (
            mapping["sequence_code"],
            int(mapping["sequence_step_index"]),
            mapping["lead_type"],
            mapping["course_category"],
        )
        existing[key] = mapping
    return existing


def validate_desired_mappings(
    desired: list[DesiredMapping],
    template_index: dict[str, dict],
    step_index: dict[tuple[str, int], dict],
) -> list[str]:
    errors: list[str] = []
    for item in desired:
        template = template_index.get(item.template_name)
        if template is None:
            errors.append(
                f"Missing approved real Twilio template '{item.template_name}' "
                f"for {item.course_category} {item.sequence_code} #{item.step_index}."
            )
        step = step_index.get((item.sequence_code, item.step_index))
        if step is None:
            errors.append(f"Missing active step {item.sequence_code} #{item.step_index}.")
        elif step["action_type"] != "follow_up":
            errors.append(
                f"Step {item.sequence_code} #{item.step_index} is "
                f"{step['action_type']}, not follow_up."
            )
    return errors


if __name__ == "__main__":
    main()
