<template>
  <div class="tm-view">
    <div class="tm-head">
      <div class="tm-title"><el-icon><Tickets /></el-icon> 任务管理</div>
      <el-button size="small" plain @click="load">
        <el-icon><RefreshRight /></el-icon> 刷新
      </el-button>
    </div>

    <div v-if="loading" class="tm-empty">加载中…</div>
    <div v-else-if="!list.length" class="tm-empty">暂无历史任务，完成一次上新后自动存档</div>

    <div v-else class="tm-list">
      <div class="tm-item" v-for="t in list" :key="t.thread_id" @click="$emit('view-task', t)">
        <div class="tm-item-main">
          <div class="tm-name">{{ t.category || '未命名商品' }}</div>
          <div class="tm-meta">
            <el-tag size="small">{{ t.platform || 'Amazon' }}</el-tag>
            <el-tag size="small" type="info">{{ t.market || 'US' }}</el-tag>
            <el-tag size="small" type="success">{{ intentLabel(t.intent) }}</el-tag>
            <span class="tm-time">{{ formatTime(t.created_at) }}</span>
          </div>
        </div>
        <el-button size="small" type="primary" plain>查看成果</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { RefreshRight } from '@element-plus/icons-vue'

defineEmits(['view-task'])

const list = ref([])
const loading = ref(false)

const INTENT_LABELS = {
  full_launch: '全链路上新',
  market_only: '仅市场洞察',
  listing_only: '仅 Listing',
}
function intentLabel(intent) {
  return INTENT_LABELS[intent] || '全链路上新'
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function load() {
  loading.value = true
  try {
    const resp = await fetch('/api/tasks?limit=50')
    const data = await resp.json()
    list.value = data.tasks || []
  } catch (e) {
    console.error('获取任务历史失败:', e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.tm-view { flex: 1; overflow-y: auto; padding: 24px 28px; }
.tm-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
.tm-title { font-size: 17px; font-weight: 700; color: var(--gl-text-hi); display: inline-flex; align-items: center; gap: 8px; }
.tm-empty { text-align: center; color: var(--gl-faint); font-size: 13px; padding: 60px 0; }
.tm-list { display: flex; flex-direction: column; gap: 10px; }
.tm-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--gl-panel);
  border: 1px solid var(--gl-border);
  border-radius: 10px;
  padding: 14px 16px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.tm-item:hover { border-color: var(--gl-hover-border); }
.tm-name { font-size: 14px; font-weight: 600; color: var(--gl-text-hi2); margin-bottom: 6px; }
.tm-meta { display: flex; align-items: center; gap: 8px; }
.tm-time { font-size: 11px; color: var(--gl-faint); }
</style>
