<template>
  <div class="app-layout">
    <AppSidebar :active="activeView" @navigate="switchView" />

    <div class="main-area">
    <!-- 工作台视图（v-show 保留运行状态） -->
    <div class="view-workbench" v-show="activeView === 'workbench'">
    <!-- 顶部导航栏 -->
    <header class="navbar">
      <div class="brand">
        <div class="logo-icon"><el-icon><Promotion /></el-icon></div>
        <div class="brand-text">
          <span class="brand-title">GloLaunch AI</span>
          <span class="brand-subtitle">AI 全链路跨境智能上新引擎 (LangGraph Core)</span>
        </div>
      </div>
      <div class="nav-actions">
        <el-tag type="success" effect="plain" class="token-plan-tag">
          <el-icon><Check /></el-icon> 专属 Token Plan 连接正常
        </el-tag>
        <el-button plain size="small" @click="openBatchDialog">
          <el-icon><Files /></el-icon> 批量上新 (CSV)
        </el-button>
        <el-button plain size="small" @click="showGraph = !showGraph">
          <el-icon><component :is="showGraph ? 'Fold' : 'Expand'" /></el-icon> {{ showGraph ? '收起拓扑' : '展开拓扑' }}
        </el-button>
        <el-button plain size="small" @click="openVersionDrawer">
          <el-icon><Switch /></el-icon> 版本对比
        </el-button>
        <el-button plain size="small" @click="switchView('tasks')">
          <el-icon><Clock /></el-icon> 任务历史
        </el-button>
        <el-button type="primary" plain size="small" @click="resetAll">
          <el-icon><RefreshRight /></el-icon> 新建上新任务
        </el-button>
      </div>
    </header>

    <!-- 主操作区 -->
    <main class="main-content">
      <!-- 顶部 LangGraph 决策图执行状态（可折叠以获得单屏空间） -->
      <section class="graph-section" v-show="showGraph">
        <AgentGraph 
          :running-node="runningNode" 
          :completed-nodes="completedNodes" 
          :planned-nodes="plannedNodes" 
          :stages="plannedStages" 
          :intent="form.intent"
          :trace-logs="traceLogs"
          :is-running="isRunning"
          :eta-seconds="etaSeconds"
          :node-durations="nodeDurations"
        />
      </section>

      <!-- 双栏布局：左侧交互与配置，右侧全链路成果看板 -->
      <div class="workspace-grid">
        <!-- 左侧：输入与控制面板 -->
        <div class="left-panel">
          <el-card shadow="never" class="control-card">
            <template #header>
              <div class="card-header">
                <span class="card-title"><el-icon><Aim /></el-icon> 上新指令与商品输入</span>
                <el-dropdown @command="handlePresetSelect">
                  <el-button type="text" size="small">
                    选择演示预设 <el-icon><ArrowDown /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="french_dress">法式复古方领碎花长裙 (Amazon US)</el-dropdown-item>
                      <el-dropdown-item command="linen_shirt">极简透气亚麻休闲衬衫 (Shopee)</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>

            <el-form label-position="top">
              <el-form-item label="上新模式">
                <el-radio-group v-model="form.intent" size="small">
                  <el-radio-button value="full_launch">全链路上新</el-radio-button>
                  <el-radio-button value="market_only">仅市场洞察</el-radio-button>
                  <el-radio-button value="listing_only">仅 Listing</el-radio-button>
                </el-radio-group>
              </el-form-item>

              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="目标平台">
                    <el-select v-model="form.target_platform" placeholder="选择平台">
                      <el-option label="Amazon (美区/欧区)" value="Amazon" />
                      <el-option label="Shopee (东南亚)" value="Shopee" />
                      <el-option label="TikTok Shop" value="TikTok" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="目标站点/国家">
                    <el-select v-model="form.target_market" placeholder="选择站点">
                      <el-option label="US (美国站)" value="US" />
                      <el-option label="Southeast Asia (东南亚)" value="Southeast Asia" />
                      <el-option label="EU (欧洲站)" value="EU" />
                    </el-select>
                  </el-form-item>
                </el-col>
              </el-row>

              <el-form-item label="商品主图 URL / 拍摄图">
                <el-input v-model="form.product_image_url" placeholder="输入图片链接，或上传本地图片 / 导入 1688">
                  <template #append>
                    <el-button @click="showImagePreview = true">预览</el-button>
                  </template>
                </el-input>
                <div class="image-action-row">
                  <el-upload
                    :show-file-list="false"
                    accept=".jpg,.jpeg,.png,.webp"
                    :http-request="handleUpload"
                  >
                    <el-button size="small" plain>
                      <el-icon><Upload /></el-icon> 上传本地商品图
                    </el-button>
                  </el-upload>
                  <el-button size="small" type="warning" plain @click="importDialogVisible = true">
                    <el-icon><Link /></el-icon> 导入 1688 商品
                  </el-button>
                </div>
              </el-form-item>

              <!-- 图片预览小图 -->
              <div class="image-thumb-box" v-if="form.product_image_url">
                <img :src="form.product_image_url" alt="商品预览" class="thumb-img" />
                <div class="thumb-tag">多模态识别源图</div>
              </div>

              <el-form-item label="Agent 自然语言指令">
                <el-input 
                  v-model="form.message" 
                  type="textarea" 
                  :rows="2" 
                  placeholder="例如：帮我把这款夏季法式复古碎花连衣裙做全链路上新，挖掘美区高转化词并生成专业 Listing 与试穿拍摄。"
                />
              </el-form-item>

              <el-button 
                type="primary" 
                size="large" 
                class="launch-btn" 
                :loading="isRunning"
                @click="startLaunch"
              >
                <el-icon><CaretRight /></el-icon>
                {{ isRunning ? 'LangGraph Agent 正在全链路生成中...' : '一键启动 AI 全链路上新' }}
              </el-button>

              <!-- 失败断点续跑提示 -->
              <div class="error-resume-box" v-if="lastError && !isRunning">
                <div class="error-text">上次执行异常：{{ lastError }}</div>
                <el-button type="warning" size="small" @click="resumeRun">
                  <el-icon><RefreshRight /></el-icon> 从断点继续执行（不重复已完成节点）
                </el-button>
              </div>
            </el-form>
          </el-card>
        </div>

        <!-- 右侧：出海全链路生成结果面板 (Tab 切换) -->
        <div class="right-panel">
          <el-card shadow="never" class="results-card">
            <el-tabs v-model="activeTab" class="custom-tabs">
              <!-- Tab 1: Listing 与文案 -->
              <el-tab-pane label="平台 Listing" name="listing">
                <div v-if="!resultData.listing_content" class="empty-state">
                  <el-empty description="启动 Agent 后此处将展示根据市场洞察生成的专业出海 Listing" />
                </div>
                <div v-else class="listing-view">
                  <div class="result-block">
                    <div class="block-label">
                      <span>Amazon 英文主标题 (Title)</span>
                      <el-tag size="small" type="success">字符数: {{ resultData.listing_content.title_char_count || resultData.listing_content.title.length }}</el-tag>
                    </div>
                    <div class="title-content">{{ resultData.listing_content.title }}</div>
                  </div>

                  <div class="result-block">
                    <div class="block-label">五点描述 (Bullet Points)</div>
                    <div class="bullet-list">
                      <div 
                        v-for="(bullet, index) in resultData.listing_content.bullet_points" 
                        :key="index" 
                        class="bullet-item"
                      >
                        <span class="bullet-num">{{ index + 1 }}</span>
                        <span class="bullet-text">{{ bullet }}</span>
                      </div>
                    </div>
                  </div>

                  <div class="result-block">
                    <div class="block-label">搜索关键词 (Search Terms)</div>
                    <div class="search-terms-box">{{ resultData.listing_content.search_terms }}</div>
                  </div>

                  <div class="result-block" v-if="resultData.listing_content.product_description">
                    <div class="block-label">商品长描述 (Product Description)</div>
                    <div class="desc-box">{{ resultData.listing_content.product_description }}</div>
                  </div>
                </div>
              </el-tab-pane>

              <!-- Tab 2: 市场洞察与选品评估 -->
              <el-tab-pane label="市场洞察报告" name="market">
                <div v-if="!resultData.market_insights" class="empty-state">
                  <el-empty description="Qwen3.8-Max 深度推理的市场趋势与选品报告将在此呈现" />
                </div>
                <div v-else class="market-view">
                  <el-row :gutter="12" class="metric-row">
                    <el-col :span="8">
                      <div class="metric-card">
                        <div class="metric-label">建议定价区间</div>
                        <div class="metric-val highlight">{{ resultData.market_insights.recommended_price_range }}</div>
                      </div>
                    </el-col>
                    <el-col :span="8">
                      <div class="metric-card">
                        <div class="metric-label">预估毛利空间</div>
                        <div class="metric-val">{{ resultData.market_insights.profit_margin_est }}</div>
                      </div>
                    </el-col>
                    <el-col :span="8">
                      <div class="metric-card">
                        <div class="metric-label">选品置信指数</div>
                        <div class="metric-val score">{{ resultData.opportunity_score?.total_score || resultData.market_insights?.launch_confidence_score || '--' }} / 100</div>
                      </div>
                    </el-col>
                  </el-row>

                  <div class="result-block">
                    <div class="block-label">目标市场趋势与客群画像</div>
                    <p class="text-p">{{ resultData.market_insights.market_overview }}</p>
                    <p class="text-p"><strong>目标客群：</strong>{{ resultData.market_insights.target_audience }}</p>
                  </div>

                  <div class="result-block">
                    <div class="block-label">海外买家核心痛点与差评预防</div>
                    <ul class="tag-list">
                      <li v-for="(pain, i) in resultData.market_insights.buyer_pain_points" :key="i" class="pain-tag">
                        {{ pain }}
                      </li>
                    </ul>
                  </div>

                  <div class="result-block">
                    <div class="block-label">挖掘的高转化出海 SEO 词</div>
                    <div class="kw-tags">
                      <el-tag 
                        v-for="(kw, i) in resultData.market_insights.high_converting_keywords" 
                        :key="i" 
                        class="kw-tag" 
                        type="primary"
                        effect="light"
                      >
                        {{ kw }}
                      </el-tag>
                    </div>
                  </div>
                </div>
              </el-tab-pane>

              <!-- Tab 2.5: 爆款对标策略 -->
              <el-tab-pane label="爆款对标" name="benchmark">
                <div v-if="!resultData.trend_benchmark" class="empty-state">
                  <el-empty description="同类爆款的标题公式与流量词埋词策略将在此呈现（Listing 据此改写而非直译）" />
                </div>
                <div v-else class="benchmark-view">
                  <div class="result-block">
                    <div class="block-label">对标爆款画像</div>
                    <div v-for="(bp, i) in resultData.trend_benchmark.benchmark_products" :key="i" class="benchmark-card">
                      <div class="bp-name">{{ bp.name }}</div>
                      <div class="bp-row"><strong>爆款原因：</strong>{{ bp.why_hit }}</div>
                      <div class="bp-row"><strong>标题结构：</strong><code class="bp-code">{{ bp.title_pattern }}</code></div>
                    </div>
                  </div>
                  <div class="result-block">
                    <div class="block-label">为该商品定制的标题公式</div>
                    <div class="formula-box">{{ resultData.trend_benchmark.title_formula }}</div>
                  </div>
                  <div class="result-block">
                    <div class="block-label">流量词埋词策略</div>
                    <ul class="strategy-list">
                      <li v-for="(s, i) in resultData.trend_benchmark.traffic_word_strategy" :key="i">{{ s }}</li>
                    </ul>
                  </div>
                  <div class="result-block" v-if="(resultData.trend_benchmark.conversion_hooks || []).length">
                    <div class="block-label">五点转化钩子</div>
                    <ul class="strategy-list">
                      <li v-for="(h, i) in resultData.trend_benchmark.conversion_hooks" :key="i">{{ h }}</li>
                    </ul>
                  </div>
                  <div class="result-block" v-if="resultData.trend_benchmark.localization_notes">
                    <div class="block-label">跨文化改写要点（拒绝直译）</div>
                    <p class="text-p">{{ resultData.trend_benchmark.localization_notes }}</p>
                  </div>
                </div>
              </el-tab-pane>

              <!-- Tab 3: AI 拍摄与虚拟试穿 -->
              <el-tab-pane label="AI 拍摄素材工坊" name="studio">
                <div v-if="!resultData.studio_assets" class="empty-state">
                  <el-empty description="AI 场景图与本地化详情图将在此呈现（搬运商品可直接使用原素材，AI 生成按需触发）" />
                </div>
                <div v-else class="studio-view">
                  <!-- 详情页图片文字本地化 -->
                  <div class="studio-section" v-if="resultData.localized_images">
                    <div class="block-label">
                      详情页图片文字本地化（→ {{ (resultData.localized_images.target_language || 'en').toUpperCase() }}）
                      <el-tag size="small" :type="resultData.localized_images.engine === 'aliyun_image_translation' ? 'success' : 'warning'">
                        {{ resultData.localized_images.engine === 'aliyun_image_translation' ? '阿里云电商图翻' : 'Qwen-VL 识别翻译' }}
                      </el-tag>
                    </div>
                    <div v-for="(item, idx) in resultData.localized_images.items" :key="idx" class="localize-pair">
                      <div class="localize-col">
                        <img :src="item.source_image" class="localize-img" alt="中文原图" />
                        <div class="localize-cap">中文原图</div>
                      </div>
                      <div class="localize-arrow">→</div>
                      <div class="localize-col">
                        <img v-if="item.localized_image" :src="item.localized_image" class="localize-img" alt="译后图" />
                        <div v-else class="localize-fallback">
                          <div v-for="(t, ti) in (item.texts || [])" :key="ti" class="text-pair">
                            <span class="origin-text">{{ t.original }}</span>
                            <span class="trans-text">{{ t.translated }}</span>
                            <span class="pos-tag">{{ t.position }}</span>
                          </div>
                          <div v-if="!(item.texts || []).length" class="no-text-tip">未识别到中文文案，无需本地化</div>
                        </div>
                        <div class="localize-cap">{{ item.localized_image ? '译后成品图' : '译文排版方案' }}</div>
                      </div>
                    </div>
                  </div>

                  <div class="studio-section" v-if="isApparel">
                    <div class="block-label">
                      虚拟试穿（服装增值服务）
                      <el-tag size="small" type="info">按需生成 · 不在主流水线内</el-tag>
                    </div>
                    <div class="tryon-banner" v-if="tryonResult">
                      <img :src="tryonResult.tryon_image_url" alt="虚拟试穿" class="tryon-img" />
                      <div class="tryon-details">
                        <div class="tryon-badge">模特特征：{{ tryonResult.model_type }}</div>
                        <div class="tryon-fit">贴合评估：{{ tryonResult.garment_fit_status }}</div>
                        <div class="tryon-drape">质感保持：{{ tryonResult.fabric_drape_retention }}</div>
                        <div class="tryon-engine">合成引擎：{{ tryonResult.engine }}</div>
                      </div>
                    </div>
                    <div class="tryon-actions" v-else>
                      <el-button type="primary" :loading="tryonLoading" @click="generateTryon">
                        {{ tryonLoading ? 'AI 模特合成中…' : '生成虚拟试穿图' }}
                      </el-button>
                      <span class="tryon-tip">搬运商品已有模特图可跳过；缺素材时按需生成，不占用上新主链路时间</span>
                    </div>
                  </div>

                  <div class="studio-section" v-if="resultData.studio_assets.material_mode === 'source' && !(resultData.studio_assets.lifestyle_scenes || []).length">
                    <div class="source-banner">
                      <div>
                        搬运原素材沿用：主图直接复用原图，未触发 AI 生图（节省额度、加速上新）
                        <div class="source-tip">若缺海外生活方式场景图，可按需 AI 生成补充</div>
                      </div>
                      <el-button type="primary" size="small" :loading="scenesLoading" @click="generateScenes">
                        {{ scenesLoading ? 'AI 生成中…' : '补充 AI 场景图' }}
                      </el-button>
                    </div>
                  </div>

                  <div class="studio-section" v-if="(resultData.studio_assets.lifestyle_scenes || []).length">
                    <div class="block-label">
                      多场景生活方式展示图 (Lifestyle Scenes)
                      <el-tag size="small" type="success" v-if="resultData.studio_assets.material_mode === 'source_plus'">按需补充</el-tag>
                    </div>
                    <div class="scene-gallery">
                      <div 
                        v-for="(scene, idx) in resultData.studio_assets.lifestyle_scenes" 
                        :key="idx" 
                        class="scene-card"
                      >
                        <img :src="scene.image_url" :alt="scene.scene_name" class="scene-img" />
                        <div class="scene-caption">{{ scene.scene_name }}</div>
                      </div>
                    </div>
                  </div>
                </div>
              </el-tab-pane>

              <!-- Tab 3.5: 商品展示带货视频 -->
              <el-tab-pane label="带货视频" name="video">
                <div v-if="!resultData.video_package" class="empty-state">
                  <el-empty description="商品展示带货视频：分镜脚本、TTS 配音与成片将在此呈现" />
                </div>
                <div v-else class="video-view">
                  <div class="result-block">
                    <div class="block-label">
                      <span>视频总览</span>
                      <el-tag size="small" :type="videoModeTagType">{{ videoModeLabel }}</el-tag>
                    </div>
                    <div class="video-hook">{{ resultData.video_package.title_hook }}</div>
                    <p class="text-p"><strong>BGM 风格：</strong>{{ resultData.video_package.bgm_style }}</p>
                    <p class="text-p"><strong>时长：</strong>约 {{ resultData.video_package.duration_seconds }} 秒 · 投放平台 {{ resultData.video_package.platform }}</p>
                    <video v-if="resultData.video_package.video_url" :src="resultData.video_package.video_url" controls class="video-player"></video>
                    <div v-if="resultData.video_package.audio_url" class="audio-row">
                      <span class="audio-label">TTS 配音（目标市场语言）</span>
                      <audio :src="resultData.video_package.audio_url" controls class="audio-player"></audio>
                    </div>
                    <el-alert v-if="resultData.video_package.fallback_note" :title="resultData.video_package.fallback_note" type="warning" :closable="false" style="margin-top: 8px;" />
                  </div>
                  <div class="result-block">
                    <div class="block-label">分镜脚本（{{ resultData.video_package.storyboard.length }} 镜）</div>
                    <div v-for="(shot, i) in resultData.video_package.storyboard" :key="i" class="shot-card">
                      <div class="shot-num">{{ i + 1 }}</div>
                      <div class="shot-body">
                        <div class="shot-scene">{{ shot.scene }} <span class="shot-cam">{{ shot.camera }}</span></div>
                        <div class="shot-voiceover">{{ shot.voiceover }}</div>
                      </div>
                      <div class="shot-duration">{{ shot.duration }}s</div>
                    </div>
                  </div>
                </div>
              </el-tab-pane>

              <!-- Tab 4: 属性识别与发布包 -->
              <el-tab-pane label="属性与发布包" name="package">
                <div v-if="!resultData.platform_package" class="empty-state">
                  <el-empty description="经平台规则校验的标准化发布包数据" />
                </div>
                <div v-else class="package-view">
                  <div class="result-block">
                    <div class="block-label">Qwen3.7-Plus 视觉识别结构化属性</div>
                    <div class="attr-grid" v-if="resultData.product_attributes">
                      <div class="attr-item"><strong>品类：</strong>{{ resultData.product_attributes.category }}</div>
                      <div class="attr-item"><strong>主色调：</strong>{{ resultData.product_attributes.main_color }}</div>
                      <div class="attr-item"><strong>面料材质：</strong>{{ (resultData.product_attributes.materials || []).join(', ') }}</div>
                      <div class="attr-item"><strong>版型设计：</strong>{{ (resultData.product_attributes.design_features || []).join(', ') }}</div>
                      <div class="attr-item"><strong>适用季节：</strong>{{ resultData.product_attributes.season }}</div>
                    </div>
                  </div>

                  <div class="result-block">
                    <div class="block-label">跨境平台合规质检清单</div>
                    <div class="rules-list">
                      <div 
                        v-for="(r, idx) in resultData.platform_package.rule_check_results" 
                        :key="idx" 
                        class="rule-row"
                      >
                        <el-icon color="#22c55e"><CircleCheckFilled /></el-icon>
                        <span class="rule-name">{{ r.rule_name }}:</span>
                        <span class="rule-desc">{{ r.details }}</span>
                      </div>
                    </div>
                  </div>

                  <div class="publish-action-box">
                    <div class="sku-info">
                      <strong>生成 SKU：</strong><code>{{ resultData.platform_package.export_package.sku }}</code>
                    </div>
                    <div class="publish-btn-row">
                      <el-button type="warning" size="large" :loading="publishLoading" @click="doPublish">
                        <el-icon><Promotion /></el-icon> 一键发布至平台 (OAuth 直连)
                      </el-button>
                      <el-button type="success" size="large" @click="exportPackage">
                        <el-icon><Download /></el-icon> 导出标准化发布包 (CSV + 素材)
                      </el-button>
                    </div>
                  </div>
                </div>
              </el-tab-pane>

              <!-- Tab 5: 选品决策评分 (V2) -->
              <el-tab-pane name="opportunity">
                <template #label>
                  <span>选品决策评分 <el-tag v-if="resultData.opportunity_score" size="small" :type="resultData.opportunity_score.recommendation === '强烈推荐' ? 'success' : resultData.opportunity_score.recommendation === '谨慎观望' ? 'warning' : 'info'">{{ resultData.opportunity_score.total_score?.toFixed(1) }}</el-tag></span>
                </template>
                <div v-if="!resultData.opportunity_score" class="empty-state">
                  <el-empty description="Agent 完成市场洞察后将自动生成六维选品评分" />
                </div>
                <div v-else class="opportunity-view">
                  <div class="score-header">
                    <div class="total-score-ring">
                      <svg viewBox="0 0 120 120" class="score-ring-svg">
                        <circle cx="60" cy="60" r="52" fill="none" stroke="var(--el-border-color-lighter)" stroke-width="8" />
                        <circle cx="60" cy="60" r="52" fill="none"
                          :stroke="resultData.opportunity_score.total_score >= 70 ? '#22c55e' : resultData.opportunity_score.total_score >= 50 ? '#f59e0b' : '#ef4444'"
                          stroke-width="8" stroke-linecap="round"
                          :stroke-dasharray="`${(resultData.opportunity_score.total_score / 100) * 327} 327`"
                          transform="rotate(-90 60 60)" />
                      </svg>
                      <div class="score-ring-text">
                        <span class="score-number">{{ resultData.opportunity_score.total_score?.toFixed(1) }}</span>
                        <span class="score-label">综合评分</span>
                      </div>
                    </div>
                    <div class="score-summary">
                      <el-tag :type="resultData.opportunity_score.recommendation === '强烈推荐' ? 'success' : resultData.opportunity_score.recommendation === '谨慎观望' ? 'warning' : 'info'" size="large" effect="dark">
                        {{ resultData.opportunity_score.recommendation }}
                      </el-tag>
                      <p class="recommendation-text">{{ resultData.opportunity_score.summary }}</p>
                      <div class="platform-recs" v-if="resultData.opportunity_score.platform_recommendations?.length">
                        <span class="rec-label">推荐平台：</span>
                        <el-tag v-for="pr in resultData.opportunity_score.platform_recommendations" :key="pr.platform" size="small" effect="plain" class="rec-tag">
                          {{ pr.platform }} ({{ pr.score?.toFixed(0) }})
                        </el-tag>
                      </div>
                    </div>
                  </div>
                  <div class="dimension-bars">
                    <div v-for="dim in resultData.opportunity_score.dimensions" :key="dim.name" class="dim-row">
                      <span class="dim-name">{{ dim.name }}</span>
                      <el-progress :percentage="dim.score" :color="dim.score >= 70 ? '#22c55e' : dim.score >= 50 ? '#f59e0b' : '#ef4444'" :stroke-width="14" :show-text="true" />
                      <span class="dim-weight">权重 {{ (dim.weight * 100).toFixed(0) }}%</span>
                    </div>
                  </div>
                  <div class="supply-market-fit" v-if="resultData.opportunity_score.supply_market_fit">
                    <div class="block-label">Supply-Market Fit 分析</div>
                    <el-alert :title="resultData.opportunity_score.supply_market_fit.verdict" :type="resultData.opportunity_score.supply_market_fit.fit_score >= 70 ? 'success' : 'warning'" :description="resultData.opportunity_score.supply_market_fit.explanation" show-icon :closable="false" />
                  </div>
                </div>
              </el-tab-pane>

              <!-- Tab 6: 素材缺口分析 (V2) -->
              <el-tab-pane name="asset_gap">
                <template #label>
                  <span>素材缺口 <el-tag v-if="resultData.asset_gap" size="small" :type="resultData.asset_gap.missing_count === 0 ? 'success' : 'warning'">{{ resultData.asset_gap.missing_count }} 项待补</el-tag></span>
                </template>
                <div v-if="!resultData.asset_gap && !resultData.asset_inventory" class="empty-state">
                  <el-empty description="Agent 完成素材盘点后将展示现有素材与缺口分析" />
                </div>
                <div v-else class="asset-gap-view">
                  <div class="inventory-summary" v-if="resultData.asset_inventory">
                    <el-row :gutter="16">
                      <el-col :span="8">
                        <el-statistic title="已有素材" :value="resultData.asset_inventory.total_count || 0">
                          <template #suffix><span style="font-size:13px;color:var(--el-text-color-secondary)"> 项</span></template>
                        </el-statistic>
                      </el-col>
                      <el-col :span="8">
                        <el-statistic title="覆盖类型" :value="resultData.asset_inventory.covered_types?.length || 0">
                          <template #suffix><span style="font-size:13px;color:var(--el-text-color-secondary)"> / {{ resultData.asset_inventory.required_types?.length || 0 }} 类</span></template>
                        </el-statistic>
                      </el-col>
                      <el-col :span="8">
                        <el-statistic title="素材来源" :value="resultData.asset_inventory.ai_generated_count || 0">
                          <template #suffix><span style="font-size:13px;color:var(--el-text-color-secondary)"> AI 生成</span></template>
                        </el-statistic>
                      </el-col>
                    </el-row>
                  </div>

                  <div class="gap-list" v-if="resultData.asset_gap?.items?.length">
                    <div class="block-label">缺口清单 (仅生成缺失项，搬运优先)</div>
                    <div v-for="(gap, idx) in resultData.asset_gap.items" :key="idx" class="gap-item">
                      <div class="gap-item-header">
                        <el-tag :type="gap.priority === 'high' ? 'danger' : gap.priority === 'medium' ? 'warning' : 'info'" size="small">{{ gap.priority === 'high' ? '必需' : gap.priority === 'medium' ? '建议' : '可选' }}</el-tag>
                        <span class="gap-asset-type">{{ gap.asset_type }}</span>
                        <span class="gap-status" :class="gap.status">{{ gap.status === 'missing' ? '缺失' : gap.status === 'generated' ? '已 AI 补全' : '已搬运' }}</span>
                      </div>
                      <p class="gap-reason" v-if="gap.reason">{{ gap.reason }}</p>
                      <div class="gap-cost" v-if="gap.estimated_cost">
                        <el-tag size="small" type="info" effect="plain">预估成本: {{ gap.estimated_cost }}</el-tag>
                      </div>
                    </div>
                  </div>
                  <el-empty v-else-if="resultData.asset_gap" description="所有必需素材已齐备，无缺口" :image-size="60" />
                </div>
              </el-tab-pane>

              <!-- Tab 7: Listing 质量评分 (V2) -->
              <el-tab-pane name="listing_health">
                <template #label>
                  <span>Listing 质量 <el-tag v-if="resultData.listing_health" size="small" :type="resultData.listing_health.grade === 'A' ? 'success' : resultData.listing_health.grade === 'B' ? '' : 'warning'">{{ resultData.listing_health.grade }} 级</el-tag></span>
                </template>
                <div v-if="!resultData.listing_health" class="empty-state">
                  <el-empty description="Listing 撰写完成后将自动进行八维质量评估" />
                </div>
                <div v-else class="health-view">
                  <div class="health-header">
                    <div class="grade-badge" :class="'grade-' + resultData.listing_health.grade">
                      {{ resultData.listing_health.grade }}
                    </div>
                    <div class="health-meta">
                      <span class="health-total">综合评分 <strong>{{ resultData.listing_health.total_score?.toFixed(1) }}</strong> / 100</span>
                      <span class="health-grade-text">{{ resultData.listing_health.grade_description }}</span>
                    </div>
                  </div>
                  <div class="health-dim-grid">
                    <div v-for="dim in resultData.listing_health.dimensions" :key="dim.name" class="health-dim-card">
                      <div class="dim-card-header">
                        <span class="dim-card-name">{{ dim.name }}</span>
                        <span class="dim-card-score" :style="{ color: dim.score >= 80 ? '#22c55e' : dim.score >= 60 ? '#f59e0b' : '#ef4444' }">{{ dim.score?.toFixed(0) }}</span>
                      </div>
                      <el-progress :percentage="dim.score" :show-text="false" :color="dim.score >= 80 ? '#22c55e' : dim.score >= 60 ? '#f59e0b' : '#ef4444'" :stroke-width="6" />
                      <p class="dim-card-feedback" v-if="dim.feedback">{{ dim.feedback }}</p>
                    </div>
                  </div>
                  <div class="improvement-priorities" v-if="resultData.listing_health.improvement_priorities?.length">
                    <div class="block-label">改进建议</div>
                    <el-timeline>
                      <el-timeline-item v-for="(imp, idx) in resultData.listing_health.improvement_priorities" :key="idx" :type="idx === 0 ? 'danger' : idx === 1 ? 'warning' : 'info'" :timestamp="'优先级 #' + (idx + 1)">
                        {{ imp }}
                      </el-timeline-item>
                    </el-timeline>
                  </div>
                </div>
              </el-tab-pane>

              <!-- Tab 8: 发布审核 (V2 Human-in-the-loop) -->
              <el-tab-pane name="publish_review">
                <template #label>
                  <span>发布审核 <el-tag v-if="resultData.publish_package" size="small" :type="resultData.publish_package.decision === 'approved' ? 'success' : resultData.publish_package.decision === 'rejected' ? 'danger' : 'warning'">{{ resultData.publish_package.decision === 'approved' ? '已通过' : resultData.publish_package.decision === 'rejected' ? '已驳回' : '待审核' }}</el-tag></span>
                </template>
                <div v-if="!resultData.publish_package" class="empty-state">
                  <el-empty description="合规质检完成后将生成发布审核包，等待人工确认" />
                </div>
                <div v-else class="publish-review-view">
                  <div class="review-header">
                    <el-descriptions :column="2" border size="small">
                      <el-descriptions-item label="目标平台">{{ resultData.publish_package.platform }}</el-descriptions-item>
                      <el-descriptions-item label="SKU">{{ resultData.publish_package.sku }}</el-descriptions-item>
                      <el-descriptions-item label="审核状态">
                        <el-tag :type="resultData.publish_package.decision === 'approved' ? 'success' : resultData.publish_package.decision === 'rejected' ? 'danger' : 'warning'" size="small">
                          {{ resultData.publish_package.decision === 'approved' ? '审核通过' : resultData.publish_package.decision === 'rejected' ? '已驳回' : '待人工审核' }}
                        </el-tag>
                      </el-descriptions-item>
                      <el-descriptions-item label="Listing 质量">
                        <el-tag :type="resultData.publish_package.listing_health_grade === 'A' ? 'success' : resultData.publish_package.listing_health_grade === 'B' ? '' : 'warning'" size="small">
                          {{ resultData.publish_package.listing_health_grade }} 级
                        </el-tag>
                      </el-descriptions-item>
                    </el-descriptions>
                  </div>

                  <div class="review-checklist">
                    <div class="block-label">合规质检清单</div>
                    <div v-for="(item, idx) in resultData.publish_package.check_items" :key="idx" class="check-item">
                      <el-icon :color="item.passed ? '#22c55e' : '#ef4444'">
                        <component :is="item.passed ? 'CircleCheckFilled' : 'CircleCloseFilled'" />
                      </el-icon>
                      <span class="check-name">{{ item.name }}</span>
                      <span class="check-detail">{{ item.detail }}</span>
                    </div>
                  </div>

                  <div class="review-actions" v-if="resultData.publish_package.decision === 'pending'">
                    <el-divider />
                    <div class="review-btn-row">
                      <el-button type="success" size="large" @click="handlePublishDecision('approved')">
                        <el-icon><CircleCheckFilled /></el-icon> 审核通过，执行发布
                      </el-button>
                      <el-button type="danger" size="large" @click="handlePublishDecision('rejected')">
                        <el-icon><CircleCloseFilled /></el-icon> 驳回，需修改后重新提交
                      </el-button>
                    </div>
                  </div>
                  <div class="review-result" v-else>
                    <el-divider />
                    <el-alert
                      :title="resultData.publish_package.decision === 'approved' ? '审核已通过，发布包已就绪' : '审核已驳回，请根据反馈修改后重新生成'"
                      :type="resultData.publish_package.decision === 'approved' ? 'success' : 'error'"
                      :description="resultData.publish_package.review_comment || ''"
                      show-icon :closable="false"
                    />
                  </div>
                </div>
              </el-tab-pane>
            </el-tabs>
          </el-card>
        </div>
      </div>
    </main>
    </div>

    <!-- 工作流和技能 hub -->
    <WorkflowHub
      v-if="activeView === 'hub'"
      :disabled-stages="disabledStages"
      @toggle-stage="toggleStage"
      @use-workflow="useWorkflow"
    />
    <TaskManager v-else-if="activeView === 'tasks'" @view-task="handleViewTask" />
    <Connections v-else-if="activeView === 'connections'" />
    </div>

    <!-- 1688 商品导入弹窗 -->
    <el-dialog v-model="importDialogVisible" title="一键搬运 1688 商品" width="560px">
      <div class="import-box">
        <div class="import-hint">粘贴商品链接即可：自动解析标题/主图/详情图 → 智能推荐平台站点 → 自动跑完全链路上新</div>
        <div class="import-oauth">
          <el-link type="primary" href="/api/import/1688/oauth/start" target="_blank" :underline="false">
            1688 账号授权（开放平台官方 API，更稳定）
          </el-link>
        </div>
        <el-input 
          v-model="importUrl" 
          placeholder="粘贴 1688 商品链接，如 https://detail.1688.com/offer/xxx.html"
          clearable
        />
        <el-button 
          type="primary" 
          :loading="importLoading" 
          style="margin-top: 12px; width: 100%;"
          @click="doImport1688"
        >
          <el-icon><Download /></el-icon> 解析商品
        </el-button>
        <el-alert 
          v-if="importMessage" 
          :title="importMessage" 
          :type="importSuccess ? 'success' : 'warning'" 
          :closable="false" 
          style="margin-top: 12px;"
        />
        <!-- 解析结果预览 -->
        <div class="import-preview" v-if="importedProduct">
          <img v-if="importedProduct.main_image" :src="importedProduct.main_image" class="import-thumb" alt="商品主图" />
          <div class="import-info">
            <div class="import-title">{{ importedProduct.title || '（未解析到标题，可手动补充指令）' }}</div>
            <div class="import-meta">
              <el-tag v-if="importedProduct.source_price" size="small" type="warning">1688 进价 {{ importedProduct.source_price }}</el-tag>
              <el-tag size="small" type="info">素材图 {{ (importedProduct.images || []).length }} 张</el-tag>
              <el-tag size="small" type="success">推荐 {{ importRecommend.platform }} · {{ importRecommend.market }}</el-tag>
            </div>
            <div class="import-actions">
              <el-button type="primary" :disabled="isRunning" @click="importAndLaunch">
                一键搬运并启动全链路上新（{{ importRecommend.platform }} {{ importRecommend.market }}）
              </el-button>
              <el-button size="small" type="info" plain @click="applyImported">先填入表单，我调一下平台/指令</el-button>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- 商品图预览弹窗 -->
    <el-dialog v-model="showImagePreview" title="商品图预览" width="480px">
      <img v-if="form.product_image_url" :src="form.product_image_url" alt="商品图" style="width: 100%; border-radius: 8px;" />
      <el-empty v-else description="未填写商品图链接" />
    </el-dialog>

    <!-- 发布回执弹窗 -->
    <el-dialog v-model="publishResultVisible" title="平台发布回执" width="620px">
      <div v-if="publishResult" class="publish-result">
        <div class="publish-head">
          <el-tag :type="publishResult.mode === 'live' ? 'success' : 'warning'" effect="dark">
            {{ publishResult.mode === 'live' ? '真实上架提交' : '演练模式 (Dry Run)' }}
          </el-tag>
          <span class="publish-id">发布单号：{{ publishResult.publish_id }}</span>
          <el-tag size="small">{{ publishResult.status }}</el-tag>
        </div>
        <div class="publish-timeline">
          <div v-for="(step, i) in (publishResult.report.timeline || [])" :key="i" class="timeline-item">
            <span class="timeline-dot">{{ i + 1 }}</span>
            <div class="timeline-body">
              <div class="timeline-step">{{ step.step }}</div>
              <div class="timeline-detail">{{ step.detail }}</div>
            </div>
          </div>
        </div>
        <el-alert v-if="publishResult.report.note" :title="publishResult.report.note" type="info" :closable="false" style="margin-top: 10px;" />
      </div>
    </el-dialog>

    <!-- 批量上新弹窗 -->
    <el-dialog v-model="batchDialogVisible" title="多商品批量上新 (CSV 导入)" width="720px">
      <div class="batch-box">
        <el-upload
          drag
          accept=".csv"
          :show-file-list="false"
          :http-request="handleBatchCsv"
        >
          <el-icon style="font-size: 34px; color: #38bdf8;"><Files /></el-icon>
          <div>将 CSV 拖到此处，或点击上传</div>
          <template #tip>
            <div class="el-upload__tip">支持列：商品名称 / 图片链接 / 平台 / 市场（中英文表头均可，UTF-8 或 GBK 编码）</div>
          </template>
        </el-upload>

        <!-- 解析预览表 -->
        <div v-if="batchItems.length" class="batch-preview">
          <div class="batch-preview-head">
            <span>已解析 {{ batchItems.length }} 个商品</span>
            <el-radio-group v-model="batchIntent" size="small">
              <el-radio-button value="full_launch">全链路</el-radio-button>
              <el-radio-button value="listing_only">仅 Listing</el-radio-button>
              <el-radio-button value="market_only">仅洞察</el-radio-button>
            </el-radio-group>
            <el-button type="primary" size="small" :loading="batchRunning" @click="runBatch">
              <el-icon><CaretRight /></el-icon> 启动批量流水线
            </el-button>
          </div>
          <div class="batch-list">
            <div v-for="(item, i) in batchItems" :key="i" class="batch-item" :class="batchStatusClass(i)">
              <span class="batch-idx">{{ i + 1 }}</span>
              <div class="batch-item-body">
                <div class="batch-item-name">{{ item.name || item.image_url }}</div>
                <div class="batch-item-meta">
                  <el-tag size="small">{{ item.platform || 'Amazon' }}</el-tag>
                  <el-tag size="small" type="info">{{ item.market || 'US' }}</el-tag>
                </div>
              </div>
              <span class="batch-status">
                <template v-if="batchResults[i] && batchResults[i].status === 'running'"><el-icon class="is-loading"><Loading /></el-icon> 执行中</template>
                <template v-else-if="batchResults[i] && batchResults[i].status === 'success'"><el-icon color="#22c55e"><CircleCheckFilled /></el-icon> {{ batchResults[i].title ? 'Listing 已生成' : '完成' }}</template>
                <template v-else-if="batchResults[i] && batchResults[i].status === 'error'"><el-icon color="#f87171"><CircleClose /></el-icon> 失败</template>
                <template v-else>待执行</template>
              </span>
            </div>
          </div>
          <el-alert v-if="batchSummary" :title="batchSummary" type="success" :closable="false" style="margin-top: 10px;" />
        </div>
      </div>
    </el-dialog>

    <!-- Listing 版本对比抽屉 -->
    <el-drawer v-model="versionDrawerVisible" title="Listing 版本对比" size="640px">
      <div class="version-box">
        <el-alert title="勾选两个版本后点击下方按钮进行对比（同一商品多次上新可观察文案迭代效果）" type="info" :closable="false" style="margin-bottom: 12px;" />
        <div v-if="versionList.length === 0" class="empty-state">
          <el-empty description="暂无版本，完成一次上新后自动存档" />
        </div>
        <div v-else class="version-list">
          <div v-for="v in versionList" :key="v.id" class="version-item" :class="{ selected: versionSelected.includes(v.id) }" @click="toggleVersionSelect(v.id)">
            <div class="version-title">{{ v.title }}</div>
            <div class="task-meta">
              <el-tag size="small" type="warning">V{{ v.id }}</el-tag>
              <el-tag size="small">{{ v.platform }}</el-tag>
              <span class="task-time">{{ formatTime(v.created_at) }}</span>
            </div>
          </div>
        </div>
        <el-button type="primary" style="margin-top: 12px; width: 100%;" :disabled="versionSelected.length !== 2" :loading="compareLoading" @click="doCompare">
          <el-icon><Switch /></el-icon> 对比选中版本（{{ versionSelected.length }}/2）
        </el-button>

        <!-- 对比结果 -->
        <div v-if="compareResult" class="compare-result">
          <div class="compare-summary">
            <el-tag size="small" :type="compareResult.diff_summary.title_changed ? 'warning' : 'info'">
              标题{{ compareResult.diff_summary.title_changed ? '已变更' : '未变' }}（字符数 {{ compareResult.diff_summary.title_length_delta >= 0 ? '+' : '' }}{{ compareResult.diff_summary.title_length_delta }}）
            </el-tag>
            <el-tag size="small" type="info">五点：新增 {{ compareResult.diff_summary.bullets_added }} / 删除 {{ compareResult.diff_summary.bullets_removed }} / 修改 {{ compareResult.diff_summary.bullets_changed }}</el-tag>
            <el-tag size="small" :type="compareResult.diff_summary.search_terms_changed ? 'warning' : 'info'">
              关键词{{ compareResult.diff_summary.search_terms_changed ? '已变更' : '未变' }}
            </el-tag>
          </div>
          <div class="compare-grid">
            <div class="compare-col" v-for="side in ['version_a', 'version_b']" :key="side">
              <div class="compare-col-head">{{ side === 'version_a' ? '版本 A' : '版本 B' }} · {{ formatTime(compareResult[side].created_at) }}</div>
              <div class="compare-title">{{ compareResult[side].listing.title }}</div>
              <div v-for="(b, i) in (compareResult[side].listing.bullet_points || [])" :key="i" class="compare-bullet">{{ i + 1 }}. {{ b }}</div>
              <div class="compare-terms">{{ compareResult[side].listing.search_terms }}</div>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import AgentGraph from './components/AgentGraph.vue'
import AppSidebar from './components/AppSidebar.vue'
import WorkflowHub from './components/WorkflowHub.vue'
import TaskManager from './components/TaskManager.vue'
import Connections from './components/Connections.vue'

// 顶层视图切换（牛顿风格侧边栏导航）
const activeView = ref('workbench')
// 执行拓扑图折叠开关（小屏收起后可单屏完整查看工作台）
const showGraph = ref(true)
// hub 技能开关关闭的可选节点（传入后端跳过对应节点）
const disabledStages = ref([])

const isRunning = ref(false)
const runningNode = ref(null)
const completedNodes = ref([])
const plannedNodes = ref([])
const plannedStages = ref([])
const etaSeconds = ref(0)
const nodeDurations = ref({})
const traceLogs = ref([])
const activeTab = ref('listing')
const lastThreadId = ref(null)
const lastError = ref('')

// 1688 导入相关状态
const importDialogVisible = ref(false)
const importUrl = ref('')
const importLoading = ref(false)
const importMessage = ref('')
const importSuccess = ref(false)
const importedProduct = ref(null)
const showImagePreview = ref(false)
const importRecommend = ref({ platform: 'Amazon', market: 'US' })

// 根据商品标题智能推荐目标平台与站点（家居厨房偏好东南亚走量，其余默认 Amazon 美区）
function pickRecommendedTarget(title) {
  const t = (title || '').toLowerCase()
  if (/收纳|厨房|家居|家纺|置物|餐具|水杯|保温杯|四件套|窗帘|地毯/.test(t)) {
    return { platform: 'Shopee', market: 'Southeast Asia' }
  }
  if (/童装|玩具|母婴|宝宝|儿童/.test(t)) {
    return { platform: 'Shopee', market: 'Southeast Asia' }
  }
  return { platform: 'Amazon', market: 'US' }
}

// 平台直连发布相关状态
const publishLoading = ref(false)
const publishResult = ref(null)
const publishResultVisible = ref(false)

// 虚拟试穿（按需增值服务，仅服装类，不在主流水线内）
const tryonLoading = ref(false)
const tryonResult = ref(null)

// AI 场景图按需补充（搬运原素材模式下手动触发）
const scenesLoading = ref(false)

// 批量上新相关状态
const batchDialogVisible = ref(false)
const batchItems = ref([])
const batchResults = ref([])
const batchRunning = ref(false)
const batchIntent = ref('full_launch')
const batchSummary = ref('')

// Listing 版本对比相关状态
const versionDrawerVisible = ref(false)
const versionList = ref([])
const versionSelected = ref([])
const compareResult = ref(null)
const compareLoading = ref(false)

const form = reactive({
  intent: 'full_launch',
  target_platform: 'Amazon',
  target_market: 'US',
  product_image_url: 'https://img.alicdn.com/imgextra/i1/6000000007892/O1CN01a2ZpQM1scXS5sBsAa_!!6000000007892-0-tps-400-400.jpg',
  imported_images: [],
  message: '帮我将这款夏季法式复古方领碎花连衣裙做全链路上新，目标市场为 Amazon US。'
})

const resultData = reactive({
  product_attributes: null,
  market_insights: null,
  trend_benchmark: null,
  listing_content: null,
  studio_assets: null,
  video_package: null,
  localized_images: null,
  platform_package: null,
  // V2 新增：选品评分 / 素材盘点 / 质量评分 / 发布审核包
  opportunity_score: null,
  asset_inventory: null,
  asset_gap: null,
  listing_health: null,
  publish_package: null
})

const VIDEO_MODE_INFO = {
  rendered: { label: '成片已合成', tag: 'success' },
  narrated_storyboard: { label: '分镜 + 配音已就绪', tag: 'warning' },
  storyboard_only: { label: '分镜脚本已就绪', tag: 'info' }
}
const videoModeLabel = computed(() =>
  VIDEO_MODE_INFO[resultData.video_package?.mode]?.label || '待生成')
const videoModeTagType = computed(() =>
  VIDEO_MODE_INFO[resultData.video_package?.mode]?.tag || 'info')
const isApparel = computed(() =>
  resultData.product_attributes?.category_family === 'apparel')

function handlePresetSelect(command) {
  if (command === 'french_dress') {
    form.target_platform = 'Amazon'
    form.target_market = 'US'
    form.product_image_url = 'https://img.alicdn.com/imgextra/i1/6000000007892/O1CN01a2ZpQM1scXS5sBsAa_!!6000000007892-0-tps-400-400.jpg'
    form.message = '帮我将这款夏季法式复古方领碎花连衣裙做全链路上新，目标市场为 Amazon US。'
  } else if (command === 'linen_shirt') {
    form.target_platform = 'Shopee'
    form.target_market = 'Southeast Asia'
    form.product_image_url = 'https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=600&auto=format&fit=crop&q=80'
    form.message = '为这款极简透气亚麻休闲长袖衬衫生成 Shopee 东南亚站点的选品分析与双语 Listing。'
  }
}

function resetAll() {
  completedNodes.value = []
  traceLogs.value = []
  runningNode.value = null
  plannedNodes.value = []
  plannedStages.value = []
  etaSeconds.value = 0
  nodeDurations.value = {}
  lastError.value = ''
  resultData.product_attributes = null
  resultData.market_insights = null
  resultData.trend_benchmark = null
  resultData.listing_content = null
  resultData.studio_assets = null
  resultData.video_package = null
  resultData.localized_images = null
  resultData.platform_package = null
  resultData.opportunity_score = null
  resultData.asset_inventory = null
  resultData.asset_gap = null
  resultData.listing_health = null
  resultData.publish_package = null
  tryonResult.value = null
}

async function runPipeline({ resume = false } = {}) {
  isRunning.value = true
  if (!resume) {
    lastError.value = ''
    ElMessage.info('LangGraph 智能体引擎启动，正在编排执行流水线...')
  } else {
    ElMessage.info('从检查点断点继续执行...')
  }

  try {
    const body = resume
      ? { resume: true, thread_id: lastThreadId.value, message: form.message }
      : {
          message: form.message,
          product_image_url: form.product_image_url,
          imported_images: form.imported_images,
          target_platform: form.target_platform,
          target_market: form.target_market,
          intent: form.intent,
          disabled_stages: disabledStages.value,
          // ── 传递 1688 真实数据 ──
          product_title: importedProduct.value?.title || '',
          supply_price_cny: parsePrice(importedProduct.value?.source_price),
          sku_attributes: importedProduct.value?.sku_attributes || {},
          source_url: importedProduct.value?.source_url || '',
        }

    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() // 保留未完整的结尾

      for (const block of lines) {
        if (!block.trim()) continue
        const eventMatch = block.match(/event:\s*([^\n]+)/)
        const dataMatch = block.match(/data:\s*([\s\S]+)/)

        if (eventMatch && dataMatch) {
          const eventType = eventMatch[1].trim()
          try {
            const data = JSON.parse(dataMatch[1].trim())
            handleSseEvent(eventType, data)
          } catch (err) {
            console.error('SSE JSON 解析错误:', err)
          }
        }
      }
    }
  } catch (error) {
    console.error('执行失败:', error)
    lastError.value = error.message
    ElMessage.error('上新任务执行异常: ' + error.message)
  } finally {
    isRunning.value = false
    runningNode.value = null
  }
}

async function startLaunch() {
  if (!form.message) {
    ElMessage.warning('请输入上新指令')
    return
  }
  resetAll()
  await runPipeline()
}

async function resumeRun() {
  if (!lastThreadId.value) {
    ElMessage.warning('无可续跑的任务')
    return
  }
  await runPipeline({ resume: true })
}

// 本地商品图上传（后端转存到 /uploads/，供前端预览与多模态识别）
async function handleUpload({ file }) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const resp = await fetch('/api/products/upload', { method: 'POST', body: formData })
    const data = await resp.json()
    if (data.status === 'success') {
      form.product_image_url = data.url
      ElMessage.success('商品图上传成功')
    } else {
      ElMessage.error(data.detail || '上传失败')
    }
  } catch (e) {
    ElMessage.error('上传失败: ' + e.message)
  }
}

// 1688 商品导入解析
async function doImport1688() {
  if (!importUrl.value.trim()) {
    ElMessage.warning('请粘贴 1688 商品链接')
    return
  }
  importLoading.value = true
  importMessage.value = ''
  importedProduct.value = null
  try {
    const resp = await fetch('/api/import/1688', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: importUrl.value.trim() })
    })
    const data = await resp.json()
    importSuccess.value = data.success
    importMessage.value = data.message
    if (data.success && data.product) {
      importedProduct.value = data.product
      importRecommend.value = pickRecommendedTarget(data.product.title)
    }
  } catch (e) {
    importSuccess.value = false
    importMessage.value = '导入失败: ' + e.message
  } finally {
    importLoading.value = false
  }
}

// 将解析结果预填到上新表单（标题入指令，主图入图片字段）
function applyImported() {
  const p = importedProduct.value
  if (!p) return
  if (p.main_image) form.product_image_url = p.main_image
  form.imported_images = p.images || []
  if (p.title) {
    form.message = `帮我将这款从 1688 搬运的商品【${p.title}】做全链路上新，目标平台 ${form.target_platform}（${form.target_market}），请基于商品图重新识别属性并生成爆款化 Listing。`
  }
  importDialogVisible.value = false
  ElMessage.success('商品已预填到上新表单，可补充指令后启动')
}

// 一键搬运：预填表单 + 自动选定平台站点 + 直接启动全链路（傻瓜式体验）
async function importAndLaunch() {
  const p = importedProduct.value
  if (!p) return
  if (p.main_image) form.product_image_url = p.main_image
  form.imported_images = p.images || []
  form.target_platform = importRecommend.value.platform
  form.target_market = importRecommend.value.market
  form.intent = 'full_launch'
  form.message = `帮我将这款从 1688 搬运的商品【${p.title || '跨境商品'}】做全链路上新，`
    + `目标平台 ${form.target_platform}（${form.target_market}），1688 进价 ${p.source_price || '未知'}，`
    + `请基于商品图识别属性，沿用搬运素材，生成爆款化 Listing 并输出发布包。`
  importDialogVisible.value = false
  ElMessage.success(`已选定 ${form.target_platform} ${form.target_market}，全链路启动中…`)
  await runPipeline()
}

// 侧边栏视图切换
function switchView(view) {
  activeView.value = view
}

// hub「使用」按钮：预置意图并回到工作台（批量工作流直接打开 CSV 弹窗）
function useWorkflow(id) {
  if (id === 'batch') {
    activeView.value = 'workbench'
    batchDialogVisible.value = true
    return
  }
  form.intent = id
  activeView.value = 'workbench'
  ElMessage.success(id === 'market_only'
    ? '已切换为「市场洞察速览」工作流，填入商品后启动'
    : '已切换为「全链路智能上新」工作流，填入商品或粘贴 1688 链接后启动')
}

// hub 技能开关：开启/关闭可选节点
function toggleStage(nodeId, on) {
  const i = disabledStages.value.indexOf(nodeId)
  if (on && i >= 0) disabledStages.value.splice(i, 1)
  if (!on && i < 0) disabledStages.value.push(nodeId)
  ElMessage.info(on ? '已开启：下次全链路包含该节点' : '已关闭：下次全链路跳过该节点')
}

// 任务管理页查看成果：载入后回到工作台
async function handleViewTask(task) {
  await viewTask(task)
  activeView.value = 'workbench'
}

async function viewTask(task) {
  try {
    const resp = await fetch(`/api/tasks/${task.thread_id}`)
    const data = await resp.json()
    const result = data.task?.result || {}
    resetAll()
    Object.assign(resultData, {
      product_attributes: result.product_attributes || null,
      market_insights: result.market_insights || null,
      trend_benchmark: result.trend_benchmark || null,
      listing_content: result.listing_content || null,
      studio_assets: result.studio_assets || null,
      video_package: result.video_package || null,
      localized_images: result.localized_images || null,
      platform_package: result.platform_package || null,
      // V2 新增字段
      opportunity_score: result.opportunity_score || null,
      asset_inventory: result.asset_inventory || null,
      asset_gap: result.asset_gap || null,
      listing_health: result.listing_health || null,
      publish_package: result.publish_package || null
    })
    // 历史任务兼容：旧存档若含试穿结果则直接展示，新链路不再自动生成
    tryonResult.value = result.studio_assets?.virtual_tryon || null
    ElMessage.success('已载入历史任务成果')
  } catch (e) {
    ElMessage.error('载入失败: ' + e.message)
  }
}

// 从价格字符串中提取数字（如 "¥39" → 39, "$12.5" → 12.5）
function parsePrice(val) {
  if (val == null) return null
  if (typeof val === 'number') return val
  const m = String(val).replace(/[^\d.]/g, '')
  const n = parseFloat(m)
  return isNaN(n) ? null : n
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function handleSseEvent(eventType, data) {
  if (eventType === 'plan') {
    lastThreadId.value = data.thread_id
    plannedNodes.value = data.nodes || []
    plannedStages.value = data.stages || []
    etaSeconds.value = data.total_eta || 0
  } else if (eventType === 'node_start') {
    runningNode.value = data.node
    etaSeconds.value = data.eta_seconds ?? 0
  } else if (eventType === 'node_update') {
    const nodeName = data.node
    runningNode.value = null
    if (!completedNodes.value.includes(nodeName)) {
      completedNodes.value.push(nodeName)
    }
    if (data.duration_seconds != null) {
      nodeDurations.value[nodeName] = data.duration_seconds
    }
    etaSeconds.value = data.eta_seconds ?? 0

    if (data.data) {
      if (data.data.product_attributes) resultData.product_attributes = data.data.product_attributes
      if (data.data.market_insights) resultData.market_insights = data.data.market_insights
      if (data.data.trend_benchmark) resultData.trend_benchmark = data.data.trend_benchmark
      if (data.data.listing_content) resultData.listing_content = data.data.listing_content
      if (data.data.studio_assets) resultData.studio_assets = data.data.studio_assets
      if (data.data.video_package) resultData.video_package = data.data.video_package
      if (data.data.localized_images) resultData.localized_images = data.data.localized_images
      if (data.data.platform_package) resultData.platform_package = data.data.platform_package
      if (data.data.opportunity_score) resultData.opportunity_score = data.data.opportunity_score
      if (data.data.asset_inventory) resultData.asset_inventory = data.data.asset_inventory
      if (data.data.asset_gap) resultData.asset_gap = data.data.asset_gap
      if (data.data.listing_health) resultData.listing_health = data.data.listing_health
      if (data.data.publish_package) resultData.publish_package = data.data.publish_package
    }

    if (data.summary) {
      traceLogs.value.push({ node: nodeName, summary: data.summary })
    }
  } else if (eventType === 'complete') {
    if (data.result) {
      Object.assign(resultData, data.result)
    }
    lastError.value = ''
    etaSeconds.value = 0
    ElMessage.success('全链路上新任务已全部完成')
  } else if (eventType === 'error') {
    lastError.value = data.error || '未知错误'
    if (data.thread_id) lastThreadId.value = data.thread_id
    ElMessage.error('执行出错: ' + lastError.value + (data.resumable ? '（可断点续跑）' : ''))
  }
}

function exportPackage() {
  const jsonStr = JSON.stringify(resultData, null, 2)
  const blob = new Blob([jsonStr], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `GloLaunch_Package_${Date.now()}.json`
  a.click()
  ElMessage.success('已导出标准发布包数据！')
}

// ---------- 平台直连发布 ----------
async function doPublish() {
  if (!lastThreadId.value) {
    ElMessage.warning('请先完成一次全链路上新再发布')
    return
  }
  publishLoading.value = true
  try {
    const resp = await fetch('/api/publish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ thread_id: lastThreadId.value })
    })
    const data = await resp.json()
    if (!resp.ok) {
      ElMessage.error(data.detail || '发布失败')
      return
    }
    publishResult.value = data
    publishResultVisible.value = true
    ElMessage.success(data.mode === 'live' ? '已真实提交至平台！' : '演练发布完成，回执已生成')
  } catch (e) {
    ElMessage.error('发布失败: ' + e.message)
  } finally {
    publishLoading.value = false
  }
}

// ---------- V2 发布审核 (Human-in-the-loop) ----------
async function handlePublishDecision(decision) {
  if (!lastThreadId.value) {
    ElMessage.warning('请先完成一次全链路上新')
    return
  }
  try {
    const resp = await fetch('/api/v2/publish/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        thread_id: lastThreadId.value,
        decision,
        comment: decision === 'rejected' ? '人工审核驳回，请根据合规反馈修改后重新提交' : ''
      })
    })
    const data = await resp.json()
    if (!resp.ok) {
      ElMessage.error(data.detail || '审核操作失败')
      return
    }
    resultData.publish_package = data.publish_package || resultData.publish_package
    if (decision === 'approved') {
      ElMessage.success('审核通过，正在执行发布...')
      // 自动触发实际发布
      await doPublish()
    } else {
      ElMessage.warning('已驳回，请修改后重新生成')
    }
  } catch (e) {
    ElMessage.error('审核操作失败: ' + e.message)
  }
}

// ---------- 虚拟试穿（按需增值服务） ----------
async function generateTryon() {
  const imgUrl = form.product_image_url || resultData.studio_assets?.white_background_main
  if (!imgUrl) {
    ElMessage.warning('缺少商品图，请先填写商品图片地址')
    return
  }
  tryonLoading.value = true
  try {
    const resp = await fetch('/api/products/studio/tryon', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_url: imgUrl,
        product_desc: resultData.product_attributes?.category || '服装商品'
      })
    })
    const data = await resp.json()
    if (resp.ok && data.virtual_tryon) {
      tryonResult.value = data.virtual_tryon
      ElMessage.success(`虚拟试穿生成完成（引擎：${data.virtual_tryon.engine}）`)
    } else {
      ElMessage.error(data.detail || '虚拟试穿生成失败')
    }
  } catch (e) {
    ElMessage.error('虚拟试穿服务请求失败: ' + e.message)
  } finally {
    tryonLoading.value = false
  }
}

// ---------- AI 场景图按需补充 ----------
async function generateScenes() {
  const attrs = resultData.product_attributes || {}
  scenesLoading.value = true
  try {
    const resp = await fetch('/api/products/studio/scenes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        category: attrs.category || '跨境商品',
        category_family: attrs.category_family || 'general',
        style_tags: attrs.style_tags || [],
        design_features: attrs.design_features || [],
        product_image_url: form.product_image_url || ''
      })
    })
    const data = await resp.json()
    if (resp.ok && data.studio_assets?.lifestyle_scenes) {
      resultData.studio_assets.lifestyle_scenes = data.studio_assets.lifestyle_scenes
      resultData.studio_assets.image_engine = `source_material + ${data.studio_assets.image_engine}`
      resultData.studio_assets.material_mode = 'source_plus'
      ElMessage.success('AI 场景图补充完成（主图仍沿用原素材）')
    } else {
      ElMessage.error(data.detail || 'AI 场景图生成失败')
    }
  } catch (e) {
    ElMessage.error('场景图服务请求失败: ' + e.message)
  } finally {
    scenesLoading.value = false
  }
}

// ---------- 批量上新 ----------
function openBatchDialog() {
  batchDialogVisible.value = true
}

async function handleBatchCsv({ file }) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const resp = await fetch('/api/batch/preview', { method: 'POST', body: formData })
    const data = await resp.json()
    if (data.status === 'success' && data.total > 0) {
      batchItems.value = data.items
      batchResults.value = []
      batchSummary.value = ''
      ElMessage.success(`CSV 解析成功，共 ${data.total} 个商品`)
    } else {
      ElMessage.error(data.detail || 'CSV 中未解析到有效商品行')
    }
  } catch (e) {
    ElMessage.error('CSV 解析失败: ' + e.message)
  }
}

function batchStatusClass(index) {
  const r = batchResults.value[index]
  if (!r) return ''
  return { running: 'batch-running', success: 'batch-success', error: 'batch-error' }[r.status] || ''
}

async function runBatch() {
  if (!batchItems.value.length) return
  batchRunning.value = true
  batchResults.value = []
  batchSummary.value = ''
  try {
    const resp = await fetch('/api/batch/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: batchItems.value, intent: batchIntent.value })
    })
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop()
      for (const block of blocks) {
        if (!block.trim()) continue
        const eventMatch = block.match(/event:\s*([^\n]+)/)
        const dataMatch = block.match(/data:\s*([\s\S]+)/)
        if (!eventMatch || !dataMatch) continue
        const eventType = eventMatch[1].trim()
        let data
        try { data = JSON.parse(dataMatch[1].trim()) } catch { continue }
        if (eventType === 'item_start') {
          batchResults.value[data.index] = { status: 'running' }
        } else if (eventType === 'item_complete') {
          batchResults.value[data.index] = { status: 'success', title: data.title, thread_id: data.thread_id }
        } else if (eventType === 'item_error') {
          batchResults.value[data.index] = { status: 'error', error: data.error }
        } else if (eventType === 'batch_complete') {
          batchSummary.value = `批量上新完成：成功 ${data.success} / 失败 ${data.failed}，耗时 ${data.elapsed_seconds}s，已自动存档至任务历史与版本库`
          ElMessage.success(batchSummary.value)
        }
      }
    }
  } catch (e) {
    ElMessage.error('批量执行异常: ' + e.message)
  } finally {
    batchRunning.value = false
  }
}

// ---------- Listing 版本对比 ----------
async function openVersionDrawer() {
  versionDrawerVisible.value = true
  compareResult.value = null
  versionSelected.value = []
  try {
    const resp = await fetch('/api/tasks/versions?limit=30')
    const data = await resp.json()
    versionList.value = data.versions || []
  } catch (e) {
    console.error('获取版本列表失败:', e)
  }
}

function toggleVersionSelect(id) {
  const idx = versionSelected.value.indexOf(id)
  if (idx >= 0) {
    versionSelected.value.splice(idx, 1)
  } else {
    if (versionSelected.value.length >= 2) versionSelected.value.shift()
    versionSelected.value.push(id)
  }
}

async function doCompare() {
  if (versionSelected.value.length !== 2) return
  compareLoading.value = true
  try {
    const [a, b] = versionSelected.value
    const resp = await fetch(`/api/tasks/versions/compare?a=${a}&b=${b}`)
    const data = await resp.json()
    if (resp.ok) {
      compareResult.value = data
    } else {
      ElMessage.error(data.detail || '对比失败')
    }
  } catch (e) {
    ElMessage.error('对比失败: ' + e.message)
  } finally {
    compareLoading.value = false
  }
}
</script>

<style>
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  background-color: var(--gl-bg);
  color: var(--gl-text);
}

.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: row;
}

.main-area {
  flex: 1;
  min-width: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.view-workbench {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.navbar {
  height: 64px;
  background: var(--gl-panel);
  border-bottom: 1px solid var(--gl-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: linear-gradient(135deg, #2563eb 0%, #38bdf8 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}

.brand-text {
  display: flex;
  flex-direction: column;
}

.brand-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--gl-text-hi);
  letter-spacing: 0.5px;
}

.brand-subtitle {
  font-size: 11px;
  color: var(--gl-sub);
}

.nav-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.main-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.graph-section {
  width: 100%;
}

.workspace-grid {
  display: grid;
  grid-template-columns: 420px 1fr;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.left-panel, .right-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.control-card, .results-card {
  background: var(--gl-panel) !important;
  border: 1px solid var(--gl-border) !important;
  border-radius: 12px !important;
  color: var(--gl-text) !important;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 单屏工作台：面板自身不滚动，内部区域独立滚动 */
.control-card :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.control-card .el-form {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

/* 紧凑表单：保证 1080p 下启动按钮可见，无需滚动 */
.control-card :deep(.el-form-item) {
  margin-bottom: 12px;
}

.results-card :deep(.el-card__body) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.results-card :deep(.el-tabs) {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.results-card :deep(.el-tabs__header) {
  flex-shrink: 0;
  margin-bottom: 10px;
}

.results-card :deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
}

.results-card :deep(.el-tab-pane) {
  height: 100%;
  overflow-y: auto;
}

.card-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--gl-text-hi2);
  font-weight: 600;
}

.launch-btn {
  width: 100%;
  margin-top: 6px;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
  border: none !important;
  font-weight: 600;
  height: 42px;
}

.image-thumb-box {
  position: relative;
  width: 100%;
  height: 100px;
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 16px;
  border: 1px solid var(--gl-border-2);
}

.thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-tag {
  position: absolute;
  bottom: 6px;
  right: 6px;
  background: rgba(0,0,0,0.7);
  font-size: 11px;
  color: #38bdf8;
  padding: 2px 8px;
  border-radius: 4px;
}

.custom-tabs .el-tabs__item {
  color: var(--gl-sub) !important;
  font-size: 14px;
}

.custom-tabs .el-tabs__item.is-active {
  color: #38bdf8 !important;
  font-weight: 600;
}

.result-block {
  margin-bottom: 20px;
  background: var(--gl-node);
  padding: 14px 16px;
  border-radius: 8px;
  border: 1px solid var(--gl-border-2);
}

.block-label {
  font-size: 13px;
  font-weight: 600;
  color: #38bdf8;
  margin-bottom: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title-content {
  font-size: 15px;
  font-weight: 500;
  line-height: 1.5;
  color: var(--gl-text-hi);
}

.bullet-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bullet-item {
  display: flex;
  gap: 10px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--gl-text-mid);
}

.bullet-num {
  background: var(--gl-border-2);
  color: #38bdf8;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  flex-shrink: 0;
}

.search-terms-box, .desc-box {
  font-size: 13px;
  color: var(--gl-text-mid);
  line-height: 1.6;
  background: var(--gl-panel-deep);
  padding: 10px;
  border-radius: 6px;
}

.metric-row {
  margin-bottom: 16px;
}

.metric-card {
  background: var(--gl-node);
  border: 1px solid var(--gl-border-2);
  border-radius: 8px;
  padding: 12px;
  text-align: center;
}

.metric-label {
  font-size: 11px;
  color: var(--gl-sub);
  margin-bottom: 4px;
}

.metric-val {
  font-size: 18px;
  font-weight: 700;
  color: var(--gl-text-hi);
}

.metric-val.highlight {
  color: #22c55e;
}

.metric-val.score {
  color: #38bdf8;
}

.text-p {
  font-size: 13px;
  line-height: 1.6;
  color: var(--gl-text-mid);
  margin-bottom: 6px;
}

.pain-tag {
  font-size: 13px;
  color: #f87171;
  margin-bottom: 6px;
  list-style: none;
}

.kw-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tryon-banner {
  display: flex;
  gap: 16px;
  background: var(--gl-panel-deep);
  padding: 12px;
  border-radius: 8px;
}

.tryon-img {
  width: 140px;
  height: 180px;
  object-fit: cover;
  border-radius: 6px;
}

.tryon-details {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 10px;
  font-size: 13px;
  color: var(--gl-text-mid);
}

.tryon-badge {
  color: #38bdf8;
  font-weight: 600;
}

.tryon-engine {
  color: var(--gl-sub);
  font-size: 12px;
}

.tryon-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.tryon-tip {
  font-size: 12px;
  color: var(--gl-faint);
}

.source-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: var(--gl-panel-deep);
  border: 1px solid var(--gl-hover-border);
  border-radius: 8px;
  padding: 14px 16px;
  font-size: 13px;
  color: var(--gl-text-mid);
}

.source-tip {
  margin-top: 6px;
  font-size: 12px;
  color: var(--gl-faint);
}

.import-hint {
  font-size: 12px;
  color: var(--gl-faint);
  margin-bottom: 10px;
  line-height: 1.5;
}

.import-oauth {
  margin-bottom: 10px;
  font-size: 12px;
}

.import-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.scene-gallery {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.scene-card {
  background: var(--gl-panel-deep);
  border-radius: 6px;
  overflow: hidden;
}

.scene-img {
  width: 100%;
  height: 120px;
  object-fit: cover;
}

.scene-caption {
  font-size: 11px;
  text-align: center;
  padding: 6px;
  color: var(--gl-sub);
}

.attr-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  font-size: 13px;
  color: var(--gl-text-mid);
}

.rules-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rule-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--gl-text-mid);
}

.publish-action-box {
  margin-top: 24px;
  padding: 16px;
  background: var(--gl-node);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.publish-btn-row {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

/* 带货视频展示 */
.video-hook {
  font-size: 15px;
  font-weight: 700;
  color: #fbbf24;
  margin-bottom: 8px;
}

.video-player {
  width: 100%;
  max-height: 360px;
  border-radius: 8px;
  background: #000;
  margin-top: 8px;
}

.audio-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.audio-label {
  font-size: 12px;
  color: var(--gl-sub);
  flex-shrink: 0;
}

.audio-player {
  flex: 1;
  height: 32px;
}

.shot-card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: var(--gl-panel-deep);
  border: 1px solid var(--gl-border-2);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.shot-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(56, 189, 248, 0.15);
  border: 1px solid #38bdf8;
  color: #38bdf8;
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.shot-body {
  flex: 1;
  min-width: 0;
}

.shot-scene {
  font-size: 13px;
  color: var(--gl-text-hi2);
  margin-bottom: 4px;
}

.shot-cam {
  font-size: 11px;
  color: var(--gl-faint);
}

.shot-voiceover {
  font-size: 12px;
  color: #22c55e;
  line-height: 1.5;
}

.shot-duration {
  font-size: 12px;
  color: #fbbf24;
  font-weight: 600;
  flex-shrink: 0;
}

/* 发布回执 */
.publish-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.publish-id {
  font-family: monospace;
  font-size: 13px;
  color: var(--gl-faint);
}

.timeline-item {
  display: flex;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px dashed var(--gl-text);
}

.timeline-item:last-child {
  border-bottom: none;
}

.timeline-dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  color: #fff;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.timeline-step {
  font-size: 13px;
  font-weight: 600;
  color: #f8fafc;
}

.timeline-detail {
  font-size: 12px;
  color: var(--gl-faint);
}

/* 批量上新 */
.batch-preview {
  margin-top: 14px;
}

.batch-preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
}

.batch-list {
  max-height: 320px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.batch-item {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--gl-panel-deep);
  border: 1px solid var(--gl-border-2);
  border-radius: 8px;
  padding: 8px 12px;
}

.batch-item.batch-running {
  border-color: #38bdf8;
}

.batch-item.batch-success {
  border-color: rgba(34, 197, 94, 0.6);
}

.batch-item.batch-error {
  border-color: rgba(248, 113, 113, 0.6);
}

.batch-idx {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--gl-border-2);
  color: var(--gl-sub);
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.batch-item-body {
  flex: 1;
  min-width: 0;
}

.batch-item-name {
  font-size: 13px;
  color: var(--gl-text-hi2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.batch-item-meta {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}

.batch-status {
  font-size: 12px;
  color: var(--gl-sub);
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

/* 版本对比 */
.version-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.version-item {
  padding: 10px 12px;
  background: var(--gl-text-hi);
  border: 1px solid var(--gl-text);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.version-item:hover {
  border-color: #409eff;
}

.version-item.selected {
  border-color: #409eff;
  background: rgba(64, 158, 255, 0.08);
  box-shadow: 0 0 0 1px #409eff inset;
}

/* 对比/历史列表中的文字色：保证亮暗主题下均可读 */
.version-title, .task-title, .compare-title {
  color: #334155;
}

.version-title {
  font-size: 12px;
  color: var(--gl-node);
  line-height: 1.5;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.compare-result {
  margin-top: 16px;
}

.compare-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.compare-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.compare-col {
  background: var(--gl-text-hi);
  border: 1px solid var(--gl-text);
  border-radius: 8px;
  padding: 10px;
}

.compare-col-head {
  font-size: 12px;
  font-weight: 700;
  color: #2563eb;
  margin-bottom: 8px;
}

.compare-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--gl-node);
  line-height: 1.5;
  margin-bottom: 8px;
}

.compare-bullet {
  font-size: 11px;
  color: var(--gl-border-3);
  line-height: 1.5;
  margin-bottom: 4px;
}

.compare-terms {
  font-size: 11px;
  color: var(--gl-faint);
  background: var(--gl-node);
  border-radius: 4px;
  padding: 6px;
  margin-top: 6px;
  word-break: break-all;
}

.empty-state {
  padding: 60px 0;
}

/* 图片操作行（上传 / 1688 导入） */
.image-action-row {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}

/* 失败断点续跑 */
.error-resume-box {
  margin-top: 12px;
  padding: 12px;
  background: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.4);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.error-text {
  font-size: 12px;
  color: #f87171;
  word-break: break-all;
}

/* 1688 导入弹窗 */
.import-preview {
  display: flex;
  gap: 14px;
  margin-top: 14px;
  padding: 12px;
  background: var(--gl-panel-deep);
  border: 1px solid var(--gl-border-2);
  border-radius: 8px;
}

.import-thumb {
  width: 110px;
  height: 110px;
  object-fit: cover;
  border-radius: 6px;
  flex-shrink: 0;
}

.import-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.import-title {
  font-size: 13px;
  color: var(--gl-text-hi2);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.import-meta {
  display: flex;
  gap: 8px;
}

/* 任务历史抽屉 */
.task-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.task-item {
  padding: 12px;
  background: var(--gl-text-hi);
  border: 1px solid var(--gl-text);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.task-item:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.15);
}

.task-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--gl-node);
  margin-bottom: 6px;
}

.task-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.task-time {
  font-size: 12px;
  color: var(--gl-sub);
  margin-left: auto;
}

/* 爆款对标展示 */
.benchmark-card {
  background: var(--gl-panel-deep);
  border: 1px solid var(--gl-border-2);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.bp-name {
  font-size: 13px;
  font-weight: 600;
  color: #fbbf24;
  margin-bottom: 4px;
}

.bp-row {
  font-size: 12px;
  color: var(--gl-text-mid);
  line-height: 1.6;
}

.bp-code {
  background: var(--gl-node);
  color: #38bdf8;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
}

.formula-box {
  background: rgba(251, 191, 36, 0.08);
  border: 1px dashed #fbbf24;
  border-radius: 8px;
  padding: 12px;
  font-size: 13px;
  color: #fde68a;
  line-height: 1.6;
}

.strategy-list {
  padding-left: 18px;
  font-size: 13px;
  color: var(--gl-text-mid);
  line-height: 1.8;
}

/* 图片本地化对比展示 */
.localize-pair {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: var(--gl-panel-deep);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
}

.localize-col {
  flex: 1;
  min-width: 0;
  text-align: center;
}

.localize-img {
  width: 100%;
  max-height: 220px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--gl-border-2);
}

.localize-cap {
  font-size: 11px;
  color: var(--gl-sub);
  margin-top: 6px;
}

.localize-arrow {
  color: #22c55e;
  font-size: 20px;
  align-self: center;
  flex-shrink: 0;
}

.localize-fallback {
  border: 1px dashed var(--gl-border-2);
  border-radius: 6px;
  padding: 10px;
  text-align: left;
  min-height: 120px;
}

.text-pair {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  font-size: 12px;
}

.origin-text {
  color: #f87171;
  text-decoration: line-through;
}

.trans-text {
  color: #22c55e;
  font-weight: 600;
}

.pos-tag {
  background: var(--gl-border-2);
  color: var(--gl-sub);
  border-radius: 4px;
  padding: 0 6px;
  font-size: 10px;
}

.no-text-tip {
  font-size: 12px;
  color: var(--gl-faint);
}

/* ========== V2 新增面板样式 ========== */

/* 选品决策评分 */
.opportunity-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.score-header {
  display: flex;
  gap: 24px;
  align-items: center;
}
.total-score-ring {
  position: relative;
  width: 120px;
  height: 120px;
  flex-shrink: 0;
}
.score-ring-svg {
  width: 100%;
  height: 100%;
}
.score-ring-text {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.score-number {
  font-size: 28px;
  font-weight: 800;
  line-height: 1;
  color: var(--el-text-color-primary);
}
.score-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.score-summary {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.recommendation-text {
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin: 0;
  line-height: 1.5;
}
.platform-recs {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.rec-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.rec-tag {
  margin-right: 0;
}
.dimension-bars {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.dim-row {
  display: grid;
  grid-template-columns: 90px 1fr 60px;
  align-items: center;
  gap: 10px;
}
.dim-name {
  font-size: 13px;
  color: var(--el-text-color-regular);
  text-align: right;
}
.dim-weight {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.supply-market-fit {
  margin-top: 4px;
}

/* 素材缺口分析 */
.asset-gap-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.inventory-summary {
  padding: 16px;
  background: var(--gl-node);
  border-radius: 8px;
}
.gap-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.gap-item {
  padding: 12px 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gap-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gap-asset-type {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gap-status {
  font-size: 12px;
  margin-left: auto;
  font-weight: 500;
}
.gap-status.missing { color: #ef4444; }
.gap-status.generated { color: #22c55e; }
.gap-status.reused { color: #3b82f6; }
.gap-reason {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0;
}
.gap-cost {
  margin-top: 2px;
}

/* Listing 质量评分 */
.health-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.health-header {
  display: flex;
  align-items: center;
  gap: 16px;
}
.grade-badge {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  font-weight: 900;
  color: #fff;
  flex-shrink: 0;
}
.grade-A { background: linear-gradient(135deg, #22c55e, #16a34a); }
.grade-B { background: linear-gradient(135deg, #3b82f6, #2563eb); }
.grade-C { background: linear-gradient(135deg, #f59e0b, #d97706); }
.grade-D { background: linear-gradient(135deg, #f97316, #ea580c); }
.grade-F { background: linear-gradient(135deg, #ef4444, #dc2626); }
.health-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.health-total {
  font-size: 16px;
  color: var(--el-text-color-primary);
}
.health-total strong {
  font-size: 22px;
}
.health-grade-text {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.health-dim-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.health-dim-card {
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.dim-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.dim-card-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.dim-card-score {
  font-size: 18px;
  font-weight: 700;
}
.dim-card-feedback {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin: 0;
  line-height: 1.4;
}
.improvement-priorities {
  margin-top: 4px;
}

/* 发布审核 */
.publish-review-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.review-header {
  margin-bottom: 4px;
}
.review-checklist {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.check-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--gl-node);
  border-radius: 6px;
}
.check-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  min-width: 100px;
}
.check-detail {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.review-btn-row {
  display: flex;
  gap: 12px;
  justify-content: center;
}
</style>
