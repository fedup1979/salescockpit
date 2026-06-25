# Sales Cockpit - Protocole de test manuel V1

Objectif : valider l'expérience V1 de bout en bout avec des faux prospects restaurables, puis terminer par deux tests réels depuis le site web : un lead et une préinscription.

## Validation automatisée courante

Dernière validation locale connue : `205 passed`, `compileall` OK.

Avant une validation manuelle propre :

```powershell
.\.venv\Scripts\python.exe scripts\reset_demo.py
```

Mot de passe local : `ChangeMe!2026`.

Le script restaure le jeu de faux prospects. Si un test manuel pollue l'état, relancer `reset_demo.py` avant de recommencer.

La suite automatisée couvre notamment :

- nouveau rendez-vous après ancien no-show, avec compteur remis à zéro par `call_cycle_id` ;
- migration des anciennes règles de flux et désactivation de `post_call_undecided` ;
- approbation/synchronisation Twilio qui débloque une demande de template liée ;
- garde-fous WhatsApp qui bloquent les relances excessives sans bloquer une réponse humaine ;
- cours complet avec appel déjà planifié ;
- session de référence dépassée qui crée une action admin ;
- inbound pendant relance bloquée par absence de template ;
- outbox qui conserve un message en `send_error` si Twilio échoue après création locale ;
- idempotence Twilio inbound et webhook SchoolDrive.

## Format de retour

```text
P0 Restauration :
P1 Admin :
P2 Setter I réponse entrante :
P3 Setter I rendez-vous setting :
P4 Setter II relance modèle :
P5 Demande de modèle :
P6 Setting vers closing :
P7 Closing signé / va signer :
P8 Ne plus contacter qui réécrit :
P9 Clore / réactiver :
P10 Lead réel site web :
P11 Préinscription réelle site web :
Bugs / confusions :
```

## Faux prospects restaurables

Utiliser les fiches de démonstration suivantes après `reset_demo.py` :

- `Léa Martin` ou `Inconnu(e)` : réponse entrante Setter I ;
- `Aline Favre` : relance Setter II avec fenêtre WhatsApp fermée ;
- `Thomas Girard` : demande de modèle ;
- `Nadia Keller` : appel setting à documenter ;
- `Nicolas Meyer` : appel closing à documenter ;
- `Hugo Muller` : statut **Ne plus contacter** qui réécrit ;
- `Chloé Schmid` ou `Irina Lopes` : clôture et réactivation.
- `Marc Dubois` : follow-up futur avec fenêtre WhatsApp ouverte ;
- `Sarah Perrin` : follow-up dû après absence de réponse ;
- `Aline Favre` : follow-up dû avec fenêtre WhatsApp fermée ;
- `Camille Laurent` : follow-up dû avec fenêtre WhatsApp ouverte ;
- `Romain Blanc` : appel setting non joint, rappel futur ;
- `Luc Moreau` : appel setting dû maintenant ;
- `Émilie Morel` : appel closing non joint, rappel futur ;
- `Mathieu Garnier` : closing `Va signer`, relance post-closing ;
- `Sonia Mercier` : reprise manuelle setter ;
- `Yves Caron` : reprise manuelle closer ;
- `Emma Complet` : session complète, relances stoppées, revue humaine ;
- `Rita Roadmap` : produit Roadmap hors flux V1, revue humaine.

## P0 Restauration

Compte : `francois.dupuis@essr.ch`.

1. Relancer le jeu de démo :

```powershell
.\.venv\Scripts\python.exe scripts\reset_demo.py
```

2. Ouvrir l'application locale.
3. Se connecter.
4. Vérifier que les faux prospects listés ci-dessus existent.

Résultat attendu : le protocole démarre depuis un état connu et restaurable.

## P1 Admin

Compte : `francois.dupuis@essr.ch`.

1. Ouvrir `Admin`.
2. Vérifier que Tanjona existe avec le rôle `Setter II`.
3. Vérifier que `Admin` contient `État`, `Utilisateurs`, `Actions admin`, `Garde-fous`, `Signalements`, `Intégrations`.
4. Créer un signalement avec le bouton `Bug`.
5. Vérifier le signalement dans `Admin > Signalements`.
6. Vérifier les horaires dans `Pilotage > Logique métier`.

Résultat attendu : admin clair, bug enregistrable, signalements visibles, horaires visibles sans bascule automatique.

## P2 Setter I Réponse Entrante

Compte : `service.etudiants@essr.ch`.

1. Ouvrir `Tâches`.
2. Ouvrir `Léa Martin` ou `Inconnu(e)`.
3. Vérifier que le prospect attend une réponse.
4. Ajouter une note interne.
5. Dans `Conversation`, envoyer un message libre si la fenêtre WhatsApp est ouverte.
6. Ne choisir aucune suite commerciale dans `Conversation`.
7. Vérifier que l'action `Répondre au message` est clôturée.
8. Vérifier qu'une relance de sécurité `Échange setter sans suite` est créée automatiquement si aucun rendez-vous n'existe.

Résultat attendu : la réponse clôt l'action entrante et la suite par défaut est créée par la logique métier, pas par un choix manuel dans le fil.

## P3 Setter I Rendez-vous Setting

Compte : `service.etudiants@essr.ch`.

1. Repartir d'un faux prospect restauré ou d'un prospect Setter I encore actif.
2. Aller dans `Actions`.
3. Programmer un appel setting avec responsable, date, heure et note interne.
4. Vérifier que l'action future apparaît dans la fiche.
5. Déplacer le rendez-vous.
6. Vérifier que l'heure affichée change.
7. Annuler le rendez-vous avec une note interne.

Résultat attendu : la programmation, le déplacement et l'annulation d'un rendez-vous setting sont compréhensibles et laissent une trace.

## P4 Setter II Relance Modèle

Compte : `setter2@essr.ch`.

1. Ouvrir `Tâches`.
2. Vérifier que la file affichée est celle de Tanjona.
3. Ouvrir `Aline Favre`.
4. Vérifier que la fenêtre WhatsApp est fermée.
5. Vérifier que le message libre est impossible.
6. Choisir un modèle approuvé.
7. Vérifier l'aperçu avec placeholders remplis.
8. Envoyer le modèle.

Résultat attendu : la relance passe obligatoirement par un modèle, puis la prochaine action se met à jour.

## P5 Demande De Modèle

Compte : `setter2@essr.ch`.

1. Ouvrir `Thomas Girard`.
2. Aller dans `Conversation > Envoyer un modèle`.
3. Créer une demande de nouveau modèle.
4. Vérifier la confirmation.
5. Aller dans `Modèles`.
6. Vérifier la demande dans `Demandes de modèles à créer`.
7. Vérifier que la demande est visible et traitable par un admin.

Résultat attendu : la demande est visible dans `Modèles`. En staging/prod, seule l'approbation d'un vrai template Twilio peut débloquer une recommandation opérationnelle.

## P6 Setting Vers Closing

Compte : `service.etudiants@essr.ch`.

1. Ouvrir `Nadia Keller`.
2. Aller dans `Actions`.
3. Essayer d'enregistrer l'appel sans note.
4. Ajouter une mini-note.
5. Choisir `Passer au closing`, closer `Yasmine`.
6. Enregistrer.

Résultat attendu : la note est obligatoire, l'action setting est terminée, une action closing est créée pour Yasmine. La note apparaît dans la conversation si les notes internes sont affichées.

## P7 Closing Signé / Va Signer

Compte : `yasmine@essr.ch`.

1. Ouvrir `Nicolas Meyer`.
2. Aller dans `Actions`.
3. Essayer d'enregistrer sans note.
4. Ajouter une mini-note.
5. Tester `Signé` ou `Va signer`.

Résultat attendu : `Signé` termine la conversation sans prochaine action. `Va signer` crée une relance Setter II selon le flux post-closing.

## P8 Ne Plus Contacter Qui Réécrit

Compte : `service.etudiants@essr.ch`.

1. Ouvrir `Hugo Muller`.
2. Vérifier que l'envoi WhatsApp est bloqué tant que le statut `Ne plus contacter` existe.
3. Aller dans `Actions`.
4. Vérifier l'action de revue de contact.
5. Cliquer `Lever et répondre`.

Résultat attendu : le statut de contact est levé, une action `Répondre au message` est créée. L'envoi reste impossible avant la levée du statut.

## P9 Clore / Réactiver

Compte : `francois.dupuis@essr.ch`.

1. Aller dans `Inbox > Terminées`.
2. Ouvrir `Chloé Schmid` ou `Irina Lopes`.
3. Cliquer `Réactiver`.
4. Vérifier que le bouton reste bloqué sans note.
5. Ajouter une note interne et réactiver avec une prochaine action.
6. Cliquer `Clore la conversation`.
7. Vérifier que le bouton reste bloqué sans note.
8. Ajouter une note interne et clore.

Résultat attendu : réactivation et clôture exigent une note interne. Les notes apparaissent dans la conversation si les notes internes sont affichées.

## P10 Lead Réel Site Web

À exécuter seulement après réussite des faux prospects restaurables.

1. Depuis le site web, créer un vrai lead de test avec un nom explicite, par exemple `Test SalesCockpit Lead`.
2. Utiliser un numéro WhatsApp et une adresse e-mail de test contrôlés par l'équipe.
3. Attendre le webhook SchoolDrive.
4. Vérifier dans Sales Cockpit :
   - création ou mise à jour du lead ;
   - lien SchoolDrive présent ;
   - autoresponder SchoolDrive visible seulement s'il est réellement `sent` ;
   - action Setter II créée seulement si le scénario le prévoit ;
   - absence de doublon après rafraîchissement ou replay.
5. Envoyer une réponse WhatsApp depuis le numéro de test.
6. Vérifier qu'une action `Répondre au message` remonte côté Setter I.

Résultat attendu : un lead réel du site web arrive dans le cockpit avec les bons liens, statuts, messages et actions.

## P11 Préinscription Réelle Site Web

À exécuter après P10.

1. Depuis le site web, créer une vraie préinscription de test avec un nom explicite, par exemple `Test SalesCockpit Presubscription`.
2. Utiliser un numéro WhatsApp et une adresse e-mail de test contrôlés par l'équipe.
3. Attendre le webhook SchoolDrive.
4. Vérifier dans Sales Cockpit :
   - création ou mise à jour de la préinscription ;
   - lien SchoolDrive présent ;
   - cours, session et date de début corrects ;
   - capacité/session full correctement reflétée si SchoolDrive l'envoie ;
   - action commerciale créée seulement si la préinscription reste traitable ;
   - absence de doublon après rafraîchissement ou replay.
5. Si SchoolDrive peut envoyer un événement de signature/enrolment de test, le déclencher.
6. Vérifier que Sales Cockpit termine ou protège la conversation selon le statut reçu.

Résultat attendu : une préinscription réelle du site web arrive dans le cockpit, reste rattachée à SchoolDrive et réagit correctement aux signaux de capacité et d'inscription.
