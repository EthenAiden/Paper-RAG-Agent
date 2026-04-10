<template>
  <div class="app-container">
    <ChatSidebar 
      :conversations="conversations"
      :active-id="activeConv?.id"
      :active-view="activeView"
      @select="selectConversation"
      @new="createNewChat"
      @delete="deleteConv"
      @switch-view="switchView"
    />
    <ChatMain 
      v-if="activeView === 'chat'"
      :conversation="activeConv"
      :messages="messages"
      :loading="loading"
      @send="sendMessage"
    />
    <KnowledgeBase v-else />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import ChatSidebar from './components/ChatSidebar.vue'
import ChatMain from './components/ChatMain.vue'
import KnowledgeBase from './components/KnowledgeBase.vue'
import { 
  createConversation, 
  getConversationList, 
  getConversationHistory,
  deleteConversation,
  streamAsk 
} from './api'

const conversations = ref([])
const activeConv = ref(null)
const messages = ref([])
const loading = ref(false)
const activeView = ref('chat')

onMounted(async () => {
  await loadConversations()
})

async function loadConversations() {
  const { data } = await getConversationList()
  conversations.value = data.data.list
}

function switchView(view) {
  activeView.value = view
}

async function createNewChat() {
  activeView.value = 'chat'
  const { data } = await createConversation()
  const conv = { 
    id: data.data.conv_id, 
    title: '新对话',
    message_count: 0 
  }
  conversations.value.unshift(conv)
  selectConversation(conv)
}

async function selectConversation(conv) {
  activeView.value = 'chat'
  activeConv.value = conv
  messages.value = []
  const { data } = await getConversationHistory(conv.id)
  messages.value = data.data.list.map(m => ({
    id: m.id,
    role: m.role,
    content: m.content,
    references: m.reference_chunks || []
  }))
}

async function deleteConv(convId) {
  await deleteConversation(convId)
  conversations.value = conversations.value.filter(c => c.id !== convId)
  if (activeConv.value?.id === convId) {
    activeConv.value = null
    messages.value = []
  }
}

async function sendMessage(question) {
  if (!activeConv.value) {
    await createNewChat()
  }
  
  messages.value.push({ id: Date.now(), role: 'user', content: question })
  messages.value.push({ id: Date.now() + 1, role: 'assistant', content: '', streaming: true, course: null, references: [] })
  loading.value = true
  
  const lastIndex = messages.value.length - 1
  
  try {
    await streamAsk(
      activeConv.value.id,
      question,
      (token) => {
        messages.value[lastIndex].content += token
      },
      (msgId, refs, course) => {
        messages.value[lastIndex].id = msgId
        messages.value[lastIndex].references = refs || []
        messages.value[lastIndex].course = course
        messages.value[lastIndex].streaming = false
      }
    )
  } catch (e) {
    messages.value[lastIndex].content = '抱歉，发生了错误，请重试。'
    messages.value[lastIndex].streaming = false
  }
  
  loading.value = false
  
  if (activeConv.value.title === '新对话') {
    activeConv.value.title = question.slice(0, 20) + (question.length > 20 ? '...' : '')
  }
}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Helvetica Neue', sans-serif;
  background: #f8fafc;
  color: #334155;
  -webkit-font-smoothing: antialiased;
}

#app {
  height: 100vh;
}

.app-container {
  display: flex;
  height: 100vh;
  background: #f8fafc;
}

::-webkit-scrollbar {
  width: 4px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 2px;
}

::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
</style>