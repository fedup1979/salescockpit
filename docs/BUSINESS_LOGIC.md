# Sales Cockpit Business Logic

Ce document est la référence métier de Sales Cockpit.

Il formalise les règles validées avec François pour que l'interface, les tests, les connecteurs Twilio/SchoolDrive et la future automatisation Setter II/IA puissent être construits sans interprétation implicite.

## Principes

- SchoolDrive reste la source de vérité des Leads et Préinscriptions.
- Le prospect commence le flux en remplissant un formulaire sur le site web.
- SchoolDrive crée ensuite soit un `lead`, soit une `presubscription`, puis envoie le premier WhatsApp automatique via Twilio.
- Les Leads viennent principalement des paid ads : Google Ads, Meta Ads ou Bing Ads.
- Les Préinscriptions viennent principalement de la recherche naturelle.
- Le cockpit ne remplace pas SchoolDrive. Il orchestre conversations, actions, qualification, relances et templates.
- Une conversation ouverte doit toujours avoir une prochaine action principale non terminale.
- Exception : si un prospect écrit alors qu'un appel setting ou closing est déjà planifié, le cockpit peut avoir temporairement deux actions non terminales : une action urgente `reply` et l'appel déjà planifié. La réponse urgente ne doit pas annuler l'appel.
- Une conversation résolue ne doit pas avoir d'action opérationnelle ouverte.
- L'action est l'unité opérationnelle centrale du système.
- Les relances automatiques ne sont pas envoyées en V1. Le cockpit crée les tâches, l'humain envoie.
- Les données et transcripts sont conservés pour le futur apprentissage d'un setter IA.

## Concepts Métier

### Parcours, Flux, Actions

Sales Cockpit distingue trois objets métier :

- `Parcours` : état commercial du prospect, stocké dans `leads.sales_stage`. Il répond à la question : où en est le prospect ?
- `Flux` : scénario de suivi qui génère des actions futures, stocké techniquement dans `sequences` et `sequence_steps`. Il répond à la question : quelle règle crée la suite ?
- `Action` : travail concret à effectuer par une personne à une date donnée, stocké dans `tasks`. Elle répond à la question : qui doit faire quoi, quand ?

Le `Parcours` est affiché en lecture seule pour l'équipe commerciale. Le forçage manuel du parcours est un mécanisme de correction, pas un flux normal.

Le terme `séquence` reste un terme technique interne pour l'implémentation d'un flux. Dans l'interface métier et dans les échanges avec Laura, utiliser `Flux` ou `Scénario de suivi`.

### Conversation

La conversation a un statut interne :

- `open` : il reste quelque chose à faire.
- `resolved` : il n'y a plus d'action à faire maintenant.

Ce statut est différent de la fenêtre WhatsApp API.

### Fenêtre WhatsApp

La fenêtre WhatsApp est une contrainte technique :

- ouverte pendant 24h après un message entrant du prospect ;
- fermée si aucun message entrant récent n'existe ;
- message libre autorisé uniquement si elle est ouverte ;
- template approuvé obligatoire si elle est fermée.

### Action Principale

Actions principales V1 :

- `reply` : répondre à un message entrant.
- `follow_up` : relancer, généralement via template WhatsApp.
- `setting_call` : appel de setting par Setter I.
- `closing_call` : appel de closing par le closer.

### Action Support

Actions support :

- qualification ;
- statut de contact ;
- note manuelle ;
- création ou demande de template ;
- revue admin.

Une action support n'apparaît dans la file de travail que si elle bloque le flux principal.

### Qualification Commerciale

La qualification commerciale est séparée du statut de contact.

Valeurs V1 :

- `eligible` : valeur par défaut ; le prospect peut continuer.
- `not_relevant` : le prospect n'est pas une opportunité utile.
- `will_sign` : le closer estime que le prospect va signer.
- `signed` : la vente est gagnée.

`not_relevant` et `signed` arrêtent les relances.

### Statut De Contact

Le statut de contact est séparé de la qualification commerciale.

Valeurs V1 :

- `contact_allowed` : le prospect peut être contacté.
- `do_not_contact` : le prospect a demandé à ne plus être contacté.

`do_not_contact` bloque les relances automatiques.

Si un prospect `do_not_contact` écrit à nouveau, le système doit créer une action `contact_review` pour Setter I. L'utilisateur lit le message et décide soit de maintenir le blocage, soit de lever le blocage et répondre.

## Calendriers

### Flux WhatsApp Standard

Les flux de relance standard suivent ce calendrier :

1. T+72h
2. T+144h
3. T+216h
4. T+16j
5. T+23j
6. T+53j
7. stop

`T` est le déclencheur du flux : premier WhatsApp automatique, dernier message sortant sans suite, appel documenté comme indécis, ou qualification `will_sign` selon le flux. Le délai ne se calcule jamais depuis l'étape précédente.

Après la dernière relance, si le prospect ne répond pas, la conversation passe en `resolved` avec le motif `sequence_completed_no_reply`.

### Appels Non Joints

Si un prospect n'est pas joint lors d'un appel de setting ou closing :

1. rappel téléphonique +2h ouvrées ;
2. rappel téléphonique +24h ouvrées ;
3. si toujours non joint, passage vers le flux no-show correspondant, porté par Setter II.

### Relances Liées Au Cours

Les relances liées au début du cours suivent ce calendrier par défaut :

1. J-14
2. J-7
3. J-3
4. J-1

Une relance liée au cours gagne toujours contre une relance relative au lead/préinscription. En cas de conflit dans une fenêtre de 24h, la relance lead/préinscription perdante est annulée.

Une relance liée au cours ne remplace pas un appel setting ou closing déjà planifié. Si un appel est prévu, l'appel reste prioritaire et visible.

Le périmètre V1 des flux structurés est strict : `APP`, `FSM` et `AS`.

Roadmap, les produits sans cours, les catégories absentes et les catégories hors V1 sont stockés et visibles, mais ne déclenchent ni relance structurée ni revue admin automatique. Seule une réponse entrante du prospect crée une action `reply`.

Lorsqu'un Lead APP/FSM/AS arrive sans session précise, la session par défaut configurée dans Pilotage sert de couche de planification. La donnée SchoolDrive reste prioritaire dès qu'elle fournit une session, une date ou une capacité. Si SchoolDrive indique une session complète, c'est un hard stop de relance.

Plusieurs fiches actives pour la même personne et la même catégorie peuvent coexister en V1. Cette multiplicité ne crée pas de fusion, de relance ou de revue automatique. Une fiche non archivée signée dans la même catégorie bloque les relances concurrentes de cette catégorie. Les fiches archivées sont ignorées dans ces arbitrages.

## Templates

Setter II doit relire la conversation avant d'envoyer une relance et sélectionner le template approprié.

Si la fenêtre WhatsApp est fermée, le système doit empêcher tout message libre et imposer un template approuvé.

Si aucun template adapté n'existe :

- l'action `follow_up` est mise en `blocked` ;
- une `template_request` est créée ;
- la demande est liée à l'action, à la conversation, au lead, au flux et à l'étape si ces informations existent ;
- l'action redevient exécutable lorsque le template est approuvé et lié à la demande.

La synchronisation Twilio peut débloquer automatiquement une demande si elle trouve un template réel approuvé (`HX...`, non mock) déjà lié à la demande, ou si le nom exact du template approuvé apparaît dans la raison ou le contexte de la demande.

Statuts de demande de template :

- `to_create`
- `submitted`
- `approved`
- `rejected`
- `cancelled`

## Règles Validées

### Règle 1 : création du lead

Lorsque le prospect remplit un formulaire web et que SchoolDrive crée un Lead ou une Préinscription puis envoie le premier WhatsApp automatique, alors le cockpit ouvre une conversation et programme une relance pour Setter II 72h après cet envoi, sauf si le prospect répond avant.

### Règle 2 : absence de réponse au message automatique

Lorsque les 72h suivant le premier WhatsApp automatique sont écoulées et que le prospect n'a pas répondu, alors Setter II doit relire la conversation et relancer immédiatement avec le template approprié. Si aucun template n'existe, Setter II doit créer une demande de template et la relance devient bloquée.

### Règle 3 : réponse entrante standard

Lorsque le prospect envoie un message WhatsApp entrant et que le contact est autorisé, alors la conversation passe immédiatement dans la file de Setter I avec une action `reply` due maintenant.

Si un appel setting ou closing est déjà planifié, cet appel reste actif. L'action `reply` est une interruption urgente pour traiter le message entrant, pas un remplacement automatique de l'appel.

### Règle 4 : réponse entrante d'un prospect Ne plus contacter

Lorsque le prospect est marqué `do_not_contact` mais envoie un nouveau message entrant, alors le cockpit crée une action `contact_review` pour Setter I. Aucune relance automatique ne doit être créée tant que Setter I n'a pas décidé de maintenir ou lever le blocage.

### Règle 5 : réponse sans rendez-vous

Lorsque Setter I répond au prospect mais ne fixe pas de rendez-vous de setting, alors l'action `reply` est terminée et une action `follow_up` est créée pour Setter II 72h après le message sortant.

Exception : si cette action `reply` était une interruption pendant qu'un appel setting ou closing était déjà planifié, aucune relance Setter II n'est créée. L'appel planifié redevient la prochaine action.

### Règle 6 : rendez-vous de setting fixé

Lorsque Setter I fixe un rendez-vous de setting avec le prospect, alors le cockpit termine l'action `reply` et crée une action `setting_call` pour Setter I à la date et l'heure du rendez-vous.

### Règle 7 : prospect non pertinent ou Ne plus contacter après échange écrit

Lorsque Setter I conclut après échange écrit que le prospect est `not_relevant` ou `do_not_contact`, alors le cockpit clôt la conversation, annule les actions ouvertes et arrête les relances futures.

### Règle 8 : relance due avec fenêtre ouverte

Lorsqu'une relance arrive à échéance et que la fenêtre WhatsApp est ouverte, alors Setter II peut envoyer un message libre ou un template.

### Règle 9 : relance due avec fenêtre fermée

Lorsqu'une relance arrive à échéance et que la fenêtre WhatsApp est fermée, alors Setter II ne peut envoyer qu'un template approuvé.

### Règle 10 : relance due sans template adapté

Lorsqu'une relance arrive à échéance, que la fenêtre WhatsApp est fermée et qu'aucun template adapté n'existe, alors l'action `follow_up` passe en `blocked` et une demande de template doit être créée.

### Règle 11 : template approuvé

Lorsqu'un template demandé pour débloquer une relance est approuvé, alors la demande passe en `approved` et l'action `follow_up` bloquée redevient ouverte.

L'action admin liée à la demande est clôturée au même moment. Setter II retrouve alors la relance dans sa file, avec le template approuvé disponible.

### Règle 12 : relance envoyée et flux non terminé

Lorsque Setter II envoie une relance et que le flux prévoit encore une étape, alors le cockpit termine la relance actuelle et programme la prochaine selon le calendrier du flux.

### Règle 13 : dernière relance envoyée

Lorsque Setter II envoie la dernière relance prévue par un flux et que le prospect ne répond toujours pas, alors le cockpit ne crée plus de prochaine action et marque la conversation comme résolue avec le motif `sequence_completed_no_reply`.

### Règle 13 bis : garde-fous de volume WhatsApp

Les limites configurées dans Admin s'appliquent aux relances `follow_up`, pas aux réponses humaines urgentes. Le kill switch global bloque tout envoi WhatsApp. Les quotas par prospect/jour, prospect/semaine, global/jour et délai minimum entre relances empêchent l'emballement des relances, mais ne doivent pas empêcher Setter I de répondre à un prospect qui vient d'écrire, sauf si le statut `do_not_contact` ou le kill switch global bloque l'envoi.

### Règle 14 : appel de setting vers closing

Lorsque Setter I termine un appel de setting et estime que le prospect doit passer au closing, alors le cockpit crée une action `closing_call` pour le closer, avec mini note obligatoire et qualification setter.

### Règle 15 : appel de setting non joint

Lorsque Setter I ne joint pas le prospect lors d'un appel de setting, alors le cockpit crée d'abord un rappel d'appel +2h ouvrées, puis +24h ouvrées, puis bascule ensuite vers le flux `setting_call_not_reached` si le prospect n'est toujours pas joint.

Les rappels sont comptés par rendez-vous, pas globalement par prospect. Si le prospect reprend contact et qu'un nouveau rendez-vous est fixé, un nouveau cycle d'appel démarre avec un nouveau `call_cycle_id` et le compteur repart au rappel 1.

### Règle 16 : appel de setting sans suite claire

Lorsque Setter I joint le prospect mais qu'aucun rendez-vous de closing n'est fixé et que le prospect n'est pas disqualifié, alors le cockpit crée une reprise manuelle Setter I dans le flux `post_setting_undecided`.

Setter I doit relire la conversation, décider si une réponse personnalisée, un nouvel appel ou une autre suite est pertinente, puis terminer l'action avec une note obligatoire. Si le flux contient une étape suivante, le cockpit la crée ensuite.

### Règle 17 : appel de setting terminal

Lorsque Setter I termine un appel de setting et qualifie le prospect comme `not_relevant` ou `do_not_contact`, alors le cockpit clôt la conversation et annule les relances futures.

### Règle 18 : closing signé

Lorsque le closer termine un appel de closing et que le prospect signe, alors le cockpit marque le prospect `signed`, clôt la conversation et annule les relances futures.

### Règle 19 : closing Va signer

Lorsque le closer termine un appel de closing et qualifie le prospect comme `will_sign`, alors le cockpit crée une relance post-closing pour Setter II 72h après l'appel, puis suit le flux `closer_will_sign`.

### Règle 20 : closing non joint

Lorsque le closer ne joint pas le prospect lors d'un appel de closing, alors le cockpit crée d'abord un rappel d'appel +2h ouvrées, puis +24h ouvrées, puis bascule ensuite vers le flux `closing_call_not_reached` si le prospect n'est toujours pas joint.

Comme pour le setting, le compteur de rappels closing est scoped par rendez-vous. Un nouveau rendez-vous closing démarre un nouveau cycle.

### Règle 21 : closing indécis

Lorsque le closer joint le prospect mais qu'aucune décision claire n'est prise, alors le cockpit crée une reprise manuelle closer dans le flux `post_closing_undecided`.

Le closer doit relire la conversation et les éléments envoyés, décider si une reprise personnalisée peut réchauffer le prospect, puis terminer l'action avec une note obligatoire. Si le flux contient une étape suivante, le cockpit la crée ensuite.

### Règle 22 : closing non pertinent

Lorsque le closer qualifie le prospect comme `not_relevant`, alors le cockpit clôt la conversation et annule les relances futures.

### Règle 23 : date de début de cours

Lorsqu'une date de début de cours approche et que le prospect n'a pas signé, alors le cockpit crée une relance liée au cours. Cette relance est prioritaire sur toute relance relative au lead.

Cette priorité ne remplace pas un appel setting ou closing déjà planifié. L'appel reste l'action principale ; la relance cours attendra un prochain déclencheur ou une décision humaine.

Si la session de référence d'une catégorie est dépassée, le cockpit ne lance pas une relance liée à une ancienne session. Un admin peut corriger la session pour les futurs flux, sans recalcul automatique des actions ouvertes en V1.

### Règle 23 bis : cours complet dans SchoolDrive

Lorsque SchoolDrive indique que le cours ou la session est complet, Sales Cockpit arrête les relances commerciales ouvertes ou futures liées à cette session et rend la capacité visible. Il ne crée pas de revue admin automatique et ne propose pas automatiquement une autre session. Si le prospect écrit ensuite, l'inbound crée une action `reply` normale.

Limite V1 : Sales Cockpit dépend du dernier webhook SchoolDrive reçu. Il ne vérifie pas encore en live la capacité du cours juste avant l'envoi d'une relance Début de cours.

### Règle 23 ter : signaux terminaux SchoolDrive

Lorsque SchoolDrive indique qu'un prospect a signé, que le prospect ne doit plus être contacté, ou qu'un opt-out email/téléphone/WhatsApp existe, Sales Cockpit aligne son état sur SchoolDrive. Une signature clôt la conversation comme gagnée. Une fiche non archivée signée pour la même personne et la même catégorie bloque aussi les relances concurrentes de cette catégorie. Un signal `do_not_contact` ou opt-out clôt la conversation, bloque tous les canaux commerciaux et conserve une note de provenance.

Les fiches archivées ne déclenchent pas de nouveaux flux, ne créent pas de revue admin automatique et sont ignorées dans les arbitrages de signatures ou de fiches multiples.

### Règle 23 quater : hors V1, Roadmap et catégorie absente

Lorsque SchoolDrive envoie Roadmap, un produit sans cours, une catégorie absente ou une catégorie hors `APP` / `FSM` / `AS`, Sales Cockpit stocke la fiche, les messages et le transcript, mais ne crée ni relance structurée ni revue admin automatique. La seule exception est un message entrant du prospect : dans ce cas, le cockpit crée une action `reply` pour traiter l'inbound.

### Règle 24 : qualification terminale à tout moment

Lorsqu'un utilisateur applique une qualification ou un statut terminal, par exemple `not_relevant`, `signed` ou `do_not_contact`, alors le cockpit clôt la conversation et annule les actions ouvertes ou futures.

### Règle 25 : résolution manuelle

Lorsqu'un utilisateur marque une conversation comme résolue, alors il doit choisir un motif de résolution. Si le motif est `other`, `do_not_contact`, `handled_elsewhere` ou `error`, une note est obligatoire.

### Règle 26 : réouverture manuelle

Lorsqu'un utilisateur rouvre une conversation résolue, alors il doit immédiatement choisir une prochaine action principale, un responsable et une échéance.

### Règle 27 : hors horaires

Lorsqu'un prospect écrit hors horaires de travail, alors le cockpit peut envoyer un accusé de réception automatique et planifie la vraie réponse pour le prochain créneau ouvré ou le backup disponible.

### Règle 28 : absence du responsable

Lorsqu'un responsable est absent ou indisponible, alors le cockpit transfère ses actions ouvertes au backup configuré, sans changer la nature de l'action ni perdre l'historique.

## V1 Vs V2

V1 locale :

- créer les actions ;
- bloquer les erreurs évidentes ;
- afficher les règles dans Admin ;
- conserver l'historique ;
- ne pas envoyer automatiquement les relances.

V2 :

- envoi automatique de certaines relances ;
- règles horaires complètes ;
- backups configurables ;
- synchronisation Twilio templates ;
- synchronisation SchoolDrive et Notion ;
- automatisation Setter II ;
- apprentissage IA sur transcripts, actions, outcomes et notes.
