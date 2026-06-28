import { defineConfig } from "vite";
import { spawn } from "child_process";

function backendPlugin() {
  let proc;
  return {
    name: "start-backend",
    configureServer() {
      proc = spawn("node", ["server/index.js"], {
        stdio: "inherit",
        cwd: process.cwd(),
        env: { ...process.env },
      });
      proc.on("error", (err) => console.error("Backend failed to start:", err.message));
      proc.on("exit", (code) => {
        if (code) console.error(`Backend exited with code ${code}`);
      });
    },
    closeBundle() {
      if (proc) proc.kill();
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
        target: "http://localhost:8001",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:8001",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "../dist",
  },
});
