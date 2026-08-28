<template>
  <div class="hub-page">
    <div class="hub-banner">
      <div class="hub-banner-left">
        <div class="hub-banner-title">工作流和技能</div>
        <div class="hub-banner-desc">
          工作流串联多个技能一键交付上新全链路；技能是可独立调用的原子能力，
          也可以创建自定义技能扩展你的 Agent
        </div>
      </div>
      <el-icon class="hub-banner-art"><MagicStick /></el-icon>
    </div>

    <div class="hub-tabs-row">
      <el-radio-group v-model="tab" size="default">
        <el-radio-button value="workflows">工作流</el-radio-button>
        <el-radio-button value="skills">技能</el-radio-button>
        <el-radio-button value="custom">我创建的</el-radio-button>
      </el-radio-group>
      <el-button v-if="tab === 'custom'" type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> 创建技能
      </el-button>
    </div>

    <!-- 工作流卡片 -->
    <div v-if="tab === 'workflows'" class="hub-grid">
      <div v-for="wf in workflows" :key="wf.id" class="hub-card">
        <div class="hub-icon"><el-icon><component :is="wf.icon" /></el-icon></div>
        <div class="hub-card-main">
          <div class="hub-card-title">{{ wf.name }}</div>
          <div class="hub-card-desc">{{ wf.desc }}</div>
          <div class="hub-card-meta">串联 {{ wf.skillCount }} 个技能</div>
        </div>
        <el-button type="primary" size="small" @click="$emit('use-workflow', wf.id)">使用</el-button>
      </div>
    </div>

    <!-- 内置技能卡片（开关真实控制后端路由） -->
    <div v-if="tab === 'skills'" class="hub-grid">
      <div v-for="sk in builtinSkills" :key="sk.id" class="hub-card">
        <div class="hub-icon"><el-icon><component :is="sk.icon" /></el-icon></div>
        <div class="hub-card-main">
          <div class="hub-card-title">
            {{ sk.name }}
            <el-tag v-if="sk.tag === 'ondemand'" size="small" type="info">按需</el-tag>
            <el-tag v-else-if="sk.tag === 'core'" size="small">核心</el-tag>
          </div>
          <div class="hub-card-desc">{{ sk.desc }}</div>
        </div>
        <div class="hub-card-action">
          <el-switch
            v-if="sk.tag === 'optional'"
            :model-value="!disabledStages.includes(sk.id)"
            @change="(v) => $emit('toggle-stage', sk.id, v)"
          />
        </div>
      </div>
    </div>

    <!-- 我创建的：自定义技能（Agent 插件扩展点） -->
    <div v-if="tab === 'custom'" class="hub-grid">
      <div v-if="!customSkills.length" class="hub-empty">
        <el-empty description="还没有自定义技能。创建一个提示词技能，例如「西班牙语文案润色」「尺码表生成」，让 Agent 拥有新能力" />
      </div>
      <div v-for="sk in customSkills" :key="sk.id" class="hub-card">
        <div class="hub-icon hub-icon-custom"><el-icon><component :is="sk.icon || 'MagicStick'" /></el-icon></div>
        <div class="hub-card-main">
          <div class="hub-card-title">
            {{ sk.name }}
            <el-tag size="small" type="warning">自建</el-tag>
          </div>
          <div class="hub-card-desc">{{ sk.description }}</div>
          <div class="hub-card-meta">创建于 {{ sk.created_at }}</div>
        </div>
        <div class="hub-card-action">
          <el-button size="small" type="primary" plain @click="openRun(sk)">运行</el-button>
          <el-button size="small" type="danger" plain @click="removeSkill(sk)">删除</el-button>
        </div>
      </div>
    </div>

    <!-- 创建自定义技能弹窗 -->
    <el-dialog v-model="createVisible" title="创建技能" width="560px">
      <el-form label-position="top">
        <el-form-item label="技能名称">
          <el-input v-model="createForm.name" placeholder="例如：西班牙语文案润色" maxlength="20" />
        </el-form-item>
        <el-form-item label="技能描述">
          <el-input v-model="createForm.description" placeholder="一句话说明这个技能做什么" maxlength="60" />
        </el-form-item>
        <el-form-item label="指令模板（支持 {context} 占位符，运行时注入商品/任务背景）">
          <el-input
            v-model="createForm.prompt_template"
            type="textarea"
            :rows="5"
            placeholder="例如：请将以下商品文案润色为地道的西班牙语电商风格，保留关键词，突出卖点：{context}"
          />
        </el-form-item>
        <el-form-item label="图标">
          <div class="icon-picker">
            <div
              v-for="ic in iconOptions"
              :key="ic"
              class="icon-option"
              :class="{ active: createForm.icon === ic }"
              @click="createForm.icon = ic"
            >
              <el-icon><component :is="ic" /></el-icon>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="doCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 运行自定义技能弹窗 -->
    <el-dialog v-model="runVisible" :title="`运行技能 · ${runSkill?.name || ''}`" width="620px">
      <el-form label-position="top">
        <el-form-item label="商品/任务背景（可选）">
          <el-input
            v-model="runContext"
            type="textarea"
            :rows="3"
            placeholder="例如：夏季法式复古碎花连衣裙，目标市场 Amazon US"
          />
        </el-form-item>
      </el-form>
      <div v-if="runResult" class="run-result">
        <div class="run-result-label">执行结果</div>
        <pre class="run-result-body">{{ runResult }}</pre>
      </div>
      <template #footer>
        <el-button @click="runVisible = false">关闭</el-button>
        <el-button type="primary" :loading="running" @click="doRun">执行</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

defineProps({ disabledStages: { type: Array, default: () => [] } })
defineEmits(['toggle-stage', 'use-workflow'])

const tab = ref('workflows')

// 内置技能默认值（接口失败时兜底）
const FALLBACK_SKILLS = [
  { id: 'extract_attributes', name: '商品智能解析', icon: 'Search', tag: 'core', desc: '多模态识别商品主图，自动抽取类目、关键词、核心属性与卖点。' },
  { id: 'analyze_market', name: '出海市场洞察', icon: 'DataAnalysis', tag: 'core', desc: '旗舰模型 + 知识库检索，输出市场机会、竞争格局与差异化建议。' },
  { id: 'trend_benchmark', name: '爆款对标研究', icon: 'TrendCharts', tag: 'core', desc: 'RAG 召回同类目爆款语料，提炼卖点框架与改写策略。' },
  { id: 'generate_listing', name: '爆款化 Listing', icon: 'EditPen', tag: 'core', desc: '标题/五点/描述/后台词全套英文 Listing，自动植入类目关键词。' },
  { id: 'studio_generation', name: 'AI 商品摄影', icon: 'Camera', tag: 'core', desc: '优先搬运原素材，素材不足时调用文生图补充场景图。' },
  { id: 'video_production', name: '带货视频生产', icon: 'VideoCamera', tag: 'optional', desc: '分镜故事板 + TTS 配音，本地 ffmpeg 自动合成成片。可在技能页关闭。' },
  { id: 'image_localization', name: '图片文字本地化', icon: 'MapLocation', tag: 'optional', desc: '检测图片中文并翻译为目标语言，优先阿里图翻官方接口。可在技能页关闭。' },
  { id: 'adapt_platform', name: '平台合规质检', icon: 'Stamp', tag: 'core', desc: '按目标平台类目规则校验 Listing 合规性。' },
  { id: 'respond', name: '成果汇总打包', icon: 'Box', tag: 'core', desc: 'LangGraph Core 聚合全链路产物，一键打包交付。' },
  { id: 'tryon', name: '虚拟试穿生成', icon: 'User', tag: 'ondemand', desc: '上传服装平铺图 + 模特图，生成真人上身效果图。按需触发。' },
]

const builtinSkills = ref(FALLBACK_SKILLS)
const customSkills = ref([])

async function loadSkills() {
  try {
    const resp = await fetch('/api/skills')
    const data = await resp.json()
    if (data.builtin?.length) builtinSkills.value = data.builtin
    customSkills.value = data.custom || []
  } catch (e) {
    console.warn('技能列表加载失败，使用本地兜底数据', e)
  }
}
onMounted(loadSkills)

const workflows = [
  { id: 'full_launch', name: '全链路上新', icon: 'Promotion', desc: '从商品解析到合规发布的完整上新链路，一个链接走完全流程', skillCount: 9 },
  { id: 'batch', name: '批量上新', icon: 'Files', desc: 'CSV 多商品批量导入，逐单跑全链路并汇总结果', skillCount: 9 },
  { id: 'market_only', name: '市场洞察', icon: 'DataAnalysis', desc: '只跑商品解析与市场洞察，快速评估选品机会', skillCount: 3 },
]

// ---------- 创建自定义技能 ----------
const createVisible = ref(false)
const creating = ref(false)
const iconOptions = ['MagicStick', 'EditPen', 'ChatLineSquare', 'DataAnalysis', 'Document', 'PriceTag', 'Histogram', 'ShoppingCart']
const createForm = reactive({ name: '', description: '', prompt_template: '', icon: 'MagicStick' })

function openCreate() {
  Object.assign(createForm, { name: '', description: '', prompt_template: '', icon: 'MagicStick' })
  createVisible.value = true
}

async function doCreate() {
  if (!createForm.name.trim() || !createForm.prompt_template.trim()) {
    ElMessage.warning('请填写技能名称和指令模板')
    return
  }
  creating.value = true
  try {
    const resp = await fetch('/api/skills', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(createForm),
    })
    if (!resp.ok) throw new Error(await resp.text())
    ElMessage.success('技能已创建，可在「我创建的」中运行')
    createVisible.value = false
    loadSkills()
  } catch (e) {
    ElMessage.error('创建失败：' + e.message)
  } finally {
    creating.value = false
  }
}

async function removeSkill(sk) {
  await ElMessageBox.confirm(`确认删除技能「${sk.name}」？`, '删除技能', { type: 'warning' })
  await fetch(`/api/skills/${sk.id}`, { method: 'DELETE' })
  ElMessage.success('已删除')
  loadSkills()
}

// ---------- 运行自定义技能 ----------
const runVisible = ref(false)
const running = ref(false)
const runSkill = ref(null)
const runContext = ref('')
const runResult = ref('')

function openRun(sk) {
  runSkill.value = sk
  runContext.value = ''
  runResult.value = ''
  runVisible.value = true
}

async function doRun() {
  running.value = true
  runResult.value = ''
  try {
    const resp = await fetch(`/api/skills/${runSkill.value.id}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ context: runContext.value }),
    })
    const data = await resp.json()
    if (!resp.ok) throw new Error(data.detail || '执行失败')
    runResult.value = data.result
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.hub-page {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px 28px;
}
.hub-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 22px 26px;
  background: linear-gradient(120deg, #16204a 0%, #1d2b6b 55%, #3b2b7a 100%);
  border: 1px solid #2b3a6e;
  border-radius: 14px;
  margin-bottom: 20px;
  color: #e2e8f0;
}
.hub-banner-title { font-size: 20px; font-weight: 700; margin-bottom: 8px; }
.hub-banner-desc { font-size: 13px; line-height: 1.6; color: #a5b4fc; max-width: 560px; }
.hub-banner-art { font-size: 56px; color: rgba(165, 180, 252, 0.5); }
.hub-tabs-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.hub-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 14px;
}
.hub-empty { grid-column: 1 / -1; }
.hub-card {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 16px;
  background: var(--gl-panel);
  border: 1px solid var(--gl-border);
  border-radius: 12px;
  transition: border-color 0.15s;
}
.hub-card:hover { border-color: var(--gl-hover-border); }
.hub-icon {
  width: 40px; height: 40px; border-radius: 10px;
  background: var(--gl-active); color: var(--gl-blue);
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; flex-shrink: 0;
}
.hub-icon-custom { background: rgba(251, 191, 36, 0.15); color: #f59e0b; }
.hub-card-main { flex: 1; min-width: 0; }
.hub-card-title {
  font-size: 14px; font-weight: 600; color: var(--gl-text-hi);
  display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
}
.hub-card-desc { font-size: 12px; line-height: 1.6; color: var(--gl-sub); }
.hub-card-meta { font-size: 11px; color: var(--gl-faint); margin-top: 6px; }
.hub-card-action {
  display: flex; align-items: center; gap: 8px; flex-shrink: 0;
}
.icon-picker { display: flex; gap: 8px; flex-wrap: wrap; }
.icon-option {
  width: 36px; height: 36px; border-radius: 8px;
  border: 1px solid var(--gl-border-2);
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; color: var(--gl-sub); cursor: pointer;
}
.icon-option.active { border-color: var(--gl-blue); color: var(--gl-blue); background: rgba(37, 99, 235, 0.08); }
.run-result { margin-top: 4px; }
.run-result-label { font-size: 12px; font-weight: 600; color: var(--gl-text-hi); margin-bottom: 6px; }
.run-result-body {
  background: var(--gl-panel-deep);
  border: 1px solid var(--gl-border);
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--gl-text);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
  font-family: inherit;
}
</style>
