import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
    hmr: {
      overlay: false,
    },
    proxy: {
      "/auth": "http://localhost:8000",
      "/drive": "http://localhost:8000",
      "/documents/latest": "http://localhost:8000",
      "/documents/all": "http://localhost:8000",
      "/documents/deals": "http://localhost:8000",
      "/documents/stats": "http://localhost:8000",
      "/documents/locked": "http://localhost:8000",
      "/sync": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/org": "http://localhost:8000",
    },
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      react: path.resolve(__dirname, "./node_modules/react"),
      "react-dom": path.resolve(__dirname, "./node_modules/react-dom"),
    },
    dedupe: ["react", "react-dom", "react/jsx-runtime"],
  },
  optimizeDeps: {
    include: ["react", "react-dom", "framer-motion"],
  },
}));
