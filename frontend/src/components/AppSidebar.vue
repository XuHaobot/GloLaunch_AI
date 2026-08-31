<template>
  <aside class="sidebar">
    <div class="sidebar-brand">
      <div class="sb-logo"><el-icon><Promotion /></el-icon></div>
      <div class="sb-brand-text">
        <span class="sb-title">GloLaunch AI</span>
        <span class="sb-subtitle">AI 场景上新工作台</span>
      </div>
    </div>

    <!-- 纵向流水线拓扑 -->
    <nav class="topology-nav">
      <div
        v-for="(node, idx) in topoNodes"
        :key="node.id"
        class="topo-node"
        :class="getNodeClass(node)"
        @click="$emit('navigate', node.section)"
      >
        <div class="topo-indicator">
          <div class="topo-dot" :class="getDotClass(node)">
            <el-icon v-if="getDotClass(node).running" class="is-loading"><Loading /></el-icon>
            <el-icon v-else-if="getDotClass(node).completed"><CircleCheckFilled /></el-icon>
          </div>
          <div v-if="idx < topoNodes.length - 1" class="topo-line" :class="{ done: getDotClass(node).completed }"></div>
        </div>
        <div class="topo-body">
          <div class="topo-name">{{ node.name }}</div>
          <div class="topo-meta">{{ getMetaText(node) }}</div>
        </div>
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
      <div class="sb-footer-line">v4.0 · 场景上新</div>
    </div>
  </aside>
</template>

<script setup>
import { ref } from 'vue'
import { Loading, CircleCheckFilled } from '@element-plus/icons-vue'

const props = defineProps({
  active: { type: String, default: 'new_product' },
  runningNode: { type: String, default: null },
  completedNodes: { type: Array, default: () => [] },
})
defineEmits(['navigate'])

const topoNodes = [
  { id: 'extract_attributes', name: '商品智能解析', section: 'new_product', icon: 'Search', model: 'Qwen-VL' },
  { id: 'analyze_market', name: '出海市场洞察', section: 'research', icon: 'DataAnalysis', model: 'Qwen + RAG' },
  { id: 'opportunity_score', name: '上架机会评分', section: 'launch_plan', icon: 'TrendCharts', model: 'Intelligence' },
  { id: 'asset_inventory', name: '素材盘点与缺口', section: 'studio', icon: 'Files', model: 'Asset Analyzer' },
  { id: 'trend_benchmark', name: '爆款对标研究', section: 'research', icon: 'TrendCharts', model: '爆款语料 RAG' },
  { id: 'generate_listing', name: '爆款化 Listing', section: 'listing', icon: 'EditPen', model: 'Qwen-Plus' },
  { id: 'studio_generation', name: 'AI 商品摄影', section: 'studio', icon: 'Camera', model: 'Wan2.7' },
  { id: 'video_production', name: '带货视频生产', section: 'studio', icon: 'VideoCamera', model: '分镜 + TTS' },
  { id: 'image_localization', name: '图片文字本地化', section: 'studio', icon: 'MapLocation', model: '图翻 / VL' },
  { id: 'adapt_platform', name: '平台合规质检', section: 'publish', icon: 'Stamp', model: 'Qwen-Flash' },
  { id: 'publish_package', name: '发布包组装审核', section: 'publish', icon: 'Finished', model: 'Health Check' },
  { id: 'respond', name: '成果汇总打包', section: 'publish', icon: 'Box', model: 'LangGraph' },
]

function getNodeClass(node) {
  return {
    'is-running': props.runningNode === node.id,
    'is-completed': props.completedNodes.includes(node.id),
    'is-active': props.active === node.section,
  }
}

function getDotClass(node) {
  return {
    running: props.runningNode === node.id,
    completed: props.completedNodes.includes(node.id),
  }
}

function getMetaText(node) {
  if (props.runningNode === node.id) return '执行中...'
  if (props.completedNodes.includes(node.id)) return '已完成'
  return node.model
}

// 深浅色主题切换
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

/* ── 纵向拓扑 ── */
.topology-nav {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 10px 12px 14px;
  display: flex;
  flex-direction: column;
}
.topo-node {
  display: flex;
  align-items: stretch;
  gap: 10px;
  cursor: pointer;
  padding: 4px 0;
  border-radius: 6px;
  transition: background 0.15s;
}
.topo-node:hover { background: var(--gl-hover); }
.topo-node.is-active .topo-name { color: #38bdf8; font-weight: 600; }

/* 左侧指示器列：圆点 + 连线 */
.topo-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 18px;
  flex-shrink: 0;
}
.topo-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid var(--gl-border-3);
  background: var(--gl-panel-deep);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  color: var(--gl-sub);
  flex-shrink: 0;
  transition: all 0.25s;
}
.topo-dot.running {
  border-color: #38bdf8;
  background: rgba(56, 189, 248, 0.15);
  color: #38bdf8;
  box-shadow: 0 0 8px rgba(56, 189, 248, 0.4);
}
.topo-dot.completed {
  border-color: #22c55e;
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}
.topo-line {
  flex: 1;
  width: 2px;
  background: var(--gl-border-3);
  min-height: 8px;
  transition: background 0.3s;
}
.topo-line.done { background: rgba(34, 197, 94, 0.5); }

/* 右侧内容 */
.topo-body {
  flex: 1;
  min-width: 0;
  padding-bottom: 6px;
}
.topo-name {
  font-size: 12.5px;
  color: var(--gl-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.15s;
}
.topo-meta {
  font-size: 10px;
  color: var(--gl-sub);
  margin-top: 1px;
}
.topo-node.is-running .topo-name { color: #38bdf8; }
.topo-node.is-running .topo-meta { color: #38bdf8; }
.topo-node.is-completed .topo-name { color: #22c55e; }
.topo-node.is-completed .topo-meta { color: rgba(34, 197, 94, 0.7); }

/* ── Footer ── */
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
