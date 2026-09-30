# Aixrea Engine — Framework d'orchestration multi-agents

> Harness agent de qualité production pour construire des produits IA.
> Orchestrez des sous-agents, la mémoire, les bacs à sable et des compétences extensibles — propulsé par LangGraph.

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](./backend/pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Framework: LangGraph](https://img.shields.io/badge/Framework-LangGraph-FF6B6B)](https://langchain-ai.github.io/langgraph/)

[English](../README.md) | [中文](README.zh-CN.md) | [日本語](README.ja.md) | **Français** | [Русский](README.ru.md)

---

## Qu'est-ce qu'Aixrea Engine ?

Aixrea Engine est un **super harness agent** open-source qui orchestre des **sous-agents**, de la **mémoire** et des **bacs à sable** pour construire des applications IA de production. Il fournit une fondation flexible et extensible pour :

- 🤖 **Orchestration multi-agents** — Lead Agent coordonne des sous-agents spécialisés
- 🧠 **Mémoire persistante** — Mémoire à court terme, long terme et résumée
- 🛠️ **Compétences extensibles** — Construisez et publiez des outils IA comme compétences réutilisables
- 🔄 **Pipelines DAG** — Exécution déterministe de workflows pour la création de contenu
- 🔒 **Garde-fous de contenu** — Framework de modération enfichable pour les sorties IA
- 💬 **Messagerie communautaire** — Chat en temps réel avec des employés IA

Construit sur **LangGraph** pour des workflows agents fiables et récupérables.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Lead Agent                      │
│  (Hybride Plan-and-Execute + ReAct, 15+ middlewares)│
├──────────┬──────────┬───────────┬────────────────┤
│ Mémoire   │ Compétences│ Bac à sable│ Sous-agents   │
│ (court/  │ (outils   │ (exécution │ (travailleurs  │
│  long/    │  marché)  │  de code)  │  spécialisés)  │
│  résumé)  │           │            │                │
├──────────┴──────────┴───────────┴────────────────┤
│              PipelineExecutor (DAG)                │
│     (workflows déterministes pour création contenu) │
├────────────────────────────────────────────────────┤
│              AIGateway (routage de modèles)         │
│     (abstraction multi-modèles, repli, suivi)      │
└────────────────────────────────────────────────────┘
```

### Modèle de contrôle à trois couches

| Couche | Modèle | Cas d'usage |
|---|---|---|
| **Graphe de workflow** | DAG (déterministe) | Tronc d'exécution principal, facturation, récupération |
| **Plan-and-Execute** | Décomposition de tâches | Tâches complexes multi-étapes |
| **ReAct** | Exploration locale | Environnements inconnus, découverte d'outils |

---

## Démarrage rapide

### Prérequis

- Python 3.12+
- Node.js 22+ (pour le frontend/outillage)
- Redis (pour mémoire/cache)
- Une clé API LLM (OpenAI, Anthropic, ou compatible)

### Installation

```bash
# Cloner
git clone https://github.com/XinWoRen-Global/aixrea-engine.git
cd aixrea-engine

# Installer les dépendances backend
cd backend
pip install -e .

# Configurer
cp .env.example .env
# Éditer .env avec vos clés API LLM

# Exécuter
uvicorn app.main:app --reload --port 8001
```

### Exemple minimal

```python
from aixrea_engine import LeadAgent, SkillRegistry

# Initialiser
agent = LeadAgent(
    model="gpt-4o",
    skills=SkillRegistry.default(),
    memory=True,
)

# Exécuter
result = await agent.run("Rechercher les 3 meilleurs frameworks IA en 2026")
print(result.summary)
```

Voir [`examples/`](./examples) pour plus d'exemples.

---

## Modules principaux

| Module | Description | Statut |
|---|---|---|
| `agents.lead_agent` | Moteur d'exécution cœur avec 15+ middlewares | ✅ Stable |
| `agents.memory` | Mémoire court/long terme/résumée | ✅ Stable |
| `agents.subagents` | Orchestration de sous-agents | ✅ Stable |
| `runtime` | Serveur FastAPI, auth, configuration | ✅ Stable |
| `skills` | Registre et framework d'exécution de compétences | ✅ Stable |
| `sandbox` | Bac à sable d'exécution de code | ⚠️ Aperçu |
| `guardrails` | Framework de modération de contenu | ⚠️ Aperçu |
| `persistence` | Couche de persistance base de données | ✅ Stable |
| `tracing` | Tracing OpenTelemetry | ✅ Stable |
| `scheduler` | Planification de tâches | ⚠️ Aperçu |

---

## Système de compétences

Construisez et publiez des outils IA comme compétences réutilisables :

```python
from aixrea_engine import skill, SkillContext

@skill(name="web_search", description="Rechercher sur le web")
async def web_search(ctx: SkillContext, query: str) -> str:
    # Votre implémentation
    return results

# Enregistrer
registry = SkillRegistry()
registry.register(web_search)
```

### Partage des revenus Marketplace

Les développeurs d'outils sont des **créateurs** sur la plateforme. Les revenus des compétences suivent le système **CreatorTier** existant (identique aux créateurs de drame/musique/comic) :

| Niveau créateur | Part développeur | Plateforme |
|---|---|---|
| Bronze | 50% | 50% |
| Silver | 60% | 40% |
| Gold / Platinum | 70% | 30% |

- **Aucun système de commission séparé** — un compte, un niveau, tous les types de revenus unifiés
- **Paiement** : Mensuel via Stripe, minimum 10 $
- **Aucune exclusivité** : Publiez vos compétences partout
- **Vous conservez la propriété** de votre code de compétence

Les parrainages d'affiliation suivent le programme d'affiliation existant (jusqu'à 25%, cookie 30 jours).

Voir [COMMERCIAL.md](./COMMERCIAL.md) pour les détails.

---

## Utilisation commerciale

Ce projet est sous licence **MIT** pour un usage personnel, de recherche et interne.

Pour une utilisation commerciale (SaaS, déploiement entreprise, revente, ou intégration dans des produits propriétaires), veuillez nous contacter pour une licence commerciale. Nous proposons :

- **Licence startup** : Basée sur les revenus, sans frais initiaux
- **Licence entreprise** : Par instance, avec SLA et support
- **Licence OEM** : Marque blanche, intégration dans votre produit

Contact : `contact@xinworen.com`

---

## Contribution

Les contributions sont les bienvenues ! Voir [CONTRIBUTING.md](./CONTRIBUTING.md) pour les directives.

**Note** : Ce projet est actuellement en mode **open source en lecture seule**. Nous publions le code pour la transparence et l'apprentissage, mais nous n'acceptons pas les Pull Requests pour le moment. Veuillez ouvrir des Issues pour les rapports de bugs et demandes de fonctionnalités.

---

## Version open source vs Version commerciale

| Couche | Version open source (ce dépôt) | Plateforme commerciale |
|---|---|---|
| Framework agent | ✅ | ✅ |
| SDK compétences | ✅ | ✅ |
| Exécuteur pipeline DAG | ✅ | ✅ |
| Framework garde-fous contenu | ✅ | ✅ |
| Facturation / registre crédits | ❌ | ✅ |
| Marketplace / boutique | ❌ | ✅ |
| Distribution de contenu | ❌ | ✅ |
| Moteur de recommandation | ❌ | ✅ |
| Routage multi-domaines | ❌ | ✅ |
| Outils de création (drame/musique/comic) | ❌ | ✅ |

Dépôt open source : [github.com/XinWoRen-Global/aixrea-engine](https://github.com/XinWoRen-Global/aixrea-engine)

---

## Licence

[MIT](./LICENSE) — Copyright (c) 2026 **XinWoRen Pte. Ltd. (Singapore)** / Aixrea. Tous droits réservés.

---

> Construit avec LangGraph. Propulsé par la communauté mondiale des créateurs.
> [aixrea.com](https://aixrea.com) · [xinworen.com](https://xinworen.com)
> XinWoRen (新我人) — Plateforme de création IA pour les créateurs du monde entier
