<template>
  <div class="cx-view">
    <div class="cx-head">
      <div class="cx-title"><el-icon><Connection /></el-icon> 连接</div>
      <el-button size="small" plain @click="load">
        <el-icon><RefreshRight /></el-icon> 刷新
      </el-button>
    </div>

    <div class="cx-grid">
      <div class="cx-card" v-for="c in items" :key="c.id">
        <div class="cx-card-head">
          <div class="cx-name">{{ c.name }}</div>
          <el-tag size="small" :type="c.configured ? 'success' : 'warning'" effect="dark">
            {{ c.status_text }}
          </el-tag>
        </div>
        <div class="cx-desc">{{ c.desc }}</div>
        <a v-if="c.action_url" :href="c.action_url" target="_blank" class="cx-action">去授权 →</a>
      </div>
    </div>

    <div class="cx-tip">凭证统一存放于 backend/.env，已被 .gitignore 忽略，不会入库。</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { RefreshRight } from '@element-plus/icons-vue'

const items = ref([])

async function load() {
  try {
    const resp = await fetch('/api/system/connections')
    const data = await resp.json()
    items.value = data.items || []
  } catch (e) {
    console.error('获取连接状态失败:', e)
  }
}

onMounted(load)
</script>

<style scoped>
.cx-view { flex: 1; overflow-y: auto; padding: 24px 28px; }
.cx-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.cx-title { font-size: 17px; font-weight: 700; color: var(--gl-text-hi); display: inline-flex; align-items: center; gap: 8px; }
.cx-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
.cx-card {
  background: var(--gl-panel);
  border: 1px solid var(--gl-border);
  border-radius: 12px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.cx-card-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.cx-name { font-size: 14px; font-weight: 600; color: var(--gl-text-hi2); }
.cx-desc { font-size: 12px; color: var(--gl-sub); line-height: 1.7; flex: 1; }
.cx-action { font-size: 12px; color: #60a5fa; text-decoration: none; }
.cx-action:hover { text-decoration: underline; }
.cx-tip { margin-top: 18px; font-size: 11px; color: var(--gl-faint); }
</style>
