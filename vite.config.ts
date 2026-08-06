import path from 'path';
import { readFileSync } from 'node:fs';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '');
  const deployVersion = readFileSync(path.resolve(__dirname, 'VERSION'), 'utf8').trim();
  if (!/^\d+$/.test(deployVersion)) {
    throw new Error(`VERSION inválida: '${deployVersion}'. Debe ser un número entero positivo.`);
  }
  return {
    server: {
      port: 3002,
      // host: '0.0.0.0',
      proxy: {
        '/api/v1': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
        }
      }
    },
    plugins: [react()],
    define: {
      '__MSMALL_DEPLOY_VERSION__': JSON.stringify(deployVersion),
      'process.env.API_KEY': JSON.stringify(env.GEMINI_API_KEY),
      'process.env.GEMINI_API_KEY': JSON.stringify(env.GEMINI_API_KEY)
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      }
    }
  };
});
