import { existsSync } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import { join } from "node:path";

const backendDir = join(process.cwd(), "apps", "backend");
const isWindows = process.platform === "win32";
const venvPython = join(
  backendDir,
  ".venv",
  isWindows ? "Scripts/python.exe" : "bin/python",
);
const python = existsSync(venvPython) ? venvPython : "python";

const pythonCheck = spawnSync(python, ["--version"], {
  cwd: backendDir,
  encoding: "utf8",
});

if (pythonCheck.status !== 0) {
  console.error("Backend virtualenv Python is not runnable.");
  console.error((pythonCheck.stderr || pythonCheck.stdout).trim());
  console.error("");
  console.error("Recreate the backend virtualenv, then run this command again:");
  console.error("  py -0p");
  console.error("  # If Python 3.12 is not listed, install Python 3.12 first.");
  console.error("  cd apps\\backend");
  console.error("  py -3.12 -m venv .venv");
  console.error("  .\\.venv\\Scripts\\python -m pip install -r requirements.txt");
  console.error("  .\\.venv\\Scripts\\python -m pip install pillow-heif");
  process.exit(pythonCheck.status ?? 1);
}

const server = spawn(
  python,
  ["-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"],
  {
    cwd: backendDir,
    stdio: "inherit",
  },
);

process.on("SIGINT", () => server.kill("SIGINT"));
process.on("SIGTERM", () => server.kill("SIGTERM"));

server.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }

  process.exit(code ?? 0);
});
