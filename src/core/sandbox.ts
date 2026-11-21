import { realpathSync } from "node:fs";
import { isAbsolute, relative, resolve, sep } from "node:path";

/**
 * Path sandbox: every file operation must stay inside the workspace root.
 * Symlinks escaping the root are rejected. Throws on violation.
 */
export function sandboxResolve(root: string, userPath: string): string {
  const absRoot = resolve(root);
  const candidate = isAbsolute(userPath) ? resolve(userPath) : resolve(absRoot, userPath);
  const rel = relative(absRoot, candidate);
  if (rel.startsWith(".." + sep) || rel === ".." || isAbsolute(rel)) {
    throw new Error(`Path escapes workspace sandbox: ${userPath}`);
  }
  // If the path exists, verify its real location too (symlink escape).
  try {
    const real = realpathSync(candidate);
    const realRoot = realpathSync(absRoot);
    const realRel = relative(realRoot, real);
    if (realRel.startsWith(".." + sep) || realRel === "..") {
      throw new Error(`Path escapes workspace sandbox via symlink: ${userPath}`);
    }
    return real;
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") return candidate;
    throw e;
  }
}

export function isInside(root: string, p: string): boolean {
  const rel = relative(resolve(root), resolve(p));
  return !(rel.startsWith(".." + sep) || rel === ".." || isAbsolute(rel));
}
