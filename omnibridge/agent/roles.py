"""Specialized agent roles: real strategy objects (tool preferences, checklists, verification)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleDef:
    id: str
    title: str
    description: str
    tools: tuple[str, ...]
    checklist: tuple[str, ...]
    verify: str

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "description": self.description,
                "tools": list(self.tools), "checklist": list(self.checklist), "verify": self.verify}


ROLES: dict[str, RoleDef] = {
    "architect": RoleDef(
        "architect", "Agent Architecte",
        "Conçoit l'architecture, analyse les besoins, organise les composants.",
        ("project_inspect", "project_analyze", "knowledge_retrieve", "agent_create_plan"),
        ("Identifier les systèmes existants avant de créer", "Définir les dépendances entre systèmes",
         "Choisir des patterns Roblox standards (services, modules)"),
        "Le plan couvre tous les systèmes demandés et respecte les conventions du projet."),
    "researcher": RoleDef(
        "researcher", "Agent Chercheur",
        "Recherche documentations, vérifie les informations, compare les solutions.",
        ("web_search", "web_open", "web_compare_sources", "documentation_search", "knowledge_retrieve"),
        ("Consulter uniquement des sources officielles d'abord", "Comparer au moins 2 sources",
         "Citer les sources (URL + date)"),
        "Chaque affirmation technique est sourcée; aucune API inventée."),
    "developer": RoleDef(
        "developer", "Agent Développeur",
        "Écrit le code, modifie les fichiers, implémente les fonctionnalités.",
        ("file_create", "file_update", "code_analyze", "roblox_edit_scripts", "roblox_create_objects"),
        ("Sauvegarder avant modification", "Respecter --!strict et les conventions Luau",
         "Petits fichiers, responsabilités uniques"),
        "code_analyze ne rapporte aucune erreur sur le code produit."),
    "debugger": RoleDef(
        "debugger", "Agent Débogueur",
        "Analyse les erreurs, identifie leurs causes, propose des corrections.",
        ("error_diagnose", "roblox_get_console_output", "code_analyze", "file_read"),
        ("Lire le message d'erreur complet", "Identifier le script et la ligne",
         "Vérifier les dépendances affectées"),
        "L'erreur disparaît après correction (re-test)."),
    "tester": RoleDef(
        "tester", "Agent Testeur",
        "Effectue les tests, vérifie les comportements et les critères d'acceptation.",
        ("code_test", "roblox_playtest", "roblox_get_console_output", "roblox_capture_screen"),
        ("Tester le chemin nominal puis les cas limites", "Comparer résultats attendus vs obtenus",
         "Noter chaque anomalie"),
        "Tous les critères d'acceptation passent ou les écarts sont documentés."),
    "optimizer": RoleDef(
        "optimizer", "Agent Optimiseur",
        "Recherche les améliorations, analyse les performances, élimine les problèmes techniques.",
        ("code_analyze", "project_analyze", "knowledge_retrieve", "error_diagnose"),
        ("Chercher les boucles sans yield", "Vérifier les allocations en hot path",
         "Réduire les réplications inutiles"),
        "Aucune régression fonctionnelle après optimisation."),
    "coordinator": RoleDef(
        "coordinator", "Agent Coordinateur",
        "Distribue le travail, contrôle les dépendances, vérifie les résultats des autres agents.",
        ("agent_get_task_status", "agent_review_result", "agent_create_checkpoint"),
        ("Respecter l'ordre des dépendances", "Checkpoint après chaque étape",
         "Stopper en cas d'erreur répétée"),
        "Le bilan final liste ce qui a été fait, testé et vérifié."),
}


def role_for_tool(tool: str) -> str:
    for role in ROLES.values():
        if tool in role.tools:
            return role.id
    return "coordinator"
