/**
 * 账号提取页面
 */
const ExtractPage = {
  props: {
    stats: {
      type: Object,
      default: () => ({
        extractable_count: 0,
        by_country: []
      })
    }
  },
  data() {
    return {
      form: {
        status: '正常',
        country: '',
        minFollowers: 0,
        maxFollowers: 999999999,
        limit: 100
      },
      loading: false,
      extractedAccounts: [],
      error: '',
      // 可提取数量（根据当前筛选条件）
      extractableCount: 0,
      countLoading: false
    }
  },
  computed: {
    countries() {
      return this.stats?.by_country || []
    },
    selectedRangeLabel() {
      return Utils.getRangeLabel(this.form.minFollowers, this.form.maxFollowers)
    },
    displayAccounts() {
      return this.extractedAccounts.slice(0, 20)
    },
    // 所有可用的状态选项
    statusOptions() {
      return ['正常', '冻结', '改密', '锁号', '错误', '待检测']
    }
  },
  template: `
    <div class="grid grid-2">
      <!-- 左侧：筛选条件 -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">🎯 筛选条件</h3>
        </div>
        
        <!-- 可提取提示 -->
        <div class="extractable-hint">
          <div class="extractable-icon">📦</div>
          <div class="extractable-info">
            <div class="extractable-value" :class="{ 'loading': countLoading }">
              {{ countLoading ? '...' : (extractableCount || 0).toLocaleString() }}
            </div>
            <div class="extractable-label">可提取账号</div>
          </div>
          <div class="extractable-note">当前筛选条件下未提取过的账号</div>
        </div>
        
        <!-- 状态选择 -->
        <div class="form-group">
          <label class="form-label">账号状态</label>
          <div class="option-group">
            <button 
              v-for="s in statusOptions" 
              :key="s" 
              class="option-btn" 
              :class="{ active: form.status === s }" 
              @click="form.status = s"
            >{{ s }}</button>
          </div>
        </div>
        
        <!-- 国家选择 -->
        <div class="form-group">
          <label class="form-label">国家筛选</label>
          <select v-model="form.country" class="input select">
            <option value="">全部国家</option>
            <option v-for="item in countries" :key="item.country" :value="item.country">
              {{ item.country || '未知' }} ({{ item.count }})
            </option>
          </select>
        </div>
        
        <!-- 粉丝数量 -->
        <div class="form-group">
          <label class="form-label">粉丝数量</label>
          <div class="option-group">
            <button 
              v-for="r in followerRanges" 
              :key="r.label" 
              class="option-btn" 
              :class="{ active: form.minFollowers === r.min && form.maxFollowers === r.max }" 
              @click="form.minFollowers = r.min; form.maxFollowers = r.max"
            >{{ r.label }}</button>
          </div>
          <div class="form-row">
            <input v-model.number="form.minFollowers" type="number" class="input" placeholder="最小">
            <span style="color: var(--text-muted); line-height: 36px;">-</span>
            <input v-model.number="form.maxFollowers" type="number" class="input" placeholder="最大">
          </div>
        </div>
        
        <!-- 提取数量 -->
        <div class="form-group">
          <label class="form-label">提取数量</label>
          <div class="option-group">
            <button 
              v-for="n in [50, 100, 200, 500, 1000]" 
              :key="n" 
              class="option-btn" 
              :class="{ active: form.limit === n }" 
              @click="form.limit = n"
            >{{ n }}</button>
          </div>
          <input v-model.number="form.limit" type="number" class="input" placeholder="自定义数量" min="1" max="10000">
        </div>
        
        <div v-if="error" class="error-msg">{{ error }}</div>
        
        <div class="form-actions">
          <button class="btn btn-primary btn-lg" @click="handleExtract" :disabled="loading || extractableCount === 0">
            {{ loading ? '提取中...' : '🔍 开始提取' }}
          </button>
        </div>
        
        <div v-if="extractableCount === 0" class="no-extractable">
          暂无可提取账号，请先导入并检测账号
        </div>
      </div>

      <!-- 右侧：提取结果 -->
      <div>
        <!-- 当前条件 -->
        <div class="card condition-card">
          <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 8px;">当前筛选条件</div>
          <div class="condition-list">
            <span>状态: <strong>{{ form.status }}</strong></span>
            <span v-if="form.country">国家: <strong>{{ form.country }}</strong></span>
            <span>粉丝: <strong>{{ selectedRangeLabel }}</strong></span>
            <span>数量: <strong>{{ form.limit }}</strong></span>
          </div>
        </div>

        <!-- 提取结果列表 -->
        <div class="card" v-if="extractedAccounts.length">
          <div class="card-header">
            <h3 class="card-title">
              📋 提取结果 
              <span class="extracted-badge">已标记为已提取</span>
            </h3>
            <div style="display: flex; gap: 6px;">
              <button class="btn btn-sm btn-secondary" @click="copyAllAccounts">📋 复制全部</button>
              <button class="btn btn-sm btn-secondary" @click="exportAccounts">📥 导出TXT</button>
            </div>
          </div>
          
          <div class="extracted-info">
            <span>✅ 成功提取 <strong>{{ extractedAccounts.length }}</strong> 个账号</span>
            <span class="extracted-note">这些账号已被标记，不会再次被提取</span>
          </div>
          
          <div class="result-list">
            <div v-for="(acc, idx) in displayAccounts" :key="acc.id" class="result-item">
              <div class="result-index">{{ idx + 1 }}</div>
              <div style="flex: 1;">
                <div class="result-username">@{{ acc.username }}</div>
                <div class="result-meta">
                  <span>👥 {{ (acc.follower_count || 0).toLocaleString() }}</span>
                  <span>🌍 {{ acc.country || '未知' }}</span>
                  <span>📅 {{ acc.create_year || '-' }}</span>
                  <span v-if="acc.is_premium">⭐ 会员</span>
                </div>
              </div>
            </div>
            <div v-if="extractedAccounts.length > 20" class="more-hint">
              还有 {{ extractedAccounts.length - 20 }} 个账号，请导出查看完整列表
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div class="card empty-card" v-else>
          <div style="font-size: 3rem; opacity: 0.3; margin-bottom: 12px;">📤</div>
          <div style="font-size: 1.1rem; color: var(--text-secondary); margin-bottom: 6px;">设置条件后点击提取</div>
          <p style="color: var(--text-muted); font-size: 0.85rem;">
            根据筛选条件提取符合要求的账号<br>
            <strong>注意：提取后账号会被标记，不可重复提取</strong>
          </p>
        </div>

        <!-- 导出格式说明 -->
        <div class="card" style="margin-top: 12px;">
          <div class="card-header">
            <h3 class="card-title">📄 导出格式</h3>
          </div>
          <code class="format-code">用户名----密码----2FA----邮箱----邮箱密码----粉丝数量----国家----年份----是否会员</code>
        </div>
      </div>
    </div>
  `,
  methods: {
    // 获取可提取账号数量
    async fetchExtractableCount() {
      this.countLoading = true
      try {
        const res = await API.getExtractableCount({
          status: this.form.status,
          country: this.form.country || undefined,
          min_followers: this.form.minFollowers,
          max_followers: this.form.maxFollowers
        })
        if (res.success) {
          this.extractableCount = res.data?.count || 0
        }
      } catch (e) {
        console.warn('获取可提取数量失败:', e)
      }
      this.countLoading = false
    },
    async handleExtract() {
      this.loading = true
      this.error = ''
      
      try {
        const res = await API.extractAccounts({
          country: this.form.country || undefined,
          min_followers: this.form.minFollowers,
          max_followers: this.form.maxFollowers,
          limit: this.form.limit,
          status: this.form.status
        })
        
        if (res.success) {
          this.extractedAccounts = res.data || []
          if (this.extractedAccounts.length > 0) {
            Toast.success(`成功提取 ${this.extractedAccounts.length} 个账号，已标记为已提取`)
            // 通知父组件刷新统计
            this.$emit('refresh-stats')
            // 刷新可提取数量
            this.fetchExtractableCount()
          } else {
            Toast.warning('没有找到符合条件的可提取账号')
          }
        } else {
          this.error = res.message
        }
      } catch (e) {
        this.error = e.message
      }
      
      this.loading = false
    },
    copyAllAccounts() {
      const text = this.extractedAccounts.map(acc => Utils.formatAccountForExport(acc)).join('\n')
      Utils.copyToClipboard(text)
    },
    exportAccounts() {
      const text = this.extractedAccounts.map(acc => Utils.formatAccountForExport(acc)).join('\n')
      const filename = `accounts_${new Date().toISOString().slice(0, 10)}.txt`
      Utils.downloadFile(text, filename)
      Toast.success('导出成功')
    },
    // localStorage 持久化
    loadConfig() {
      try {
        const saved = localStorage.getItem('extract_config')
        if (saved) {
          const config = JSON.parse(saved)
          if (config.status) this.form.status = config.status
          if (config.country !== undefined) this.form.country = config.country
          if (config.minFollowers !== undefined) this.form.minFollowers = config.minFollowers
          if (config.maxFollowers !== undefined) this.form.maxFollowers = config.maxFollowers
          if (config.limit !== undefined) this.form.limit = config.limit
        }
      } catch (e) {
        console.warn('加载提取配置失败:', e)
      }
    },
    saveConfig() {
      try {
        localStorage.setItem('extract_config', JSON.stringify({
          status: this.form.status,
          country: this.form.country,
          minFollowers: this.form.minFollowers,
          maxFollowers: this.form.maxFollowers,
          limit: this.form.limit
        }))
      } catch (e) {
        console.warn('保存提取配置失败:', e)
      }
    }
  },
  watch: {
    'form.status'() { 
      this.saveConfig()
      this.fetchExtractableCount()
    },
    'form.country'() { 
      this.saveConfig()
      this.fetchExtractableCount()
    },
    'form.minFollowers'() { 
      this.saveConfig()
      this.fetchExtractableCount()
    },
    'form.maxFollowers'() { 
      this.saveConfig()
      this.fetchExtractableCount()
    },
    'form.limit'() { this.saveConfig() }
  },
  created() {
    this.followerRanges = Utils.followerRanges
  },
  mounted() {
    this.loadConfig()
    // 加载配置后立即获取可提取数量
    this.fetchExtractableCount()
  }
}

// 页面专用样式
const extractStyles = `
  .extractable-hint {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 16px;
    background: linear-gradient(135deg, rgba(34, 197, 94, 0.1) 0%, rgba(6, 182, 212, 0.1) 100%);
    border: 1px solid rgba(34, 197, 94, 0.2);
    border-radius: var(--radius-md);
    margin-bottom: 20px;
  }
  .extractable-icon {
    font-size: 2rem;
  }
  .extractable-info { flex: 1; }
  .extractable-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--success);
    font-family: var(--font-mono);
    transition: opacity 0.2s;
  }
  .extractable-value.loading {
    opacity: 0.5;
  }
  .extractable-label {
    font-size: 0.8rem;
    color: var(--text-secondary);
  }
  .extractable-note {
    font-size: 0.75rem;
    color: var(--text-muted);
  }
  
  .no-extractable {
    text-align: center;
    padding: 16px;
    color: var(--text-muted);
    font-size: 0.85rem;
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
    margin-top: 12px;
  }
  
  .condition-card {
    padding: 12px 16px;
    margin-bottom: 12px;
  }
  .condition-list {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    font-size: 0.85rem;
  }
  .condition-list strong {
    color: var(--primary);
  }
  
  .extracted-badge {
    font-size: 0.7rem;
    font-weight: 500;
    padding: 2px 8px;
    background: var(--success-bg);
    color: var(--success);
    border-radius: 10px;
    margin-left: 8px;
  }
  
  .extracted-info {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px;
    background: var(--success-bg);
    border-radius: var(--radius-md);
    margin-bottom: 12px;
    font-size: 0.85rem;
  }
  .extracted-info strong {
    color: var(--success);
    font-family: var(--font-mono);
  }
  .extracted-note {
    font-size: 0.75rem;
    color: var(--text-muted);
  }
  
  .result-list {
    max-height: 400px;
    overflow-y: auto;
  }
  .more-hint {
    text-align: center;
    padding: 12px;
    color: var(--text-muted);
    font-size: 0.8rem;
    border-top: 1px solid var(--border);
  }
  .empty-card {
    padding: 50px 20px;
    text-align: center;
  }
  .format-code {
    display: block;
    padding: 10px 14px;
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--primary);
    word-break: break-all;
  }
`

const extractStyleEl = document.createElement('style')
extractStyleEl.id = 'extract-styles'
if (!document.getElementById('extract-styles')) {
  extractStyleEl.textContent = extractStyles
  document.head.appendChild(extractStyleEl)
}

window.ExtractPage = ExtractPage
