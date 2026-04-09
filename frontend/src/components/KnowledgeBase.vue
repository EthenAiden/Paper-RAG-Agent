<template>
  <div class="knowledge-base">
    <div class="page-header">
      <h1>知识库</h1>
      <p>管理您的文档资源，支持 PDF、Word、Markdown 等格式</p>
    </div>
    
    <div class="toolbar">
      <div class="search-box">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
        <input v-model="searchText" placeholder="搜索文档..." />
      </div>
      <label class="upload-btn">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="17 8 12 3 7 8"></polyline>
          <line x1="12" y1="3" x2="12" y2="15"></line>
        </svg>
        <span>上传文档</span>
        <input type="file" accept=".pdf,.doc,.docx,.md,.txt" @change="handleUpload" hidden />
      </label>
    </div>
    
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-value">{{ documents.length }}</div>
        <div class="stat-label">文档总数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ totalChunks }}</div>
        <div class="stat-label">分块数量</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ completedCount }}</div>
        <div class="stat-label">已完成</div>
      </div>
    </div>
    
    <div class="doc-list">
      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <span>加载中...</span>
      </div>
      
      <div v-else-if="filteredDocs.length === 0" class="empty-state">
        <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
        </svg>
        <p>暂无文档</p>
        <span>上传文档开始构建知识库</span>
      </div>
      
      <div v-else class="doc-grid">
        <div v-for="doc in filteredDocs" :key="doc.id" class="doc-card">
          <div class="doc-icon" :class="getFileType(doc.file_type)">
            {{ getFileIcon(doc.file_type) }}
          </div>
          <div class="doc-info">
            <div class="doc-name">{{ doc.name }}</div>
            <div class="doc-meta">
              <span>{{ formatSize(doc.file_size) }}</span>
              <span>·</span>
              <span>{{ doc.chunk_count || 0 }} 分块</span>
            </div>
          </div>
          <div class="doc-status" :class="getStatusClass(doc.status)">
            {{ getStatusText(doc.status) }}
          </div>
          <button v-if="doc.status === 2" class="retry-btn" @click="retryDoc(doc.id)" title="重试">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M1 4v6h6"></path>
              <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path>
            </svg>
          </button>
          <button class="doc-action" @click="deleteDoc(doc.id)">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="3 6 5 6 21 6"></polyline>
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getDocumentList, uploadDocument, deleteDocument, reparseDocument } from '../api'

const documents = ref([])
const loading = ref(false)
const searchText = ref('')
let pollTimer = null

const filteredDocs = computed(() => {
  if (!searchText.value) return documents.value
  return documents.value.filter(d => 
    d.name.toLowerCase().includes(searchText.value.toLowerCase())
  )
})

const totalChunks = computed(() => 
  documents.value.reduce((sum, d) => sum + (d.chunk_count || 0), 0)
)

const completedCount = computed(() => 
  documents.value.filter(d => d.status === 1).length
)

// 是否有处理中的文档
const hasProcessing = computed(() => 
  documents.value.some(d => d.status === 0)
)

// 智能轮询：有处理中的文档时 10 秒，否则 60 秒
function startPolling() {
  stopPolling()
  const interval = hasProcessing.value ? 10000 : 60000
  pollTimer = setInterval(() => {
    loadDocuments()
  }, interval)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(() => {
  loadDocuments()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})

async function loadDocuments() {
  loading.value = true
  try {
    const { data } = await getDocumentList(1, 100)
    documents.value = data.data.list
    // 根据处理状态调整轮询间隔
    startPolling()
  } catch (e) {
    console.error('加载文档失败', e)
  }
  loading.value = false
}

async function handleUpload(e) {
  const file = e.target.files[0]
  if (!file) return
  
  const formData = new FormData()
  formData.append('file', file)
  
  try {
    await uploadDocument(formData)
    await loadDocuments()
  } catch (err) {
    console.error('上传失败', err)
  }
  e.target.value = ''
}

async function deleteDoc(docId) {
  if (!confirm('确定删除该文档？')) return
  try {
    await deleteDocument(docId)
    documents.value = documents.value.filter(d => d.id !== docId)
  } catch (e) {
    console.error('删除失败', e)
  }
}

async function retryDoc(docId) {
  try {
    await reparseDocument(docId)
    // 更新状态为处理中
    const doc = documents.value.find(d => d.id === docId)
    if (doc) {
      doc.status = 0
    }
  } catch (e) {
    console.error('重试失败', e)
  }
}

function getFileType(type) {
  if (type === 'pdf') return 'pdf'
  if (type === 'doc' || type === 'docx') return 'word'
  if (type === 'md') return 'markdown'
  return 'other'
}

function getFileIcon(type) {
  if (type === 'pdf') return 'PDF'
  if (type === 'doc' || type === 'docx') return 'W'
  if (type === 'md') return 'M'
  return '📄'
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

function getStatusClass(status) {
  if (status === 0) return 'processing'
  if (status === 1) return 'completed'
  return 'failed'
}

function getStatusText(status) {
  if (status === 0) return '处理中'
  if (status === 1) return '已完成'
  return '失败'
}
</script>

<style scoped>
.knowledge-base {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 24px 32px;
  overflow-y: auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 24px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 4px;
}

.page-header p {
  font-size: 14px;
  color: #64748b;
}

.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.search-box {
  flex: 1;
  max-width: 320px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  transition: all 0.2s;
}

.search-box:focus-within {
  border-color: #c7d2fe;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08);
}

.search-box svg {
  color: #94a3b8;
}

.search-box input {
  flex: 1;
  border: none;
  outline: none;
  font-size: 14px;
  color: #334155;
  background: transparent;
}

.search-box input::placeholder {
  color: #94a3b8;
}

.upload-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: #6366f1;
  color: #fff;
  border-radius: 8px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.upload-btn:hover {
  background: #4f46e5;
}

.stats-row {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  flex: 1;
  max-width: 160px;
  padding: 16px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

.stat-value {
  font-size: 28px;
  font-weight: 600;
  color: #1e293b;
}

.stat-label {
  font-size: 12px;
  color: #64748b;
  margin-top: 4px;
}

.doc-list {
  flex: 1;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px;
  color: #94a3b8;
  gap: 12px;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #e2e8f0;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px;
  color: #94a3b8;
  text-align: center;
}

.empty-state svg {
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-state p {
  font-size: 16px;
  color: #64748b;
  margin-bottom: 4px;
}

.empty-state span {
  font-size: 13px;
}

.doc-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.doc-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  transition: all 0.2s;
}

.doc-card:hover {
  border-color: #c7d2fe;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

.doc-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.doc-icon.pdf {
  background: #fef2f2;
  color: #dc2626;
}

.doc-icon.word {
  background: #eff6ff;
  color: #2563eb;
}

.doc-icon.markdown {
  background: #f0fdf4;
  color: #16a34a;
}

.doc-icon.other {
  background: #f8fafc;
  color: #64748b;
}

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-name {
  font-size: 14px;
  font-weight: 500;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-meta {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 2px;
  display: flex;
  gap: 6px;
}

.doc-status {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 12px;
  font-weight: 500;
}

.doc-status.processing {
  background: #fef3c7;
  color: #d97706;
}

.doc-status.completed {
  background: #dcfce7;
  color: #16a34a;
}

.doc-status.failed {
  background: #fee2e2;
  color: #dc2626;
}

.doc-action {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  border-radius: 6px;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.15s;
}

.doc-action:hover {
  background: #fef2f2;
  color: #dc2626;
}

.retry-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  color: #64748b;
  cursor: pointer;
  transition: all 0.15s;
}

.retry-btn:hover {
  background: #fef3c7;
  border-color: #f59e0b;
  color: #d97706;
}
</style>