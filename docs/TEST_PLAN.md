# Sales Cockpit - Parcours de test court

Objectif : valider vite si l'interface permet de savoir quoi faire, de répondre correctement, et de ne pas se tromper avec WhatsApp.

Avant de tester :

```powershell
.\.venv\Scripts\python.exe scripts\reset_demo.py
```

Mot de passe local : `ChangeMe!2026`.

## Parcours 1 : Mihary, message entrant chaud

Compte : `service.etudiants@essr.ch`.

1. Ouvrir **Tâches**.
2. Trouver `Léa Martin` ou `Inconnu(e)`.
3. Vérifier que le client est clairement à traiter maintenant.
4. Ouvrir la conversation.
5. Vérifier que la fenêtre WhatsApp est ouverte.
6. Envoyer un message libre.
7. Dans **Actions**, vérifier que la suite choisie est compréhensible.

Résultat attendu : l'utilisateur comprend immédiatement qu'il faut répondre, le message peut être envoyé, et la prochaine action est cohérente.

## Parcours 2 : Tanjona, relance avec fenêtre fermée

Compte : `setter2@essr.ch`.

1. Ouvrir **Tâches**.
2. Trouver `Aline Favre`.
3. Vérifier que la fenêtre WhatsApp est fermée.
4. Vérifier que le message libre est bloqué.
5. Choisir un modèle approuvé.
6. Vérifier l'aperçu avec placeholders remplis.
7. Envoyer le modèle.

Résultat attendu : impossible de se tromper, la relance passe par un modèle, et la prochaine action est claire.

## Parcours 3 : Tanjona, aucun modèle ne convient

Compte : `setter2@essr.ch`.

1. Ouvrir `Thomas Girard`.
2. Aller dans **Conversation**, section **Envoyer un modèle**.
3. Créer une demande de nouveau modèle.
4. Aller dans **Admin > Templates** avec un admin.
5. Vérifier que la demande existe.

Résultat attendu : la demande est facile à créer, visible en admin, et ne ressemble pas à une action commerciale normale.

## Parcours 4 : Yasmine, closing

Compte : `yasmine@essr.ch`.

1. Ouvrir **Tâches**.
2. Trouver `Nicolas Meyer`.
3. Ouvrir l'action de closing.
4. Essayer de terminer sans note.
5. Ajouter une mini-note et choisir `Signé`.

Résultat attendu : la note est obligatoire, la conversation se termine, et il ne reste aucune prochaine action.

## Contrôle final ultra-court

Avec un compte admin :

1. Vérifier que `Tanjona` apparaît bien comme `Setter II`.
2. Vérifier que les horaires affichent :
   - entreprise : lundi-vendredi 08:00-20:00 ;
   - Mihary : 08:00-17:00 ;
   - Yasmine : 11:00-20:00 ;
   - Tanjona : 12:00-16:00.
3. Vérifier qu'une conversation active a une prochaine action.
4. Vérifier qu'une conversation terminée n'a pas de prochaine action.

Si ces quatre parcours passent, le prototype est assez clair pour continuer vers les corrections restantes avant staging.
