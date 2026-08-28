import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import './theme.css'

// 主题初始化：默认暗色，尊重用户上次选择（持久化于 localStorage）
const savedTheme = localStorage.getItem('gl-theme') || 'dark'
document.documentElement.classList.toggle('dark', savedTheme === 'dark')

const app = createApp(App)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(ElementPlus)
app.mount('#app')
