# Prompt Image - Graphe Business Sales Cockpit

Copier-coller ce prompt dans une IA génératrice d'image.

## Prompt Complet

Crée une infographie métier unique, claire et exhaustive, au format paysage très large, ratio 16:9 ou 21:9, style schéma whiteboard propre, inspiré d'un diagramme en arête de poisson. L'image doit représenter la logique business statique du Sales Cockpit ESSR : états du parcours, flux latéraux, actions successives dans chaque flux, et états finaux.

Important : l'image doit être très proche mentalement du croquis fourni : une grande ligne horizontale noire représente le temps et le parcours principal, de gauche à droite. Des branches obliques violettes partent de cette ligne principale comme des arêtes de poisson. Chaque branche est un flux. Sur chaque branche, des petits cercles verts représentent les actions successives. À l'extrémité de chaque branche, un petit rectangle vert indique la fin du flux ou la sortie du flux. À droite, la ligne principale se divise vers les états terminaux. Utilise une esthétique sobre, lisible, professionnelle, avec beaucoup d'espace blanc.

Ne montre pas les transitions dynamiques causées par des événements externes. Ne dessine pas de flèches pour "le client répond", "le client appelle", "SchoolDrive envoie un signal", "un message entrant interrompt le flux", "do_not_contact bloque", etc. Ces transitions sont des règles métier, mais elles ne doivent pas être illustrées dans cette image. L'image doit seulement représenter la structure statique : parcours principal, flux disponibles, actions internes à chaque flux, états finaux.

Titre en haut : "Sales Cockpit ESSR - Parcours, Flux, Actions".

## Axe Principal

Dessine une ligne horizontale principale noire, épaisse, partant de la gauche vers la droite.

À gauche, grand libellé noir :
"Envoi formulaire
lead ou préinscription"

Sous la ligne principale, place les états du parcours en orange, espacés de gauche à droite :

1. "Nouveau prospect"
2. "Échange avec setter"
3. "RDV setting agendé"
4. "Appel setting à documenter"
5. "RDV closing agendé"
6. "Appel closing à documenter"
7. "Va signer"

À gauche sous la ligne, ajoute en bleu :
"Conversation ouverte"

À droite, trace une ligne verticale pointillée bleue qui marque la frontière :
"Conversation fermée"

Après cette frontière, fais diverger la ligne principale en cinq flèches terminales noires :

- "A signé"
- "Non pertinent"
- "Ne plus contacter"
- "Suivi terminé sans réponse"
- "Traité ailleurs / erreur / autre"

Ces états terminaux doivent être grands, lisibles, en noir, à droite de l'image.

## Flux Latéraux À Dessiner

Chaque flux est une branche oblique violette partant de son état d'ancrage sur l'axe principal. Écris le nom du flux en violet, près de la branche. Les actions du flux sont des cercles verts, avec texte vert à côté. Le dernier nœud est un rectangle vert indiquant la sortie ou fin.

### Flux 1 - Lead Sans Réponse Initiale

Ancrage : "Nouveau prospect".
Nom de branche violet : "Lead sans réponse initiale".
Code technique discret sous le titre : "lead_no_reply".

Actions vertes sur la branche :

1. "Relance 1 - T+72h"
2. "Relance 2 - T+144h"
3. "Relance 3 - T+216h"
4. "Relance 4 - T+16j"
5. "Relance 5 - T+23j"
6. "Relance 6 - T+53j"

Rectangle final vert :
"Fin du flux : suivi terminé sans réponse"

### Flux 2 - Échange Setter Sans Suite

Ancrage : "Échange avec setter".
Nom violet : "Échange setter sans suite".
Code discret : "setter_no_next_step".

Actions vertes :

1. "Relance 1 - T+72h"
2. "Relance 2 - T+144h"
3. "Relance 3 - T+216h"
4. "Relance 4 - T+16j"
5. "Relance 5 - T+23j"
6. "Relance 6 - T+53j"

Rectangle final vert :
"Fin du flux : suivi terminé sans réponse"

### Flux 3 - No-Show Setting

Ancrage : "Appel setting à documenter".
Nom violet : "No-show setting".
Code discret : "setting_call_not_reached".

Actions vertes :

1. "Rappel setting 1 - +2h ouvrées"
2. "Rappel setting 2 - +24h"
3. "Relance WhatsApp - +72h"

Rectangle final vert :
"Suite selon réponse ou fin du suivi"

### Flux 4 - Post-Appel Setting Indécis

Ancrage : "Appel setting à documenter".
Nom violet : "Post-appel setting indécis".
Code discret : "post_setting_undecided".

Action verte :

1. "Reprise manuelle setter - +72h"

Rectangle final vert :
"Décision humaine obligatoire"

### Flux 5 - No-Show Closing

Ancrage : "Appel closing à documenter".
Nom violet : "No-show closing".
Code discret : "closing_call_not_reached".

Actions vertes :

1. "Rappel closing 1 - +2h ouvrées"
2. "Rappel closing 2 - +24h"
3. "Relance WhatsApp - +72h"

Rectangle final vert :
"Suite selon réponse ou fin du suivi"

### Flux 6 - Post-Appel Closing Indécis

Ancrage : "Appel closing à documenter".
Nom violet : "Post-appel closing indécis".
Code discret : "post_closing_undecided".

Action verte :

1. "Reprise manuelle closer - +72h"

Rectangle final vert :
"Décision humaine obligatoire"

### Flux 7 - Closer : Va Signer

Ancrage : "Va signer".
Nom violet : "Closer : va signer".
Code discret : "closer_will_sign".

Actions vertes :

1. "Relance 1 - T+72h"
2. "Relance 2 - T+144h"
3. "Relance 3 - T+216h"
4. "Relance 4 - T+16j"
5. "Relance 5 - T+23j"
6. "Relance 6 - T+53j"

Rectangle final vert :
"Fin du flux : suivi terminé sans réponse"

### Flux 8 - Début De Cours

Ce flux est transversal, car il dépend de la date de cours SchoolDrive et peut devenir prioritaire avant les états terminaux. Représente-le comme une branche violette longue, un peu au-dessus de l'axe principal, couvrant plusieurs états ouverts.

Nom violet : "Début de cours".
Code discret : "course_start".

Actions vertes :

1. "Relance cours - J-14"
2. "Relance cours - J-7"
3. "Relance cours - J-3"
4. "Relance cours - J-1"

Rectangle final vert :
"Fin du flux cours"

## Actions Transversales À Mettre En Légende

Ajoute une légende discrète dans un encadré en bas à droite, sans relier cette légende par des flèches. Titre : "Actions principales V1".

Liste dans la légende, avec petits pictogrammes simples :

- "Répondre au message" = reply, Setter I, preuve : message WhatsApp sortant.
- "Envoyer relance" = follow_up, Setter II, preuve : message libre ou template.
- "Appeler et documenter appel setting" = setting_call, Setter I, preuve : résultat d'appel + note.
- "Appeler et documenter appel closing" = closing_call, Closer, preuve : résultat d'appel + note.
- "Reprise manuelle setter" = manual_reprise_setter, Setter I, preuve : note obligatoire.
- "Reprise manuelle closer" = manual_reprise_closer, Closer, preuve : note obligatoire.

Ajoute un deuxième petit encadré : "Actions support / revue humaine".

Liste :

- "Revue contact" = contact_review.
- "Revue SchoolDrive / Roadmap / cours complet" = other.
- "Demande de modèle" = template_request.
- "Action admin" = admin_action.
- "Note interne" = manual_note.
- "Qualification / statut contact" = support action.

## États Et Codes Couleur

Utilise ces couleurs :

- Axe principal : noir.
- États du parcours : orange.
- Flux : violet.
- Actions : vert.
- Conversation ouverte / fermée : bleu.
- États terminaux : noir, plus grands.
- Blocage ou arrêt strict : petit accent rouge uniquement dans la légende, pas dans les flux.

Ajoute une mini légende couleurs :

- Orange = Parcours.
- Violet = Flux.
- Vert = Action.
- Bleu = Statut conversation.
- Noir = Début / fin.

## Contraintes De Lisibilité

L'image doit rester lisible même avec beaucoup d'informations. Utilise une grande toile. Le style doit être propre et structuré, pas décoratif. Évite les effets 3D, les ombres lourdes, les personnages, les icônes fantaisistes, les dégradés, les fonds sombres, les couleurs criardes. Ne fais pas une infographie marketing. Fais un schéma métier pédagogique, comme une version propre et exhaustive d'un croquis de tableau blanc.

Tous les textes doivent être en français, sans faute, avec accents. Les textes doivent être parfaitement lisibles.

## Negative Prompt

Ne pas montrer :

- les transitions dynamiques ;
- les messages entrants du client ;
- les appels entrants du client ;
- les flèches de changement de flux ;
- les règles SchoolDrive comme des événements ;
- les webhooks ;
- les bases de données ;
- Twilio, Meta, Front ou Notion comme logos ;
- un organigramme vertical ;
- un diagramme BPMN complexe ;
- une carte mentale décorative ;
- une interface logicielle ;
- des personnages ;
- des emojis ;
- des couleurs néon ;
- un fond sombre ;
- des petits textes illisibles.

Résultat attendu : une seule image, exhaustive, de type arête de poisson, qui montre tous les états principaux, tous les flux V1, toutes les actions de flux et tous les états finaux, au plus proche du croquis original mais propre, lisible et complet.
