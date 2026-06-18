# Sales Cockpit Gap Analysis

Ce document compare la logique métier cible avec l'état actuel du système local.

## Synthèse

Le cockpit local couvre maintenant les fondations critiques :

- conversations WhatsApp ;
- fenêtre WhatsApp ouverte/fermée ;
- actions principales ;
- qualification commerciale ;
- statut de contact séparé ;
- résolution avec motif obligatoire ;
- réouverture avec prochaine action obligatoire ;
- demandes de template liées aux relances bloquées ;
- séquences et étapes de séquence structurées ;
- tests métier sur les règles critiques.

Le système reste volontairement local et mock. Il ne touche pas encore Twilio production, SchoolDrive production, Notion ou Front.io.

## Ce Qui Existe

### Données

Présent :

- `users`
- `leads`
- `conversations`
- `messages`
- `whatsapp_templates`
- `template_placeholders`
- `tasks`
- `lead_events`
- `ai_labels`
- `sequences`
- `sequence_steps`
- `template_requests`

Ajouté ou consolidé :

- `leads.contact_status`
- `leads.acquisition_type`
- `conversations.resolution_reason`
- `conversations.resolution_note`
- `conversations.resolved_at`
- `conversations.reopened_at`
- champs de chaînage sur `tasks`

### Logique Métier

Présent :

- inbound WhatsApp crée une action `reply` pour Setter 1 ;
- inbound sur conversation résolue rouvre la conversation ;
- inbound d'un prospect `do_not_contact` crée une action `contact_review` ;
- relance bloquée par template manquant crée une `template_request` ;
- envoi sortant clôt l'action `reply` ou `follow_up` active ;
- `reply` envoyé sans RDV crée une relance Setter 2 +72h ;
- appel non joint crée rappels +2h, +24h, puis relance WhatsApp ;
- closing `will_sign` crée une séquence Setter 2 ;
- résolution manuelle exige un motif ;
- réouverture manuelle exige une prochaine action.

### Admin

Présent :

- rôles commerciaux ;
- qualifications ;
- statuts de contact ;
- motifs de résolution ;
- règles opérationnelles ;
- règles d'attribution ;
- horaires et bascules déclaratifs ;
- types de leads SchoolDrive ;
- workflow ;
- séquences ;
- étapes de séquence ;
- templates de démonstration ;
- demandes de templates.

### Tests

Présent :

- règles WhatsApp 24h ;
- login ;
- envoi libre bloqué hors fenêtre ;
- résolution/réouverture ;
- résolution exigeant motif ;
- réouverture exigeant action ;
- inbound créant `reply` ;
- inbound `do_not_contact` créant `contact_review` ;
- relance planifiée ;
- message reply créant relance ;
- demande de template bloquant une action ;
- handoff closer ;
- appel setting non joint créant rappel ;
- statuts stop bloquant relances ;
- objets métier déclaratifs.

## Gaps Restants Avant Staging

### À Faire Avant Staging Local Partagé

1. Faire une revue UI manuelle complète dans Streamlit.
2. Vérifier que les popovers Streamlit de résolution/réouverture sont ergonomiques.
3. Vérifier que l'onglet Admin reste lisible malgré les nouvelles tables.
4. Vérifier que les données mock couvrent les nouveaux cas : `contact_review`, relance bloquée, template request.
5. Ajouter un smoke test Streamlit après stabilisation UI.
6. Nettoyer les imports inutilisés si nécessaire.
7. Redémarrer Streamlit après migration de schéma.

### À Faire Avant Connexion Réelle

1. Confirmer l'URL exacte SchoolDrive d'un lead.
2. Confirmer les champs SchoolDrive disponibles : type `lead/presubscription`, catégorie de cours, session, date de début, statut d'inscription/signature.
3. Confirmer le webhook SchoolDrive de création de lead.
4. Confirmer la méthode fiable d'identification lead par téléphone Twilio.
5. Synchroniser les vrais templates Twilio et leurs statuts.
6. Remplacer les templates `demo_*` par un mapping réel.
7. Définir les horaires par collaborateur.
8. Définir les backups par collaborateur.
9. Définir le message hors horaire.
10. Définir la politique de backup SQLite et pièces jointes.

### Gardé Pour V2

- envoi automatique de templates ;
- automatisation Setter 2 ;
- PBX Twilio ;
- écriture Notion ;
- écriture SchoolDrive ;
- règles horaires complètes avec jours fériés ;
- interface admin éditable pour modifier les séquences ;
- moteur de conflits avancé entre plusieurs relances ;
- scoring IA ;
- entraînement setter IA.

## Risques Critiques À Surveiller

### Risque 1 : trop d'actions ouvertes

Une conversation ouverte doit avoir une prochaine action, mais pas plusieurs actions concurrentes contradictoires.

Mitigation actuelle :

- le store complète ou annule les actions ouvertes dans les principaux flux.

À renforcer :

- test global d'invariant : conversation ouverte = exactement une action active principale, sauf action bloquée supportée.

### Risque 2 : résolution abusive

Un utilisateur peut résoudre une opportunité encore valable.

Mitigation actuelle :

- motif obligatoire ;
- note obligatoire sur les motifs sensibles.

À renforcer :

- rapport Admin des conversations résolues par utilisateur et motif.

### Risque 3 : statut Ne plus contacter mal géré

Répondre à quelqu'un qui a demandé à ne plus être contacté peut être dangereux.

Mitigation actuelle :

- `contact_status` séparé ;
- inbound sur `do_not_contact` crée une revue humaine ;
- aucune relance automatique.

À renforcer :

- message d'avertissement très visible dans la conversation.

### Risque 4 : templates mal mappés

Une relance peut envoyer un template inadapté.

Mitigation actuelle :

- `sequence_steps` lie chaque étape à un template par défaut ;
- `template_requests` trace les manques.

À renforcer :

- synchronisation Twilio réelle ;
- validation par Laura des templates par séquence/cours.

### Risque 5 : dates de cours mal choisies

Pour un simple Lead, la date de cours pertinente peut être ambiguë.

Mitigation actuelle :

- règle documentée, non automatisée.

À renforcer :

- lecture SchoolDrive ;
- règle explicite de sélection de session pour les Leads génériques.

## Recommandation

Continuer en deux temps :

1. terminer la revue locale avec Laura et François sur cette logique ;
2. seulement ensuite brancher SchoolDrive/Twilio/Notion et préparer le staging.
