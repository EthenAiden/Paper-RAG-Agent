<template>
  <div :class="['message', message.role]">
    <div v-if="message.role === 'assistant'" class="avatar">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
        <path d="M2 17l10 5 10-5"></path>
        <path d="M2 12l10 5 10-5"></path>
      </svg>
    </div>
    <div class="body">
      <div v-if="message.course" class="course-tag">
        <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
        </svg>
        {{ message.course }}
      </div>
      <div class="text" v-html="renderedContent"></div>
      <div v-if="message.references?.length" class="references">
        <div class="ref-header" @click="showRefs = !showRefs">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
          </svg>
          <span>引用来源</span>
          <span class="ref-count">{{ message.references.length }}</span>
          <svg :class="['arrow', { open: showRefs }]" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"></polyline>
          </svg>
        </div>
        <transition name="slide">
          <div v-show="showRefs" class="ref-list">
            <div v-for="ref in message.references" :key="ref.id || ref.chunk_id" class="ref-item">
              <div class="ref-id">[来源:{{ ref.id }}]</div>
              <div class="ref-name">{{ ref.doc_name }}</div>
              <div class="ref-content">{{ ref.content }}</div>
            </div>
          </div>
        </transition>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  message: Object
})

const showRefs = ref(false)

const renderedContent = computed(() => {
  if (!props.message.content) return ''
  return marked.parse(props.message.content)
})
</script>

<style scoped>
.message {
  display: flex;
  gap: 10px;
  padding: 12px 0;
  animation: fadeUp 0.3s ease forwards;
  opacity: 0;
}

.message.user {
  flex-direction: row-reverse;
  justify-content: flex-start;
}

.message.user .body {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.message.user .text {
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  color: #fff;
  padding: 10px 14px;
  border-radius: 16px 16px 4px 16px;
  max-width: 70%;
  font-size: 14px;
  line-height: 1.6;
}

.message.user .text :deep(p) {
  margin: 0;
}

.message.user .text :deep(code) {
  background: rgba(255,255,255,0.15);
  color: #fff;
}

.message.assistant {
  justify-content: flex-start;
}

@keyframes fadeUp {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.avatar {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%);
  color: #6366f1;
  flex-shrink: 0;
}

.body {
  flex: 1;
  min-width: 0;
}

.course-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%);
  color: #6366f1;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
  margin-bottom: 6px;
}

.text {
  line-height: 1.7;
  color: #334155;
  font-size: 14px;
}

.text :deep(p) {
  margin: 0 0 10px;
}

.text :deep(p:last-child) {
  margin-bottom: 0;
}

.text :deep(ul), .text :deep(ol) {
  margin: 6px 0;
  padding-left: 18px;
}

.text :deep(li) {
  margin: 3px 0;
}

.text :deep(code) {
  background: #f1f5f9;
  color: #e11d48;
  padding: 2px 5px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
}

.text :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  padding: 12px 14px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 10px 0;
}

.text :deep(pre code) {
  background: none;
  color: inherit;
  padding: 0;
  font-size: 13px;
}

.text :deep(blockquote) {
  border-left: 3px solid #c7d2fe;
  padding-left: 12px;
  margin: 10px 0;
  color: #64748b;
}

.text :deep(h1), .text :deep(h2), .text :deep(h3) {
  margin: 14px 0 6px;
  color: #1e293b;
  font-weight: 600;
}

.text :deep(a) {
  color: #6366f1;
  text-decoration: none;
}

.text :deep(a:hover) {
  text-decoration: underline;
}

.references {
  margin-top: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  max-width: 100%;
}

.message.user .references {
  max-width: 100%;
}

.ref-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  cursor: pointer;
  color: #64748b;
  font-size: 12px;
  transition: all 0.15s;
}

.ref-header:hover {
  background: #f8fafc;
}

.ref-count {
  background: #f1f5f9;
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 11px;
  color: #64748b;
}

.arrow {
  margin-left: auto;
  transition: transform 0.2s;
}

.arrow.open {
  transform: rotate(180deg);
}

.slide-enter-active, .slide-leave-active {
  transition: all 0.2s ease;
}

.slide-enter-from, .slide-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.ref-list {
  border-top: 1px solid #f1f5f9;
}

.ref-item {
  padding: 10px 12px;
  border-bottom: 1px solid #f8fafc;
}

.ref-item:last-child {
  border-bottom: none;
}

.ref-id {
  display: inline-block;
  background: #6366f1;
  color: #fff;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 500;
  margin-right: 6px;
}

.ref-name {
  display: inline-block;
  background: #f1f5f9;
  color: #475569;
  padding: 2px 8px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 500;
  margin-bottom: 4px;
}

.ref-content {
  font-size: 11px;
  color: #64748b;
  line-height: 1.5;
  margin-top: 4px;
}
</style>