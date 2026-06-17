from __future__ import annotations


QUALIFICATION_STATUSES = [
    {
        "value": "neutral",
        "label": "Neutre",
        "meaning": "Qualification par défaut, le prospect n'a pas encore été jugé.",
        "stops_followups": False,
    },
    {
        "value": "eligible",
        "label": "Éligible",
        "meaning": "Le prospect peut continuer dans le parcours commercial.",
        "stops_followups": False,
    },
    {
        "value": "not_relevant",
        "label": "Non pertinent",
        "meaning": "Le prospect ne correspond pas à une opportunité commerciale utile.",
        "stops_followups": True,
    },
    {
        "value": "will_sign",
        "label": "Va signer",
        "meaning": "Le closer estime que le prospect va signer, relance dédiée à activer.",
        "stops_followups": False,
    },
    {
        "value": "signed",
        "label": "A signé",
        "meaning": "La vente est gagnée, les relances commerciales s'arrêtent.",
        "stops_followups": True,
    },
    {
        "value": "do_not_contact",
        "label": "Ne plus contacter",
        "meaning": "Le prospect a demandé à ne plus être contacté, arrêt strict.",
        "stops_followups": True,
    },
]

STOP_FOLLOWUP_STATUSES = {
    item["value"] for item in QUALIFICATION_STATUSES if item["stops_followups"]
}

SALES_ACTORS = [
    {
        "code": "setter_1",
        "label": "Setter 1",
        "person": "Mihary",
        "email": "service.etudiants@essr.ch",
        "responsibility": "Conversation écrite active et entretien de setting.",
        "automation": "Humain en V1",
    },
    {
        "code": "setter_2",
        "label": "Setter 2",
        "person": "Setter 2",
        "email": "setter2@essr.ch",
        "responsibility": "Relances structurées par template, hors conversation active.",
        "automation": "Candidat prioritaire à l'automatisation après V1",
    },
    {
        "code": "closer",
        "label": "Closer",
        "person": "Yasmine",
        "email": "yasmine@essr.ch",
        "responsibility": "Closing téléphonique et qualification de closing.",
        "automation": "Humain",
    },
]

OPERATING_RULES = [
    {
        "rule": "Fenêtre WhatsApp",
        "value": "Ouverte 24h après chaque message entrant du prospect.",
        "effect": "Message libre possible uniquement pendant cette fenêtre.",
    },
    {
        "rule": "Premier template automatique",
        "value": "Envoyé par SchoolDrive/Twilio à la création du lead.",
        "effect": "N'ouvre pas la fenêtre WhatsApp tant que le prospect ne répond pas.",
    },
    {
        "rule": "Relances hors fenêtre",
        "value": "Template approuvé obligatoire.",
        "effect": "Setter 2 prépare ou envoie la relance selon la séquence.",
    },
    {
        "rule": "Délai minimum WhatsApp",
        "value": "24h entre deux relances sortantes.",
        "effect": "Une relance concurrente trop proche doit être annulée ou repoussée.",
    },
    {
        "rule": "Conflit lead vs cours",
        "value": "La relance liée à une date de cours gagne toujours.",
        "effect": "La relance liée au cycle du lead est annulée.",
    },
    {
        "rule": "Non pertinent",
        "value": "Qualification commerciale négative.",
        "effect": "Fin du process et arrêt des relances.",
    },
    {
        "rule": "Ne plus contacter",
        "value": "Demande explicite du prospect.",
        "effect": "Blocage strict des relances commerciales.",
    },
]

SCHEDULE_RULES = [
    {
        "rule": "Horaires humains",
        "value": "À confirmer par collaborateur.",
        "effect": "Hors horaire, créer une action différée ou envoyer un répondeur automatique.",
    },
    {
        "rule": "Absence",
        "value": "À confirmer par collaborateur.",
        "effect": "Transfert de la prochaine action à un backup défini.",
    },
    {
        "rule": "Répondeur hors horaire",
        "value": "Template ou message automatique à définir.",
        "effect": "Informer le prospect qu'un retour sera fait au prochain créneau ouvré.",
    },
]

SEQUENCES = [
    {
        "code": "lead_no_reply",
        "label": "Lead sans réponse initiale",
        "timeline": "Relative au lead",
        "trigger": "Template automatique envoyé, aucun message entrant du prospect.",
        "owner": "Setter 2",
        "steps": "+72h, +72h, +72h, +7j, +7j, +30j, puis stop",
        "templates": "demo_relance_72h_1 à demo_relance_30j_stop",
        "stop_when": "Réponse entrante, non pertinent, ne plus contacter, signé.",
    },
    {
        "code": "setter_no_next_step",
        "label": "Conversation setter sans suite",
        "timeline": "Relative au dernier échange",
        "trigger": "Setter 1 a échangé, aucun RDV posé et 72h sans échange.",
        "owner": "Setter 2",
        "steps": "+72h, +72h, +72h, +7j, +7j, +30j, puis stop",
        "templates": "demo_relance_setting_72h_1 à demo_relance_setting_30j_stop",
        "stop_when": "Réponse entrante, RDV posé, non pertinent, ne plus contacter.",
    },
    {
        "code": "closer_will_sign",
        "label": "Closer : va signer",
        "timeline": "Relative à la qualification closer",
        "trigger": "Yasmine qualifie le prospect en Va signer.",
        "owner": "Setter 2",
        "steps": "+72h, +72h, +72h, +7j, +7j, +30j, puis stop",
        "templates": "demo_va_signer_72h_1 à demo_va_signer_30j_stop",
        "stop_when": "Signature, réponse entrante nécessitant humain, ne plus contacter.",
    },
    {
        "code": "course_start",
        "label": "Début de cours",
        "timeline": "Relative au cours",
        "trigger": "Date de début de session connue dans SchoolDrive.",
        "owner": "Setter 2 ou automatisation",
        "steps": "J-14, J-7, J-3, J-1, à confirmer.",
        "templates": "demo_cours_j14 à demo_cours_j1",
        "stop_when": "Signature, non pertinent, ne plus contacter.",
    },
]

LEAD_TYPES = [
    {
        "type": "lead_generic",
        "label": "Lead générique",
        "source": "Demande d'information sans session pré-sélectionnée.",
        "course_date_rule": "Utiliser la prochaine session pertinente depuis SchoolDrive, à confirmer.",
    },
    {
        "type": "pre_registration",
        "label": "Préinscription",
        "source": "Le prospect a pré-sélectionné une session.",
        "course_date_rule": "Utiliser la date de cette session SchoolDrive.",
    },
]

DEMO_TEMPLATE_CATALOG = [
    {
        "name": "demo_initial_offer",
        "category": "marketing",
        "body": "Bonjour {{first_name}}, merci pour votre demande concernant {{course_title}}. Nous avons actuellement une offre spéciale. Répondez à ce message et je vous donne les détails. Yasmine",
        "sequence": "lead_created",
    },
    {
        "name": "demo_relance_72h_1",
        "category": "marketing",
        "body": "Bonjour {{first_name}}, je me permets de revenir vers vous au sujet de {{course_title}}. Souhaitez-vous recevoir les informations pratiques ? Yasmine",
        "sequence": "lead_no_reply",
    },
    {
        "name": "demo_relance_72h_2",
        "category": "marketing",
        "body": "Bonjour {{first_name}}, avez-vous encore un intérêt pour la formation {{course_title}} ? Je peux vous orienter rapidement. Yasmine",
        "sequence": "lead_no_reply",
    },
    {
        "name": "demo_relance_72h_3",
        "category": "marketing",
        "body": "Bonjour {{first_name}}, je vous relance une dernière fois cette semaine pour {{course_title}}. Souhaitez-vous que l'on vous appelle ? Yasmine",
        "sequence": "lead_no_reply",
    },
    {
        "name": "demo_relance_7j_1",
        "category": "marketing",
        "body": "Bonjour {{first_name}}, les inscriptions avancent pour {{course_title}}. Voulez-vous que je vérifie les possibilités pour vous ? Yasmine",
        "sequence": "lead_no_reply",
    },
    {
        "name": "demo_relance_7j_2",
        "category": "marketing",
        "body": "Bonjour {{first_name}}, je reviens vers vous concernant votre demande ESSR. Souhaitez-vous toujours des informations ? Yasmine",
        "sequence": "lead_no_reply",
    },
    {
        "name": "demo_relance_30j_stop",
        "category": "marketing",
        "body": "Bonjour {{first_name}}, je clôture votre demande pour le moment. Si vous souhaitez reprendre le sujet, répondez simplement à ce message. Yasmine",
        "sequence": "lead_no_reply",
    },
    {
        "name": "demo_setting_rdv",
        "category": "utility",
        "body": "Bonjour {{first_name}}, êtes-vous disponible demain pour un court appel ? Mon collègue pourra vous présenter la formation {{course_title}}. Yasmine",
        "sequence": "setter_conversation",
    },
    {
        "name": "demo_va_signer_72h_1",
        "category": "utility",
        "body": "Bonjour {{first_name}}, je reviens vers vous pour finaliser votre inscription à {{course_title}}. Avez-vous besoin d'aide pour la dernière étape ? Yasmine",
        "sequence": "closer_will_sign",
    },
    {
        "name": "demo_cours_j3",
        "category": "marketing",
        "body": "Bonjour {{first_name}}, la session {{course_title}} commence bientôt. Souhaitez-vous que je vérifie s'il reste une possibilité pour vous ? Yasmine",
        "sequence": "course_start",
    },
    {
        "name": "demo_hors_horaire",
        "category": "utility",
        "body": "Bonjour {{first_name}}, merci pour votre message. L'équipe est actuellement indisponible, nous vous répondrons au prochain créneau ouvré. Yasmine",
        "sequence": "out_of_hours",
    },
]
