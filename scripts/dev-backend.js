// Starts the FastAPI backend with the project's virtualenv Python.
// The venv lays out its interpreter differently on Windows and macOS/Linux,
// so pick the right path here instead of hard-coding one in package.json.
const { spawn } = require("child_process");
const path = require("path");

const backendDir = path.join(__dirname, "..", "apps", "backend");
const python =
  process.platform === "win32"
    ? path.join(backendDir, ".venv", "Scripts", "python.exe")
    : path.join(backendDir, ".venv", "bin", "python");

const child = spawn(
  python,
  ["-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"],
  { cwd: backendDir, stdio: "inherit" }
);

child.on("exit", (code) => process.exit(code ?? 1));
