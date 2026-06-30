# Sales Cockpit - Protocole Playwright E2E

Objectif : transformer le protocole humain V1 en batterie Playwright automatisable, couvrant les rôles, les files de travail, les actions critiques, les signaux SchoolDrive et les deux tests réels site web.

Ce document est un protocole d'automatisation. Il ne remplace pas la décision humaine de cutover : il prépare une exécution reproductible, observable et bloquée par défaut dès qu'un test pourrait toucher un système réel.

## État Observé

Playwright est disponible localement dans `.Codex/playwright-runner`.

Probe réalisé sur staging :

- URL UI : `http://139.59.158.77:8502` ;
- l'écran de login se charge ;
- les sélecteurs suivants répondent :
  - `page.getByLabel("E-mail")` ;
  - `page.getByLabel("Mot de passe")` ;
  - `page.getByRole("button", { name: "Se connecter" })` ;
- les comptes opérationnels staging partagent le mot de passe seed affiché sur la page de login.

Conséquence : les tests Playwright ne doivent jamais hardcoder les mots de passe. Utiliser `SC_E2E_SHARED_PASSWORD`, ou les variables par rôle si un compte diverge.

## Garde-Fous

Les tests doivent refuser de démarrer si ces conditions ne sont pas satisfaites :

- `SC_E2E_BASE_URL` pointe explicitement vers staging, sauf `SC_E2E_ALLOW_PRODUCTION=true` ;
- `SC_E2E_ALLOW_PRODUCTION=true` est interdit dans CI par défaut ;
- tous les mots de passe viennent de variables d'environnement ;
- `reset_demo.py` a été exécuté avant les specs mutantes ;
- les specs mutantes ne ciblent que les prospects `SD-DEMO-*` ;
- aucune spec ne modifie les vrais mappings Twilio ESSR ;
- aucune spec ne crée ou soumet un vrai template Twilio ;
- les envois WhatsApp réels sont désactivés par défaut ;
- les tests site web réels sont désactivés par défaut en CI générique, mais ils sont obligatoires dans une batterie complète demandée par François.

Variables recommandées :

```powershell
$env:SC_E2E_BASE_URL = "http://139.59.158.77:8502"
$env:SC_E2E_API_BASE_URL = "http://139.59.158.77:8602"

$env:SC_E2E_ADMIN_EMAIL = "francois.dupuis@essr.ch"
$env:SC_E2E_SETTER1_EMAIL = "service.etudiants@essr.ch"
$env:SC_E2E_SETTER2_EMAIL = "setter2@essr.ch"
$env:SC_E2E_CLOSER_EMAIL = "yasmine@essr.ch"
$env:SC_E2E_SHARED_PASSWORD = "<mot de passe staging affiché sur la page de login>"

$env:SC_E2E_ALLOW_MUTATION = "true"
$env:SC_E2E_ALLOW_WHATSAPP_SEND = "false"
$env:SC_E2E_ALLOW_REAL_SITE = "false"
$env:SC_E2E_SITE_LEAD_URL = "<URL ESSR indiquée pour le test lead>"
$env:SC_E2E_SITE_PRESUBSCRIPTION_URL = "<URL ESSR indiquée pour le test préinscription>"
$env:SC_E2E_SITE_LEAD_EMAIL = "<email indiqué pour le test lead>"
$env:SC_E2E_SITE_PRESUBSCRIPTION_EMAIL = "<email indiqué pour le test préinscription>"
$env:SC_E2E_SITE_TEST_PHONE = "<numéro contrôlé>"
```

Si les comptes n'ont plus un mot de passe commun, remplacer `SC_E2E_SHARED_PASSWORD` par les variables spécifiques `SC_E2E_ADMIN_PASSWORD`, `SC_E2E_SETTER1_PASSWORD`, `SC_E2E_SETTER2_PASSWORD` et `SC_E2E_CLOSER_PASSWORD`.

Les specs qui cliquent réellement sur `Envoyer` doivent exiger `SC_E2E_ALLOW_WHATSAPP_SEND=true` et vérifier que le prospect appartient au jeu `SD-DEMO-*` ou à un identifiant live explicitement créé pour le test.

## Structure De Suite

Première suite exécutable : `tests/e2e/`.

Elle couvre déjà le smoke public, le login par rôle, la navigation principale, la régression du sélecteur de page supprimé, la terminologie du guide et l'absence de fragments HTML visibles dans les surfaces opérationnelles. Les scénarios mutateurs restent protégés par flags et doivent être enrichis progressivement depuis ce protocole.

Arborescence cible complète :

```text
tests/e2e/
  playwright.config.ts
  global.setup.ts
  fixtures/
    auth.ts
    cockpit.ts
    demoProspects.ts
  helpers/
    navigation.ts
    selectors.ts
    assertions.ts
    dates.ts
  specs/
    00-preflight.spec.ts
    01-auth-sidebar-role-access.spec.ts
    02-admin-bug-actions.spec.ts
    03-inbox-search-schooldrive.spec.ts
    04-setter1-reply-contact-setting.spec.ts
    05-setter1-manual-reprise-skip.spec.ts
    06-closer-closing.spec.ts
    07-setter2-followups-templates.spec.ts
    08-close-reactivate-terminal-states.spec.ts
    09-schooldrive-special-records.spec.ts
    10-admin-pilotage-models-guide.spec.ts
    11-live-website-lead-presubscription.spec.ts
```

Exécution cible :

```powershell
cd .Codex\playwright-runner
npx playwright test ..\..\tests\e2e\specs --config ..\..\tests\e2e\playwright.config.ts
```

## Stratégie De Sélecteurs

Streamlit rerender souvent le DOM. Les tests doivent utiliser les libellés visibles et attendre les textes métier, pas les classes CSS.

Préférer :

```ts
await page.getByLabel("E-mail").fill(email);
await page.getByLabel("Mot de passe").fill(password);
await page.getByRole("button", { name: "Se connecter" }).click();

await page.getByRole("button", { name: "Tâches" }).click();
await page.getByText("Léa Martin").first().click();
await expect(page.getByText("Répondre au message")).toBeVisible();
```

Éviter :

- sélecteurs `.stButton > button:nth-child(...)` ;
- indexes non justifiés ;
- `networkidle` seul après une action Streamlit ;
- tests qui supposent l'ordre exact d'une table si le tri métier peut changer.

Après chaque action qui déclenche Streamlit, attendre une preuve métier :

- texte de confirmation ;
- disparition de l'action ;
- apparition de la prochaine action ;
- changement de statut ;
- ligne dans `Journal` ;
- ligne dans `Admin > Signalements`.

## Helpers Obligatoires

Les helpers doivent masquer les détails répétitifs mais pas les assertions métier.

```ts
async function loginAs(page, role) {}
async function logout(page) {}
async function openPage(page, label) {}
async function openProspect(page, name) {}
async function expectSelectedProspect(page, name) {}
async function expectNextAction(page, label) {}
async function expectConversationStatus(page, statusLabel) {}
async function expectQualification(page, label) {}
async function expectContactStatus(page, label) {}
async function addInternalNote(page, text) {}
async function sendFreeform(page, text) {}
async function sendAttachment(page, filePath, caption) {}
async function requestTemplate(page, reason, context) {}
async function scheduleSettingCall(page, assignee, date, time, note) {}
async function scheduleClosingCall(page, assignee, date, time, note) {}
async function rescheduleCall(page, date, time, note) {}
async function documentSettingCall(page, outcome, note, next) {}
async function documentClosingCall(page, outcome, note, next) {}
async function closeConversation(page, reason, note) {}
async function reactivateConversation(page, nextAction, assignee, note) {}
async function skipCurrentFlowStep(page, note) {}
async function createBugReport(page, data) {}
async function completeAdminAction(page, title, resolutionNote) {}
```

Les helpers `sendFreeform`, `sendAttachment` et `sendTemplate` doivent vérifier `SC_E2E_ALLOW_WHATSAPP_SEND=true` avant tout clic final d'envoi réel.

## Matrice Démo

Après reset, la suite doit retrouver ces cas :

| ID | Prospect | Cas à couvrir |
|---|---|---|
| `SD-DEMO-4001` | Léa Martin | réponse entrante urgente Setter I |
| `SD-DEMO-4002` | Marc Dubois | follow-up futur, fenêtre WhatsApp ouverte |
| `SD-DEMO-4003` | Sarah Perrin | lead sans réponse initiale, relance due |
| `SD-DEMO-4004` | Aline Favre | relance due, fenêtre fermée, template obligatoire |
| `SD-DEMO-4005` | Thomas Girard | relance bloquée par template manquant |
| `SD-DEMO-4006` | Nadia Keller | appel setting planifié futur |
| `SD-DEMO-4007` | Romain Blanc | appel setting non joint, rappel futur |
| `SD-DEMO-4008` | Nicolas Meyer | appel closing dû |
| `SD-DEMO-4009` | Émilie Morel | appel closing non joint, rappel futur |
| `SD-DEMO-4010` | Mathieu Garnier | closing `Va signer`, relance post-closing |
| `SD-DEMO-4011` | Océane Petit | relance début de cours prioritaire |
| `SD-DEMO-4012` | Hugo Muller | `Ne plus contacter` qui réécrit |
| `SD-DEMO-4013` | Irina Lopes | signé terminal |
| `SD-DEMO-4014` | Chloé Schmid | conversation terminée réactivable |
| `SD-DEMO-4015` | Philippe Aubert | non pertinent terminal |
| `SD-DEMO-4016` | Inconnu(e) | inbound inconnu |
| `SD-DEMO-4017` | Laura Admin Démo | action admin assignée Laura |
| `SD-DEMO-4018` | François Admin Démo | action admin assignée François |
| `SD-DEMO-4019` | Tiago Admin Démo | action admin assignée Tiago |
| `SD-DEMO-4020` | Camille Laurent | relance due, fenêtre ouverte |
| `SD-DEMO-4021` | Luc Moreau | appel setting dû maintenant |
| `SD-DEMO-4022` | Sonia Mercier | reprise manuelle setter |
| `SD-DEMO-4023` | Yves Caron | reprise manuelle closer |
| `SD-DEMO-4024` | Emma Complet | cours complet, aucune revue automatique |
| `SD-DEMO-4025` | Rita Roadmap | produit Roadmap hors V1 |

## 00 - Preflight

Compte : aucun, puis admin.

Étapes :

1. Vérifier que `SC_E2E_BASE_URL` existe.
2. Refuser l'exécution si l'URL ressemble à la production et que `SC_E2E_ALLOW_PRODUCTION` n'est pas `true`.
3. Vérifier la présence des quatre couples email/password.
4. Vérifier que l'UI répond.
5. Vérifier que l'écran de login contient `E-mail`, `Mot de passe`, `Se connecter`.
6. En mode mutant, lancer ou exiger le reset démo staging.
7. Se connecter admin.
8. Chercher `SD-DEMO-4001` et `SD-DEMO-4025`.
9. Vérifier que `pre_cutover_check` staging est vert si un endpoint ou script distant est exposé au runner.

Résultat attendu : environnement connu, credentials valides, jeu démo complet, aucune écriture hors scope.

## 01 - Auth, Sidebar, Droits

Comptes : admin, Setter I, Setter II, Closer.

Étapes admin :

1. Login admin.
2. Vérifier que la sidebar est visible au premier chargement.
3. Plier la sidebar.
4. Vérifier que l'affordance native de réouverture reste visible.
5. Rouvrir la sidebar.
6. Vérifier l'absence de sélecteur de page dans le contenu principal.
7. Naviguer vers `Tâches`, `Inbox`, `Pilotage`, `Modèles`, `Mode d'emploi`, `Admin`.
8. Cliquer `Déconnexion`.
9. Vérifier retour à l'écran de login.

Étapes rôles commerciaux :

1. Login Setter I.
2. Vérifier accès à `Tâches`, `Inbox`, `Modèles`, `Mode d'emploi`, `Bug`, `Déconnexion`.
3. Vérifier que `Admin` n'est pas accessible.
4. Refaire pour Setter II.
5. Refaire pour Closer.

Résultat attendu : navigation stable, sidebar toujours rouvrable, droits cohérents par rôle.

## 02 - Admin, Bug, Actions Admin

Compte : admin.

Étapes :

1. Aller dans `Bug`.
2. Créer un signalement :
   - titre : `Test fonction bug Playwright` ;
   - description : `démo playwright` ;
   - attendu : `démo` ;
   - obtenu : `démo` ;
   - priorité : `normale`.
3. Aller dans `Admin > Signalements`.
4. Vérifier le signalement en statut `open`.
5. Aller dans `Tâches > Actions admin`.
6. Vérifier que l'action du bug est visible.
7. Terminer l'action avec résolution `traité`.
8. Retourner dans `Admin > Signalements`.
9. Vérifier statut `resolved` et `resolved_at` non vide.
10. Vérifier que les actions admin assignées à Laura, François et Tiago sont visibles par l'admin connecté.

Résultat attendu : bug traçable de bout en bout, actions admin globales pour tous les admins, résolution propagée au signalement.

## 03 - Inbox, Recherche, SchoolDrive

Compte : admin puis rôles commerciaux.

Étapes :

1. Ouvrir `Inbox`.
2. Tester les vues `À traiter`, `En suspens`, `Terminées`, `Toutes`.
3. Rechercher `Léa Martin`, ouvrir la fiche.
4. Rechercher `Inconnu(e)`, ouvrir la fiche.
5. Rechercher `Rita Roadmap`, ouvrir la fiche.
6. Vérifier que la fiche de droite reste synchronisée avec le prospect sélectionné.
7. Cliquer `Ouvrir SchoolDrive` sur un prospect qui a une URL SchoolDrive.
8. Intercepter le popup ou l'attribut `href`.
9. Vérifier que l'URL ouverte correspond au prospect sélectionné.
10. Vérifier que le fil conversation ne contient pas de fragments HTML visibles comme `</div>`.

Résultat attendu : files lisibles, recherche fiable, lien SchoolDrive bon prospect, aucun HTML parasite dans la conversation.

## 04 - Setter I : Réponse, Contact, Appel Setting

Compte : Setter I.

### Réponse Entrante

1. Ouvrir `Tâches > À traiter`.
2. Ouvrir `Léa Martin`.
3. Vérifier prochaine action `Répondre au message`.
4. Vérifier signal `client attend depuis`.
5. Ajouter une note interne.
6. Envoyer un message libre si `SC_E2E_ALLOW_WHATSAPP_SEND=true`.
7. Sinon, vérifier que le formulaire d'envoi est présent et que le clic final est sauté par le test.
8. Vérifier disparition de l'action `reply`.
9. Vérifier prochaine action cohérente : relance de sécurité ou appel déjà planifié.
10. Refaire sur `Inconnu(e)` pour valider l'affichage prospect sans nom.

### Pièce Jointe

1. Ouvrir un prospect avec fenêtre ouverte, par exemple `Camille Laurent`.
2. Charger un fichier fixture inoffensif, par exemple `fixtures/brochure-test.pdf`.
3. Ajouter une légende `Test PJ Playwright`.
4. Envoyer seulement si `SC_E2E_ALLOW_WHATSAPP_SEND=true`.
5. Vérifier trace dans la conversation ou message de blocage clair.

### Contact Bloqué

1. Ouvrir `Hugo Muller`.
2. Vérifier statut `Ne plus contacter`.
3. Vérifier que l'envoi WhatsApp commercial est bloqué.
4. Vérifier action `Revoir le statut de contact`.
5. Cliquer `Lever et répondre`.
6. Vérifier statut `Contact autorisé`.
7. Vérifier action `Répondre au message`.

### Appel Setting

1. Ouvrir `Luc Moreau`.
2. Vérifier appel setting dû maintenant.
3. Essayer de documenter sans note.
4. Vérifier blocage note obligatoire.
5. Déplacer l'appel avec note `demande client`.
6. Vérifier nouvelle échéance.
7. Replacer l'appel à maintenant ou utiliser `Nadia Keller`.
8. Documenter `non joint`.
9. Vérifier création du rappel suivant selon `setting_call_not_reached`.
10. Repartir d'un autre cas, documenter `joint`, `Passer au closing`, closer `Yasmine`.
11. Vérifier création d'une action closing.

Résultat attendu : réponse entrante, contact bloqué, upload, appel setting, déplacement et passage au closing conformes.

## 05 - Setter I : Reprise Manuelle Et Croix

Compte : Setter I.

### Reprise Manuelle Setter

1. Ouvrir `Sonia Mercier`.
2. Vérifier action `Reprise manuelle setter`.
3. Essayer de terminer sans note.
4. Vérifier blocage.
5. Ajouter une note `Reprise Playwright`.
6. Terminer.
7. Vérifier prochaine action ou fin de flux conforme à `post_setting_undecided`.

### Reprise Closer Demandée Depuis Setter

1. Ouvrir un prospect actif avec appel setting planifié.
2. Demander une reprise manuelle closer avec note.
3. Vérifier que l'appel déjà planifié n'est pas supprimé sans justification.
4. Vérifier que la prochaine action prioritaire reste cohérente.

### Croix Sur Actions Skippables

1. Ouvrir une relance `follow_up` skippable, par exemple `Sarah Perrin`.
2. Vérifier que la croix est visible.
3. Cliquer la croix.
4. Vérifier le libellé danger `Ignorer cette étape de flux`.
5. Vérifier la note obligatoire.
6. Vérifier que la confirmation affiche la prochaine action calculée ou la fin de flux.
7. Confirmer avec note.
8. Vérifier que l'action courante est marquée comme ignorée et que l'étape suivante du même flux existe si applicable.
9. Ouvrir un prospect avec action `reply` et vérifier que la croix affiche `Aucune réponse nécessaire`, note obligatoire et confirmation, sans envoyer de WhatsApp.
10. Ouvrir `Luc Moreau`, `Nicolas Meyer`, `Hugo Muller`, `Rita Roadmap`.
11. Vérifier que la croix de flux n'apparaît pas pour appels, `contact_review`, `other`, conversation terminale ou état terminal.

Résultat attendu : la croix de `follow_up` signifie uniquement `Ignorer cette étape de flux`. La croix de `reply` est un contrôle séparé : `Aucune réponse nécessaire`, jamais annuler n'importe quelle action.

## 06 - Closer : Closing

Compte : Closer.

### Appel Closing Dû

1. Ouvrir `Nicolas Meyer`.
2. Vérifier action `Appeler et documenter appel closing`.
3. Essayer sans note.
4. Vérifier blocage.
5. Documenter `signé`.
6. Vérifier conversation terminée, qualification `A signé`, aucune prochaine action commerciale.

### Va Signer

1. Repartir après reset ou ouvrir `Mathieu Garnier`.
2. Vérifier qualification `Va signer`.
3. Vérifier relance Setter II `closer_will_sign`.
4. Sur un closing actif, documenter `Va signer`.
5. Vérifier création d'une relance Setter II à +72h.

### No-Show Closing

1. Ouvrir `Émilie Morel`.
2. Vérifier rappel closing futur ou dû.
3. Documenter non joint sur un closing dû.
4. Vérifier progression dans `closing_call_not_reached`.

### Reprise Manuelle Closer

1. Ouvrir `Yves Caron`.
2. Vérifier action `Reprise manuelle closer`.
3. Vérifier note obligatoire.
4. Terminer avec note.
5. Vérifier prochaine action ou fin de flux cohérente.

Résultat attendu : closing signé ferme, va signer crée une relance, non joint suit le flux, reprise closer est documentée.

## 07 - Setter II : Relances Et Templates

Compte : Setter II.

### Fenêtre Fermée

1. Ouvrir `Aline Favre`.
2. Vérifier fenêtre WhatsApp fermée.
3. Vérifier que le message libre est impossible.
4. Vérifier qu'un template approuvé réel est proposé.
5. Vérifier l'aperçu et les variables.
6. Envoyer seulement si `SC_E2E_ALLOW_WHATSAPP_SEND=true`.
7. Vérifier prochaine étape du flux `setter_no_next_step`.

### Fenêtre Ouverte

1. Ouvrir `Camille Laurent`.
2. Vérifier fenêtre WhatsApp ouverte.
3. Vérifier que le message libre est possible.
4. Envoyer ou simuler selon garde-fou.
5. Vérifier prochaine étape.

### Lead Sans Réponse Initiale

1. Ouvrir `Sarah Perrin`.
2. Vérifier `lead_no_reply`, étape 1.
3. Vérifier template obligatoire si fenêtre fermée.
4. Vérifier qu'un skip affiche l'étape 2.

### Template Request

1. Ouvrir `Thomas Girard`.
2. Vérifier action bloquée `template_missing`.
3. Aller dans `Conversation > Envoyer un modèle`.
4. Créer une demande de modèle :
   - raison : `Modèle financement employeur Playwright` ;
   - contexte : `Le prospect demande si l'employeur peut prendre en charge la formation`.
5. Vérifier confirmation.
6. Aller dans `Modèles`.
7. Vérifier que la demande existe.
8. Ne pas lier de template réel sauf flag dédié `SC_E2E_ALLOW_TEMPLATE_LINK=true`.
9. Si le flag est actif, lier seulement à un template approuvé existant et vérifier que l'action commerciale se débloque.

Résultat attendu : relances conformes aux fenêtres WhatsApp, demandes de modèle visibles, aucun écrasement de templates ESSR.

## 08 - Clore, Réactiver, États Terminaux

Compte : admin.

### Clôture

Pour chaque motif, utiliser un prospect distinct ou reset entre scénarios :

- `signed` ;
- `not_relevant` ;
- `do_not_contact` ;
- `duplicate` ;
- `handled_elsewhere` ;
- `sequence_completed_no_reply` ;
- `error` ;
- `other`.

Étapes :

1. Ouvrir un prospect actif.
2. Cliquer `Clore la conversation`.
3. Essayer sans note quand le motif exige une note.
4. Vérifier blocage.
5. Ajouter une note.
6. Clore.
7. Vérifier statut conversation fermé.
8. Vérifier qualification/contact cohérent.
9. Vérifier absence d'action active.
10. Vérifier trace dans `Journal`.

### Réactivation

1. Ouvrir `Chloé Schmid`.
2. Cliquer `Réactiver`.
3. Essayer sans note.
4. Vérifier blocage.
5. Choisir prochaine action `Envoyer une relance` ou `Répondre`.
6. Choisir responsable.
7. Si la qualification terminale bloque, remettre d'abord la qualification à `Éligible`.
8. Réactiver avec note.
9. Vérifier conversation ouverte, prochaine action créée, trace dans `Journal`.

### États Terminaux Restaurables

1. Ouvrir `Irina Lopes`.
2. Vérifier `A signé`, conversation terminée, aucune relance.
3. Ouvrir `Philippe Aubert`.
4. Vérifier `Non pertinent`, conversation terminée, aucune relance.

Résultat attendu : fermeture et réactivation contrôlées, note obligatoire respectée, aucun état impossible.

## 09 - SchoolDrive Spécial

Compte : admin puis Setter I.

### Cours Complet

1. Ouvrir `Emma Complet`.
2. Vérifier affichage cours/session sous la fiche.
3. Vérifier capacité `20 / 20` ou `0 place restante`.
4. Vérifier signal visible `session complète` ou `cours complet`.
5. Vérifier absence de revue admin automatique.
6. Vérifier absence de relance commerciale normale.
7. Si un appel déjà planifié existe dans un fixture futur, vérifier qu'il reste une action humaine explicite et qu'aucune relance automatique n'est recréée.

### Roadmap

1. Ouvrir `Rita Roadmap`.
2. Vérifier produit Roadmap hors V1.
3. Vérifier absence de revue admin automatique.
4. Vérifier absence de flux normal `lead_no_reply`.

### Payload SchoolDrive 2.1 Par API

À automatiser côté API puis vérifier côté UI :

1. Envoyer un webhook lead `schema_version=2.1` avec `course.id`, `course.short_name`, `course.seats_*` et `course.is_full=true`.
2. Vérifier upsert par `schooldrive_id`.
3. Rejouer le même payload : vérifier absence de doublon.
4. Rejouer avec `aggregated_updated_at` plus ancien : vérifier ignore.
5. Rejouer avec `signed=true` : vérifier arrêt des relances.
6. Rejouer avec `do_not_contact.blocked=true` et `do_not_contact.reasons[]` objet : vérifier blocage des envois et note lisible.
7. Ajouter `related_subscriptions[].signed=true` avec `related_subscriptions[].course` imbriqué : vérifier stop des relances concurrentes même catégorie, sans fiche archivée.
8. Envoyer `product` sans `course` : vérifier absence de flux normal et absence de revue admin automatique.

Résultat attendu : SchoolDrive reste source de vérité, capacité et statuts arrêtent les relances au bon moment.

## 10 - Pilotage, Modèles, Guide

Compte : admin puis rôles commerciaux.

Étapes :

1. Ouvrir `Pilotage`.
2. Vérifier les onglets principaux sans erreur.
3. Vérifier `Logique métier` : états, flux, délais.
4. Ouvrir `Modèles`.
5. Vérifier les demandes à lier.
6. Vérifier qu'aucun test ne modifie un mapping ESSR sans flag.
7. Ouvrir `Mode d'emploi`.
8. Vérifier sections :
   - mode d'emploi général ;
   - Setter I ;
   - Setter II ;
   - Closer ;
   - Administrateur.
9. Vérifier terminologie `Notes internes`.
10. Vérifier absence de `Historique des actions` dans l'onglet `Actions`.
11. Vérifier que les textes destinés aux prospects vouvoient.

Résultat attendu : pilotage consultable, modèles protégés, guide aligné avec la terminologie V1.

## 11 - Lead Et Préinscription Site Web

Ces specs sont désactivées sauf `SC_E2E_ALLOW_REAL_SITE=true` pour éviter les créations involontaires en CI. Quand François demande la batterie complète, `SC_E2E_ALLOW_REAL_SITE=true` doit être activé et ces deux tests doivent être exécutés. Les inscriptions créées avec les URL/e-mails indiqués sont ensuite supprimées automatiquement dans le système.

### Lead Réel

1. Ouvrir `SC_E2E_SITE_LEAD_URL`, l'URL ESSR indiquée pour le test lead.
2. Cliquer `Voir les dates de cours`.
3. Remplir une demande d'information :
   - civilité : `Monsieur` ;
   - nom : `Test SalesCockpit` ;
   - prénom : `Lead` ;
   - email : `SC_E2E_SITE_LEAD_EMAIL` ;
   - téléphone : `SC_E2E_SITE_TEST_PHONE` ;
   - commentaire distinctif : `Playwright lead <timestamp>`.
4. Soumettre.
5. Poller Sales Cockpit pendant une fenêtre définie.
6. Vérifier fiche créée ou upsertée.
7. Vérifier `lead_type=lead`.
8. Vérifier lien SchoolDrive.
9. Vérifier cours, date, capacité si présents.
10. Vérifier autoresponder affiché seulement si `sent`.
11. Vérifier absence de doublon.
12. Envoyer une réponse WhatsApp depuis le numéro contrôlé seulement si l'environnement de test le permet.
13. Vérifier action `Répondre au message`.

### Préinscription Réelle

1. Ouvrir `SC_E2E_SITE_PRESUBSCRIPTION_URL`, l'URL ESSR indiquée pour le test préinscription.
2. Utiliser l'email `SC_E2E_SITE_PRESUBSCRIPTION_EMAIL`.
3. Soumettre.
4. Poller Sales Cockpit.
5. Vérifier `lead_type=presubscription`.
6. Vérifier lien SchoolDrive.
7. Vérifier cours, date, capacité, `course.is_full` si présents.
8. Vérifier arrêt strict si `signed=true`.
9. Vérifier blocage strict si `do_not_contact.blocked=true`.
10. Vérifier absence de flux normal si produit Roadmap.

Résultat attendu : le site web, SchoolDrive et Sales Cockpit sont alignés sur les deux flux réels.

## Exemple De Config

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./specs",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [["html"], ["json", { outputFile: "playwright-report/results.json" }]],
  use: {
    baseURL: process.env.SC_E2E_BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  globalSetup: require.resolve("./global.setup"),
});
```

## Exemple De Login Helper

```ts
import { expect, Page } from "@playwright/test";

const roles = {
  admin: ["SC_E2E_ADMIN_EMAIL", "SC_E2E_ADMIN_PASSWORD"],
  setter1: ["SC_E2E_SETTER1_EMAIL", "SC_E2E_SETTER1_PASSWORD"],
  setter2: ["SC_E2E_SETTER2_EMAIL", "SC_E2E_SETTER2_PASSWORD"],
  closer: ["SC_E2E_CLOSER_EMAIL", "SC_E2E_CLOSER_PASSWORD"],
} as const;

export async function loginAs(page: Page, role: keyof typeof roles) {
  const [emailKey, passwordKey] = roles[role];
  const email = process.env[emailKey];
  const password = process.env[passwordKey];
  if (!email || !password) throw new Error(`Missing credentials for ${role}`);

  await page.goto("/");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Mot de passe").fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByText(email).or(page.getByRole("button", { name: "Déconnexion" }))).toBeVisible();
}
```

## Exemple De Test Admin

```ts
import { test, expect } from "@playwright/test";
import { loginAs } from "../fixtures/auth";

test("bug report creates and resolves an admin action", async ({ page }) => {
  await loginAs(page, "admin");

  await page.getByRole("button", { name: "Bug" }).click();
  await page.getByLabel("Titre").fill("Test fonction bug Playwright");
  await page.getByLabel("Description").fill("démo playwright");
  await page.getByLabel("Résultat attendu").fill("démo");
  await page.getByLabel("Résultat obtenu").fill("démo");
  await page.getByRole("button", { name: "Envoyer" }).click();
  await expect(page.getByText("Signalement enregistré")).toBeVisible();

  await page.getByRole("button", { name: "Admin" }).click();
  await page.getByText("Signalements").click();
  await expect(page.getByText("Test fonction bug Playwright")).toBeVisible();
  await expect(page.getByText("open")).toBeVisible();

  await page.getByRole("button", { name: "Tâches" }).click();
  await page.getByText("Actions admin").click();
  await page.getByText("Test fonction bug Playwright").click();
  await page.getByLabel("Résolution").fill("traité");
  await page.getByRole("button", { name: "Marquer comme terminé" }).click();

  await page.getByRole("button", { name: "Admin" }).click();
  await page.getByText("Signalements").click();
  await expect(page.getByText("resolved")).toBeVisible();
  await expect(page.getByText("resolved_at")).toBeVisible();
});
```

Ce snippet est volontairement indicatif : si les labels exacts Streamlit diffèrent, les helpers doivent encapsuler l'adaptation, pas les assertions métier.

## Critères De Passage

La suite Playwright est verte seulement si :

- toutes les specs P0 à P10 passent sur staging après reset ;
- P11 passe en mode supervisé quand `SC_E2E_ALLOW_REAL_SITE=true` ;
- aucun mapping/template Twilio ESSR n'a été modifié par les tests ;
- aucune conversation non démo n'a été modifiée hors test live explicitement autorisé ;
- aucun fragment HTML parasite n'apparaît dans `Conversation` ;
- la sidebar reste pliable et rouvrable ;
- les rôles voient seulement leurs pages attendues ;
- chaque action critique laisse une trace vérifiable ;
- `pre_cutover_check` staging reste vert après exécution.

## Ordre Cutover

1. Reset démo staging.
2. Exécuter Playwright P0 à P10.
3. Corriger les bugs bloquants.
4. Rejouer P0 à P10.
5. Exécuter P11 lead réel.
6. Exécuter P11 préinscription réelle.
7. Attendre confirmation finale SchoolDrive/Tiago sur le contrat 2.1.
8. Rejouer SchoolDrive payload 2.1 si possible.
9. Faire le recheck équipe.
10. Tourner la clé seulement si tous les critères sont verts.
