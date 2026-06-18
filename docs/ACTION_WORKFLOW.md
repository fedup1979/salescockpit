# Sales Cockpit Action Workflow

Ce document formalise la logique métier validée avec François autour des actions commerciales.

Pour la logique exhaustive validée, lire aussi `docs/BUSINESS_LOGIC.md`.
Pour l'état d'implémentation et les écarts restants, lire `docs/GAP_ANALYSIS.md`.

Il doit devenir la référence de travail pour toute évolution de `Tâches`, Inbox, automatisation Setter 2, Twilio, SchoolDrive, Notion et futur setter IA.

La version structurée de cette logique existe dans `sales_cockpit/business_rules.py` via `MAIN_ACTION_TYPES`, `SUPPORT_ACTIONS`, `ACTION_STATUSES` et `WORKFLOW_TRANSITIONS`. Elle est affichée dans l'onglet Admin > Workflow.

## Décisions Validées

- L'action est l'unité opérationnelle centrale du système.
- Une conversation ouverte doit toujours avoir une prochaine action ouverte.
- La chaîne principale doit rester simple et lisible pour l'équipe commerciale.
- Le système doit distinguer action principale, action support, preuve, résultat et déclencheur.
- L'envoi d'un message WhatsApp doit clôturer l'action active correspondante, puis ouvrir l'action suivante si nécessaire.
- La vraie valeur du système est le chaînage explicite des actions commerciales.

## Vocabulaire

### Action Principale

Une action principale fait avancer le flux commercial.

Elle apparaît dans la file `Tâches` comme travail opérationnel à faire.

Actions principales V1 :

| Type interne | Libellé UI | Sens métier | Responsable typique |
|---|---|---|---|
| `reply` | Répondre | Répondre à un message entrant WhatsApp | Setter 1 |
| `follow_up` | Relancer | Relancer le prospect, souvent via template WhatsApp | Setter 2, puis IA |
| `setting_call` | Appel de setting | Appeler pour qualifier et obtenir la suite commerciale | Setter 1 |
| `closing_call` | Appel de closing | Appeler pour vendre, finaliser ou trancher | Closer |

`setting_call` est préféré à `call` dans le modèle métier, parce que `call` est trop vague. L'UI peut afficher `Appel` ou `Appel de setting` selon le niveau de simplicité souhaité.

### Action Support

Une action support documente, débloque ou complète une action principale.

Elle ne doit pas polluer la file principale sauf si elle bloque réellement le flux.

Actions support :

| Type | Rôle |
|---|---|
| Qualification | Résultat métier qui influence le chaînage. La qualification closer prime sur la qualification setter. |
| Note manuelle | Preuve ou contexte ajouté après un appel, un échange privé ou une décision. |
| Création de template | Débloque une relance quand aucun template approuvé ne convient. |
| Revue admin | Cas ambigu, conflit de règles ou donnée manquante. |

### Preuve

Une preuve est ce qui montre qu'une action a réellement été effectuée.

Exemples :

| Action | Preuve attendue |
|---|---|
| `reply` | Message WhatsApp sortant après le message entrant |
| `follow_up` | Template ou message de relance envoyé |
| `setting_call` | Résultat d'appel + mini note + qualification setter |
| `closing_call` | Résultat d'appel + mini note + qualification closer |
| Qualification support | Changement de qualification historisé |
| Note support | Message `manual_note` ou note privée enregistrée |
| Template support | Template créé, soumis, approuvé ou refusé |

### Résultat

Le résultat est l'issue métier de l'action. Il détermine souvent l'action suivante.

Exemples :

- `reply_sent`
- `appointment_requested`
- `setting_call_booked`
- `closing_call_booked`
- `no_answer`
- `not_relevant`
- `do_not_contact`
- `will_sign`
- `signed`
- `needs_follow_up`
- `template_missing`
- `blocked`

### Déclencheur

Le déclencheur explique pourquoi une action existe.

Exemples :

- `lead_created`
- `automatic_initial_message_sent`
- `prospect_replied`
- `no_reply_after_72h`
- `setter_no_next_step`
- `setting_call_completed`
- `handoff_to_closer`
- `closing_call_completed`
- `closer_marked_will_sign`
- `course_start_approaching`
- `template_missing`
- `business_hours_closed`

## Statuts

Statuts persistés recommandés :

| Statut | Sens |
|---|---|
| `planned` | Action prévue plus tard |
| `open` | Action active |
| `in_progress` | Quelqu'un l'a prise en main |
| `done` | Action terminée avec preuve ou outcome |
| `cancelled` | Action annulée car remplacée, conflit, réponse entrante, stop status, etc. |
| `blocked` | Action impossible tant qu'un blocage n'est pas levé |

`due` ne doit pas être un statut persisté. C'est une vue calculée : action non terminée + `due_at <= now`.

## Champs Métier Recommandés Pour Une Action

Les champs actuels de `tasks` couvrent une partie du besoin. Le modèle cible devrait permettre :

| Champ | Rôle |
|---|---|
| `type` | Action principale : `reply`, `follow_up`, `setting_call`, `closing_call` |
| `status` | Cycle de vie : `planned`, `open`, `in_progress`, `done`, `cancelled`, `blocked` |
| `assigned_to_user_id` | Responsable actuel |
| `due_at` | Quand l'action doit être effectuée |
| `trigger_reason` | Pourquoi l'action existe |
| `sequence_code` | Séquence qui porte l'action, ex. `lead_no_reply`, `course_start` |
| `expected_proof_type` | Message, appel, note, qualification, template |
| `outcome` | Résultat choisi ou calculé |
| `proof_message_id` | Message WhatsApp ou note qui prouve l'action |
| `proof_event_id` | Événement métier qui prouve l'action |
| `previous_action_id` | Action qui a généré celle-ci |
| `next_action_id` | Action générée ensuite, si connue |
| `cancelled_reason` | Pourquoi l'action a été annulée |
| `blocked_reason` | Pourquoi l'action est bloquée |
| `metadata_json` | Détails spécifiques sans exploser le schéma |

## Règles Transversales

- Un message entrant du prospect annule ou clôt les relances ouvertes et crée un `reply` immédiat pour Setter 1.
- Un message sortant envoyé en réponse clôt le `reply` actif.
- Une relance envoyée clôt le `follow_up` actif.
- Un appel terminé clôt le `setting_call` ou `closing_call` actif.
- Un statut stop (`not_relevant`, `do_not_contact`, `signed`) clôt les actions ouvertes et résout la conversation.
- `do_not_contact` est strict : aucune relance ne doit être créée ensuite.
- Les relances liées aux dates de cours gagnent sur les relances relatives au lead.
- Une action bloquée par template manquant doit créer une `template_request`, pas disparaître.
- Une conversation ouverte sans action ouverte est une anomalie.

## Table De Transitions V1

Cette table décrit le chaînage cible. Elle doit rester lisible par l'équipe métier.

| Situation actuelle | Déclencheur | Résultat / condition | Action à clôturer | Action suivante | Responsable | Échéance | Conversation | Supports obligatoires | Effets secondaires |
|---|---|---|---|---|---|---|---|---|---|
| Lead créé dans SchoolDrive | `lead_created` | Message initial automatique envoyé | Aucune | `follow_up` | Setter 2 | +72h | Ouverte ou en attente | Aucun | Stocker l'événement initial |
| Lead sans réponse | `no_reply_after_72h` | Prospect n'a pas répondu | `follow_up` précédent si existant | `follow_up` | Setter 2 | Maintenant | Ouverte | Template approuvé | Respecter délai minimum 24h |
| Prospect répond | `prospect_replied` | Dernier message entrant non répondu | `follow_up`, `setting_call`, `closing_call` ouverts sauf règle contraire | `reply` | Setter 1 | Maintenant | Ouverte | Aucun | Hot signal, file de Setter 1, annuler relances futures |
| Réponse envoyée | `outbound_message_sent` | Action active = `reply` | `reply` | `follow_up` de sécurité | Setter 2 | +72h | Ouverte | Message sortant | Supprimer hot signal |
| Réponse envoyée avec RDV setting | `outbound_message_sent` | RDV setting fixé | `reply` | `setting_call` | Setter 1 | Date/heure RDV | Ouverte | Message sortant, RDV noté | Annuler relance de sécurité |
| Réponse envoyée avec disqualification claire | `outbound_message_sent` | Prospect non pertinent ou stop | `reply` | Aucune | Personne | Aucun | Résolue | Qualification | Stopper relances |
| Relance due | `follow_up_due` | Fenêtre WhatsApp ouverte | `follow_up` | À déterminer après envoi | Setter 2 | Maintenant | Ouverte | Message libre ou template selon choix | Respecter délai minimum |
| Relance due | `follow_up_due` | Fenêtre WhatsApp fermée + template disponible | `follow_up` | À déterminer après envoi | Setter 2 | Maintenant | Ouverte | Template approuvé | Respecter délai minimum |
| Relance due | `follow_up_due` | Aucun template adapté | `follow_up` | `follow_up` bloquée | Setter 2 | Maintenant | Ouverte | `template_request` | Action principale passe `blocked` |
| Template demandé | `template_request_created` | Template à créer ou soumettre | `template_request` support | `follow_up` reste bloquée | Setter 2 | Dès approbation | Ouverte | Template demandé | Surveiller statut template |
| Template approuvé | `template_approved` | Relance bloquée par ce template | `template_request` support | `follow_up` | Setter 2 | Maintenant | Ouverte | Template approuvé | Débloquer action |
| Relance envoyée | `outbound_template_sent` ou `outbound_message_sent` | Action active = `follow_up` | `follow_up` | `follow_up` suivant si séquence non terminée | Setter 2 | +72h, +7j ou +30j | Ouverte | Message sortant | Incrémenter séquence |
| Relance envoyée | `outbound_template_sent` | Dernière relance de séquence | `follow_up` | Aucune | Personne | Aucun | Résolue | Message sortant | Motif `sequence_completed_no_reply` |
| RDV setting arrive | `setting_call_due` | Appel à faire | `setting_call` | Selon résultat appel | Setter 1 | Maintenant | Ouverte | Appel | Option `in_progress` si pris en main |
| Appel setting terminé | `setting_call_completed` | À closer | `setting_call` | `closing_call` | Closer | Date RDV ou maintenant | Ouverte | Mini note + qualification setter | Lead passe en `closing` |
| Appel setting terminé | `setting_call_completed` | Pas de réponse | `setting_call` | `follow_up` | Setter 2 | +72h | Ouverte | Mini note | Séquence setter no next step |
| Appel setting terminé | `setting_call_completed` | Pas prêt / à relancer | `setting_call` | `follow_up` | Setter 2 | +72h | Ouverte | Mini note + qualification setter | Séquence setter no next step |
| Appel setting terminé | `setting_call_completed` | Non pertinent | `setting_call` | Aucune | Personne | Aucun | Résolue | Mini note + qualification `not_relevant` | Stopper relances |
| Appel setting terminé | `setting_call_completed` | Ne plus contacter | `setting_call` | Aucune | Personne | Aucun | Résolue | Mini note + qualification `do_not_contact` | Stop strict |
| RDV closing arrive | `closing_call_due` | Appel à faire | `closing_call` | Selon résultat appel | Closer | Maintenant | Ouverte | Appel | Option `in_progress` si pris en main |
| Appel closing terminé | `closing_call_completed` | Signé | `closing_call` | Aucune | Personne | Aucun | Résolue | Mini note + qualification closer `signed` | Vente gagnée, stopper relances |
| Appel closing terminé | `closing_call_completed` | Va signer | `closing_call` | `follow_up` | Setter 2 | +72h | Ouverte | Mini note + qualification closer `will_sign` | Séquence closer will sign |
| Appel closing terminé | `closing_call_completed` | Non pertinent | `closing_call` | Aucune | Personne | Aucun | Résolue | Mini note + qualification closer `not_relevant` | Stopper relances |
| Appel closing terminé | `closing_call_completed` | Pas de réponse | `closing_call` | `follow_up` | Setter 2 | +72h | Ouverte | Mini note | Relance post-closing |
| Date de cours approche | `course_start_approaching` | Lead non signé, date pertinente connue | `follow_up` lead-relative concurrente | `follow_up` cours | Setter 2 ou IA | J-14/J-7/J-3/J-1 | Ouverte | Template cours | La relance cours gagne le conflit |
| Qualification stop à tout moment | `qualification_updated` | `not_relevant`, `do_not_contact`, `signed` | Toutes actions ouvertes | Aucune | Personne | Aucun | Résolue | Qualification | Stopper relances |
| Conversation résolue manuellement | `conversation_resolved` | Utilisateur clôture | Toutes actions ouvertes | Aucune | Personne | Aucun | Résolue | Option note | Historiser la résolution |
| Conversation rouverte manuellement | `conversation_reopened` | Utilisateur rouvre | Aucune | Action à choisir | Utilisateur courant ou responsable choisi | Maintenant ou planifié | Ouverte | Raison de réouverture | Éviter conversation ouverte sans action |
| Hors horaires | `business_hours_closed` | Prospect écrit hors disponibilité | Aucune ou action active | `reply` planifiée | Backup ou responsable prochain créneau | Prochain créneau ouvré | Ouverte | Option template hors horaire | Message automatique possible |
| Absence responsable | `assignee_unavailable` | Responsable absent | Action active | Même action transférée | Backup | Même échéance ou prochain créneau | Inchangée | Règle de backup | Historiser transfert |

## Séquences Principales

### Lead Sans Réponse Initiale

Déclencheur : message automatique envoyé par SchoolDrive/Twilio, aucun message entrant.

Chaîne :

1. `follow_up` Setter 2 à +72h.
2. `follow_up` Setter 2 à +72h.
3. `follow_up` Setter 2 à +72h.
4. `follow_up` Setter 2 à +7j.
5. `follow_up` Setter 2 à +7j.
6. `follow_up` Setter 2 à +30j.
7. Stop.

Stop si : réponse entrante, `not_relevant`, `do_not_contact`, `signed`.

### Conversation Setter Sans Suite

Déclencheur : Setter 1 a échangé, aucun RDV posé, plus d'échange depuis 72h.

Même cadence que ci-dessus.

Stop si : réponse entrante, RDV setting, handoff closer, `not_relevant`, `do_not_contact`.

### Closer Va Signer

Déclencheur : qualification closer = `will_sign`.

Même cadence que ci-dessus, portée par Setter 2.

Stop si : `signed`, réponse entrante nécessitant humain, `do_not_contact`, `not_relevant`.

### Date De Cours

Déclencheur : date de début de cours connue depuis SchoolDrive.

Cadence à confirmer : J-14, J-7, J-3, J-1.

Règle : une relance de cours gagne toujours contre une relance relative au lead. La relance perdante est annulée, pas décalée.

## Points Encore À Confirmer

- Horaires exacts de chaque collaborateur.
- Backup principal et secondaire de chaque collaborateur.
- Message ou template hors horaire.
- Données SchoolDrive exactes pour choisir la date de cours pertinente d'un simple `lead`.
- URL SchoolDrive exacte du prospect.
- Données Notion à synchroniser ou seulement afficher comme historique.

## Points Tranchés Depuis Validation

- Après la dernière relance sans réponse, la conversation passe en `resolved` avec le motif `sequence_completed_no_reply`.
- Les outcomes `setting_call` sont : passer au closing, pas joint, pas prêt / pas de suite claire, non pertinent, ne plus contacter.
- Les outcomes `closing_call` sont : signé, va signer, pas joint, joint mais pas décidé, non pertinent.
- Une mini note est obligatoire après un appel.
- Tous les utilisateurs peuvent créer ou demander un template.
- Une action de template apparaît dans la file seulement si elle bloque réellement une relance.
- `Ne plus contacter` est un statut de contact séparé, pas une qualification commerciale.

## Implications Techniques V1

À implémenter ensuite :

1. Continuer à durcir les statuts persistés `planned`, `cancelled`, `blocked`, `in_progress`.
2. Ne pas stocker `due` comme statut ; calculer `À faire` depuis `due_at`.
3. Continuer à créer l'action suivante à partir de la table de transitions.
4. Historiser toutes les transitions dans `lead_events`.
5. Afficher un historique lisible qui mélange actions, messages, qualifications et notes.
6. Garder l'interface simple : l'utilisateur choisit un résultat, le système crée la suite.
