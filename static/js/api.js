/**
 * API 请求封装
 */
const API = {
  baseURL: '',

  // 通用请求方法
  async request(method, url, data = null) {
    const config = {
      method,
      headers: { 'Content-Type': 'application/json' }
    }
    if (data) {
      config.body = JSON.stringify(data)
    }
    const response = await fetch(this.baseURL + url, config)
    return response.json()
  },

  // GET 请求
  get(url, params = {}) {
    const query = new URLSearchParams(params).toString()
    const fullUrl = query ? `${url}?${query}` : url
    return this.request('GET', fullUrl)
  },

  // POST 请求
  post(url, data) {
    return this.request('POST', url, data)
  },

  // ==================== 统计 API ====================
  
  // 获取总览统计
  getStatistics() {
    return this.get('/api/statistics')
  },

  // 获取国家统计
  getCountryStatistics() {
    return this.get('/api/statistics/countries')
  },

  // 获取粉丝区间统计
  getFollowerStatistics() {
    return this.get('/api/statistics/followers')
  },

  // ==================== 检测 API ====================

  // 导入账号（文本格式）
  importAccounts(data) {
    return this.post('/api/import', data)
  },

  // 导入账号（JSON 数据，支持 Excel 解析后的数据）
  importAccountsFromData(data) {
    return this.post('/api/import/data', data)
  },

  // 单个账号检测
  checkSingleAccount(data) {
    return this.post('/api/check/single', data)
  },

  // 批量检测
  checkBatchAccounts(data) {
    return this.post('/api/check/batch', data)
  },

  // ==================== 账号列表 API ====================

  // 按状态获取
  getAccountsByStatus(status, page = 1, pageSize = 50, isExtracted = undefined) {
    const params = { page, page_size: pageSize }
    if (isExtracted !== undefined) params.is_extracted = isExtracted
    return this.get(`/api/accounts/status/${encodeURIComponent(status)}`, params)
  },

  // 按国家获取
  getAccountsByCountry(country, page = 1, pageSize = 50, isExtracted = undefined) {
    const params = { page, page_size: pageSize }
    if (isExtracted !== undefined) params.is_extracted = isExtracted
    return this.get(`/api/accounts/country/${encodeURIComponent(country)}`, params)
  },

  // 按粉丝数量获取
  getAccountsByFollowers(minFollowers, maxFollowers, page = 1, pageSize = 50, isExtracted = undefined) {
    const params = {
      min_followers: minFollowers,
      max_followers: maxFollowers,
      page,
      page_size: pageSize
    }
    if (isExtracted !== undefined) params.is_extracted = isExtracted
    return this.get('/api/accounts/followers', params)
  },

  // ==================== 提取 API ====================

  // 提取账号
  extractAccounts(data) {
    return this.post('/api/extract', data)
  },

  // 导出账号
  exportAccounts(data, format = 'text') {
    return this.post(`/api/extract/export?format=${format}`, data)
  },

  // ==================== 任务管理 API ====================

  // 获取任务状态
  getTaskStatus() {
    return this.get('/api/task/status')
  },

  // 获取任务配置
  getTaskConfig() {
    return this.get('/api/task/config')
  },

  // 保存任务配置
  saveTaskConfig(config) {
    return this.post('/api/task/config', config)
  },

  // 获取任务日志
  getTaskLogs(afterId = 0) {
    return this.get('/api/task/logs', { after_id: afterId })
  },

  // 启动任务
  startTask(config) {
    return this.post('/api/task/start', config)
  },

  // 暂停任务
  pauseTask() {
    return this.post('/api/task/pause')
  },

  // 恢复任务
  resumeTask() {
    return this.post('/api/task/resume')
  },

  // 停止任务
  stopTask() {
    return this.post('/api/task/stop')
  },

  // ==================== 账号管理 API ====================

  // 重置所有账号状态为待检测
  resetAllAccountsStatus() {
    return this.post('/api/accounts/reset-status')
  },

  // 清空所有账号
  clearAllAccounts() {
    return this.post('/api/accounts/clear')
  }
}

// 导出
window.API = API

