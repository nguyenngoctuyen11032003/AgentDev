<template>
  <div class="launch-view">
    <div class="launch-bg"></div>
    <div class="header">
      <h1>{{ $t('launch.title') }}</h1>
      <button class="settings-button" @click="showSettingsModal = true" :title="$t('launch.settings')">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="3"></circle>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
        </svg>
      </button>
    </div>
    <div class="content">
      <!-- Session history: switch between runs and pick up where you left off -->
      <SessionSidebar
        :sessions="sessions"
        :active-id="activeSessionId"
        :draft="draftWorkflow"
        :draft-project="currentProjectName"
        :project-workflows="projectWorkflows"
        :collapsed="!isSessionSidebarOpen"
        @select="openSession"
        @new="startNewSession"
        @add-project="handleAddProject"
        @delete-group="handleDeleteGroup"
        @rename="handleRenameSession"
        @delete="handleDeleteSession"
        @toggle="isSessionSidebarOpen = !isSessionSidebarOpen"
      />

      <!-- Left panel -->
      <div class="left-panel">
        <!-- Chat Panel: fullscreen in chat mode, overlay in graph -->
        <div
          class="chat-panel"
          :class="{
            'chat-panel-fullscreen': viewMode === 'chat',
            'chat-panel-collapsed': viewMode !== 'chat' && !isChatPanelOpen
          }"
          v-show="viewMode === 'chat' || true"
        >
          <button v-show="viewMode !== 'chat'" class="chat-panel-toggle" @click="isChatPanelOpen = !isChatPanelOpen" :title="isChatPanelOpen ? $t('launch.collapse_chat') : $t('launch.expand_chat')">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :class="{ 'chevron-collapsed': !isChatPanelOpen }">
              <polyline points="15 18 9 12 15 6"></polyline>
            </svg>
          </button>
          <div v-show="viewMode === 'chat' || isChatPanelOpen" class="chat-panel-content">
            <div class="chat-header">
              <div class="chat-header-main">
                <span class="chat-header-title" :title="currentSessionTitle">{{ currentSessionTitle }}</span>
                <span v-if="selectedFile" class="chat-header-sub">
                  <span v-if="currentProjectName" class="chat-header-project" :title="$t('launch.sessions.project_label', { name: currentProjectName })">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>{{ currentProjectName }}
                  </span>
                  {{ selectedFile.replace(/\.ya?ml$/i, '') }} · {{ getTranslatedStatus(status) }}
                </span>
              </div>
              <div class="chat-header-actions">
                <button
                  type="button"
                  class="chat-header-btn"
                  :class="{ active: isSessionSidebarOpen }"
                  :title="$t('launch.sessions.history')"
                  :aria-label="$t('launch.sessions.history')"
                  @click="isSessionSidebarOpen = !isSessionSidebarOpen"
                >
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"></path><path d="M3 3v5h5"></path><path d="M12 7v5l3 3"></path></svg>
                </button>
                <button
                  type="button"
                  class="chat-header-btn"
                  :title="newSessionLabel"
                  :aria-label="newSessionLabel"
                  @click="startNewSession()"
                >
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-4.2-7.6"></path><path d="M12 8v8M8 12h8"></path></svg>
                </button>
              </div>
            </div>
            <div class="chat-box">
              <div class="chat-messages" ref="chatMessagesRef">
                <!-- Notifications and dialogues in order -->
                <div
                  v-for="(message, index) in chatMessages"
                  :key="`message-${index}`"
                  class="chat-message-item"
                  v-memo="[
                    message.rev,
                    message.duration,
                    message.loading,
                    message.dataUri,
                    message.error,
                    configStore.AUTO_EXPAND_MESSAGES,
                    i18nLocale
                  ]"
                >
              <!-- Notification -->
              <div
                v-if="['notification', 'warning', 'error'].includes(message.type)"
                class="chat-notification"
                :class="{
                  'chat-notification-warning': message.type === 'warning',
                  'chat-notification-error': message.type === 'error'
                }"
              >
                <div class="notification-content">
                  <div class="notification-text">{{ message.message }}</div>
                  <div class="message-timestamp">{{ formatTime(message.timestamp) }}</div>
                </div>
              </div>

              <!-- Dialogue -->
              <div
                v-else-if="message.type === 'dialogue'"
                class="dialogue"
                :class="{ 'dialogue-right': message.isRight }"
              >
                <div class="profile-picture">
                  <img :src="messageAvatar(message)" :alt="$t('launch.avatar_alt', { name: getDisplayName(message) })" />
                </div>
                <div class="message-content">
                  <div class="user-name">
                    {{ getDisplayName(message) }}
                    <span class="message-timestamp">{{ formatTime(message.timestamp) }}</span>
                  </div>
                  <div
                    class="message-bubble"
                    :class="{ 'loading-bubble': message.isLoading }"
                  >
                  <CollapsibleMessage
                    v-if="message.text"
                    :html-content="message.htmlContent || renderMarkdown(message.text)"
                    :raw-content="message.text"
                    :default-expanded="configStore.AUTO_EXPAND_MESSAGES"
                  />

                  <TransitionGroup
                    v-if="message.loadingEntries && message.loadingEntries.length"
                    name="loading-entry"
                    tag="div"
                    class="loading-entries"
                  >
                    <div
                      v-for="entry in message.loadingEntries"
                      :key="entry.key"
                      class="loading-entry"
                      :class="{
                        'entry-running': entry.status === 'running',
                        'entry-done': entry.status === 'done'
                      }"
                    >
                      <span class="loading-entry-label">{{ entry.label }}</span>
                      <span class="loading-entry-duration">
                        <LiveDuration :started-at="entry.startedAt" :ended-at="entry.endedAt || 0" />
                      </span>
                    </div>
                  </TransitionGroup>

                  <!-- Artifact image -->

                  <div
                    v-if="message.isArtifact && message.isImage"
                    class="artifact-image-wrapper"
                  >
                    <div
                      v-if="message.loading"
                      class="artifact-status"
                    >
                      {{ $t('launch.loading_image') }}
                    </div>
                    <div
                      v-else-if="message.error"
                      class="artifact-status artifact-error"
                    >
                      {{ message.error }}
                    </div>
                    <div v-else>
                      <img
                        :src="message.dataUri"
                        :alt="message.fileName || $t('launch.image_artifact_alt')"
                        class="artifact-image"
                        role="button"
                        tabindex="0"
                        @click="openImageModal(message)"
                        @keydown.enter.prevent="openImageModal(message)"
                        @keydown.space.prevent="openImageModal(message)"
                      />
                      <div class="artifact-filename">
                        <img
                          v-if="getFilePreviewSrc(message)"
                          :src="getFilePreviewSrc(message)"
                          :alt="$t('launch.file_preview_alt', { name: message.fileName || '' })"
                          class="artifact-filename-icon"
                        />
                        <span class="artifact-filename-text">{{ message.fileName }}</span>
                      </div>
                      <!-- Added unified download button for image artifacts -->
                      <button
                        class="artifact-download-button"
                        type="button"
                        :disabled="message.loading"
                        @click="downloadArtifact(message)"
                      >
                        {{ $t('launch.download') }}
                      </button>
                    </div>
                  </div>

                  <!-- Artifact file download -->
                  <div
                    v-else-if="message.isArtifact && !message.isImage"
                    class="artifact-file-wrapper"
                  >
                    <div class="artifact-filename">
                      <img
                        v-if="getFilePreviewSrc(message)"
                        :src="getFilePreviewSrc(message)"
                        :alt="$t('launch.file_preview_alt', { name: message.fileName || '' })"
                        class="artifact-filename-icon"
                      />
                      <span class="artifact-filename-text">{{ message.fileName }}</span>
                    </div>
                    <button
                      class="artifact-download-button"
                      type="button"
                      :disabled="message.loading"
                      @click="downloadArtifact(message)"
                    >
                      {{ message.loading ? $t('launch.preparing') : $t('launch.download') }}
                    </button>
                  </div>

                  <!-- Model/tool call timer -->
                  <div
                    v-if="message.isLoading || message.duration"
                    class="loading-timer"
                  >
                    <LiveDuration v-if="message.isLoading" :started-at="message.startedAt" />
                    <template v-else>{{ message.duration }}</template>
                  </div>
                </div>
                </div>
              </div>
            </div>
          </div>
            </div>
            <div class="input-area">
              <div
                :class="['input-shell', 'composer', { glow: shouldGlow, 'drag-active': isDragActive }]"
                @dragenter="handleDragEnter"
                @dragover="handleDragOver"
                @dragleave="handleDragLeave"
                @drop="handleDrop"
              >
                <!-- Attached files / pasted images -->
                <div
                  v-if="uploadedAttachments.length || isUploadingAttachment"
                  class="composer-attachments"
                >
                  <div
                    v-for="attachment in uploadedAttachments"
                    :key="attachment.attachmentId"
                    class="attachment-chip"
                    :title="attachment.kind === 'project' ? attachment.workspacePath : attachment.name"
                  >
                    <img
                      v-if="attachmentPreviews[attachment.attachmentId]"
                      class="chip-thumb"
                      :src="attachmentPreviews[attachment.attachmentId]"
                      alt=""
                    />
                    <span v-else class="chip-icon">{{ attachment.kind === 'project' ? '📁' : '📄' }}</span>
                    <span class="chip-name">{{ attachment.name }}</span>
                    <span v-if="attachment.kind === 'project'" class="chip-meta">
                      {{ $t('launch.project_files', { count: attachment.fileCount || 0 }) }}
                    </span>
                    <button
                      type="button"
                      class="chip-remove"
                      :title="$t('launch.remove_attachment')"
                      :aria-label="$t('launch.remove_attachment')"
                      @click.stop="removeAttachment(attachment.attachmentId)"
                    >
                      ×
                    </button>
                  </div>
                  <div v-if="isUploadingAttachment" class="attachment-chip chip-uploading">
                    <span class="chip-spinner"></span>
                    <span class="chip-name">{{ uploadProgressText || $t('launch.uploading') }}</span>
                  </div>
                </div>

                <textarea
                  v-model="taskPrompt"
                  class="task-input"
                  rows="1"
                  :disabled="!isConnectionReady || (isWorkflowRunning && status !== 'Waiting for input...')"
                  :placeholder="$t('launch.enter_prompt')"
                  ref="taskInputRef"
                  @input="autoResizeTaskInput"
                  @keydown.enter="handleEnterKey"
                  @paste="handlePaste"
                ></textarea>

                <div class="composer-toolbar">
                  <div class="attach-menu-wrap" ref="attachMenuRef">
                    <button
                      type="button"
                      class="composer-icon-btn"
                      :class="{ active: showAttachMenu }"
                      :title="$t('launch.upload_file')"
                      :aria-label="$t('launch.upload_file')"
                      aria-haspopup="menu"
                      :aria-expanded="showAttachMenu"
                      :disabled="!isConnectionReady || !sessionId || isUploadingAttachment || (isWorkflowRunning && status !== 'Waiting for input...')"
                      @click="showAttachMenu = !showAttachMenu"
                    >
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="12" y1="5" x2="12" y2="19"></line>
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                      </svg>
                    </button>
                    <Transition name="attachment-popover">
                      <div v-if="showAttachMenu" class="attach-menu" role="menu">
                        <button type="button" class="attach-menu-item" role="menuitem" @click="pickAttachmentFile">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path></svg>
                          {{ $t('launch.upload_file') }}
                        </button>
                        <button type="button" class="attach-menu-item" role="menuitem" :title="$t('launch.upload_folder_hint')" @click="pickAttachmentFolder">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                          {{ $t('launch.upload_folder') }}
                        </button>
                      </div>
                    </Transition>
                  </div>
                  <input
                    ref="attachmentInputRef"
                    type="file"
                    multiple
                    class="hidden-file-input"
                    @change="onAttachmentSelected"
                  />
                  <button
                    type="button"
                    class="composer-send"
                    :class="{ glow: shouldGlow && !isStopMode, 'is-stop': isStopMode }"
                    :title="buttonLabel"
                    :aria-label="buttonLabel"
                    :disabled="!isStopMode && (loading || (isWorkflowRunning && !taskPrompt.trim()) || (!isWorkflowRunning && status !== 'Completed' && status !== 'Cancelled' && !isConnectionReady))"
                    @click="isStopMode ? cancelWorkflow() : handleButtonClick()"
                  >
                    <svg v-if="isStopMode" width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                      <rect x="4" y="4" width="16" height="16" rx="3"></rect>
                    </svg>
                    <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                      <line x1="12" y1="19" x2="12" y2="5"></line>
                      <polyline points="5 12 12 5 19 12"></polyline>
                    </svg>
                  </button>
                </div>
                <div v-if="isDragActive" class="drag-overlay">
                  <div class="drag-overlay-content">{{ $t('launch.drop_files') }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-show="viewMode === 'graph'" class="graph-panel">
          <VueFlow class="vueflow-graph">
            <template #node-workflow-node="props">
              <WorkflowNode
                :id="props.id"
                :data="props.data"
                :is-active="activeNodes.includes(props.id)"
                :sprite="nodeSpriteMap.get(props.id) || ''"
                @hover="onNodeHover"
                @leave="onNodeLeave"
              />
            </template>
            <template #node-start-node="props">
              <StartNode :id="props.id" :data="props.data" />
            </template>
            <template #edge-workflow-edge="props">
              <WorkflowEdge
                :id="props.id"
                :source="props.source"
                :target="props.target"
                :source-x="props.sourceX"
                :source-y="props.sourceY"
                :target-x="props.targetX"
                :target-y="props.targetY"
                :source-position="props.sourcePosition"
                :target-position="props.targetPosition"
                :data="props.data"
                :marker-end="props.markerEnd"
                :animated="props.animated"
                :hovered-node-id="hoveredNodeId"
              />
            </template>
            <Background pattern-color="var(--canvas-dot)"/>
            <Controls position="bottom-left"/>
          </VueFlow>
        </div>

        <div v-show="viewMode === 'office'" class="graph-panel office-panel" :style="{ '--office-inset-left': isChatPanelOpen ? 'min(380px, 50%)' : '0px' }">
          <OfficeView
            ref="officeRef"
            :graph="officeGraph"
            :sprite-map="nodeSpriteMap"
            :active-nodes="activeNodes"
            :status="status"
            :workflow-name="selectedFile ? selectedFile.replace(/\.yaml$/i, '') : ''"
            :visible="viewMode === 'office'"
          />
        </div>

        <div v-if="visitedViews.board" v-show="viewMode === 'board'" class="graph-panel insight-panel" :style="insetStyle">
          <KanbanView
            :graph="officeGraph"
            :sprite-map="nodeSpriteMap"
            :tracker="runTracker.state"
            :status="status"
            :workflow-name="workflowTitle"
            :visible="viewMode === 'board'"
            @review="viewMode = 'review'"
          />
        </div>

        <div v-if="visitedViews.review" v-show="viewMode === 'review'" class="graph-panel insight-panel" :style="insetStyle">
          <ReviewView
            :sessions="sessions"
            :focus-id="activeSessionId || ''"
            :busy="isReworking"
            :visible="viewMode === 'review'"
            @open-session="openSessionInChat"
            @rework="handleRework"
            @reviewed="refreshSessions"
          />
        </div>

        <div v-if="visitedViews.dashboard" v-show="viewMode === 'dashboard'" class="graph-panel insight-panel" :style="insetStyle">
          <DashboardView
            :graph="officeGraph"
            :sprite-map="nodeSpriteMap"
            :tracker="runTracker.state"
            :status="status"
            :workflow-name="workflowTitle"
            :sessions="sessions"
            :current-session-id="activeSessionId || ''"
            :visible="viewMode === 'dashboard'"
            @open-session="openSession"
          />
        </div>

        <!-- Right panel floating toggle (bottom-right of canvas) -->
        <button v-show="viewMode !== 'chat'" class="right-panel-fab" @click="isRightPanelOpen = !isRightPanelOpen" :title="isRightPanelOpen ? $t('launch.collapse_panel') : $t('launch.expand_panel')">
          <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="5" cy="6" r="2.5"></circle>
            <circle cx="19" cy="6" r="2.5"></circle>
            <circle cx="12" cy="18" r="2.5"></circle>
            <line x1="5" y1="8.5" x2="12" y2="15.5"></line>
            <line x1="19" y1="8.5" x2="12" y2="15.5"></line>
          </svg>
        </button>
      </div>

      <!-- Right panel -->
      <div
        class="right-panel"
        :class="{
          'right-panel-overlay': viewMode !== 'chat',
          'right-panel-collapsed': viewMode !== 'chat' && !isRightPanelOpen
        }"
      >

        <div v-show="viewMode === 'chat' || isRightPanelOpen" class="control-section">
          <label class="section-label">{{ $t('launch.workflow_selection') }}</label>
      <div
        class="select-wrapper custom-file-selector"
        ref="fileSelectorWrapperRef"
      >
        <input
          ref="fileSelectorInputRef"
          v-model="fileSearchQuery"
          type="text"
          class="file-selector-input"
          :placeholder="loading ? $t('launch.loading') : $t('launch.select_yaml')"
          :disabled="loading || isWorkflowRunning"
          @focus="handleFileInputFocus"
          @input="handleFileInputChange"
          @keydown.enter.prevent="handleFileInputEnter"
          @blur="handleFileInputBlur"
        />
        <div class="select-arrow">▼</div>
        <Transition name="file-dropdown">
          <ul
            v-if="isFileDropdownOpen"
            class="file-dropdown"
          >
            <li
              v-for="workflow in filteredWorkflowFiles"
              :key="workflow.name"
              class="file-option"
              @mousedown.prevent="selectWorkflow(workflow.name)"
            >
              <span class="file-name">{{ workflow.name }}</span>
              <span
                v-if="workflow.description"
                class="file-desc"
              >
                {{ localizedWorkflowDescription(workflow.name, workflow.description) }}
              </span>
            </li>
            <li
              v-if="!filteredWorkflowFiles.length"
              class="file-empty"
            >
              {{ $t('launch.no_results') }}
            </li>
          </ul>
        </Transition>
      </div>
          <p v-if="workflowHint" class="workflow-hint">{{ workflowHint }}</p>

          <label class="section-label">{{ $t('launch.status') }}</label>
          <div class="status-display" :class="{ 'status-active': status === 'Running...' }">
            {{ getTranslatedStatus(status) }}
          </div>

          <label class="section-label">{{ $t('launch.view') }}</label>
          <div class="view-toggle">
            <button
              class="toggle-button"
              :class="{ active: viewMode === 'chat' }"
              @click="viewMode = 'chat'"
            >
              {{ $t('launch.chat') }}
            </button>
            <button
              class="toggle-button"
              :class="{ active: viewMode === 'graph' }"
              @click="switchToGraph"
            >
              {{ $t('launch.graph') }}
            </button>
            <button
              class="toggle-button"
              :class="{ active: viewMode === 'office' }"
              @click="viewMode = 'office'"
            >
              {{ $t('launch.office.view') }}
            </button>
            <button
              class="toggle-button"
              :class="{ active: viewMode === 'board' }"
              @click="viewMode = 'board'"
            >
              {{ $t('launch.board.view') }}
            </button>
            <button
              class="toggle-button"
              :class="{ active: viewMode === 'dashboard' }"
              @click="viewMode = 'dashboard'"
            >
              {{ $t('launch.dashboard.view') }}
            </button>
            <button
              class="toggle-button"
              :class="{ active: viewMode === 'review' }"
              @click="viewMode = 'review'"
            >
              {{ $t('launch.review.view') }}
              <span v-if="reviewPendingCount" class="toggle-badge">{{ reviewPendingCount }}</span>
            </button>
          </div>

          <!-- Button area -->
          <div class="button-section">
            <button
              class="launch-button"
              :class="{ glow: shouldGlow, 'is-sending': isWorkflowRunning }"
              @click="handleButtonClick"
              :disabled="loading || (isWorkflowRunning && !taskPrompt.trim()) || (!isWorkflowRunning && status !== 'Completed' && status !== 'Cancelled' && !isConnectionReady)">
              {{ buttonLabel }}
            </button>

            <button
              class="cancel-button"
              :disabled="status !== 'Running...'"
              @click="cancelWorkflow"
            >
              {{ $t('common.cancel') }}
            </button>

            <button
              class="download-button"
              :disabled="status !== 'Completed' && status !== 'Cancelled'"
              @click="downloadLogs"
            >
              {{ $t('launch.download_logs') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <Transition name="image-modal">
    <div
      v-if="selectedArtifactImage"
      class="image-modal"
      @click.self="closeImageModal"
    >
      <div class="image-modal-content">
        <img
          :src="selectedArtifactImage.src"
          :alt="selectedArtifactImage.name"
          :click="closeImageModal"
        />
      </div>
    </div>
  </Transition>

  <SettingsModal
    :is-visible="showSettingsModal"
    @update:is-visible="showSettingsModal = $event"
  />

  <LocalFolderPicker
    :open="showFolderPicker"
    :busy="isOpeningFolder"
    :hint="folderPickerHint"
    @open="onFolderPicked"
    @cancel="cancelFolderPicker"
  />
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { checkWorkflowConnections, fetchWorkflowsWithDesc, fetchLogsZip, fetchWorkflowYAML, postFile, getAttachment, fetchVueGraph, fetchSessions, saveSessionReview, renameSession, deleteSession, updateSessionWorkflow, cloneProjectIntoSession, openLocalProject } from '@/api/client.js'
import { collectDroppedItems } from '@/utils/projectFiles.js'
import LocalFolderPicker from '@/components/launch/LocalFolderPicker.vue'
import KanbanView from '@/components/launch/KanbanView.vue'
import DashboardView from '@/components/launch/DashboardView.vue'
import ReviewView from '@/components/launch/ReviewView.vue'
import { createRunTracker } from '@/utils/runTracker.js'
import { confirmDialog } from '@/utils/confirm'
import { toast } from '@/utils/toast.js'
import { configStore } from '@/stores/configStore.js'
import { spriteFetcher } from '@/utils/spriteFetcher.js'
import { onWorkflowChanged, workflowKey } from '@/utils/workflowSync.js'
import OfficeView from '@/components/office/OfficeView.vue'
import SessionSidebar from '@/components/launch/SessionSidebar.vue'
import yaml from 'js-yaml'
import MarkdownIt from 'markdown-it'
import SettingsModal from '@/components/common/SettingsModal.vue'
const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true
})

// Memoize markdown output by source text so re-renders never re-parse the same message
const MARKDOWN_CACHE_LIMIT = 300
const markdownCache = new Map()
// Above this size a message is shown as preformatted text: running markdown-it
// (linkify + typographer) over hundreds of KB blocks the WebSocket handler and
// freezes the page for a noticeable moment.
const MARKDOWN_MAX_CHARS = 120_000
const preformatted = (text, lang = '') =>
  `<pre><code${lang ? ` class="language-${lang}"` : ''}>${md.utils.escapeHtml(text)}</code></pre>`

const renderMarkdown = (text) => {
  const source = text || ''
  const cached = markdownCache.get(source)
  if (cached !== undefined) return cached
  const html = source.length > MARKDOWN_MAX_CHARS ? preformatted(source) : md.render(source)
  if (markdownCache.size >= MARKDOWN_CACHE_LIMIT) {
    markdownCache.delete(markdownCache.keys().next().value)
  }
  markdownCache.set(source, html)
  return html
}

// Intl.DateTimeFormat is expensive to create; keep one per locale
const timeFormatterCache = new Map()
const getTimeFormatter = (dateLocale) => {
  let formatter = timeFormatterCache.get(dateLocale)
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(dateLocale, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23'
    })
    timeFormatterCache.set(dateLocale, formatter)
  }
  return formatter
}

const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const dateLocale = TIME_LOCALE_MAP[i18nLocale.value] || 'en-GB'
  return getTimeFormatter(dateLocale).format(new Date(timestamp)) // HH:mm:ss
}
import { VueFlow, useVueFlow, MarkerType } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/controls/dist/style.css'
import '@/assets/styles/vueflow.css'
import WorkflowNode from '@/components/workflow/WorkflowNode.vue'
import WorkflowEdge from '@/components/workflow/WorkflowEdge.vue'
import StartNode from '@/components/workflow/StartNode.vue'
import CollapsibleMessage from '@/components/common/CollapsibleMessage.vue'
// Ticking durations render themselves; the chat list no longer re-renders every second.
import LiveDuration from '@/components/common/LiveDuration.js'
import { localizedWorkflowDescription } from '@/utils/workflowDescription.js'

const router = useRouter()
const route = useRoute()
const { t, te, locale: i18nLocale } = useI18n()

// Map i18n locale to a date locale for 24h time display
const TIME_LOCALE_MAP = {
  vi: 'vi-VN',
  zh: 'zh-CN',
  en: 'en-GB'
}

// Internal name used for messages typed by the user in this view
const USER_SENDER = 'User'

// Display name for a chat dialogue (localizes the local user's name)
const getDisplayName = (message) => {
  if (!message) return ''
  if (message.isRight && message.name === USER_SENDER) {
    return t('launch.user_name')
  }
  return message.name || ''
}

// Turn an error detail (string / FastAPI validation list / object / Error) into readable text
const formatErrorDetail = (detail) => {
  if (detail === null || detail === undefined || detail === '') return ''
  if (typeof detail === 'string') return detail
  if (detail instanceof Error) return detail.message || ''
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === 'object' && item.msg) {
          const loc = Array.isArray(item.loc) ? item.loc.join('.') : ''
          return loc ? `${loc}: ${item.msg}` : String(item.msg)
        }
        return formatErrorDetail(item)
      })
      .filter(Boolean)
      .join('; ')
  }
  if (typeof detail === 'object') {
    if (typeof detail.message === 'string') return detail.message
    if (typeof detail.detail !== 'undefined') return formatErrorDetail(detail.detail)
    try {
      return JSON.stringify(detail)
    } catch {
      return ''
    }
  }
  return String(detail)
}

// Build a localized error message, appending backend detail when available
const errorWithDetail = (key, detail, params = {}) => {
  const text = formatErrorDetail(detail)
  return text
    ? t(`${key}_detail`, { ...params, detail: text })
    : t(key, params)
}

// Localize backend log levels / roles with fallback to the raw value
const localizeOrRaw = (key, raw) => (te(key) ? t(key) : raw)

// Backend INFO log events shown in the chat: localized per event type, raw message otherwise
const LOG_EVENT_KEYS = {
  WORKFLOW_START: 'launch.log_events.workflow_start',
  WORKFLOW_END: 'launch.log_events.workflow_end',
  HUMAN_INTERACTION: 'launch.log_events.human_interaction',
  THINKING_PROCESS: 'launch.log_events.thinking_process',
  MEMORY_OPERATION: 'launch.log_events.memory_operation'
}
// Actionable hint for well-known backend/provider failures (appended after the raw detail)
const ERROR_HINTS = [
  [/MAC_ALLOW_UNSAFE_CODE_EXECUTION/, 'launch.error_hints.python_disabled'],
  [/invalid_api_key|incorrect api key|api key not valid|unauthorized|\b401\b/i, 'launch.error_hints.invalid_api_key'],
  [/rate.?limit|quota|\b429\b/i, 'launch.error_hints.rate_limit'],
  [/model.{0,40}(not found|does not exist)|\b404\b/i, 'launch.error_hints.model_not_found'],
  [/connection (error|refused)|timed? ?out|name or service not known|getaddrinfo|failed to establish/i, 'launch.error_hints.connection']
]
const withErrorHint = (text) => {
  if (typeof text !== 'string' || !text) return text
  const match = ERROR_HINTS.find(([re]) => re.test(text))
  return match ? `${text}\n\n${t(match[1])}` : text
}

const localizeLogMessage = (data) => {
  const key = LOG_EVENT_KEYS[data?.event_type]
  if (key && te(key)) {
    return t(key, { node: data?.node_id || t('launch.unknown_node') })
  }
  return formatErrorDetail(data?.message)
}

// The executor prefixes node inputs with "=== INPUT FROM <source> (<role>) ===".
// Show that header in the UI language (display only; the backend text is unchanged).
const INPUT_HEADER_RE = /^=== INPUT FROM (.+?) \((\w+)\) ===$/gm
const localizeInputHeaders = (text) => {
  if (typeof text !== 'string') return text
  return text.replace(INPUT_HEADER_RE, (_, source, role) => {
    const sourceLabel = source === 'TASK' ? t('launch.input_source_task') : source
    const roleLabel = localizeOrRaw(`launch.roles.${role}`, role)
    return t('launch.input_from_header', { source: sourceLabel, role: roleLabel })
  })
}
const { fromObject, fitView, onPaneReady, onNodesInitialized, setNodes, setEdges, edges } = useVueFlow()

const getTranslatedStatus = (statusText) => {
  if (!statusText) return ''
  // Internal status values (kept in English for logic) -> i18n keys
  const statusKeyMap = {
    'Waiting for workflow selection...': 'launch.status_waiting_workflow',
    'Waiting for file selection...': 'launch.status_waiting_file',
    'Pending workflow selection': 'launch.status_waiting_workflow',
    'Pending file selection': 'launch.status_waiting_file',
    'Connecting...': 'launch.status_connecting',
    'Connected': 'launch.status_connected',
    'Connection error': 'launch.status_connection_error',
    'Disconnected': 'launch.status_disconnected',
    'Waiting for launch...': 'launch.status_waiting_launch',
    'Pending launch': 'launch.status_waiting_launch',
    'Launching...': 'launch.status_launching',
    'Running...': 'launch.status_running',
    'In Progress': 'launch.status_running',
    'Waiting for input...': 'launch.status_waiting_input',
    'Completed': 'launch.status_completed',
    'Cancelled': 'launch.status_cancelled',
    'Failed': 'launch.status_failed',
    'Error': 'launch.status_error'
  }
  const key = statusKeyMap[statusText]
  return key ? localizeOrRaw(key, statusText) : statusText
}

// Task input state
const taskPrompt = ref('')

// File selector state
const workflowFiles = ref([])
const selectedFile = ref('')
const fileSearchQuery = ref('')
const isFileSearchDirty = ref(false)
const isFileDropdownOpen = ref(false)
const fileSelectorWrapperRef = ref(null)
const fileSelectorInputRef = ref(null)

// Status state
const status = ref('Waiting for workflow selection...')
const loading = ref(false)

// Session ID for downloads
let sessionIdToDownload = null

// All notifications and dialogues
const chatMessages = ref([])
const chatMessagesRef = ref(null) // Extra ref

// Map in-progress model/tool call messages by node ID
// Map<nodeId, { message, entryMap, baseKeyToKey, counters }>
const nodesLoadingMessagesMap = new Map()

// Create or fetch the loading bubble for a node
const addTotalLoadingMessage = (nodeId) => {
  if (!nodeId) return null

  let nodeState = nodesLoadingMessagesMap.get(nodeId)
  if (nodeState) return nodeState

  const avatar = avatarFor(nodeId)

  // Use the reactive proxy (not the raw object) so later mutations from
  // nodesLoadingMessagesMap are tracked instead of relying on the 1s timer tick
  const message = reactive({
    type: 'dialogue',
    name: nodeId,
    text: '',
    htmlContent: '',
    avatar,
    isRight: false,
    isLoading: true,
    startedAt: Date.now(),
    timestamp: Date.now(),
    loadingEntries: [],
    rev: 0
  })

  chatMessages.value.push(message)
  scheduleScrollToBottom()

  nodeState = {
    message,
    entryMap: new Map(),
    baseKeyToKey: new Map(),
    counters: new Map()
  }
  nodesLoadingMessagesMap.set(nodeId, nodeState)
  return nodeState
}

// Add a loading entry (model/tool call) and associate it with baseKey
const addLoadingEntry = (nodeId, baseKey, label) => {
  const nodeState = addTotalLoadingMessage(nodeId)
  if (!nodeState || !baseKey) return null

  const count = (nodeState.counters.get(baseKey) || 0) + 1
  nodeState.counters.set(baseKey, count)
  const key = `${baseKey}-${count}`

  const entry = {
    key,
    baseKey,
    label,
    status: 'running',
    startedAt: Date.now(),
    endedAt: null
  }

  nodeState.entryMap.set(key, entry)
  nodeState.baseKeyToKey.set(baseKey, key)
  nodeState.message.loadingEntries.push(entry)
  nodeState.message.rev += 1
  runningLoadingEntries.value += 1
  if (runningLoadingEntries.value === 1) {
    startLoadingTimer()
  }
  // The bubble grew; keep the view pinned to the bottom if the user is there
  scheduleScrollToBottom()
  return entry
}

// Finish a loading entry
const finishLoadingEntry = (nodeId, baseKey) => {
  const nodeState = nodesLoadingMessagesMap.get(nodeId)
  if (!nodeState || !baseKey) return null

  const key = nodeState.baseKeyToKey.get(baseKey)
  const entry = key ? nodeState.entryMap.get(key) : null
  if (!entry) return null

  const wasRunning = entry.status === 'running'
  entry.status = 'done'
  entry.endedAt = Date.now()
  nodeState.baseKeyToKey.delete(baseKey)
  nodeState.message.rev += 1
  if (wasRunning) {
    runningLoadingEntries.value = Math.max(0, runningLoadingEntries.value - 1)
    if (runningLoadingEntries.value === 0) {
      stopLoadingTimer()
    }
  }
  return entry
}

// Finish all running entries when a node ends or cancels
const finalizeAllLoadingEntries = (nodeState, endedAt = Date.now()) => {
  if (!nodeState) return
  let finishedCount = 0
  for (const entry of nodeState.entryMap.values()) {
    if (entry.status === 'running') {
      entry.status = 'done'
      entry.endedAt = endedAt
      finishedCount += 1
    }
  }
  nodeState.baseKeyToKey.clear()
  if (finishedCount) {
    nodeState.message.rev += 1
    runningLoadingEntries.value = Math.max(0, runningLoadingEntries.value - finishedCount)
    if (runningLoadingEntries.value === 0) {
      stopLoadingTimer()
    }
  }
}

// Global timer for updating loading bubble durations
const now = ref(Date.now())
let loadingTimerInterval = null
const runningLoadingEntries = ref(0)

const startLoadingTimer = () => {
  if (loadingTimerInterval) return
  loadingTimerInterval = setInterval(() => {
    now.value = Date.now()
  }, 1000)
}

const stopLoadingTimer = () => {
  if (!loadingTimerInterval) return
  clearInterval(loadingTimerInterval)
  loadingTimerInterval = null
}

// Map sprites for different roles (script-only lookup table; no reactivity needed)
const nameToSpriteMap = new Map()

// Map node IDs to sprites for graph display
const nodeSpriteMap = ref(new Map())

// Stable avatar for any sender: a workflow node uses its bound mascot, other senders
// (subgraph nodes, artifacts) get a deterministic character instead of a random one.
const avatarFor = (name) => {
  const key = name || ''
  if (nameToSpriteMap.has(key)) return nameToSpriteMap.get(key)
  // The user is not a node: keep a free-floating character so no node loses its own
  const avatar = key === USER_SENDER ? spriteFetcher.fetchSprite() : spriteFetcher.fetchSprite(key || null, 'D', 1)
  nameToSpriteMap.set(key, avatar)
  return avatar
}

// Chat avatars follow the current bindings, so a mascot edited in the workflow
// editor (even in another tab) updates every past message immediately.
const messageAvatar = (message) => nodeSpriteMap.value.get(message.name) || message.avatar

// Rebind every node of the workflow to its mascot and publish one fresh sprite map
// (a single reactive swap: graph, kanban, dashboard and office all update at once).
let lastYamlSource = ''
const applyWorkflowSprites = (nodes, source = '') => {
  lastYamlSource = source
  spriteFetcher.bindNodes(Array.isArray(nodes) ? nodes : [])
  nameToSpriteMap.clear()
  const next = new Map()
  for (const node of Array.isArray(nodes) ? nodes : []) {
    if (node?.id) next.set(node.id, spriteFetcher.fetchSprite(node.id, 'D', 1))
  }
  nodeSpriteMap.value = next
}

// Pick up edits saved in the workflow editor (usually another tab) without a reload:
// mascots, node list and the drawn graph refresh in place and the chat is kept.
let workflowRefreshSeq = 0
let workflowRefreshTimer = null
let pendingGraphRefresh = false
const refreshSelectedWorkflow = async ({ graphChanged = false } = {}) => {
  const fileName = selectedFile.value
  if (!fileName) return
  const seq = ++workflowRefreshSeq
  try {
    const source = await fetchWorkflowYAML(fileName)
    if (seq !== workflowRefreshSeq || selectedFile.value !== fileName) return
    const yamlChanged = source !== lastYamlSource || nodeSpriteMap.value.size === 0
    if (yamlChanged) {
      const parsed = yaml.load(source) || {}
      workflowYaml.value = parsed
      applyWorkflowSprites(parsed?.graph?.nodes, source)
    }
    // A running / finished session keeps its node states; only drafts redraw the graph
    if ((yamlChanged || graphChanged) && !hasLaunched.value) {
      await loadVueFlowGraph()
    }
  } catch (error) {
    console.warn('Failed to refresh workflow after an external change:', error)
  }
}

const scheduleWorkflowRefresh = ({ graphChanged = false } = {}) => {
  pendingGraphRefresh = pendingGraphRefresh || graphChanged
  clearTimeout(workflowRefreshTimer)
  // A save writes the YAML and the graph back to back: coalesce them into one refresh
  workflowRefreshTimer = setTimeout(() => {
    const graph = pendingGraphRefresh
    pendingGraphRefresh = false
    refreshSelectedWorkflow({ graphChanged: graph })
  }, 120)
}

const handleWorkflowChanged = (detail) => {
  if (!detail?.key || !selectedFile.value) return
  if (workflowKey(detail.key) !== workflowKey(selectedFile.value)) return
  scheduleWorkflowRefresh({ graphChanged: detail.kind === 'graph' })
}
let stopWorkflowSync = null

// Input glow state
const shouldGlow = ref(false)
const taskInputRef = ref(null)
const attachmentInputRef = ref(null)
const uploadProgressText = ref('')
const uploadedAttachments = ref([])
const isDragActive = ref(false)
const showAttachmentPopover = ref(false)
const showAttachMenu = ref(false)
const attachMenuRef = ref(null)
// Thumbnails (object URLs) for attached images, keyed by attachmentId
const attachmentPreviews = ref({})
const isUploadingAttachment = ref(false)
let attachmentHoverTimeout = null
const selectedArtifactImage = ref(null)
let dragDepth = 0

// Recording state
const isRecording = ref(false)
let mediaRecorder = null
let audioChunks = []
let audioStream = null

// WebSocket readiness state
const isConnectionReady = ref(false)
const showSettingsModal = ref(false)

// View mode: 'chat' | 'graph' | 'office'
const viewMode = ref('chat')
// 2D office view: agents of the selected workflow, driven by the run events below
const officeRef = ref(null)
const officeGraph = computed(() => workflowYaml.value?.graph || {})
const isChatPanelOpen = ref(true)
const isRightPanelOpen = ref(true)

// Task board (Kanban per workflow step) and dashboard: both read this run record,
// fed by the same events as the chat and the office (replays included).
const runTracker = createRunTracker()
const workflowTitle = computed(() => (selectedFile.value ? selectedFile.value.replace(/\.ya?ml$/i, '') : ''))
// Mounted on first use only, then kept so switching views is instant
const visitedViews = reactive({ board: false, dashboard: false, review: false })
watch(viewMode, (mode) => {
  if (mode in visitedViews) visitedViews[mode] = true
}, { immediate: true })
// Content stays clear of the chat panel that floats over the canvas
const insetStyle = computed(() => ({ '--inset-left': isChatPanelOpen.value ? 'min(380px, 50%)' : '0px' }))

// ---------------------------------------------------------------- session history
// Every launched run is saved by the backend; the sidebar lists them so the user can
// switch between runs and reopen one later (after a reload or a server restart).
const SIDEBAR_OPEN_KEY = 'agentdev.sessions.sidebarOpen'
const LAST_SESSION_KEY = 'agentdev.launch.lastSession'
const readStorage = (key) => {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
const writeStorage = (key, value) => {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    // per-browser convenience only
  }
}

const sessions = ref([])
const isSessionSidebarOpen = ref(readStorage(SIDEBAR_OPEN_KEY) !== '0')
watch(isSessionSidebarOpen, (open) => writeStorage(SIDEBAR_OPEN_KEY, open ? '1' : '0'))

// The URL carries the open session (?session=...), so it is the single source of truth
const activeSessionId = computed(() => {
  const value = route.query?.session
  return typeof value === 'string' ? value : ''
})
const draftWorkflow = computed(() => (activeSessionId.value ? '' : selectedFile.value || ''))
const currentSessionTitle = computed(() => {
  const current = sessions.value.find((item) => item.session_id === activeSessionId.value)
  return current?.title || t('launch.sessions.untitled')
})

// ---------------------------------------------------------------- projects
// A project is a folder the agent works on. Its sessions are grouped together, and
// each project remembers its own workflow, so moving between projects never changes
// the workflow of another one. A new session in a project starts from the project's
// latest state (copied on the server from its most recent session), not a re-upload.
const PROJECT_WORKFLOWS_KEY = 'agentdev.launch.projectWorkflows'
const readJson = (key) => {
  try {
    const value = JSON.parse(readStorage(key) || 'null')
    return value && typeof value === 'object' ? value : null
  } catch {
    return null
  }
}
const projectWorkflows = ref(readJson(PROJECT_WORKFLOWS_KEY) || {})
const rememberProjectWorkflow = (name, file) => {
  if (!name || !file || projectWorkflows.value[name] === file) return
  projectWorkflows.value = { ...projectWorkflows.value, [name]: file }
  writeStorage(PROJECT_WORKFLOWS_KEY, JSON.stringify(projectWorkflows.value))
}

const stripSlash = (name) => (name || '').replace(/\/+$/, '')
// { name, sessionId, projectId } of the first project attached to a session
const sessionProject = (item) => {
  const project = item?.projects?.[0]
  const name = stripSlash(project?.name)
  return name
    ? { name, sessionId: item.session_id, projectId: project.project_id || '', localPath: project.local_path || '' }
    : null
}

// Project of what is open in this tab ('' for a session without a project folder)
const currentProjectName = ref('')
// The open session has been launched (its workflow is then fixed)
const hasLaunched = ref(false)
// Project to copy into the session that is connecting (see the 'connection' message)
let pendingProject = null

const workflowExists = (file) => !workflowFiles.value.length || workflowFiles.value.some((item) => item.name === file)
const workflowForProject = (name) => {
  const saved = projectWorkflows.value[name]
  if (saved && workflowExists(saved)) return saved
  const latest = sessions.value.find((item) => sessionProject(item)?.name === name && item.yaml_file)
  return latest?.yaml_file || selectedFile.value
}
// Sessions are listed newest first: the first copy found is the project's latest state
const latestProjectSource = (name) =>
  sessions.value
    .map(sessionProject)
    .find((project) => project?.name === name && (project.projectId || project.localPath)) || null

const newSessionLabel = computed(() =>
  currentProjectName.value
    ? t('launch.sessions.new_in_project', {
        name: currentProjectName.value,
        workflow: (workflowForProject(currentProjectName.value) || '').replace(/\.ya?ml$/i, '')
      })
    : t('launch.sessions.new')
)
const workflowHint = computed(() => {
  if (!selectedFile.value) return ''
  if (hasLaunched.value && !isWorkflowRunning.value) return t('launch.sessions.workflow_locked_hint')
  if (currentProjectName.value) return t('launch.sessions.project_workflow_hint', { name: currentProjectName.value })
  return ''
})

// ---------------------------------------------------------------- composer per session
// What was typed (and attached) but not sent yet stays with its session while you
// work in another one.
const composerDrafts = new Map()
const composerKey = (project = currentProjectName.value, file = selectedFile.value) =>
  activeSessionId.value || (file ? `draft:${project}:${file}` : '')
const stashComposer = () => {
  const key = composerKey()
  if (!key) return
  const prompt = taskPrompt.value
  // Uploads belong to their session id; only a saved session can get them back
  const attachments = activeSessionId.value ? uploadedAttachments.value.map((item) => ({ ...item })) : []
  if (prompt.trim() || attachments.length) composerDrafts.set(key, { prompt, attachments })
  else composerDrafts.delete(key)
}
const takeComposer = (key) => {
  const value = composerDrafts.get(key) || null
  composerDrafts.delete(key)
  return value
}

// ---------------------------------------------------------------- background sessions
// Runs keep going on the server while another session is open here. Watch their
// status and say when one needs an answer or has finished.
const LIVE_STATUSES = new Set(['running', 'waiting_for_input'])
const knownStatuses = new Map()
let statusesPrimed = false
const notifyBackgroundChanges = (list) => {
  for (const item of list) {
    const previous = knownStatuses.get(item.session_id)
    knownStatuses.set(item.session_id, item.status)
    if (!statusesPrimed || !previous || previous === item.status) continue
    if (item.session_id === activeSessionId.value) continue
    const title = item.title || t('launch.sessions.untitled')
    const project = sessionProject(item)?.name
    const name = project ? `${project} · ${title}` : title
    const action = { label: t('launch.sessions.menu.open'), run: () => openSession(item) }
    if (item.status === 'waiting_for_input') {
      toast.warning(t('launch.sessions.bg_waiting', { name }), { action, duration: 15000 })
    } else if (item.status === 'completed') {
      toast.success(t('launch.sessions.bg_completed', { name }), { action, duration: 8000 })
    } else if (item.status === 'error') {
      toast.error(t('launch.sessions.bg_error', { name }), { action, duration: 12000 })
    }
  }
  statusesPrimed = true
}
const waitingElsewhere = computed(
  () => sessions.value.filter((item) => item.status === 'waiting_for_input' && item.session_id !== activeSessionId.value).length
)
const BASE_TITLE = document.title
watch(waitingElsewhere, (count) => {
  document.title = count ? `(${count}) ${BASE_TITLE}` : BASE_TITLE
})

let sessionsPollTimer = null
let sessionsRefreshTimer = null
const refreshSessions = async () => {
  try {
    const list = await fetchSessions()
    sessions.value = list
    notifyBackgroundChanges(list)
  } catch (error) {
    console.warn('Failed to load sessions:', error)
  }
}
// Coalesce bursts of status changes into one request
const scheduleSessionsRefresh = () => {
  clearTimeout(sessionsRefreshTimer)
  sessionsRefreshTimer = setTimeout(refreshSessions, 400)
}
// Poll often while a run is live (here or in the background), slowly otherwise
const schedulePoll = () => {
  clearTimeout(sessionsPollTimer)
  const live = sessions.value.some((item) => LIVE_STATUSES.has(item.status))
  sessionsPollTimer = setTimeout(async () => {
    if (document.visibilityState === 'visible') await refreshSessions()
    schedulePoll()
  }, live ? 4000 : 15000)
}
const onVisibilityChange = () => {
  if (document.visibilityState !== 'visible') return
  refreshSessions()
  // Edits made elsewhere (another browser, a teammate) show up when the tab is back
  if (isPageReady) scheduleWorkflowRefresh()
}

// WebSocket reference
let ws = null
let sessionId = null

const filteredWorkflowFiles = computed(() => {
  // If the file search box is untouched, return all workflows
  if (!isFileSearchDirty.value) {
    return workflowFiles.value
  }
  const query = fileSearchQuery.value.trim().toLowerCase()
  if (!query) {
    return workflowFiles.value
  }
  return workflowFiles.value.filter((workflow) =>
    workflow.name?.toLowerCase().includes(query)
  )
})

// While the workflow is working the composer button turns into a Stop button
const isStopMode = computed(() => isWorkflowRunning.value && status.value === 'Running...')

// Button label computed property
const buttonLabel = computed(() => {
  if (isStopMode.value) {
    return t('common.cancel')
  }
  if (isWorkflowRunning.value) {
    return t('launch.send')
  }
  if (status.value === 'Completed' || status.value === 'Cancelled') {
    return t('launch.relaunch')
  }
  return t('launch.launch_button')
})

const setAttachmentPreview = (attachmentId, file) => {
  if (!attachmentId || !file?.type?.startsWith('image/')) return
  attachmentPreviews.value[attachmentId] = URL.createObjectURL(file)
}

const dropAttachmentPreview = (attachmentId) => {
  const url = attachmentPreviews.value[attachmentId]
  if (!url) return
  URL.revokeObjectURL(url)
  delete attachmentPreviews.value[attachmentId]
}

const clearUploadedAttachments = () => {
  Object.keys(attachmentPreviews.value).forEach(dropAttachmentPreview)
  showAttachMenu.value = false
  uploadedAttachments.value = []
  showAttachmentPopover.value = false
  if (attachmentInputRef.value) {
    attachmentInputRef.value.value = ''
  }
}

// Reset the WebSocket connection and related state
const resetConnectionState = ({ closeSocket = true, keepSession = false } = {}) => {
  if (closeSocket && ws) {
    try {
      ws.close()
    } catch (closeError) {
      console.warn('Failed to close WebSocket:', closeError)
    }
  }

  ws = null
  isConnectionReady.value = false

  if (!keepSession) {
    sessionId = null
    hasLaunched.value = false
    isWorkflowRunning.value = false
    activeNodes.value = []
    shouldGlow.value = false
    clearUploadedAttachments()
    chatMessages.value = []
    nodesLoadingMessagesMap.clear()
    nameToSpriteMap.clear()
    nodeSpriteMap.value.clear()
    officeRef.value?.reset()
    runTracker.reset()
  }

  if (attachmentHoverTimeout) {
    clearTimeout(attachmentHoverTimeout)
    attachmentHoverTimeout = null
  }
}

// Button state management
const isWorkflowRunning = ref(false)
const isReconnecting = ref(false)

// Active node list
const activeNodes = ref([])
// Hovered node id for highlighting related edges
const hoveredNodeId = ref(null)

const onNodeHover = (nodeId) => {
  hoveredNodeId.value = nodeId || null
}
const onNodeLeave = () => {
  hoveredNodeId.value = null
}

// Current workflow YAML content
const workflowYaml = ref({})

// const goBack = () => {
//   router.push('/workflows')
// }

const applyWorkflowFromRoute = () => {
  let workflowParam = route.query?.workflow || route.query?.file || route.query?.name
  if (Array.isArray(workflowParam)) {
    workflowParam = workflowParam[0]
  }
  if (!workflowParam || typeof workflowParam !== 'string') {
    return
  }

  let fileName = workflowParam.trim()
  if (!fileName) {
    return
  }
  if (!fileName.toLowerCase().endsWith('.yaml')) {
    fileName = `${fileName}.yaml`
  }

  setWorkflowSelection(fileName)
}

const normalizeWorkflowName = (value) => {
  const raw = Array.isArray(value) ? value[0] : value
  if (!raw || typeof raw !== 'string' || !raw.trim()) return ''
  const name = raw.trim()
  return name.toLowerCase().endsWith('.yaml') ? name : `${name}.yaml`
}

// Only shows the workflow; opening a session or draft is always an explicit step
const setWorkflowSelection = (fileName) => {
  selectedFile.value = fileName || ''
  fileSearchQuery.value = fileName || ''
  isFileSearchDirty.value = false
}

// Load workflow list
const loadWorkflows = async () => {
  loading.value = true
  const result = await fetchWorkflowsWithDesc()
  loading.value = false

  if (result.success) {
    workflowFiles.value = result.workflows
    applyWorkflowFromRoute()
  } else {
    console.error('Failed to load workflows:', result.error)
    // client.js returns a fixed English error text, so show the localized message only
    addChatNotification(t('launch.errors.load_workflows_failed'), { type: 'error' })
  }
}

const openFileDropdown = () => {
  if (loading.value || isWorkflowRunning.value) {
    return
  }
  isFileDropdownOpen.value = true
}

const handleFileInputFocus = () => {
  isFileSearchDirty.value = false
  openFileDropdown()
  if (fileSearchQuery.value?.trim()) {
    nextTick(() => fileSelectorInputRef.value?.select())
  }
}

const handleFileInputChange = () => {
  if (loading.value || isWorkflowRunning.value) {
    return
  }
  isFileSearchDirty.value = true
  openFileDropdown()
}

const closeFileDropdown = () => {
  isFileDropdownOpen.value = false
}

const selectWorkflow = (fileName) => {
  if (!fileName) {
    return
  }
  closeFileDropdown()
  // Avoid focusing on element after selection
  fileSelectorInputRef.value?.blur()
  if (fileName === selectedFile.value) {
    resetFileSearchQuery()
    return
  }
  changeWorkflow(fileName)
}

const handleFileInputEnter = () => {
  const [firstMatch] = filteredWorkflowFiles.value
  if (firstMatch) {
    selectWorkflow(firstMatch.name)
  }
}

const resetFileSearchQuery = () => {
  fileSearchQuery.value = selectedFile.value || ''
  isFileSearchDirty.value = false
}

const handleFileInputBlur = () => {
  setTimeout(() => {
    if (!isFileDropdownOpen.value) {
      resetFileSearchQuery()
    }
  }, 120)
}

const autoResizeTaskInput = () => {
  const el = taskInputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`
}

const pickAttachmentFile = () => {
  showAttachMenu.value = false
  handleAttachmentButtonClick()
}

const pickAttachmentFolder = () => {
  showAttachMenu.value = false
  handleFolderButtonClick()
}

const handleClickOutside = (event) => {
  if (showAttachMenu.value && attachMenuRef.value && !attachMenuRef.value.contains(event.target)) {
    showAttachMenu.value = false
  }
  if (
    isFileDropdownOpen.value &&
    fileSelectorWrapperRef.value &&
    !fileSelectorWrapperRef.value.contains(event.target)
  ) {
    closeFileDropdown()
    resetFileSearchQuery()
  }
}

// Add a dialogue entry
const addDialogue = (name, message) => {
  if (message === null || message === undefined) {
    return
  }
  let text
  let htmlContent = null
  if (typeof message === 'string') {
    text = message
  } else if (typeof message === 'object') {
    // Avoid showing "[object Object]" for structured outputs. The JSON code block
    // is built directly (escaped) instead of markdown-parsing the whole dump.
    try {
      const json = JSON.stringify(message, null, 2)
      text = '```json\n' + json + '\n```'
      htmlContent = preformatted(json, 'json')
    } catch {
      text = String(message)
    }
  } else {
    text = String(message)
  }
  if (!text.trim()) {
    return
  }
  const avatar = avatarFor(name)

  const isRight = name === USER_SENDER

  if (htmlContent === null) htmlContent = renderMarkdown(text)
  chatMessages.value.push({
    type: 'dialogue',
    name: name,
    text: text,
    htmlContent,
    avatar: avatar,
    isRight: isRight,
    timestamp: Date.now(),
    rev: 0
  })
  // The user's own message always brings the view back to the bottom
  scheduleScrollToBottom(isRight)
}

// Add a notification (supports levels)
const addChatNotification = (message, { type = 'notification' } = {}) => {
  chatMessages.value.push({
    type,
    message,
    timestamp: Date.now(),
    rev: 0
  })
  scheduleScrollToBottom()
}

// Format a millisecond timestamp as mm:ss
const formatDuration = (startedAt, endedAt = null) => {
  if (!startedAt) {
    return ''
  }
  const end = endedAt ?? now.value
  const totalSeconds = Math.max(0, Math.floor((end - startedAt) / 1000))
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, '0')
  const seconds = String(totalSeconds % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
}

const isAttachmentUploadAllowed = () => {
  if (!isConnectionReady.value || !sessionId || isUploadingAttachment.value) {
    return false
  }
  if (isWorkflowRunning.value && status.value !== 'Waiting for input...') {
    return false
  }
  return true
}

const handleAttachmentButtonClick = () => {
  if (!isAttachmentUploadAllowed()) {
    return
  }
  attachmentInputRef.value?.click()
}

const uploadFiles = async (files) => {
  if (!files || files.length === 0) {
    return
  }

  if (!sessionId) {
    toast.warning(t('launch.alert_session_not_ready'))
    return
  }

  isUploadingAttachment.value = true
  try {
    for (const file of files) {
      try {
        const result = await postFile(sessionId, file)

        if (result?.success && result?.attachmentId) {
          uploadedAttachments.value.push(result)
          setAttachmentPreview(result.attachmentId, file)
        } else {
          console.error('File upload failed:', result)
          toast.error(t('launch.errors.upload_failed', { name: file?.name || '' }))
        }
      } catch (error) {
        console.error('Failed to upload attachment:', error)
        toast.error(errorWithDetail('launch.errors.upload_error', error, { name: file?.name || '' }))
      }
    }
  } finally {
    isUploadingAttachment.value = false
  }
}

const onAttachmentSelected = async (event) => {
  const files = Array.from(event.target?.files || [])
  if (event.target) {
    event.target.value = ''
  }

  if (!files.length) {
    return
  }

  await uploadFiles(files)
}

// "Open folder" works like VS Code: the in-app picker lists folders on this machine
// (served by the local backend, so the browser never asks for file access) and the
// agents then work directly in the chosen folder; nothing is uploaded.
const showFolderPicker = ref(false)
const isOpeningFolder = ref(false)
// Name of a folder dropped on the chat: the picker points it out when it shows up
const folderPickerHint = ref('')

// "Add project" in the sidebar may need a new session for the folder; it is prepared
// once a folder is chosen.
let folderTargetsNewSession = false

const cancelFolderPicker = () => {
  showFolderPicker.value = false
  folderPickerHint.value = ''
  folderTargetsNewSession = false
}

const handleFolderButtonClick = ({ newSession = false } = {}) => {
  folderTargetsNewSession = newSession
  if (!newSession && !isAttachmentUploadAllowed()) {
    return
  }
  showFolderPicker.value = true
}

const onFolderPicked = async (path) => {
  const toNewSession = folderTargetsNewSession
  folderTargetsNewSession = false
  isOpeningFolder.value = true
  try {
    if (toNewSession) {
      showFolderPicker.value = false
      await openDraft(selectedFile.value)
      if (!(await waitForConnection())) {
        toast.warning(t('launch.alert_session_not_ready'))
        return
      }
    }
    if (!sessionId) {
      toast.warning(t('launch.alert_session_not_ready'))
      return
    }
    const result = await openLocalProject(sessionId, path, { yamlFile: selectedFile.value })
    if (!result?.success || !result.attachmentId) {
      toast.error(t('launch.open_folder.failed'), { detail: result?.detail || result?.message || '' })
      return
    }
    showFolderPicker.value = false
    folderPickerHint.value = ''
    uploadedAttachments.value.push(result)
    if (!currentProjectName.value) {
      currentProjectName.value = stripSlash(result.name)
      rememberProjectWorkflow(currentProjectName.value, selectedFile.value)
    }
    if (activeSessionId.value !== sessionId) {
      router.replace({ query: { ...route.query, session: sessionId } })
    }
    scheduleSessionsRefresh()
    toast.success(t('launch.open_folder.opened', { name: stripSlash(result.name) }), {
      detail: t('launch.open_folder.opened_detail', { count: result.fileCount || 0, path: result.localPath })
    })
  } finally {
    isOpeningFolder.value = false
  }
}

// Resolves once the socket of the session being opened is ready (false on timeout)
const waitForConnection = (timeoutMs = 10000) =>
  new Promise((resolve) => {
    if (isConnectionReady.value && sessionId) {
      resolve(true)
      return
    }
    let stop = null
    const timer = setTimeout(() => {
      stop?.()
      resolve(false)
    }, timeoutMs)
    stop = watch(isConnectionReady, (ready) => {
      if (ready && sessionId) {
        clearTimeout(timer)
        stop()
        resolve(true)
      }
    })
  })

const removeAttachment = (attachmentId) => {
  dropAttachmentPreview(attachmentId)
  uploadedAttachments.value = uploadedAttachments.value.filter(
    (attachment) => attachment.attachmentId !== attachmentId
  )
}

const startRecording = async () => {
  if (!isConnectionReady.value || !sessionId || isUploadingAttachment.value || isRecording.value) {
    return
  }

  // Add global listeners to ensure recording stops even if mouse leaves button
  window.addEventListener('mouseup', stopRecordingGlobal)
  window.addEventListener('touchend', stopRecordingGlobal)

  try {
    // Request microphone access
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: true })

    // Check for MP3 support, fallback to webm
    const mimeTypes = ['audio/mpeg', 'audio/wav', 'audio/webm', 'audio/ogg']
    let selectedMimeType = 'audio/webm'

    for (const mimeType of mimeTypes) {
      if (MediaRecorder.isTypeSupported(mimeType)) {
        selectedMimeType = mimeType
        break
      }
    }

    mediaRecorder = new MediaRecorder(audioStream, {
      mimeType: selectedMimeType
    })

    audioChunks = []

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.push(event.data)
      }
    }

    mediaRecorder.onstop = async () => {
      if (audioChunks.length === 0) {
        cleanupRecording()
        return
      }

      // Create blob from audio chunks
      const audioBlob = new Blob(audioChunks, { type: selectedMimeType })

      // Generate filename with current time
      const now = new Date()
      const timestamp = now.toISOString().replace(/[:.]/g, '-').slice(0, -5)
      const filename = `recording_${timestamp}.${selectedMimeType.split('/')[1]}`

      // Create File object from blob
      const audioFile = new File([audioBlob], filename, { type: selectedMimeType })

      // Upload the file
      try {
        isUploadingAttachment.value = true
        const result = await postFile(sessionId, audioFile)

        if (result?.success && result?.attachmentId) {
          uploadedAttachments.value.push(result)
        } else {
          console.error('Recording upload failed:', result)
          toast.error(t('launch.alert_recording_upload_failed'))
        }
      } catch (error) {
        console.error('Failed to upload recording:', error)
        toast.error(t('launch.alert_recording_upload_failed'))
      } finally {
        isUploadingAttachment.value = false
        cleanupRecording()
      }
    }

    mediaRecorder.onerror = (event) => {
      console.error('MediaRecorder error:', event.error)
      toast.error(t('launch.alert_recording_error'))
      cleanupRecording()
    }

    mediaRecorder.start()
    isRecording.value = true
  } catch (error) {
    console.error('Failed to start recording:', error)
    toast.error(t('launch.alert_mic_access_failed'))
    cleanupRecording()
  }
}

const stopRecording = () => {
  if (mediaRecorder && isRecording.value && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop()
    isRecording.value = false
  }
  removeGlobalListeners()
}

const stopRecordingGlobal = () => {
  stopRecording()
}

const removeGlobalListeners = () => {
  window.removeEventListener('mouseup', stopRecordingGlobal)
  window.removeEventListener('touchend', stopRecordingGlobal)
}

const handleMicrophoneMouseLeave = () => {
  // If mouse leaves while recording, don't stop (let global listener handle it)
  // This allows recording to continue if user drags outside button
}

const cleanupRecording = () => {
  removeGlobalListeners()
  if (audioStream) {
    audioStream.getTracks().forEach(track => track.stop())
    audioStream = null
  }
  mediaRecorder = null
  audioChunks = []
  isRecording.value = false
}

const handleAttachmentHover = (isHovering) => {
  if (isHovering) {
    if (attachmentHoverTimeout) {
      clearTimeout(attachmentHoverTimeout)
      attachmentHoverTimeout = null
    }

    if (uploadedAttachments.value.length > 0) {
      showAttachmentPopover.value = true
    }
    return
  }

  if (attachmentHoverTimeout) {
    clearTimeout(attachmentHoverTimeout)
  }

  attachmentHoverTimeout = setTimeout(() => {
    showAttachmentPopover.value = false
    attachmentHoverTimeout = null
  }, 140)
}

const lockBodyScroll = () => {
  if (typeof document !== 'undefined') {
    document.body.style.overflow = 'hidden'
  }
}

const unlockBodyScroll = () => {
  if (typeof document !== 'undefined') {
    document.body.style.overflow = ''
  }
}

const openImageModal = (message) => {
  if (!message || message.loading || !message.dataUri) {
    return
  }
  selectedArtifactImage.value = {
    src: message.dataUri,
    name: message.fileName || t('launch.image_artifact_alt')
  }
  lockBodyScroll()
}

const closeImageModal = () => {
  if (!selectedArtifactImage.value) {
    return
  }
  selectedArtifactImage.value = null
  unlockBodyScroll()
}

const handleKeydown = (event) => {
  if (event.key === 'Escape' && selectedArtifactImage.value) {
    closeImageModal()
  }
}

const handleEnterKey = (e) => {
  if (e.metaKey || e.ctrlKey) {
    // Check disabled state logically similar to button
    if (isStopMode.value || loading.value || (isWorkflowRunning.value && !taskPrompt.value.trim()) || (!isWorkflowRunning.value && status.value !== 'Completed' && status.value !== 'Cancelled' && !isConnectionReady.value)) {
       return
    }
    handleButtonClick()
  }
}

// Handle paste events, including file uploads
const handlePaste = async (event) => {
  // Check if upload is allowed
  if (!isAttachmentUploadAllowed()) {
    return
  }

  // Get clipboard data
  const clipboardData = event.clipboardData
  if (!clipboardData) {
    return
  }

  // Check whether the clipboard contains files
  const files = clipboardData.files
  if (!files || files.length === 0) {
    return
  }

  // Prevent default paste to avoid inserting text
  event.preventDefault()

  // Upload all pasted files
  await uploadFiles(files)
}

const isFileDragEvent = (event) => {
  const types = event?.dataTransfer?.types
  if (!types) {
    return false
  }
  return Array.from(types).includes('Files')
}

const handleDragEnter = (event) => {
  if (!isFileDragEvent(event) || !isAttachmentUploadAllowed()) {
    return
  }
  dragDepth += 1
  isDragActive.value = true
  event.preventDefault()
}

const handleDragOver = (event) => {
  if (!isFileDragEvent(event) || !isAttachmentUploadAllowed()) {
    return
  }
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy'
  }
}

const handleDragLeave = (event) => {
  if (!isFileDragEvent(event)) {
    return
  }
  dragDepth = Math.max(0, dragDepth - 1)
  if (dragDepth === 0) {
    isDragActive.value = false
  }
}

const handleDrop = async (event) => {
  if (!isFileDragEvent(event)) {
    return
  }
  event.preventDefault()
  dragDepth = 0
  isDragActive.value = false

  if (!isAttachmentUploadAllowed()) {
    return
  }

  // Read the DataTransfer synchronously. Loose files are attached; a dropped folder is
  // opened in place through the picker (the drop does not say where it lives on disk).
  const { files, folders } = await collectDroppedItems(event.dataTransfer)
  if (files.length) {
    await uploadFiles(files)
  }
  if (folders.length) {
    folderPickerHint.value = folders[0]
    handleFolderButtonClick()
  }
}

// Handle YAML file selection
const handleYAMLSelection = async (fileName) => {
  if (!fileName) {
    workflowYaml.value = {}
    chatMessages.value = []
    setNodes([])
    setEdges([])
    spriteFetcher.reset()
    nodeSpriteMap.value.clear()
    return
  }

  // Clear the chat
  chatMessages.value = []

  try {
    // Fetch YAML config and emit initial_instructions to the chat
    const yamlContentString = await fetchWorkflowYAML(fileName)
    const parsedYaml = yaml.load(yamlContentString)
    workflowYaml.value = parsedYaml || {}
    const initialInstructions = workflowYaml.value?.graph?.initial_instruction || ''

    if (initialInstructions) {
      addChatNotification(initialInstructions)
    } else {
      addChatNotification(t('launch.no_initial_instructions'))
    }

    // Bind every node to its saved (or stable auto-assigned) mascot, replacing the
    // previous workflow's bindings; binding also preloads each character's frames
    applyWorkflowSprites(workflowYaml.value?.graph?.nodes, yamlContentString)

    // Warm the remaining characters in the background for chat avatars and edge walkers
    spriteFetcher.preloadAll()
  } catch (error) {
    console.error('Failed to load YAML file:', error)
    workflowYaml.value = {}
    addChatNotification(
      errorWithDetail('launch.errors.load_yaml_failed', error, { name: fileName }),
      { type: 'error' }
    )
    nodeSpriteMap.value.clear()
  }

  await loadVueFlowGraph({ fit: viewMode.value === 'graph' })
}

// Handle button clicks
const handleButtonClick = () => {
  if (isWorkflowRunning.value) {
    // If Send, send user input
    sendHumanInput()

    status.value = "Running..."
    shouldGlow.value = false
  } else if (status.value === 'Completed' || status.value === 'Cancelled') {
    // If Relaunch, restart the same workflow and re-enter Launch state
    if (!selectedFile.value) {
      toast.warning(t('launch.alert_choose_workflow'))
      return
    }

    // A new session of the same workflow (and project); the finished one stays in the history
    startNewSession({ project: currentProjectName.value, file: selectedFile.value })
  } else {
    // If Launch, start the workflow
    launchWorkflow()
  }
}

// Send human input
const sendHumanInput = () => {
  if (!ws) {
    return
  }

  const trimmedInput = taskPrompt.value.trim()
  const attachmentIds = uploadedAttachments.value.map((attachment) => attachment.attachmentId)
  const attachmentNames = uploadedAttachments.value.map(
    (attachment) => attachment.name || attachment.attachmentId
  )

  if (!trimmedInput && attachmentIds.length === 0) {
    return
  }

  const message = {
    type: 'human_input',
    data: {
      input: trimmedInput,
      attachments: attachmentIds
    }
  }

  clearUploadedAttachments()
  ws.send(JSON.stringify(message))
  runTracker.inputSent(trimmedInput)

  const fullMessage = []
  if (trimmedInput) {
    fullMessage.push(trimmedInput)
  }
  if (attachmentNames.length) {
    fullMessage.push(t('launch.attachments_line', { names: attachmentNames.join(', ') }))
  }

  if (fullMessage.length) {
    addDialogue(USER_SENDER, fullMessage.join('\n\n'))
  }

  taskPrompt.value = ''
}

// Establish a WebSocket connection
const establishWebSocketConnection = (options = {}) => {
  let { sessionId: reconnectSid, fresh = false } = options

  // If no explicit sessionId, check URL for an existing session
  if (!reconnectSid && !fresh) {
    const urlSession = route.query?.session
    if (urlSession && typeof urlSession === 'string' && urlSession.trim()) {
      reconnectSid = urlSession.trim()
    }
  }

  const reconnecting = !!reconnectSid

  if (reconnecting) {
    isReconnecting.value = true
    resetConnectionState({ closeSocket: true, keepSession: true })
    status.value = 'Connecting...'
  } else {
    resetConnectionState()
    if (!selectedFile.value) {
      return
    }
  }

  const apiBase = import.meta.env.VITE_API_BASE_URL || ''
  // Defaults: same-origin (works with Vite dev proxy)
  const defaultScheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  let scheme = defaultScheme
  let host = window.location.host

  // In production, prefer explicit API base if provided
  if (!import.meta.env.DEV && apiBase) {
    try {
      const api = new URL(apiBase, window.location.origin)
      scheme = api.protocol === 'https:' ? 'wss:' : 'ws:'
      host = api.host
    } catch {
      // keep defaults
    }
  }

  const wsUrl = reconnecting
    ? `${scheme}//${host}/ws?session_id=${encodeURIComponent(reconnectSid)}`
    : `${scheme}//${host}/ws`
  const socket = new WebSocket(wsUrl)
  ws = socket

  socket.onopen = () => {
    // Ignore events from stale sockets
    if (ws !== socket) return
  }

  socket.onmessage = (event) => {
    // Ignore messages from sockets that are no longer current
    if (ws !== socket) return

    let msg
    try {
      msg = JSON.parse(event.data)
    } catch (parseError) {
      console.warn('Ignoring malformed WebSocket message:', parseError)
      return
    }
    if (!msg || typeof msg !== 'object') return

    if (msg.type === 'connection') {
      sessionId = msg.data?.session_id || null

      if (!sessionId) {
        status.value = 'Connection error'
        toast.error(t('launch.errors.missing_session'))
        resetConnectionState()
        return
      }

      isConnectionReady.value = true

      if (isReconnecting.value && !msg.data?.resumed) {
        // Nothing saved under that id (deleted or expired): continue as a new session
        isReconnecting.value = false
        currentProjectName.value = ''
        const { session: _staleSession, ...query } = route.query
        router.replace({ query })
        if (selectedFile.value) {
          handleYAMLSelection(selectedFile.value)
        }
      }

      // For new connections, set initial state; reconnections are handled by session_resumed
      if (!isReconnecting.value) {
        shouldGlow.value = true
        status.value = 'Waiting for launch...'
        nextTick(() => {
          taskInputRef.value?.focus()
        })
        // New session in a project: bring the project's latest state into it
        if (pendingProject) {
          const source = pendingProject
          pendingProject = null
          bringProjectIntoSession(source)
        }
      }
    } else {
      processMessage(msg)
    }
  }

  socket.onerror = (error) => {
    // Ignore errors from sockets that are no longer current
    if (ws !== socket) return

    console.error('WebSocket error:', error)
    status.value = 'Connection error'
    toast.error(t('launch.errors.ws_connection'))
    resetConnectionState({ closeSocket: false })
  }

  socket.onclose = () => {
    // Ignore close events from sockets that are no longer current
    if (ws !== socket) return

    if (status.value === 'Running...') {
      status.value = 'Disconnected'
    } else if (status.value === 'Connecting...' || status.value === 'Waiting for launch...') {
      status.value = 'Disconnected'
    }
    resetConnectionState({ closeSocket: false })
  }
}

// Open a saved session: the backend replays its messages, then session_resumed
// restores the workflow, status and active node
// The run of the session you leave keeps going on the server; its messages are
// replayed when you come back to it.
const openSession = async (item) => {
  if (!item?.session_id) return
  if (item.session_id === activeSessionId.value && isConnectionReady.value) return
  stashComposer()
  resetConnectionState()
  pendingProject = null
  // Set before the URL changes so the route watch does not open a draft
  isReconnecting.value = true
  status.value = 'Connecting...'
  taskPrompt.value = ''
  currentProjectName.value = sessionProject(item)?.name || ''
  if (item.yaml_file) setWorkflowSelection(item.yaml_file)
  await router.replace({ query: { ...route.query, workflow: item.yaml_file, session: item.session_id } })
  establishWebSocketConnection({ sessionId: item.session_id })
}

// Open an empty session of a workflow; with a source, the project comes along
const openDraft = async (file, { project = '', source = null } = {}) => {
  stashComposer()
  isReconnecting.value = false
  resetConnectionState()
  currentProjectName.value = project
  pendingProject = source
  setWorkflowSelection(file)
  const query = { ...route.query, workflow: file }
  delete query.session
  await router.replace({ query })
  status.value = 'Connecting...'
  taskPrompt.value = takeComposer(composerKey(project, file))?.prompt || ''
  handleYAMLSelection(file)
  establishWebSocketConnection({ fresh: true })
}

const bringProjectIntoSession = async (source) => {
  const targetSession = sessionId
  isUploadingAttachment.value = true
  uploadProgressText.value = t('launch.sessions.project_copying', { name: source.name })
  try {
    // A folder opened in place is simply opened again; an uploaded copy is cloned
    const result = source.localPath
      ? await openLocalProject(targetSession, source.localPath, { yamlFile: selectedFile.value })
      : await cloneProjectIntoSession(targetSession, {
          sourceSessionId: source.sessionId,
          projectId: source.projectId,
          yamlFile: selectedFile.value
        })
    if (targetSession !== sessionId) return // the user moved on meanwhile
    if (result?.success && result.attachmentId) {
      uploadedAttachments.value.push(result)
      await router.replace({ query: { ...route.query, session: targetSession } })
      scheduleSessionsRefresh()
      addChatNotification(t('launch.sessions.project_continued', { name: source.name }))
    } else {
      currentProjectName.value = ''
      toast.error(t('launch.sessions.project_copy_failed', { name: source.name }), {
        detail: result?.detail || result?.message || ''
      })
    }
  } finally {
    uploadProgressText.value = ''
    isUploadingAttachment.value = false
  }
}

/**
 * Start a new session.
 * - no target: where you are now (same project, its workflow; else the same workflow)
 * - a sidebar group: in that project (with its own workflow) or with that workflow
 * - { project, file }: explicit; a missing file falls back to the project's workflow
 */
const startNewSession = async (target = null) => {
  const isGroup = target && typeof target === 'object' && 'isProject' in target
  let project
  let file
  if (isGroup) {
    project = target.isProject ? target.label : ''
    file = target.isProject ? '' : target.workflow
  } else if (target && typeof target === 'object') {
    project = target.project || ''
    file = target.file || ''
  } else {
    project = currentProjectName.value
    file = ''
  }
  if (!file) file = project ? workflowForProject(project) : selectedFile.value
  if (!file) {
    isRightPanelOpen.value = true
    toast.info(t('launch.sessions.pick_workflow'))
    nextTick(() => fileSelectorInputRef.value?.focus())
    return
  }
  // Already in a fresh session of that project and workflow: no second empty one
  if (
    !hasLaunched.value &&
    isConnectionReady.value &&
    !isUploadingAttachment.value &&
    project === currentProjectName.value &&
    file === selectedFile.value
  ) {
    nextTick(() => taskInputRef.value?.focus())
    return
  }
  let source = null
  if (project) {
    source = latestProjectSource(project)
    if (!source) {
      toast.info(t('launch.sessions.project_missing', { name: project }))
    }
  }
  await openDraft(file, { project: source ? project : '', source })
}

// ---------------------------------------------------------------- review & rework
// Finished runs nobody has accepted or sent back yet (badge on the "Review" view)
const reviewPendingCount = computed(
  () => sessions.value.filter((s) => s.status === 'completed' && (s.review?.verdict || 'pending') === 'pending').length
)
const isReworking = ref(false)

// Resolves true once `predicate` holds, false after `timeoutMs`
const waitUntil = (predicate, timeoutMs) =>
  new Promise((resolve) => {
    if (predicate()) {
      resolve(true)
      return
    }
    let stop = null
    const timer = setTimeout(() => {
      stop?.()
      resolve(false)
    }, timeoutMs)
    stop = watch(predicate, (ok) => {
      if (!ok) return
      clearTimeout(timer)
      stop()
      resolve(true)
    })
  })

const openSessionInChat = async (item) => {
  await openSession(item)
  viewMode.value = 'chat'
}

// "Request rework": a new run of the same workflow in the same project (its latest
// state, or the folder opened in place), started with the reviewer's feedback; the
// reviewed run then points at it so the rounds stay linked.
const handleRework = async ({ session, prompt, review, round }) => {
  if (isWorkflowRunning.value) {
    toast.warning(t('launch.sessions.add_project_busy'))
    return
  }
  isReworking.value = true
  try {
    const project = stripSlash(session.projects?.[0]?.name || '')
    await startNewSession({ project, file: session.yaml_file })
    const ready = await waitUntil(
      () =>
        isConnectionReady.value &&
        !!sessionId &&
        !isUploadingAttachment.value &&
        (!currentProjectName.value || uploadedAttachments.value.some((item) => item.kind === 'project')),
      60000
    )
    if (!ready) throw new Error(t('launch.alert_session_not_ready'))
    taskPrompt.value = prompt
    await launchWorkflow()
    if (!hasLaunched.value || !sessionId) throw new Error(t('launch.alert_session_not_ready'))
    await saveSessionReview(session.session_id, { ...review, rework_session_id: sessionId })
    await refreshSessions()
    toast.success(t('launch.review.rework_started', { n: round }))
    viewMode.value = 'board'
  } catch (error) {
    toast.error(t('launch.review.rework_failed'), { detail: formatErrorDetail(error?.message || error) })
  } finally {
    isReworking.value = false
  }
}

// The user picked another workflow in the right panel
const changeWorkflow = async (file) => {
  if (!file || file === selectedFile.value) return
  if (currentProjectName.value) rememberProjectWorkflow(currentProjectName.value, file)
  if (!hasLaunched.value && ws && isConnectionReady.value) {
    // Still a draft: keep this session and what is attached to it, only switch the workflow
    setWorkflowSelection(file)
    await router.replace({ query: { ...route.query, workflow: file } })
    handleYAMLSelection(file)
    if (activeSessionId.value) {
      updateSessionWorkflow(activeSessionId.value, file)
        .then(scheduleSessionsRefresh)
        .catch((error) => console.warn('Failed to update the draft workflow:', error))
    }
    return
  }
  // A launched session keeps the workflow it ran with: continue in a new session
  await startNewSession({ project: currentProjectName.value, file })
}

// Add a project to work on. A fresh, empty session takes it; otherwise (a launched run,
// or a session that already has a project) the folder gets a session of its own, so
// several projects can be worked on side by side.
const handleAddProject = () => {
  if (!selectedFile.value) {
    isRightPanelOpen.value = true
    toast.info(t('launch.sessions.add_project_pick_workflow'))
    nextTick(() => fileSelectorInputRef.value?.focus())
    return
  }
  if (isUploadingAttachment.value) {
    toast.info(t('launch.sessions.add_project_busy'))
    return
  }
  const reuseCurrent = !hasLaunched.value && isConnectionReady.value && !currentProjectName.value
  handleFolderButtonClick({ newSession: !reuseCurrent })
}

const handleRenameSession = async (item, title) => {
  const previous = item.title
  item.title = title
  try {
    await renameSession(item.session_id, title)
  } catch (error) {
    item.title = previous
    toast.error(t('errors.api.sessions_failed'), { detail: formatErrorDetail(error) })
  }
}

const handleDeleteSession = async (item) => {
  if (['running', 'waiting_for_input'].includes(item.status)) {
    toast.warning(t('launch.sessions.delete_running'))
    return
  }
  const confirmed = await confirmDialog({
    title: t('launch.sessions.delete_title', { title: item.title || t('launch.sessions.untitled') }),
    message: t('launch.sessions.delete_detail'),
    confirmText: t('launch.sessions.delete'),
    tone: 'danger'
  })
  if (!confirmed) {
    return
  }
  try {
    await deleteSession(item.session_id)
  } catch (error) {
    toast.error(t('errors.api.sessions_failed'), { detail: formatErrorDetail(error) })
    return
  }
  sessions.value = sessions.value.filter((entry) => entry.session_id !== item.session_id)
  if (item.session_id === activeSessionId.value) {
    startNewSession({ project: sessionProject(item)?.name || '', file: item.yaml_file })
  }
}

// Right-click "Delete project": remove every session of a sidebar group in one go.
// Running sessions are kept (the backend refuses to delete them anyway).
const handleDeleteGroup = async (group) => {
  const items = group?.items || []
  const running = items.filter((item) => ['running', 'waiting_for_input'].includes(item.status))
  const deletable = items.filter((item) => !running.includes(item))
  if (!deletable.length) {
    toast.warning(t('launch.sessions.delete_running'))
    return
  }
  const confirmed = await confirmDialog({
    title: t('launch.sessions.delete_group_title', { name: group.label }),
    message: t('launch.sessions.delete_group_detail', { n: deletable.length }),
    confirmText: group.isProject ? t('launch.sessions.menu.delete_project') : t('launch.sessions.menu.delete_group'),
    tone: 'danger'
  })
  if (!confirmed) {
    return
  }
  const deleted = new Set()
  for (const item of deletable) {
    try {
      await deleteSession(item.session_id)
      deleted.add(item.session_id)
    } catch (error) {
      toast.error(t('errors.api.sessions_failed'), { detail: formatErrorDetail(error) })
    }
  }
  sessions.value = sessions.value.filter((entry) => !deleted.has(entry.session_id))
  if (running.length) {
    toast.info(t('launch.sessions.delete_group_running', { n: running.length }))
  }
  if (deleted.has(activeSessionId.value)) {
    startNewSession({ project: '', file: group.workflow || selectedFile.value })
  }
}

// Remember what is open so returning to this page continues there
watch([selectedFile, activeSessionId], ([file, sid]) => {
  if (!file) return
  writeStorage(LAST_SESSION_KEY, JSON.stringify({ workflow: file, session: sid || null }))
})
watch(status, scheduleSessionsRefresh)

// Watch for file selection changes
// Keep the textarea height in sync when the prompt is cleared or replaced from code
watch(taskPrompt, () => nextTick(autoResizeTaskInput))


watch(
  () => uploadedAttachments.value.length,
  (length) => {
    if (!length) {
      showAttachmentPopover.value = false
    }
  }
)

// Arriving here with another workflow in the URL (e.g. from the workflow list) opens a
// draft of it. Changes made by this page set the selection first, so they are no-ops.
let isPageReady = false
watch(
  () => route.query?.workflow,
  (value) => {
    const file = normalizeWorkflowName(value)
    if (!isPageReady || !file || file === selectedFile.value || isReconnecting.value) return
    openDraft(file)
  }
)

onMounted(async () => {
  document.addEventListener('click', handleClickOutside)
  document.addEventListener('keydown', handleKeydown)
  chatMessagesRef.value?.addEventListener('scroll', handleChatScroll, { passive: true })
  document.addEventListener('visibilitychange', onVisibilityChange)
  stopWorkflowSync = onWorkflowChanged(handleWorkflowChanged)
  refreshSessions().finally(schedulePoll)
  // Coming back to the page without a target: reopen the session that was open last time
  if (!route.query?.workflow && !route.query?.session) {
    try {
      const last = JSON.parse(readStorage(LAST_SESSION_KEY) || 'null')
      if (last?.workflow) {
        await router.replace({
          query: { ...route.query, workflow: last.workflow, ...(last.session ? { session: last.session } : {}) }
        })
      }
    } catch {
      // ignore a malformed entry
    }
  }
  await loadWorkflows()
  // A session in the URL is reopened (its replay restores workflow, project and status);
  // otherwise a draft of the selected workflow is prepared.
  const sessionParam = route.query?.session
  if (sessionParam && typeof sessionParam === 'string' && sessionParam.trim()) {
    establishWebSocketConnection({ sessionId: sessionParam.trim() })
  } else if (selectedFile.value) {
    openDraft(selectedFile.value)
  } else {
    status.value = 'Waiting for workflow selection...'
  }
  isPageReady = true
})

onUnmounted(() => {
  clearTimeout(sessionsPollTimer)
  clearTimeout(sessionsRefreshTimer)
  clearTimeout(workflowRefreshTimer)
  stopWorkflowSync?.()
  document.removeEventListener('visibilitychange', onVisibilityChange)
  document.title = BASE_TITLE
  document.removeEventListener('click', handleClickOutside)
  document.removeEventListener('keydown', handleKeydown)
  chatMessagesRef.value?.removeEventListener('scroll', handleChatScroll)
  if (scrollRafId !== null) {
    cancelAnimationFrame(scrollRafId)
    scrollRafId = null
  }
  unlockBodyScroll()
  resetConnectionState()
  cleanupRecording()
  removeSpriteWalkerLayer()

  stopLoadingTimer()
  runningLoadingEntries.value = 0
})


// Fit the view after the pane is ready or nodes are initialized
onPaneReady(() => {
  requestAnimationFrame(() => fitView?.({ padding: 0.1 }))
})
onNodesInitialized(() => {
  requestAnimationFrame(() => fitView?.({ padding: 0.1 }))
})

const syncNodeAndEdgeData = () => {
  try {
    const yamlNodes = workflowYaml.value?.graph?.nodes || []
    const yamlEdges = workflowYaml.value?.graph?.edges || []

    const yamlNodeById = new Map(
      Array.isArray(yamlNodes) ? yamlNodes.map(node => [node.id, node]) : []
    )
    const yamlEdgeByKey = new Map(
      Array.isArray(yamlEdges)
        ? yamlEdges.map(edge => [`${edge.from}-${edge.to}`, edge])
        : []
    )

    setNodes(existingNodes => {
      if (!Array.isArray(existingNodes)) {
        return existingNodes
      }
      return existingNodes.map(node => {
        const yamlNode = yamlNodeById.get(node.id)
        if (yamlNode) {
          return {
            ...node,
            data: yamlNode
          }
        }
        return node
      })
    })

    setEdges(existingEdges => {
      if (!Array.isArray(existingEdges)) {
        return existingEdges
      }
      return existingEdges.map(edge => {
        const key = `${edge.source}-${edge.target}`
        const yamlEdge = yamlEdgeByKey.get(key)
        if (yamlEdge) {
          return {
            ...edge,
            data: yamlEdge,
            markerEnd: {
              type: MarkerType.Arrow,
              width: 18,
              height: 18,
              color: 'var(--text-1)',
              strokeWidth: 2,
            }
          }
        }
        return edge
      })
    })
  } catch (error) {
    console.error('Failed to sync graph data with YAML:', error)
  }
}

const generateNodesAndEdges = async ({ fit = false } = {}) => {
  try {
    const yamlNodes = Array.isArray(workflowYaml.value?.graph?.nodes)
      ? workflowYaml.value.graph.nodes
      : []
    const yamlEdges = Array.isArray(workflowYaml.value?.graph?.edges)
      ? workflowYaml.value.graph.edges
      : []

    const generatedNodes = yamlNodes.map((node, index) => ({
      id: node.id,
      type: 'workflow-node',
      label: node.id,
      position: {
        x: 20 + (index % 5) * 200,
        y: 10 + Math.floor(index / 5) * 150
      },
      data: node
    }))

    const generatedEdges = yamlEdges.map(edge => ({
      id: `${edge.from}-${edge.to}`,
      source: edge.from,
      target: edge.to,
      type: 'workflow-edge',
      markerEnd: {
        type: MarkerType.Arrow,
        width: 18,
        height: 18,
        color: 'var(--text-1)',
        strokeWidth: 2,
      },
      data: edge
    }))

    setNodes(generatedNodes)
    setEdges(generatedEdges)
  } catch (error) {
    console.error('Error generating nodes and edges from YAML:', error)
  }

  if (fit && viewMode.value === 'graph') {
    await nextTick()
    fitView?.({ padding: 0.1 })
  }
}

const loadVueFlowGraph = async ({ fit = false } = {}) => {
  const selectionSnapshot = selectedFile.value
  const shouldFit = fit && viewMode.value === 'graph'

  const runFallback = async () => {
    if (selectedFile.value === selectionSnapshot) {
      await generateNodesAndEdges({ fit: shouldFit })
    }
    return false
  }

  if (!selectionSnapshot) {
    return await runFallback()
  }

  const key = selectionSnapshot.replace(/\.yaml$/i, '')
  if (!key) {
    return await runFallback()
  }

  try {
    const result = await fetchVueGraph(key)

    if (selectedFile.value !== selectionSnapshot) {
      return false
    }

    if (result?.status === 404) {
      return await runFallback()
    }

    if (!result?.success) {
      console.error('Failed to load VueFlow graph:', result?.message || result?.detail)
      return await runFallback()
    }

    if (selectedFile.value !== selectionSnapshot) {
      return false
    }

    const content = result?.content

    if (!content) {
      return await runFallback()
    }

    let flow
    try {
      flow = JSON.parse(content)
    } catch (parseError) {
      console.error('Failed to parse saved VueFlow graph:', parseError)
      return await runFallback()
    }

    fromObject?.(flow)
    await nextTick()

    if (selectedFile.value !== selectionSnapshot) {
      return false
    }

    syncNodeAndEdgeData()

    if (shouldFit) {
      await nextTick()

      if (selectedFile.value !== selectionSnapshot) {
        return false
      }

      fitView?.({ padding: 0.1 })
    }

    return true
  } catch (error) {
    console.error('Failed to load VueFlow graph:', error)
  }

  return await runFallback()
}

const switchToGraph = async () => {
  viewMode.value = 'graph'
  await nextTick()
  await loadVueFlowGraph({ fit: true })
}

const launchWorkflow = async () => {
  if (!selectedFile.value) {
    toast.warning(t('launch.alert_choose_workflow'))
    return
  }

  const trimmedPrompt = taskPrompt.value.trim()
  const attachmentIds = uploadedAttachments.value.map((attachment) => attachment.attachmentId)
  const attachmentNames = uploadedAttachments.value.map(
    (attachment) => attachment.name || attachment.attachmentId
  )

  if (!trimmedPrompt && attachmentIds.length === 0) {
    toast.warning(t('launch.alert_enter_prompt'))
    return
  }

  if (
    !ws ||
    !isConnectionReady.value ||
    !sessionId
  ) {
    toast.warning(t('launch.alert_ws_not_ready'))
    return
  }

  // Block the run early when a node references a connection that is missing or has no credential.
  // A failed check (e.g. network) must not stop the launch; the runtime still reports the error.
  try {
    const check = await checkWorkflowConnections(await fetchWorkflowYAML(selectedFile.value))
    if (!check.ok) {
      toast.error(t('connections.precheck_failed'), {
        items: check.problems.map((problem) => `${problem.nodeId}: ${problem.message}`)
      })
      return
    }
  } catch (error) {
    console.warn('Connection pre-check skipped:', error)
  }

  shouldGlow.value = false
  status.value = 'Launching...'

  try {
    const response = await fetch('/api/workflow/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        yaml_file: selectedFile.value,
        task_prompt: trimmedPrompt,
        session_id: sessionId,
        attachments: attachmentIds
      })
    })

    if (response.ok) {
      // Clear uploaded attachments
      clearUploadedAttachments()

      await response.json().catch(() => null)

      const fullMessage = []
      if (trimmedPrompt) {
        fullMessage.push(trimmedPrompt)
      }
      if (attachmentNames.length) {
        fullMessage.push(t('launch.attachments_line', { names: attachmentNames.join(', ') }))
      }
      if (fullMessage.length) {
        addDialogue(USER_SENDER, fullMessage.join('\n\n'))
      }

      taskPrompt.value = ''
      runTracker.begin(trimmedPrompt, attachmentNames)

      status.value = 'Running...'
      isWorkflowRunning.value = true
      hasLaunched.value = true
      // The project runs this workflow from now on (until the user picks another)
      if (currentProjectName.value) rememberProjectWorkflow(currentProjectName.value, selectedFile.value)

      // Persist session id in URL for reconnection after refresh
      router.push({
        query: {
          ...route.query,
          workflow: selectedFile.value,
          session: sessionId
        }
      })
    } else {
      const error = await response.json().catch(() => ({}))
      console.error('Failed to launch workflow:', error)
      status.value = 'Failed'
      toast.error(errorWithDetail('launch.errors.launch_failed', error.detail || (response.status ? `HTTP ${response.status}` : '')))
      shouldGlow.value = true
      if (isConnectionReady.value) {
        status.value = 'Waiting for launch...'
      }
    }
  } catch (error) {
    console.error('Error calling execute API:', error)
    status.value = 'Error'
    toast.error(errorWithDetail('launch.errors.execute_failed', error))
    shouldGlow.value = true
    if (isConnectionReady.value) {
      status.value = 'Waiting for launch...'
    }
  }
}

// When workflow is finished or cancelled, re-enable glow
watch(status, (newStatus) => {
  if (newStatus === 'Completed' || newStatus === 'Cancelled') {
    shouldGlow.value = true
  }
})

const downloadArtifact = async (message) => {
  if (!sessionId || !message?.attachmentId) {
    return
  }
  try {
    // to support download for both code file and image file
    // If we already have dataUri (e.g., images preloaded), avoid toggling loading to prevent flicker
    let dataUri = message.dataUri
    if (!dataUri) {
      message.loading = true
      dataUri = await getAttachment(sessionId, message.attachmentId)
      if (!dataUri) {
        throw new Error(t('launch.errors.empty_attachment'))
      }
      // Cache here
      message.dataUri = dataUri
    }

    const link = document.createElement('a')
    link.href = dataUri
    link.download = message.fileName || 'download'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  } catch (error) {
    console.error('Failed to download artifact:', error)
    toast.error(errorWithDetail('launch.errors.download_failed', error, { name: message?.fileName || '' }))
  } finally {
    if (message.loading) {
      message.loading = false
    }
  }
}

// Handle edge condition messages and trigger sprite animation
const handleEdgeConditionMessage = (message, at) => {
  // Parse message format: "Edge condition met for Source Node -> Target Node"
  const edgeMatch = message.match(/Edge condition met for (.+) -> (.+)/)
  if (!edgeMatch) {
    console.warn('Could not parse edge condition message:', message)
    return
  }

  const sourceNode = edgeMatch[1].trim()
  const targetNode = edgeMatch[2].trim()

  // Office view: the source agent walks over to hand its result to the target
  officeRef.value?.handoff(sourceNode, targetNode)
  runTracker.handoff(sourceNode, targetNode, at)

  // Find the edge in the VueFlow edges
  const edge = edges.value.find(e => e.source === sourceNode && e.target === targetNode)
  if (!edge) {
    return
  }

  // Trigger sprite animation along the edge
  animateSpriteAlongEdge(edge)
}

const SVG_NS = 'http://www.w3.org/2000/svg'

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  typeof window.matchMedia === 'function' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches

// Escape a value for use inside a CSS attribute selector
const escapeSelector = (value) =>
  typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
    ? CSS.escape(value)
    : String(value).replace(/["\\]/g, '\\$&')

// Overlay <svg> that hosts the edge walkers. It lives inside the Vue Flow transformation
// pane (same pan/zoom transform and coordinate space as the edge paths) but is stacked
// above the node layer, otherwise the character would walk behind the node cards.
let spriteWalkerLayer = null

const getSpriteWalkerLayer = (edgeElement) => {
  const pane = edgeElement.closest('.vue-flow__transformationpane')
  if (!pane) return null

  // Reuse the layer from a previous walk / workflow while it is still attached to this pane
  if (spriteWalkerLayer && spriteWalkerLayer.parentNode === pane) return spriteWalkerLayer

  let layer = pane.querySelector(':scope > svg.sprite-walker-layer')
  if (!layer) {
    layer = document.createElementNS(SVG_NS, 'svg')
    layer.setAttribute('class', 'sprite-walker-layer')
    layer.setAttribute('width', '100%')
    layer.setAttribute('height', '100%')
    layer.setAttribute('aria-hidden', 'true')
    pane.appendChild(layer)
  }
  spriteWalkerLayer = layer
  return layer
}

const removeSpriteWalkerLayer = () => {
  if (spriteWalkerLayer) spriteWalkerLayer.remove()
  spriteWalkerLayer = null
}

// Animate a sprite walking along an edge from source to target
const animateSpriteAlongEdge = (edge) => {
  // Make sure the source node has a character bound so chat avatar and walker match
  avatarFor(edge.source)

  // Find edge element in DOM
  const edgeId = `${edge.source}-${edge.target}`
  const edgeElement = document.querySelector(`.vue-flow__edge[data-id="${escapeSelector(edgeId)}"]`)
  if (!edgeElement) {
    console.warn('Edge element not found in DOM for:', edgeId)
    return
  }

  // Find the path element within the edge
  const pathElement = edgeElement.querySelector('path')
  if (!pathElement) {
    console.warn('Path element not found for edge:', edgeId)
    return
  }

  // Overlay layer above the nodes that will host the walker
  const layer = getSpriteWalkerLayer(edgeElement)
  if (!layer) {
    console.warn('Transformation pane not found for edge:', edgeId)
    return
  }

  // Get the total length of the path
  let pathLength = 0
  try {
    pathLength = pathElement.getTotalLength()
  } catch {
    return
  }
  if (!pathLength) return

  // Make sure every direction/frame of this character is cached before we start
  const character = spriteFetcher.getCharacter(edge.source)
  if (character) spriteFetcher.preloadCharacter(character)

  // Sprite box: the image keeps its own aspect ratio inside this box (feet bottom-aligned)
  const SPRITE_H = 48
  const SPRITE_W = 40
  const FEET_OVERLAP = 4 // how far the feet dip below the path point
  const SHADOW_RX = 12
  const SHADOW_RY = 3.5
  const WALK_CYCLE = [1, 2, 1, 3]
  const WALK_STEP_MS = 180
  const FADE_FRACTION = 0.1 // fade in/out over the first/last 10 % of the walk
  const DIRECTION_HYSTERESIS = 1.25 // one axis must dominate by 25 % before the stance flips
  const DIRECTION_CHECK_MS = 90 // re-evaluate the facing direction at most this often
  const REDUCED_MOTION_MS = 600 // static idle sprite shown at the target when motion is reduced

  // Group that moves along the path: ground shadow + character
  const walker = document.createElementNS(SVG_NS, 'g')
  walker.setAttribute('class', 'edge-sprite-walker')
  walker.setAttribute('opacity', '0')
  walker.style.pointerEvents = 'none'

  const shadow = document.createElementNS(SVG_NS, 'ellipse')
  shadow.setAttribute('cx', '0')
  shadow.setAttribute('cy', '0')
  shadow.setAttribute('rx', String(SHADOW_RX))
  shadow.setAttribute('ry', String(SHADOW_RY))
  shadow.setAttribute('fill', 'rgba(0, 0, 0, 0.32)')
  shadow.style.filter = 'blur(1.5px)'

  const spriteImage = document.createElementNS(SVG_NS, 'image')
  spriteImage.setAttribute('width', String(SPRITE_W))
  spriteImage.setAttribute('height', String(SPRITE_H))
  spriteImage.setAttribute('x', String(-SPRITE_W / 2)) // Center horizontally
  spriteImage.setAttribute('y', String(-SPRITE_H + FEET_OVERLAP)) // Feet on the path
  spriteImage.setAttribute('preserveAspectRatio', 'xMidYMax meet')
  spriteImage.setAttribute('image-rendering', 'optimizeSpeed')
  spriteImage.style.imageRendering = 'pixelated'
  spriteImage.style.filter = 'drop-shadow(0 2px 1.5px rgba(0, 0, 0, 0.35))'

  walker.appendChild(shadow)
  walker.appendChild(spriteImage)

  // Ease-in-out so the character accelerates out of the source and settles into the target
  const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)

  // Derive the facing direction from the local tangent of the path. Near-45° tangents keep
  // the current axis (hysteresis) so the stance does not flicker between L/R and U/D.
  const directionAt = (length, current) => {
    const eps = Math.min(4, pathLength * 0.02) || 1
    const a = Math.max(0, Math.min(pathLength, length))
    const b = a + eps <= pathLength ? a + eps : a - eps
    const pa = pathElement.getPointAtLength(Math.min(a, b))
    const pb = pathElement.getPointAtLength(Math.max(a, b))
    const dx = pb.x - pa.x
    const dy = pb.y - pa.y
    const ax = Math.abs(dx)
    const ay = Math.abs(dy)
    const horizontal = dx >= 0 ? 'R' : 'L'
    const vertical = dy >= 0 ? 'D' : 'U'
    if (ax > ay * DIRECTION_HYSTERESIS) return horizontal
    if (ay > ax * DIRECTION_HYSTERESIS) return vertical
    if (current === 'L' || current === 'R') return horizontal
    if (current === 'U' || current === 'D') return vertical
    return ax >= ay ? horizontal : vertical
  }

  let direction = directionAt(0, null)
  let frame = WALK_CYCLE[0]
  spriteImage.setAttribute('href', spriteFetcher.fetchSprite(edge.source, direction, frame))

  // Add to the overlay layer (same coordinate space as the edge path)
  layer.appendChild(walker)

  // Animation duration based on path length (longer paths = more time)
  const duration = Math.min(Math.max(pathLength * 0.02, 2000), 4000) // 2-4 seconds

  let startTime = null
  let rafId = null
  let lastDirectionCheck = 0

  const cleanup = () => {
    if (rafId !== null) cancelAnimationFrame(rafId)
    rafId = null
    walker.remove()
  }

  // Reduced motion: no walk along the path. Briefly show the idle sprite at the
  // destination with a fade so the hand-off is still visible, then clean up.
  if (prefersReducedMotion()) {
    let endPoint
    try {
      endPoint = pathElement.getPointAtLength(pathLength)
    } catch {
      cleanup()
      return
    }
    walker.setAttribute('transform', `translate(${endPoint.x}, ${endPoint.y})`)
    spriteImage.setAttribute('href', spriteFetcher.fetchSprite(edge.source, 'D', 1))

    const fadeStatic = (timestamp) => {
      if (!layer.isConnected || !walker.isConnected) {
        cleanup()
        return
      }
      if (!startTime) startTime = timestamp
      const progress = Math.min((timestamp - startTime) / REDUCED_MOTION_MS, 1)
      let opacity = 1
      if (progress < 0.3) {
        opacity = progress / 0.3
      } else if (progress > 0.7) {
        opacity = (1 - progress) / 0.3
      }
      walker.setAttribute('opacity', opacity.toFixed(3))
      if (progress < 1) {
        rafId = requestAnimationFrame(fadeStatic)
      } else {
        cleanup()
      }
    }

    rafId = requestAnimationFrame(fadeStatic)
    return
  }

  const animate = (timestamp) => {
    // Guard against the layer/path being torn down (view switch, graph reload)
    if (!layer.isConnected || !pathElement.isConnected || !walker.isConnected) {
      cleanup()
      return
    }

    if (!startTime) startTime = timestamp

    const elapsed = timestamp - startTime
    const progress = Math.min(elapsed / duration, 1)
    const eased = easeInOut(progress)
    const distance = eased * pathLength

    let point
    try {
      point = pathElement.getPointAtLength(distance)
    } catch {
      cleanup()
      return
    }

    // Position the walker at the point (SVG coordinates work directly in the SVG element)
    walker.setAttribute('transform', `translate(${point.x}, ${point.y})`)

    // Fade in at the start and out at the end
    let opacity = 1
    if (progress < FADE_FRACTION) {
      opacity = progress / FADE_FRACTION
    } else if (progress > 1 - FADE_FRACTION) {
      opacity = (1 - progress) / FADE_FRACTION
    }
    walker.setAttribute('opacity', opacity.toFixed(3))

    // Walk cycle 1 -> 2 -> 1 -> 3, facing the local tangent of the path.
    // The direction is only re-evaluated on a frame change (or every DIRECTION_CHECK_MS),
    // never on every RAF, so the href does not churn on wobbly tangents.
    const targetFrame = WALK_CYCLE[Math.floor(elapsed / WALK_STEP_MS) % WALK_CYCLE.length]
    let targetDirection = direction
    if (progress < 1 && (targetFrame !== frame || elapsed - lastDirectionCheck >= DIRECTION_CHECK_MS)) {
      targetDirection = directionAt(distance, direction)
      lastDirectionCheck = elapsed
    }

    if (frame !== targetFrame || direction !== targetDirection) {
      frame = targetFrame
      direction = targetDirection
      spriteImage.setAttribute('href', spriteFetcher.fetchSprite(edge.source, direction, frame))
    }

    // Tiny step bounce on the contact frames so the gait reads as footsteps
    const bounce = frame === 1 ? 0 : -1
    spriteImage.setAttribute('y', String(-SPRITE_H + FEET_OVERLAP + bounce))
    shadow.setAttribute('rx', String(SHADOW_RX + (frame === 1 ? 0 : -1)))

    if (progress < 1) {
      rafId = requestAnimationFrame(animate)
    } else {
      // Animation complete
      cleanup()
    }
  }

  // Start animation
  rafId = requestAnimationFrame(animate)
}

const processMessage = async (msg) => {
  // What the user typed earlier; only arrives when a saved session is replayed
  if (msg.type === 'user_message') {
    const text = msg.data?.text || ''
    const names = Array.isArray(msg.data?.attachments) ? msg.data.attachments : []
    const parts = [text.trim(), names.length ? t('launch.attachments_line', { names: names.join(', ') }) : '']
    addDialogue(USER_SENDER, parts.filter(Boolean).join('\n\n'))
    // The first message of a run is the task, later ones are replies to the agents
    if (runTracker.state.task && !runTracker.state.outcome) runTracker.inputSent(text)
    else runTracker.begin(text, names)
    return
  }

  // Session resumed after reconnection — sync final UI state
  if (msg.type === 'session_resumed') {
    const data = msg.data
    sessionId = data.session_id

    // Restore workflow selection without clearing chat (messages were already replayed)
    // Set selectedFile BEFORE clearing isReconnecting so the watch skips
    if (data.yaml_file) {
      selectedFile.value = data.yaml_file
      fileSearchQuery.value = data.yaml_file
      // Load YAML data and sprites (but don't clear chat)
      try {
        const yamlContentString = await fetchWorkflowYAML(data.yaml_file)
        const parsedYaml = yaml.load(yamlContentString)
        workflowYaml.value = parsedYaml || {}
        // Always rebind: the session may belong to another workflow than the last one
        // bound, and its mascots may have been edited since the session started.
        applyWorkflowSprites(parsedYaml?.graph?.nodes, yamlContentString)
      } catch (e) {
        console.error('Failed to load YAML on reconnect:', e)
      }
    }

    isReconnecting.value = false
    currentProjectName.value = stripSlash(data.projects?.[0]?.name)
    hasLaunched.value = Boolean(data.status) && data.status !== 'idle'
    const composer = takeComposer(sessionId)
    if (composer?.prompt) taskPrompt.value = composer.prompt

    // Restore workflow status
    const statusMap = {
      // A draft: projects were added but it was never launched
      'idle': 'Waiting for launch...',
      'running': 'Running...',
      'waiting_for_input': 'Waiting for input...',
      'completed': 'Completed',
      'error': 'Error',
      'cancelled': 'Cancelled',
    }
    status.value = statusMap[data.status] || 'Connected'

    if (data.status === 'running' || data.status === 'waiting_for_input') {
      isWorkflowRunning.value = true
    }

    if (data.status === 'waiting_for_input') {
      shouldGlow.value = true
    }

    // Reopened draft: put its projects back in the message box, ready for the first prompt
    if (data.status === 'idle') {
      shouldGlow.value = true
      uploadedAttachments.value = composer?.attachments?.length ? composer.attachments : (data.projects || []).map((project) => ({
        success: true,
        kind: 'project',
        name: `${project.name}/`,
        attachmentId: project.attachment_id,
        fileCount: project.file_count,
        workspacePath: project.workspace_path
      }))
    } else if (data.status === 'waiting_for_input' && composer?.attachments?.length) {
      uploadedAttachments.value = composer.attachments
    }

    if (data.status === 'completed' || data.status === 'error' || data.status === 'cancelled') {
      sessionIdToDownload = sessionId
    }

    if (data.current_node_id && !activeNodes.value.includes(data.current_node_id)) {
      activeNodes.value.push(data.current_node_id)
    }

    isConnectionReady.value = true
    if (data.error_message === 'Interrupted by a server restart') {
      addChatNotification(t('launch.sessions.interrupted'), { type: 'warning' })
    } else {
      addChatNotification(t('launch.reconnected'))
    }
    if (viewMode.value === 'graph') {
      loadVueFlowGraph({ fit: true })
    }
    scheduleSessionsRefresh()
    return
  }

  // Prompt for human input
  if (msg.type === 'human_input_required') {
    const fullMessage = [msg.data?.task_description, localizeInputHeaders(msg.data?.input)]
      .filter((part) => part !== null && part !== undefined && String(part).trim())
      .join('\n\n')
    addDialogue(msg.data?.node_id || t('launch.unknown_node'), fullMessage || t('launch.input_required'))
    officeRef.value?.waitingInput(msg.data?.node_id)
    runTracker.waitingInput(msg.data?.node_id)

    status.value = "Waiting for input..."
    shouldGlow.value = true
  }

  // Handle artifact messages (file/image output)
  if (msg.type === 'artifact_created') {
    const events = msg?.data?.events
    if (Array.isArray(events)) {
      for (const event of events) {
        const nodeName = event?.node_id || t('launch.artifact_sender')
        const fileName = event?.file_name || 'artifact'
        const mimeType = event?.mime_type || ''
        const attachmentId = event?.attachment_id

        // Build the avatar
        const avatar = avatarFor(nodeName)

        const isRight = false

        // Reactive proxy so the async dataUri/loading updates below re-render the item
        const message = reactive({
          // Treat message as dialogue
          type: 'dialogue',
          name: nodeName,
          text: '',
          avatar,
          isRight,

          // Add artifact-specific fields
          isArtifact: true,
          fileName,
          mimeType,
          attachmentId,
          isImage: !!mimeType && mimeType.includes('image'),
          dataUri: null,
          loading: true,
          error: null,
          timestamp: Date.now(),
          rev: 0
        })

        chatMessages.value.push(message)
        scheduleScrollToBottom()

        // Preload image content. Not awaited: several images in one event load in
        // parallel instead of one after another.
        if (message.isImage && sessionId && attachmentId) {
          getAttachment(sessionId, attachmentId)
            .then((dataUri) => {
              message.dataUri = dataUri
            })
            .catch((error) => {
              console.error('Failed to load image artifact:', error)
              message.error = t('launch.errors.image_load_failed')
            })
            .finally(() => {
              message.loading = false
            })
        } else {
          message.loading = false
        }
      }
    }
  }

  // Handle warning/error messages
  if (msg.type === 'log' && (msg.data.level === 'WARNING' || msg.data.level === 'ERROR')) {
    const notificationType = msg.data.level === 'WARNING' ? 'warning' : 'error'
    // Backend warning/error text is technical English; give it a localized lead-in
    const detail = formatErrorDetail(msg.data.message)
    const fallbackKey = notificationType === 'warning' ? 'launch.unknown_warning' : 'launch.unknown_error'
    addChatNotification(
      detail ? withErrorHint(t(`launch.log_events.backend_${notificationType}`, { detail })) : t(fallbackKey),
      { type: notificationType }
    )
  }

  // Handle log messages
  if (msg.type === 'log' && msg.data.level === 'INFO') {
    const eventType = msg.data.event_type
    const nodeId = msg.data.node_id

    // Node active
    if (eventType === 'NODE_START') {
      if (nodeId && !activeNodes.value.includes(nodeId)) {
        activeNodes.value.push(nodeId)
      }
      runTracker.nodeStart(nodeId, msg.data.timestamp)
    }

    // Model call
    else if (eventType === 'MODEL_CALL') {
      // Model call started
      if (msg.data.details.stage === "before") {
        const baseKey = `model-${msg.data.details.model_name || 'unknown'}`
        addLoadingEntry(nodeId, baseKey, t('launch.loading_model', { name: msg.data.details.model_name || t('launch.unknown_name') }))
        officeRef.value?.activity(nodeId, 'model', msg.data.details.model_name || '', true)
        runTracker.activity(nodeId, 'model', msg.data.details.model_name || '', true, msg.data.timestamp)
      }

      // Model call ended
      if (msg.data.details.stage === "after") {
        const baseKey = `model-${msg.data.details.model_name || 'unknown'}`
        finishLoadingEntry(nodeId, baseKey)
        officeRef.value?.activity(nodeId, 'model', msg.data.details.model_name || '', false)
        runTracker.activity(nodeId, 'model', msg.data.details.model_name || '', false, msg.data.timestamp)
      }
    }

    // Tool call (a node may call tools multiple times)
    else if (eventType === 'TOOL_CALL') {
      // Tool call started
      if (msg.data.details.stage === "before") {
        const baseKey = `tool-${msg.data.details.tool_name || 'unknown'}`
        addLoadingEntry(nodeId, baseKey, t('launch.loading_tool', { name: msg.data.details.tool_name || t('launch.unknown_name') }))
        officeRef.value?.activity(nodeId, 'tool', msg.data.details.tool_name || '', true)
        runTracker.activity(nodeId, 'tool', msg.data.details.tool_name || '', true, msg.data.timestamp)
      }

      // Tool call ended
      if (msg.data.details.stage === "after") {
        const baseKey = `tool-${msg.data.details.tool_name || 'unknown'}`
        finishLoadingEntry(nodeId, baseKey)
        officeRef.value?.activity(nodeId, 'tool', msg.data.details.tool_name || '', false)
        runTracker.activity(nodeId, 'tool', msg.data.details.tool_name || '', false, msg.data.timestamp)
      }
    }

    // Node ended (with output)
    else if (eventType === 'NODE_END') {
      if (nodeId) {
        // Remove from active node list
        const index = activeNodes.value.indexOf(nodeId)
        if (index > -1) {
          activeNodes.value.splice(index, 1)
        }

        const nodeState = nodesLoadingMessagesMap.get(nodeId)
        if (nodeState) {
          const endedAt = Date.now()
          finalizeAllLoadingEntries(nodeState, endedAt)
          nodeState.message.isLoading = false
          nodeState.message.duration = formatDuration(nodeState.message.startedAt, endedAt)
          nodesLoadingMessagesMap.delete(nodeId)
        }
      }

      addDialogue(nodeId || t('launch.unknown_node'), msg.data.details?.output)
      if (nodeId) officeRef.value?.nodeEnd(nodeId, msg.data.details?.output)
      runTracker.nodeEnd(nodeId, msg.data.details?.output, msg.data.timestamp)
    }

    // Edge condition met - trigger sprite animation
    else if (msg.data.message && msg.data.message.includes('Edge condition met for')) {
      handleEdgeConditionMessage(msg.data.message, msg.data.timestamp)
    }

    // Other log messages
    else if (msg.data.message) {
      addChatNotification(localizeLogMessage(msg.data))
    }
  }

  // Workflow completed
  if (msg.type === 'workflow_completed') {
    addChatNotification(formatErrorDetail(msg.data?.summary) || t('launch.workflow_completed'))
    runTracker.finish('completed', { summary: formatErrorDetail(msg.data?.summary), tokenUsage: msg.data?.token_usage })
    status.value = 'Completed'
    isWorkflowRunning.value = false
    sessionIdToDownload = sessionId
  }

  // Workflow cancelled (e.g., from server-side cancellation)
  if (msg.type === 'workflow_cancelled') {
    addChatNotification(formatErrorDetail(msg.data?.message) || t('launch.workflow_cancelled'))
    if (runTracker.state.outcome !== 'cancelled') runTracker.finish('cancelled', { summary: formatErrorDetail(msg.data?.message) })
    status.value = 'Cancelled'
    isWorkflowRunning.value = false
    sessionIdToDownload = sessionId
  }

  // Handle direct error messages (e.g., workflow execution errors)
  if (msg.type === 'error') {
    const errorMessage = withErrorHint(errorWithDetail('launch.errors.workflow_error', msg.data?.message))
    addChatNotification(errorMessage, { type: 'error' })
    runTracker.finish('error', { error: formatErrorDetail(msg.data?.message) })
    status.value = 'Error'
    isWorkflowRunning.value = false
    sessionIdToDownload = sessionId
  }
}

// Cancel the currently running workflow
const cancelWorkflow = () => {
  if (!isWorkflowRunning.value || !ws) {
    return
  }

  // Send cancel request through WebSocket so the server stops the workflow
  try {
    ws.send(JSON.stringify({ type: 'cancel' }))
  } catch (sendError) {
    console.warn('Failed to send cancel message:', sendError)
  }

  addChatNotification(t('launch.workflow_cancelled'))
  runTracker.finish('cancelled')
  status.value = 'Cancelled'
  isWorkflowRunning.value = false
  sessionIdToDownload = sessionId

  // Finish all loading messages
  const endedAt = Date.now()
  for (const [nodeId, nodeState] of nodesLoadingMessagesMap.entries()) {
    if (nodeState?.message) {
      finalizeAllLoadingEntries(nodeState, endedAt)
      nodeState.message.isLoading = false
      nodeState.message.duration = formatDuration(nodeState.message.startedAt, endedAt)
      nodesLoadingMessagesMap.delete(nodeId)
    }
  }
}

// Download logs
const downloadLogs = async () => {
  if (!sessionIdToDownload) {
    return
  }
  try {
    await fetchLogsZip(sessionIdToDownload)
  } catch (error) {
    console.error('Download failed:', error)
    toast.error(errorWithDetail('launch.errors.download_logs_failed', error))
  }
}

// Return a preview by file name/type (data URI). Images return thumbnails; others return an extension icon.
const getFilePreviewSrc = (message) => {
  try {
    const fileName = message?.fileName || ''
    const mimeType = message?.mimeType || ''
    if (message?.isImage && message?.dataUri) {
      // Use existing image data as the preview thumbnail
      return message.dataUri
    }
    return getPreviewIconByExt(fileName, mimeType)
  } catch {
    return ''
  }
}

const getPreviewIconByExt = (fileName = '', mimeType = '') => {
  const ext = (fileName.split('.').pop() || '').toLowerCase()
  const isImg = mimeType.includes('image') || ['png','jpg','jpeg','gif','webp','svg','bmp','tiff','ico'].includes(ext)

  if (isImg) return svgIconDataUri('IMG', '#9b59b6')

  const map = {
    pdf: ['PDF', '#e74c3c'],
    doc: ['DOC', '#3498db'], docx: ['DOC', '#3498db'],
    xls: ['XLS', '#2ecc71'], xlsx: ['XLS', '#2ecc71'], csv: ['CSV', '#27ae60'],
    ppt: ['PPT', '#e67e22'], pptx: ['PPT', '#e67e22'],
    txt: ['TXT', '#7f8c8d'], log: ['LOG', '#7f8c8d'], md: ['MD', '#95a5a6'],
    json: ['JSON', '#f1c40f'], yaml: ['YML', '#f39c12'], yml: ['YML', '#f39c12'],
    zip: ['ZIP', '#8e44ad'], rar: ['ZIP', '#8e44ad'], '7z': ['ZIP', '#8e44ad'], tar: ['ZIP', '#8e44ad'], gz: ['ZIP', '#8e44ad'],
    py: ['PY', '#3572A5'], js: ['JS', '#f1e05a'], ts: ['TS', '#3178c6'], jsx: ['JSX', '#61dafb'], tsx: ['TSX', '#61dafb'],
    html: ['HTML', '#e34c26'], css: ['CSS', '#563d7c'], scss: ['SCSS', '#c6538c'],
    mp3: ['AUD', '#27ae60'], wav: ['AUD', '#27ae60'], flac: ['AUD', '#27ae60'],
    mp4: ['VID', '#8e44ad'], mov: ['VID', '#8e44ad'], avi: ['VID', '#8e44ad'], mkv: ['VID', '#8e44ad']
  }

  const [label, color] = map[ext] || ['FILE', '#95a5a6']
  return svgIconDataUri(label, color)
}

const svgIconDataUri = (label, bgColor) => {
  const svg = `<?xml version="1.0" encoding="UTF-8"?>
  <svg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 48 48'>
    <defs>
      <style>
        .t{font: 700 16px "Inter, Arial"; fill: var(--text-1)}
      </style>
    </defs>
    <rect x='0' y='0' width='48' height='48' rx='8' ry='8' fill='${bgColor}' />
    <text x='50%' y='58%' text-anchor='middle' class='t'>${(label || '').toUpperCase().slice(0,4)}</text>
  </svg>`
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`
}

// Auto-scroll: a single rAF-scheduled scroll, only while the user is near the bottom
const SCROLL_BOTTOM_THRESHOLD = 120
let isNearBottom = true
let scrollRafId = null

const handleChatScroll = () => {
  const el = chatMessagesRef.value
  if (!el) return
  isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= SCROLL_BOTTOM_THRESHOLD
}

function scheduleScrollToBottom(force = false) {
  if (force) {
    isNearBottom = true
  }
  if (!isNearBottom || scrollRafId !== null) return
  scrollRafId = requestAnimationFrame(() => {
    scrollRafId = null
    const el = chatMessagesRef.value
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  })
}

// Clearing / replacing the whole list (new session, reconnect) starts pinned to the bottom
watch(
  () => chatMessages.value.length,
  (length) => {
    if (length === 0) {
      isNearBottom = true
    }
    scheduleScrollToBottom()
  },
  { flush: 'post' }
)
</script>

<style scoped>
.launch-view {
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-base);
  color: var(--text-1);
  font-family: 'Inter', sans-serif;
  position: relative;
  overflow: hidden;
}

.launch-bg {
  position: fixed;
  top: -150px;
  left: 0;
  right: 0;
  height: 500px;
  /* Pre-softened radial glows instead of filter: blur(120px) on a large layer,
     which is very expensive to rasterise and composite. */
  background:
    radial-gradient(ellipse 40% 70% at 18% 45%, var(--accent-mint), transparent 72%),
    radial-gradient(ellipse 40% 70% at 50% 45%, var(--accent-sky), transparent 72%),
    radial-gradient(ellipse 40% 70% at 82% 45%, var(--accent-indigo), transparent 72%);
  opacity: 0.15;
  z-index: 0;
  pointer-events: none;
}

.header {
  display: flex;
  align-items: center;
  padding: 0 20px;
  height: 40px;
  background-color: rgb(var(--ink) / 0.05);
  border-bottom: 1px solid rgb(var(--ink) / 0.1);
  flex-shrink: 0;
  position: relative;
  z-index: 2;
}

.header h1 {
  margin: 0;
  color: var(--text-1);
  font-size: 18px;
  font-weight: 600;
}

.back-button {
  padding: 8px;
  margin-right: 16px;
  background: transparent;
  color: rgb(var(--ink) / 0.6);
  cursor: pointer;
  transition: color 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  outline: none;
}

.back-button:hover {
  color: var(--text-1);
}

.content {
  flex: 1;
  display: flex;
  overflow: hidden;
  padding: 20px;
  gap: 20px;
  position: relative;
  z-index: 1;
}

/* Left Panel */
.left-panel {
  flex: 3;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0; /* Prevents overflow */
  position: relative;
}

/* Persistent Chat Panel */
.chat-panel {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: 380px;
  max-width: 50%;
  z-index: 10;
  display: flex;
  flex-direction: row;
  pointer-events: none;
  transition: width 0.3s ease;
}

/* Full-screen chat mode */
.chat-panel-fullscreen {
  position: relative;
  width: 100%;
  max-width: 100%;
  flex: 1;
  flex-direction: column;
  pointer-events: auto;
  z-index: auto;
  min-height: 0;
}

.chat-panel-fullscreen .chat-panel-content {
  background: rgb(var(--ink) / 0.03);
  border: 1px solid rgb(var(--ink) / 0.1);
}

.chat-panel-collapsed {
  width: 0;
}

.chat-panel-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  min-height: 0;
  pointer-events: auto;
  background: rgb(var(--panel-26) / 0.97);
  border: 1px solid rgb(var(--ink) / 0.1);
  border-radius: 12px;
  overflow: hidden;
  padding: 0;
}

.chat-panel-toggle {
  position: absolute;
  top: 12px;
  right: -28px;
  width: 28px;
  height: 28px;
  border-radius: 0 8px 8px 0;
  border: 1px solid rgb(var(--ink) / 0.15);
  border-left: none;
  background: rgb(var(--panel-26) / 0.97);
  color: rgb(var(--ink) / 0.7);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: auto;
  transition: background-color 0.2s ease, color 0.2s ease;
  padding: 0;
  z-index: 11;
}

.chat-panel-toggle:hover {
  background: rgb(var(--ink) / 0.1);
  color: var(--text-1);
}

.chat-panel-toggle svg {
  transition: transform 0.3s ease;
}

.chat-panel-toggle .chevron-collapsed {
  transform: rotate(180deg);
}

.chat-panel-collapsed .chat-panel-toggle {
  right: -28px;
  left: auto;
}

/* Chat header: session title + history / new-session actions */
.chat-header {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 12px 10px 16px;
  border-bottom: 1px solid rgb(var(--ink) / 0.08);
}

.chat-header-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.chat-header-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-1);
  font-size: 15px;
  font-weight: 700;
}

.chat-header-sub {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: rgb(var(--ink) / 0.5);
}

.chat-header-project {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-right: 4px;
  padding: 0 6px;
  border-radius: 4px;
  background: rgb(245 185 74 / 0.14);
  color: #e0a43a;
  font-weight: 600;
  vertical-align: 1px;
}

.workflow-hint {
  margin: -2px 0 2px;
  font-size: 11.5px;
  line-height: 1.4;
  color: rgb(var(--ink) / 0.5);
}

.chat-header-actions {
  flex: none;
  display: flex;
  gap: 4px;
}

.chat-header-btn {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: rgb(var(--ink) / 0.65);
  cursor: pointer;
  transition: background-color 0.2s ease, color 0.2s ease;
}

.chat-header-btn:hover,
.chat-header-btn.active {
  background: rgb(var(--ink) / 0.08);
  color: var(--text-1);
}

/* Chat Box */
.chat-box {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.chat-messages::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
.chat-messages::-webkit-scrollbar-track {
  background: transparent;
}
.chat-messages::-webkit-scrollbar-thumb {
  background-color: rgb(var(--neutral-160) / 0.28);
  border-radius: 8px;
  border: 2px solid transparent;
  background-clip: padding-box;
}
.chat-messages::-webkit-scrollbar-thumb:hover {
  background-color: rgb(var(--neutral-160) / 0.48);
}

.chat-messages {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scroll-behavior: auto;
  color: var(--text-2);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Each message lays out independently so a growing bubble does not invalidate the whole list */
.chat-message-item {
  contain: layout style;
  content-visibility: auto;
  contain-intrinsic-size: auto 120px;
}

/* Chat Notification */
.chat-notification {
  display: flex;
  justify-content: center;
  margin: 10px 0;
}

.notification-content {
  background: rgb(var(--ink) / 0.08);
  border: 1px solid rgb(var(--ink) / 0.1);
  border-radius: 20px;
  padding: 8px 16px;
  max-width: 80%;
  animation: slideIn 0.3s ease-out;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.notification-text {
  color: rgb(var(--ink) / 0.8);
  font-size: 13px;
  font-weight: 500;
  text-align: center;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.chat-notification-warning .notification-content {
  background: rgba(255, 204, 0, 0.12);
  border-color: rgba(255, 204, 0, 0.4);
}

.chat-notification-warning .notification-text {
  color: var(--warn-soft-2);
}

.chat-notification-error .notification-content {
  background: rgba(255, 82, 82, 0.12);
  border-color: rgba(255, 82, 82, 0.4);
  color: var(--danger-soft);
}

.message-timestamp {
  font-size: 0.75rem;
  color: rgb(var(--ink) / 0.4);
  margin-left: 8px;
  flex-shrink: 0;
}

.chat-notification .message-timestamp {
  margin-left: 0;
  margin-top: 4px;
  color: rgb(var(--ink) / 0.3);
}

.dialogue-right .message-timestamp {
  margin-left: 0;
  margin-right: 8px;
}

.user-name {
  display: flex;
  align-items: baseline;
  justify-content: flex-start;
}

.dialogue-right .user-name {
  flex-direction: row-reverse;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Dialogue Messages */
.dialogue {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 8px;
}

.dialogue-right {
  flex-direction: row-reverse;
}

.message-content {
  flex: 1;
  max-width: 85%;
  display: flex;
  flex-direction: column;
  gap: 4px;
  /* Shrink to fit content */
  align-items: flex-start;
}

.dialogue-right .message-content {
  /* Right-side fit logic */
  align-items: flex-end;
}

.user-name {
  font-size: 12px;
  color: rgb(var(--ink) / 0.5);
  font-weight: 500;
  margin: 0 4px;
}

.dialogue-right .user-name {
  text-align: right;
}

/* Chat avatar: pixel-art chibi inside a soft pastel rounded-square tile */
.profile-picture {
  --avatar-size: 44px;
  --avatar-sprite-size: 40px;
  --avatar-bg: linear-gradient(145deg, rgb(var(--accent-indigo-rgb) / 0.28), rgba(201, 167, 235, 0.22) 55%, rgba(255, 180, 237, 0.2));
  --avatar-base: rgb(var(--ink) / 0.06);
  --avatar-border: rgb(var(--ink) / 0.18);
  --avatar-shadow: 0 2px 6px rgb(var(--shade) / 0.35);

  flex-shrink: 0;
  position: relative;
  width: var(--avatar-size);
  height: var(--avatar-size);
  border-radius: 14px;
  overflow: hidden;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding-bottom: 2px;
  box-sizing: border-box;
  background: var(--avatar-bg), var(--avatar-base);
  /* 1px inner border + small outer shadow */
  box-shadow: inset 0 0 0 1px var(--avatar-border), var(--avatar-shadow);
}

/* Faint ground spot so the character looks like it stands in the tile */
.profile-picture::before {
  content: '';
  position: absolute;
  left: 50%;
  bottom: 1px;
  width: 60%;
  height: 7px;
  transform: translateX(-50%);
  border-radius: 50%;
  background: radial-gradient(ellipse at center, rgb(var(--shade) / 0.28), transparent 70%);
  filter: blur(1px);
}

.profile-picture img {
  position: relative;
  width: var(--avatar-sprite-size);
  height: var(--avatar-sprite-size);
  object-fit: contain;
  object-position: 50% 100%;
  image-rendering: crisp-edges;
  image-rendering: pixelated;
  filter: drop-shadow(0 1px 1px rgb(var(--shade) / 0.3));
}

/* Light theme is applied via :root[data-theme="light"] (configStore.applyTheme), not the OS preference */
:root[data-theme="light"] .profile-picture {
  --avatar-bg: linear-gradient(145deg, rgb(var(--accent-indigo-rgb) / 0.55), rgba(201, 167, 235, 0.45) 55%, rgba(255, 180, 237, 0.45));
  --avatar-base: rgb(var(--panel-20) / 0.9);
  --avatar-border: rgba(30, 30, 50, 0.1);
  --avatar-shadow: 0 2px 6px rgba(30, 30, 50, 0.12);
}

.message-bubble {
  background: rgb(var(--ink) / 0.05);
  border: 1px solid rgb(var(--ink) / 0.1);
  border-radius: 12px;
  border-top-left-radius: 2px;
  padding: 0 16px;
  position: relative;
  transition: background-color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.dialogue-right .message-bubble {
  background: linear-gradient(135deg, rgb(var(--accent-indigo-rgb) / 0.15), rgba(189, 178, 255, 0.15));
  border-color: rgb(var(--accent-indigo-rgb) / 0.3);
  border-top-left-radius: 12px;
  border-top-right-radius: 2px;
}

.loading-bubble {
  border-color: var(--accent-mint);
  background-color: rgb(var(--ink) / 0.08);
  box-shadow: 0 0 12px rgb(var(--accent-sky-rgb) / 0.35);
  animation: borderPulse 3s ease-in-out infinite alternate;
  animation: bubbleGlow 3s ease-in-out infinite alternate;
}

@keyframes bubbleGlow {
  0% {
    box-shadow: 0 0 6px rgb(var(--accent-sky-rgb) / 0.35);
  }
  50% {
    box-shadow: 0 0 12px rgb(var(--accent-sky-rgb) / 0.35);
  }
}

.loading-timer {
  margin-left: 8px;
  margin-bottom: 10px;
  font-size: 12px;
  color: rgb(var(--ink) / 0.7);
}

.loading-entries {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 10px 0 4px;
  padding: 2px 0;
  border-radius: 10px;
}

.loading-entry {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 10px;
  background: rgb(var(--ink) / 0.05);
  border: 1px solid rgb(var(--ink) / 0.12);
  position: relative;
  /* no backdrop-filter here: it forced a re-blur on every pulse frame of each entry */
}

.loading-entry-label {
  font-size: 14px;
  color: rgb(var(--ink) / 0.9);
}

.loading-entry-duration {
  font-size: 12px;
  color: rgb(var(--ink) / 0.6);
}

.entry-running {
  border-color: var(--accent-mint);
  box-shadow: 0 0 8px rgb(var(--accent-sky-rgb) / 0.25);
  animation: loadingEntryPulse 2.6s ease-in-out infinite;
}

.entry-done {
  border-color: rgb(var(--ink) / 0.15);
  opacity: 0.8;
}

/* Fade-slide-in animation for entries */
.loading-entry-enter-active,
.loading-entry-leave-active {
  transition: opacity 0.22s ease-out, transform 0.22s ease-out;
}

.loading-entry-enter-from,
.loading-entry-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

.loading-entry-enter-to,
.loading-entry-leave-from {
  opacity: 1;
  transform: translateY(0);
}

@keyframes loadingEntryPulse {
  0% {
    box-shadow: 0 0 4px rgb(var(--accent-sky-rgb) / 0.18);
    border-color: rgb(var(--accent-sky-rgb) / 0.6);
    background: rgb(var(--ink) / 0.06);
  }
  50% {
    box-shadow: 0 0 10px rgb(var(--accent-sky-rgb) / 0.38);
    border-color: rgb(var(--accent-mint-rgb) / 0.9);
    background: rgb(var(--ink) / 0.09);
  }
  100% {
    box-shadow: 0 0 4px rgb(var(--accent-sky-rgb) / 0.18);
    border-color: rgb(var(--accent-sky-rgb) / 0.6);
    background: rgb(var(--ink) / 0.06);
  }
}

.message-text {
  color: var(--text-1);
  font-size: 14px;
  line-height: 1.5;
  word-wrap: break-word;
  white-space: pre-wrap;
}

/* Artifact wrappers */
.artifact-image-wrapper {
  padding: 10px 0;
}

.artifact-file-wrapper {
  padding: 10px 0;
}

.artifact-image {
  max-width: 260px;
  max-height: 200px;
  display: block;
  cursor: zoom-in;
  border-radius: 6px;
  padding: 0 0 10px 0;
}

.artifact-filename {
  margin-top: 4px;
  font-size: 12px;
  color: rgb(var(--ink) / 0.7);
  display: flex;
  align-items: center;
  gap: 6px;
}

.artifact-filename-icon {
  width: 18px;
  height: 18px;
  border-radius: 3px;
  object-fit: cover;
  flex-shrink: 0;
}

.artifact-filename-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.artifact-download-button {
  margin-top: 15px;
  padding: 4px 10px;
  border-radius: 10px;
  border: 1px solid rgb(var(--ink) / 0.3);
  background: rgb(var(--ink) / 0.06);
  color: var(--text-1);
  font-size: 12px;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.artifact-download-button:hover:not(:disabled) {
  background: rgb(var(--ink) / 0.12);
}

.artifact-download-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.artifact-status {
  font-size: 12px;
  color: rgb(var(--ink) / 0.6);
}

.artifact-status.artifact-error {
  color: var(--danger-2);
}

/* Input Area */
.input-area {
  flex: 0 0 auto;
}

.input-shell {
  height: 100%;
  display: flex;
  flex-direction: row;
  /* Near-opaque instead of backdrop-filter: this panel can float over the animated
     office map / graph, where a blur would be recomputed every frame. Over the flat
     page background it looks the same as the former translucent fill. */
  background-color: rgb(32 32 34 / 0.94);
  border: 1px solid rgb(var(--ink) / 0.1);
  border-radius: 12px;
  transition: border-color 0.3s ease, background-color 0.3s ease, box-shadow 0.3s ease;
  position: relative;
}

.input-shell:focus-within {
  border-color: rgb(var(--ink) / 0.3);
  background-color: rgb(var(--ink) / 0.05);
}

.input-shell.glow {
  border-color: var(--accent-mint);
  box-shadow: 0 0 15px rgb(var(--accent-sky-rgb) / 0.3);
  animation: borderPulse 4s ease-in-out infinite alternate;
}

.input-shell.drag-active {
  border-color: rgb(var(--accent-sky-rgb) / 0.9);
  background-color: rgb(var(--accent-sky-rgb) / 0.08);
  box-shadow: 0 0 20px rgb(var(--accent-sky-rgb) / 0.35);
}

/* Composer (message box): attachment chips on top, textarea, then a toolbar */
.input-shell.composer {
  flex-direction: column;
  height: auto;
  border-radius: 16px;
  padding: 0;
}

.composer .task-input {
  flex: none;
  min-height: 44px;
  max-height: 200px;
  padding: 14px 16px 6px;
  overflow-y: auto;
}

.composer-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 12px 0;
}

.attachment-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  min-width: 0;
  padding: 5px 6px 5px 8px;
  border-radius: 8px;
  border: 1px solid rgb(var(--ink) / 0.14);
  background: rgb(var(--ink) / 0.06);
  color: var(--text-1);
  font-size: 12px;
  font-weight: 600;
}

.chip-thumb {
  width: 22px;
  height: 22px;
  flex: none;
  border-radius: 5px;
  object-fit: cover;
  background: rgb(var(--ink) / 0.1);
}

.chip-icon { flex: none; font-size: 14px; line-height: 1; }

.chip-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chip-meta { flex: none; font-weight: 400; color: rgb(var(--ink) / 0.5); }

.chip-remove {
  flex: none;
  width: 18px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: rgb(var(--ink) / 0.55);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
}

.chip-remove:hover { background: rgb(var(--ink) / 0.14); color: var(--text-1); }

.chip-uploading { color: rgb(var(--ink) / 0.7); font-weight: 500; }

.chip-spinner {
  width: 12px;
  height: 12px;
  flex: none;
  border-radius: 50%;
  border: 2px solid rgb(var(--ink) / 0.2);
  border-top-color: var(--accent-sky);
  animation: chip-spin 0.8s linear infinite;
}

@keyframes chip-spin { to { transform: rotate(360deg); } }

.composer-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px 10px;
}

.attach-menu-wrap { position: relative; }

.composer-icon-btn,
.composer-send {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border-radius: 50%;
  cursor: pointer;
  transition: background-color 0.2s ease, color 0.2s ease, opacity 0.2s ease;
}

.composer-icon-btn {
  border: 1px solid rgb(var(--ink) / 0.18);
  background: transparent;
  color: rgb(var(--ink) / 0.75);
}

.composer-icon-btn:hover:not(:disabled),
.composer-icon-btn.active { background: rgb(var(--ink) / 0.1); color: var(--text-1); }

.composer-send {
  border: none;
  background: #ff6b6b;
  color: #fff;
}

.composer-send:hover:not(:disabled) { background: #ff5252; }

/* Stop state (Visual Studio style): rounded square inside the red button */
.composer-send.is-stop {
  border-radius: 10px;
  box-shadow: 0 0 0 2px rgb(255 107 107 / 0.35);
  animation: composer-stop-pulse 1.6s ease-in-out infinite;
}

@keyframes composer-stop-pulse {
  0%, 100% { box-shadow: 0 0 0 2px rgb(255 107 107 / 0.35); }
  50% { box-shadow: 0 0 0 5px rgb(255 107 107 / 0.15); }
}

.composer-icon-btn:disabled,
.composer-send:disabled { opacity: 0.4; cursor: not-allowed; }

.attach-menu {
  position: absolute;
  left: 0;
  bottom: calc(100% + 8px);
  min-width: 170px;
  display: flex;
  flex-direction: column;
  padding: 4px;
  border-radius: 10px;
  border: 1px solid rgb(var(--ink) / 0.12);
  background: var(--surface-3);
  box-shadow: 0 10px 30px rgb(var(--shade) / 0.5);
  z-index: 20;
}

.attach-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--text-2);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.attach-menu-item:hover { background: rgb(var(--ink) / 0.08); color: var(--text-1); }

/* Office view: own stacking context so the map's high z-index HUD/roster cannot paint over the chat panel */
.insight-panel {
  position: relative;
  min-width: 0;
  min-height: 0;
}

.office-panel {
  position: relative;
  z-index: 0;
  isolation: isolate;
}

.drag-overlay {
  position: absolute;
  inset: 6px;
  border-radius: 10px;
  border: 1px dashed rgb(var(--accent-sky-rgb) / 0.6);
  background: rgb(var(--panel-20b) / 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.drag-overlay-content {
  font-size: 12px;
  letter-spacing: 0.6px;
  text-transform: uppercase;
  color: rgb(var(--accent-sky-rgb) / 0.95);
}

@keyframes borderPulse {
  0% { border-color: var(--accent-mint); box-shadow: 0 0 0px rgb(var(--accent-mint-rgb) / 0.15); }
  50% { border-color: var(--accent-sky); box-shadow: 0 0 8px rgb(var(--accent-sky-rgb) / 0.35); }
   100% { border-color: var(--accent-indigo); box-shadow: 0 0 0px rgb(var(--accent-indigo-rgb) / 0.2); }
}

.task-input {
  flex: 1;
  padding: 16px;
  border: none;
  font-family: 'Inter', sans-serif;
  font-size: 14px;
  resize: none;
  outline: none;
  background: transparent;
  color: var(--text-1);
  line-height: 1.5;
}

.task-input::placeholder {
  color: rgb(var(--ink) / 0.3);
}

.input-footer {
  display: flex;
  justify-content: flex-end;
  padding: 10px 12px 10px 6px;
  border-top: 1px solid rgb(var(--ink) / 0.05);
}

.input-footer-buttons {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  flex-direction: column;
  height: 100%;
}

.microphone-button {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid rgb(var(--ink) / 0.2);
  background: rgb(var(--ink) / 0.05);
  color: rgb(var(--ink) / 0.8);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
  padding: 0;
  outline: none;
  position: relative;
}

.microphone-button:hover:not(:disabled) {
  background: rgb(var(--ink) / 0.1);
  border-color: rgb(var(--ink) / 0.4);
  color: var(--text-1);
}

.microphone-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.microphone-button.recording {
  background: rgb(var(--ink) / 0.1);
  border-color: var(--accent-mint);
  color: var(--text-1);
}

.microphone-button.pulsating {
  animation: microphonePulse 2s ease-in-out infinite;
}

@keyframes microphonePulse {
  0% {
    box-shadow:
      0 0 0 0 rgb(var(--accent-mint-rgb) / 0.7),
      0 0 0 0 rgb(var(--accent-sky-rgb) / 0.5);
    border-color: var(--accent-mint);
  }
  50% {
    box-shadow:
      0 0 0 12px rgb(var(--accent-mint-rgb) / 0),
      0 0 0 6px rgb(var(--accent-sky-rgb) / 0.3);
    border-color: var(--accent-sky);
  }
  100% {
    box-shadow:
      0 0 0 24px rgb(var(--accent-mint-rgb) / 0),
      0 0 0 18px rgb(var(--accent-sky-rgb) / 0);
    border-color: var(--accent-mint);
  }
}

.attachment-upload {
  position: relative;
}

.attachment-button-wrapper {
  position: relative;
  display: inline-flex;
  gap: 6px;
}

.attachment-button {
  padding: 6px 16px;
  border-radius: 20px;
  border: 1px solid rgb(var(--ink) / 0.2);
  background: rgb(var(--ink) / 0.05);
  color: rgb(var(--ink) / 0.8);
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: background-color 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.attachment-button:hover:not(:disabled) {
  background: rgb(var(--ink) / 0.1);
  border-color: rgb(var(--ink) / 0.4);
  color: var(--text-1);
}

.attachment-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.hidden-file-input {
  display: none;
}

.attachment-count {
  position: absolute;
  top: -8px;
  right: -6px;
  background: var(--accent-sky);
  color: var(--bg-base);
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 10px;
}

/* Attachment Modal */
.attachment-modal {
  position: absolute;
  right: 0;
  bottom: calc(100% + 10px);
  width: 240px;
  background: var(--surface-3);
  border: 1px solid rgb(var(--ink) / 0.1);
  border-radius: 8px;
  padding: 8px;
  box-shadow: 0 10px 30px rgb(var(--shade) / 0.5);
  display: flex;
  flex-direction: column;
  gap: 6px;
  z-index: 10;
}

.attachment-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  background: rgb(var(--ink) / 0.05);
  border-radius: 4px;
}

.attachment-name {
  font-size: 12px;
  color: var(--text-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attachment-kind {
  margin-right: 4px;
}

.attachment-meta {
  margin-left: 6px;
  font-size: 11px;
  color: var(--text-3, rgb(var(--ink) / 0.5));
}

.remove-attachment {
  border: none;
  background: transparent;
  color: var(--accent-sky);
  cursor: pointer;
  padding: 0 4px;
}

/* Right Panel */
.right-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 250px;
}

/* Right Panel — overlay mode (graph view) */
.right-panel-overlay {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 300px;
  max-width: 40%;
  z-index: 10;
  flex: none;
  min-width: 0;
  pointer-events: none;
  transition: width 0.3s ease;
}

.right-panel-overlay .control-section {
  pointer-events: auto;
}

.right-panel-collapsed {
  width: 0;
}

.right-panel-fab {
  position: absolute;
  bottom: 20px;
  right: 20px;
  width: 56px;
  height: 56px;
  border-radius: 16px;
  border: 1px solid rgb(var(--periwinkle-2) / 0.3);
  background: rgb(var(--panel-26) / 0.97);
  box-shadow: 0 3px 12px rgb(var(--shade) / 0.4), 0 0 0 1px rgb(var(--periwinkle-2) / 0.08);
  color: rgb(var(--periwinkle) / 0.85);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: auto;
  transition: background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
  padding: 0;
  z-index: 11;
}

.right-panel-fab:hover {
  background: rgb(var(--panel-40c) / 0.95);
  color: var(--accent-indigo-2);
  border-color: rgb(var(--periwinkle-2) / 0.5);
  box-shadow: 0 4px 16px rgb(var(--shade) / 0.5), 0 0 12px rgb(var(--periwinkle-2) / 0.15);
  transform: translateY(-2px);
}


.control-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  /* Near-opaque instead of backdrop-filter: this panel can float over the animated
     office map / graph, where a blur would be recomputed every frame. Over the flat
     page background it looks the same as the former translucent fill. */
  background-color: rgb(32 32 34 / 0.94);
  border: 1px solid rgb(var(--ink) / 0.1);
  border-radius: 12px;
  padding: 20px;
}

.section-label {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: rgb(var(--ink) / 0.4);
  font-weight: 600;
  margin-top: 4px;
}

/* Custom Select */
.select-wrapper {
  position: relative;
}

.custom-file-selector {
  position: relative;
}

.file-selector,
.file-selector-input {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 12px;
  padding-right: 30px;
  background-color: rgb(var(--ink) / 0.05);
  border: 1px solid rgb(var(--ink) / 0.1);
  border-radius: 8px;
  color: var(--text-1);
  font-size: 14px;
  appearance: none;
  color: var(--text-1);
}

.file-selector-input {
  cursor: text;
}

.file-selector:hover:not(:disabled),
.file-selector-input:hover:not(:disabled),
.file-selector-input:focus {
  background-color: rgb(var(--ink) / 0.08);
  border-color: rgb(var(--ink) / 0.2);
}

.file-selector:disabled,
.file-selector-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.select-arrow {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: rgb(var(--ink) / 0.3);
  pointer-events: none;
  font-size: 10px;
}

.file-dropdown {
  position: absolute;
  top: calc(100%);
  left: 0;
  right: 0;
  margin-top: 1px;
  background-color: var(--surface-3);
  border: 1px solid rgb(var(--ink) / 0.12);
  border-radius: 8px;
  box-shadow: 0 20px 40px rgb(var(--shade) / 0.45);
  max-height: 260px;
  overflow-y: auto;
  z-index: 5;
  padding: 6px 0;
}

.file-dropdown::-webkit-scrollbar {
  display: none;
}

.file-option {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 14px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.file-option:hover {
  background: rgb(var(--ink) / 0.06);
}

.file-name {
  color: var(--text-1);
  font-size: 12px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-desc {
  color: rgb(var(--ink) / 0.5);
  font-size: 11px;
}

.file-empty {
  padding: 12px 14px;
  color: rgb(var(--ink) / 0.4);
  font-size: 13px;
  text-align: center;
}

.file-dropdown-enter-active,
.file-dropdown-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.file-dropdown-enter-from,
.file-dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* Status Display */
.status-display {
  padding: 10px;
  background: rgb(var(--shade) / 0.2);
  border-radius: 8px;
  color: rgb(var(--ink) / 0.6);
  font-size: 13px;
  text-align: center;
  transition: color 0.3s ease, background-color 0.3s ease;
}

.status-active {
  color: var(--accent-indigo);
  background: rgb(var(--accent-indigo-rgb) / 0.1);
}

/* View Toggle */
.view-toggle {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(78px, 1fr));
  gap: 2px;
  background: rgb(var(--shade) / 0.2);
  padding: 4px;
  border-radius: 8px;
}

.toggle-button {
  flex: 1;
  padding: 6px;
  white-space: nowrap;
  border: none;
  background: transparent;
  color: rgb(var(--ink) / 0.5);
  cursor: pointer;
  border-radius: 6px;
  font-size: 13px;
  transition: background-color 0.2s ease, color 0.2s ease;
}

.toggle-button.active {
  background: rgb(var(--ink) / 0.1);
  color: var(--text-1);
  font-weight: 500;
}

/* Work waiting for your review */
.toggle-badge {
  display: inline-grid;
  place-items: center;
  min-width: 16px;
  height: 16px;
  margin-left: 4px;
  padding: 0 4px;
  border-radius: 99px;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  color: #fff;
  background: #f59e0b;
  vertical-align: 1px;
}

/* Active Nodes */
.active-nodes-display {
  flex: 1;
  background: rgb(var(--shade) / 0.2);
  border-radius: 8px;
  padding: 10px;
  overflow-y: auto;
  min-height: 100px;
}

.no-active-nodes {
  color: rgb(var(--ink) / 0.3);
  font-size: 13px;
  text-align: center;
  margin-top: 10px;
}

.active-node-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  margin-bottom: 4px;
  background: rgb(var(--ink) / 0.05);
  border-radius: 4px;
  font-size: 13px;
}

.node-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: var(--accent-sky);
  box-shadow: 0 0 6px var(--accent-sky);
}

/* Button Section */
.button-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cancel-button {
  padding: 12px 14px;
  border-radius: 12px;
  border: none;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  color: var(--bg-base);
  background: linear-gradient(
    135deg,
    #e07152,
    #dc5d4c,
    #bd4a4a
  );
  background-size: 200% 100%;
  animation: gradientShift 6s ease-in-out infinite;
  transition: transform 0.3s ease, box-shadow 0.3s ease, background-color 0.3s ease, color 0.3s ease;
  position: relative;
  overflow: hidden;
}

.cancel-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 15px rgb(var(--shade) / 0.2);
}

.cancel-button:disabled {
  background: var(--line-2);
  color: rgb(var(--ink) / 0.3);
  cursor: not-allowed;
}

.launch-button {
  padding: 14px;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  font-size: 16px;
  font-weight: 600;
  color: var(--bg-base);
  background: linear-gradient(
        135deg,
    var(--accent-mint),
    var(--accent-sky),
    var(--accent-indigo)
  );
  background-size: 200% 100%;
  animation: gradientShift 6s ease-in-out infinite;
  transition: transform 0.3s ease, box-shadow 0.3s ease, background-color 0.3s ease, color 0.3s ease;
  position: relative;
  overflow: hidden;
}

.launch-button:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 15px rgb(var(--shade) / 0.2);
}

.launch-button:disabled {
  background: var(--line-2);
  color: rgb(var(--ink) / 0.3);
  cursor: not-allowed;
}

.launch-button.glow {
  animation: glowPulse 3s ease-in-out infinite, gradientShift 6s ease-in-out infinite;
}

/* Markdown Styles moved to CollapsibleMessage.vue */

@keyframes gradientShift {
  0%, 100% { background-position: 0% 0%; }
  50% { background-position: 100% 0%; }
}

@keyframes glowPulse {
  0% { box-shadow: 0 0 0 0 rgb(var(--accent-indigo-rgb) / 0.4); }
  50% { box-shadow: 0 0 0 5px rgb(var(--accent-sky-rgb) / 0); }
  100% { box-shadow: 0 0 0 0 rgb(var(--accent-indigo-rgb) / 0); }
}

.download-button {
  padding: 12px;
  background: rgb(var(--ink) / 0.03);
  border: 1px solid rgb(var(--ink) / 0.1);
  border-radius: 12px;
  color: var(--text-1);
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.download-button:hover:not(:disabled) {
  background: rgb(var(--ink) / 0.08);
  border-color: rgb(var(--ink) / 0.2);
  transform: translateY(-1px);
}

.download-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Graph Panel */
.graph-panel {
  flex: 1;
  background-color: rgb(var(--ink) / 0.03);
  border: 1px solid rgb(var(--ink) / 0.1);
  border-radius: 12px;
  overflow: hidden;
}

.vueflow-graph {
  width: 100%;
  height: 100%;
}

.image-modal {
  position: fixed;
  inset: 0;
  background: rgb(var(--shade) / 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(2px);
}

.image-modal-content {
  position: relative;
  max-width: 95vw;
  max-height: 95vh;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  background: rgb(var(--panel-26) / 0.9);
  padding: 20px;
  border: 1px solid rgb(var(--ink) / 0.1);
}

.image-modal-content img {
  max-width: 70vw;
  max-height: 65vh;
  box-shadow: 0 20px 40px rgb(var(--shade) / 0.5);
}

.image-modal-enter-active,
.image-modal-leave-active {
  transition: opacity 0.2s ease;
}

.image-modal-enter-from,
.image-modal-leave-to {
  opacity: 0;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
}

.settings-button {
  background: transparent;
  border: none;
  color: var(--accent-indigo);
  cursor: pointer;
  padding: 8px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.2s;
}

.settings-button:hover {
  background-color: rgb(var(--accent-indigo-rgb) / 0.1);
}

@media (prefers-reduced-motion: reduce) {
  .launch-button,
  .cancel-button,
  .launch-button.glow,
  .input-shell.glow,
  .loading-bubble,
  .entry-running,
  .microphone-button.pulsating,
  .notification-content {
    animation: none;
  }

  .chat-panel,
  .right-panel-overlay,
  .chat-panel-toggle svg,
  .message-bubble,
  .input-shell,
  .status-display,
  .launch-button,
  .cancel-button,
  .download-button,
  .right-panel-fab,
  .file-dropdown-enter-active,
  .file-dropdown-leave-active,
  .loading-entry-enter-active,
  .loading-entry-leave-active,
  .image-modal-enter-active,
  .image-modal-leave-active {
    transition-duration: 0.01ms;
  }
}

/* ---------- Light theme: white glass cards instead of dark tinted panels ---------- */
:root[data-theme="light"] .header {
  background-color: rgb(255 255 255 / 0.72);
  border-bottom-color: rgb(var(--ink) / 0.08);
}
:root[data-theme="light"] .chat-panel-content,
:root[data-theme="light"] .chat-panel-fullscreen .chat-panel-content,
:root[data-theme="light"] .graph-panel {
  background: rgb(255 255 255 / 0.82);
  border-color: rgb(var(--ink) / 0.08);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.04), 0 10px 30px -14px rgb(15 23 42 / 0.14);
}
:root[data-theme="light"] .control-section {
  background: rgb(255 255 255 / 0.95);
  border-color: rgb(var(--ink) / 0.08);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.04), 0 10px 30px -14px rgb(15 23 42 / 0.14);
}
:root[data-theme="light"] .input-shell {
  background-color: rgb(255 255 255 / 0.95);
  border-color: rgb(var(--ink) / 0.1);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.04);
}
:root[data-theme="light"] .input-shell:focus-within {
  background-color: #fff;
  border-color: rgb(var(--accent-sky-rgb) / 0.55);
  box-shadow: 0 0 0 3px rgb(var(--accent-sky-rgb) / 0.12);
}
:root[data-theme="light"] .file-selector-input {
  background-color: #fff;
  border-color: rgb(var(--ink) / 0.12);
}
:root[data-theme="light"] .file-selector-input:hover:not(:disabled),
:root[data-theme="light"] .file-selector-input:focus {
  background-color: #fff;
  border-color: rgb(var(--accent-sky-rgb) / 0.55);
}

/* ---------- Light theme: legibility (low-alpha ink text is too faint on white) ---------- */
:root[data-theme="light"] .back-button,
:root[data-theme="light"] .chat-panel-toggle {
  color: var(--text-soft-1);
}
:root[data-theme="light"] .chat-panel-toggle {
  border-color: rgb(var(--ink) / 0.16);
}
:root[data-theme="light"] .user-name,
:root[data-theme="light"] .message-timestamp,
:root[data-theme="light"] .chat-notification .message-timestamp,
:root[data-theme="light"] .attachment-meta,
:root[data-theme="light"] .file-desc,
:root[data-theme="light"] .file-empty,
:root[data-theme="light"] .no-active-nodes,
:root[data-theme="light"] .loading-entry-duration,
:root[data-theme="light"] .artifact-status {
  color: var(--text-muted-1);
}
:root[data-theme="light"] .section-label {
  color: var(--text-soft-1);
}
:root[data-theme="light"] .task-input::placeholder {
  color: var(--text-muted-1);
}
:root[data-theme="light"] .select-arrow {
  color: var(--text-muted-1);
}
:root[data-theme="light"] .notification-text,
:root[data-theme="light"] .artifact-filename,
:root[data-theme="light"] .loading-timer {
  color: var(--text-soft-3);
}
:root[data-theme="light"] .notification-content {
  background: var(--surface-4);
  border-color: rgb(var(--ink) / 0.12);
}
:root[data-theme="light"] .chat-notification-warning .notification-content {
  background: #fffbeb;
  border-color: #fcd34d;
}
:root[data-theme="light"] .chat-notification-warning .notification-text {
  color: #92400e;
}
:root[data-theme="light"] .chat-notification-error .notification-content {
  background: #fef2f2;
  border-color: #fca5a5;
}
:root[data-theme="light"] .chat-notification-error .notification-text {
  color: #991b1b;
}

/* Bubbles / entries: give edges enough definition on white */
:root[data-theme="light"] .message-bubble {
  background: var(--surface-4);
  border-color: rgb(var(--ink) / 0.12);
}
:root[data-theme="light"] .dialogue-right .message-bubble {
  background: linear-gradient(135deg, rgb(var(--accent-indigo-rgb) / 0.1), rgb(var(--accent-indigo-rgb) / 0.06));
  border-color: rgb(var(--accent-indigo-rgb) / 0.3);
}
:root[data-theme="light"] .message-bubble.loading-bubble {
  background-color: var(--surface-4);
  border-color: var(--accent-mint);
}
:root[data-theme="light"] .loading-entry.entry-running {
  border-color: var(--accent-mint);
}
:root[data-theme="light"] .loading-entry {
  background: #fff;
  border-color: rgb(var(--ink) / 0.16);
}
:root[data-theme="light"] .loading-entry-label {
  color: var(--text-1);
}
:root[data-theme="light"] .entry-done {
  opacity: 1;
  border-color: rgb(var(--ink) / 0.14);
}

/* Input controls */
:root[data-theme="light"] .microphone-button,
:root[data-theme="light"] .attachment-button,
:root[data-theme="light"] .artifact-download-button {
  background: #fff;
  border-color: rgb(var(--ink) / 0.2);
  color: var(--text-soft-3);
}
:root[data-theme="light"] .microphone-button:hover:not(:disabled),
:root[data-theme="light"] .attachment-button:hover:not(:disabled),
:root[data-theme="light"] .artifact-download-button:hover:not(:disabled) {
  background: var(--surface-4);
  border-color: rgb(var(--ink) / 0.35);
  color: var(--text-1);
}
:root[data-theme="light"] .microphone-button.recording {
  background: var(--surface-4);
  border-color: var(--accent-mint);
  color: var(--text-1);
}
:root[data-theme="light"] .attachment-count {
  background: var(--accent-sky-2);
  color: #fff;
}
:root[data-theme="light"] .remove-attachment,
:root[data-theme="light"] .drag-overlay-content {
  color: var(--accent-sky-2);
}
:root[data-theme="light"] .drag-overlay {
  background: rgb(255 255 255 / 0.85);
}
:root[data-theme="light"] .attachment-modal,
:root[data-theme="light"] .file-dropdown {
  border-color: rgb(var(--ink) / 0.14);
  box-shadow: 0 12px 32px -8px rgb(15 23 42 / 0.18);
}
:root[data-theme="light"] .attachment-item {
  background: var(--surface-4);
}
:root[data-theme="light"] .file-option:hover {
  background: var(--surface-4);
}

/* Right panel: status, toggle, active nodes */
:root[data-theme="light"] .status-display,
:root[data-theme="light"] .view-toggle,
:root[data-theme="light"] .active-nodes-display {
  background: var(--surface-4);
}
:root[data-theme="light"] .status-display {
  color: var(--text-soft-1);
}
:root[data-theme="light"] .status-active {
  color: var(--accent-indigo-2);
  background: rgb(var(--accent-indigo-rgb) / 0.1);
}
:root[data-theme="light"] .toggle-button {
  color: var(--text-soft-1);
}
:root[data-theme="light"] .toggle-button.active {
  background: #fff;
  color: var(--text-1);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.1);
}
:root[data-theme="light"] .active-node-item {
  background: #fff;
  border: 1px solid rgb(var(--ink) / 0.08);
  color: var(--text-2);
}
:root[data-theme="light"] .node-dot {
  box-shadow: none;
}
:root[data-theme="light"] .right-panel-fab {
  color: var(--accent-indigo-2);
}

/* Primary buttons: white text needs a darker gradient than the pastel-tuned one */
:root[data-theme="light"] .launch-button {
  color: #fff;
  background: linear-gradient(135deg, #0f766e, #0369a1, #4338ca);
  background-size: 200% 100%;
}
:root[data-theme="light"] .cancel-button {
  color: #fff;
  background: linear-gradient(135deg, #c2410c, #b91c1c, #991b1b);
  background-size: 200% 100%;
}
:root[data-theme="light"] .launch-button:disabled,
:root[data-theme="light"] .cancel-button:disabled {
  background: var(--surface-5);
  color: var(--text-muted-1);
}
:root[data-theme="light"] .download-button {
  background: #fff;
  border-color: rgb(var(--ink) / 0.16);
}
:root[data-theme="light"] .download-button:hover:not(:disabled) {
  background: var(--surface-4);
  border-color: rgb(var(--ink) / 0.28);
}
:root[data-theme="light"] .settings-button {
  color: var(--accent-indigo-2);
}
:root[data-theme="light"] .image-modal {
  background: rgb(15 23 42 / 0.55);
}
:root[data-theme="light"] .image-modal-content {
  background: rgb(255 255 255 / 0.96);
  border-color: rgb(var(--ink) / 0.12);
}

</style>
