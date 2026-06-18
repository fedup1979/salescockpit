# Sales Cockpit - Plan de test V1

Ce plan sert à valider le comportement local mock avant connexion SchoolDrive, Twilio et Notion.

## Préconditions

- Lancer l'app locale : `streamlit run sales_cockpit\ui\app.py`.
- Se connecter avec le mot de passe local : `ChangeMe!2026`.
- Avant une session de validation complète, repartir d'un jeu de démo propre :
  `.\.venv\Scripts\python.exe scripts\reset_demo.py`.
- Vérifier d'abord les comptes suivants :
  - `service.etudiants@essr.ch` : Mihary, Setter 1.
  - `setter2@essr.ch` : Setter 2.
  - `yasmine@essr.ch` : closer.
  - `francois.dupuis@essr.ch`, `laura.escariz@essr.ch`, `tiago.jacobs@gmail.com` : admins.

## Données de démo

Les leads `SD-DEMO-*` sont des scénarios de test. Ils peuvent être réinitialisés par le seed de démo versionné.

| ID | Prospect | Objectif du cas |
|---|---|---|
| `SD-DEMO-4001` | Léa Martin | Message entrant récent, réponse immédiate Setter 1, fenêtre ouverte, signal client attend. |
| `SD-DEMO-4002` | Marc Dubois | Réponse déjà envoyée, relance Setter 2 en suspens. |
| `SD-DEMO-4003` | Sarah Perrin | Premier WhatsApp automatique sans réponse, relance 72h due, fenêtre jamais ouverte. |
| `SD-DEMO-4004` | Aline Favre | Relance due après échange ancien, fenêtre fermée, template obligatoire. |
| `SD-DEMO-4005` | Thomas Girard | Relance bloquée car aucun template adapté, demande de template à créer. |
| `SD-DEMO-4006` | Nadia Keller | Entretien setting planifié pour Mihary. |
| `SD-DEMO-4007` | Romain Blanc | Appel setting non joint, rappel setting futur. |
| `SD-DEMO-4008` | Nicolas Meyer | Entretien closing dû pour Yasmine. |
| `SD-DEMO-4009` | Émilie Morel | Closing non joint, rappel closing futur. |
| `SD-DEMO-4010` | Mathieu Garnier | Prospect `Va signer`, relance post-closing Setter 2. |
| `SD-DEMO-4011` | Océane Petit | Relance liée au début de cours, prioritaire sur relance lead. |
| `SD-DEMO-4012` | Hugo Muller | Prospect `Ne plus contacter` qui réécrit, revue contact Setter 1. |
| `SD-DEMO-4013` | Irina Lopes | Vente signée, conversation terminée, pas de prochaine action ouverte. |
| `SD-DEMO-4014` | Chloé Schmid | Séquence terminée sans réponse, conversation terminée. |
| `SD-DEMO-4015` | Philippe Aubert | Prospect non pertinent, conversation terminée. |
| `SD-DEMO-4016` | Inconnu(e) | Prospect sans nom identifié, fallback d'affichage `Inconnu(e)`. |
| `SD-DEMO-4017` | Laura Admin Démo | Tâche admin future pour Laura. |
| `SD-DEMO-4018` | François Admin Démo | Tâche admin due pour François. |
| `SD-DEMO-4019` | Tiago Admin Démo | Tâche admin future pour Tiago. |

## Parcours manuel minimal

Ce parcours est la validation manuelle prioritaire. Il couvre les décisions métier les plus risquées sans obliger à tester chaque bouton de chaque écran.

1. Se connecter comme Mihary avec `service.etudiants@essr.ch`.
   Vérifier `SD-DEMO-4001` ou `SD-DEMO-4016` pour une réponse immédiate, `SD-DEMO-4006` pour un entretien setting, et `SD-DEMO-4012` pour une revue `Ne plus contacter`.

2. Se connecter comme Setter 2 avec `setter2@essr.ch`.
   Vérifier `SD-DEMO-4004` pour une relance avec fenêtre fermée, `SD-DEMO-4005` pour une action bloquée par modèle manquant, `SD-DEMO-4010` pour une relance post-closing et `SD-DEMO-4011` pour une relance liée au début de cours.

3. Se connecter comme Yasmine avec `yasmine@essr.ch`.
   Vérifier `SD-DEMO-4008` pour un entretien closing et confirmer que la mini-note est obligatoire avant de terminer l'appel.

4. Aller dans Inbox > `Terminées`.
   Vérifier `SD-DEMO-4013`, `SD-DEMO-4014` et `SD-DEMO-4015`. Chaque conversation terminée doit pouvoir être lue, ne doit pas avoir de prochaine action ouverte, et doit proposer une réactivation avec choix d'une nouvelle action.

## Matrice prioritaire de scénarios

| Priorité | Scénario | Donnée démo | Résultat attendu |
|---|---|---|---|
| P0 | Message entrant chaud | `SD-DEMO-4001` Léa Martin ou `SD-DEMO-4016` Inconnu(e) | Apparaît dans `À traiter`, signal `Client attend`, fenêtre ouverte, message libre possible, puis relance +72h si réponse sans RDV. |
| P0 | Relance due hors fenêtre | `SD-DEMO-4004` Aline Favre | Relance Setter 2, fenêtre fermée, message libre bloqué, modèle approuvé obligatoire. |
| P0 | Modèle manquant | `SD-DEMO-4005` Thomas Girard | Action bloquée, raison visible, demande de modèle liée à la relance. |
| P0 | Prospect `Ne plus contacter` qui réécrit | `SD-DEMO-4012` Hugo Muller | Pas de relance automatique, action `Revue contact` pour Setter 1. |
| P0 | Setting vers closing | `SD-DEMO-4006` Nadia Keller | Mini-note obligatoire, résultat `Passer au closing`, création d'un entretien closing pour Yasmine. |
| P0 | Closing signé | `SD-DEMO-4008` Nicolas Meyer | Mini-note obligatoire, résultat `Signé`, conversation terminée, aucune prochaine action. |
| P1 | Closing `Va signer` | `SD-DEMO-4010` Mathieu Garnier | Relance Setter 2 selon la séquence `closer_will_sign`. |
| P1 | Relance début de cours | `SD-DEMO-4011` Océane Petit | Relance `course_start` visible et prioritaire. |
| P1 | Conversations terminées | `SD-DEMO-4013`, `SD-DEMO-4014`, `SD-DEMO-4015` | Présentes dans `Terminées`, pas de prochaine action, réactivation contrôlée. |
| P1 | Files par rôle | `SD-DEMO-4001..4019` | Mihary voit réponses/setting/revue contact, Setter 2 voit relances, Yasmine voit closing, admins voient leurs tâches démo. |

## Tests globaux d'interface

1. Connexion : chaque utilisateur peut se connecter avec son e-mail et le mot de passe local.
2. Navigation admin : l'ordre est `Tâches`, `Inbox`, `Modèles`, `Mode d'emploi`, `Admin`.
3. Navigation non-admin : `Admin` ne doit pas être visible.
4. File personnelle : à la connexion, `Tâches` affiche par défaut les actions assignées à l'utilisateur connecté.
5. Changement de responsable : choisir un autre responsable dans `Tâches`, aller dans `Inbox`, revenir dans `Tâches`, le choix doit persister.
6. Onglets de file : les onglets doivent être `À traiter`, `En suspens`, `Terminées`, `Toutes`.
7. Cartes : le bouton de sélection doit dire `Voir`, pas `Ouvrir`.
8. Détail prospect : le nom du prospect doit être lisible et aligné comme dans Inbox.
9. Prospect inconnu : aucun écran ne doit afficher `WhatsApp Unknown`; le fallback visible doit être `Inconnu(e)`.
10. Mode d'emploi : vérifier que la page explique Tâches vs Inbox, rôles, fenêtre WhatsApp, conversations, actions, chaînage et interruptions.
11. Bouton Bug : créer un signalement, vérifier qu'il apparaît dans Admin > Bugs & logs.

## Tests WhatsApp

1. Fenêtre ouverte : ouvrir Léa Martin. Le badge doit indiquer `Fenêtre ouverte` et `Ferme le ... à ...`.
2. Fenêtre fermée : ouvrir Aline Favre. Le badge doit indiquer `Fenêtre fermée` et `Fermée le ... à ...`.
3. Fenêtre jamais ouverte : ouvrir Sarah Perrin. Le badge doit indiquer `Fenêtre fermée` et `Jamais ouverte`.
4. Message libre autorisé : sur une fenêtre ouverte, le champ de message libre doit être utilisable.
5. Message libre bloqué : sur une fenêtre fermée, le message libre doit être bloqué et le système doit forcer l'utilisation d'un modèle approuvé.
6. Recherche de modèle : chercher un mot présent dans un template, par exemple `financement`, et vérifier que la liste filtre immédiatement.
7. Prévisualisation template : sélectionner un template, vérifier que le rendu avec placeholders remplis apparaît avant l'envoi.

## Tests Inbox

1. `À traiter` : vérifier que les conversations avec action due ou message client entrant apparaissent ici.
2. `En suspens` : vérifier que Marc Dubois ou Romain Blanc apparaît ici si l'action est future.
3. `Terminées` : vérifier qu'Irina Lopes, Chloé Schmid ou Philippe Aubert apparaît ici.
4. `Toutes` : vérifier que les conversations actives, en suspens et terminées sont visibles.
5. Signal urgent : Léa Martin et Inconnu(e) doivent montrer `Client attend depuis ...` et remonter en haut.
6. Conversation terminée : ouvrir Irina Lopes, vérifier que le bouton propose `Réactiver`.
7. Conversation active : ouvrir Léa Martin, vérifier que le bouton propose `Clore`.

## Tests Tâches

1. Mihary : se connecter comme Mihary et vérifier les actions `Répondre au message`, `Entretien Setting`, `Revue contact`.
2. Setter 2 : se connecter comme Setter 2 et vérifier les actions `Envoyer relance`, y compris due, future et bloquée.
3. Yasmine : se connecter comme Yasmine et vérifier les actions `Entretien Closing`.
4. Admins : se connecter comme Laura, François et Tiago et vérifier qu'une tâche personnelle de démonstration existe.
5. Action terminée : ouvrir l'onglet `Terminées` et vérifier qu'une ancienne action close reste consultable.
6. Prochaine action : la carte doit afficher le type d'action, la date/heure, et le responsable, sans texte ambigu du type `En retard depuis`.

## Tests Actions

1. `reply` avec réponse simple : ouvrir Léa Martin, envoyer un message libre avec le résultat `Réponse envoyée sans RDV`. Résultat attendu : l'action `reply` est terminée et une relance Setter 2 est créée à +72h.
2. `reply` avec RDV setting : ouvrir Inconnu(e) ou un autre cas de réponse, envoyer un message avec le résultat `RDV setting fixé`. Résultat attendu : une action `Entretien Setting` est créée à la date choisie.
3. `reply` terminale : envoyer une réponse avec résultat `Non pertinent` ou `Ne plus contacter`. Résultat attendu : la conversation est terminée et les relances futures sont annulées.
4. `follow_up` avec template disponible : ouvrir Aline Favre, envoyer un modèle approuvé. Résultat attendu : la relance est terminée et la prochaine étape de séquence est créée.
5. `follow_up` sans template : ouvrir Thomas Girard. Résultat attendu : l'action est bloquée et une demande de template est visible.
6. Template approuvé : dans Admin, passer la demande de template à `Approuvé`. Résultat attendu : la demande devient approuvée. V1 peut encore nécessiter une reprise manuelle de l'action bloquée.
7. `setting_call` vers closing : ouvrir Nadia Keller, terminer l'appel avec `Passer au closing`, ajouter une mini note. Résultat attendu : action `Entretien Closing` créée pour Yasmine.
8. `setting_call` non joint : ouvrir Romain Blanc, terminer le rappel avec `Pas joint`. Résultat attendu : rappel setting suivant ou relance Setter 2 selon le nombre de tentatives.
9. `closing_call` signé : ouvrir Nicolas Meyer, terminer l'appel avec `Signé`, ajouter une mini note. Résultat attendu : conversation terminée, vente gagnée, aucune prochaine action.
10. `closing_call` va signer : terminer un closing avec `Va signer`. Résultat attendu : relance Setter 2 selon la séquence `closer_will_sign`.
11. `closing_call` indécis : terminer un closing avec `Joint mais pas décidé`. Résultat attendu : relance Setter 2 à +72h.
12. `contact_review` : ouvrir Hugo Muller, choisir maintenir ou lever `Ne plus contacter`. Résultat attendu : maintien termine la conversation, levée crée une action de réponse.

## Tests Qualification

1. Qualification : changer `Qualification` à `Non pertinent`. Résultat attendu : relances bloquées et conversation terminée selon le workflow utilisé.
2. Contact : changer `Statut du lead` à `Ne plus contacter`. Résultat attendu : plus de relance automatique, mais un nouveau message entrant crée une revue humaine.
3. Parcours : ne modifier `Parcours` que pour corriger une étape traitée hors cockpit, par exemple un rendez-vous closing ajouté manuellement dans SchoolDrive.
4. Vérifier que `Température` n'apparaît plus dans l'interface.

## Tests Admin

1. Règles métier : vérifier que les règles de fenêtre, attribution, horaires et priorités sont lisibles.
2. Workflow : vérifier que les types d'actions, actions support, statuts et transitions sont visibles.
3. Séquences : vérifier les séquences `lead_no_reply`, `setter_no_next_step`, `closer_will_sign`, `course_start`.
4. Templates : vérifier que les templates de démo existent et que leurs statuts sont visibles.
5. Utilisateurs : vérifier que Laura apparaît en premier et que la matrice d'accès montre Admin partout, les autres sans Admin.
6. Horaires : vérifier que les lignes entreprise, Setter 1, Setter 2, Closer, absences/backups et répondeur hors horaire sont visibles.
7. Bugs & logs : vérifier les signalements bug et le journal utilisateur.

## Tests techniques

1. Lancer `pytest`.
2. Vérifier qu'aucun test ne dépend d'un ordre instable de conversations.
3. Vérifier que le seed ne touche pas les leads hors préfixe `SD-DEMO-*`.
4. Vérifier que la popup Streamlit `Clear caches` n'apparaît plus via le menu, avec `client.toolbarMode = "viewer"`.
5. Redémarrer Streamlit après modification de modules Python si une erreur d'import ancienne apparaît.
