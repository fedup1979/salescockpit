# Sales Cockpit Business Logic

Ce document est la référence métier de Sales Cockpit.

Il formalise les règles validées avec François pour que l'interface, les tests, les connecteurs Twilio/SchoolDrive et la future automatisation Tanjona/IA puissent être construits sans interprétation implicite.

## Principes

- SchoolDrive reste la source de vérité des Leads et Préinscriptions.
- Le prospect commence le flux en remplissant un formulaire sur le site web.
- SchoolDrive crée ensuite soit un `lead`, soit une `presubscription`, puis envoie le premier WhatsApp automatique via Twilio.
- Les Leads viennent principalement des paid ads : Google Ads, Meta Ads ou Bing Ads.
- Les Préinscriptions viennent principalement de la recherche naturelle.
- Le cockpit ne remplace pas SchoolDrive. Il orchestre conversations, actions, qualification, relances et templates.
- Une conversation ouverte doit toujours avoir une prochaine action ouverte ou bloquée.
- Une conversation résolue ne doit pas avoir d'action opérationnelle ouverte.
- L'action est l'unité opérationnelle centrale du système.
- Les relances automatiques ne sont pas envoyées en V1. Le cockpit crée les tâches, l'humain envoie.
- Les données et transcripts sont conservés pour le futur apprentissage d'un setter IA.

## Concepts Métier

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
- `setting_call` : appel de setting par Setter 1.
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

- `neutral` : valeur par défaut.
- `eligible` : le prospect peut continuer.
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

Si un prospect `do_not_contact` écrit à nouveau, le système doit créer une action `contact_review` pour Setter 1. L'utilisateur lit le message et décide soit de maintenir le blocage, soit de lever le blocage et répondre.

## Calendriers

### Séquences WhatsApp Standard

Les séquences de relance standard suivent ce calendrier :

1. +72h
2. +72h
3. +72h
4. +7j
5. +7j
6. +30j
7. stop

Le délai se calcule depuis l'événement précédent de la même séquence.

Après la dernière relance, si le prospect ne répond pas, la conversation passe en `resolved` avec le motif `sequence_completed_no_reply`.

### Appels Non Joints

Si un prospect n'est pas joint lors d'un appel de setting ou closing :

1. rappel téléphonique +2h ouvrées ;
2. rappel téléphonique +24h ouvrées ;
3. si toujours non joint, passage à Tanjona pour relance WhatsApp +72h.

### Relances Liées Au Cours

Les relances liées au début du cours suivent ce calendrier par défaut :

1. J-14
2. J-7
3. J-3
4. J-1

Une relance liée au cours gagne toujours contre une relance relative au lead. En cas de conflit, la relance perdante est annulée.

## Templates

Tanjona doit relire la conversation avant d'envoyer une relance et sélectionner le template approprié.

Si la fenêtre WhatsApp est fermée, le système doit empêcher tout message libre et imposer un template approuvé.

Si aucun template adapté n'existe :

- l'action `follow_up` est mise en `blocked` ;
- une `template_request` est créée ;
- la demande est liée à l'action, à la conversation, au lead, à la séquence et à l'étape si ces informations existent ;
- l'action redevient exécutable lorsque le template est approuvé.

Statuts de demande de template :

- `to_create`
- `submitted`
- `approved`
- `rejected`
- `cancelled`

## Règles Validées

### Règle 1 : création du lead

Lorsque le prospect remplit un formulaire web et que SchoolDrive crée un Lead ou une Préinscription puis envoie le premier WhatsApp automatique, alors le cockpit ouvre une conversation et programme une relance pour Tanjona 72h après cet envoi, sauf si le prospect répond avant.

### Règle 2 : absence de réponse au message automatique

Lorsque les 72h suivant le premier WhatsApp automatique sont écoulées et que le prospect n'a pas répondu, alors Tanjona doit relire la conversation et relancer immédiatement avec le template approprié. Si aucun template n'existe, Tanjona doit créer une demande de template et la relance devient bloquée.

### Règle 3 : réponse entrante standard

Lorsque le prospect envoie un message WhatsApp entrant et que le contact est autorisé, alors la conversation passe immédiatement dans la file de Setter 1 avec une action `reply` due maintenant.

### Règle 4 : réponse entrante d'un prospect Ne plus contacter

Lorsque le prospect est marqué `do_not_contact` mais envoie un nouveau message entrant, alors le cockpit crée une action `contact_review` pour Setter 1. Aucune relance automatique ne doit être créée tant que Setter 1 n'a pas décidé de maintenir ou lever le blocage.

### Règle 5 : réponse sans rendez-vous

Lorsque Setter 1 répond au prospect mais ne fixe pas de rendez-vous de setting, alors l'action `reply` est terminée et une action `follow_up` est créée pour Tanjona 72h après le message sortant.

### Règle 6 : rendez-vous de setting fixé

Lorsque Setter 1 fixe un rendez-vous de setting avec le prospect, alors le cockpit termine l'action `reply` et crée une action `setting_call` pour Setter 1 à la date et l'heure du rendez-vous.

### Règle 7 : prospect non pertinent ou Ne plus contacter après échange écrit

Lorsque Setter 1 conclut après échange écrit que le prospect est `not_relevant` ou `do_not_contact`, alors le cockpit clôt la conversation, annule les actions ouvertes et arrête les relances futures.

### Règle 8 : relance due avec fenêtre ouverte

Lorsqu'une relance arrive à échéance et que la fenêtre WhatsApp est ouverte, alors Tanjona peut envoyer un message libre ou un template.

### Règle 9 : relance due avec fenêtre fermée

Lorsqu'une relance arrive à échéance et que la fenêtre WhatsApp est fermée, alors Tanjona ne peut envoyer qu'un template approuvé.

### Règle 10 : relance due sans template adapté

Lorsqu'une relance arrive à échéance, que la fenêtre WhatsApp est fermée et qu'aucun template adapté n'existe, alors l'action `follow_up` passe en `blocked` et une demande de template doit être créée.

### Règle 11 : template approuvé

Lorsqu'un template demandé pour débloquer une relance est approuvé, alors la demande passe en `approved` et l'action `follow_up` bloquée redevient ouverte.

### Règle 12 : relance envoyée et séquence non terminée

Lorsque Tanjona envoie une relance et que la séquence prévoit encore une étape, alors le cockpit termine la relance actuelle et programme la prochaine selon le calendrier de la séquence.

### Règle 13 : dernière relance envoyée

Lorsque Tanjona envoie la dernière relance prévue par une séquence et que le prospect ne répond toujours pas, alors le cockpit ne crée plus de prochaine action et marque la conversation comme résolue avec le motif `sequence_completed_no_reply`.

### Règle 14 : appel de setting vers closing

Lorsque Setter 1 termine un appel de setting et estime que le prospect doit passer au closing, alors le cockpit crée une action `closing_call` pour le closer, avec mini note obligatoire et qualification setter.

### Règle 15 : appel de setting non joint

Lorsque Setter 1 ne joint pas le prospect lors d'un appel de setting, alors le cockpit crée d'abord un rappel d'appel +2h ouvrées, puis +24h ouvrées, puis une relance WhatsApp Tanjona +72h si le prospect n'est toujours pas joint.

### Règle 16 : appel de setting sans suite claire

Lorsque Setter 1 joint le prospect mais qu'aucun rendez-vous de closing n'est fixé et que le prospect n'est pas disqualifié, alors le cockpit crée une relance Tanjona 72h après l'appel.

### Règle 17 : appel de setting terminal

Lorsque Setter 1 termine un appel de setting et qualifie le prospect comme `not_relevant` ou `do_not_contact`, alors le cockpit clôt la conversation et annule les relances futures.

### Règle 18 : closing signé

Lorsque le closer termine un appel de closing et que le prospect signe, alors le cockpit marque le prospect `signed`, clôt la conversation et annule les relances futures.

### Règle 19 : closing Va signer

Lorsque le closer termine un appel de closing et qualifie le prospect comme `will_sign`, alors le cockpit crée une relance post-closing pour Tanjona 72h après l'appel, puis suit la séquence `closer_will_sign`.

### Règle 20 : closing non joint

Lorsque le closer ne joint pas le prospect lors d'un appel de closing, alors le cockpit crée d'abord un rappel d'appel +2h ouvrées, puis +24h ouvrées, puis une relance WhatsApp Tanjona +72h si le prospect n'est toujours pas joint.

### Règle 21 : closing sans décision claire

Lorsque le closer joint le prospect mais qu'aucune décision claire n'est prise, alors le cockpit crée une relance Tanjona 72h après l'appel.

### Règle 22 : closing non pertinent

Lorsque le closer qualifie le prospect comme `not_relevant`, alors le cockpit clôt la conversation et annule les relances futures.

### Règle 23 : date de début de cours

Lorsqu'une date de début de cours approche et que le prospect n'a pas signé, alors le cockpit crée une relance liée au cours. Cette relance est prioritaire sur toute relance relative au lead.

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
- automatisation Tanjona ;
- apprentissage IA sur transcripts, actions, outcomes et notes.
