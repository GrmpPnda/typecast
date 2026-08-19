import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";
import fs from "fs";

const ssl = process.env.VITE_SSL === "1";
const certsDir = path.resolve(__dirname, "../.certs");

function getHttpsConfig() {
  if (!ssl) return undefined;
  const certFile = path.join(certsDir, "localhost.pem");
  const keyFile = path.join(certsDir, "localhost-key.pem");
  if (!fs.existsSync(certFile) || !fs.existsSync(keyFile)) return undefined;
  return {
    key: fs.readFileSync(keyFile),
    cert: fs.readFileSync(certFile),
  };
}

const backendProtocol = ssl ? "https" : "http";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    https: getHttpsConfig(),
    proxy: {
      "/api": {
        target: `${backendProtocol}://localhost:8000`,
        changeOrigin: true,
        secure: false,
      },
      "/uploads": {
        target: `${backendProtocol}://localhost:8000`,
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
