import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 60000
})

// 会话管理
export const createConversation = () => api.post('/conversation/create')
export const getConversationList = (page = 1, pageSize = 20) => 
  api.get('/conversation/list', { params: { page, page_size: pageSize } })
export const getConversationHistory = (convId) => 
  api.get(`/conversation/${convId}/history`)
export const deleteConversation = (convId) => 
  api.delete(`/conversation/${convId}`)

// 问答
export const askQuestion = (convId, question, topK = 5) => 
  api.post('/chat/ask', { conv_id: convId, question, top_k: topK })

export const streamAsk = async (convId, question, onMessage, onEnd, topK = 5) => {
  const response = await fetch(`/api/v1/chat/stream_ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conv_id: convId, question, top_k: topK })
  })
  
  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`)
  }
  
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    
    buffer += decoder.decode(value, { stream: true })
    
    // SSE 以双换行分隔事件
    const events = buffer.split('\n\n')
    buffer = events.pop() || ''
    
    for (const event of events) {
      const lines = event.split('\n')
      let eventType = ''
      let dataStr = ''
      
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7)
        } else if (line.startsWith('data: ')) {
          dataStr = line.slice(6)
        }
      }
      
      if (dataStr) {
        try {
          const data = JSON.parse(dataStr)
          if (eventType === 'message' && data.content) {
            onMessage(data.content)
          } else if (eventType === 'end') {
            onEnd(data.message_id, data.references, data.course)
          }
        } catch (e) {
          console.error('JSON parse error:', e, dataStr)
        }
      }
    }
  }
}

// 文档管理
export const getDocumentList = (page = 1, pageSize = 10) => 
  api.get('/document/list', { params: { page, page_size: pageSize } })
export const uploadDocument = (formData) => 
  api.post('/document/upload', formData, { 
    headers: { 'Content-Type': 'multipart/form-data' } 
  })
export const deleteDocument = (docId) => 
  api.delete(`/document/${docId}`)
export const reparseDocument = (docId) => 
  api.post(`/document/${docId}/reparse`)