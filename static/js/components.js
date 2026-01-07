/**
 * 公共 Vue 组件
 */

// 加载组件
const LoadingComponent = {
  template: `
    <div class="loading">
      <div class="loading-dot"></div>
      <div class="loading-dot"></div>
      <div class="loading-dot"></div>
    </div>
  `
}

// 空状态组件
const EmptyStateComponent = {
  props: {
    icon: { type: String, default: '📭' },
    title: { type: String, default: '暂无数据' },
    description: { type: String, default: '' }
  },
  template: `
    <div class="empty-state">
      <div class="icon">{{ icon }}</div>
      <div class="title">{{ title }}</div>
      <p v-if="description">{{ description }}</p>
    </div>
  `
}

// 统计卡片组件
const StatCardComponent = {
  props: {
    icon: String,
    value: [Number, String],
    label: String,
    color: { type: String, default: 'var(--primary)' }
  },
  template: `
    <div class="stat-card" :style="{ '--status-color': color }">
      <div class="stat-icon">{{ icon }}</div>
      <div>
        <div class="stat-value" :style="{ color: color }">{{ formatValue(value) }}</div>
        <div class="stat-label">{{ label }}</div>
      </div>
    </div>
  `,
  methods: {
    formatValue(val) {
      if (typeof val === 'number') {
        return val.toLocaleString()
      }
      return val
    }
  }
}

// 分页组件
const PaginationComponent = {
  props: {
    page: { type: Number, default: 1 },
    total: { type: Number, default: 0 },
    pageSize: { type: Number, default: 50 }
  },
  emits: ['update:page'],
  computed: {
    totalPages() {
      return Math.ceil(this.total / this.pageSize) || 1
    }
  },
  template: `
    <div class="pagination">
      <button class="btn btn-sm btn-secondary" :disabled="page === 1" @click="$emit('update:page', page - 1)">上一页</button>
      <span class="page-info">第 {{ page }} / {{ totalPages }} 页</span>
      <button class="btn btn-sm btn-secondary" :disabled="page >= totalPages" @click="$emit('update:page', page + 1)">下一页</button>
    </div>
  `
}

// 状态标签组件
const StatusTagComponent = {
  props: {
    status: String
  },
  computed: {
    tagClass() {
      const map = {
        '正常': 'tag-success',
        '冻结': 'tag-error',
        '改密': 'tag-warning',
        '待检测': 'tag-info',
        '错误': 'tag-purple',
        '不存在': 'tag-error'
      }
      return map[this.status] || ''
    }
  },
  template: `<span class="tag" :class="tagClass">{{ status }}</span>`
}

// 进度条组件
const ProgressBarComponent = {
  props: {
    value: { type: Number, default: 0 },
    max: { type: Number, default: 100 }
  },
  computed: {
    percent() {
      return this.max > 0 ? (this.value / this.max * 100) : 0
    }
  },
  template: `
    <div>
      <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 6px; display: flex; justify-content: space-between;">
        <span>处理进度</span>
        <span>{{ value }} / {{ max }}</span>
      </div>
      <div class="progress">
        <div class="progress-bar" :style="{ width: percent + '%' }"></div>
      </div>
    </div>
  `
}

// Toast 提示（自定义样式）
const Toast = {
  container: null,
  
  init() {
    if (!this.container) {
      this.container = document.createElement('div')
      this.container.className = 'toast-container'
      document.body.appendChild(this.container)
    }
  },
  
  show(message, type = 'info', duration = 3000) {
    this.init()
    
    const toast = document.createElement('div')
    toast.className = `custom-toast custom-toast-${type}`
    
    const icons = {
      success: '✓',
      error: '✕',
      warning: '⚠',
      info: 'ℹ'
    }
    
    toast.innerHTML = `
      <span class="toast-icon">${icons[type] || icons.info}</span>
      <span class="toast-message">${message}</span>
    `
    
    this.container.appendChild(toast)
    
    // 触发动画
    requestAnimationFrame(() => {
      toast.classList.add('show')
    })
    
    setTimeout(() => {
      toast.classList.remove('show')
      toast.classList.add('hide')
      setTimeout(() => toast.remove(), 300)
    }, duration)
  },
  
  success(msg) { this.show(msg, 'success') },
  error(msg) { this.show(msg, 'error') },
  warning(msg) { this.show(msg, 'warning') },
  info(msg) { this.show(msg, 'info') }
}

// 自定义确认弹窗
const Modal = {
  show(options) {
    return new Promise((resolve) => {
      const {
        title = '提示',
        message = '',
        type = 'info', // info, warning, error, danger
        confirmText = '确定',
        cancelText = '取消',
        showCancel = true,
        dangerous = false
      } = options
      
      const overlay = document.createElement('div')
      overlay.className = 'modal-overlay'
      
      const icons = {
        info: '💡',
        warning: '⚠️',
        error: '❌',
        danger: '🚨',
        success: '✅'
      }
      
      const typeClass = dangerous ? 'danger' : type
      
      overlay.innerHTML = `
        <div class="modal-container modal-${typeClass}">
          <div class="modal-header">
            <span class="modal-icon">${icons[type] || icons.info}</span>
            <h3 class="modal-title">${title}</h3>
          </div>
          <div class="modal-body">
            <p class="modal-message">${message.replace(/\n/g, '<br>')}</p>
          </div>
          <div class="modal-footer">
            ${showCancel ? `<button class="btn btn-secondary modal-cancel">${cancelText}</button>` : ''}
            <button class="btn ${dangerous ? 'btn-error' : 'btn-primary'} modal-confirm">${confirmText}</button>
          </div>
        </div>
      `
      
      document.body.appendChild(overlay)
      
      // 触发动画
      requestAnimationFrame(() => {
        overlay.classList.add('show')
      })
      
      const close = (result) => {
        overlay.classList.remove('show')
        setTimeout(() => overlay.remove(), 200)
        resolve(result)
      }
      
      // 事件绑定
      overlay.querySelector('.modal-confirm').addEventListener('click', () => close(true))
      if (showCancel) {
        overlay.querySelector('.modal-cancel').addEventListener('click', () => close(false))
      }
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay && showCancel) close(false)
      })
      
      // ESC 关闭
      const handleEsc = (e) => {
        if (e.key === 'Escape' && showCancel) {
          close(false)
          document.removeEventListener('keydown', handleEsc)
        }
      }
      document.addEventListener('keydown', handleEsc)
    })
  },
  
  // 快捷方法
  confirm(message, title = '确认') {
    return this.show({ title, message, type: 'warning', showCancel: true })
  },
  
  alert(message, title = '提示') {
    return this.show({ title, message, type: 'info', showCancel: false })
  },
  
  warning(message, title = '警告') {
    return this.show({ title, message, type: 'warning', showCancel: true })
  },
  
  danger(message, title = '危险操作') {
    return this.show({ title, message, type: 'danger', dangerous: true, showCancel: true })
  }
}

// 工具函数
const Utils = {
  // 复制到剪贴板
  async copyToClipboard(text) {
    try {
      await navigator.clipboard.writeText(text)
      Toast.success('已复制到剪贴板')
      return true
    } catch (e) {
      Toast.error('复制失败')
      return false
    }
  },

  // 下载文件
  downloadFile(content, filename) {
    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  },

  // 格式化账号为导出文本
  formatAccountForExport(acc) {
    const premium = acc.is_premium ? '会员' : '普通用户'
    return `${acc.username}----${acc.password || ''}----${acc.two_fa || ''}----${acc.ct0 || ''}----${acc.auth_token || ''}----${acc.email || ''}----${acc.email_password || ''}----${acc.follower_count || 0}----${acc.country || ''}----${acc.create_year || ''}----${premium}`
  },

  // 粉丝数量区间选项
  followerRanges: [
    { label: '全部', min: 0, max: 999999999 },
    { label: '0-9', min: 0, max: 9 },
    { label: '10-99', min: 10, max: 99 },
    { label: '100-999', min: 100, max: 999 },
    { label: '1K-10K', min: 1000, max: 9999 },
    { label: '10K-100K', min: 10000, max: 99999 },
    { label: '100K+', min: 100000, max: 999999999 }
  ],

  // 获取区间标签
  getRangeLabel(min, max) {
    const r = this.followerRanges.find(r => r.min === min && r.max === max)
    return r ? r.label : '自定义'
  }
}

// 导出
window.Components = {
  LoadingComponent,
  EmptyStateComponent,
  StatCardComponent,
  PaginationComponent,
  StatusTagComponent,
  ProgressBarComponent
}
window.Toast = Toast
window.Modal = Modal
window.Utils = Utils

// 注入 Modal 和 Toast 样式
const modalStyles = document.createElement('style')
modalStyles.textContent = `
  /* Toast 容器 */
  .toast-container {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 10000;
    display: flex;
    flex-direction: column;
    gap: 10px;
    pointer-events: none;
  }
  
  /* Toast 样式 */
  .custom-toast {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 20px;
    border-radius: 8px;
    background: #1a1a2e;
    border: 1px solid rgba(255,255,255,0.1);
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    color: #fff;
    font-size: 0.9rem;
    opacity: 0;
    transform: translateX(100%);
    transition: all 0.3s ease;
    pointer-events: auto;
  }
  
  .custom-toast.show {
    opacity: 1;
    transform: translateX(0);
  }
  
  .custom-toast.hide {
    opacity: 0;
    transform: translateX(100%);
  }
  
  .custom-toast-success {
    border-color: #10b981;
    background: linear-gradient(135deg, rgba(16,185,129,0.15), rgba(16,185,129,0.05));
  }
  .custom-toast-success .toast-icon { color: #10b981; }
  
  .custom-toast-error {
    border-color: #ef4444;
    background: linear-gradient(135deg, rgba(239,68,68,0.15), rgba(239,68,68,0.05));
  }
  .custom-toast-error .toast-icon { color: #ef4444; }
  
  .custom-toast-warning {
    border-color: #f59e0b;
    background: linear-gradient(135deg, rgba(245,158,11,0.15), rgba(245,158,11,0.05));
  }
  .custom-toast-warning .toast-icon { color: #f59e0b; }
  
  .custom-toast-info {
    border-color: #3b82f6;
    background: linear-gradient(135deg, rgba(59,130,246,0.15), rgba(59,130,246,0.05));
  }
  .custom-toast-info .toast-icon { color: #3b82f6; }
  
  .toast-icon {
    font-size: 1.2rem;
    font-weight: bold;
  }
  
  /* Modal 遮罩 */
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0,0,0,0.7);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10001;
    opacity: 0;
    transition: opacity 0.2s ease;
  }
  
  .modal-overlay.show {
    opacity: 1;
  }
  
  .modal-overlay.show .modal-container {
    transform: scale(1);
    opacity: 1;
  }
  
  /* Modal 容器 */
  .modal-container {
    background: #16161e;
    border-radius: 16px;
    padding: 0;
    max-width: 420px;
    width: 90%;
    box-shadow: 0 25px 50px rgba(0,0,0,0.5);
    border: 1px solid rgba(255,255,255,0.1);
    transform: scale(0.9);
    opacity: 0;
    transition: all 0.2s ease;
    overflow: hidden;
  }
  
  .modal-header {
    padding: 24px 24px 16px;
    display: flex;
    align-items: center;
    gap: 12px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
  }
  
  .modal-icon {
    font-size: 1.5rem;
  }
  
  .modal-title {
    font-size: 1.1rem;
    font-weight: 600;
    color: #fff;
    margin: 0;
  }
  
  .modal-body {
    padding: 20px 24px;
  }
  
  .modal-message {
    color: rgba(255,255,255,0.8);
    font-size: 0.95rem;
    line-height: 1.6;
    margin: 0;
  }
  
  .modal-footer {
    padding: 16px 24px 24px;
    display: flex;
    justify-content: flex-end;
    gap: 12px;
  }
  
  .modal-footer .btn {
    min-width: 80px;
    padding: 10px 20px;
  }
  
  /* Modal 类型样式 */
  .modal-warning .modal-header {
    background: linear-gradient(135deg, rgba(245,158,11,0.1), transparent);
  }
  
  .modal-danger .modal-header {
    background: linear-gradient(135deg, rgba(239,68,68,0.15), transparent);
  }
  
  .modal-danger .modal-title {
    color: #ef4444;
  }
  
  .modal-info .modal-header {
    background: linear-gradient(135deg, rgba(59,130,246,0.1), transparent);
  }
`
document.head.appendChild(modalStyles)

