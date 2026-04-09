<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="logo">
        <div class="logo-icon">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
            <path d="M2 17l10 5 10-5"></path>
            <path d="M2 12l10 5 10-5"></path>
          </svg>
        </div>
        <span class="logo-text">知识助手</span>
      </div>
    </div>
    
    <div class="nav-tabs">
      <div 
        :class="['nav-tab', { active: activeView === 'chat' }]" 
        @click="$emit('switch-view', 'chat')"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>
        <span>对话</span>
      </div>
      <div 
        :class="['nav-tab', { active: activeView === 'knowledge' }]" 
        @click="$emit('switch-view', 'knowledge')"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
        </svg>
        <span>知识库</span>
      </div>
    </div>
    
    <button class="new-chat-btn" @click="$emit('new')">
      <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="12" y1="5" x2="12" y2="19"></line>
        <line x1="5" y1="12" x2="19" y2="12"></line>
      </svg>
      <span>新建对话</span>
    </button>
    
    <div class="conv-section">
      <div class="section-title">历史记录</div>
      <div class="conv-list">
        <div 
          v-for="conv in conversations" 
          :key="conv.id"
          :class="['conv-item', { active: conv.id === activeId && activeView === 'chat' }]"
          @click="$emit('select', conv)"
        >
          <svg class="conv-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
          </svg>
          <span class="conv-title">{{ conv.title || '新对话' }}</span>
          <button class="delete-btn" @click.stop="$emit('delete', conv.id)">
            <svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        <div v-if="conversations.length === 0" class="empty-tip">
          暂无对话记录
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup>
defineProps({
  conversations: Array,
  activeId: String,
  activeView: String
})

defineEmits(['select', 'new', 'delete', 'switch-view'])
</script>

<style scoped>
.sidebar {
  width: 200px;
  background: #fff;
  border-right: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  padding: 12px;
}

.sidebar-header {
  padding-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
}

.logo-icon {
  width: 28px;
  height: 28px;
  background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6366f1;
}

.logo-text {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}

.nav-tabs {
  display: flex;
  gap: 4px;
  margin-top: 12px;
  padding: 3px;
  background: #f8fafc;
  border-radius: 6px;
}

.nav-tab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 6px 8px;
  border-radius: 4px;
  font-size: 12px;
  color: #64748b;
  cursor: pointer;
  transition: all 0.15s;
}

.nav-tab:hover {
  color: #475569;
}

.nav-tab.active {
  background: #fff;
  color: #6366f1;
  font-weight: 500;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.new-chat-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 12px;
  margin-top: 12px;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
  border-radius: 6px;
  color: #64748b;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.new-chat-btn:hover {
  background: #f1f5f9;
  border-color: #94a3b8;
  color: #475569;
}

.conv-section {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  margin-top: 12px;
}

.section-title {
  font-size: 10px;
  color: #94a3b8;
  padding: 0 4px 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 500;
}

.conv-list {
  flex: 1;
  overflow-y: auto;
}

.conv-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  margin: 2px 0;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.conv-item:hover {
  background: #f8fafc;
}

.conv-item.active {
  background: #f1f5f9;
}

.conv-icon {
  color: #94a3b8;
  flex-shrink: 0;
}

.conv-item.active .conv-icon {
  color: #6366f1;
}

.conv-title {
  flex: 1;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #64748b;
}

.conv-item.active .conv-title {
  color: #334155;
  font-weight: 500;
}

.delete-btn {
  opacity: 0;
  background: none;
  border: none;
  cursor: pointer;
  color: #94a3b8;
  padding: 2px;
  display: flex;
  align-items: center;
  border-radius: 4px;
  transition: all 0.15s;
}

.conv-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  color: #ef4444;
  background: #fef2f2;
}

.empty-tip {
  text-align: center;
  color: #94a3b8;
  font-size: 12px;
  padding: 16px 0;
}
</style>