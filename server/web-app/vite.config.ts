import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { port: 80, host: true, allowedHosts: ['1bit2qbit.theburkenator.com'] },
  preview: { port: 80, host: true, allowedHosts: ['1bit2qbit.theburkenator.com'] },
})
