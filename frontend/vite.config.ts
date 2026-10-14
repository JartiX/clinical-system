import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// В разработке запросы /api уходят на локальный FastAPI
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": process.env.API_URL ?? "http://localhost:8000" },
  },
});
