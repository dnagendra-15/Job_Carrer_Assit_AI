import { defineConfig } from "vite";
import { spawn } from "child_process";

function backendPlugin() {
  let backendProc;
  return {
    name: "start-backend",
    configureServer() {
      const env = {
        ...process.env,
        PATH: `${process.env.HOME}/.local/bin:${process.env.PATH}`,
        PYTHONPATH: process.cwd(),
      };

      const pip = spawn("pip", ["install", "-r", "requirements.txt"], {
        stdio: "inherit",
        cwd: process.cwd(),
        env,
      });

      pip.on("close", (code) => {
        if (code !== 0) {
          console.error(`pip install exited with code ${code}, attempting to start backend anyway...`);
        }
        backendProc = spawn("python3", ["-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"], {
          stdio: "inherit",
          cwd: process.cwd(),
          env,
        });
        backendProc.on("error", (err) => console.error("Backend failed to start:", err.message));
      });

      pip.on("error", () => {
        backendProc = spawn("python3", ["-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"], {
          stdio: "inherit",
          cwd: process.cwd(),
          env,
        });
        backendProc.on("error", (err) => console.error("Backend failed to start:", err.message));
      });
    },
    closeBundle() {
      if (backendProc) backendProc.kill();
    },
  };
}

export default defineConfig({
  root: "frontend",
  plugins: [backendPlugin()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
      },
      "/health": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "../dist",
  },
});
