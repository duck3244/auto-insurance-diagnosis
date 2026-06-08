import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Node 18 고정 → Vite 6 사용 (Vite 7 은 Node 20.19+ 필요).
// Tailwind 는 v3 사용 (v4 의 native oxide 엔진은 Node 20+ 요구). docs/frontend-tech-review.md 참고.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 백엔드 FastAPI(uvicorn) 로 프록시 — CORS 설정 없이 동일 출처처럼 호출
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
