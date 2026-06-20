# Sales Cockpit - Protocole de test court

Objectif : tester un maximum de boutons, fonctions, actions et transitions avec un minimum de clics.

Avant une validation propre :

```powershell
.\.venv\Scripts\python.exe scripts\reset_demo.py
```

Mot de passe local : `ChangeMe!2026`.

## Format de retour

```text
P0 Admin :
P1 Mihary réponse client :
P2 Tanjona relance modèle :
P3 Demande de modèle :
P4 Setting call vers closing :
P5 Closing signé / va signer :
P6 Ne plus contacter qui réécrit :
P7 Clore / Réactiver :
Bugs / confusions :
```

## P0 Admin

Compte : `francois.dupuis@essr.ch`.

1. Ouvrir `Admin`.
2. Vérifier que Tanjona existe avec le rôle `Setter II`.
3. Vérifier `Règles métier > Horaires et bascules`.
4. Créer un signalement avec le bouton `Bug`.
5. Vérifier le signalement dans `Admin > Bugs & logs`.

Résultat attendu : admin clair, bug enregistrable, logs visibles.

## P1 Mihary Réponse Client

Compte : `service.etudiants@essr.ch`.

1. Ouvrir `Tâches`.
2. Ouvrir `Léa Martin` ou `Inconnu(e)`.
3. Vérifier que le client attend une réponse.
4. Ajouter une note privée.
5. Dans `Actions`, choisir la suite après réponse.
6. Si le prospect accepte un appel, choisir `RDV setting fixé : créer un appel`.
7. Dans `Conversation`, envoyer le message libre.

Résultat attendu : la réponse clôt l'action `Répondre au message`. La prochaine action correspond au choix fait dans `Actions`.

## P2 Tanjona Relance Modèle

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

## P3 Demande De Modèle

Compte : `setter2@essr.ch`.

1. Ouvrir `Thomas Girard`.
2. Aller dans `Conversation > Envoyer un modèle`.
3. Créer une demande de nouveau modèle.
4. Vérifier la confirmation.
5. Aller dans `Modèles`.
6. Vérifier la demande dans `Demandes de modèles à créer`.
7. Vérifier que la demande est visible et traitable par un admin.

Résultat attendu : la demande est visible dans `Modèles`. En staging/prod, seule l'approbation d'un vrai template Twilio peut débloquer une recommandation opérationnelle.

## P4 Setting Call Vers Closing

Compte : `service.etudiants@essr.ch`.

1. Ouvrir `Nadia Keller`.
2. Aller dans `Actions`.
3. Essayer d'enregistrer l'appel sans note.
4. Ajouter une mini-note.
5. Choisir `Passer au closing`, closer `Yasmine`.
6. Enregistrer.

Résultat attendu : la note est obligatoire, l'action setting est terminée, une action closing est créée pour Yasmine. La note apparaît dans la conversation si les notes internes sont affichées.

## P5 Closing Signé / Va Signer

Compte : `yasmine@essr.ch`.

1. Ouvrir `Nicolas Meyer`.
2. Aller dans `Actions`.
3. Essayer d'enregistrer sans note.
4. Ajouter une mini-note.
5. Tester `Signé` ou `Va signer`.

Résultat attendu : `Signé` termine la conversation sans prochaine action. `Va signer` crée une relance Tanjona selon le flux post-closing.

## P6 Ne Plus Contacter Qui Réécrit

Compte : `service.etudiants@essr.ch`.

1. Ouvrir `Hugo Muller`.
2. Vérifier que l'envoi WhatsApp est bloqué tant que le statut `Ne plus contacter` existe.
3. Aller dans `Actions`.
4. Vérifier l'action de revue de contact.
5. Cliquer `Lever et répondre`.

Résultat attendu : le statut de contact est levé, une action `Répondre au message` est créée. L'envoi reste impossible avant la levée du statut.

## P7 Clore / Réactiver

Compte : `francois.dupuis@essr.ch`.

1. Aller dans `Inbox > Terminées`.
2. Ouvrir `Chloé Schmid` ou `Irina Lopes`.
3. Cliquer `Réactiver`.
4. Vérifier que le bouton reste bloqué sans note.
5. Ajouter une note et réactiver avec une prochaine action.
6. Cliquer `Clore la conversation`.
7. Vérifier que le bouton reste bloqué sans note.
8. Ajouter une note et clore.

Résultat attendu : réactivation et clôture exigent une note. Les notes apparaissent dans la conversation si les notes internes sont affichées.
