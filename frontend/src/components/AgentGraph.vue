<template>
  <div class="agent-graph-container">
    <div class="graph-header">
      <div class="title-area">
        <el-icon class="pulse-icon"><Cpu /></el-icon>
        <span class="title">LangGraph 全链路工作台</span>
        <span class="intent-tag" v-if="intentLabel">{{ intentLabel }}</span>
      </div>
      <div class="header-right">
        <span class="eta-text" v-if="isRunning && etaSeconds > 0">
          <el-icon class="is-loading"><Loading /></el-icon>
          预计还需约 {{ etaSeconds }} 秒
        </span>
        <span class="eta-text done" v-else-if="allCompleted">全部完成</span>
        <el-tag :type="statusTagType" size="small" effect="dark">
          {{ graphStatusText }}
        </el-tag>
      </div>
    </div>

    <!-- 总进度条 -->
    <div class="progress-bar-wrap" v-if="isRunning || allCompleted">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
      <span class="progress-text">{{ progressPercent }}%</span>
    </div>

    <!-- 阶段泳道：按 商品理解 → 市场洞察 → 内容生产 → 合规发布 分组 -->
    <div class="stage-lanes">
      <div 
        v-for="(stage, sIdx) in visibleStages" 
        :key="stage.id" 
        class="stage-lane"
        :class="{ 'stage-active': isStageActive(stage), 'stage-done': isStageDone(stage) }"
      >
        <div class="stage-head">
          <span class="stage-status-icon">
            <el-icon v-if="isStageDone(stage)" color="#22c55e"><CircleCheckFilled /></el-icon>
            <el-icon v-else-if="isStageActive(stage)" class="is-loading" color="#38bdf8"><Loading /></el-icon>
            <span v-else class="stage-num">{{ sIdx + 1 }}</span>
          </span>
          <span class="stage-label">{{ stage.label }}</span>
        </div>

        <div class="stage-nodes">
          <div 
            v-for="node in nodesByStage(stage.id)" 
            :key="node.id"
            class="graph-node"
            :class="getNodeState(node.id)"
          >
            <div class="node-icon"><el-icon><component :is="node.icon" /></el-icon></div>
            <div class="node-info">
              <div class="node-name">{{ node.name }}</div>
              <div class="node-desc">
                <template v-if="getNodeState(node.id) === 'running'">
                  <el-icon class="is-loading mini"><Loading /></el-icon> 执行中...
                </template>
                <template v-else-if="getNodeState(node.id) === 'completed'">
                  {{ durationText(node.id) }}
                </template>
                <template v-else>{{ node.model }}</template>
              </div>
            </div>
          </div>
        </div>

        <!-- 阶段间箭头 -->
        <div v-if="sIdx < visibleStages.length - 1" class="lane-arrow" :class="{ active: isStageDone(stage) }">
          <el-icon><Right /></el-icon>
        </div>
      </div>
    </div>

    <!-- 实时执行 Trace 日志 -->
    <div class="trace-log-box" v-if="traceLogs.length > 0">
      <div class="log-title">
        <el-icon><Operation /></el-icon>
        <span>执行轨迹 Trace ({{ traceLogs.length }})</span>
      </div>
      <div class="log-items">
        <div v-for="(log, i) in traceLogs" :key="i" class="log-item">
          <span class="log-badge">{{ log.node }}</span>
          <span class="log-summary">{{ log.summary }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Cpu, Loading, CircleCheckFilled, Right, Operation } from '@element-plus/icons-vue'

const props = defineProps({
  runningNode: { type: String, default: null },
  completedNodes: { type: Array, default: () => [] },
  plannedNodes: { type: Array, default: () => [] },
  stages: { type: Array, default: () => [] },
  intent: { type: String, default: 'full_launch' },
  traceLogs: { type: Array, default: () => [] },
  isRunning: { type: Boolean, default: false },
  etaSeconds: { type: Number, default: 0 },
  nodeDurations: { type: Object, default: () => ({}) }
})

// 后端未推送 plan 时的默认全链路泳道（兜底展示）
const DEFAULT_STAGES = [
  { id: 'understand', label: '① 商品理解' },
  { id: 'insight', label: '② 市场洞察' },
  { id: 'decision', label: '③ 上架决策' },
  { id: 'benchmark', label: '④ 爆款对标' },
  { id: 'content', label: '⑤ 内容生产' },
  { id: 'publish', label: '⑥ 合规发布' }
]
const DEFAULT_NODES = [
  { id: 'extract_attributes', name: '商品智能解析', stage: 'understand', model: 'Qwen-VL 多模态', icon: 'Search' },
  { id: 'analyze_market', name: '出海市场洞察', stage: 'insight', model: 'Qwen 旗舰 + RAG', icon: 'DataAnalysis' },
  { id: 'opportunity_score', name: '上架机会评分', stage: 'decision', model: 'Intelligence Engine', icon: 'TrendCharts' },
  { id: 'asset_inventory', name: '素材盘点与缺口', stage: 'decision', model: 'Asset Analyzer', icon: 'Files' },
  { id: 'trend_benchmark', name: '爆款对标研究', stage: 'benchmark', model: '爆款语料 RAG', icon: 'TrendCharts' },
  { id: 'generate_listing', name: '爆款化 Listing', stage: 'content', model: 'Qwen-Plus', icon: 'EditPen' },
  { id: 'studio_generation', name: 'AI 商品摄影', stage: 'content', model: '搬运原素材 / Wan2.7 按需', icon: 'Camera' },
  { id: 'video_production', name: '带货视频生产', stage: 'content', model: '分镜 + TTS + 合成', icon: 'VideoCamera' },
  { id: 'image_localization', name: '图片文字本地化', stage: 'content', model: '阿里图翻 / Qwen-VL', icon: 'MapLocation' },
  { id: 'adapt_platform', name: '平台合规质检', stage: 'publish', model: 'Qwen-Flash', icon: 'Stamp' },
  { id: 'publish_package', name: '发布包组装审核', stage: 'publish', model: 'Listing Health', icon: 'Finished' },
  { id: 'respond', name: '成果汇总打包', stage: 'publish', model: 'LangGraph Core', icon: 'Box' }
]
const INTENT_LABELS = {
  full_launch: '全链路上新',
  market_only: '仅市场洞察',
  listing_only: '仅 Listing'
}

const activeNodes = computed(() => props.plannedNodes.length ? props.plannedNodes : DEFAULT_NODES)
const visibleStages = computed(() => {
  const stages = props.stages.length ? props.stages : DEFAULT_STAGES
  const usedStageIds = new Set(activeNodes.value.map(n => n.stage))
  return stages.filter(s => usedStageIds.has(s.id))
})
const intentLabel = computed(() => INTENT_LABELS[props.intent] || '')

const progressPercent = computed(() => {
  const total = activeNodes.value.length
  if (!total) return 0
  return Math.round((props.completedNodes.length / total) * 100)
})

const allCompleted = computed(() =>
  activeNodes.value.length > 0 && props.completedNodes.length >= activeNodes.value.length
)

function nodesByStage(stageId) {
  return activeNodes.value.filter(n => n.stage === stageId)
}

function getNodeState(nodeId) {
  if (props.completedNodes.includes(nodeId)) return 'completed'
  if (props.runningNode === nodeId) return 'running'
  return 'pending'
}

function isStageActive(stage) {
  return nodesByStage(stage.id).some(n => n.id === props.runningNode)
}

function isStageDone(stage) {
  const nodes = nodesByStage(stage.id)
  return nodes.length > 0 && nodes.every(n => props.completedNodes.includes(n.id))
}

function durationText(nodeId) {
  const d = props.nodeDurations[nodeId]
  return d != null ? `完成 · ${d}s` : '完成'
}

const graphStatusText = computed(() => {
  if (props.isRunning) return 'Agent 编排执行中'
  if (allCompleted.value) return '全链路执行完毕'
  return '就绪'
})

const statusTagType = computed(() => {
  if (props.isRunning) return 'warning'
  if (allCompleted.value) return 'success'
  return 'info'
})
</script>

<style scoped>
.agent-graph-container {
  background: linear-gradient(135deg, var(--gl-node) 0%, var(--gl-panel-deep) 100%);
  border: 1px solid var(--gl-border-2);
  border-radius: 12px;
  padding: 12px 16px;
  color: var(--gl-text-hi);
  box-shadow: 0 10px 25px -5px var(--gl-shadow);
}

.graph-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--gl-border-2);
}

.title-area {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 15px;
  color: #38bdf8;
}

.intent-tag {
  font-size: 11px;
  color: var(--gl-bg);
  background: #38bdf8;
  border-radius: 4px;
  padding: 1px 8px;
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.eta-text {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #fbbf24;
}

.eta-text.done {
  color: #22c55e;
}

.pulse-icon {
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.1); }
}

.progress-bar-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: var(--gl-border-2);
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #38bdf8, #22c55e);
  border-radius: 3px;
  transition: width 0.5s ease;
}

.progress-text {
  font-size: 12px;
  color: var(--gl-sub);
  width: 38px;
  text-align: right;
}

.stage-lanes {
  display: flex;
  align-items: stretch;
  gap: 4px;
  overflow-x: auto;
}

.stage-lane {
  flex: 1;
  min-width: 170px;
  background: var(--gl-panel-deep);
  border: 1px solid var(--gl-border-2);
  border-radius: 10px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  position: relative;
  transition: all 0.3s ease;
}

.stage-lane.stage-active {
  border-color: #38bdf8;
  box-shadow: 0 0 14px rgba(56, 189, 248, 0.25);
}

.stage-lane.stage-done {
  border-color: rgba(34, 197, 94, 0.5);
}

.stage-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--gl-text);
}

.stage-num {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--gl-border-2);
  color: var(--gl-sub);
  font-size: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.stage-status-icon {
  display: flex;
  align-items: center;
}

.stage-nodes {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.graph-node {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--gl-node);
  border: 1px solid var(--gl-border-3);
  border-radius: 8px;
  padding: 6px 9px;
  transition: all 0.3s ease;
}

.graph-node.pending {
  opacity: 0.5;
  border-color: var(--gl-border-2);
}

.graph-node.running {
  background: rgba(56, 189, 248, 0.15);
  border-color: #38bdf8;
  box-shadow: 0 0 10px rgba(56, 189, 248, 0.4);
}

.graph-node.completed {
  background: rgba(34, 197, 94, 0.12);
  border-color: rgba(34, 197, 94, 0.6);
}

.node-icon {
  font-size: 15px;
  color: var(--gl-sub);
  display: flex;
  align-items: center;
}

.graph-node.running .node-icon { color: #38bdf8; }
.graph-node.completed .node-icon { color: #22c55e; }

.node-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.node-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--gl-text-hi2);
  white-space: nowrap;
}

.node-desc {
  font-size: 10px;
  color: var(--gl-sub);
  display: flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}

.graph-node.running .node-desc { color: #38bdf8; }
.graph-node.completed .node-desc { color: #22c55e; }

.mini { font-size: 10px; }

.lane-arrow {
  position: absolute;
  right: -12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--gl-border-3);
  z-index: 2;
  display: flex;
}

.lane-arrow.active { color: #22c55e; }

.trace-log-box {
  margin-top: 10px;
  background: var(--gl-panel-deep);
  border-radius: 6px;
  padding: 8px 12px;
  border: 1px solid var(--gl-node);
}

.log-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--gl-sub);
  margin-bottom: 8px;
}

.log-items {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 66px;
  overflow-y: auto;
}

.log-item {
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.log-badge {
  background: var(--gl-border-2);
  color: #38bdf8;
  padding: 1px 6px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 11px;
  flex-shrink: 0;
}

.log-summary {
  color: var(--gl-text-mid);
}
</style>
