/**
 * 账号导入页面 - 支持 Excel 文件导入
 */
const ImportPage = {
  data() {
    return {
      // 导入模式: 'file' 或 'text'
      importMode: 'file',
      // 文件相关
      isDragging: false,
      selectedFile: null,
      // 解析后的账号数据
      parsedAccounts: [],
      // 文本导入
      textForm: {
        accountsText: '',
        delimiter: '----'
      },
      // 状态
      loading: false,
      parsing: false,
      importResult: null,
      error: ''
    }
  },
  computed: {
    accountCount() {
      if (this.importMode === 'file') {
        return this.parsedAccounts.length
      }
      return this.textForm.accountsText.trim().split('\n').filter(l => l.trim()).length
    },
    canSubmit() {
      if (this.importMode === 'file') {
        return this.parsedAccounts.length > 0
      }
      return this.textForm.accountsText.trim().length > 0
    }
  },
  template: `
    <div class="grid grid-2">
      <!-- 左侧：导入表单 -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">📥 账号导入</h3>
          <div class="mode-switch">
            <button class="mode-btn" :class="{ active: importMode === 'file' }" @click="importMode = 'file'">📁 文件导入</button>
            <button class="mode-btn" :class="{ active: importMode === 'text' }" @click="importMode = 'text'">📝 文本导入</button>
          </div>
        </div>
        
        <!-- 文件导入 -->
        <div v-if="importMode === 'file'">
          <div 
            class="drop-zone" 
            :class="{ dragging: isDragging, 'has-file': selectedFile }"
            @dragover.prevent="isDragging = true"
            @dragleave.prevent="isDragging = false"
            @drop.prevent="handleDrop"
            @click="triggerFileSelect"
          >
            <input 
              type="file" 
              ref="fileInput" 
              accept=".xls,.xlsx,.csv" 
              @change="handleFileSelect" 
              style="display: none"
            >
            <div v-if="parsing" class="drop-content">
              <div class="drop-icon">⏳</div>
              <div class="drop-text">正在解析文件...</div>
            </div>
            <div v-else-if="selectedFile" class="drop-content">
              <div class="drop-icon">📊</div>
              <div class="drop-text">{{ selectedFile.name }}</div>
              <div class="drop-hint">已解析 <strong>{{ parsedAccounts.length }}</strong> 个账号</div>
              <button class="btn btn-sm btn-secondary" @click.stop="clearFile" style="margin-top: 10px;">重新选择</button>
            </div>
            <div v-else class="drop-content">
              <div class="drop-icon">📁</div>
              <div class="drop-text">拖拽 Excel 文件到这里</div>
              <div class="drop-hint">或点击选择文件 (.xls, .xlsx, .csv)</div>
            </div>
          </div>
          
          <!-- 预览表格 -->
          <div v-if="parsedAccounts.length" class="preview-section">
            <div class="preview-header">
              <span>📋 数据预览（前 5 条）</span>
              <span class="preview-count">共 {{ parsedAccounts.length }} 条</span>
            </div>
            <div class="table-container" style="max-height: 200px;">
              <table class="table preview-table">
                <thead>
                  <tr>
                    <th>账号</th>
                    <th>粉丝</th>
                    <th>国家</th>
                    <th>年份</th>
                    <th>会员</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(acc, idx) in parsedAccounts.slice(0, 5)" :key="idx">
                    <td class="username">@{{ acc.username }}</td>
                    <td>{{ acc.follower_count || 0 }}</td>
                    <td>{{ acc.country || '-' }}</td>
                    <td>{{ acc.create_year || '-' }}</td>
                    <td><span class="tag" :class="acc.is_premium ? 'tag-success' : ''">{{ acc.is_premium ? '✓' : '-' }}</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          
          <div class="format-hint">
            <div class="format-title">📄 Excel 格式说明</div>
            <code class="format-code">账号 | 密码 | 2FA | ct0:xxx | authtoken | 邮箱 | 邮箱密码 | 粉丝数 | 国家 | 年份 | 会员</code>
          </div>
        </div>
        
        <!-- 文本导入 -->
        <div v-else>
          <div class="form-group">
            <label class="form-label">账号数据</label>
            <textarea 
              v-model="textForm.accountsText" 
              class="input textarea" 
              placeholder="每行一个账号，格式：用户名----密码----2FA----邮箱----邮箱密码" 
              rows="12"
            ></textarea>
            <div class="form-hint">已输入 <strong>{{ accountCount }}</strong> 个账号</div>
          </div>
          <div class="form-group">
            <label class="form-label">分隔符</label>
            <input v-model="textForm.delimiter" class="input" placeholder="默认: ----" style="width: 120px;">
          </div>
        </div>
        
        <div v-if="error" class="error-msg">{{ error }}</div>
        
        <div class="form-actions">
          <button class="btn btn-secondary" @click="clearAll">清空</button>
          <button 
            class="btn btn-primary btn-lg" 
            @click="handleImport" 
            :disabled="loading || !canSubmit"
          >
            {{ loading ? '导入中...' : '📥 导入账号' }}
          </button>
        </div>
      </div>

      <!-- 右侧：导入结果 & 帮助 -->
      <div>
        <!-- 导入结果 -->
        <div class="card" v-if="importResult">
          <div class="card-header">
            <h3 class="card-title">✅ 导入完成</h3>
          </div>
          <div class="import-result">
            <div class="result-icon">🎉</div>
            <div class="result-text">成功导入 <strong>{{ importResult.count }}</strong> 个账号</div>
            <p class="result-hint">账号已添加到待检测队列，请前往「任务管理」页面开始检测</p>
            <button class="btn btn-primary" @click="$emit('navigate', 'task')" style="margin-top: 12px;">
              🚀 前往任务管理
            </button>
          </div>
        </div>

        <!-- 帮助提示 -->
        <div class="card" v-else style="padding: 40px; text-align: center;">
          <div style="font-size: 3rem; opacity: 0.3; margin-bottom: 12px;">💡</div>
          <div style="font-size: 1.1rem; color: var(--text-secondary); margin-bottom: 6px;">使用说明</div>
          <p style="color: var(--text-muted); font-size: 0.85rem;">
            支持导入 Excel 文件 (.xls, .xlsx)<br>
            拖拽文件或点击选择即可导入<br><br>
            导入后前往「任务管理」开始检测
          </p>
        </div>
        
        <!-- 下载模板 -->
        <div class="card" style="margin-top: 12px;">
          <div class="card-header">
            <h3 class="card-title">📥 导入模板</h3>
          </div>
          <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 12px;">
            Excel 列顺序：账号、密码、2FA、ct0、authtoken、邮箱、邮箱密码、粉丝数、国家、年份、会员
          </p>
          <button class="btn btn-secondary" @click="downloadTemplate">📄 下载模板</button>
        </div>
      </div>
    </div>
  `,
  methods: {
    triggerFileSelect() {
      if (!this.selectedFile) {
        this.$refs.fileInput.click()
      }
    },
    handleFileSelect(e) {
      const file = e.target.files[0]
      if (file) this.parseFile(file)
    },
    handleDrop(e) {
      this.isDragging = false
      const file = e.dataTransfer.files[0]
      if (file) this.parseFile(file)
    },
    async parseFile(file) {
      const validExtensions = ['.xls', '.xlsx', '.csv']
      const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase()
      
      if (!validExtensions.includes(ext)) {
        this.error = '请选择 Excel 文件 (.xls, .xlsx) 或 CSV 文件'
        return
      }
      
      this.selectedFile = file
      this.parsing = true
      this.error = ''
      this.parsedAccounts = []
      
      try {
        const data = await this.readFileAsArrayBuffer(file)
        const workbook = XLSX.read(data, { type: 'array' })
        const firstSheet = workbook.Sheets[workbook.SheetNames[0]]
        const rows = XLSX.utils.sheet_to_json(firstSheet, { header: 1 })
        
        this.parsedAccounts = rows
          .filter(row => row && row.length > 0 && row[0])
          .map(row => this.parseRow(row))
          .filter(acc => acc.username)
        
        if (this.parsedAccounts.length === 0) {
          this.error = '未能解析到有效账号数据，请检查文件格式'
        }
      } catch (e) {
        console.error('解析文件失败:', e)
        this.error = '解析文件失败: ' + e.message
      }
      
      this.parsing = false
    },
    readFileAsArrayBuffer(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = (e) => resolve(new Uint8Array(e.target.result))
        reader.onerror = reject
        reader.readAsArrayBuffer(file)
      })
    },
    parseRow(row) {
      const getString = (val) => val ? String(val).trim() : ''
      const getNumber = (val) => {
        const num = parseInt(val)
        return isNaN(num) ? 0 : num
      }
      
      const ct0 = getString(row[3])
      const authToken = getString(row[4])
      let cookie = ''
      if (ct0 || authToken) {
        const parts = []
        if (ct0) {
          parts.push(ct0.startsWith('ct0:') ? ct0 : `ct0=${ct0}`)
        }
        if (authToken) {
          parts.push(`auth_token=${authToken}`)
        }
        cookie = parts.join('; ')
      }
      
      const premiumVal = getString(row[10]).toLowerCase()
      const isPremium = premiumVal === '会员' || premiumVal === '是' || premiumVal === 'yes' || premiumVal === 'true' || premiumVal === '1'
      
      return {
        username: getString(row[0]),
        password: getString(row[1]),
        two_fa: getString(row[2]),
        cookie: cookie,
        email: getString(row[5]),
        email_password: getString(row[6]),
        follower_count: getNumber(row[7]),
        country: getString(row[8]),
        create_year: getString(row[9]),
        is_premium: isPremium
      }
    },
    clearFile() {
      this.selectedFile = null
      this.parsedAccounts = []
      this.error = ''
      if (this.$refs.fileInput) {
        this.$refs.fileInput.value = ''
      }
    },
    clearAll() {
      this.clearFile()
      this.textForm.accountsText = ''
      this.importResult = null
      this.error = ''
    },
    async handleImport() {
      this.loading = true
      this.error = ''
      this.importResult = null
      
      try {
        let accountsData = []
        
        if (this.importMode === 'file') {
          accountsData = this.parsedAccounts
        } else {
          const lines = this.textForm.accountsText.trim().split('\n')
          accountsData = lines
            .filter(l => l.trim())
            .map(line => {
              const parts = line.split(this.textForm.delimiter)
              return {
                username: parts[0]?.trim() || '',
                password: parts[1]?.trim() || '',
                two_fa: parts[2]?.trim() || '',
                email: parts[3]?.trim() || '',
                email_password: parts[4]?.trim() || ''
              }
            })
            .filter(acc => acc.username)
        }
        
        if (accountsData.length === 0) {
          this.error = '没有有效的账号数据'
          this.loading = false
          return
        }
        
        const res = await API.importAccountsFromData({
          accounts: accountsData,
          auto_check: false  // 不自动检测
        })
        
        if (res.success) {
          this.importResult = res.data
          Toast.success(`成功导入 ${res.data.count} 个账号`)
        } else {
          this.error = res.message
        }
      } catch (e) {
        this.error = e.message
      }
      
      this.loading = false
    },
    downloadTemplate() {
      const templateData = [
        ['账号', '密码', '2FA', 'ct0', 'authtoken', '邮箱', '邮箱密码', '粉丝数', '国家', '年份', '会员'],
        ['example_user', 'password123', 'ABCD1234', 'ct0_value_here', 'auth_token_here', 'email@example.com', 'email_pwd', '100', '日本', '2019', '普通用户']
      ]
      
      const ws = XLSX.utils.aoa_to_sheet(templateData)
      const wb = XLSX.utils.book_new()
      XLSX.utils.book_append_sheet(wb, ws, 'Template')
      XLSX.writeFile(wb, 'twitter_import_template.xlsx')
      
      Toast.success('模板已下载')
    },
    // localStorage 持久化
    loadConfig() {
      try {
        const saved = localStorage.getItem('import_config')
        if (saved) {
          const config = JSON.parse(saved)
          if (config.delimiter) this.textForm.delimiter = config.delimiter
          if (config.importMode) this.importMode = config.importMode
        }
      } catch (e) {
        console.warn('加载导入配置失败:', e)
      }
    },
    saveConfig() {
      try {
        localStorage.setItem('import_config', JSON.stringify({
          delimiter: this.textForm.delimiter,
          importMode: this.importMode
        }))
      } catch (e) {
        console.warn('保存导入配置失败:', e)
      }
    }
  },
  watch: {
    'textForm.delimiter'() { this.saveConfig() },
    'importMode'() { this.saveConfig() }
  },
  mounted() {
    this.loadConfig()
  }
}

// 页面专用样式
const importStyles = `
  .mode-switch {
    display: flex;
    gap: 4px;
    background: var(--bg-secondary);
    padding: 3px;
    border-radius: var(--radius-md);
  }
  .mode-btn {
    padding: 6px 12px;
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 0.8rem;
    font-family: var(--font-sans);
    transition: all 0.2s ease;
  }
  .mode-btn:hover { color: var(--text-primary); }
  .mode-btn.active { background: var(--bg-card); color: var(--primary); }
  
  .drop-zone {
    border: 2px dashed var(--border);
    border-radius: var(--radius-lg);
    padding: 40px 20px;
    text-align: center;
    cursor: pointer;
    transition: all 0.3s ease;
    margin-bottom: 16px;
  }
  .drop-zone:hover, .drop-zone.dragging {
    border-color: var(--primary);
    background: var(--primary-light);
  }
  .drop-zone.has-file {
    border-style: solid;
    border-color: var(--success);
    background: var(--success-bg);
    cursor: default;
  }
  .drop-content { pointer-events: none; }
  .drop-icon { font-size: 2.5rem; margin-bottom: 10px; }
  .drop-text { font-size: 1rem; font-weight: 500; margin-bottom: 4px; }
  .drop-hint { font-size: 0.8rem; color: var(--text-muted); }
  
  .preview-section {
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
    padding: 12px;
    margin-bottom: 16px;
  }
  .preview-header {
    display: flex;
    justify-content: space-between;
    font-size: 0.85rem;
    margin-bottom: 10px;
    color: var(--text-secondary);
  }
  .preview-count { color: var(--primary); font-weight: 500; }
  .preview-table { font-size: 0.75rem; }
  .preview-table .username { font-family: var(--font-mono); color: var(--primary); }
  
  .format-hint {
    background: var(--bg-secondary);
    border-radius: var(--radius-md);
    padding: 12px;
    margin-bottom: 16px;
  }
  .format-title { font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 6px; }
  .format-code {
    display: block;
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-muted);
    word-break: break-all;
  }
  
  .import-result {
    text-align: center;
    padding: 20px;
  }
  .result-icon { font-size: 3rem; margin-bottom: 12px; }
  .result-text { font-size: 1.2rem; margin-bottom: 8px; }
  .result-text strong { color: var(--success); }
  .result-hint { font-size: 0.85rem; color: var(--text-muted); }
`

const importStyleEl = document.createElement('style')
importStyleEl.textContent = importStyles
document.head.appendChild(importStyleEl)

window.ImportPage = ImportPage

