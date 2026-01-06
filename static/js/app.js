/**
 * 主应用入口 - 使用 Vue Router
 */
const { createApp, ref, computed, onMounted, watch, provide } = Vue
const { createRouter, createWebHistory, useRoute, useRouter } = VueRouter

// 定义路由
const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: 'dashboard', component: DashboardPage, meta: { title: '数据总览' } },
  { path: '/import', name: 'import', component: ImportPage, meta: { title: '账号导入' } },
  { path: '/task', name: 'task', component: TaskPage, meta: { title: '任务管理' } },
  { path: '/accounts', name: 'accounts', component: AccountsPage, meta: { title: '账号列表' } },
  { path: '/extract', name: 'extract', component: ExtractPage, meta: { title: '账号提取' } }
]

// 创建路由实例
const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫 - 更新页面标题
router.beforeEach((to, from, next) => {
  document.title = `${to.meta.title || 'Twitter'} - 账号管理`
  next()
})

const App = {
  setup() {
    const route = useRoute()
    const routerInstance = useRouter()
    
    // 当前页面标题
    const pageTitle = computed(() => route.meta.title || '')
    
    // 当前路由名称
    const currentRoute = computed(() => route.name)
    
    // 统计数据（用于多个页面共享）
    const stats = ref({
      total: 0,
      pending_count: 0,
      checked_count: 0,
      extracted_count: 0,
      extractable_count: 0,
      by_status: {},
      by_country: [],
      by_follower_range: []
    })
    
    // 获取统计数据
    const fetchStats = async () => {
      try {
        stats.value = await API.getStatistics()
      } catch (e) {
        console.error('获取统计数据失败:', e)
      }
    }
    
    // 导航到指定页面
    const navigate = (name) => {
      routerInstance.push({ name })
    }
    
    // 监听路由变化刷新统计
    watch(() => route.name, (newName) => {
      if (['dashboard', 'accounts', 'extract'].includes(newName)) {
        fetchStats()
      }
    })
    
    // 初始化
    onMounted(() => {
      fetchStats()
    })
    
    return {
      currentRoute,
      pageTitle,
      stats,
      navigate,
      fetchStats
    }
  },
  template: `
    <div class="app-layout">
      <!-- 侧边栏 -->
      <aside class="sidebar">
        <div class="sidebar-header">
          <div class="logo">
            <span class="logo-icon">𝕏</span>
            <span class="logo-text">账号管理</span>
          </div>
        </div>
        <nav class="sidebar-nav">
          <router-link to="/dashboard" class="nav-item" :class="{ active: currentRoute === 'dashboard' }">
            <span>📊</span> 数据总览
          </router-link>
          <router-link to="/import" class="nav-item" :class="{ active: currentRoute === 'import' }">
            <span>📥</span> 账号导入
          </router-link>
          <router-link to="/task" class="nav-item" :class="{ active: currentRoute === 'task' }">
            <span>🚀</span> 任务管理
          </router-link>
          <router-link to="/accounts" class="nav-item" :class="{ active: currentRoute === 'accounts' }">
            <span>👥</span> 账号列表
          </router-link>
          <router-link to="/extract" class="nav-item" :class="{ active: currentRoute === 'extract' }">
            <span>📤</span> 账号提取
          </router-link>
        </nav>
      </aside>

      <!-- 主内容区 -->
      <main class="main-content">
        <header class="page-header">
          <h1 class="page-title">{{ pageTitle }}</h1>
          <div class="status-indicator">
            <span class="status-dot"></span>
            服务运行中
          </div>
        </header>

        <div class="page-content">
          <router-view v-slot="{ Component, route }">
            <component 
              :is="Component" 
              :stats="stats" 
              @navigate="navigate"
              @refresh-stats="fetchStats"
            />
          </router-view>
        </div>
      </main>
    </div>
  `
}

// 创建并挂载应用
const app = createApp(App)
app.use(router)
app.mount('#app')
