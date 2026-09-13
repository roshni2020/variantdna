export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: false },
  modules: ['@nuxt/ui'],
  css: ['~/assets/css/main.css'],
  ssr: false,
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000',
    },
  },
  app: {
    head: {
      title: 'VariantCourt',
      meta: [{ name: 'description', content: 'AI courtroom for DNA variant interpretation. Research prototype, not for clinical diagnosis.' }],
    },
  },
})
