import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Read .env from the project root (hw4/.env) so frontend and backend share one file.
  // Only VITE_-prefixed variables are exposed to browser code.
  envDir: "..",
  server: {
    port: 5173,
  },
});
