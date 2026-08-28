<template>
  <aside class="sidebar">
    <div class="sidebar-brand">
      <div class="sb-logo"><el-icon><Promotion /></el-icon></div>
      <div class="sb-brand-text">
        <span class="sb-title">GloLaunch AI</span>
        <span class="sb-subtitle">跨境智能上新引擎</span>
      </div>
    </div>

    <nav class="sidebar-nav">
      <div
        v-for="item in items"
        :key="item.id"
        class="sb-nav-item"
        :class="{ active: active === item.id }"
        @click="$emit('navigate', item.id)"
      >
        <el-icon class="sb-nav-icon"><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </div>
    </nav>

    <div class="sidebar-footer">
      <div class="sb-theme-row">
        <span class="sb-theme-label">
          <el-icon><component :is="isDark ? 'Moon' : 'Sunny'" /></el-icon>
          {{ isDark ? '深色模式' : '浅色模式' }}
        </span>
        <el-switch v-model="isDark" size="small" @change="toggleTheme" />
      </div>
      <div class="sb-footer-line">v3.2 · LangGraph Core</div>
    </div>
  </aside>
</template>

<script setup>
import { ref } from 'vue'

defineProps({ active: { type: String, default: 'workbench' } })
defineEmits(['navigate'])

const items = [
  { id: 'workbench', icon: 'Plus', label: '新任务' },
  { id: 'hub', icon: 'MagicStick', label: '工作流和技能' },
  { id: 'tasks', icon: 'Tickets', label: '任务管理' },
  { id: 'connections', icon: 'Connection', label: '连接' },
]

// 深浅色主题切换（与 main.js 初始化逻辑一致，持久化于 localStorage）
const isDark = ref(document.documentElement.classList.contains('dark'))
function toggleTheme(val) {
  document.documentElement.classList.toggle('dark', val)
  localStorage.setItem('gl-theme', val ? 'dark' : 'light')
}
</script>

<style scoped>
.sidebar {
  width: 216px;
  flex-shrink: 0;
  height: 100vh;
  background: var(--gl-side);
  border-right: 1px solid var(--gl-border);
  display: flex;
  flex-direction: column;
}
.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px;
  border-bottom: 1px solid var(--gl-border);
}
.sb-logo {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: linear-gradient(135deg, #2563eb 0%, #38bdf8 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
}
.sb-brand-text { display: flex; flex-direction: column; }
.sb-title { font-size: 15px; font-weight: 700; color: var(--gl-text-hi); }
.sb-subtitle { font-size: 10px; color: var(--gl-faint); }
.sidebar-nav { flex: 1; padding: 12px 8px; display: flex; flex-direction: column; gap: 4px; }
.sb-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  color: var(--gl-sub);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.sb-nav-item:hover { background: var(--gl-hover); color: var(--gl-text); }
.sb-nav-item.active { background: var(--gl-active); color: var(--gl-text-hi); font-weight: 600; }
.sb-nav-icon { font-size: 15px; }
.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--gl-border);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sb-theme-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.sb-theme-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--gl-sub);
}
.sb-footer-line { font-size: 10px; color: var(--gl-faint); }
</style>
