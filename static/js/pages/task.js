/**
 * 任务管理页面 - 检测任务控制与日志
 */
const TaskPage = {
  components: {
    'loading-spinner': Components.LoadingComponent
  },
  data() {
    return {
      // 任务状态
      taskStatus: null,
      // 代理设置
      proxyConfig: {
        proxy: '',
        concurrency: 5
      },
      // 日志
      logs: [],
      lastServerLogId: 0,  // 追踪服务器日志的最后 id
      maxLogs: 500,
      autoScroll: true,
      // 轮询
      pollTimer: null,
      // 加载状态
      loading: false,
      actionLoading: false,
      fetchingLogs: false  // 防止并发获取日志
    }
  },
  computed: {
    isRunning() {
      return this.taskStatus?.status === 'running'
    },
    isPaused() {
      return this.taskStatus?.status === 'paused'
    },
    // 任务进行中（运行或暂停），禁止修改配置
    isTaskActive() {
      return this.taskStatus && ['running', 'paused'].includes(this.taskStatus.status)
    },
    isStopped() {
      return !this.taskStatus || ['idle', 'stopped', 'completed'].includes(this.taskStatus.status)
    },
    progressPercent() {
      if (!this.taskStatus || this.taskStatus.total_count === 0) return 0
      return Math.round(this.taskStatus.processed_count / this.taskStatus.total_count * 100)
    },
    statusText() {
      const map = {
        'running': '运行中',
        'paused': '已暂停',
        'stopped': '已停止',
        'completed': '已完成',
        'idle': '空闲'
      }
      return map[this.taskStatus?.status] || '空闲'
    },
    statusClass() {
      const map = {
        'running': 'status-running',
        'paused': 'status-paused',
        'stopped': 'status-stopped',
        'completed': 'status-completed'
      }
      return map[this.taskStatus?.status] || 'status-idle'
    }
  },
  template: `
    <div class="task-layout">
      <!-- 左侧：任务控制 -->
      <div class="task-control">
        <!-- 任务状态卡片 -->
        <div class="card status-card">
          <div class="status-header">
            <div class="status-badge" :class="statusClass">
              <span class="status-dot"></span>
              {{ statusText }}
            </div>
            <div class="status-actions">
              <button class="btn btn-sm btn-secondary" @click="fetchStatus" :disabled="loading">
                🔄 刷新
              </button>
            </div>
          </div>
          
          <!-- 危险操作按钮 -->
          <div class="danger-actions" v-if="isStopped">
            <button 
              class="btn btn-sm btn-warning" 
              @click="confirmResetStatus"
              :disabled="actionLoading || !taskStatus || taskStatus.total_count === 0"
            >
              🔄 重置状态
            </button>
            <button 
              class="btn btn-sm btn-error" 
              @click="confirmClearAccounts"
              :disabled="actionLoading || !taskStatus || taskStatus.total_count === 0"
            >
              🗑️ 清空账号
            </button>
          </div>
          
          <div class="status-stats" v-if="taskStatus">
            <div class="stat-item">
              <div class="stat-value">{{ taskStatus.pending_count || 0 }}</div>
              <div class="stat-label">待检测</div>
            </div>
            <div class="stat-item">
              <div class="stat-value" style="color: var(--info)">{{ taskStatus.processed_count || 0 }}</div>
              <div class="stat-label">已处理</div>
            </div>
            <div class="stat-item">
              <div class="stat-value" style="color: var(--success)">{{ taskStatus.success_count || 0 }}</div>
              <div class="stat-label">正常</div>
            </div>
            <div class="stat-item">
              <div class="stat-value" style="color: var(--error)">{{ taskStatus.suspended_count || 0 }}</div>
              <div class="stat-label">冻结</div>
            </div>
            <div class="stat-item">
              <div class="stat-value" style="color: var(--warning)">{{ taskStatus.reset_pwd_count || 0 }}</div>
              <div class="stat-label">改密</div>
            </div>
            <div class="stat-item">
              <div class="stat-value" style="color: #e11d48">{{ taskStatus.locked_count || 0 }}</div>
              <div class="stat-label">锁号</div>
            </div>
            <div class="stat-item">
              <div class="stat-value" style="color: #8b5cf6">{{ taskStatus.error_count || 0 }}</div>
              <div class="stat-label">错误</div>
            </div>
          </div>
          
          <!-- 进度条 -->
          <div class="progress-section" v-if="taskStatus && taskStatus.total_count > 0">
            <div class="progress-info">
              <span>检测进度</span>
              <span>{{ taskStatus.processed_count }} / {{ taskStatus.total_count }} ({{ progressPercent }}%)</span>
            </div>
            <div class="progress">
              <div class="progress-bar" :style="{ width: progressPercent + '%' }"></div>
            </div>
          </div>
        </div>

        <!-- 代理配置 -->
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">⚙️ 检测配置</h3>
          </div>
          
          <div class="form-group">
            <label class="form-label">代理地址</label>
            <input 
              v-model="proxyConfig.proxy" 
              class="input" 
              placeholder="user:pass@host:port"
              :disabled="isTaskActive"
            >
            <div class="form-hint">
              IP2World: <code>x_user-zone-resi-region-jp:password@host:port</code>
            </div>
          </div>
          
          <div class="form-group">
            <label class="form-label">并发数量</label>
            <div class="concurrency-control">
              <button class="btn btn-sm btn-secondary" @click="proxyConfig.concurrency = Math.max(1, proxyConfig.concurrency - 1)" :disabled="isTaskActive">-</button>
              <input 
                type="number" 
                v-model.number="proxyConfig.concurrency" 
                class="input concurrency-input" 
                min="1" 
                max="20"
                :disabled="isTaskActive"
              >
              <button class="btn btn-sm btn-secondary" @click="proxyConfig.concurrency = Math.min(20, proxyConfig.concurrency + 1)" :disabled="isTaskActive">+</button>
            </div>
            <div class="form-hint">建议 3-10，过高可能触发风控</div>
            <div v-if="isTaskActive" class="form-hint" style="color: var(--warning)">任务进行中，无法修改配置</div>
          </div>
        </div>

        <!-- 任务控制按钮 -->
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">🎮 任务控制</h3>
          </div>
          
          <div class="action-buttons">
            <!-- 开始按钮 -->
            <button 
              v-if="isStopped"
              class="btn btn-primary btn-lg btn-block"
              @click="startTask"
              :disabled="actionLoading || (taskStatus?.pending_count || 0) === 0"
            >
              <span v-if="actionLoading">处理中...</span>
              <span v-else>🚀 开始检测</span>
            </button>
            
            <!-- 运行中的控制按钮 -->
            <template v-if="isRunning">
              <button class="btn btn-warning btn-block" @click="pauseTask" :disabled="actionLoading">
                ⏸️ 暂停任务
              </button>
              <button class="btn btn-error btn-block" @click="stopTask" :disabled="actionLoading">
                ⏹️ 停止任务
              </button>
            </template>
            
            <!-- 暂停中的控制按钮 -->
            <template v-if="isPaused">
              <button class="btn btn-success btn-block" @click="resumeTask" :disabled="actionLoading">
                ▶️ 恢复任务
              </button>
              <button class="btn btn-error btn-block" @click="stopTask" :disabled="actionLoading">
                ⏹️ 停止任务
              </button>
            </template>
          </div>
          
          <div v-if="(taskStatus?.pending_count || 0) === 0 && isStopped" class="empty-hint">
            暂无待检测账号，请先导入账号
          </div>
        </div>
      </div>

      <!-- 右侧：日志显示 -->
      <div class="task-logs">
        <div class="card log-card">
          <div class="card-header">
            <h3 class="card-title">📋 运行日志</h3>
            <div class="log-controls">
              <label class="checkbox-label">
                <input type="checkbox" v-model="autoScroll">
                <span>自动滚动</span>
              </label>
              <button class="btn btn-sm btn-secondary" @click="clearLogs">清空</button>
            </div>
          </div>
          
          <div class="log-container" ref="logContainer">
            <div v-if="logs.length === 0" class="log-empty">
              暂无日志，开始任务后将显示检测日志
            </div>
            <div v-else class="log-list">
              <div 
                v-for="(log, idx) in logs" 
                :key="idx" 
                class="log-item"
                :class="'log-' + log.level"
              >
                <span class="log-time">{{ log.time }}</span>
                <span class="log-level">{{ log.level.toUpperCase() }}</span>
                <span class="log-message">{{ log.message }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `,
  methods: {
    async fetchStatus() {
      this.loading = true
      try {
        const res = await API.getTaskStatus()
        if (res.success) {
          this.taskStatus = res.data
        }
      } catch (e) {
        console.error('获取状态失败:', e)
      }
      this.loading = false
    },
    async fetchLogs() {
      // 防止并发请求
      if (this.fetchingLogs) return
      this.fetchingLogs = true
      
      try {
        const res = await API.getTaskLogs(this.lastServerLogId)
        if (res.success && res.data.length > 0) {
          // 过滤掉已存在的日志（根据 id 去重）
          const existingIds = new Set(this.logs.filter(l => l.isServer).map(l => l.id))
          const newLogs = res.data.filter(log => !existingIds.has(log.id))
          
          if (newLogs.length > 0) {
            // 标记为服务器日志并添加
            const serverLogs = newLogs.map(log => ({ ...log, isServer: true }))
            this.logs.push(...serverLogs)
            
            // 更新最后的服务器日志 id
            const lastLog = res.data[res.data.length - 1]
            if (lastLog && lastLog.id) {
              this.lastServerLogId = lastLog.id
            }
            
            // 限制日志数量
            if (this.logs.length > this.maxLogs) {
              this.logs = this.logs.slice(-this.maxLogs)
            }
            // 自动滚动
            if (this.autoScroll) {
              this.$nextTick(() => {
                const container = this.$refs.logContainer
                if (container) {
                  container.scrollTop = container.scrollHeight
                }
              })
            }
          }
        }
      } catch (e) {
        console.error('获取日志失败:', e)
      } finally {
        this.fetchingLogs = false
      }
    },
    async startTask() {
      this.actionLoading = true
      try {
        // 清空前端日志和重置服务器日志 id
        this.logs = []
        this.lastServerLogId = 0
        
        const res = await API.startTask({
          proxy: this.proxyConfig.proxy || undefined,
          concurrency: this.proxyConfig.concurrency
        })
        if (res.success) {
          Toast.success('任务已启动')
          this.addLocalLog('info', '任务已启动，并发数: ' + this.proxyConfig.concurrency)
          this.fetchStatus()
        } else {
          Toast.error(res.message)
        }
      } catch (e) {
        Toast.error('启动失败: ' + e.message)
      }
      this.actionLoading = false
    },
    async pauseTask() {
      this.actionLoading = true
      try {
        const res = await API.pauseTask()
        if (res.success) {
          Toast.success('任务已暂停')
          this.addLocalLog('warning', '任务已暂停')
          this.fetchStatus()
        } else {
          Toast.error(res.message)
        }
      } catch (e) {
        Toast.error('暂停失败: ' + e.message)
      }
      this.actionLoading = false
    },
    async resumeTask() {
      this.actionLoading = true
      try {
        const res = await API.resumeTask()
        if (res.success) {
          Toast.success('任务已恢复')
          this.addLocalLog('info', '任务已恢复运行')
          this.fetchStatus()
        } else {
          Toast.error(res.message)
        }
      } catch (e) {
        Toast.error('恢复失败: ' + e.message)
      }
      this.actionLoading = false
    },
    async stopTask() {
      const confirmed = await Modal.confirm('确定要停止当前检测任务吗？', '停止任务')
      if (!confirmed) return
      
      this.actionLoading = true
      try {
        const res = await API.stopTask()
        if (res.success) {
          Toast.success('任务已停止')
          this.addLocalLog('error', '任务已停止')
          this.fetchStatus()
        } else {
          Toast.error(res.message)
        }
      } catch (e) {
        Toast.error('停止失败: ' + e.message)
      }
      this.actionLoading = false
    },
    
    // 重置所有账号状态
    async confirmResetStatus() {
      const count = this.taskStatus?.total_count || 0
      const confirmed = await Modal.warning(
        `确定要将所有 <strong>${count}</strong> 个账号的状态重置为"待检测"吗？<br><br>此操作将：<br>• 清除所有已检测的状态（正常、冻结、改密等）<br>• 所有账号需要重新检测<br><br><span style="color:#ef4444">此操作不可撤销！</span>`,
        '重置状态'
      )
      if (!confirmed) return
      
      this.actionLoading = true
      try {
        const res = await API.resetAllAccountsStatus()
        if (res.success) {
          Toast.success(res.message || '状态已重置')
          this.addLocalLog('warning', `已重置 ${count} 个账号的状态`)
          this.fetchStatus()
        } else {
          Toast.error(res.message)
        }
      } catch (e) {
        Toast.error('重置失败: ' + e.message)
      }
      this.actionLoading = false
    },
    
    // 清空所有账号
    async confirmClearAccounts() {
      const count = this.taskStatus?.total_count || 0
      
      // 第一次确认
      const firstConfirm = await Modal.danger(
        `确定要删除所有 <strong>${count}</strong> 个账号吗？<br><br>此操作将 <strong>永久删除</strong> 所有账号数据！<br><br><span style="color:#ef4444;font-weight:bold">此操作不可撤销！</span>`,
        '危险操作'
      )
      if (!firstConfirm) return
      
      // 二次确认
      const secondConfirm = await Modal.show({
        title: '🚨 最后确认',
        message: `真的要删除全部 <strong style="color:#ef4444">${count}</strong> 个账号吗？<br><br>点击 "确认删除" 将永久清空数据`,
        type: 'danger',
        dangerous: true,
        confirmText: '确认删除',
        cancelText: '取消'
      })
      if (!secondConfirm) return

      this.actionLoading = true
      try {
        const res = await API.clearAllAccounts()
        if (res.success) {
          Toast.success(res.message || '账号已清空')
          this.addLocalLog('error', `已删除所有 ${count} 个账号`)
          this.fetchStatus()
        } else {
          Toast.error(res.message)
        }
      } catch (e) {
        Toast.error('清空失败: ' + e.message)
      }
      this.actionLoading = false
    },
    
    addLocalLog(level, message) {
      const now = new Date()
      const time = now.toLocaleTimeString('zh-CN', { hour12: false })
      this.logs.push({
        id: Date.now(),
        time,
        level,
        message
      })
    },
    clearLogs() {
      this.logs = []
      this.lastServerLogId = 0
    },
    startPolling() {
      // 先停止现有轮询，避免重复
      this.stopPolling()
      // 每 1 秒轮询一次状态和日志
      this.pollTimer = setInterval(() => {
        this.fetchStatus()
        this.fetchLogs()
      }, 1000)
    },
    stopPolling() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer)
        this.pollTimer = null
      }
    },
    // 从服务器加载配置
    async loadConfig() {
      try {
        // 从服务器加载代理和并发配置
        const res = await API.getTaskConfig()
        if (res.success && res.data) {
          this.proxyConfig.proxy = res.data.proxy || ''
          this.proxyConfig.concurrency = res.data.concurrency || 5
        }
        
        // 从 localStorage 加载 autoScroll（仅本地设置）
        const saved = localStorage.getItem('task_autoscroll')
        if (saved !== null) {
          this.autoScroll = saved === 'true'
        }
      } catch (e) {
        console.warn('加载任务配置失败:', e)
      }
    },
    // 保存配置到服务器
    async saveConfigToServer() {
      // 避免任务运行时保存
      if (this.isTaskActive) return
      
      try {
        await API.saveTaskConfig({
          proxy: this.proxyConfig.proxy,
          concurrency: this.proxyConfig.concurrency
        })
      } catch (e) {
        console.warn('保存任务配置失败:', e)
      }
    },
    // 保存 autoScroll 到本地
    saveAutoScroll() {
      localStorage.setItem('task_autoscroll', this.autoScroll.toString())
    }
  },
  watch: {
    'proxyConfig.proxy'() { this.saveConfigToServer() },
    'proxyConfig.concurrency'() { this.saveConfigToServer() },
    'autoScroll'() { this.saveAutoScroll() }
  },
  async mounted() {
    await this.loadConfig()
    this.fetchStatus()
    // 不单独调用 fetchLogs，由 startPolling 统一处理
    this.startPolling()
  },
  beforeUnmount() {
    this.stopPolling()
  }
}

// 页面专用样式
const taskStyles = `
  .task-layout {
    display: flex;
    gap: 20px;
  }
  
  .task-control {
    width: 400px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  
  .task-logs {
    flex: 1;
    min-width: 0;
  }
  
  .status-card { }
  .status-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }
  .status-actions {
    display: flex;
    gap: 8px;
  }
  .danger-actions {
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
    padding-top: 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.1);
  }
  .danger-actions .btn {
    flex: 1;
  }
  .status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 0.85rem;
    font-weight: 500;
  }
  .status-badge .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }
  .status-idle { background: var(--bg-secondary); color: var(--text-muted); }
  .status-idle .status-dot { background: var(--text-muted); }
  .status-running { background: var(--success-bg); color: var(--success); }
  .status-running .status-dot { background: var(--success); animation: pulse 1s ease-in-out infinite; }
  .status-paused { background: var(--warning-bg); color: var(--warning); }
  .status-paused .status-dot { background: var(--warning); }
  .status-stopped, .status-completed { background: var(--bg-secondary); color: var(--text-secondary); }
  .status-stopped .status-dot, .status-completed .status-dot { background: var(--text-secondary); }
  
  .status-stats {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 8px;
    margin-bottom: 16px;
  }
  .stat-item {
    text-align: center;
    padding: 10px 4px;
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
  }
  .stat-item .stat-value {
    font-size: 1.2rem;
    font-weight: 700;
    font-family: var(--font-mono);
  }
  .stat-item .stat-label {
    font-size: 0.7rem;
    color: var(--text-muted);
    margin-top: 2px;
  }
  
  .progress-section { }
  .progress-info {
    display: flex;
    justify-content: space-between;
    font-size: 0.8rem;
    color: var(--text-secondary);
    margin-bottom: 6px;
  }
  
  .concurrency-control {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .concurrency-input {
    width: 60px;
    text-align: center;
  }
  
  .action-buttons {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .btn-block { width: 100%; }
  .btn-warning { background: var(--warning); color: white; }
  .btn-warning:hover { background: #d97706; }
  .btn-error { background: var(--error); color: white; }
  .btn-error:hover { background: #dc2626; }
  .btn-success { background: var(--success); color: white; }
  .btn-success:hover { background: #16a34a; }
  
  .empty-hint {
    text-align: center;
    padding: 16px;
    color: var(--text-muted);
    font-size: 0.85rem;
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
    margin-top: 12px;
  }
  
  .log-card {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .log-card .card-header {
    flex-shrink: 0;
  }
  
  .log-controls {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  
  .log-container {
    flex: 1;
    overflow-y: auto;
    background: #0d0d12;
    border-radius: var(--radius-md);
    padding: 12px;
    font-family: var(--font-mono);
    font-size: 0.75rem;
    line-height: 1.6;
    max-height: 500px;
    min-height: 300px;
  }
  
  .log-empty {
    color: var(--text-muted);
    text-align: center;
    padding: 40px;
  }
  
  .log-item {
    display: flex;
    gap: 8px;
    padding: 2px 0;
  }
  .log-time { color: var(--text-muted); flex-shrink: 0; }
  .log-level { 
    width: 50px; 
    flex-shrink: 0;
    font-weight: 600;
  }
  .log-message { color: var(--text-primary); word-break: break-all; }
  
  .log-info .log-level { color: var(--info); }
  .log-success .log-level { color: var(--success); }
  .log-warning .log-level { color: var(--warning); }
  .log-error .log-level { color: var(--error); }
  .log-debug .log-level { color: var(--text-muted); }
  
  @media (max-width: 1200px) {
    .task-layout {
      flex-direction: column;
    }
    .task-control {
      width: 100%;
    }
    .log-container {
      max-height: 400px;
    }
  }
  
  @media (max-width: 900px) {
    .status-stats {
      grid-template-columns: repeat(3, 1fr);
    }
  }
  @media (max-width: 600px) {
    .status-stats {
      grid-template-columns: repeat(2, 1fr);
    }
  }
`

const taskStyleEl = document.createElement('style')
taskStyleEl.textContent = taskStyles
document.head.appendChild(taskStyleEl)

window.TaskPage = TaskPage

