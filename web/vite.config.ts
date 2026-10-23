import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API is the compose service or a local `python -m pramana` on 8080.
const api = process.env.PRAMANA_API ?? "http://127.0.0.1:8080";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": api, "/health": api } },
});
