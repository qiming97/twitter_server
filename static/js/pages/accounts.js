/**
 * 账号列表页面
 */
const AccountsPage = {
  components: {
    'loading-spinner': Components.LoadingComponent,
    'empty-state': Components.EmptyStateComponent,
    'pagination': Components.PaginationComponent,
    'status-tag': Components.StatusTagComponent
  },
  props: ['stats'],
  data() {
    return {
      filter: {
        type: 'status',
        status: '正常',
        country: '',
        minFollowers: 0,
        maxFollowers: 999999999,
        isExtracted: ''  // '', 'true', 'false'
      },
      accounts: [],
      total: 0,
      page: 1,
      loading: false,
      // 批量选择
      selectedIds: [],
      // 删除确认
      showDeleteConfirm: false,
      deleteTarget: null,  // null: 批量删除, {id, username}: 单个删除
      deleting: false
    }
  },
  computed: {
    countries() {
      return this.stats?.by_country || []
    },
    // 是否全选
    isAllSelected() {
      return this.accounts.length > 0 && this.selectedIds.length === this.accounts.length
    },
    // 是否有选中项
    hasSelection() {
      return this.selectedIds.length > 0
    },
    // 选中的账号列表
    selectedAccounts() {
      return this.accounts.filter(acc => this.selectedIds.includes(acc.id))
    }
  },
  template: `
    <div>
      <!-- 筛选区域 -->
      <div class="card filter-card">
        <div class="filter-tabs">
          <button class="option-btn" :class="{ active: filter.type === 'status' }" @click="setFilterType('status')">📊 按状态</button>
          <button class="option-btn" :class="{ active: filter.type === 'country' }" @click="setFilterType('country')">🌍 按国家</button>
          <button class="option-btn" :class="{ active: filter.type === 'followers' }" @click="setFilterType('followers')">👥 按粉丝</button>
        </div>
        
        <!-- 状态筛选 -->
        <div class="option-group" v-if="filter.type === 'status'">
          <button 
            v-for="s in ['正常', '冻结', '改密', '错误', '待检测']" 
            :key="s" 
            class="option-btn" 
            :class="{ active: filter.status === s }" 
            @click="filter.status = s; fetchAccounts()"
          >{{ s }}</button>
        </div>
        
        <!-- 国家筛选 -->
        <div class="option-group" v-if="filter.type === 'country'">
          <button 
            v-for="item in countries.slice(0, 12)" 
            :key="item.country" 
            class="option-btn" 
            :class="{ active: filter.country === item.country }" 
            @click="filter.country = item.country; fetchAccounts()"
          >{{ item.country || '未知' }} ({{ item.count }})</button>
        </div>
        
        <!-- 粉丝筛选 -->
        <div class="option-group" v-if="filter.type === 'followers'">
          <button 
            v-for="r in followerRanges" 
            :key="r.label" 
            class="option-btn" 
            :class="{ active: filter.minFollowers === r.min && filter.maxFollowers === r.max }" 
            @click="filter.minFollowers = r.min; filter.maxFollowers = r.max; fetchAccounts()"
          >{{ r.label }}</button>
        </div>
        
        <!-- 是否提取过筛选 -->
        <div class="extract-filter">
          <label class="form-label" style="margin-right: 10px; margin-bottom: 0;">是否提取过:</label>
          <select class="input" style="width: 150px;" v-model="filter.isExtracted" @change="fetchAccounts()">
            <option value="">全部</option>
            <option value="false">未提取</option>
            <option value="true">已提取</option>
          </select>
        </div>
      </div>

      <!-- 批量操作栏 -->
      <div class="card batch-actions" v-if="hasSelection">
        <div class="batch-info">
          <span class="selected-count">已选择 <strong>{{ selectedIds.length }}</strong> 个账号</span>
          <button class="btn btn-sm btn-ghost" @click="clearSelection">取消选择</button>
        </div>
        <div class="batch-buttons">
          <button class="btn btn-sm btn-primary" @click="copySelectedAccounts">
            📋 复制选中
          </button>
          <button class="btn btn-sm btn-danger" @click="confirmBatchDelete">
            🗑️ 删除选中
          </button>
        </div>
      </div>

      <!-- 账号列表 -->
      <div class="card" style="padding: 0;">
        <div class="card-header" style="padding: 16px 20px; margin-bottom: 0;">
          <h3 class="card-title">
            👥 账号列表 
            <span style="font-size: 0.8rem; font-weight: 400; color: var(--text-muted); margin-left: 6px;">共 {{ total }} 个</span>
          </h3>
        </div>
        
        <loading-spinner v-if="loading" />
        
        <template v-else-if="accounts.length">
          <div class="table-container">
            <table class="table">
              <thead>
                <tr>
                  <th class="checkbox-col">
                    <input 
                      type="checkbox" 
                      :checked="isAllSelected" 
                      @change="toggleSelectAll"
                      class="checkbox"
                    />
                  </th>
                  <th>用户名</th>
                  <th>粉丝</th>
                  <th>关注</th>
                  <th>国家</th>
                  <th>年份</th>
                  <th>会员</th>
                  <th>状态</th>
                  <th>状态信息</th>
                  <th>已提取</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="acc in accounts" :key="acc.id" :class="{ 'row-selected': selectedIds.includes(acc.id) }">
                  <td class="checkbox-col">
                    <input 
                      type="checkbox" 
                      :checked="selectedIds.includes(acc.id)" 
                      @change="toggleSelect(acc.id)"
                      class="checkbox"
                    />
                  </td>
                  <td>
                    <a :href="'https://x.com/' + acc.username" target="_blank" class="username-link">@{{ acc.username }}</a>
                    <a :href="'https://x.com/' + acc.username" target="_blank" class="profile-link" title="打开主页">🔗</a>
                  </td>
                  <td class="mono">{{ (acc.follower_count || 0).toLocaleString() }}</td>
                  <td class="mono">{{ (acc.following_count || 0).toLocaleString() }}</td>
                  <td>{{ acc.country || '-' }}</td>
                  <td>{{ acc.create_year || '-' }}</td>
                  <td><span class="tag" :class="acc.is_premium ? 'tag-success' : ''">{{ acc.is_premium ? '✓' : '-' }}</span></td>
                  <td><status-tag :status="acc.status" /></td>
                  <td class="status-msg" :title="acc.status_message || ''">{{ acc.status_message || '-' }}</td>
                  <td><span class="tag" :class="acc.is_extracted ? 'tag-info' : ''">{{ acc.is_extracted ? '已提取' : '-' }}</span></td>
                  <td class="action-col">
                    <button class="btn btn-sm btn-secondary" @click="copyAccount(acc)" title="复制">📋</button>
                    <button class="btn btn-sm btn-danger-outline" @click="confirmDeleteSingle(acc)" title="删除">🗑️</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          
          <pagination 
            :page="page" 
            :total="total" 
            :page-size="50" 
            @update:page="page = $event; fetchAccounts()" 
          />
        </template>
        
        <empty-state v-else icon="📭" title="暂无数据" />
      </div>

      <!-- 删除确认弹窗 -->
      <div class="modal-overlay" v-if="showDeleteConfirm" @click.self="cancelDelete">
        <div class="modal">
          <div class="modal-header">
            <h3>⚠️ 确认删除</h3>
          </div>
          <div class="modal-body">
            <p v-if="deleteTarget">
              确定要删除账号 <strong>@{{ deleteTarget.username }}</strong> 吗？
            </p>
            <p v-else>
              确定要删除选中的 <strong>{{ selectedIds.length }}</strong> 个账号吗？
            </p>
            <p class="warning-text">此操作不可撤销！</p>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="cancelDelete" :disabled="deleting">取消</button>
            <button class="btn btn-danger" @click="executeDelete" :disabled="deleting">
              {{ deleting ? '删除中...' : '确认删除' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  `,
  methods: {
    setFilterType(type) {
      this.filter.type = type
      this.page = 1
      this.clearSelection()
      this.fetchAccounts()
    },
    async fetchAccounts() {
      this.loading = true
      this.clearSelection()
      try {
        let res
        // 构建 is_extracted 参数
        const isExtracted = this.filter.isExtracted === '' ? undefined : this.filter.isExtracted === 'true'
        
        if (this.filter.type === 'status') {
          res = await API.getAccountsByStatus(this.filter.status, this.page, 50, isExtracted)
        } else if (this.filter.type === 'country') {
          res = await API.getAccountsByCountry(this.filter.country || '未知', this.page, 50, isExtracted)
        } else {
          res = await API.getAccountsByFollowers(this.filter.minFollowers, this.filter.maxFollowers, this.page, 50, isExtracted)
        }
        this.accounts = res.items || []
        this.total = res.total || 0
      } catch (e) {
        console.error(e)
      }
      this.loading = false
    },
    // 复制单个账号
    copyAccount(acc) {
      const text = Utils.formatAccountForExport(acc)
      Utils.copyToClipboard(text)
    },
    // 批量选择相关
    toggleSelect(id) {
      const index = this.selectedIds.indexOf(id)
      if (index > -1) {
        this.selectedIds.splice(index, 1)
      } else {
        this.selectedIds.push(id)
      }
    },
    toggleSelectAll() {
      if (this.isAllSelected) {
        this.selectedIds = []
      } else {
        this.selectedIds = this.accounts.map(acc => acc.id)
      }
    },
    clearSelection() {
      this.selectedIds = []
    },
    // 复制选中的账号
    copySelectedAccounts() {
      const text = this.selectedAccounts.map(acc => Utils.formatAccountForExport(acc)).join('\n')
      Utils.copyToClipboard(text)
      Toast.success(`已复制 ${this.selectedAccounts.length} 个账号`)
    },
    // 删除确认
    confirmDeleteSingle(acc) {
      this.deleteTarget = acc
      this.showDeleteConfirm = true
    },
    confirmBatchDelete() {
      this.deleteTarget = null
      this.showDeleteConfirm = true
    },
    cancelDelete() {
      this.showDeleteConfirm = false
      this.deleteTarget = null
    },
    // 执行删除
    async executeDelete() {
      this.deleting = true
      try {
        if (this.deleteTarget) {
          // 单个删除
          const res = await API.deleteAccount(this.deleteTarget.id)
          if (res.success) {
            Toast.success('账号已删除')
            this.fetchAccounts()
            this.$emit('refresh-stats')
          } else {
            Toast.error(res.message || '删除失败')
          }
        } else {
          // 批量删除
          const res = await API.batchDeleteAccounts(this.selectedIds)
          if (res.success) {
            Toast.success(`已删除 ${res.data?.count || this.selectedIds.length} 个账号`)
            this.clearSelection()
            this.fetchAccounts()
            this.$emit('refresh-stats')
          } else {
            Toast.error(res.message || '删除失败')
          }
        }
      } catch (e) {
        console.error(e)
        Toast.error('删除失败: ' + e.message)
      }
      this.deleting = false
      this.showDeleteConfirm = false
      this.deleteTarget = null
    }
  },
  created() {
    this.followerRanges = Utils.followerRanges
  },
  mounted() {
    this.fetchAccounts()
  }
}

// 页面专用样式
const accountsStyles = `
  .filter-card {
    margin-bottom: 16px;
    padding: 16px;
  }
  .filter-tabs {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
  }
  .extract-filter {
    display: flex;
    align-items: center;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }
  .username {
    font-family: var(--font-mono);
    color: var(--primary);
  }
  .username-link {
    font-family: var(--font-mono);
    color: var(--primary);
    text-decoration: none;
    transition: color 0.2s;
  }
  .username-link:hover {
    color: var(--primary-light);
    text-decoration: underline;
  }
  .profile-link {
    margin-left: 6px;
    text-decoration: none;
    opacity: 0.6;
    transition: opacity 0.2s;
  }
  .profile-link:hover {
    opacity: 1;
  }
  .mono {
    font-family: var(--font-mono);
  }
  .tag-info {
    background: rgba(59, 130, 246, 0.15);
    color: #3b82f6;
  }
  .status-msg {
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.75rem;
    color: var(--text-secondary);
    cursor: help;
  }
  
  /* 批量操作栏 */
  .batch-actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    margin-bottom: 16px;
    background: rgba(59, 130, 246, 0.08);
    border: 1px solid rgba(59, 130, 246, 0.2);
  }
  .batch-info {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .selected-count {
    color: var(--primary);
  }
  .batch-buttons {
    display: flex;
    gap: 8px;
  }
  
  /* 复选框样式 */
  .checkbox-col {
    width: 40px;
    text-align: center;
  }
  .checkbox {
    width: 16px;
    height: 16px;
    cursor: pointer;
    accent-color: var(--primary);
  }
  .row-selected {
    background: rgba(59, 130, 246, 0.05);
  }
  
  /* 操作列 */
  .action-col {
    display: flex;
    gap: 4px;
  }
  .btn-danger-outline {
    background: transparent;
    border: 1px solid var(--danger);
    color: var(--danger);
  }
  .btn-danger-outline:hover {
    background: var(--danger);
    color: white;
  }
  
  /* 弹窗样式 */
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1000;
    backdrop-filter: blur(2px);
  }
  .modal {
    background: var(--bg-card);
    border-radius: 12px;
    min-width: 400px;
    max-width: 90%;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    animation: modalIn 0.2s ease-out;
  }
  @keyframes modalIn {
    from {
      opacity: 0;
      transform: scale(0.95) translateY(-10px);
    }
    to {
      opacity: 1;
      transform: scale(1) translateY(0);
    }
  }
  .modal-header {
    padding: 20px 24px;
    border-bottom: 1px solid var(--border);
  }
  .modal-header h3 {
    margin: 0;
    font-size: 1.1rem;
  }
  .modal-body {
    padding: 24px;
  }
  .modal-body p {
    margin: 0 0 12px 0;
    line-height: 1.6;
  }
  .warning-text {
    color: var(--danger);
    font-size: 0.9rem;
    font-weight: 500;
  }
  .modal-footer {
    padding: 16px 24px;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: flex-end;
    gap: 12px;
  }
`

const accountsStyleEl = document.createElement('style')
accountsStyleEl.textContent = accountsStyles
document.head.appendChild(accountsStyleEl)

window.AccountsPage = AccountsPage
