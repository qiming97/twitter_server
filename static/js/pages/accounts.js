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
      loading: false
    }
  },
  computed: {
    countries() {
      return this.stats?.by_country || []
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
                <tr v-for="acc in accounts" :key="acc.id">
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
                  <td><button class="btn btn-sm btn-secondary" @click="copyAccount(acc)">复制</button></td>
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
    </div>
  `,
  methods: {
    setFilterType(type) {
      this.filter.type = type
      this.page = 1
      this.fetchAccounts()
    },
    async fetchAccounts() {
      this.loading = true
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
    copyAccount(acc) {
      const text = Utils.formatAccountForExport(acc)
      Utils.copyToClipboard(text)
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
`

const accountsStyleEl = document.createElement('style')
accountsStyleEl.textContent = accountsStyles
document.head.appendChild(accountsStyleEl)

window.AccountsPage = AccountsPage

