import { loadPyodide, version, reloadPyodideLockFileURL, reloadPyodideLockFileURLSync } from "./pyodide";
import { type PackageData } from "./types";
export { loadPyodide, reloadPyodideLockFileURL, reloadPyodideLockFileURLSync, version, type PackageData };
(globalThis as any).loadPyodide = loadPyodide;
// FIXME: export in a more private place
(globalThis as any).reloadPyodideLockFileURL = reloadPyodideLockFileURL;
(globalThis as any).reloadPyodideLockFileURLSync = reloadPyodideLockFileURLSync;
