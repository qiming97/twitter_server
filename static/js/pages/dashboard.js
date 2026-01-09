/**
 * 数据总览页面
 */
const DashboardPage = {
  components: {
    'loading-spinner': Components.LoadingComponent,
    'empty-state': Components.EmptyStateComponent
  },
  data() {
    return {
      loading: false,
      stats: null,
      taskStatus: null
    }
  },
  template: `
    <div>
      <loading-spinner v-if="loading" />
      
      <template v-else-if="stats">
        <!-- 第一行：核心状态数据（正常、冻结、改密、锁号、错误） -->
        <div class="grid grid-5" style="margin-bottom: 20px;">
          <div class="stat-card" style="--status-color: var(--success)">
            <div class="stat-icon">✓</div>
            <div>
              <div class="stat-value" style="color: var(--success)">{{ (stats.by_status['正常'] || 0).toLocaleString() }}</div>
              <div class="stat-label">正常</div>
            </div>
          </div>
          <div class="stat-card" style="--status-color: var(--error)">
            <div class="stat-icon">❄</div>
            <div>
              <div class="stat-value" style="color: var(--error)">{{ (stats.by_status['冻结'] || 0).toLocaleString() }}</div>
              <div class="stat-label">冻结</div>
            </div>
          </div>
          <div class="stat-card" style="--status-color: var(--warning)">
            <div class="stat-icon">🔑</div>
            <div>
              <div class="stat-value" style="color: var(--warning)">{{ (stats.by_status['改密'] || 0).toLocaleString() }}</div>
              <div class="stat-label">改密</div>
            </div>
          </div>
          <div class="stat-card" style="--status-color: #e11d48">
            <div class="stat-icon">🔒</div>
            <div>
              <div class="stat-value" style="color: #e11d48">{{ (stats.by_status['锁号'] || 0).toLocaleString() }}</div>
              <div class="stat-label">锁号</div>
            </div>
          </div>
          <div class="stat-card" style="--status-color: #8b5cf6">
            <div class="stat-icon">⚠</div>
            <div>
              <div class="stat-value" style="color: #8b5cf6">{{ (stats.by_status['错误'] || 0).toLocaleString() }}</div>
              <div class="stat-label">错误</div>
            </div>
          </div>
        </div>
        
        <!-- 第二行：提取状态 + 任务状态 -->
        <div class="grid grid-2" style="margin-bottom: 20px;">
          <!-- 提取状态 -->
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">📤 提取状态</h3>
            </div>
            <div class="extract-stats">
              <div class="extract-stat">
                <div class="extract-icon" style="background: var(--success-bg); color: var(--success);">✓</div>
                <div class="extract-info">
                  <div class="extract-value">{{ stats.extractable_count.toLocaleString() }}</div>
                  <div class="extract-label">可提取</div>
                </div>
                <div class="extract-hint">正常且未提取</div>
              </div>
              <div class="extract-stat">
                <div class="extract-icon" style="background: var(--info-bg); color: var(--info);">📋</div>
                <div class="extract-info">
                  <div class="extract-value">{{ stats.extracted_count.toLocaleString() }}</div>
                  <div class="extract-label">已提取</div>
                </div>
                <div class="extract-hint">已导出过</div>
              </div>
            </div>
            <div class="extract-progress">
              <div class="extract-progress-info">
                <span>提取进度</span>
                <span>{{ stats.extracted_count }} / {{ stats.extracted_count + stats.extractable_count }}</span>
              </div>
              <div class="progress">
                <div class="progress-bar" :style="{ width: extractedPercent + '%' }"></div>
              </div>
            </div>
          </div>
          
          <!-- 任务状态 -->
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">🚀 任务状态</h3>
              <button class="btn btn-sm btn-secondary" @click="fetchTaskStatus">刷新</button>
            </div>
            <div v-if="taskStatus" class="task-status-content">
              <div class="task-badge" :class="'task-' + taskStatus.status">
                <span class="task-dot"></span>
                {{ taskStatusText }}
              </div>
              <div v-if="taskStatus.status === 'running' || taskStatus.status === 'paused'" class="task-progress">
                <div class="task-stats">
                  <span>已处理: <strong>{{ taskStatus.processed_count }}</strong></span>
                  <span>正常: <strong style="color: var(--success)">{{ taskStatus.success_count }}</strong></span>
                  <span>冻结: <strong style="color: var(--error)">{{ taskStatus.suspended_count }}</strong></span>
                  <span>改密: <strong style="color: var(--warning)">{{ taskStatus.reset_pwd_count }}</strong></span>
                  <span>错误: <strong style="color: #8b5cf6">{{ taskStatus.error_count || 0 }}</strong></span>
                </div>
              </div>
              <div v-else class="task-idle">
                <p v-if="stats.pending_count > 0">有 <strong>{{ stats.pending_count }}</strong> 个账号待检测</p>
                <p v-else>暂无待检测账号</p>
              </div>
            </div>
            <div v-else class="task-idle">
              <p>加载中...</p>
            </div>
          </div>
        </div>

        <!-- 第三行：国家分布 + 粉丝分布 -->
        <div class="grid grid-2">
          <!-- 国家分布 -->
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">🌍 国家分布 TOP 10</h3>
            </div>
            <div v-for="(item, idx) in stats.by_country" :key="item.country" class="dist-row">
              <div class="dist-rank">{{ idx + 1 }}</div>
              <div class="dist-name">{{ item.country || '未知' }}</div>
              <div class="dist-bar">
                <div class="dist-bar-inner" :style="{ width: getBarWidth(item.count, stats.by_country[0]?.count) }"></div>
              </div>
              <div class="dist-count">{{ item.count.toLocaleString() }}</div>
            </div>
            <empty-state v-if="!stats.by_country.length" icon="🌍" title="暂无数据" />
          </div>

          <!-- 粉丝分布 -->
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">👥 粉丝数量分布</h3>
            </div>
            <div v-for="item in stats.by_follower_range" :key="item.range" class="dist-row">
              <div class="dist-range">{{ item.range }}</div>
              <div class="dist-bar follower-bar">
                <div class="dist-bar-inner follower-bar-inner" :style="{ width: getBarWidth(item.count, maxFollowerCount) }"></div>
              </div>
              <div class="dist-count">{{ item.count.toLocaleString() }}</div>
            </div>
          </div>
        </div>
      </template>
      
      <empty-state v-else icon="📭" title="暂无数据" description="请先导入账号" />
    </div>
  `,
  computed: {
    maxFollowerCount() {
      if (!this.stats?.by_follower_range?.length) return 1
      return Math.max(...this.stats.by_follower_range.map(r => r.count)) || 1
    },
    extractedPercent() {
      if (!this.stats) return 0
      const total = this.stats.extracted_count + this.stats.extractable_count
      if (total === 0) return 0
      return Math.round(this.stats.extracted_count / total * 100)
    },
    taskStatusText() {
      if (!this.taskStatus) return '加载中'
      const map = {
        'running': '运行中',
        'paused': '已暂停',
        'stopped': '已停止',
        'completed': '已完成',
        'idle': '空闲'
      }
      return map[this.taskStatus.status] || '空闲'
    }
  },
  methods: {
    async fetchStats() {
      this.loading = true
      try {
        this.stats = await API.getStatistics()
      } catch (e) {
        console.error(e)
      }
      this.loading = false
    },
    async fetchTaskStatus() {
      try {
        const res = await API.getTaskStatus()
        if (res.success) {
          this.taskStatus = res.data
        }
      } catch (e) {
        console.error(e)
      }
    },
    getBarWidth(value, max) {
      if (!max) return '0%'
      return (value / max * 100) + '%'
    }
  },
  mounted() {
    this.fetchStats()
    this.fetchTaskStatus()
    
    // 定时刷新任务状态
    this._timer = setInterval(() => {
      this.fetchTaskStatus()
    }, 5000)
  },
  beforeUnmount() {
    if (this._timer) {
      clearInterval(this._timer)
    }
  }
}

// 页面专用样式
const dashboardStyles = `
  .grid-5 {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 16px;
  }
  @media (max-width: 1400px) {
    .grid-5 { grid-template-columns: repeat(3, 1fr); }
  }
  @media (max-width: 900px) {
    .grid-5 { grid-template-columns: repeat(2, 1fr); }
  }
  @media (max-width: 600px) {
    .grid-5 { grid-template-columns: 1fr; }
  }
  
  .gradient-text {
    background: var(--gradient-primary);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  
  .main-stat {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%);
  }
  
  .extract-stats {
    display: flex;
    gap: 20px;
    margin-bottom: 16px;
  }
  .extract-stat {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px;
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
  }
  .extract-icon {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-md);
    font-size: 1.2rem;
  }
  .extract-info { flex: 1; }
  .extract-value {
    font-size: 1.5rem;
    font-weight: 700;
    font-family: var(--font-mono);
  }
  .extract-label {
    font-size: 0.8rem;
    color: var(--text-secondary);
  }
  .extract-hint {
    font-size: 0.7rem;
    color: var(--text-muted);
    white-space: nowrap;
  }
  .extract-progress { margin-top: 8px; }
  .extract-progress-info {
    display: flex;
    justify-content: space-between;
    font-size: 0.8rem;
    color: var(--text-secondary);
    margin-bottom: 6px;
  }
  
  .task-status-content { }
  .task-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border-radius: 20px;
    font-size: 0.9rem;
    font-weight: 500;
    margin-bottom: 16px;
  }
  .task-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }
  .task-idle { background: var(--bg-secondary); color: var(--text-muted); }
  .task-idle .task-dot { background: var(--text-muted); }
  .task-running { background: var(--success-bg); color: var(--success); }
  .task-running .task-dot { background: var(--success); animation: pulse 1s ease-in-out infinite; }
  .task-paused { background: var(--warning-bg); color: var(--warning); }
  .task-paused .task-dot { background: var(--warning); }
  .task-stopped, .task-completed { background: var(--bg-secondary); color: var(--text-secondary); }
  .task-stopped .task-dot, .task-completed .task-dot { background: var(--text-secondary); }
  
  .task-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    font-size: 0.85rem;
    color: var(--text-secondary);
  }
  .task-stats strong {
    font-family: var(--font-mono);
  }
  
  .task-idle p {
    color: var(--text-muted);
    font-size: 0.9rem;
  }
  .task-idle strong {
    color: var(--primary);
  }
  
  .dist-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
  }
  .dist-rank {
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-secondary);
    border-radius: 50%;
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--text-secondary);
  }
  .dist-name {
    width: 80px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .dist-range {
    width: 60px;
    font-family: var(--font-mono);
    font-size: 0.8rem;
  }
  .dist-bar {
    flex: 1;
    height: 6px;
    background: var(--bg-secondary);
    border-radius: 3px;
    overflow: hidden;
  }
  .dist-bar-inner {
    height: 100%;
    background: var(--gradient-primary);
    border-radius: 3px;
    transition: width 0.5s ease;
  }
  .follower-bar {
    height: 20px;
  }
  .follower-bar-inner {
    background: linear-gradient(90deg, var(--primary) 0%, var(--info) 100%);
    border-radius: var(--radius-sm);
  }
  .dist-count {
    width: 60px;
    text-align: right;
    font-family: var(--font-mono);
    font-size: 0.8rem;
    color: var(--text-secondary);
  }
`

const dashboardStyleEl = document.createElement('style')
dashboardStyleEl.id = 'dashboard-styles'
if (!document.getElementById('dashboard-styles')) {
  dashboardStyleEl.textContent = dashboardStyles
  document.head.appendChild(dashboardStyleEl)
}

window.DashboardPage = DashboardPage
