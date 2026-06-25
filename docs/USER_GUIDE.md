# Sales Cockpit - Mode d'emploi V1

Sales Cockpit sert à piloter le travail commercial quotidien : qui contacter, quand, par quel canal, avec quelle preuve, et quelle suite créer. SchoolDrive reste la source de vérité pour les personnes, leads, préinscriptions, cours et inscriptions.

## Général

### Pages principales

- **Tâches** : page de travail principale. Elle affiche les actions ouvertes ou planifiées par collaborateur.
- **Inbox** : historique des conversations WhatsApp, conversations actives, conversations terminées et fiches à identifier.
- **Conversation** : fil complet du prospect, envoi WhatsApp libre ou par modèle, notes internes et contexte SchoolDrive.
- **Actions** : documentation des appels, déplacement ou annulation d'un rendez-vous déjà planifié, création d'une prochaine action standard quand une fiche doit être reprise.
- **Pilotage** : réglages métier des flux, cours, sessions et modèles.
- **Admin** : utilisateurs, actions admin, signalements, intégrations et garde-fous.

### Notions clés

**Parcours** : position commerciale du prospect, par exemple nouveau lead, échange setter, appel setting prévu, appel closing prévu, va signer, gagné ou perdu. Le parcours se met à jour via les actions et résultats métier. Il ne se force pas manuellement dans l'usage normal.

**Flux** : règle de suivi automatisée, par exemple lead sans réponse, échange setter sans suite, appel non joint, va signer ou début de cours. Un flux peut créer une ou plusieurs relances futures.

**Action** : travail concret à faire maintenant ou plus tard. Une action porte un prospect, un responsable, une échéance, un type de travail et une preuve attendue.

### WhatsApp

La fenêtre WhatsApp est ouverte pendant 24 heures après un message entrant du prospect. Quand elle est ouverte, l'équipe peut envoyer un message libre.

Quand elle est fermée, l'équipe doit utiliser un modèle WhatsApp approuvé. Si aucun modèle ne correspond, il faut créer une demande de modèle depuis la conversation ou l'action concernée. L'action reste bloquée jusqu'à disponibilité d'un modèle adapté.

Un message envoyé par l'équipe n'ouvre pas la fenêtre WhatsApp. Seule une réponse du prospect l'ouvre.

### Notes internes

Les notes internes servent à transmettre le contexte commercial à la personne suivante : résumé d'appel, objection, raison d'une relance, décision de clore, réactivation ou anomalie. Elles ne sont pas envoyées au prospect.

Quand un appel setting ou closing est documenté, la mini-note est obligatoire et apparaît ensuite dans le fil comme note interne.

### Conversations actives et terminées

Une conversation active doit avoir une prochaine action claire, sauf exception contrôlée : si un appel setting ou closing est déjà planifié et que le prospect écrit avant l'appel, Sales Cockpit crée une action urgente **Répondre au message** sans annuler l'appel planifié.

Une conversation terminée signifie qu'il n'y a plus rien à faire pour le moment. Elle peut être réactivée avec une note interne et une prochaine action.

La conversation active ou terminée est différente de la fenêtre WhatsApp ouverte ou fermée. Une conversation peut être active avec une fenêtre fermée ; dans ce cas, la suite passe par un modèle approuvé.

### Fiches à identifier

Quand un message WhatsApp arrive d'un numéro que Sales Cockpit ne rattache pas avec certitude, la fiche affiche **À identifier**. Cela peut vouloir dire qu'aucune fiche SchoolDrive ne correspond au numéro, ou que plusieurs fiches correspondent.

L'équipe peut répondre au message, mais les informations temporaires restent à vérifier dans SchoolDrive.

## Setter I

Setter I traite les messages entrants, les échanges écrits actifs et les appels de setting.

### Répondre à un message entrant

1. Ouvrir **Tâches**.
2. Prendre l'action **Répondre au message**.
3. Lire le fil, les notes internes, le contexte SchoolDrive et les éventuelles actions planifiées.
4. Répondre dans **Conversation** :
   - message libre si la fenêtre WhatsApp est ouverte ;
   - modèle approuvé si la fenêtre est fermée.
5. Ajouter une note interne si la réponse change le contexte ou explique la suite.

Après la réponse, Sales Cockpit clôt l'action de réponse. Si aucun rendez-vous n'est déjà planifié, une relance de sécurité peut être créée pour Setter II selon le flux applicable.

### Programmer un appel setting

Quand le prospect accepte un appel de qualification :

1. Aller dans **Actions**.
2. Utiliser le bloc de programmation d'action.
3. Choisir l'appel setting, le responsable, la date et l'heure.
4. Ajouter une note interne courte.
5. Enregistrer.

Le rendez-vous apparaît comme action future. L'action future sert surtout à documenter le résultat de l'appel.

### Documenter un appel setting

Au moment de l'appel :

1. Ouvrir l'action d'appel setting.
2. Renseigner une mini-note obligatoire.
3. Choisir le résultat métier :
   - passer au closing ;
   - rappeler plus tard ;
   - non joint ;
   - non pertinent ;
   - autre résultat disponible dans l'interface.
4. Enregistrer.

Si le prospect passe au closing, Sales Cockpit crée l'action closing pour le closer.

## Setter II

Setter II traite les relances structurées et les suites sans réponse.

### Envoyer une relance

1. Ouvrir **Tâches** avec la file Setter II.
2. Ouvrir l'action de relance.
3. Lire le fil, les notes internes et le modèle recommandé.
4. Vérifier la fenêtre WhatsApp :
   - fenêtre ouverte : message libre possible si c'est adapté ;
   - fenêtre fermée : modèle approuvé obligatoire.
5. Vérifier les placeholders du modèle.
6. Envoyer.

Après l'envoi, Sales Cockpit termine l'action et planifie la suite prévue par le flux, sauf si la relance termine le scénario.

### Demander un modèle

Si aucun modèle approuvé ne correspond :

1. Ouvrir la zone d'envoi de modèle.
2. Créer une demande de modèle avec le contexte et l'intention du message.
3. Enregistrer.

La demande devient visible côté admin. L'action commerciale reste bloquée tant qu'un modèle adapté n'est pas disponible.

### Quand le prospect répond

Si le prospect répond pendant une séquence de relance, les relances futures sont arrêtées et une action **Répondre au message** est créée pour Setter I. Si un appel setting ou closing était déjà planifié, il reste en place.

## Closer

Closer traite les appels de closing et les suites de signature.

### Documenter un appel closing

1. Ouvrir **Tâches** avec la file closer.
2. Ouvrir l'action d'appel closing.
3. Lire le fil, les notes internes, la qualification et le contexte SchoolDrive.
4. Renseigner une mini-note obligatoire.
5. Choisir le résultat métier :
   - signé ;
   - va signer ;
   - indécis ;
   - non joint ;
   - non pertinent.
6. Enregistrer.

**Signé** termine la conversation commerciale. **Va signer** crée une relance Setter II selon le flux post-closing. **Non joint** déclenche les rappels prévus. **Non pertinent** arrête les flux.

### Statuts sensibles

La qualification **Non pertinent** signifie que le prospect n'est pas un client potentiel. Les flux s'arrêtent.

Le statut **Ne plus contacter** doit être utilisé quand un prospect demande à ne plus être dérangé. Les flux s'arrêtent et l'envoi WhatsApp est bloqué.

Si un prospect marqué **Ne plus contacter** écrit à nouveau, Sales Cockpit crée une revue humaine au lieu de relancer automatiquement.

## Administrateur

### Pilotage

La page **Pilotage** sert à régler les flux commerciaux avec l'équipe :

- cours et catégories traités ;
- sessions de référence ;
- étapes de flux ;
- modèles recommandés par étape.

Les changements affectent les nouvelles actions créées après enregistrement. Les actions déjà ouvertes ne sont pas recalculées automatiquement en V1.

### Admin

La page **Admin** contient :

- **État** : santé générale de l'installation ;
- **Utilisateurs** : comptes, rôles et files ;
- **Actions admin** : demandes de modèles, bugs, incidents et revues ;
- **Garde-fous** : limites d'envoi WhatsApp ;
- **Signalements** : bugs remontés depuis l'interface ;
- **Intégrations** : SchoolDrive, Twilio et Front.

### Modèles WhatsApp

Seuls les admins créent, synchronisent et soumettent les modèles WhatsApp à Twilio. Les autres utilisateurs peuvent utiliser les modèles existants et demander un nouveau modèle.

### Signalements

Le bouton **Bug** dans la barre latérale sert à signaler une action, conversation, relance, statut ou intégration qui semble incorrect. Le signalement conserve le contexte courant et crée une action admin.
