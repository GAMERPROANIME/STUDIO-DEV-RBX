/**
 * Specialized agent roles. Each role is a real strategy object used by the
 * planner (to assign steps) and the executor (to shape step execution).
 * They are not characters: they carry concrete tool preferences, checklists
 * and verification rules.
 */
export type AgentRole =
  | "architect" | "researcher" | "developer" | "debugger"
  | "tester" | "optimizer" | "coordinator";

export interface RoleDef {
  id: AgentRole;
  title: string;
  description: string;
  /** Tools this role prefers, in order. */
  tools: string[];
  checklist: string[];
  /** How this role verifies its own output. */
  verify: string;
}

export const ROLES: Record<AgentRole, RoleDef> = {
  architect: {
    id: "architect", title: "Agent Architecte",
    description: "Conçoit l'architecture, analyse les besoins, organise les composants.",
    tools: ["project_inspect", "project_analyze", "knowledge_retrieve", "agent_create_plan"],
    checklist: ["Identifier les systèmes existants avant de créer", "Définir les dépendances entre systèmes", "Choisir des patterns Roblox standards (services, modules)"],
    verify: "Le plan couvre tous les systèmes demandés et respecte les conventions du projet.",
  },
  researcher: {
    id: "researcher", title: "Agent Chercheur",
    description: "Recherche documentations, vérifie les informations, compare les solutions.",
    tools: ["web_search", "web_open", "web_compare_sources", "documentation_search", "knowledge_retrieve"],
    checklist: ["Consulter uniquement des sources officielles d'abord", "Comparer au moins 2 sources", "Citer les sources (URL + date)"],
    verify: "Chaque affirmation technique est sourcée; aucune API inventée.",
  },
  developer: {
    id: "developer", title: "Agent Développeur",
    description: "Écrit le code, modifie les fichiers, implémente les fonctionnalités.",
    tools: ["file_create", "file_update", "code_analyze", "roblox_edit_scripts", "roblox_create_objects"],
    checklist: ["Sauvegarder avant modification", "Respecter --!strict et les conventions Luau", "Petits fichiers, responsabilités uniques"],
    verify: "code_analyze ne rapporte aucune erreur sur le code produit.",
  },
  debugger: {
    id: "debugger", title: "Agent Débogueur",
    description: "Analyse les erreurs, identifie leurs causes, propose des corrections.",
    tools: ["error_diagnose", "roblox_get_console_output", "code_analyze", "file_read"],
    checklist: ["Lire le message d'erreur complet", "Identifier le script et la ligne", "Vérifier les dépendances affectées"],
    verify: "L'erreur disparaît après correction (re-test).",
  },
  tester: {
    id: "tester", title: "Agent Testeur",
    description: "Effectue les tests, vérifie les comportements et les critères d'acceptation.",
    tools: ["code_test", "roblox_playtest", "roblox_get_console_output", "roblox_capture_screen"],
    checklist: ["Tester le chemin nominal puis les cas limites", "Comparer résultats attendus vs obtenus", "Noter chaque anomalie"],
    verify: "Tous les critères d'acceptation passent ou les écarts sont documentés.",
  },
  optimizer: {
    id: "optimizer", title: "Agent Optimiseur",
    description: "Recherche les améliorations, analyse les performances, élimine les problèmes techniques.",
    tools: ["code_analyze", "project_analyze", "knowledge_retrieve", "error_diagnose"],
    checklist: ["Chercher les boucles sans yield", "Vérifier les allocations en hot path", "Réduire les réplications inutiles"],
    verify: "Aucune régression fonctionnelle après optimisation.",
  },
  coordinator: {
    id: "coordinator", title: "Agent Coordinateur",
    description: "Distribue le travail, contrôle les dépendances, vérifie les résultats des autres agents.",
    tools: ["agent_get_task_status", "agent_review_result", "agent_create_checkpoint"],
    checklist: ["Respecter l'ordre des dépendances", "Checkpoint après chaque étape", "Stopper en cas d'erreur répétée"],
    verify: "Le bilan final liste ce qui a été fait, testé et vérifié.",
  },
};

export function roleForTool(tool: string): AgentRole {
  for (const role of Object.values(ROLES)) if (role.tools.includes(tool)) return role.id;
  return "coordinator";
}
