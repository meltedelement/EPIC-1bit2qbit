import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/verify/',
  server: { port: 3000, host: true, allowedHosts: ['1bit2qbit.theburkenator.com'] },
  preview: { port: 3000, host: true, allowedHosts: ['1bit2qbit.theburkenator.com'] },
})
