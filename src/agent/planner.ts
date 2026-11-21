import { roleForTool, type AgentRole } from "./roles.js";

export interface PlanStep {
  id: string;
  title: string;
  /** Tool to call (must exist in the registry). */
  tool: string;
  args: Record<string, unknown>;
  role: AgentRole;
  /** Ids of steps that must complete first. */
  dependsOn: string[];
  /** Acceptance criterion checked after execution. */
  acceptance: string;
}

export interface Plan {
  goal: string;
  steps: PlanStep[];
  rationale: string;
}

let stepCounter = 0;
function step(title: string, tool: string, args: Record<string, unknown>, dependsOn: string[] = [], acceptance = "Step completes without error"): PlanStep {
  return { id: `s${++stepCounter}`, title, tool, args, role: roleForTool(tool), dependsOn, acceptance };
}

/**
 * Deterministic planner: decomposes a goal into executable steps using
 * keyword routing over the real tool catalogue. The connected AI can refine
 * this plan via agent_create_plan with explicit steps; this is the safe
 * default that never invents tools.
 */
export function createPlan(goal: string, opts: { workspace?: string; projectPath?: string } = {}): Plan {
  stepCounter = 0;
  const g = goal.toLowerCase();
  const steps: PlanStep[] = [];
  const ws = opts.workspace ?? ".";

  const inspect = step("Inspect current project state", "project_inspect", { path: ws }, [], "Existing systems identified");
  steps.push(inspect);

  if (/roblox|studio|luau|jeu|game|combat|arena|personnage|character/.test(g)) {
    const kb = step("Retrieve Luau/Roblox knowledge", "knowledge_retrieve", { query: goal, limit: 6 }, [inspect.id], "Relevant docs retrieved with citations");
    steps.push(kb);
    const arch = step("Design system architecture", "agent_compare_solutions", {
      problem: goal,
      solutions: [
        { name: "ModuleScript services (ReplicatedStorage)", description: "Shared modules + RemoteEvents, standard Roblox pattern", pros: ["Standard", "Testable", "Réutilisable"], cons: ["Plus de fichiers"] },
        { name: "Monolithic Scripts", description: "Scripts uniques par système", pros: ["Simple au départ"], cons: ["Couplage fort", "Difficile à maintenir"] },
      ],
    }, [kb.id], "Architecture choisie avec compromis documentés");
    steps.push(arch);
    const build = step("Implement systems (Luau files)", "file_create", {
      path: "src/server/CombatServer.server.luau",
      content: "--!strict\n-- OMNIBRIDGE example combat server. Replace via file_update with the real implementation.\nlocal ReplicatedStorage = game:GetService(\"ReplicatedStorage\")\nprint(\"[CombatServer] ready\")\n",
    }, [arch.id], "Fichiers Luau créés et sauvegardés");
    steps.push(build);
    const analyze = step("Static analysis of generated Luau", "code_analyze", { path: "src/server/CombatServer.server.luau" }, [build.id], "Aucune erreur bloquante");
    steps.push(analyze);
    const test = step("Run tests / playtest checks", "code_test", { path: "src/server/CombatServer.server.luau" }, [analyze.id], "Tests passent ou écarts documentés");
    steps.push(test);
    const review = step("Review final result", "agent_review_result", { taskId: "pending", stepId: test.id }, [test.id], "Bilan présenté");
    steps.push(review);
  } else if (/recherche|research|documentation|doc|compare|comparer|web/.test(g)) {
    const search = step("Search web sources", "web_search", { query: goal, maxResults: 6 }, [inspect.id], "Sources officielles identifiées");
    steps.push(search);
    const compare = step("Compare sources", "web_compare_sources", { query: goal, urls: [] }, [search.id], "Contradictions signalées");
    steps.push(compare);
    const kb = step("Index findings into knowledge base", "knowledge_index", { source: "agent-research", title: goal, text: goal }, [compare.id], "Synthèse indexée");
    steps.push(kb);
  } else if (/bug|erreur|error|debug|fix|corriger/.test(g)) {
    const diag = step("Diagnose error", "error_diagnose", { message: goal, path: ws }, [inspect.id], "Cause racine identifiée");
    steps.push(diag);
    const fix = step("Apply fix", "file_update", { path: "src/fix.luau", content: "-- fix placeholder\n" }, [diag.id], "Correction appliquée avec sauvegarde");
    steps.push(fix);
    const test = step("Verify fix", "code_test", { path: "src/fix.luau" }, [fix.id], "Erreur disparue");
    steps.push(test);
  } else {
    const kb = step("Retrieve relevant knowledge", "knowledge_retrieve", { query: goal, limit: 6 }, [inspect.id], "Contexte récupéré");
    steps.push(kb);
    const exec = step("Execute core action", "file_list", { path: ws }, [kb.id], "Action exécutée");
    steps.push(exec);
    const review = step("Review result", "agent_review_result", { taskId: "pending", stepId: exec.id }, [exec.id], "Bilan présenté");
    steps.push(review);
  }

  return {
    goal,
    steps,
    rationale: `Plan généré par le planificateur déterministe OMNIBRIDGE (${steps.length} étapes). ` +
      `Boucle: ANALYSE → PLANIFICATION → RECHERCHE → EXÉCUTION → TEST → INSPECTION → CORRECTION → VALIDATION. ` +
      `Chaque étape est checkpointée et annulable.`,
  };
}
