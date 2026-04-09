<template>
  <main class="chat-main">
    <div v-if="!conversation" class="empty-state">
      <div class="empty-content">
        <div class="empty-visual">
          <div class="circle circle-1"></div>
          <div class="circle circle-2"></div>
          <div class="circle circle-3"></div>
          <div class="center-icon">
            <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
              <path d="M2 17l10 5 10-5"></path>
              <path d="M2 12l10 5 10-5"></path>
            </svg>
          </div>
        </div>
        <h1>欢迎使用课程助手</h1>
        <p>高校课程智能问答系统，为您提供精准的知识解答</p>
        <div class="features">
          <div class="feature-item">
            <div class="feature-icon">📚</div>
            <div class="feature-text">课程知识库</div>
          </div>
          <div class="feature-item">
            <div class="feature-icon">💡</div>
            <div class="feature-text">智能问答</div>
          </div>
          <div class="feature-item">
            <div class="feature-icon">🎯</div>
            <div class="feature-text">精准引用</div>
          </div>
        </div>
      </div>
    </div>
    
    <template v-else>
      <div class="messages" ref="messagesRef">
        <div class="messages-inner">
          <div v-if="messages.length === 0" class="welcome">
            <div class="welcome-icon">
              <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
              </svg>
            </div>
            <h2>开始对话</h2>
            <p>输入您的问题，我将基于课程知识库为您解答</p>
          </div>
          <MessageItem 
            v-for="(msg, index) in messages" 
            :key="msg.id"
            :message="msg"
            :style="{ animationDelay: `${index * 0.05}s` }"
          />
        </div>
      </div>
      
      <div class="input-area">
        <div class="input-container">
          <div class="input-wrapper" :class="{ focused: isFocused, 'has-content': input.trim() }">
            <textarea 
              v-model="input"
              placeholder="输入您的问题..."
              :disabled="loading"
              @keydown="handleKeydown"
              @focus="isFocused = true"
              @blur="isFocused = false"
              @input="autoResize"
              ref="inputRef"
              rows="1"
            ></textarea>
            <button 
              @click="handleSubmit" 
              :disabled="loading || !input.trim()" 
              :class="{ active: input.trim() && !loading }"
            >
              <svg v-if="loading" class="loading" viewBox="0 0 24 24" width="16" height="16">
                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="31.4 31.4" stroke-linecap="round"/>
              </svg>
              <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
          <div class="input-hint">Enter 发送 · Shift+Enter 换行</div>
        </div>
      </div>
    </template>
  </main>
</template>

<script setup>
import { ref, nextTick, watch, onMounted } from 'vue'
import MessageItem from './MessageItem.vue'

const props = defineProps({
  conversation: Object,
  messages: Array,
  loading: Boolean
})

const emit = defineEmits(['send'])

const input = ref('')
const messagesRef = ref(null)
const inputRef = ref(null)
const isFocused = ref(false)

// 自动调整高度
function autoResize() {
  const textarea = inputRef.value
  if (textarea) {
    textarea.style.height = 'auto'
    textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px'
  }
}

// 处理键盘事件
function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSubmit()
  }
}

function handleSubmit() {
  if (!input.value.trim() || props.loading) return
  emit('send', input.value.trim())
  input.value = ''
  
  // 重置高度
  nextTick(() => {
    if (inputRef.value) {
      inputRef.value.style.height = 'auto'
    }
    messagesRef.value?.scrollTo({ top: messagesRef.value.scrollHeight, behavior: 'smooth' })
  })
}

watch(() => props.messages, () => {
  nextTick(() => {
    messagesRef.value?.scrollTo({ top: messagesRef.value.scrollHeight, behavior: 'smooth' })
  })
}, { deep: true })

// 对话切换时聚焦输入框
watch(() => props.conversation, () => {
  nextTick(() => {
    inputRef.value?.focus()
  })
})

onMounted(() => {
  inputRef.value?.focus()
})
</script>

<style scoped>
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #f8fafc;
  min-width: 0;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.empty-content {
  text-align: center;
  max-width: 480px;
}

.empty-visual {
  position: relative;
  width: 120px;
  height: 120px;
  margin: 0 auto 32px;
}

.circle {
  position: absolute;
  border-radius: 50%;
  background: #e0e7ff;
  opacity: 0.5;
}

.circle-1 {
  width: 120px;
  height: 120px;
  top: 0;
  left: 0;
  animation: pulse 3s ease-in-out infinite;
}

.circle-2 {
  width: 90px;
  height: 90px;
  top: 15px;
  left: 15px;
  animation: pulse 3s ease-in-out infinite 0.5s;
}

.circle-3 {
  width: 60px;
  height: 60px;
  top: 30px;
  left: 30px;
  animation: pulse 3s ease-in-out infinite 1s;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 0.3; }
  50% { transform: scale(1.05); opacity: 0.5; }
}

.center-icon {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 48px;
  height: 48px;
  background: #fff;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6366f1;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.15);
}

.empty-content h1 {
  font-size: 28px;
  color: #1e293b;
  margin-bottom: 12px;
  font-weight: 600;
  letter-spacing: -0.5px;
}

.empty-content > p {
  font-size: 15px;
  color: #64748b;
  margin-bottom: 40px;
  line-height: 1.6;
}

.features {
  display: flex;
  gap: 24px;
  justify-content: center;
}

.feature-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.feature-icon {
  font-size: 24px;
}

.feature-text {
  font-size: 13px;
  color: #64748b;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
}

.messages-inner {
  max-width: 720px;
  margin: 0 auto;
}

.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  text-align: center;
}

.welcome-icon {
  width: 48px;
  height: 48px;
  background: #f1f5f9;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  margin-bottom: 16px;
}

.welcome h2 {
  font-size: 20px;
  color: #1e293b;
  margin-bottom: 8px;
  font-weight: 500;
}

.welcome p {
  color: #94a3b8;
  font-size: 14px;
}

.input-area {
  padding: 16px 32px 24px;
  background: #f8fafc;
}

.input-container {
  max-width: 720px;
  margin: 0 auto;
}

.input-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #fff;
  border-radius: 12px;
  padding: 8px 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.03);
  border: 1px solid #e2e8f0;
  transition: all 0.2s ease;
}

.input-wrapper.focused {
  border-color: #c7d2fe;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08), 0 1px 3px rgba(0,0,0,0.04);
}

.input-wrapper.has-content {
  border-color: #c7d2fe;
}

textarea {
  flex: 1;
  background: transparent;
  border: none;
  color: #334155;
  font-size: 14px;
  resize: none;
  outline: none;
  min-height: 24px;
  max-height: 150px;
  line-height: 1.6;
  font-family: inherit;
  overflow-y: auto;
}

textarea::placeholder {
  color: #94a3b8;
}

textarea:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

button {
  width: 28px;
  height: 28px;
  background: #f1f5f9;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

button.active {
  background: #6366f1;
  color: #fff;
}

button.active:hover {
  background: #4f46e5;
  transform: scale(1.04);
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.loading {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.input-hint {
  text-align: center;
  font-size: 12px;
  color: #94a3b8;
  margin-top: 8px;
}
</style>