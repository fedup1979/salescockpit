# Sales Cockpit - Protocole E2E V1

Ce protocole formalise le parcours de test décrit par François. Il doit pouvoir être exécuté manuellement sur staging, puis automatisé plus tard par Playwright ou par un agent navigateur.

Environnement cible actuel : `http://139.59.158.77:8502`.

Avant un passage complet, restaurer les faux prospects :

```powershell
.\.venv\Scripts\python.exe scripts\reset_demo.py
```

Sur staging, le reset doit être lancé sur le serveur avec l'environnement staging chargé. Il ne doit réinitialiser que les prospects `SD-DEMO-*`.

## Principes De Test

- Tester séquentiellement, sans sauter d'étape.
- À chaque action, vérifier trois choses : statut du parcours, prochaine action, trace dans `Journal` ou `Admin`.
- Les messages adressés aux prospects doivent toujours vouvoyer.
- Les tests internes utilisent les faux prospects restaurables.
- Les deux derniers tests seulement utilisent les vrais formulaires du site web : un lead et une préinscription.
- Dans une batterie complète demandée par François, ces deux inscriptions réelles ESSR sont obligatoires. Elles doivent être faites sur les deux URL indiquées et avec les e-mails indiqués pour le test, car ces inscriptions sont ensuite supprimées automatiquement dans le système.
- Les mappings Twilio réels et les templates ESSR ne doivent pas être modifiés pendant ce protocole.

## Comptes

- Admin François : `francois.dupuis@essr.ch`
- Setter I : `service.etudiants@essr.ch`
- Setter II : `setter2@essr.ch`
- Closer : `yasmine@essr.ch`

Mot de passe local seed : `ChangeMe!2026`.

Sur staging, utiliser les mots de passe réels via variables d'environnement ou coffre d'équipe. Ne pas supposer que `ChangeMe!2026` fonctionne sur staging.

## Checklist De Retour

```text
P0 Reset staging :
P1 Admin / navigation / bug :
P2 Droits par rôle :
P3 Setter I réponse entrante :
P4 Setter I appels setting :
P5 Setter I reprise manuelle :
P6 Closer appels closing :
P7 Setter II relance :
P8 Template request :
P9 Clore / réactiver :
P10 Journal / recherche / inbox / pilotage :
P11 Lead réel site web :
P12 Préinscription réelle site web :
Bugs / confusions :
```

## P0 Reset Staging

Compte : François admin.

1. Restaurer les scénarios démo.
2. Ouvrir staging.
3. Se connecter.
4. Aller dans `Tâches`.
5. Vérifier que les prospects `SD-DEMO-4001` à `SD-DEMO-4025` sont présents via la recherche ou les files.

Résultat attendu : le protocole démarre depuis un état connu, sans doublons évidents, avec `pre_cutover_check` vert.

## P1 Admin / Navigation / Bug

Compte : François admin.

1. Vérifier que la sidebar peut être pliée et rouverte.
2. Vérifier que les onglets et boutons radio de `Tâches` répondent.
3. Cliquer sur `Bug`.
4. Créer un bug :
   - titre : `Test fonction bug`
   - description : `démo`
   - attendu : `démo`
   - obtenu : `démo`
   - priorité : normale.
5. Aller dans `Admin > Signalements`.
6. Vérifier que le bug est visible avec statut `open`.
7. Aller dans `Tâches`.
8. Dans `Actions admin`, terminer l'action bug avec résolution `traité`.
9. Retourner dans `Admin > Signalements`.
10. Vérifier que le bug est passé en `resolved` et possède un `resolved_at`.

Résultat attendu : le signalement crée une action admin, l'action admin est visible pour tous les admins, et la résolution de l'action met à jour le signalement.

## P2 Droits Par Rôle

1. Se connecter comme François, Laura ou Tiago admin si les comptes sont disponibles.
2. Vérifier que chaque admin voit les mêmes actions admin ouvertes, même si elles sont assignées à un autre admin.
3. Se déconnecter.
4. Se connecter comme Setter I.
5. Vérifier que `Admin` n'est pas accessible.
6. Se connecter comme Closer.
7. Vérifier que seules les pages utiles au rôle sont accessibles.
8. Se connecter comme Setter II.
9. Vérifier que `Tâches`, `Modèles` si autorisé, `Mode d'emploi`, `Bug` et `Déconnexion` sont cohérents.

Résultat attendu : droits cohérents, aucun utilisateur commercial ne voit les écrans admin.

## P3 Setter I Réponse Entrante

Compte : Setter I.

1. Ouvrir `Tâches > À traiter`.
2. Ouvrir `Léa Martin` ou le prospect `Inconnu(e)`.
3. Vérifier que la prochaine action est `Répondre au message`.
4. Vérifier que le compteur `client attend depuis...` est cohérent avec l'heure du dernier message entrant.
5. Envoyer un message libre court, par exemple `Bonjour, merci pour votre message.`
6. Vérifier que la réponse est affichée dans la conversation.
7. Vérifier que l'action `reply` est terminée.
8. Vérifier que la prochaine action est cohérente : relance de sécurité si aucun rendez-vous n'existe, ou appel déjà planifié si un appel était déjà prévu.
9. Tester les onglets du fil de travail et vérifier que le prospect reste correctement sélectionné.

Résultat attendu : réponse libre possible seulement si la fenêtre WhatsApp est ouverte, action clôturée, suite métier cohérente.

## P4 Setter I Appels Setting

Compte : Setter I.

1. Ouvrir un prospect actif, par exemple `Luc Moreau` ou `Nadia Keller`.
2. Programmer un appel setting.
3. Vérifier que l'appel apparaît comme prochaine action planifiée.
4. Déplacer le rendez-vous avec note obligatoire.
5. Vérifier que l'heure est modifiée.
6. Replacer l'appel à une échéance due ou passée.
7. Documenter l'appel comme non joint.
8. Vérifier que le rappel suivant est programmé selon la règle métier.
9. Refaire un appel setting dû.
10. Documenter l'appel comme joint et `Passer au closing`, avec Yasmine comme closer.

Résultat attendu : programmation, déplacement, appel non joint et passage au closing fonctionnent et laissent une trace.

## P5 Setter I Reprise Manuelle

Compte : Setter I.

1. Ouvrir `Sonia Mercier` ou un cas indécis.
2. Vérifier l'action `Reprise manuelle setter`.
3. Documenter la reprise avec note obligatoire.
4. Vérifier que la prochaine étape de flux est créée si elle existe.
5. Ouvrir un prospect avec appel setting planifié.
6. Demander une reprise manuelle closer.
7. Vérifier que l'appel déjà planifié n'est pas supprimé sans raison.

Résultat attendu : reprise manuelle documentée, flux poursuivi, appel planifié préservé si applicable.

## P6 Closer Appels Closing

Compte : Yasmine closer.

1. Ouvrir `Yves Caron` ou `Nicolas Meyer`.
2. Programmer ou ouvrir un appel closing dû.
3. Documenter l'appel avec note obligatoire.
4. Tester `Va signer`.
5. Vérifier que le parcours passe à `va signer`.
6. Vérifier qu'une relance Setter II est créée.
7. Tester sur un autre cas `Signé`.
8. Vérifier que la conversation est terminée et qu'aucune relance commerciale n'est ouverte.

Résultat attendu : closing documenté, qualification cohérente, relance post-closing ou fermeture selon l'issue.

## P7 Setter II Relance

Compte : Tanjona Setter II.

1. Ouvrir `Tâches`.
2. Ouvrir une relance due, par exemple `Aline Favre` ou `Camille Laurent`.
3. Vérifier l'état de la fenêtre WhatsApp.
4. Si la fenêtre est fermée, vérifier que le message libre est impossible.
5. Choisir un template réel approuvé.
6. Vérifier l'aperçu et les variables.
7. Envoyer la relance.
8. Vérifier que la prochaine action du flux est créée ou que le flux se termine si c'était la dernière étape.

Résultat attendu : relance conforme aux règles WhatsApp, pas de message libre hors fenêtre, prochaine action cohérente.

## P8 Template Request

Compte : Setter II puis Admin.

1. Ouvrir un prospect sans template adapté, par exemple `Thomas Girard`.
2. Créer une demande de modèle avec un contexte précis.
3. Vérifier que l'action commerciale devient bloquée si elle dépend du template.
4. Se connecter comme admin.
5. Aller dans `Modèles`.
6. Vérifier que la demande existe.
7. Vérifier qu'elle peut être liée à un template Twilio réel approuvé sans créer de template fictif.

Résultat attendu : demande visible, action bloquée traçable, résolution possible par liaison à un template réel.

## P9 Clore / Réactiver

Compte : François admin.

1. Ouvrir une conversation active.
2. Tester `Clore la conversation` avec chaque motif sensible sur des cas distincts ou après reset.
3. Vérifier que la note est obligatoire.
4. Vérifier que le parcours, la qualification et le contact deviennent cohérents avec le motif.
5. Réactiver une conversation terminée.
6. Vérifier que la réactivation exige une note et une prochaine action.
7. Vérifier que le `Journal` contient la clôture et la réactivation.

Résultat attendu : impossible d'avoir une conversation ouverte sans action, ou terminée avec action active.

## P10 Journal / Recherche / Inbox / Pilotage

Compte : François admin, puis rôles commerciaux.

1. Tester `Inbox` avec `À traiter`, `En suspens`, `Terminées`, `Toutes`.
2. Tester la recherche par nom.
3. Ouvrir plusieurs conversations et vérifier que les fiches affichent le bon statut.
4. Aller dans `Pilotage`.
5. Vérifier que les onglets s'affichent sans erreur.
6. Aller dans `Mode d'emploi`.
7. Vérifier que les guides Setter I, Setter II, Closer et Administrateur sont présents.
8. Vérifier que les textes visibles aux prospects ou destinés aux prospects vouvoient toujours.

Résultat attendu : navigation stable, recherche utile, journal lisible au minimum, aucune copie prospect en tutoiement.

## P11 Lead Réel Site Web

À exécuter seulement après réussite des faux prospects. Obligatoire dans une batterie complète demandée par François.

1. Aller sur l'URL ESSR indiquée pour le test lead, par exemple la page `formation/secretaire-medical`.
2. Cliquer `Voir les dates de cours`.
3. Faire une demande d'information avec :
   - civilité : Monsieur ;
   - nom : `Test` ;
   - prénom : `Test` ;
   - email indiqué pour le test lead, ou email unique contrôlé avec suffixe `+test-salescockpit-YYYY-MM-DD-HH-MM-lead` si François demande une variante ;
   - téléphone contrôlé indiqué pour le test ;
   - commentaire ou champ distinctif si disponible.
4. Attendre l'arrivée SchoolDrive.
5. Vérifier dans Sales Cockpit :
   - lead créé ou upserté ;
   - lien SchoolDrive correct ;
   - cours et `course.id` cohérents si envoyés ;
   - autoresponder affiché seulement s'il est `sent` ;
   - action Setter II créée au bon moment ;
   - aucun doublon.

Résultat attendu : le lead réel arrive dans staging et suit le flux V1 attendu.

## P12 Préinscription Réelle Site Web

À exécuter après P11. Obligatoire dans une batterie complète demandée par François.

1. Aller sur l'URL ESSR indiquée pour le test préinscription et refaire le parcours avec l'option de préinscription.
2. Utiliser l'email indiqué pour le test préinscription, ou un email unique distinct avec suffixe `+test-salescockpit-YYYY-MM-DD-HH-MM-presubscription` si François demande une variante.
3. Utiliser le téléphone contrôlé indiqué pour le test.
4. Attendre l'arrivée SchoolDrive.
5. Vérifier dans Sales Cockpit :
   - `lead_type = presubscription` ;
   - lien SchoolDrive correct ;
   - cours, date de début, capacité, `course.is_full` si présents ;
   - pas de flux normal si Roadmap ou produit hors V1 ;
   - arrêt strict si `signed = true` ou `do_not_contact.blocked = true`.

Résultat attendu : la préinscription réelle arrive dans staging et respecte les signaux SchoolDrive `2.1`.

## Automatisation Playwright Cible

Protocole détaillé : `docs/PLAYWRIGHT_E2E_PROTOCOL.md`.

Le protocole doit être automatisé par blocs indépendants, pas comme un seul scénario géant fragile.

- `auth.spec`: login/logout, sidebar, droits par rôle.
- `admin.spec`: création bug, action admin globale, statut signalement résolu.
- `setter1.spec`: réponse entrante, contact bloqué levé, appels setting, reprise manuelle.
- `closer.spec`: closing signé, va signer, relance post-closing.
- `setter2.spec`: relance template, template request.
- `conversation.spec`: clore/réactiver, journal, recherche, inbox.
- `schooldrive-live.spec`: lead réel et préinscription réelle, à lancer seulement en mode manuel supervisé.

Chaque test automatisé doit :

- démarrer depuis `reset_demo.py` ou un fixture dédié ;
- se connecter avec un seul rôle ;
- chercher un prospect par nom stable ;
- faire une action ;
- vérifier un état visible et, si nécessaire, une donnée API/DB ;
- ne jamais envoyer de vrai WhatsApp hors environnement explicitement prévu.
