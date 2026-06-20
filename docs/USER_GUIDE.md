# Sales Cockpit - Mode d'emploi utilisateur

Bienvenue dans Sales Cockpit. Cet outil sert à savoir très vite qui contacter, quand le faire, et quelle suite donner à chaque prospect. Il ne remplace pas SchoolDrive comme source de vérité, mais il regroupe le travail quotidien autour des conversations WhatsApp, des relances, des appels et des statuts commerciaux.

## Par où commencer

La page **Tâches** est la page principale. Quand vous vous connectez, commencez par cette page. Elle montre les actions qui vous sont attribuées : répondre à un message, envoyer une relance, documenter un appel setting, documenter un appel closing ou revoir un contact particulier. Par défaut, la page affiche votre propre file. Vous pouvez consulter la file d'une autre personne si nécessaire.

La page **Inbox** sert à retrouver les conversations WhatsApp. Elle est utile pour lire l'historique complet, chercher un prospect, vérifier une conversation terminée ou comprendre ce qui s'est passé avant une action. Dans **Tâches**, on travaille par action. Dans **Inbox**, on consulte par conversation.

## Les trois notions importantes

**Le Parcours** indique où en est le prospect commercialement : nouveau lead, échange avec setter, appel setting prévu, appel closing prévu, va signer, gagné ou perdu. Le parcours est affiché dans la fiche, mais il ne se force pas manuellement dans l'usage normal. Il change quand une action produit un résultat.

**Un Flux** est une règle de suivi. Par exemple : lead sans réponse initiale, échange setter sans suite, appel non joint, va signer ou début de cours. Un flux peut créer plusieurs relances futures. Les admins règlent les flux et les templates dans **Pilotage**.

**Une Action** est le travail concret à faire maintenant ou plus tard. C'est l'unité opérationnelle du cockpit. Une action dit qui doit faire quoi, pour quel prospect, et à quel moment.

## Les rôles commerciaux

**Setter I** répond aux messages entrants, mène les échanges écrits actifs et réalise les appels de setting. Dans le cockpit, ce rôle correspond principalement aux actions de réponse immédiate et aux appels setting à documenter.

**Tanjona, Setter II** gère les relances structurées. Elle relit la conversation, choisit le bon modèle WhatsApp quand la fenêtre est fermée, et crée une demande de modèle si aucun modèle existant ne convient.

**Closer** gère les appels de closing. Après l'appel, il indique le résultat : signé, va signer, indécis, non joint ou non pertinent. Cette décision détermine la suite du parcours.

## Fenêtre WhatsApp et modèles

La fenêtre WhatsApp est ouverte pendant 24 heures après un message entrant du prospect. Quand cette fenêtre est ouverte, vous pouvez envoyer un message libre.

Quand la fenêtre est fermée, vous ne pouvez pas envoyer de message libre. Vous devez utiliser un modèle WhatsApp approuvé. Si aucun modèle ne correspond à la situation, créez une demande de modèle depuis l'action concernée. L'action reste alors bloquée jusqu'à ce qu'un modèle adapté soit disponible.

Seuls les admins peuvent créer, synchroniser et soumettre des modèles à Twilio. Les autres utilisateurs peuvent chercher les modèles existants et demander un nouveau modèle si rien ne convient.

Dans le fil de conversation, les messages envoyés par l'équipe peuvent afficher des coches : une coche signifie envoyé, deux coches signifient reçu, deux coches bleues signifient lu, et un point d'exclamation signale un échec.

Le premier WhatsApp automatique envoyé après une demande d'information ne suffit pas à ouvrir la fenêtre. La fenêtre s'ouvre seulement quand le prospect répond.

## Conversations actives et terminées

Une conversation active doit normalement avoir une seule prochaine action principale. S'il y a une conversation active sans prochaine action, c'est une anomalie à signaler.

Il existe une exception importante : si un appel setting ou closing est déjà planifié et que le prospect écrit avant l'appel, le cockpit crée une action urgente **Répondre au message** sans annuler l'appel planifié. Après la réponse, si le rendez-vous reste inchangé, l'appel planifié redevient la prochaine action visible.

Une conversation terminée signifie qu'il n'y a plus rien à faire pour le moment. Elle peut être réactivée, mais il faut alors choisir immédiatement une prochaine action : répondre, relancer, documenter un appel setting ou documenter un appel closing.

La conversation active ou terminée est différente de la fenêtre WhatsApp ouverte ou fermée. Une conversation peut être active alors que la fenêtre WhatsApp est fermée. Dans ce cas, la suite doit passer par un modèle approuvé.

## Fiches à identifier

Quand un message WhatsApp arrive d'un numéro que le cockpit ne sait pas rattacher avec certitude, la fiche affiche **À identifier**. Cela veut dire soit qu'aucune fiche SchoolDrive connue ne correspond au numéro, soit que plusieurs fiches correspondent.

Dans ce cas, l'équipe peut répondre au message, mais elle doit compléter les informations temporaires dans **Statuts** : prénom, nom, cours ou catégorie, et une note d'identification. Ces informations servent à travailler tout de suite. Elles doivent rester à vérifier dans SchoolDrive.

## Actions, statuts et preuves

Les actions principales sont : répondre au message, envoyer une relance, documenter un appel setting, documenter un appel closing et revoir un contact.

Une action peut être planifiée, ouverte, en cours, terminée, annulée ou bloquée. Quand elle est terminée, elle doit laisser une preuve : message WhatsApp envoyé, résultat d'appel, mini-note, qualification ou demande de modèle.

Quand un appel est fixé, le cockpit crée une action future à l'heure du rendez-vous. Cette action ne signifie pas seulement "appeler" : elle signifie surtout **documenter le résultat de l'appel**. La mini-note est obligatoire. Elle permet au prochain utilisateur de comprendre rapidement ce qui s'est passé et pourquoi la suite a été créée.

Dans l'onglet **Actions**, utilisez **Programmer / attribuer une action** pour créer une prochaine action standard : répondre, relancer, planifier un appel setting ou planifier un appel closing. Le cockpit demande toujours l'action concernée, le responsable, la date et une note. Le parcours affiché en haut de la fiche est mis à jour par ces actions et ne se modifie pas manuellement.

Dans l'onglet **Statuts**, vous pouvez modifier la qualification commerciale et le statut de contact. La qualification répond à la question : ce prospect a-t-il une chance de s'inscrire ? Le statut de contact répond à la question : avons-nous encore le droit de lui écrire ?

## Chaînage des actions

Quand une action est terminée, le cockpit crée la suite selon la règle métier. Si vous répondez à un prospect sans fixer de rendez-vous et qu'aucun appel n'est déjà planifié, l'action de réponse est terminée et une relance est planifiée pour Tanjona. Si vous fixez un rendez-vous de setting, l'action de réponse est terminée et un appel setting est planifié. Si vous fixez directement un rendez-vous de closing, l'action de réponse est terminée et un appel closing est planifié pour le closer. Si un appel setting doit passer au closing, une action de closing est créée pour le closer.

Le chaînage peut être interrompu. Si le prospect répond, les relances futures sont arrêtées et la conversation remonte avec une action de réponse immédiate. Si un appel est déjà planifié, il reste en place. Si le prospect est marqué **Non pertinent**, **Ne plus contacter** ou **A signé**, les relances s'arrêtent. Si un prospect marqué **Ne plus contacter** écrit à nouveau, le cockpit crée une revue humaine au lieu de relancer automatiquement.

Le flux **Début de cours** est transversal. Il peut remplacer une relance lead ou préinscription si une relance liée au cours doit partir dans les 24 heures. Il ne remplace pas un appel setting ou closing déjà planifié.

## Pilotage pour les admins

La page **Pilotage** sert à régler les flux commerciaux avec Laura. Elle permet de définir les cours traités, les sessions de référence, les étapes de chaque flux et le template recommandé pour chaque étape. Ces réglages affectent seulement les nouvelles actions créées après enregistrement. Les actions déjà ouvertes ne sont pas recalculées automatiquement en V1.

## Signaler un problème

Le bouton **Bug** se trouve dans la barre latérale. Utilisez-le quand une action, une conversation, un statut, une relance ou un affichage vous semble incorrect. Décrivez ce que vous voyez et ce que vous attendiez. Le cockpit enregistre le signalement avec le contexte courant pour faciliter la vérification.
