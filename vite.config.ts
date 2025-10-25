import fs from "node:fs";
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function createHttpsConfig() {
  if (process.env.VITE_DEV_HTTPS !== "true") {
    return false;
  }

  const keyPath = path.resolve(process.cwd(), process.env.VITE_DEV_TLS_KEY ?? "certs/localhost-key.pem");
  const certPath = path.resolve(process.cwd(), process.env.VITE_DEV_TLS_CERT ?? "certs/localhost-cert.pem");

  try {
    return {
      key: fs.readFileSync(keyPath),
      cert: fs.readFileSync(certPath)
    };
  } catch (error) {
    console.warn("[vite] Unable to load HTTPS certificates. Falling back to HTTP.", error);
    return false;
  }
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    https: createHttpsConfig()
  }
});
