Tu es un architecte logiciel senior spécialisé dans :

* broadcast vidéo temps réel,
* vision par ordinateur,
* applications web modernes,
* automatisation de réalisation vidéo,
* pipelines multimédia faibles latences.

Tu dois concevoir et implémenter une application complète nommée **Subvision Studio**.

# CONTEXTE

Subvision Studio est une application web de réalisation vidéo automatisée pour des compétitions de tir subaquatique.

L’application pilote automatiquement :

* les changements de caméras,
* les plans actifs,
* les comportements PTZ éventuels,
* les transitions vidéo,
* la logique de réalisation selon des évènements de compétition.

Les évènements proviennent d’une API externe déjà existante.
Tu ne dois PAS développer cette API.

Les évènements sont détectés entre deux frames vidéo.
L’application interroge périodiquement l’API externe afin de récupérer les nouveaux évènements.

Exemples d’évènements :

* début d’épreuve,
* fin d’épreuve,
* départ tireur,
* tir effectué,
* récupération de flèche,
* validation cible,
* pénalité,
* timeout,
* annonce arbitre.

# OBJECTIF PRINCIPAL

Créer une application web moderne permettant :

* la gestion multi-caméras,
* l’automatisation des changements de plans,
* la configuration complète des règles de réalisation,
* la supervision temps réel,
* l’intégration OBS,
* l’extensibilité future.

# STACK TECHNIQUE IMPOSÉE

Frontend:

* Angular latest
* Standalone Components
* TypeScript
* RxJS
* PrimeNG
* PrimeFlex
* Signals Angular
* Vite

Backend:

* Python
* FastAPI
* AsyncIO
* WebSocket temps réel
* SQLAlchemy
* Pydantic
* Architecture modulaire
* API REST interne
* FFmpeg/GStreamer pour les flux vidéo

Vision/Tracking:

* OpenCV
* possibilité future d’intégrer YOLO
* pipeline découplé

OBS:

* obs-websocket

Déploiement:

* Docker
* accès navigateur web
* architecture client/server

# ARCHITECTURE GLOBALE

Concevoir une architecture modulaire séparée en services.

## 1. Video Ingest Service

Responsabilités :

* gestion RTSP/NDI/webcams,
* synchronisation des flux,
* extraction de frames,
* monitoring qualité flux,
* buffering faible latence,
* snapshots temps réel,
* génération previews navigateur.

## 2. Event Engine

Responsabilités :

* polling de l’API externe,
* réception des évènements,
* timestamping,
* déduplication,
* diffusion interne des évènements.

IMPORTANT :
Les évènements surviennent entre deux frames.
Le moteur doit pouvoir associer précisément un évènement à une frame vidéo ou à un intervalle temporel.

## 3. Realization Engine

Le coeur du système.

Responsabilités :

* analyse des évènements,
* décision de changement de caméra,
* exécution des transitions,
* gestion des priorités,
* cooldown anti-zapping,
* règles conditionnelles,
* logique de scénarios.

Le moteur doit être entièrement configurable.

## 4. Camera Rule Engine

Chaque caméra possède des règles configurables.

Exemples :

* si événement = TIR alors activer caméra cible,
* si événement = DÉPART_TIREUR alors caméra bassin,
* si événement = FIN_EPReUVE alors caméra large,
* si événement = RECUPERATION_FLECHE alors caméra underwater 2.

Chaque règle doit permettre :

* priorité,
* durée minimale d’affichage,
* transition,
* délai,
* conditions,
* cooldown,
* override manuel,
* activation/désactivation.

## 5. OBS Integration Service

Responsabilités :

* connexion obs-websocket,
* changement de scènes,
* transitions,
* preview/program,
* overlays,
* replay futur.

## 6. Configuration Service

Responsabilités :

* sauvegarde JSON/YAML,
* profils d’évènements,
* profils de compétitions,
* import/export,
* validation de configuration.

# FONCTIONNALITÉS UI

Créer une UI moderne type régie broadcast professionnelle avec PrimeNG.

## Layout principal

* grille multi-caméras,
* preview/program,
* timeline évènements,
* état des flux,
* logs temps réel,
* panneau règles,
* monitoring API externe,
* contrôles manuels broadcast.

## Composants PrimeNG à utiliser

* Splitter
* Dock
* Menubar
* Toolbar
* Panel
* Card
* Table
* TreeTable
* Timeline
* Dialog
* Toast
* ConfirmDialog
* TabView
* Accordion
* OverlayPanel
* ContextMenu
* TieredMenu
* InputSwitch
* Dropdown
* MultiSelect
* Slider
* Knob
* Tag
* Badge

## Éditeur de règles

Créer un éditeur visuel avancé permettant :

* associer évènements → actions caméra,
* créer des conditions,
* gérer priorités,
* tester les règles,
* simuler des évènements,
* reorder drag & drop,
* profiling des règles.

Le système doit être pensé comme un moteur d’automatisation broadcast configurable.

# SYSTÈME DE RÈGLES

Créer un moteur déclaratif.

Exemple JSON :

```json id="dhqjtx"
{
  "event": "SHOT_FIRED",
  "camera": "TARGET_CAM_1",
  "priority": 100,
  "duration": 5000,
  "transition": "CUT",
  "cooldown": 2000,
  "enabled": true
}
```

Prévoir :

* règles multiples,
* conflits,
* scoring,
* fallback camera,
* règles globales,
* règles spécifiques compétition,
* héritage de profils,
* presets.

# ARCHITECTURE BACKEND

Créer les modules suivants :

```id="h1f1ul"
backend/
├── api/
├── core/
├── events/
├── realization/
├── rules/
├── video/
├── obs/
├── websocket/
├── config/
├── models/
├── schemas/
├── services/
├── repositories/
├── workers/
└── tests/
```

# ARCHITECTURE FRONTEND

Créer les modules Angular suivants :

```id="1ab7rc"
frontend/
├── core/
├── shared/
├── layout/
├── features/
│   ├── dashboard/
│   ├── cameras/
│   ├── rules/
│   ├── events/
│   ├── obs/
│   ├── settings/
│   └── monitoring/
├── services/
├── store/
└── websocket/
```

# STREAMING NAVIGATEUR

Le système doit permettre l’affichage live dans le navigateur via :

* WebRTC faible latence,
* ou LL-HLS selon les besoins,
* previews temps réel,
* mosaïque multi-caméras,
* preview/program style régie TV.

Prévoir :

* serveur de relay vidéo,
* génération thumbnails,
* snapshots,
* monitoring FPS/latence.

# WEBSOCKET TEMPS RÉEL

Créer un système temps réel bidirectionnel :

* état des caméras,
* caméra active,
* évènements entrants,
* changements de scènes,
* logs live,
* erreurs,
* stats performance.

# LATENCE

Objectif :

* changement caméra < 150ms après évènement,
* architecture async,
* pipeline non bloquant,
* queues internes,
* gestion backpressure.

# EXTENSIBILITÉ

Le système doit être prévu pour :

* tracking IA,
* auto-follow,
* PTZ automatique,
* replay IA,
* highlights automatiques,
* multi-compétitions,
* cluster distribué futur,
* GPU inference.

# QUALITÉ CODE

Exigences :

* architecture clean,
* fortement typé,
* Pydantic partout,
* services découplés,
* injection dépendances,
* testabilité maximale,
* logs structurés,
* monitoring,
* gestion erreurs robuste.

# LIVRABLES ATTENDUS

Tu dois générer :

1. architecture complète,
2. structure dossiers,
3. modèles SQLAlchemy,
4. schémas Pydantic,
5. API REST FastAPI,
6. protocoles websocket,
7. moteur de règles,
8. logique de réalisation,
9. intégration OBS,
10. stratégie vidéo navigateur,
11. UI Angular PrimeNG complète,
12. composants standalone Angular,
13. services FastAPI,
14. workers async,
15. exemples de configs,
16. roadmap MVP → production,
17. stratégie tests,
18. dockerisation,
19. CI/CD,
20. monitoring Prometheus/Grafana.

# IMPORTANT

Tu dois :

* produire du vrai code production-ready,
* éviter les simplifications inutiles,
* proposer une architecture scalable,
* détailler les flux temps réel,
* détailler les structures de données,
* expliquer les décisions techniques,
* penser comme un logiciel broadcast professionnel.

Le résultat doit ressembler à :

* un mélange entre OBS,
* un automate de réalisation TV,
* un système événementiel temps réel,
* une régie vidéo programmable professionnelle accessible depuis un navigateur web.
Ajoute et applique STRICTEMENT les contraintes d’architecture suivantes dans Subvision Studio.

# GESTION ÉVÈNEMENTIELLE PAR CAMÉRA

Le système doit fonctionner selon un modèle de subscriptions événementielles par caméra.

IMPORTANT :
Toutes les caméras doivent pouvoir recevoir et analyser les évènements même lorsqu’elles ne sont PAS actives à l’antenne.

Cela est indispensable afin :

* d’anticiper les changements de plans,
* de préparer les transitions,
* de détecter des actions importantes hors antenne,
* de calculer des scores de pertinence,
* de permettre une réalisation proactive et non réactive.

Exemple :
Une caméra cible peut détecter un tir imminent alors qu’une caméra bassin est actuellement en program.
Le moteur doit déjà connaitre cet évènement pour préparer un switch immédiat.

# SUBSCRIPTIONS ÉVÈNEMENTIELLES

Chaque caméra possède une configuration indépendante définissant :

* quels évènements elle écoute,
* quels évènements elle ignore,
* quelles actions elle déclenche,
* quelles métadonnées elle produit,
* son niveau de priorité selon l’évènement,
* ses contraintes de diffusion.

IMPORTANT :
Une caméra peut :

* écouter un évènement sans devenir active,
* écouter un évènement uniquement pour enrichir le contexte global,
* produire un score de pertinence,
* déclencher un prewarm/préchargement,
* demander un switch conditionnel.

# ARCHITECTURE DEMANDÉE

Créer un système distribué de traitement événementiel.

## Pipeline global

```id="p3v1d0"
External Event API
        ↓
Event Engine
        ↓
Global Event Bus
        ↓
Camera Event Subscribers
        ↓
Per-Camera Context Engine
        ↓
Realization Decision Engine
        ↓
OBS / Program Output
```

# CAMERA EVENT SUBSCRIBERS

Chaque caméra doit embarquer un subscriber indépendant.

Exemple :

```json id="1tz8ri"
{
  "camera_id": "TARGET_CAM_1",
  "subscriptions": [
    "SHOT_FIRED",
    "TARGET_VALIDATION",
    "ARROW_RECOVERY"
  ]
}
```

Une autre caméra :

```json id="wlk8h8"
{
  "camera_id": "POOL_WIDE",
  "subscriptions": [
    "MATCH_START",
    "MATCH_END",
    "ATHLETE_READY"
  ]
}
```

# CONTEXTE GLOBAL

Le système doit maintenir un contexte temps réel global.

Ce contexte contient :

* dernier évènement par caméra,
* activité récente,
* score d’intérêt,
* état compétition,
* caméra actuellement active,
* évènements critiques récents,
* historique court terme,
* cooldowns,
* transitions récentes.

# CONTEXTE PAR CAMÉRA

Chaque caméra possède un contexte indépendant :

```json id="2ut6xk"
{
  "camera_id": "TARGET_CAM_1",
  "last_event": "SHOT_FIRED",
  "interest_score": 92,
  "last_activity_at": 1710000000,
  "cooldown_until": 1710000200,
  "pending_transition": true
}
```

# REALIZATION DECISION ENGINE

Le moteur de décision ne doit PAS simplement réagir au dernier évènement.

Il doit :

* agréger tous les contextes caméras,
* comparer les scores,
* analyser les priorités,
* appliquer les cooldowns,
* éviter les changements inutiles,
* permettre l’anticipation des actions.

Le moteur doit pouvoir :

* préparer une caméra avant diffusion,
* charger une scène OBS en preview,
* attendre une confirmation évènementielle,
* effectuer des transitions intelligentes.

# MODÈLE DE SCORING

Chaque caméra doit produire un score dynamique basé sur :

* pertinence évènement,
* récence activité,
* priorité règle,
* durée depuis dernier passage antenne,
* criticité évènement,
* type compétition,
* état actuel du programme.

Exemple :

```id="0sfb3d"
score =
event_priority
+ activity_weight
+ critical_bonus
- cooldown_penalty
- repetition_penalty
```

# MODES DE RÉACTION

Chaque règle caméra peut définir un mode :

## 1. INFORM_ONLY

La caméra écoute l’évènement uniquement pour contexte.

## 2. PREPARE

Précharge preview / PTZ / buffer sans switch.

## 3. SWITCH_IF_HIGH_SCORE

Switch uniquement si score global suffisant.

## 4. FORCE_SWITCH

Priorité absolue.

# CONFIGURATION PAR CAMÉRA

Exemple complet :

```json id="i9l7e3"
{
  "camera_id": "TARGET_CAM_1",
  "subscriptions": [
    {
      "event": "SHOT_FIRED",
      "mode": "FORCE_SWITCH",
      "priority": 100,
      "duration": 5000,
      "cooldown": 3000
    },
    {
      "event": "TARGET_VALIDATION",
      "mode": "SWITCH_IF_HIGH_SCORE",
      "priority": 70
    },
    {
      "event": "MATCH_START",
      "mode": "INFORM_ONLY"
    }
  ]
}
```

# UI DE CONFIGURATION

Créer une interface permettant :

* voir les subscriptions par caméra,
* activer/désactiver des évènements,
* modifier priorités,
* visualiser les scores live,
* voir les caméras candidates,
* voir pourquoi une caméra a été sélectionnée,
* voir les évènements ignorés,
* debug complet du moteur décisionnel.

# DEBUGGING TEMPS RÉEL

Le système doit exposer :

* score de chaque caméra,
* règles déclenchées,
* règles ignorées,
* cooldowns actifs,
* raison des switches,
* évènements consommés,
* évènements ignorés,
* timeline décisionnelle.

# IMPORTANT

Le système NE DOIT PAS :

* être purement réactif,
* dépendre uniquement de la caméra active,
* ignorer les évènements hors programme.

Le système DOIT :

* maintenir une compréhension globale de la compétition,
* écouter tous les flux événementiels utiles,
* anticiper les actions importantes,
* fonctionner comme une vraie régie TV intelligente.

Ajoute la contrainte suivante au cahier des charges de **Subvision Studio**.

# INSPIRATION PROJET EXISTANT

Le système peut et doit s’inspirer d’architectures et concepts existants, notamment du projet :

👉 [https://github.com/miroir-os/gabin](https://github.com/miroir-os/gabin)

Le but n’est pas de copier ce projet, mais de :

* s’inspirer de ses choix d’architecture,
* comprendre ses patterns de gestion événementielle,
* réutiliser ses idées de design si pertinentes,
* adapter ses concepts à un système broadcast temps réel multi-caméras.

# UTILISATION ATTENDUE DE L’INSPIRATION

L’agent doit analyser ce projet comme référence technique pour enrichir Subvision Studio sur les points suivants :

## 1. Architecture événementielle

* modèles de flux d’évènements
* propagation d’évènements dans le système
* découplage producteurs / consommateurs
* bus événementiel ou équivalent

## 2. Patterns de modularité

* séparation forte des responsabilités
* services indépendants mais interconnectés
* logique plugin / modules remplaçables

## 3. Gestion de contexte

* conservation d’état global
* synchronisation de contextes multiples
* propagation de changements d’état

## 4. Réactivité du système

* traitement temps réel
* priorisation des évènements
* minimisation de latence
* gestion des flux concurrents

# CONTRAINTE IMPORTANTE

L’agent doit :

* considérer ce projet comme une **source d’inspiration uniquement**
* ne pas réutiliser du code sans adaptation
* reformuler entièrement l’architecture dans le contexte Subvision Studio
* adapter les concepts au domaine **broadcast vidéo + multi-caméras + régie TV automatique**

# OBJECTIF DE CETTE INSPIRATION

L’objectif est d’augmenter la qualité du système Subvision Studio en :

* renforçant la robustesse du moteur événementiel,
* améliorant la cohérence du système de règles,
* optimisant la propagation des évènements caméra,
* améliorant la scalabilité du système temps réel.

# INTÉGRATION DANS L’ARCHITECTURE

Cette inspiration doit se traduire concrètement dans :

* Event Engine (FastAPI backend)
* Global Event Bus
* Camera Subscriber System
* Realization Decision Engine
* Context Management Layer

# RÈGLE FINALE

Subvision Studio doit rester :

* un système original,
* spécialisé pour la régie vidéo automatisée,
* optimisé pour les compétitions de tir subaquatique,
* capable de décisions temps réel basées sur multi-caméras.

Mais il peut s’appuyer sur les idées architecturales de ce projet pour atteindre un niveau industriel de robustesse et de modularité.

