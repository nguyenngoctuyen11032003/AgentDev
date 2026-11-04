<template>
  <div class="launch-view">
    <div class="header">
      <!-- The app's own nav is hidden on this page (it opens in a tab of its own): the logo is the way back -->
      <router-link to="/" target="_blank" rel="noopener" class="brand-link" :aria-label="$t('launch.shell.home')" :title="$t('launch.shell.home')">
        <img src="/media/logo.svg?v=2" alt="" width="24" height="24" />
      </router-link>
      <h1>{{ $t('launch.title') }}</h1>
      <!-- Persistent view switcher: the same in every mode and at every width -->
      <div class="view-tabs" role="tablist" :aria-label="$t('launch.view')" @keydown="onViewTabKey">
        <button
          v-for="option in viewOptions"
          :id="`view-tab-${option.mode}`"
          :key="option.mode"
          type="button"
          role="tab"
          class="view-tab"
          :class="{ active: viewMode === option.mode }"
          :aria-selected="viewMode === option.mode"
          :tabindex="viewMode === option.mode ? 0 : -1"
          @click="selectView(option.mode)"
        >
          {{ $t(option.label) }}
          <span v-if="option.mode === 'review' && reviewPendingCount" class="toggle-badge">{{ reviewPendingCount }}</span>
        </button>
      </div>
      <div class="header-actions">
        <router-link to="/workflows" target="_blank" rel="noopener" class="header-btn header-link" :title="$t('launch.shell.workflows_hint')" :aria-label="$t('launch.shell.workflows_hint')">
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="6" rx="1.5"></rect><rect x="14" y="15" width="7" height="6" rx="1.5"></rect><path d="M6.5 9v3.5a2 2 0 0 0 2 2h9V15"></path></svg>
          <span class="header-btn-label">{{ $t('launch.shell.workflows') }}</span>
        </router-link>
        <button
          type="button"
          class="header-btn"
          :class="{ active: isControlsVisible, 'needs-workflow': !selectedFile && !loading }"
          :aria-expanded="isControlsVisible"
          :aria-label="$t('launch.panel.toggle')"
          :title="$t('launch.panel.toggle')"
          @click="toggleControls"
        >
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5"></rect><line x1="15" y1="4" x2="15" y2="20"></line></svg>
          <span class="header-btn-label">{{ $t('launch.panel.toggle') }}</span>
        </button>
      <button class="header-btn settings-button" type="button" @click="showSettingsModal = true" :title="$t('launch.settings')" :aria-label="$t('launch.settings')">
        <svg aria-hidden="true" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="3"></circle>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
        </svg>
        <span class="header-btn-label settings-label">{{ $t('launch.settings') }}</span>
      </button>
      </div>
    </div>
    <div class="content">
      <!-- Session history: switch between runs and pick up where you left off -->
      <!-- Wide: a column. Narrow (< 900px): a drawer that slides over the chat -->
      <div
        ref="sessionsDrawerRef"
        class="sessions-drawer"
        :class="{ 'is-drawer': isNarrow, 'is-open': isSessionsDrawerOpen }"
        :inert="isNarrow && !isSessionsDrawerOpen ? true : undefined"
      >
        <!-- Wide, collapsed: a slim rail keeps the three things people reach for -->
        <nav v-if="!isNarrow && !isSessionSidebarOpen" class="sessions-rail" :aria-label="$t('launch.sessions.title')">
          <button
            type="button"
            class="rail-btn"
            :title="$t('launch.shell.sessions_expand')"
            :aria-label="$t('launch.shell.sessions_expand')"
            aria-expanded="false"
            @click="toggleSessionsPanel"
          >
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5"></rect><line x1="9" y1="4" x2="9" y2="20"></line><path d="m13 10 2 2-2 2"></path></svg>
            <span v-if="hasLiveSession" class="rail-dot" :title="$t('launch.shell.sessions_live')"></span>
          </button>
          <button type="button" class="rail-btn" :title="newSessionLabel" :aria-label="newSessionLabel" @click="startNewSession()">
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"></path></svg>
          </button>
          <button type="button" class="rail-btn" :title="$t('launch.shell.sessions_search')" :aria-label="$t('launch.shell.sessions_search')" @click="openSessionSearch">
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg>
          </button>
        </nav>
        <SessionSidebar
          v-show="isNarrow || isSessionSidebarOpen"
          :sessions="sessions"
          :active-id="activeSessionId"
          :draft="draftWorkflow"
          :draft-project="currentProjectName"
          :project-workflows="projectWorkflows"
          :collapsed="false"
          :loading="!sessionsLoaded"
          @select="onSidebarSelect"
          @new="onSidebarNew"
          @add-project="handleAddProject"
          @delete-group="handleDeleteGroup"
          @rename="handleRenameSession"
          @delete="handleDeleteSession"
          @toggle="toggleSessionsPanel"
        />
      </div>
      <div v-if="isNarrow && isSessionsDrawerOpen" class="sheet-backdrop" @click="isSessionsDrawerOpen = false"></div>

      <!-- Left panel -->
      <div ref="leftPanelRef" class="left-panel" :style="chatWidthStyle">
        <!-- Outside the chat view, a collapsed chat leaves a slim rail: nothing floats over the work -->
        <div v-if="viewMode !== 'chat' && !isChatPanelOpen" class="chat-rail">
          <button
            type="button"
            class="rail-btn"
            :title="$t('launch.shell.chat_expand')"
            :aria-label="$t('launch.shell.chat_expand')"
            aria-expanded="false"
            @click="isChatPanelOpen = true"
          >
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
            <span v-if="pendingQuestion || hasUnseenMessages" class="rail-dot" :class="{ 'is-waiting': pendingQuestion }" :title="pendingQuestion ? $t('launch.shell.lead_waiting') : $t('launch.jump_to_latest')"></span>
          </button>
        </div>
        <!-- Chat Panel: fullscreen in chat mode, a resizable column over the canvas elsewhere -->
        <div
          class="chat-panel"
          :class="{
            'chat-panel-fullscreen': viewMode === 'chat',
            'chat-panel-collapsed': viewMode !== 'chat' && !isChatPanelOpen,
            'is-resizing': isResizingChat
          }"
        >
          <div
            v-if="viewMode !== 'chat' && isChatPanelOpen && !isNarrow"
            class="chat-resizer"
            role="separator"
            tabindex="0"
            aria-orientation="vertical"
            :aria-label="$t('launch.shell.chat_resize')"
            :title="$t('launch.shell.chat_resize')"
            :aria-valuenow="chatWidth"
            :aria-valuemin="CHAT_MIN_W"
            :aria-valuemax="CHAT_MAX_W"
            @pointerdown="startChatResize"
            @keydown="onChatResizeKey"
            @dblclick="setChatWidth(CHAT_DEFAULT_W)"
          ></div>
          <!-- Kept laid out while collapsed (hidden via CSS) so the panel can slide on the
               compositor and reopening a long chat never re-lays out every message -->
          <div class="chat-panel-content" :inert="viewMode !== 'chat' && !isChatPanelOpen ? true : undefined">
            <div class="chat-header">
              <div class="chat-header-main">
                <div class="chat-header-row">
                  <span class="chat-header-title" :title="currentSessionTitle">{{ currentSessionTitle }}</span>
                  <!-- The one place the run state lives: visible in every view -->
                  <span v-if="selectedFile" class="chat-header-status" role="status">
                    <StatusPill compact :tone="statusPillTone" :label="isStopping ? $t('launch.stopping') : statusLabel" />
                  </span>
                </div>
                <span v-if="selectedFile" class="chat-header-sub">
                  <span v-if="currentProjectName" class="chat-header-project" :title="$t('launch.sessions.project_label', { name: currentProjectName })">
                    <svg aria-hidden="true" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
                    <span class="chat-header-project-name">{{ currentProjectName }}</span>
                  </span>
                  <span class="chat-header-workflow">{{ workflowTitle }}</span>
                </span>
              </div>
              <div class="chat-header-actions">
                <button
                  type="button"
                  class="chat-header-btn"
                  :class="{ active: isNarrow ? isSessionsDrawerOpen : isSessionSidebarOpen }"
                  :title="$t('launch.sessions.history')"
                  :aria-label="$t('launch.sessions.history')"
                  @click="toggleSessionsPanel"
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
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-4.2-7.6"></path><path d="M12 8v8M8 12h8"></path></svg>
                </button>
                <!-- Outside the chat view: fold the chat away to a rail (the work gets the room) -->
                <button
                  v-if="viewMode !== 'chat'"
                  type="button"
                  class="chat-header-btn"
                  :title="$t('launch.shell.chat_collapse')"
                  :aria-label="$t('launch.shell.chat_collapse')"
                  :aria-expanded="isChatPanelOpen"
                  @click="isChatPanelOpen = false"
                >
                  <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5"></rect><line x1="9" y1="4" x2="9" y2="20"></line><path d="m16 10-2 2 2 2"></path></svg>
                </button>
              </div>
            </div>
            <div class="chat-box">
              <!-- This session is open in another tab: nothing reconnects by itself (the tabs
                   would take it from each other forever); the button takes it back here -->
              <div v-if="replacedSessionId" class="replaced-banner" role="status">
                <span class="replaced-banner-text">{{ $t('launch.replaced_by_other_tab') }}</span>
                <button type="button" class="replaced-banner-button" @click="takeOverSession">
                  {{ $t('launch.take_over_here') }}
                </button>
              </div>
              <div class="chat-messages" ref="chatMessagesRef" @click="handleChatClick">
                <!-- Empty session: say who answers and what to do, like a new Claude / Codex chat -->
                <div v-if="!chatMessages.length && !isReconnecting && (selectedFile || !loading)" class="chat-empty">
                  <span class="chat-empty-avatar" aria-hidden="true">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="3.5"></circle><path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5"></path></svg>
                  </span>
                  <template v-if="selectedFile">
                    <h2 class="chat-empty-title">{{ leadName ? $t('launch.empty_chat.greeting_lead', { lead: leadName }) : $t('launch.empty_chat.title') }}</h2>
                    <p class="chat-empty-hint">{{ currentProjectName ? $t('launch.empty_chat.hint_project', { project: currentProjectName }) : $t('launch.empty_chat.hint_team') }}</p>
                    <div class="chat-empty-suggest" role="list" :aria-label="$t('launch.chat_ui.suggestions_label')">
                      <button
                        v-for="key in EMPTY_SUGGESTION_KEYS"
                        :key="key"
                        type="button"
                        role="listitem"
                        class="chat-empty-chip"
                        :disabled="!isConnectionReady || isStopping"
                        @click="pickSuggestion($t(key, { workflow: workflowTitle }))"
                      >{{ $t(key, { workflow: workflowTitle }) }}</button>
                    </div>
                    <p class="chat-empty-note">{{ $t('launch.empty_chat.plan_note') }}</p>
                  </template>
                  <template v-else>
                    <h2 class="chat-empty-title">{{ $t('launch.empty_chat.pick_title') }}</h2>
                    <p class="chat-empty-hint">{{ $t('launch.empty_chat.pick_hint') }}</p>
                    <button type="button" class="btn primary chat-empty-pick" @click="focusWorkflowPicker">{{ $t('launch.composer.pick_workflow_action') }}</button>
                  </template>
                </div>
                <div v-if="isReconnecting && !chatMessages.length" class="chat-skeleton" role="status" :aria-label="$t('launch.loading')">
                  <BaseSkeleton width="40%" height="14px" />
                  <BaseSkeleton height="14px" />
                  <BaseSkeleton width="85%" height="14px" />
                  <BaseSkeleton width="55%" height="14px" />
                </div>
                <!-- Notifications and dialogues in order -->
                <div
                  v-for="message in chatMessages"
                  :key="messageKey(message)"
                  class="chat-message-item"
                  v-memo="[
                    message.rev,
                    messageAvatar(message),
                    message.duration,
                    message.loading,
                    message.dataUri,
                    message.error,
                    configStore.AUTO_EXPAND_MESSAGES,
                    message.plan ? isPlanOpen(message) : false,
                    message.retryPrompt ? canRetryRun(message) : false,
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
                  <button
                    v-if="canRetryRun(message)"
                    type="button"
                    class="send-error-btn send-error-retry notification-retry"
                    :disabled="loading || isStopping"
                    @click="retryRun(message)"
                  >
                    {{ $t('launch.chat_ui.retry') }}
                  </button>
                  <div class="message-timestamp">{{ formatTime(message.timestamp) }}</div>
                </div>
              </div>

              <!-- Dialogue -->
              <div
                v-else-if="message.type === 'dialogue'"
                class="dialogue"
                :class="{ 'dialogue-right': message.isRight }"
              >
                <div v-if="!message.isRight" class="profile-picture">
                  <img :src="messageAvatar(message)" :alt="$t('launch.avatar_alt', { name: getDisplayName(message) })" />
                </div>
                <div class="message-content">
                  <div v-if="!message.isRight" class="user-name">
                    {{ getDisplayName(message) }}
                    <span v-if="message.isQuestion" class="question-tag">{{ $t('launch.question_tag') }}</span>
                    <span class="message-timestamp">{{ formatTime(message.timestamp) }}</span>
                  </div>
                  <div
                    class="message-bubble"
                    :class="{ 'loading-bubble': message.isLoading }"
                    :title="message.isRight ? formatTime(message.timestamp) : undefined"
                  >
                  <!-- Agent activity: one quiet line (like Claude / ChatGPT), details on demand -->
                  <div
                    v-if="message.loadingEntries && (message.isLoading || message.loadingEntries.length)"
                    class="activity"
                    :class="{ 'activity-running': message.isLoading, 'activity-open': message.activityOpen }"
                  >
                    <!-- Finished: one collapsed line; the steps on demand -->
                    <button
                      v-if="!message.isLoading"
                      type="button"
                      class="activity-summary"
                      :aria-expanded="!!message.activityOpen"
                      @click="toggleActivity(message)"
                    >
                      <svg class="activity-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"></path></svg>
                      <span class="activity-label">{{ activityHeadline(message) }}</span>
                    </button>
                    <!-- Running: the last few finished steps grow above the live one -->
                    <button
                      v-if="message.isLoading && hiddenStepCount(message)"
                      type="button"
                      class="activity-more"
                      :aria-expanded="!!message.activityOpen"
                      @click="toggleActivity(message)"
                    >
                      {{ message.activityOpen ? $t('launch.activity.fewer_steps') : $t('launch.activity.more_steps', { n: hiddenStepCount(message) }) }}
                    </button>
                    <ol v-if="message.activityOpen || (message.isLoading && shownSteps(message).length)" class="activity-steps">
                      <li
                        v-for="entry in shownSteps(message)"
                        :key="entry.key"
                        class="activity-step"
                        :class="{ 'step-running': entry.status === 'running' }"
                      >
                        <component
                          :is="entry.detailHtml ? 'button' : 'div'"
                          :type="entry.detailHtml ? 'button' : undefined"
                          class="activity-step-row"
                          :class="{ 'activity-step-toggle': !!entry.detailHtml }"
                          :aria-expanded="entry.detailHtml ? !!entry.detailOpen : undefined"
                          @click="entry.detailHtml && toggleStepDetail(message, entry)"
                        >
                          <span class="activity-step-dot" aria-hidden="true"></span>
                          <span class="activity-step-label">{{ stepLabel(entry) }}<span v-if="entry.count > 1" class="activity-step-count"> ×{{ entry.count }}</span></span>
                          <svg v-if="entry.detailHtml" class="activity-step-chevron" :class="{ 'is-open': entry.detailOpen }" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"></path></svg>
                          <span v-if="showStepTime(entry)" class="activity-step-time">
                            <LiveDuration :started-at="entry.startedAt" :ended-at="entry.endedAt || 0" />
                          </span>
                        </component>
                        <!-- A member's report to its lead: readable here, not a chat message of its own -->
                        <div v-if="entry.detailHtml && entry.detailOpen" class="activity-step-detail">
                          <CollapsibleMessage
                            :html-content="entry.detailHtml"
                            :raw-content="entry.detailText"
                            :default-expanded="false"
                          />
                        </div>
                      </li>
                    </ol>
                    <div v-if="message.isLoading" class="activity-live" role="status">
                      <span class="activity-spinner" aria-hidden="true"></span>
                      <span class="activity-label">{{ liveStep(message).label }}</span>
                      <span class="activity-time">
                        <LiveDuration :key="liveStep(message).at" :started-at="liveStep(message).at" />
                      </span>
                    </div>
                  </div>

                  <!-- The lead's plan waiting for your go-ahead (replaces its normal answer) -->
                  <div v-if="message.plan" class="plan-card" :class="{ 'plan-card-open': isPlanOpen(message) }">
                    <div class="plan-card-head">
                      <span class="plan-card-badge">{{ isPlanOpen(message) ? $t('launch.plan.awaiting') : $t('launch.plan.title') }}</span>
                    </div>
                    <p v-if="message.plan.summary" class="plan-card-summary">{{ message.plan.summary }}</p>
                    <details class="plan-card-details" :open="isPlanOpen(message) || !message.plan.summary">
                      <summary>{{ $t('launch.plan.show') }}</summary>
                      <CollapsibleMessage
                        v-if="message.plan.plan || message.text"
                        :html-content="message.plan.plan ? renderMarkdown(message.plan.plan) : (message.htmlContent || renderMarkdown(message.text))"
                        :raw-content="message.plan.plan || message.text"
                        :default-expanded="true"
                      />
                    </details>
                    <div v-if="isPlanOpen(message)" class="plan-card-actions">
                      <button type="button" class="plan-btn plan-btn-primary" :disabled="loading || isStopping" @click="approvePlan">
                        {{ $t('launch.plan.approve') }}
                      </button>
                      <button type="button" class="plan-btn" @click="requestPlanChanges">
                        {{ $t('launch.plan.request_changes') }}
                      </button>
                    </div>
                  </div>

                  <template v-else-if="message.text">
                    <CollapsibleMessage
                      v-if="!userAttachments(message) || userAttachments(message).body"
                      :html-content="userAttachments(message) ? renderMarkdown(userAttachments(message).body) : (message.htmlContent || renderMarkdown(message.text))"
                      :raw-content="userAttachments(message) ? userAttachments(message).body : message.text"
                      :default-expanded="true"
                    />
                    <!-- "Tệp đính kèm: a, b/" in a user message: one chip per file or folder -->
                    <ul v-if="userAttachments(message)" class="msg-attachments" :aria-label="$t('launch.attachments_label')">
                      <li v-for="name in userAttachments(message).names" :key="name" class="msg-attachment">
                        <svg v-if="name.endsWith('/')" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path></svg>
                        <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"></path><polyline points="14 3 14 8 19 8"></polyline></svg>
                        <span class="msg-attachment-name">{{ name }}</span>
                      </li>
                    </ul>
                  </template>

                  <!-- Files the turn produced (the agent's and its team's), each shown once -->
                  <div v-if="message.files && message.files.length" class="turn-files">
                    <div v-for="file in message.files" :key="file.fileName" class="turn-file">
                      <img
                        v-if="file.isImage && file.dataUri"
                        :src="file.dataUri"
                        :alt="file.fileName || $t('launch.image_artifact_alt')"
                        class="artifact-image"
                        role="button"
                        tabindex="0"
                        @click="openImageModal(file)"
                        @keydown.enter.prevent="openImageModal(file)"
                        @keydown.space.prevent="openImageModal(file)"
                      />
                      <div v-else-if="file.error" class="artifact-status artifact-error">{{ file.error }}</div>
                      <div class="artifact-file-wrapper">
                        <div class="artifact-filename">
                          <img
                            v-if="getFilePreviewSrc(file)"
                            :src="getFilePreviewSrc(file)"
                            :alt="$t('launch.file_preview_alt', { name: file.fileName || '' })"
                            class="artifact-filename-icon"
                          />
                          <span class="artifact-filename-text">{{ file.fileName }}</span>
                        </div>
                        <button
                          class="artifact-download-button"
                          type="button"
                          :disabled="file.loading"
                          @click="downloadTurnFile(message, file)"
                        >
                          {{ file.loading ? $t('launch.preparing') : $t('launch.download') }}
                        </button>
                      </div>
                    </div>
                  </div>

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
                </div>
                </div>
              </div>
            </div>
          </div>
            </div>
            <div class="input-area">
              <!-- Scrolled up while new messages came in: one click back to the latest -->
              <Transition name="jump-latest">
                <button
                  v-if="hasUnseenMessages || isScrolledUp"
                  type="button"
                  class="jump-latest"
                  :aria-label="hasUnseenMessages ? $t('launch.jump_to_latest') : $t('launch.chat_ui.scroll_to_bottom')"
                  @click="jumpToLatest"
                >
                  {{ hasUnseenMessages ? $t('launch.jump_to_latest') : $t('launch.chat_ui.scroll_to_bottom') }}
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"></line><polyline points="19 12 12 19 5 12"></polyline></svg>
                </button>
              </Transition>
              <!-- The lead waits on you: its question stays in view right above the box -->
              <div v-if="pendingQuestion" class="question-card" role="status">
                <div class="question-card-head">
                  <span class="question-card-dot" aria-hidden="true"></span>
                  {{ pendingQuestion.name ? $t('launch.question_card.asking', { name: pendingQuestion.name }) : $t('launch.question_card.asking_any') }}
                </div>
                <div
                  v-if="pendingQuestion.text"
                  class="question-card-text"
                  :class="{ 'is-clamped': !isQuestionExpanded }"
                >{{ pendingQuestion.text }}</div>
                <button
                  v-if="pendingQuestion.isLong"
                  type="button"
                  class="question-card-toggle"
                  @click="isQuestionExpanded = !isQuestionExpanded"
                >
                  {{ isQuestionExpanded ? $t('components.collapsible_message.show_less') : $t('components.collapsible_message.show_more') }}
                </button>
              </div>
              <!-- The message never reached the server: it is still in the box, one click resends it -->
              <div v-if="launchError" class="send-error" role="alert">
                <span class="send-error-text">{{ launchError }}</span>
                <button
                  type="button"
                  class="send-error-btn send-error-retry"
                  :disabled="loading || isStopping || isWorkflowRunning || !hasComposerContent"
                  @click="retryLaunch"
                >
                  {{ $t('launch.chat_ui.retry') }}
                </button>
                <button
                  type="button"
                  class="send-error-btn"
                  :aria-label="$t('launch.chat_ui.dismiss')"
                  :title="$t('launch.chat_ui.dismiss')"
                  @click="launchError = ''"
                >
                  ×
                </button>
              </div>
              <!-- Why the box cannot send yet (the old Run button's disabled reasons live here now) -->
              <p v-if="composerHint" class="composer-hint" role="status">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><line x1="12" y1="8" x2="12" y2="12.5"></line><circle cx="12" cy="16" r="0.6" fill="currentColor"></circle></svg>
                <span>{{ composerHint }}</span>
                <button v-if="!selectedFile && !loading && chatMessages.length" type="button" class="composer-hint-action" @click="focusWorkflowPicker">
                  {{ $t('launch.composer.pick_workflow_action') }}
                </button>
              </p>
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
                    <span v-else class="chip-icon">{{ attachmentIcon(attachment) }}</span>
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
                  :disabled="!isConnectionReady || isStopping"
                  :placeholder="composerPlaceholder"
                  :aria-label="$t(leadName ? 'launch.chat_ui.composer_label' : 'launch.chat_ui.composer_label_agent')"
                  ref="taskInputRef"
                  @input="autoResizeTaskInput"
                  @keydown.enter="handleEnterKey"
                  @compositionstart="handleCompositionStart"
                  @compositionend="handleCompositionEnd"
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
                      :disabled="!isConnectionReady || !sessionId || isUploadingAttachment || isStopping || (isWorkflowRunning && status !== 'Waiting for input...')"
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
                    :disabled="isStopping || (!isStopMode && (loading || (isWorkflowRunning && !hasComposerContent) || (!isWorkflowRunning && !isRunFinished && !isConnectionReady)))"
                    @click="isStopMode ? cancelWorkflow() : handlePanelRunClick()"
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

        <div v-show="viewMode === 'graph'" class="graph-panel graph-flow-panel" :style="insetStyle">
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
          </VueFlow>
          <!-- Its own bar above the canvas: the zoom controls never sit on a node -->
          <div class="graph-bar">
            <h2 class="graph-bar-title">{{ workflowTitle || $t('launch.graph') }}</h2>
            <div class="graph-tools" role="toolbar" :aria-label="$t('launch.graph')">
              <button type="button" class="graph-tool" :title="$t('launch.shell.zoom_out')" :aria-label="$t('launch.shell.zoom_out')" @click="zoomOut?.()">
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="5" y1="12" x2="19" y2="12"></line></svg>
              </button>
              <span class="graph-zoom">{{ Math.round((viewport?.zoom || 1) * 100) }}%</span>
              <button type="button" class="graph-tool" :title="$t('launch.shell.zoom_in')" :aria-label="$t('launch.shell.zoom_in')" @click="zoomIn?.()">
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
              </button>
              <button type="button" class="graph-tool" :title="$t('launch.shell.zoom_fit')" :aria-label="$t('launch.shell.zoom_fit')" @click="fitView()">
                <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"></path></svg>
              </button>
              <button
                type="button"
                class="graph-tool"
                :aria-pressed="!isGraphInteractive"
                :title="isGraphInteractive ? $t('launch.shell.graph_lock') : $t('launch.shell.graph_unlock')"
                :aria-label="isGraphInteractive ? $t('launch.shell.graph_lock') : $t('launch.shell.graph_unlock')"
                @click="toggleGraphInteractive"
              >
                <svg v-if="isGraphInteractive" aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="10" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 7.8-1.2"></path></svg>
                <svg v-else aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="10" rx="2"></rect><path d="M8 11V7a4 4 0 0 1 8 0v4"></path></svg>
              </button>
            </div>
          </div>
        </div>

        <div v-show="viewMode === 'office'" class="graph-panel office-panel" :style="officeInsetStyle">
          <OfficeView
            ref="officeRef"
            :graph="officeGraph"
            :sprite-map="nodeSpriteMap"
            :active-nodes="activeNodes"
            :status="status"
            :workflow-name="selectedFile ? selectedFile.replace(/\.yaml$/i, '') : ''"
            :tracker="runTracker.state"
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
            @pending-count="reviewPendingFromView = $event"
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

      </div>

      <div v-if="isNarrow && isControlSheetOpen" class="sheet-backdrop" @click="isControlSheetOpen = false"></div>

      <!-- Control panel. Chat view: a column (can be folded away from the header). Other views:
           a drawer on the right, opened from the header. Narrow: a bottom sheet. -->
      <div
        class="right-panel"
        :class="{
          'right-panel-overlay': !isNarrow && viewMode !== 'chat',
          'right-panel-collapsed': !isNarrow && viewMode !== 'chat' && !isRightPanelOpen,
          'right-panel-hidden': !isNarrow && viewMode === 'chat' && !isStatusColumnOpen,
          'is-sheet': isNarrow,
          'is-open': isControlSheetOpen
        }"
        :inert="(isNarrow && !isControlSheetOpen) || (!isNarrow && !isControlsVisible) ? true : undefined"
      >
        <div v-show="isNarrow || isControlsVisible" class="control-section" role="region" :aria-label="$t('launch.panel.toggle')">
          <div v-if="isNarrow || viewMode !== 'chat'" class="sheet-head">
            <span v-if="isNarrow" class="sheet-grip" aria-hidden="true"></span>
            <h2 class="sheet-title">{{ $t('launch.panel.toggle') }}</h2>
            <button type="button" class="chat-header-btn" :aria-label="$t('launch.panel.close')" :title="$t('launch.panel.close')" @click="closeControls">
              <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>
            </button>
          </div>

          <section class="panel-block">
            <label class="panel-heading" for="launch-workflow-select">{{ $t('launch.workflow_selection') }}</label>
            <div ref="workflowPickerRef" class="workflow-picker" :class="{ 'needs-workflow': !selectedFile && !loading, nudge: pickerNudge }">
              <BaseSkeleton v-if="loading && !workflowFiles.length" height="40px" radius="10px" />
              <BaseSelect
                v-else
                id="launch-workflow-select"
                :model-value="selectedFile"
                :disabled="loading || isWorkflowRunning"
                @update:model-value="selectWorkflow"
              >
                <option value="" disabled>{{ loading ? $t('launch.loading') : $t('launch.select_yaml') }}</option>
                <option v-for="workflow in workflowFiles" :key="workflow.name" :value="workflow.name">{{ workflow.name.replace(/\.ya?ml$/i, '') }}</option>
              </BaseSelect>
            </div>
            <template v-if="selectedDescription">
              <p id="launch-workflow-desc" ref="descriptionRef" class="panel-note" :class="{ 'is-clamped': !isDescriptionOpen }">{{ selectedDescription }}</p>
              <button
                v-if="isDescriptionLong"
                type="button"
                class="panel-link"
                aria-controls="launch-workflow-desc"
                :aria-expanded="isDescriptionOpen"
                @click="isDescriptionOpen = !isDescriptionOpen"
              >{{ isDescriptionOpen ? $t('components.collapsible_message.show_less') : $t('components.collapsible_message.show_more') }}</button>
            </template>
            <p v-if="workflowHint" class="workflow-hint">{{ workflowHint }}</p>
          </section>

          <!-- Details of this run; its state itself is the chip in the chat header -->
          <section v-if="runFacts.length" class="panel-block">
            <h3 class="panel-heading">{{ $t('launch.panel.run') }}</h3>
            <dl class="status-facts">
              <div v-for="fact in runFacts" :key="fact.key" class="status-fact">
                <dt>{{ fact.label }}</dt>
                <dd :class="{ 'is-num': fact.numeric }">
                  <LiveDuration v-if="fact.key === 'elapsed'" :started-at="runTracker.state.startedAt" :ended-at="runTracker.state.endedAt || 0" />
                  <template v-else>{{ fact.value }}</template>
                </dd>
              </div>
            </dl>
          </section>

          <section v-if="selectedFile" class="panel-block">
            <div class="panel-heading-row">
              <h3 class="panel-heading">{{ $t('launch.panel.team') }}</h3>
              <button v-if="teamSize" type="button" class="panel-link" @click="selectView('office')">{{ $t('launch.panel.team_all', { n: teamSize }) }}</button>
            </div>
            <ul v-if="teamMembers.length" class="team-list">
              <li v-for="member in teamMembers" :key="member.id" class="team-row">
                <span class="team-avatar" aria-hidden="true">
                  <img v-if="member.sprite" :src="member.sprite" alt="" />
                </span>
                <span class="team-name" :title="member.id">{{ member.id }}</span>
                <StatusPill compact :tone="member.status" :label="$t(`launch.panel.step_${member.status}`)" />
              </li>
            </ul>
            <p v-else class="panel-note">{{ $t('launch.panel.team_empty') }}</p>
          </section>

          <section v-if="selectedFile" class="panel-block">
            <h3 class="panel-heading">{{ $t('launch.panel.activity') }}</h3>
            <ol v-if="recentEvents.length" class="activity-feed">
              <li v-for="event in recentEvents" :key="event.id" class="activity-feed-item">
                <span class="activity-feed-text">{{ event.text }}</span>
                <time class="activity-feed-time">{{ formatTime(event.at) }}</time>
              </li>
            </ol>
            <p v-else class="panel-note">{{ $t('launch.panel.activity_empty') }}</p>
          </section>

          <!-- Starting, continuing and stopping a run all live in the composer; only the log export stays here -->
          <div class="button-section">
            <button
              type="button"
              class="btn secondary sm"
              :disabled="!isRunFinished"
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
      role="dialog"
      aria-modal="true"
      :aria-label="selectedArtifactImage.name"
      @click.self="closeImageModal"
    >
      <div class="image-modal-content">
        <button ref="imageModalCloseRef" type="button" class="image-modal-close" aria-label="Đóng ảnh" @click="closeImageModal">
          <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>
        </button>
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
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick, toRaw } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { checkWorkflowConnections, fetchWorkflowsWithDesc, fetchLogsZip, fetchWorkflowYAML, postFile, getAttachment, fetchVueGraph, fetchSessions, saveSessionReview, renameSession, deleteSession, updateSessionWorkflow, cloneProjectIntoSession, openLocalProject } from '@/api/client.js'
import { collectDroppedItems } from '@/utils/projectFiles.js'
import LocalFolderPicker from '@/components/launch/LocalFolderPicker.vue'
import KanbanView from '@/components/launch/KanbanView.vue'
import DashboardView from '@/components/launch/DashboardView.vue'
import ReviewView from '@/components/launch/ReviewView.vue'
import { createRunTracker, usageTotals, formatCost, stepStatus } from '@/utils/runTracker.js'
import StatusPill from '@/components/launch/StatusPill.vue'
import { localizeErrorText } from '@/utils/errorTranslate.js'
import { confirmDialog } from '@/utils/confirm'
import { toast } from '@/utils/toast.js'
import { configStore } from '@/stores/configStore.js'
import { spriteFetcher } from '@/utils/spriteFetcher.js'
import { onWorkflowChanged, workflowKey } from '@/utils/workflowSync.js'
import OfficeView from '@/components/office/OfficeView.vue'
import SessionSidebar from '@/components/launch/SessionSidebar.vue'
import BaseSelect from '@/components/ui/BaseSelect.vue'
import BaseSkeleton from '@/components/ui/BaseSkeleton.vue'
import { computeTeamLinks, layoutOrgTree } from '@/utils/teamLinks.js'
import yaml from 'js-yaml'
import MarkdownIt from 'markdown-it'
import SettingsModal from '@/components/common/SettingsModal.vue'
const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true
})
// Code blocks get their own copy button (like Claude / ChatGPT) and wide tables scroll
// sideways instead of squeezing a column per letter. The button label is localized at
// render time, so the markdown cache is keyed by locale too.
const CODE_COPY_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>'
let codeCopyLabel = 'Copy'
const withCopyButton = (rule) => (tokens, idx, options, env, self) => {
  const html = rule(tokens, idx, options, env, self)
  const lang = (tokens[idx].info || '').trim().split(/\s+/)[0]
  const label = md.utils.escapeHtml(codeCopyLabel)
  const langTag = lang ? `<span class="md-code-lang">${md.utils.escapeHtml(lang)}</span>` : ''
  return `<div class="md-code">${langTag}<button type="button" class="md-code-copy" data-code-copy title="${label}" aria-label="${label}">${CODE_COPY_ICON}<span>${label}</span></button>${html}</div>`
}
md.renderer.rules.fence = withCopyButton(md.renderer.rules.fence)
md.renderer.rules.code_block = withCopyButton(md.renderer.rules.code_block)
md.renderer.rules.table_open = () => '<div class="md-table"><table>\n'
md.renderer.rules.table_close = () => '</table></div>\n'
// Links in a message open in a new tab and never get a handle back on this page
const defaultLinkOpen = md.renderer.rules.link_open || ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, idx, options, env, self)
}

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
  codeCopyLabel = t('launch.copy_code')
  const cacheKey = `${i18nLocale.value}\u0000${source}`
  const cached = markdownCache.get(cacheKey)
  if (cached !== undefined) return cached
  const html = source.length > MARKDOWN_MAX_CHARS ? preformatted(source) : md.render(source)
  if (markdownCache.size >= MARKDOWN_CACHE_LIMIT) {
    markdownCache.delete(markdownCache.keys().next().value)
  }
  markdownCache.set(cacheKey, html)
  return html
}

// One delegated listener for every code block's copy button in the chat
const copiedTimers = new WeakMap()
const handleChatClick = async (event) => {
  const button = event.target.closest?.('[data-code-copy]')
  if (!button) return
  event.stopPropagation()
  const code = button.parentElement?.querySelector('pre')?.innerText ?? ''
  try {
    await navigator.clipboard.writeText(code.replace(/\n$/, ''))
  } catch (error) {
    console.warn('Copy failed:', error)
    toast.error(t('launch.copy_failed'))
    return
  }
  const label = button.querySelector('span')
  if (label) label.textContent = t('launch.copied')
  button.classList.add('copied')
  clearTimeout(copiedTimers.get(button))
  copiedTimers.set(button, setTimeout(() => {
    button.classList.remove('copied')
    if (label) label.textContent = t('launch.copy_code')
  }, 1600))
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
import { VueFlow, useVueFlow, MarkerType, getRectOfNodes } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import '@vue-flow/core/dist/style.css'
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
  const text = localizeErrorText(formatErrorDetail(detail))
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
// Run set-up lines that mean nothing to the user (memory stores being loaded)
const SETUP_LOG_RE = /^(Global memory '.*' built successfully|Memory manager built for node )/
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
const {
  fromObject, fitView: fitFlow, onPaneReady, onNodesInitialized, setNodes, setEdges, edges, getNodes, dimensions, setViewport,
  viewport, zoomIn, zoomOut, nodesDraggable, nodesConnectable, elementsSelectable
} = useVueFlow()
// Lock: the same switch the stock controls had (drag, connect and select off together)
const isGraphInteractive = computed(() => Boolean(nodesDraggable.value || nodesConnectable.value || elementsSelectable.value))
const toggleGraphInteractive = () => {
  const next = !isGraphInteractive.value
  nodesDraggable.value = next
  nodesConnectable.value = next
  elementsSelectable.value = next
}
// Fit the workflow on screen, but never so small the node names stop being readable
// (names are 15px: 0.75 keeps them >= 11px). A graph too big for that is shown from its
// left edge (the start and the lead), centred vertically; pan or zoom out for the rest.
const GRAPH_MIN_ZOOM = 0.75
const GRAPH_SPRITE_HEADROOM = 56
const fitView = async (options = {}) => {
  if (!fitFlow) return
  await fitFlow({ ...options, padding: 0.12, maxZoom: 1.1 })
  const nodes = getNodes.value || []
  const { width, height } = dimensions.value || {}
  if (!nodes.length || !width || !height) return
  // Sprites stand above their node box, which getRectOfNodes ignores: reserve that headroom
  // so the top row is not clipped by the canvas edge.
  const base = getRectOfNodes(nodes)
  const rect = { ...base, y: base.y - GRAPH_SPRITE_HEADROOM, height: base.height + GRAPH_SPRITE_HEADROOM }
  const fitZoom = Math.min(width / (rect.width * 1.24), height / (rect.height * 1.24))
  if (!(fitZoom < GRAPH_MIN_ZOOM)) {
    const vp = viewport.value
    const clipped = vp.y + rect.y * vp.zoom
    if (clipped < 8) setViewport({ ...vp, y: vp.y + (8 - clipped) })
    return
  }
  const zoom = GRAPH_MIN_ZOOM
  setViewport({ x: 32 - rect.x * zoom, y: (height - rect.height * zoom) / 2 - rect.y * zoom, zoom })
}

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

// Status state
const status = ref('Waiting for workflow selection...')
const loading = ref(false)

// Session ID for downloads
let sessionIdToDownload = null

// All notifications and dialogues
const chatMessages = ref([])
// Stable v-for keys: a finished turn can move below the delegation lines, and index keys
// combined with v-memo would then show a stale row
const messageKeys = new WeakMap()
let messageKeySeq = 0
const messageKey = (message) => {
  const raw = toRaw(message)
  let key = messageKeys.get(raw)
  if (!key) {
    key = ++messageKeySeq
    messageKeys.set(raw, key)
  }
  return key
}
const chatMessagesRef = ref(null) // Extra ref

// Map in-progress model/tool call messages by node ID
// Map<nodeId, { message, entryMap, baseKeyToKey, counters }>
const nodesLoadingMessagesMap = new Map()

// Create or fetch the loading bubble for a node
const addTotalLoadingMessage = (nodeId, at = Date.now()) => {
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
    startedAt: at,
    timestamp: at,
    loadingEntries: [],
    activityOpen: false,
    endedAt: null,
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
// `at` is the backend event time (ms), so a replayed session shows the real durations
const addLoadingEntry = (nodeId, baseKey, label, { isModel = false, at = Date.now(), member = '', doneLabel = '', delegates = false } = {}) => {
  const nodeState = addTotalLoadingMessage(nodeId, at)
  if (!nodeState || !baseKey) return null

  const count = (nodeState.counters.get(baseKey) || 0) + 1
  nodeState.counters.set(baseKey, count)
  const key = `${baseKey}-${count}`

  const entry = {
    key,
    baseKey,
    label,
    doneLabel,
    isModel,
    member,
    delegates,
    status: 'running',
    startedAt: at,
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
const finishLoadingEntry = (nodeId, baseKey, at = Date.now()) => {
  const nodeState = nodesLoadingMessagesMap.get(nodeId)
  if (!nodeState || !baseKey) return null

  const key = nodeState.baseKeyToKey.get(baseKey)
  const entry = key ? nodeState.entryMap.get(key) : null
  if (!entry) return null

  const wasRunning = entry.status === 'running'
  entry.status = 'done'
  entry.endedAt = Math.max(at, entry.startedAt)
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

// Close a node's activity row (collapsed "Worked for 28s") and, when the node has something to say,
// put that text in the same message so one assistant turn = activity summary + answer.
// Returns true when the content was merged into the activity message.
const settleNodeTurn = (nodeId, content = null, at = Date.now()) => {
  const nodeState = nodeId ? nodesLoadingMessagesMap.get(nodeId) : null
  if (!nodeState) return false
  const endedAt = Math.max(at, nodeState.message.startedAt)
  finalizeAllLoadingEntries(nodeState, endedAt)
  const message = nodeState.message
  // Members' steps shown in this bubble end with it too
  for (const entry of message.loadingEntries || []) {
    if (entry.status !== 'running') continue
    entry.status = 'done'
    entry.endedAt = Math.max(endedAt, entry.startedAt)
  }
  message.isLoading = false
  message.endedAt = endedAt
  message.duration = formatDuration(message.startedAt, endedAt)
  nodesLoadingMessagesMap.delete(nodeId)
  const built = buildDialogueContent(content)
  const merged = Boolean(built && !message.text)
  if (merged) {
    message.text = built.text
    message.htmlContent = built.htmlContent
    message.timestamp = endedAt
    // The bubble stays where it is: the team's steps went into its activity block, so the
    // answer lands right below that block instead of the bubble jumping to the bottom
  }
  message.rev += 1
  // An agent's answer landed in its bubble while you read further up
  if (merged && !isNearBottom) hasUnseenMessages.value = true
  scheduleScrollToBottom()
  return merged
}

// The run is over (completed, stopped, failed, or cut off by a server restart): no bubble may
// keep spinning. `interrupted` marks the turns that never got to finish.
const settleAllNodeTurns = ({ at = Date.now(), interrupted = false } = {}) => {
  for (const [nodeId, nodeState] of [...nodesLoadingMessagesMap.entries()]) {
    const message = nodeState.message
    settleNodeTurn(nodeId, null, at)
    if (interrupted) {
      message.interrupted = true
      message.rev += 1
    }
  }
}

// Who handed each team member its task in this session (member -> lead); unlike
// delegatedNodes it is kept after the member is done, for its late files and report
const memberLeads = new Map()
// When each delegated member picked up its task (event time, ms)
const memberStarts = new Map()

// The agent bubble of the current turn that speaks for `nodeId`: its own bubble, else the one
// of the lead it reports to (up the chain of sub-leads). Running bubbles first, then the
// finished ones since your last message. null when the turn has none.
const findTurnBubble = (nodeId) => {
  if (!nodeId) return null
  const chain = [nodeId]
  for (let lead = memberLeads.get(nodeId); lead && !chain.includes(lead); lead = memberLeads.get(lead)) {
    chain.push(lead)
  }
  for (const name of chain) {
    const state = nodesLoadingMessagesMap.get(name)
    if (state) return state.message
  }
  const list = chatMessages.value
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const message = list[i]
    if (message.type !== 'dialogue') continue
    if (message.isRight) break
    if (!message.isArtifact && chain.includes(message.name)) return message
  }
  return null
}

// Something since your last message came from an agent (its bubble speaks for the turn)
const turnHasAgentBubble = () => {
  const list = chatMessages.value
  for (let i = list.length - 1; i >= 0; i -= 1) {
    if (list[i].type !== 'dialogue') continue
    return !list[i].isRight
  }
  return false
}

// A finished team step (a member's report, a file it made) in a lead's activity block
let teamStepSeq = 0
const addTeamStep = (message, { label, startedAt = 0, endedAt = 0, detail = null }) => {
  if (!message?.loadingEntries) return false
  const built = detail ? buildDialogueContent(detail) : null
  message.loadingEntries.push({
    key: `team-${++teamStepSeq}`,
    baseKey: 'team',
    label,
    doneLabel: label,
    isModel: false,
    member: '',
    status: 'done',
    startedAt,
    endedAt: endedAt ? Math.max(endedAt, startedAt) : null,
    detailText: built?.text || '',
    detailHtml: built?.htmlContent || '',
    detailOpen: false
  })
  message.rev += 1
  scheduleScrollToBottom()
  return true
}

// Running steps say what is going on ("Đang suy nghĩ…"), finished ones what was done
const stepLabel = (entry) => (entry.status === 'running' ? entry.label : entry.doneLabel || entry.label)

const toggleStepDetail = (message, entry) => {
  entry.detailOpen = !entry.detailOpen
  message.rev += 1
}

// A file the turn produced: one card on the bubble that speaks for the turn, however many
// times it is reported (the member makes it, the lead hands the same file over again)
const attachTurnFile = (message, { nodeId, fileName, mimeType, attachmentId }) => {
  if (!message.files) message.files = []
  const isImage = !!mimeType && mimeType.includes('image')
  let file = message.files.find((item) => item.fileName === fileName)
  if (file) {
    // Same name again: the latest copy is the one to download
    if (attachmentId && file.attachmentId !== attachmentId) {
      file.attachmentId = attachmentId
      file.mimeType = mimeType
      file.isImage = isImage
      file.dataUri = null
      file.error = null
    } else {
      return
    }
  } else {
    message.files.push({ fileName, mimeType, attachmentId, isImage, dataUri: null, loading: false, error: null })
    file = message.files[message.files.length - 1]
    // A member's file also shows up as a step of the lead's work
    if (nodeId && nodeId !== message.name && message.loadingEntries) {
      addTeamStep(message, { label: t('launch.activity.member_file', { member: nodeId, file: fileName }) })
    }
  }
  message.rev += 1
  scheduleScrollToBottom()
  if (isImage && sessionId && attachmentId) {
    file.loading = true
    getAttachment(sessionId, attachmentId)
      .then((dataUri) => { file.dataUri = dataUri })
      .catch((error) => {
        console.error('Failed to load image artifact:', error)
        file.error = t('launch.errors.image_load_failed')
      })
      .finally(() => {
        file.loading = false
        message.rev += 1
      })
  }
}

const downloadTurnFile = async (message, file) => {
  const pending = downloadArtifact(file)
  message.rev += 1
  await pending
  message.rev += 1
}

// Human-friendly activity labels (no raw model ids in the chat). Covers the workflow's own
// tools and those a CLI agent reports (claude:Bash, codex:shell, mcp__playwright__browser_click …)
const TOOL_ACTIVITY_KEYS = {
  ask_user: 'ask_user',
  delegate_task: 'delegate',
  delegate_parallel: 'delegate_parallel',
  read_file_segment: 'read',
  read_file: 'read',
  read: 'read',
  notebookread: 'read',
  list_directory: 'list',
  describe_available_files: 'list',
  ls: 'list',
  search_in_files: 'search',
  glob: 'search',
  grep: 'search',
  write_file: 'write',
  save_file: 'write',
  edit_file: 'write',
  apply_patch: 'write',
  apply_text_edits: 'write',
  create_folder: 'write',
  move_path: 'write',
  rename_path: 'write',
  delete_path: 'write',
  write: 'write',
  edit: 'write',
  multiedit: 'write',
  notebookedit: 'write',
  run_command: 'run',
  run_shell_command: 'run',
  execute_code: 'run',
  bash: 'run',
  shell: 'run',
  powershell: 'run',
  web_search: 'web',
  websearch: 'web',
  fetch_url: 'web',
  webfetch: 'web'
}

const bareToolName = (toolName) => String(toolName || '').split('__').pop().replace(/^(claude|codex):/i, '')

const toolActivityKey = (toolName) => {
  const base = bareToolName(toolName).toLowerCase()
  if (base.startsWith('browser_')) return 'browser'
  return TOOL_ACTIVITY_KEYS[base] || ''
}

const isDelegateTool = (toolName) => ['delegate', 'delegate_parallel'].includes(toolActivityKey(toolName))

// `done`: the past-tense label of a finished step ("Đã giao việc cho …")
const toolActivityLabel = (toolName, rawArgs, done = false) => {
  let args = rawArgs
  if (typeof args === 'string') {
    try { args = JSON.parse(args) } catch { args = null }
  }
  const group = done ? 'launch.activity_done' : 'launch.activity'
  const key = toolActivityKey(toolName)
  if (key === 'delegate' && args?.member) return t(`${group}.delegate_to`, { member: args.member })
  if (key) return t(`${group}.${key}`)
  const pretty = (bareToolName(toolName) || t('launch.unknown_name')).replace(/[_-]+/g, ' ')
  return t(`${group}.tool`, { name: pretty })
}

const humanDuration = (ms) => {
  const total = Math.max(1, Math.round((ms || 0) / 1000))
  const m = Math.floor(total / 60)
  const s = total % 60
  return m ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`
}

// What each delegated member is doing right now: { kind: 'model' | 'tool' | null, name, args, at }
// (`at`: when that step began, or when the last one ended)
const memberNow = new Map()
const setMemberNow = (member, kind, at, name = '', args = null) => {
  memberNow.set(member, { kind, name, args, at })
}

// An agent run through a CLI in native mode works on its own (reads, edits, runs commands)
// and reports those steps only when it is done: while it runs it is "working", not "thinking"
const isNativeNode = (id) => {
  const node = (workflowYaml.value?.graph?.nodes || []).find((item) => item?.id === id)
  return Boolean(node?.config?.native_mode?.enabled)
}

const memberDoing = (member) => {
  const now = memberNow.get(member)
  if (now?.kind === 'tool') return toolActivityLabel(now.name, now.args)
  if (now?.kind === 'model') return t(isNativeNode(member) ? 'launch.activity.working' : 'launch.activity.thinking')
  return ''
}

// The member actually working under `lead` (down the chain of sub-leads, the most recently
// active one when several work at once) and what it is doing, timed from that step's start
const activeWorkerStep = (lead) => {
  const chain = []
  let current = lead
  for (;;) {
    let next = ''
    let nextAt = -1
    for (const [member, by] of delegatedNodes) {
      if (by !== current || member === lead || chain.includes(member)) continue
      const at = memberNow.get(member)?.at ?? memberStarts.get(member) ?? 0
      if (at > nextAt) {
        next = member
        nextAt = at
      }
    }
    if (!next) break
    chain.push(next)
    current = next
  }
  if (!chain.length) return null
  const worker = chain[chain.length - 1]
  const doing = memberDoing(worker)
  return {
    label: t(doing ? 'launch.activity.member_working_doing' : 'launch.activity.member_working', {
      chain: chain.join(' → '),
      doing
    }),
    at: memberNow.get(worker)?.at || memberStarts.get(worker) || 0
  }
}

// The live line of a running bubble: the step going on right now, timed from its start
const liveStep = (message) => {
  const entries = message.loadingEntries || []
  let running = null
  for (let i = entries.length - 1; i >= 0; i--) {
    if (entries[i].status === 'running' && !entries[i].sub) {
      running = entries[i]
      break
    }
  }
  if (!running || running.delegates) {
    const worker = activeWorkerStep(message.name)
    if (worker) return { label: worker.label, at: worker.at || running?.startedAt || message.startedAt }
  }
  if (running) return { label: running.label, at: running.startedAt }
  const last = entries[entries.length - 1]
  return { label: t('launch.activity.thinking'), at: last?.endedAt || message.startedAt }
}

// While running, the last few finished steps stay in view above the live line
const LIVE_STEP_ROWS = 3
const finishedSteps = (message) => (message.loadingEntries || []).filter((entry) => entry.status !== 'running')
const shownSteps = (message) => {
  if (!message.isLoading) return message.loadingEntries || []
  const done = finishedSteps(message)
  return message.activityOpen ? done : done.slice(-LIVE_STEP_ROWS)
}
const hiddenStepCount = (message) => Math.max(0, finishedSteps(message).length - LIVE_STEP_ROWS)
// A step that took no measurable time (e.g. a CLI agent's steps, reported all at once) shows none
const showStepTime = (entry) =>
  Boolean(entry.startedAt) && (entry.status === 'running' || !entry.endedAt || entry.endedAt - entry.startedAt >= 1000)

// A member's own step (a command it ran, a file it read …) in its lead's activity block.
// Repeats of the same step in a row share one row ("QA Tester · Đã chạy lệnh ×3").
const memberStepKeys = new Map()
const addMemberStep = (member, toolName, args, at) => {
  const message = findTurnBubble(member)
  if (!message?.loadingEntries || message.name === member) return
  const label = t('launch.activity.member_step', { member, step: toolActivityLabel(toolName, args) })
  const doneLabel = t('launch.activity.member_step', { member, step: toolActivityLabel(toolName, args, true) })
  const entries = message.loadingEntries
  const last = entries[entries.length - 1]
  let entry = last
  if (last?.sub === member && last.doneLabel === doneLabel && last.status !== 'running') {
    last.count = (last.count || 1) + 1
    last.status = 'running'
    last.endedAt = null
  } else {
    entry = {
      key: `member-${++teamStepSeq}`,
      baseKey: 'member',
      label,
      doneLabel,
      isModel: false,
      member: '',
      sub: member,
      count: 1,
      status: 'running',
      startedAt: at,
      endedAt: null
    }
    entries.push(entry)
  }
  memberStepKeys.set(`${member}|${toolName}`, { entry, message })
  message.rev += 1
  scheduleScrollToBottom()
}

const endMemberStep = (key, found, at) => {
  memberStepKeys.delete(key)
  found.entry.status = 'done'
  found.entry.endedAt = Math.max(at, found.entry.startedAt)
  found.message.rev += 1
}

const finishMemberStep = (member, toolName, at) => {
  const key = `${member}|${toolName}`
  const found = memberStepKeys.get(key)
  if (found) endMemberStep(key, found, at)
}

const finishMemberSteps = (member, at) => {
  for (const [key, found] of [...memberStepKeys.entries()]) {
    if (found.entry.sub === member) endMemberStep(key, found, at)
  }
}

// The finished turn's collapsed line: "Đã xử lý trong 12s · 5 bước"
const activityHeadline = (message) => {
  // The count is the number of rows the block lists; thinking alone is just "thought for 5s"
  const entries = message.loadingEntries || []
  const steps = entries.some((e) => !e.isModel) ? entries.length : 0
  const time = humanDuration((message.endedAt || Date.now()) - message.startedAt)
  if (message.interrupted) return t('launch.activity.interrupted', { time })
  return steps
    ? t('launch.activity.done_steps', { time, steps })
    : t('launch.activity.done', { time })
}

const toggleActivity = (message) => {
  message.activityOpen = !message.activityOpen
  message.rev += 1
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
const showAttachMenu = ref(false)
const attachMenuRef = ref(null)
// Thumbnails (object URLs) for attached images, keyed by attachmentId
const attachmentPreviews = ref({})
const isUploadingAttachment = ref(false)
const selectedArtifactImage = ref(null)
let dragDepth = 0

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
// Outside the chat the control panel is a drawer over the view: after picking a view, get it
// out of the way (the "Bảng điều khiển" button in the header brings it back).
watch(viewMode, (mode) => {
  if (mode !== 'chat') isRightPanelOpen.value = false
})
// Most used first: talk to the lead, then watch the team, then the work around it
const viewOptions = [
  { mode: 'chat', label: 'launch.chat' },
  { mode: 'office', label: 'launch.office.view' },
  { mode: 'board', label: 'launch.board.view' },
  { mode: 'review', label: 'launch.review.view' },
  { mode: 'dashboard', label: 'launch.dashboard.view' },
  { mode: 'graph', label: 'launch.graph' }
]
const selectView = (mode) => {
  isControlSheetOpen.value = false
  isSessionsDrawerOpen.value = false
  // Narrow screens: the chat would cover the view it was just switched to; it stays one tap away
  if (isNarrow.value && mode !== 'chat' && viewMode.value === 'chat') isChatPanelOpen.value = false
  if (mode === 'chat') isChatPanelOpen.value = true
  if (mode === 'graph') switchToGraph()
  else viewMode.value = mode
}
// Keep the active tab in view when the strip scrolls (narrow screens)
watch(viewMode, (mode) => {
  nextTick(() => document.getElementById(`view-tab-${mode}`)?.scrollIntoView?.({ inline: 'nearest', block: 'nearest' }))
})
// Tab list keyboard support: arrows / Home / End move the focus, Enter or Space opens the view
const onViewTabKey = (event) => {
  const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End']
  if (!keys.includes(event.key)) return
  const modes = viewOptions.map((option) => option.mode)
  const current = modes.indexOf(document.activeElement?.id?.replace('view-tab-', ''))
  let next = current < 0 ? modes.indexOf(viewMode.value) : current
  if (event.key === 'ArrowRight') next = (next + 1) % modes.length
  else if (event.key === 'ArrowLeft') next = (next - 1 + modes.length) % modes.length
  else if (event.key === 'Home') next = 0
  else next = modes.length - 1
  event.preventDefault()
  document.getElementById(`view-tab-${modes[next]}`)?.focus()
}

// Per-browser layout memory (localStorage may be unavailable: private mode, blocked storage)
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

// ---------------------------------------------------------------- layout: wide vs narrow
// Below 900px the status panel becomes a bottom sheet and the session list a drawer
const NARROW_QUERY = '(max-width: 899.98px)'
const narrowMql = typeof window !== 'undefined' && typeof window.matchMedia === 'function' ? window.matchMedia(NARROW_QUERY) : null
const isNarrow = ref(Boolean(narrowMql?.matches))
const isControlSheetOpen = ref(false)
const isSessionsDrawerOpen = ref(false)
const onNarrowChange = (event) => {
  isNarrow.value = event.matches
  isControlSheetOpen.value = false
  isSessionsDrawerOpen.value = false
}
narrowMql?.addEventListener?.('change', onNarrowChange)
onUnmounted(() => narrowMql?.removeEventListener?.('change', onNarrowChange))

// Chat view (wide): the control panel is a column the person can fold away (remembered)
const STATUS_COLUMN_KEY = 'agentdev.launch.statusColumnOpen'
const isStatusColumnOpen = ref(readStorage(STATUS_COLUMN_KEY) !== '0')
watch(isStatusColumnOpen, (open) => writeStorage(STATUS_COLUMN_KEY, open ? '1' : '0'))
const isControlsVisible = computed(() => {
  if (isNarrow.value) return isControlSheetOpen.value
  return viewMode.value === 'chat' ? isStatusColumnOpen.value : isRightPanelOpen.value
})
const setControlsOpen = (open) => {
  if (isNarrow.value) {
    if (open) isSessionsDrawerOpen.value = false
    isControlSheetOpen.value = open
  } else if (viewMode.value === 'chat') {
    isStatusColumnOpen.value = open
  } else {
    isRightPanelOpen.value = open
  }
}
const toggleControls = () => setControlsOpen(!isControlsVisible.value)
const closeControls = () => setControlsOpen(false)
// Show the panel (workflow picker) wherever it lives in the current layout
const revealControls = () => setControlsOpen(true)
const toggleSessionsPanel = () => {
  if (isNarrow.value) {
    isControlSheetOpen.value = false
    isSessionsDrawerOpen.value = !isSessionsDrawerOpen.value
  } else {
    isSessionSidebarOpen.value = !isSessionSidebarOpen.value
  }
}
const onSidebarSelect = (...args) => {
  isSessionsDrawerOpen.value = false
  return openSession(...args)
}
const onSidebarNew = (...args) => {
  isSessionsDrawerOpen.value = false
  return startNewSession(...args)
}
// Esc closes whichever sheet is open
const onSheetEscape = (event) => {
  if (event.key !== 'Escape' || event.defaultPrevented || showSettingsModal.value) return
  if (isControlSheetOpen.value) isControlSheetOpen.value = false
  else if (isSessionsDrawerOpen.value) isSessionsDrawerOpen.value = false
  else if (!isNarrow.value && viewMode.value !== 'chat' && isRightPanelOpen.value) isRightPanelOpen.value = false
}
document.addEventListener('keydown', onSheetEscape)
onUnmounted(() => document.removeEventListener('keydown', onSheetEscape))

// ---------------------------------------------------------------- status panel
const workflowPickerRef = ref(null)
const pickerNudge = ref(false)
let pickerNudgeTimer = null
// Bring the workflow picker into view and focus it (also from the composer's hint)
const focusWorkflowPicker = () => {
  revealControls()
  pickerNudge.value = true
  clearTimeout(pickerNudgeTimer)
  pickerNudgeTimer = setTimeout(() => { pickerNudge.value = false }, 1800)
  nextTick(() => workflowPickerRef.value?.querySelector('select')?.focus())
}
onUnmounted(() => clearTimeout(pickerNudgeTimer))

const selectedDescription = computed(() => {
  const workflow = workflowFiles.value.find((item) => item.name === selectedFile.value)
  return workflow?.description ? localizedWorkflowDescription(workflow.name, workflow.description) : ''
})
// One of running | warn | success | danger | muted, drives the chip's colour and icon
const statusTone = computed(() => {
  if (isStopping.value) return 'warn'
  if (isAwaitingPlan.value) return 'warn'
  const value = status.value
  if (value === 'Running...' || value === 'Launching...') return 'running'
  if (value === 'Waiting for input...') return 'warn'
  if (value === 'Completed') return 'success'
  if (value === 'Error' || value === 'Failed') return 'danger'
  return 'muted'
})
const activeNodeNames = computed(() => (isRunActive.value ? activeNodes.value.join(', ') : ''))
const usageSummary = computed(() => {
  const usage = usageTotals(runTracker.state.tokenUsage)
  if (!usage.tokens) return ''
  const tokens = t('launch.panel.tokens', { n: usage.tokens.toLocaleString() })
  return usage.cost === null ? tokens : `${tokens} · ${formatCost(usage.cost)}`
})

// Starter prompts of an empty chat ({workflow} is the selected workflow's name)
const EMPTY_SUGGESTION_KEYS = [
  'launch.empty_chat.suggestions.intro',
  'launch.empty_chat.suggestions.plan',
  'launch.empty_chat.suggestions.review',
  'launch.empty_chat.suggestions.tests'
]

// Why the composer cannot send yet; the old Run button's disabled reasons live here now
const composerHint = computed(() => {
  if (!selectedFile.value) return loading.value ? '' : t('launch.composer.pick_workflow')
  if (!isWorkflowRunning.value && !isRunFinished.value && !isConnectionReady.value && !isReconnecting.value) {
    return t('launch.composer.connecting')
  }
  return ''
})

// "Tệp đính kèm: a, b/" at the end of a user message -> { body, names }, cached per message text
const ATTACHMENT_LINE = /^(?:Tệp đính kèm|Attachments|附件)\s*[:：]\s*(\S.*)$/u
const attachmentCache = new WeakMap()
const userAttachments = (message) => {
  if (!message?.isRight || typeof message.text !== 'string') return null
  const cached = attachmentCache.get(message)
  if (cached && cached.text === message.text) return cached.value
  let value = null
  try {
    const cut = message.text.lastIndexOf('\n\n')
    const tail = (cut >= 0 ? message.text.slice(cut + 2) : message.text).trim()
    const match = tail.includes('\n') ? null : tail.match(ATTACHMENT_LINE)
    if (match) {
      const names = match[1].split(',').map((name) => name.trim()).filter(Boolean)
      if (names.length) value = { body: cut >= 0 ? message.text.slice(0, cut).trim() : '', names }
    }
  } catch {
    value = null
  }
  attachmentCache.set(message, { text: message.text, value })
  return value
}
// ---------------------------------------------------------------- chat column (outside the chat view)
// Resizable by drag or arrow keys (double-click resets), remembered per browser.
const CHAT_MIN_W = 320
const CHAT_MAX_W = 560
const CHAT_DEFAULT_W = 380
const CHAT_RAIL_W = 48
const CHAT_WIDTH_KEY = 'agentdev.launch.chatWidth'
const clampChatWidth = (value) => Math.round(Math.min(CHAT_MAX_W, Math.max(CHAT_MIN_W, Number(value) || CHAT_DEFAULT_W)))
const chatWidth = ref(clampChatWidth(readStorage(CHAT_WIDTH_KEY)))
const setChatWidth = (value) => { chatWidth.value = clampChatWidth(value) }
const leftPanelRef = ref(null)
const isResizingChat = ref(false)
let chatResizeRaf = 0
let chatResizeCleanup = null
const startChatResize = (event) => {
  if (event.button !== 0) return
  event.preventDefault()
  const left = leftPanelRef.value?.getBoundingClientRect().left || 0
  isResizingChat.value = true
  const onMove = (moveEvent) => {
    cancelAnimationFrame(chatResizeRaf)
    chatResizeRaf = requestAnimationFrame(() => setChatWidth(moveEvent.clientX - left))
  }
  const onUp = () => chatResizeCleanup?.()
  chatResizeCleanup = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    window.removeEventListener('pointercancel', onUp)
    cancelAnimationFrame(chatResizeRaf)
    isResizingChat.value = false
    writeStorage(CHAT_WIDTH_KEY, String(chatWidth.value))
    chatResizeCleanup = null
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  window.addEventListener('pointercancel', onUp)
}
const onChatResizeKey = (event) => {
  const step = event.shiftKey ? 64 : 16
  const next = {
    ArrowLeft: chatWidth.value - step,
    ArrowRight: chatWidth.value + step,
    Home: CHAT_MIN_W,
    End: CHAT_MAX_W
  }[event.key]
  if (next === undefined) return
  event.preventDefault()
  setChatWidth(next)
  writeStorage(CHAT_WIDTH_KEY, String(chatWidth.value))
}
onUnmounted(() => chatResizeCleanup?.())
// The chat column never takes more than half the work area
const chatColumnCss = computed(() => `min(${chatWidth.value}px, 50%)`)
const chatWidthStyle = computed(() => ({ '--chat-w': chatColumnCss.value }))
// The width the chat covers on the left of a view: its column, or the rail when folded
const chatCoverCss = computed(() => {
  if (viewMode.value === 'chat') return '0px'
  return isChatPanelOpen.value ? chatColumnCss.value : `${CHAT_RAIL_W}px`
})
// Views pad their content by --inset-left + 34px (room for an old edge toggle): subtract it
// so content starts one gutter (16px) right of the chat column or rail
const insetStyle = computed(() => ({
  '--inset-left': `calc(${chatCoverCss.value} - 18px)`,
  '--graph-inset': chatCoverCss.value
}))
// the office map cancels the page zoom (see OfficeView), so convert the chat width into its units
const officeInsetStyle = computed(() => ({ '--office-inset-left': `calc(${chatCoverCss.value} * var(--ui-zoom, 1))` }))

// ---------------------------------------------------------------- control panel content
// A long workflow description folds to three lines
const isDescriptionOpen = ref(false)
const isDescriptionLong = ref(false)
const descriptionRef = ref(null)
// The toggle shows only when three lines really cut the text (measured, so the panel's
// width - column, drawer or sheet - decides)
const measureDescription = () => {
  const el = descriptionRef.value
  if (!el || isDescriptionOpen.value) return
  isDescriptionLong.value = el.scrollHeight > el.clientHeight + 1
}
let descriptionObserver = null
watch(descriptionRef, (el, previous) => {
  if (previous) descriptionObserver?.unobserve(previous)
  if (!el || typeof ResizeObserver === 'undefined') return
  if (!descriptionObserver) descriptionObserver = new ResizeObserver(() => measureDescription())
  descriptionObserver.observe(el)
})
watch(selectedFile, () => { isDescriptionOpen.value = false })
watch([selectedDescription, isControlsVisible], () => nextTick(measureDescription))
onUnmounted(() => descriptionObserver?.disconnect())
// StatusPill tone for the run state (same chip vocabulary as the session list)
const statusPillTone = computed(() => ({
  running: 'working',
  warn: 'waiting',
  success: 'done',
  danger: 'error'
}[statusTone.value] || 'idle'))
const runFacts = computed(() => {
  const facts = []
  if (activeNodeNames.value) facts.push({ key: 'working', label: t('launch.panel.working'), value: activeNodeNames.value })
  if (runTracker.state.startedAt) facts.push({ key: 'elapsed', label: t('launch.panel.elapsed'), numeric: true })
  if (usageSummary.value) facts.push({ key: 'usage', label: t('launch.panel.usage'), value: usageSummary.value, numeric: true })
  return facts
})
// The team of this run: who has picked up work, live state first, then most recent
const TEAM_LIMIT = 6
const TEAM_ORDER = { working: 0, waiting: 1, error: 2, done: 3, cancelled: 4, todo: 5 }
const teamMembers = computed(() =>
  Object.entries(runTracker.state.nodes)
    .filter(([, node]) => node.runs.length || node.waiting)
    .map(([id, node]) => ({ id, status: stepStatus(node), lastAt: node.lastAt || 0, sprite: nodeSpriteMap.value.get(id) || '' }))
    .sort((a, b) => (TEAM_ORDER[a.status] ?? 9) - (TEAM_ORDER[b.status] ?? 9) || b.lastAt - a.lastAt)
    .slice(0, TEAM_LIMIT)
)
const teamSize = computed(() => {
  const nodes = officeGraph.value?.nodes
  if (!Array.isArray(nodes)) return 0
  const agents = nodes.filter((node) => node?.type === 'agent').length
  return agents || nodes.length
})
// Last few things that happened, newest first, in plain words
const RECENT_LIMIT = 5
const eventSentence = (event) => {
  const name = event.nodeId || ''
  switch (event.kind) {
    case 'task': return t('launch.dashboard.ev_task', { text: event.text || '' })
    case 'start': return t('launch.dashboard.ev_start', { name })
    case 'end': return t('launch.dashboard.ev_end', { name })
    case 'tool': return t('launch.dashboard.ev_tool', { name, tool: event.text || '' })
    case 'handoff': return t('launch.dashboard.ev_handoff', { name, target: event.target || '' })
    case 'waiting': return name ? t('launch.dashboard.ev_waiting', { name }) : t('launch.dashboard.ev_waiting_any')
    case 'input': return t('launch.dashboard.ev_input', { text: event.text || '' })
    case 'completed': return t('launch.dashboard.ev_completed')
    case 'cancelled': return t('launch.dashboard.ev_cancelled')
    case 'error': return t('launch.dashboard.ev_error')
    default: return event.kind
  }
}
const recentEvents = computed(() =>
  runTracker.state.events.slice(-RECENT_LIMIT).reverse().map((event) => ({ id: event.id, at: event.at, text: eventSentence(event) }))
)
// The person who answers in the chat of a team workflow: the top lead (a lead nobody
// delegates to). Empty for workflows without a team.
const leadName = computed(() => {
  const graph = workflowYaml.value?.graph
  const links = computeTeamLinks(graph?.nodes, graph?.edges)
  const members = new Set(links.map((link) => link.to))
  return links.find((link) => !members.has(link.from))?.from || ''
})
// The graph canvas resizes with the chat panel: re-fit once its slide has finished
let graphRefitTimer = null
watch([isChatPanelOpen, isResizingChat], () => {
  if (viewMode.value !== 'graph' || isResizingChat.value) return
  clearTimeout(graphRefitTimer)
  graphRefitTimer = setTimeout(() => fitView?.({ padding: 0.1 }), 280)
})
onUnmounted(() => clearTimeout(graphRefitTimer))

// ---------------------------------------------------------------- session history
// Every launched run is saved by the backend; the sidebar lists them so the user can
// switch between runs and reopen one later (after a reload or a server restart).
const SIDEBAR_OPEN_KEY = 'agentdev.sessions.sidebarOpen'
const LAST_SESSION_KEY = 'agentdev.launch.lastSession'

const sessions = ref([])
const sessionsLoaded = ref(false)
// Open or folded to a rail, remembered per view: the chat keeps its list by default, the
// work views (office, board, ...) start folded so the work gets the width. An explicit
// choice in a view sticks for that view.
const SESSIONS_BY_VIEW_KEY = 'agentdev.launch.sessionsByView'
const sessionsByView = reactive((() => {
  try {
    const saved = JSON.parse(readStorage(SESSIONS_BY_VIEW_KEY) || '{}')
    return saved && typeof saved === 'object' ? saved : {}
  } catch {
    return {}
  }
})())
const isSessionSidebarOpen = computed({
  get: () => {
    const saved = sessionsByView[viewMode.value]
    if (typeof saved === 'boolean') return saved
    return viewMode.value === 'chat' ? readStorage(SIDEBAR_OPEN_KEY) !== '0' : false
  },
  set: (open) => {
    sessionsByView[viewMode.value] = Boolean(open)
    writeStorage(SESSIONS_BY_VIEW_KEY, JSON.stringify(sessionsByView))
    if (viewMode.value === 'chat') writeStorage(SIDEBAR_OPEN_KEY, open ? '1' : '0')
  }
})
const hasLiveSession = computed(() => sessions.value.some((item) => ['running', 'cancelling', 'waiting_for_input'].includes(item.status)))
const sessionsDrawerRef = ref(null)
// Rail search: open the list and put the cursor in its search box
const openSessionSearch = async () => {
  isSessionSidebarOpen.value = true
  await nextTick()
  sessionsDrawerRef.value?.querySelector('.session-sidebar input[type="text"]')?.focus()
}

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
  } finally {
    sessionsLoaded.value = true
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
// Shows the "new messages" button: something arrived while the chat was scrolled up
const hasUnseenMessages = ref(false)
// The chat is scrolled well above the latest message
const isScrolledUp = ref(false)
// A send that never reached the server: shown above the composer with a Retry
const launchError = ref('')
// The prompt of the latest turn launched from this page, offered again after a failed run
let lastLaunchPrompt = ''
// Session being opened right now: a second click (double click) while it connects is a no-op
let pendingOpenSessionId = null
// Set when Stop was pressed here, so the server's confirmation adds no second notice
let locallyCancelled = false
// Stop was pressed and the server has not confirmed it yet: the composer stays locked
const isStopping = ref(false)
let stopFallbackTimer = null
const STOP_FALLBACK_MS = 20000
const endStopping = () => {
  clearTimeout(stopFallbackTimer)
  stopFallbackTimer = null
  isStopping.value = false
}
// An answer sent over the socket, until the server acknowledges it (input_received) or
// turns it down (non-fatal error): then it is put back in the composer
let pendingInput = null
// A follow-up that was posted, until the server starts it (workflow_started) or turns it
// down because a run is still going (run_in_progress): `undo` puts everything back
let pendingLaunch = null
let workflowStartedCount = 0
let launchRejectedCount = 0
// This session was opened in another tab: the banner offers to take it back here
const replacedSessionId = ref('')

const hasComposerContent = computed(() =>
  Boolean(taskPrompt.value.trim()) || uploadedAttachments.value.length > 0
)
const isWaitingForInput = computed(() => status.value === 'Waiting for input...')
// A run the server is working on, also while it waits for your answer (it can be stopped then too)
const isRunActive = computed(() =>
  isWorkflowRunning.value && (status.value === 'Running...' || status.value === 'Launching...' || isWaitingForInput.value)
)
// While the workflow is working the composer button turns into a Stop button; while it waits
// for your answer it becomes Send again as soon as you type one.
const isStopMode = computed(() => isStopping.value || (isRunActive.value && !(isWaitingForInput.value && hasComposerContent.value)))

// A finished run (completed, cancelled or failed) whose composer holds a new message continues
// the same session as a follow-up turn; with an empty composer the button relaunches instead.
const isRunFinished = computed(() => ['Completed', 'Cancelled', 'Error', 'Failed'].includes(status.value))

// ---------------------------------------------------------------- plan approval
// The lead ended its turn with a plan: the run is "done" for the server, but for you it
// waits on your go-ahead. Your next message (approval or changes) opens the next turn.
const isAwaitingPlan = computed(() => Boolean(runTracker.state.plan) && !isWorkflowRunning.value && status.value === 'Completed')
const statusLabel = computed(() => (isAwaitingPlan.value ? t('launch.plan.status') : getTranslatedStatus(status.value)))
// Only the latest plan of the session, while nothing newer started, can still be answered
const isPlanOpen = (message) => Boolean(message?.plan && isAwaitingPlan.value && runTracker.state.plan?.id === message.plan.id)
let planSeq = 0
const showProposedPlan = (data = {}) => {
  const node = data.node || ''
  const id = `plan-${++planSeq}`
  const plan = { id, node, summary: String(data.summary || '').trim(), plan: String(data.plan || '') }
  runTracker.proposePlan(plan)
  // The plan is that turn's answer: put the card on the lead's bubble instead of a second copy.
  // Still working: its bubble is the activity row the answer will merge into.
  let target = node ? nodesLoadingMessagesMap.get(node)?.message : null
  if (!target) {
    const list = chatMessages.value
    for (let i = list.length - 1; i >= 0; i -= 1) {
      const message = list[i]
      if (message.type !== 'dialogue') continue
      if (message.isRight) break
      if (!node || message.name === node) {
        target = message
        break
      }
    }
  }
  if (!target) target = addDialogue(node || t('launch.unknown_node'), plan.plan || plan.summary)
  if (!target) return
  target.plan = plan
  target.rev += 1
  scheduleScrollToBottom()
}
const approvePlan = () => {
  if (!isAwaitingPlan.value || loading.value || isStopping.value) return
  taskPrompt.value = t('launch.plan.approve_message')
  handleButtonClick()
}
const requestPlanChanges = () => {
  const prefix = t('launch.plan.change_prefix')
  if (!taskPrompt.value.startsWith(prefix)) taskPrompt.value = prefix + taskPrompt.value
  nextTick(() => {
    const input = taskInputRef.value
    if (!input) return
    input.focus()
    input.setSelectionRange(input.value.length, input.value.length)
    autoResizeTaskInput()
  })
}

// Chip icon by kind: project folder, video, audio, archive, any other file
const attachmentIcon = (attachment) => {
  if (attachment.kind === 'project') return '📁'
  const ext = String(attachment.name || '').split('.').pop().toLowerCase()
  if (['mp4', 'mov', 'webm', 'mkv', 'avi', 'm4v'].includes(ext)) return '🎬'
  if (['mp3', 'wav', 'ogg', 'm4a', 'flac'].includes(ext)) return '🎵'
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return '🗜️'
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'].includes(ext)) return '🖼️'
  return '📄'
}

// While an agent waits on you the box is where you answer it
const composerPlaceholder = computed(() => {
  if (isWaitingForInput.value) {
    const asker = pendingQuestion.value?.name
    return asker ? t('launch.reply_placeholder', { name: asker }) : t('launch.reply_placeholder_any')
  }
  // The box is locked while the team works: say why, and what can be done meanwhile
  if (isWorkflowRunning.value) return t(leadName.value ? 'launch.chat_ui.running_draft_placeholder' : 'launch.chat_ui.running_draft_placeholder_agent')
  if (isRunFinished.value) return t('launch.followup_placeholder')
  return t('launch.enter_prompt')
})

// The question the run is waiting on (the latest one an agent asked), pinned above the composer
const pendingQuestion = computed(() => {
  if (!isWaitingForInput.value) return null
  const list = chatMessages.value
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const message = list[i]
    if (message.type === 'dialogue' && message.isRight) break
    if (message.isQuestion) {
      const text = String(message.text || '').trim()
      // Clamped to three lines; longer ones get a "show more"
      const isLong = text.length > 180 || text.split('\n').length > 3
      return { name: getDisplayName(message), text, isLong }
    }
  }
  return { name: '', text: '', isLong: false }
})
const isQuestionExpanded = ref(false)
watch(pendingQuestion, (question, previous) => {
  if (question?.text !== previous?.text) isQuestionExpanded.value = false
})

// With an empty composer after a finished run this button starts a whole new session: an easy
// click to make by mistake, so it asks first
const handlePanelRunClick = async () => {
  if (!isWorkflowRunning.value && isRunFinished.value && !hasComposerContent.value && chatMessages.value.length) {
    const confirmed = await confirmDialog({
      title: t('launch.confirm_new_run.title'),
      message: t('launch.confirm_new_run.message'),
      confirmText: t('launch.confirm_new_run.confirm')
    })
    if (!confirmed) return
  }
  handleButtonClick()
}

// Button label computed property
const buttonLabel = computed(() => {
  if (isStopping.value) return t('launch.stopping')
  if (isStopMode.value) {
    return t('launch.chat_ui.stop')
  }
  if (isWorkflowRunning.value) {
    return t('launch.send')
  }
  if (isRunFinished.value) {
    return hasComposerContent.value ? t('launch.send') : t('launch.relaunch')
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
  if (attachmentInputRef.value) {
    attachmentInputRef.value.value = ''
  }
}

// Reset the WebSocket connection and related state
const resetConnectionState = ({ closeSocket = true, keepSession = false } = {}) => {
  // Any deliberate switch (other session, new draft, leaving the page) stops a pending auto-reconnect
  if (closeSocket) cancelReconnect()
  if (closeSocket && ws) {
    try {
      ws.close()
    } catch (closeError) {
      console.warn('Failed to close WebSocket:', closeError)
    }
  }

  ws = null
  isConnectionReady.value = false

  pendingInput = null
  pendingLaunch = null
  if (!keepSession) {
    locallyCancelled = false
    endStopping()
    replacedSessionId.value = ''
    sessionId = null
    hasLaunched.value = false
    isWorkflowRunning.value = false
    activeNodes.value = []
    shouldGlow.value = false
    clearUploadedAttachments()
    chatMessages.value = []
    nodesLoadingMessagesMap.clear()
    delegatedNodes.clear()
    memberLeads.clear()
    memberStarts.clear()
    memberNow.clear()
    memberStepKeys.clear()
    refreshTeamEdges()
    nameToSpriteMap.clear()
    nodeSpriteMap.value.clear()
    officeRef.value?.reset()
    runTracker.reset()
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

const selectWorkflow = (fileName) => {
  if (!fileName) {
    return
  }
  if (fileName !== selectedFile.value) changeWorkflow(fileName)
  // A native <select> keeps what was clicked even when the change was refused: show the truth
  nextTick(() => {
    const select = workflowPickerRef.value?.querySelector('select')
    if (select) select.value = selectedFile.value || ''
  })
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
}

// Add a dialogue entry
// Turn a node output (string or structured) into { text, htmlContent }, or null when empty
const buildDialogueContent = (message) => {
  if (message === null || message === undefined) {
    return null
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
    return null
  }
  if (htmlContent === null) htmlContent = renderMarkdown(text)
  return { text, htmlContent }
}

// `at`: when it happened (the WebSocket message's `ts`), else now
const addDialogue = (name, message, at = null) => {
  const built = buildDialogueContent(message)
  if (!built) {
    return
  }
  const { text, htmlContent } = built
  const avatar = avatarFor(name)

  const isRight = name === USER_SENDER

  chatMessages.value.push({
    type: 'dialogue',
    name: name,
    text: text,
    htmlContent,
    avatar: avatar,
    isRight: isRight,
    timestamp: at ?? Date.now(),
    rev: 0
  })
  // The user's own message always brings the view back to the bottom
  scheduleScrollToBottom(isRight)
  return chatMessages.value[chatMessages.value.length - 1]
}

// Team members currently working on a task delegated by a lead agent (their output is not a
// chat message): member id -> lead id
const delegatedNodes = new Map()
// The graph shows the generated team links (no saved layout): they light up while a member
// works on a delegated task
let graphHasTeamFallback = false
const refreshTeamEdges = () => {
  if (!graphHasTeamFallback) return
  let changed = false
  const next = edges.value.map((edge) => {
    if (edge.data?.kind !== 'team') return edge
    const active = delegatedNodes.get(edge.data.member) === edge.data.lead
    if (Boolean(edge.data.active) === active) return edge
    changed = true
    return { ...edge, data: { ...edge.data, active } }
  })
  if (changed) setEdges(next)
}

// Backend log time (ISO, local) in ms; live UI events without one happen "now"
const eventTime = (at) => {
  const parsed = at ? Date.parse(at) : NaN
  return Number.isFinite(parsed) ? parsed : Date.now()
}
// The server's send time of a WebSocket message (top-level ISO `ts`) in ms, null without one
const messageTime = (msg) => {
  const parsed = typeof msg?.ts === 'string' ? Date.parse(msg.ts) : NaN
  return Number.isFinite(parsed) ? parsed : null
}

// What a delegate_task / delegate_parallel call hands over: [{ member, task }]
// (CLI providers prefix tool names, e.g. mcp__team__delegate_task)
const delegatedTasks = (toolName, rawArgs) => {
  const name = String(toolName || '').split('__').pop()
  if (name !== 'delegate_task' && name !== 'delegate_parallel') return []
  let args = rawArgs
  if (typeof args === 'string') {
    try { args = JSON.parse(args) } catch { args = null }
  }
  const items = name === 'delegate_task' ? [args] : Array.isArray(args?.tasks) ? args.tasks : []
  return items
    .filter((item) => typeof item?.member === 'string' && item.member)
    .map((item) => ({ member: item.member, task: typeof item.task === 'string' ? item.task : '' }))
}
// The single member a delegate_task call waits on ('' for anything else)
const delegateTarget = (toolName, rawArgs) =>
  String(toolName || '').split('__').pop() === 'delegate_task' ? delegatedTasks(toolName, rawArgs)[0]?.member || '' : ''

// A delegated member started, ended or changed activity: the lead's running activity line
// ("Project Manager → QA Tester · reading files") must re-render
const touchWorkingTurns = () => {
  for (const state of nodesLoadingMessagesMap.values()) state.message.rev += 1
}

// Add a notification (supports levels)
const addChatNotification = (message, { type = 'notification', at = null, retryPrompt = '' } = {}) => {
  chatMessages.value.push({
    type,
    message,
    timestamp: at ?? Date.now(),
    rev: 0,
    ...(retryPrompt ? { retryPrompt } : {})
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

const imageModalCloseRef = ref(null)
const onImageModalKeydown = (e) => {
  if (e.key === 'Escape') closeImageModal()
}
watch(selectedArtifactImage, (val) => {
  if (val) {
    window.addEventListener('keydown', onImageModalKeydown)
    nextTick(() => imageModalCloseRef.value?.focus())
  } else {
    window.removeEventListener('keydown', onImageModalKeydown)
  }
})
onUnmounted(() => window.removeEventListener('keydown', onImageModalKeydown))

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

// Like Claude/Codex chat: Enter sends, Shift+Enter is a new line. Never send while an IME
// (e.g. Vietnamese Telex/VNI) is still composing a character.
// Safari fires the Enter that commits a composition *after* compositionend (isComposing is
// already false then), so a composition that just ended still counts for a moment.
let isImeComposing = false
let imeEndedAt = 0
const handleCompositionStart = () => {
  isImeComposing = true
}
const handleCompositionEnd = () => {
  isImeComposing = false
  imeEndedAt = Date.now()
}
const handleEnterKey = (e) => {
  if (e.shiftKey || e.altKey || e.isComposing || e.keyCode === 229) return
  if (isImeComposing || Date.now() - imeEndedAt < 60) return
  e.preventDefault()
  // Check disabled state logically similar to button
  if (isStopMode.value || loading.value || (isWorkflowRunning.value && !hasComposerContent.value) || (!isWorkflowRunning.value && !isRunFinished.value && !isConnectionReady.value)) {
    return
  }
  // An empty message box never relaunches a finished run from the keyboard
  if (!isWorkflowRunning.value && !hasComposerContent.value) return
  handleButtonClick()
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

    // Nothing to say when the workflow has no opening instructions: the empty chat
    // shows its own hint instead of a placeholder notice
    if (initialInstructions) addChatNotification(initialInstructions)

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
  if (isStopping.value) return
  if (isWorkflowRunning.value) {
    // Only an answer to a pending question can be sent while a run is live (or launching)
    if (!isWaitingForInput.value) return
    if (!sendHumanInput()) return

    status.value = "Running..."
    shouldGlow.value = false
  } else if (isRunFinished.value) {
    // Follow-up turn: keep the current session (and its chat) and run the workflow again with
    // the new message; the backend prepends the previous turns as a transcript.
    if (hasComposerContent.value) {
      launchWorkflow()
      return
    }

    // Empty composer: Relaunch, i.e. restart the same workflow in a fresh session
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
  // After a click on Send the focus is back in the box, ready for the next message
  nextTick(() => {
    const input = taskInputRef.value
    if (input && !input.disabled && document.activeElement !== input) input.focus({ preventScroll: true })
  })
}

// Send human input
const sendHumanInput = () => {
  // A closed (or still opening) socket would drop the answer silently: keep it in the box
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    toast.warning(t('launch.errors.input_not_sent'))
    return false
  }

  const trimmedInput = taskPrompt.value.trim()
  const attachmentIds = uploadedAttachments.value.map((attachment) => attachment.attachmentId)
  const attachmentNames = uploadedAttachments.value.map(
    (attachment) => attachment.name || attachment.attachmentId
  )

  if (!trimmedInput && attachmentIds.length === 0) {
    return false
  }

  const message = {
    type: 'human_input',
    data: {
      input: trimmedInput,
      attachments: attachmentIds
    }
  }

  try {
    ws.send(JSON.stringify(message))
  } catch (sendError) {
    console.warn('Failed to send human input:', sendError)
    toast.warning(t('launch.errors.input_not_sent'))
    return false
  }
  const waitingIds = Object.entries(runTracker.state.nodes).filter(([, node]) => node.waiting).map(([id]) => id)
  runTracker.inputSent(trimmedInput)

  const fullMessage = []
  if (trimmedInput) {
    fullMessage.push(trimmedInput)
  }
  if (attachmentNames.length) {
    fullMessage.push(t('launch.attachments_line', { names: attachmentNames.join(', ') }))
  }

  const bubble = fullMessage.length ? addDialogue(USER_SENDER, fullMessage.join('\n\n')) : null

  // The text leaves the box now; the attachments stay until the server has the answer, and
  // both come back if it turns the answer down (see restorePendingInput)
  pendingInput = { text: trimmedInput, attachments: [...uploadedAttachments.value], bubble, statusBefore: status.value, waitingIds }
  taskPrompt.value = ''
  return true
}

// The server has the answer: the attachments it carried leave the composer
const confirmPendingInput = () => {
  if (!pendingInput) return
  const sentIds = new Set(pendingInput.attachments.map((attachment) => attachment.attachmentId))
  const current = uploadedAttachments.value
  if (sentIds.size && current.length && current.every((attachment) => sentIds.has(attachment.attachmentId))) {
    clearUploadedAttachments()
  }
  pendingInput = null
}

// The server turned the answer down: take back the bubble and the input count, and put the
// text back in the composer (unless something new was typed meanwhile)
const restorePendingInput = (code = '') => {
  if (!pendingInput) return
  const { text, bubble, statusBefore, waitingIds } = pendingInput
  pendingInput = null
  const index = bubble ? chatMessages.value.indexOf(bubble) : -1
  if (index > -1) chatMessages.value.splice(index, 1)
  runTracker.undoInput(code === 'not_waiting' ? [] : waitingIds)
  if (!taskPrompt.value.trim()) taskPrompt.value = text
  // Still waiting for an answer unless the server said it was not
  if (code !== 'not_waiting' && status.value === 'Running...' && statusBefore === 'Waiting for input...') status.value = statusBefore
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
      // Another tab took this session: remember it so the close that follows is not
      // mistaken for a dropped connection (which would reconnect and take it back).
      if (msg?.type === 'session_replaced') {
        socket.__replaced = true
        return
      }
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
      reconnectAttempts = 0
      if (autoReconnecting) {
        autoReconnecting = false
        if (msg.data?.resumed) clearReplayedState()
      }

      if (isReconnecting.value && !msg.data?.resumed) {
        // Nothing saved under that id (deleted or expired): continue as a new session
        isReconnecting.value = false
        pendingOpenSessionId = null
        currentProjectName.value = ''
        const query = { ...route.query }
        delete query.session
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
    // Ignore errors from sockets that are no longer current; onclose always follows and
    // takes care of the state (and of reconnecting)
    if (ws !== socket) return
    console.error('WebSocket error:', error)
    // Retries after a dropped connection stay quiet: the status line already says it
    if (!reconnectAttempts) toast.error(t('launch.errors.ws_connection'))
  }

  socket.onclose = (event) => {
    // Ignore close events from sockets that are no longer current (closed on purpose)
    if (ws !== socket) return

    const lostSession = sessionId
    status.value = 'Disconnected'
    pendingOpenSessionId = null
    // The same session was opened in another tab (the server keeps one socket per session,
    // see websocket_manager.connect): reconnecting here would just take it back from that
    // tab, and so on forever. Stay put and say so; the banner's "open here" takes it back,
    // only when clicked.
    if (socket.__replaced || (event?.code === 1000 && String(event.reason || '').startsWith('Replaced'))) {
      isReconnecting.value = false
      resetConnectionState({ closeSocket: true, keepSession: Boolean(lostSession) })
      replacedSessionId.value = lostSession || ''
      return
    }
    // Keep the chat on screen while the server is away (e.g. it restarted); the replay
    // on reconnect rebuilds it exactly.
    resetConnectionState({ closeSocket: false, keepSession: Boolean(lostSession) })
    if (lostSession) scheduleReconnect(lostSession)
  }
}

// The server went away (restart, network): reconnect to the same session with backoff,
// keeping what is being typed in the message box.
let reconnectTimer = null
let reconnectAttempts = 0
// Set while an automatic reconnect is in flight (see clearReplayedState)
let autoReconnecting = false
const cancelReconnect = () => {
  clearTimeout(reconnectTimer)
  reconnectTimer = null
  reconnectAttempts = 0
  autoReconnecting = false
}
const scheduleReconnect = (lostSession) => {
  clearTimeout(reconnectTimer)
  const delay = Math.min(1000 * 2 ** reconnectAttempts, 10000)
  reconnectAttempts += 1
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    // Something else opened a connection meanwhile (the user switched sessions)
    if (ws || sessionId !== lostSession) return
    const attempts = reconnectAttempts
    establishWebSocketConnection({ sessionId: lostSession })
    reconnectAttempts = attempts
    autoReconnecting = true
  }, delay)
}
// The session moved to another tab: take it back here (the newest socket wins on the
// server). Like an automatic reconnect, the chat stays until the server replays it.
const takeOverSession = () => {
  const target = replacedSessionId.value
  if (!target) return
  replacedSessionId.value = ''
  establishWebSocketConnection({ sessionId: target })
  autoReconnecting = true
}

// Set while an automatic reconnect is in flight: the chat is cleared only once the server
// answers (it then replays the whole session), so a failed retry leaves it on screen.
const clearReplayedState = () => {
  locallyCancelled = false
  endStopping()
  chatMessages.value = []
  nodesLoadingMessagesMap.clear()
  activeNodes.value = []
  delegatedNodes.clear()
  memberLeads.clear()
  memberStarts.clear()
  memberNow.clear()
  memberStepKeys.clear()
  refreshTeamEdges()
  officeRef.value?.reset()
  runTracker.reset()
}

// Open a saved session: the backend replays its messages, then session_resumed
// restores the workflow, status and active node
// The run of the session you leave keeps going on the server; its messages are
// replayed when you come back to it.
const openSession = async (item) => {
  if (!item?.session_id) return
  if (item.session_id === activeSessionId.value && isConnectionReady.value) return
  if (isReconnecting.value && pendingOpenSessionId === item.session_id) return
  pendingOpenSessionId = item.session_id
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
  pendingOpenSessionId = null
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
    nextTick(() => focusWorkflowPicker())
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
// Once the review view has looked, its own count wins: it leaves out plain Q&A runs
const reviewPendingFromView = ref(null)
// Plans waiting for your go-ahead count too: they need you just as much
const awaitingPlanCount = computed(() => sessions.value.filter((s) => s.awaiting_plan && !['cancelled', 'error'].includes(s.status)).length)
const reviewPendingCount = computed(() =>
  awaitingPlanCount.value + (reviewPendingFromView.value ?? sessions.value.filter((s) =>
    s.status === 'completed' && (s.review?.verdict || 'pending') === 'pending' && !s.awaiting_plan && s.has_work !== false
  ).length)
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
    nextTick(() => focusWorkflowPicker())
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
  removeSpriteWalkerLayer()
  // Free the blob URLs of attachment thumbnails
  Object.keys(attachmentPreviews.value).forEach(dropAttachmentPreview)

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

    // A team (lead -> members) is laid out as an org chart, like the editor does; anyone
    // outside it keeps the plain grid below the chart
    const teamLinks = computeTeamLinks(yamlNodes, yamlEdges)
    const treePositions = teamLinks.length ? layoutOrgTree(teamLinks, { originX: 20, originY: 10, gapY: 170 }) : new Map()
    const treeBottom = Math.max(-Infinity, ...[...treePositions.values()].map((pos) => pos.y))
    const gridTop = Number.isFinite(treeBottom) ? treeBottom + 170 : 10
    let gridIndex = 0
    const generatedNodes = yamlNodes.map((node) => {
      let position = treePositions.get(node.id)
      if (!position) {
        position = { x: 20 + (gridIndex % 5) * 200, y: gridTop + Math.floor(gridIndex / 5) * 150 }
        gridIndex += 1
      }
      return { id: node.id, type: 'workflow-node', label: node.id, position, data: node }
    })

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

    // Visual-only delegation links (never YAML edges); lit while the member works on a task
    const teamEdges = teamLinks.map((link) => ({
      id: `team:${link.from}->${link.to}`,
      source: link.from,
      target: link.to,
      type: 'workflow-edge',
      selectable: false,
      focusable: false,
      data: { virtual: true, kind: 'team', lead: link.from, member: link.to, active: delegatedNodes.get(link.to) === link.from },
      markerEnd: {
        type: MarkerType.Arrow,
        width: 14,
        height: 14,
        color: 'var(--text-muted-2)',
        strokeWidth: 1.2,
      }
    }))

    setNodes(generatedNodes)
    setEdges([...generatedEdges, ...teamEdges])
    graphHasTeamFallback = teamEdges.length > 0
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
    // A saved layout may carry the team links too: they light up the same way
    graphHasTeamFallback = edges.value.some((edge) => edge.data?.kind === 'team')
    refreshTeamEdges()

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
  launchError.value = ''
  // A failed follow-up leaves a finished session as it was (not a draft "waiting for launch")
  const statusBefore = ['Completed', 'Cancelled', 'Error', 'Failed'].includes(status.value) ? status.value : 'Waiting for launch...'
  // The run is live from the moment it is posted: the server may already stream its first
  // events (a question, an error, even the end) before the POST returns, and those must win
  // over what happens below. This also stops a second launch while this one is in flight.
  status.value = 'Launching...'
  isWorkflowRunning.value = true
  locallyCancelled = false
  const trackerBefore = JSON.parse(JSON.stringify(runTracker.state))
  const startedBefore = workflowStartedCount
  const rejectedBefore = launchRejectedCount
  runTracker.begin(trimmedPrompt, attachmentNames)
  // A launch that did not happen puts everything back as it was
  const undoLaunch = () => {
    takeBackBubble()
    Object.assign(runTracker.state, trackerBefore)
    isWorkflowRunning.value = false
  }

  // Show the message right away (before the server's "started" notice), like a chat does;
  // it is taken back if the launch fails
  const fullMessage = []
  if (trimmedPrompt) fullMessage.push(trimmedPrompt)
  if (attachmentNames.length) fullMessage.push(t('launch.attachments_line', { names: attachmentNames.join(', ') }))
  const userBubble = fullMessage.length ? addDialogue(USER_SENDER, fullMessage.join('\n\n')) : null
  const takeBackBubble = () => {
    const index = chatMessages.value.indexOf(userBubble)
    if (userBubble && index > -1) chatMessages.value.splice(index, 1)
  }

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
      // The server may still turn it down over the socket (run_in_progress) before it
      // starts: until workflow_started, this puts the turn and the message back
      const undoRejected = () => {
        undoLaunch()
        status.value = statusBefore
        if (!taskPrompt.value.trim()) taskPrompt.value = trimmedPrompt
      }
      if (launchRejectedCount !== rejectedBefore && workflowStartedCount === startedBefore) {
        // Already turned down while the request was in flight
        undoRejected()
        return
      }
      if (status.value === 'Launching...' && workflowStartedCount === startedBefore) {
        pendingLaunch = { undo: undoRejected }
      }

      lastLaunchPrompt = trimmedPrompt
      // Clear uploaded attachments
      clearUploadedAttachments()

      await response.json().catch(() => null)

      // Only clear what was sent (not an answer typed meanwhile to an early question)
      if (taskPrompt.value.trim() === trimmedPrompt) taskPrompt.value = ''

      // Events that arrived during the POST (question, error, end) already set the state
      if (status.value === 'Launching...') status.value = 'Running...'
      hasLaunched.value = true
      // The project runs this workflow from now on (until the user picks another)
      if (currentProjectName.value) rememberProjectWorkflow(currentProjectName.value, selectedFile.value)

      // Persist session id in URL for reconnection after refresh (no extra history entry)
      router.replace({
        query: {
          ...route.query,
          workflow: selectedFile.value,
          session: sessionId
        }
      })
    } else if (response.status === 409) {
      // The server is still running a turn of this session (e.g. started from another tab):
      // nothing was launched, so the run state stays as it was
      const error = await response.json().catch(() => ({}))
      console.warn('Launch rejected, a run is in progress:', error)
      undoLaunch()
      status.value = statusBefore
      toast.warning(t('launch.run_in_progress'))
    } else {
      const error = await response.json().catch(() => ({}))
      console.error('Failed to launch workflow:', error)
      undoLaunch()
      status.value = 'Failed'
      launchError.value = errorWithDetail('launch.errors.launch_failed', error.detail || error.error?.message || (response.status ? `HTTP ${response.status}` : ''))
      shouldGlow.value = true
      if (isConnectionReady.value) {
        status.value = statusBefore
      }
    }
  } catch (error) {
    console.error('Error calling execute API:', error)
    undoLaunch()
    status.value = 'Error'
    launchError.value = errorWithDetail('launch.errors.execute_failed', error)
    shouldGlow.value = true
    if (isConnectionReady.value) {
      status.value = statusBefore
    }
  }
}

// Starter prompt from the empty chat: into the box (not sent), cursor at the end
const pickSuggestion = (text) => {
  taskPrompt.value = text
  nextTick(() => {
    const input = taskInputRef.value
    if (!input) return
    input.focus()
    input.setSelectionRange(input.value.length, input.value.length)
    autoResizeTaskInput()
  })
}

// Retry for a send that never reached the server: the message is still in the box
const retryLaunch = () => {
  launchError.value = ''
  handleButtonClick()
}

// Retry for a run that failed: the same prompt again as a new turn of this session. A draft
// typed meanwhile is kept and put back once the retry is on its way.
const canRetryRun = (message) =>
  Boolean(message.retryPrompt) &&
  message === chatMessages.value[chatMessages.value.length - 1] &&
  !isWorkflowRunning.value &&
  isRunFinished.value
const retryRun = async (message) => {
  if (!canRetryRun(message) || loading.value || isStopping.value) return
  const draft = taskPrompt.value
  taskPrompt.value = message.retryPrompt
  await launchWorkflow()
  if (draft.trim() && !taskPrompt.value.trim()) taskPrompt.value = draft
  nextTick(() => taskInputRef.value?.focus())
}

// Another session's failed send is not this one's
watch(activeSessionId, () => {
  launchError.value = ''
  lastLaunchPrompt = ''
})

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

// Time of the latest backend log event (ms): messages without their own time follow it
let lastLogAt = 0
const processMessage = async (msg) => {
  // When the server sent it (null on older servers: the chat then stamps "now")
  const at = messageTime(msg)
  if (msg.type === 'log' && msg.data?.timestamp) lastLogAt = eventTime(msg.data.timestamp)
  // What the user typed earlier; only arrives when a saved session is replayed
  if (msg.type === 'user_message') {
    const text = msg.data?.text || ''
    const names = Array.isArray(msg.data?.attachments) ? msg.data.attachments : []
    const parts = [text.trim(), names.length ? t('launch.attachments_line', { names: names.join(', ') }) : '']
    addDialogue(USER_SENDER, parts.filter(Boolean).join('\n\n'), at)
    // The first message of a run is the task, later ones are replies to the agents; a message
    // after a finished run opens the next turn of the session (kept with the earlier ones).
    // A reply only answers a question that is pending: a request while nobody waits is a new
    // turn, even when the turn before never recorded its end (e.g. the server restarted).
    const tracker = runTracker.state
    const awaitingAnswer = Object.values(tracker.nodes).some((node) => node.waiting)
    if (tracker.task && !tracker.outcome && awaitingAnswer) runTracker.inputSent(text, at ?? undefined)
    else runTracker.begin(text, names, at ?? undefined, { closeOpen: true })
    return
  }

  // The posted request really started: it can no longer be turned down
  if (msg.type === 'workflow_started') {
    workflowStartedCount += 1
    pendingLaunch = null
  }

  // Session resumed after reconnection — sync final UI state
  if (msg.type === 'session_resumed') {
    const data = msg.data
    sessionId = data.session_id

    // Restore workflow selection without clearing chat (messages were already replayed)
    // Set selectedFile BEFORE clearing isReconnecting so the watch skips
    if (data.yaml_file) {
      selectedFile.value = data.yaml_file
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
    pendingOpenSessionId = null
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
      // Stop was pressed and the run is winding down: locked until workflow_cancelled
      'cancelling': 'Running...',
    }
    status.value = statusMap[data.status] || 'Connected'

    if (data.status === 'running' || data.status === 'waiting_for_input' || data.status === 'cancelling') {
      isWorkflowRunning.value = true
      if (data.status === 'cancelling') startStopping()
    } else {
      // The run this page was following ended while the connection was down (e.g. a server
      // restart): unlock the box instead of still saying the team is at work
      isWorkflowRunning.value = false
      endStopping()
    }
    if (!['running', 'waiting_for_input', 'cancelling'].includes(data.status) && runTracker.state.task && !runTracker.state.outcome) {
      // The replay never recorded the end of the last turn, but the server is not running it:
      // close it, so the next request starts a turn of its own
      const outcome = { completed: 'completed', error: 'error' }[data.status] || 'cancelled'
      runTracker.finish(outcome, { error: outcome === 'error' ? formatErrorDetail(data.error_message) : '', settled: true })
      activeNodes.value = []
    }
    const isLive = ['running', 'waiting_for_input', 'cancelling'].includes(data.status)
    if (!isLive || data.error_message === 'Interrupted by a server restart') {
      // The replay left turns open (the run was cut off, e.g. by a server restart): close them
      // at their last recorded activity rather than letting their timers run on
      const lastAt = (state) => Math.max(state.message.startedAt, ...state.message.loadingEntries.map((e) => e.endedAt || e.startedAt))
      for (const [nodeId, state] of [...nodesLoadingMessagesMap.entries()]) {
        const message = state.message
        settleNodeTurn(nodeId, null, lastAt(state))
        if (data.status !== 'completed') {
          message.interrupted = true
          message.rev += 1
        }
      }
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

    if (isLive && data.current_node_id && !activeNodes.value.includes(data.current_node_id)) {
      activeNodes.value.push(data.current_node_id)
    }

    isConnectionReady.value = true
    // The replay is in: open at the latest message, once now and once more after late layout
    // (fonts, tables, images) has settled
    scheduleScrollToBottom(true)
    setTimeout(() => scheduleScrollToBottom(true), 250)
    if (data.error_message === 'Interrupted by a server restart') {
      addChatNotification(t('launch.sessions.interrupted'), { type: 'warning' })
    } else if (data.status === 'running' || data.status === 'waiting_for_input') {
      // Only worth saying while the run is live; a finished or draft session just opens
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
    // A human step usually gets the previous agent's reply as its input: that reply is
    // already the last bubble, so it is not shown a second time
    const lastAgentBubble = (() => {
      const list = chatMessages.value
      for (let i = list.length - 1; i >= 0; i -= 1) {
        if (list[i].type !== 'dialogue') continue
        return list[i].isRight ? null : list[i].text ? list[i] : null
      }
      return null
    })()
    const rawInput = msg.data?.input
    const localizedInput = localizeInputHeaders(rawInput)
    const lastText = String(lastAgentBubble?.text || '').trim()
    const repeatsLast = Boolean(lastText) &&
      [rawInput, localizedInput].some((part) => typeof part === 'string' && part.trim() === lastText)
    const fullMessage = [msg.data?.task_description, repeatsLast ? null : localizedInput]
      .filter((part) => part !== null && part !== undefined && String(part).trim())
      .join('\n\n')
    // The question closes the agent's current activity row and becomes its message;
    // work after the user's answer starts a fresh row below it.
    const askingNode = msg.data?.node_id
    // Without a server time it follows the agent's last logged event (right for replays too)
    const askedAt = at || lastLogAt || Date.now()
    let question = null
    if (repeatsLast && !fullMessage) {
      // Nothing new to say: the reply on screen is the question
      settleNodeTurn(askingNode, null, askedAt)
      question = lastAgentBubble
    } else {
      if (!settleNodeTurn(askingNode, fullMessage || t('launch.input_required'), askedAt)) {
        addDialogue(askingNode || t('launch.unknown_node'), fullMessage || t('launch.input_required'), at)
      }
      question = chatMessages.value[chatMessages.value.length - 1]
    }
    // Shown as the lead's question, waiting for your answer
    if (question?.type === 'dialogue' && !question.isRight) {
      question.isQuestion = true
      question.rev += 1
    }
    // Ready to answer: the box takes the focus unless you are typing somewhere else
    nextTick(() => {
      const active = document.activeElement
      if (!active || active === document.body) taskInputRef.value?.focus()
    })
    officeRef.value?.waitingInput(msg.data?.node_id, msg.data?.task_description || msg.data?.input)
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

        // The turn's agent bubble (the lead's, for a member's file) shows it once, under its answer
        const turnBubble = findTurnBubble(event?.node_id)
        if (turnBubble) {
          attachTurnFile(turnBubble, { nodeId: event?.node_id, fileName, mimeType, attachmentId })
          continue
        }

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
          timestamp: at ?? Date.now(),
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

  // Account ran out of quota: say plainly which account took over (or that none is left)
  const accountEvent = msg.type === 'log' ? msg.data?.details?.event : null
  if (accountEvent === 'account_fallback' || accountEvent === 'account_exhausted') {
    const params = { from: msg.data.details.from || '', to: msg.data.details.to || '', model: msg.data.details.model || '' }
    const key = accountEvent === 'account_fallback' ? 'launch.account_fallback' : 'launch.account_exhausted'
    addChatNotification(t(key, params), { type: accountEvent === 'account_fallback' ? 'warning' : 'error', at })
    toast[accountEvent === 'account_fallback' ? 'warning' : 'error'](t(key, params))
  }

  // Handle warning/error messages
  else if (msg.type === 'log' && (msg.data.level === 'WARNING' || msg.data.level === 'ERROR')) {
    const notificationType = msg.data.level === 'WARNING' ? 'warning' : 'error'
    // Backend warning/error text is technical English; give it a localized lead-in
    const detail = formatErrorDetail(msg.data.message)
    const fallbackKey = notificationType === 'warning' ? 'launch.unknown_warning' : 'launch.unknown_error'
    addChatNotification(
      detail ? withErrorHint(t(`launch.log_events.backend_${notificationType}`, { detail })) : t(fallbackKey),
      { type: notificationType, at }
    )
  }

  // Handle log messages
  if (msg.type === 'log' && msg.data.level === 'INFO') {
    const eventType = msg.data.event_type
    const nodeId = msg.data.node_id

    const delegatedBy = msg.data.details?.delegated_by
    const eventAt = eventTime(msg.data.timestamp)

    // Node active
    if (eventType === 'NODE_START') {
      if (nodeId && !activeNodes.value.includes(nodeId)) {
        activeNodes.value.push(nodeId)
      }
      runTracker.nodeStart(nodeId, msg.data.timestamp, { delegatedBy: delegatedBy || '' })
      // The user's request is what an entry agent (e.g. the CTO) is working on
      if (!delegatedBy && nodeId) officeRef.value?.brief(nodeId, runTracker.state.task?.text)
      // Team member picked up a task from its lead: one compact line, no member chatter in the chat.
      if (delegatedBy && nodeId) {
        delegatedNodes.set(nodeId, delegatedBy)
        memberLeads.set(nodeId, delegatedBy)
        memberStarts.set(nodeId, eventAt)
        setMemberNow(nodeId, null, eventAt)
        refreshTeamEdges()
        touchWorkingTurns()
        officeRef.value?.handoff(delegatedBy, nodeId, { visit: true })
        runTracker.handoff(delegatedBy, nodeId, msg.data.timestamp)
        // The lead's "delegating to …" step already says it; a separate line only when the
        // turn has no lead bubble to hold it
        if (!findTurnBubble(delegatedBy)) {
          addChatNotification(t('launch.team.assigned', { lead: delegatedBy, member: nodeId }), { at })
        }
      }
    }

    // Model call
    else if (eventType === 'MODEL_CALL') {
      // Model call started
      if (msg.data.details.stage === "before") {
        const baseKey = `model-${msg.data.details.model_name || 'unknown'}`
        if (!delegatedNodes.has(nodeId)) {
          addLoadingEntry(nodeId, baseKey, t('launch.activity.thinking'), {
            isModel: true,
            at: eventAt,
            doneLabel: t('launch.activity_done.thinking')
          })
        }
        else {
          setMemberNow(nodeId, 'model', eventAt)
          touchWorkingTurns()
        }
        officeRef.value?.activity(nodeId, 'model', msg.data.details.model_name || '', true)
        runTracker.activity(nodeId, 'model', msg.data.details.model_name || '', true, msg.data.timestamp)
      }

      // Model call ended
      if (msg.data.details.stage === "after") {
        const baseKey = `model-${msg.data.details.model_name || 'unknown'}`
        finishLoadingEntry(nodeId, baseKey, eventAt)
        if (delegatedNodes.has(nodeId)) {
          setMemberNow(nodeId, null, eventAt)
          touchWorkingTurns()
        }
        officeRef.value?.activity(nodeId, 'model', msg.data.details.model_name || '', false)
        runTracker.activity(nodeId, 'model', msg.data.details.model_name || '', false, msg.data.timestamp)
      }
    }

    // Tool call (a node may call tools multiple times)
    else if (eventType === 'TOOL_CALL') {
      // Tool call started
      if (msg.data.details.stage === "before") {
        const baseKey = `tool-${msg.data.details.tool_name || 'unknown'}`
        // Any lead (sub-leads too) handing work over: remember the task for the member's card
        for (const { member, task } of delegatedTasks(msg.data.details.tool_name, msg.data.details.arguments)) {
          runTracker.assign(member, task)
          officeRef.value?.brief(member, task)
        }
        if (!delegatedNodes.has(nodeId)) {
          addLoadingEntry(nodeId, baseKey, toolActivityLabel(msg.data.details.tool_name, msg.data.details.arguments), {
            at: eventAt,
            doneLabel: toolActivityLabel(msg.data.details.tool_name, msg.data.details.arguments, true),
            member: delegateTarget(msg.data.details.tool_name, msg.data.details.arguments),
            delegates: isDelegateTool(msg.data.details.tool_name)
          })
        } else {
          // A member's step: live on its lead's bubble (the line below the finished steps)
          setMemberNow(nodeId, 'tool', eventAt, msg.data.details.tool_name || '', msg.data.details.arguments || null)
          addMemberStep(nodeId, msg.data.details.tool_name || '', msg.data.details.arguments || null, eventAt)
          touchWorkingTurns()
        }
        officeRef.value?.activity(nodeId, 'tool', msg.data.details.tool_name || '', true, msg.data.details.arguments || null)
        runTracker.activity(nodeId, 'tool', msg.data.details.tool_name || '', true, msg.data.timestamp)
      }

      // Tool call ended
      if (msg.data.details.stage === "after") {
        const baseKey = `tool-${msg.data.details.tool_name || 'unknown'}`
        finishLoadingEntry(nodeId, baseKey, eventAt)
        if (delegatedNodes.has(nodeId)) {
          finishMemberStep(nodeId, msg.data.details.tool_name || '', eventAt)
          setMemberNow(nodeId, null, eventAt)
          touchWorkingTurns()
        }
        officeRef.value?.activity(nodeId, 'tool', msg.data.details.tool_name || '', false, msg.data.details.arguments || null)
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

      }

      // A member cut short by Stop ends with nothing to hand over: it did not report anything
      const details = msg.data.details || {}
      const memberCancelled = Boolean(delegatedBy) && (
        details.cancelled === true || details.status === 'cancelled' || isStopping.value || locallyCancelled
      )
      const memberReported = Boolean(delegatedBy) && !memberCancelled && details.output_count !== 0
      if (delegatedBy && nodeId) {
        settleNodeTurn(nodeId, null, eventAt)
        finishMemberSteps(nodeId, eventAt)
        // The lead summarises for the user; the member's full report stays in Tasks / Overview / Review.
        delegatedNodes.delete(nodeId)
        refreshTeamEdges()
        touchWorkingTurns()
        if (memberReported) {
          officeRef.value?.handoff(nodeId, delegatedBy, { visit: true })
          runTracker.handoff(nodeId, delegatedBy, msg.data.timestamp)
          // The report is a step of the lead's work (expand it to read); the lead's answer
          // speaks for the turn
          const added = addTeamStep(findTurnBubble(delegatedBy), {
            label: t('launch.team.reported', { lead: delegatedBy, member: nodeId }),
            startedAt: memberStarts.get(nodeId) || eventAt,
            endedAt: eventAt,
            detail: details.output
          })
          if (!added) addChatNotification(t('launch.team.reported', { lead: delegatedBy, member: nodeId }), { at })
        }
        memberStarts.delete(nodeId)
        memberNow.delete(nodeId)
      } else if (!settleNodeTurn(nodeId, msg.data.details?.output, eventAt)) {
        addDialogue(nodeId || t('launch.unknown_node'), msg.data.details?.output, at)
      }
      if (nodeId) officeRef.value?.nodeEnd(nodeId, msg.data.details?.output)
      runTracker.nodeEnd(nodeId, msg.data.details?.output, msg.data.timestamp, { status: memberCancelled ? 'cancelled' : 'done' })
    }

    // Edge condition met - trigger sprite animation
    else if (msg.data.message && msg.data.message.includes('Edge condition met for')) {
      handleEdgeConditionMessage(msg.data.message, msg.data.timestamp)
    }

    // Other log messages
    // "Received your input for CTO": your own bubble already says it
    else if (eventType === 'HUMAN_INTERACTION') {
      // nothing to add
    }

    // "Run started" / "run finished": the turn's bubble already shows it working and done.
    // The end line stays only for a turn where no agent said anything.
    else if (eventType === 'WORKFLOW_START' || (eventType === 'WORKFLOW_END' && turnHasAgentBubble())) {
      // nothing to add
    }

    // An agent looked up / saved memory or reflected: a step of its own turn, not a chat line
    // (a member's goes nowhere: its lead's block lists what it did)
    else if (eventType === 'MEMORY_OPERATION' || eventType === 'THINKING_PROCESS') {
      if (nodeId && !delegatedNodes.has(nodeId)) {
        const details = msg.data.details || {}
        const label = eventType === 'THINKING_PROCESS'
          ? t('launch.activity_done.reflect')
          : t(String(details.operation_type || '').toUpperCase() === 'RETRIEVE' ? 'launch.activity_done.memory_read' : 'launch.activity_done.memory_write')
        const baseKey = `note-${eventType}`
        addLoadingEntry(nodeId, baseKey, label, { at: eventAt, doneLabel: label })
        finishLoadingEntry(nodeId, baseKey, eventAt)
      } else if (!nodeId) {
        addChatNotification(localizeLogMessage(msg.data), { at })
      }
    }

    // Set-up chatter ("Global memory 'X' built successfully", "Memory manager built for node A")
    else if (!eventType && SETUP_LOG_RE.test(msg.data.message || '')) {
      // nothing to add
    }

    else if (msg.data.message) {
      addChatNotification(localizeLogMessage(msg.data), { at })
    }
  }

  // The lead ended its turn with a plan that waits for your approval (replayed on reload)
  if (msg.type === 'plan_proposed') {
    showProposedPlan(msg.data || {})
    scheduleSessionsRefresh()
    return
  }

  // Workflow completed
  if (msg.type === 'workflow_completed') {
    // The backend summary ("Workflow finished with N node outputs...") is technical and the
    // WORKFLOW_END log line already said the run is over: only say it when nothing did.
    const endLine = t('launch.log_events.workflow_end')
    const last = chatMessages.value[chatMessages.value.length - 1]
    const isEndLine = last?.type === 'notification' && last.message === endLine
    if (runTracker.state.plan) {
      // The turn ended with a plan waiting for approval: "finished" would mislead
      if (isEndLine) chatMessages.value.pop()
    } else if (!isEndLine && !turnHasAgentBubble()) addChatNotification(t('launch.workflow_completed'), { at })
    runTracker.finish('completed', { summary: formatErrorDetail(msg.data?.summary), tokenUsage: msg.data?.token_usage })
    settleAllNodeTurns({ at: at || Date.now() })
    status.value = 'Completed'
    isWorkflowRunning.value = false
    sessionIdToDownload = sessionId
    endStopping()
    pendingLaunch = null
  }

  // The server has the answer that was sent (also acknowledges a cancel request)
  if (msg.type === 'input_received') {
    if (msg.data?.message !== 'Cancellation requested') confirmPendingInput()
    return
  }

  // Workflow cancelled: from the server, or the confirmation that Stop really stopped it
  if (msg.type === 'workflow_cancelled') {
    const message = locallyCancelled ? t('launch.workflow_cancelled') : formatErrorDetail(msg.data?.message) || t('launch.workflow_cancelled')
    markRunCancelled(message, { at, summary: formatErrorDetail(msg.data?.message) })
  }

  // Handle direct error messages (e.g., workflow execution errors)
  if (msg.type === 'error' && msg.data?.code === 'run_in_progress') {
    // A follow-up was turned down because a run is still going: a notice, not a failure.
    // The turn it opened here (and its message) is taken back; the live run carries on.
    launchRejectedCount += 1
    if (pendingLaunch) {
      pendingLaunch.undo()
      pendingLaunch = null
    }
    if (!isReconnecting.value) toast.warning(t('launch.run_in_progress'))
    return
  }
  if (msg.type === 'error' && msg.data?.fatal === false) {
    // A request was turned down (an answer nobody waits for, an empty or malformed message):
    // say so, but the run and its state carry on; a turned-down answer goes back in the box
    restorePendingInput(msg.data?.code || '')
    if (!isReconnecting.value) {
      const code = msg.data?.code || ''
      const known = code && te(`launch.errors.codes.${code}`)
      toast.warning(known ? t(`launch.errors.codes.${code}`) : errorWithDetail('launch.errors.request_rejected', msg.data?.message))
    }
    return
  }
  if (msg.type === 'error') {
    const errorMessage = withErrorHint(errorWithDetail('launch.errors.workflow_error', msg.data?.message))
    // Live failures of a turn sent from this page can be retried in place
    const retryPrompt = !isReconnecting.value ? lastLaunchPrompt : ''
    addChatNotification(errorMessage, { type: 'error', at, retryPrompt })
    runTracker.finish('error', { error: formatErrorDetail(msg.data?.message) })
    settleAllNodeTurns({ at: at || Date.now(), interrupted: true })
    status.value = 'Error'
    isWorkflowRunning.value = false
    sessionIdToDownload = sessionId
    endStopping()
    pendingInput = null
    pendingLaunch = null
  }
}

// The run is over after a stop: notice, run record, status, and the open activity rows
const markRunCancelled = (message, { at = null, summary = '' } = {}) => {
  endStopping()
  locallyCancelled = false
  pendingInput = null
  pendingLaunch = null
  if (message) addChatNotification(message, at ? { at } : {})
  if (runTracker.state.task && !runTracker.state.outcome) runTracker.finish('cancelled', { summary })
  status.value = 'Cancelled'
  isWorkflowRunning.value = false
  sessionIdToDownload = sessionId
  settleAllNodeTurns({ at: at || Date.now(), interrupted: true })
}

// Stop the running workflow (also while it waits for the user's answer, or is launching).
// The run only counts as stopped once the server confirms it (workflow_cancelled); until
// then the composer stays locked and says "Stopping…". If no confirmation comes, the run is
// marked stopped here after a while so the screen never stays locked.
const cancelWorkflow = () => {
  if (!isRunActive.value || isStopping.value) {
    return
  }
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    toast.warning(t('launch.errors.stop_not_sent'))
    return
  }

  try {
    ws.send(JSON.stringify({ type: 'cancel' }))
  } catch (sendError) {
    console.warn('Failed to send cancel message:', sendError)
    toast.warning(t('launch.errors.stop_not_sent'))
    return
  }

  locallyCancelled = true
  addChatNotification(t('launch.stopping'))
  startStopping()
}

// "Stopping…": locked until the server confirms the stop, marked stopped here after a while
// if it never does (also used when a reopened session is still winding down: "cancelling")
const startStopping = () => {
  isStopping.value = true
  clearTimeout(stopFallbackTimer)
  stopFallbackTimer = setTimeout(() => {
    stopFallbackTimer = null
    if (!isStopping.value) return
    markRunCancelled(t('launch.stop_unconfirmed'))
  }, STOP_FALLBACK_MS)
}

// Download logs
const downloadLogs = async () => {
  // A run that failed early may not have recorded its id for download yet
  const target = sessionIdToDownload || sessionId
  if (!target) {
    return
  }
  try {
    await fetchLogsZip(target)
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

let lastScrollTop = 0

const handleChatScroll = () => {
  const el = chatMessagesRef.value
  if (!el) return
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  // Only scrolling up lets go of the bottom: content that grew between our own scroll to the
  // bottom and its scroll event must not count as "you scrolled away"
  const movedUp = el.scrollTop < lastScrollTop - 2
  lastScrollTop = el.scrollTop
  isNearBottom = distance <= SCROLL_BOTTOM_THRESHOLD || (isNearBottom && !movedUp)
  if (isNearBottom) hasUnseenMessages.value = false
  // Far up in the history: offer the way back down even when nothing new came in
  const scrolledUp = !isNearBottom && distance > SCROLL_BOTTOM_THRESHOLD * 3
  if (isScrolledUp.value !== scrolledUp) isScrolledUp.value = scrolledUp
}

// "New messages" button: back to the latest message, following the chat again from there
const jumpToLatest = () => {
  scheduleScrollToBottom(true)
  taskInputRef.value?.focus({ preventScroll: true })
}

function scheduleScrollToBottom(force = false) {
  if (force) {
    isNearBottom = true
    hasUnseenMessages.value = false
    isScrolledUp.value = false
  }
  if (!isNearBottom || scrollRafId !== null) return
  scrollRafId = requestAnimationFrame(() => {
    scrollRafId = null
    const el = chatMessagesRef.value
    if (el) {
      el.scrollTop = el.scrollHeight
      lastScrollTop = el.scrollTop
    }
    // At the bottom now: nothing is unseen, the "new messages" button goes away
    hasUnseenMessages.value = false
    isScrolledUp.value = false
  })
}

// Clearing / replacing the whole list (new session, reconnect) starts pinned to the bottom
watch(
  () => chatMessages.value.length,
  (length, previous) => {
    if (length === 0) {
      isNearBottom = true
      hasUnseenMessages.value = false
      isScrolledUp.value = false
    } else if (length > (previous || 0) && !isNearBottom) {
      // Reading further up: say something new came in instead of yanking the view down
      hasUnseenMessages.value = true
    }
    scheduleScrollToBottom()
  },
  { flush: 'post' }
)
</script>

<style scoped>

/* ---- Rails: a folded sessions list / chat keeps a slim strip of icon buttons ---- */
.sessions-rail,
.chat-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  width: 48px;
  padding: var(--space-1) 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
}
.sessions-rail { flex: none; }
.chat-rail {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: 9;
  animation: fade-in 0.18s var(--ease-out);
}
.rail-btn {
  position: relative;
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--fg-muted);
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), color 0.15s var(--ease-out);
}
.rail-btn:hover { background: var(--surface-raised); color: var(--fg); }
.rail-btn:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
.rail-dot {
  position: absolute;
  top: 7px;
  right: 7px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 2px var(--surface);
}
.rail-dot.is-waiting { background: var(--warn); }

/* Drag handle on the chat column's right edge (wide screens, outside the chat view) */
.chat-resizer {
  position: absolute;
  top: 12px;
  bottom: 12px;
  right: -7px;
  width: 14px;
  z-index: 12;
  cursor: col-resize;
  pointer-events: auto;
  touch-action: none;
  border-radius: 7px;
}
.chat-resizer::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 5px;
  width: 4px;
  height: 36px;
  margin-top: -18px;
  border-radius: 2px;
  background: var(--border-strong);
  opacity: 0;
  transition: opacity 0.15s var(--ease-out), background-color 0.15s var(--ease-out);
}
.chat-resizer:hover::after,
.chat-resizer:focus-visible::after,
.is-resizing .chat-resizer::after { opacity: 1; }
.chat-resizer:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.is-resizing .chat-resizer::after { background: var(--accent); }
.chat-panel.is-resizing { transition: none; user-select: none; }

/* Chat header: session title + run state, then project and workflow; actions on the right */
.chat-header {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 12px 10px 16px;
  border-bottom: 1px solid var(--border);
}

.chat-header-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.chat-header-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}
.chat-header-status { flex: none; display: inline-flex; max-width: 70%; }

.chat-header-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--fg);
  font-size: 15px;
  font-weight: 650;
}

.chat-header-sub {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
  font-size: var(--fs-xs);
  color: var(--fg-muted);
}

/* The project is context, not a warning: a neutral chip */
.chat-header-project {
  flex: 0 0 auto;
  max-width: 65%;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  min-height: 20px;
  padding: 0 7px 0 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface-raised);
  color: var(--fg);
  font-weight: 550;
}
.chat-header-project svg { flex: none; color: var(--fg-muted); }
.chat-header-project-name,
.chat-header-workflow { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chat-header-workflow { flex: 0 1 auto; }
/* The state outranks the title when room runs out: the title truncates first */
.chat-panel:not(.chat-panel-fullscreen) .chat-header-actions { gap: 0; }
.chat-panel:not(.chat-panel-fullscreen) .chat-header { padding-right: 4px; }

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
  width: 40px;
  height: 40px;
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
  /* Extra room at the bottom: the "new messages" button never sits on the last line */
  padding: 24px clamp(16px, 4%, 48px) 52px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scroll-behavior: auto;
  color: var(--text-2);
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* Empty session */

/* Markdown extras rendered by renderMarkdown: code blocks with a copy button, scrolling tables */
.chat-messages :deep(.md-code) {
  position: relative;
  margin: 4px 0 10px;
}
.chat-messages :deep(.md-code pre) {
  margin: 0;
  padding-top: 30px;
}
.chat-messages :deep(.md-code-lang) {
  position: absolute;
  top: 7px;
  left: 12px;
  font-size: var(--fs-xs);
  color: var(--text-muted-7);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  pointer-events: none;
}
.chat-messages :deep(.md-code-copy) {
  position: absolute;
  top: 4px;
  right: 6px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 7px;
  font-size: var(--fs-xs);
  color: var(--text-muted-7);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 5px;
  cursor: pointer;
}
.chat-messages :deep(.md-code-copy:hover),
.chat-messages :deep(.md-code-copy:focus-visible) {
  color: var(--text-strong);
  background: rgb(var(--ink) / 0.08);
  border-color: rgb(var(--ink) / 0.12);
}
.chat-messages :deep(.md-code-copy.copied) {
  color: var(--accent-green, #34d399);
}
.chat-messages :deep(.md-table) {
  max-width: 100%;
  overflow-x: auto;
  margin: 4px 0 10px;
}
.chat-messages :deep(.md-table table) {
  border-collapse: collapse;
  font-size: 13px;
  min-width: 100%;
}
.chat-messages :deep(.md-table th),
.chat-messages :deep(.md-table td) {
  border: 1px solid rgb(var(--ink) / 0.12);
  padding: 6px 10px;
  text-align: left;
  vertical-align: top;
  min-width: 72px;
  max-width: 360px;
}
/* The user's own line breaks stay as typed (a single Enter is a soft break in markdown) */
.chat-messages :deep(.dialogue-right .markdown-body p) {
  white-space: pre-line;
}
/* Long URLs / unbroken words wrap instead of widening the bubble (code blocks keep scrolling) */
.chat-messages :deep(.markdown-body p),
.chat-messages :deep(.markdown-body li),
.chat-messages :deep(.markdown-body td),
.chat-messages :deep(.markdown-body blockquote) {
  overflow-wrap: anywhere;
}
.chat-messages :deep(.md-table th) {
  background: rgb(var(--ink) / 0.05);
  font-weight: 600;
  white-space: nowrap;
}

/* Keep a readable column, centred like ChatGPT / Claude */
.chat-message-item {
  width: 100%;
  max-width: 820px;
  margin: 0 auto;
}

/* Each message lays out independently so a growing bubble does not invalidate the whole list */
.chat-message-item {
  contain: layout style;
  content-visibility: auto;
  contain-intrinsic-size: auto 120px;
}

/* Chat Notification */
/* System events: a quiet centred caption, not a card */
.chat-notification {
  display: flex;
  justify-content: center;
  margin: 0;
}

.notification-content {
  background: transparent;
  border: 1px solid transparent;
  border-radius: 10px;
  padding: 2px 12px;
  max-width: 90%;
  animation: slideIn 0.3s ease-out;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.notification-text {
  color: rgb(var(--ink) / 0.45);
  font-size: 12px;
  font-weight: 500;
  text-align: center;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.chat-notification:not(.chat-notification-warning):not(.chat-notification-error) .message-timestamp {
  display: none;
}

.chat-notification-warning .notification-content,
.chat-notification-error .notification-content {
  flex-direction: column;
  align-items: center;
  padding: 8px 14px;
}

.chat-notification-warning .notification-content {
  background: rgba(255, 204, 0, 0.08);
  border-color: rgba(255, 204, 0, 0.3);
}

.chat-notification-warning .notification-text {
  color: var(--warn-soft-2);
}

.chat-notification-error .notification-content {
  background: color-mix(in srgb, var(--danger) 12%, transparent);
  border-color: color-mix(in srgb, var(--danger) 40%, transparent);
  color: var(--danger-soft);
}

.question-tag {
  display: inline-flex;
  align-items: center;
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--warn);
  background: color-mix(in srgb, var(--warn) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--warn) 35%, transparent);
}

.message-timestamp {
  font-size: 0.75rem;
  color: rgb(var(--ink) / 0.4);
  margin-left: 8px;
  flex-shrink: 0;
}

.chat-notification .message-timestamp {
  margin-left: 0;
  margin-top: 2px;
  color: rgb(var(--ink) / 0.3);
}

.user-name .message-timestamp {
  opacity: 0;
  transition: opacity 0.15s ease;
}

.dialogue:hover .user-name .message-timestamp {
  opacity: 1;
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
}

.dialogue-right {
  flex-direction: row-reverse;
}

.message-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: stretch;
}

.dialogue-right .message-content {
  max-width: 80%;
  flex: 0 1 auto;
  align-items: flex-end;
}

.user-name {
  font-size: 13px;
  color: rgb(var(--ink) / 0.85);
  font-weight: 600;
  margin: 0;
  min-height: 28px;
  align-items: center;
}

.dialogue-right .user-name {
  text-align: right;
}

/* Chat avatar: pixel-art chibi inside a soft pastel rounded-square tile */
.profile-picture {
  --avatar-size: 28px;
  --avatar-sprite-size: 26px;
  --avatar-bg: linear-gradient(145deg, rgb(var(--accent-indigo-rgb) / 0.28), rgba(201, 167, 235, 0.22) 55%, rgba(255, 180, 237, 0.2));
  --avatar-base: rgb(var(--ink) / 0.06);
  --avatar-border: rgb(var(--ink) / 0.18);
  --avatar-shadow: 0 2px 6px rgb(var(--shade) / 0.35);

  flex-shrink: 0;
  position: relative;
  width: var(--avatar-size);
  height: var(--avatar-size);
  border-radius: 8px;
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

/* Assistant turns: plain text on the page (no card), like Claude / ChatGPT */
.message-bubble {
  background: transparent;
  border: none;
  border-radius: 0;
  padding: 0;
  position: relative;
  color: rgb(var(--ink) / 0.92);
  font-size: 15px;
  line-height: 1.65;
}

/* User turns: a soft rounded bubble on the right, no avatar */
.dialogue-right .message-bubble {
  background: rgb(var(--ink) / 0.07);
  border: 1px solid rgb(var(--ink) / 0.06);
  border-radius: 18px;
  border-bottom-right-radius: 6px;
  padding: 2px 16px;
}

.loading-bubble {
  min-height: 24px;
}

/* ---------- Activity line ---------- */
.activity {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  margin: 0 0 4px;
}

.activity-summary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  padding: 4px 8px 4px 2px;
  margin-left: -2px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: rgb(var(--ink) / 0.5);
  font: inherit;
  font-size: 13px;
  line-height: 1.4;
  cursor: pointer;
  text-align: left;
  transition: color 0.15s ease, background-color 0.15s ease;
}

.activity-summary:hover {
  color: rgb(var(--ink) / 0.8);
  background: rgb(var(--ink) / 0.05);
}

.activity-summary:focus-visible {
  outline: 2px solid rgb(var(--accent-sky-rgb) / 0.6);
  outline-offset: 1px;
}

.activity-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Running label shimmers instead of glowing borders */
.activity-running .activity-label {
  color: rgb(var(--ink) / 0.85);
  animation: activityPulse 1.8s ease-in-out infinite;
}

@keyframes activityPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

/* The step going on now, under the finished ones */
.activity-live {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  min-width: 0;
  padding: 4px 8px 4px 2px;
  font-size: 13px;
  line-height: 1.4;
}

/* "+4 earlier steps": opens the whole list while the turn runs */
.activity-more {
  padding: 2px 6px 2px 2px;
  margin: 0 0 -2px 21px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: rgb(var(--ink) / 0.42);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.activity-more:hover {
  color: rgb(var(--ink) / 0.75);
  background: rgb(var(--ink) / 0.05);
}

.activity-more:focus-visible {
  outline: 2px solid rgb(var(--accent-sky-rgb) / 0.6);
  outline-offset: 1px;
}

.activity-step-count {
  font-variant-numeric: tabular-nums;
  color: rgb(var(--ink) / 0.4);
}

.activity-time {
  font-variant-numeric: tabular-nums;
  color: rgb(var(--ink) / 0.4);
  font-size: 12px;
}

.activity-spinner {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  border-radius: 50%;
  border: 2px solid rgb(var(--ink) / 0.15);
  border-top-color: var(--accent-mint);
  animation: activitySpin 0.9s linear infinite;
}

@keyframes activitySpin {
  to { transform: rotate(360deg); }
}

.activity-chevron {
  flex-shrink: 0;
  transition: transform 0.15s ease;
}

.activity-open .activity-chevron {
  transform: rotate(90deg);
}

.activity-steps {
  list-style: none;
  margin: 2px 0 6px 7px;
  padding: 2px 0 2px 14px;
  border-left: 1px solid rgb(var(--ink) / 0.12);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.activity-step {
  display: flex;
  flex-direction: column;
  font-size: 12.5px;
  color: rgb(var(--ink) / 0.55);
}

.activity-step-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
}

/* A member's report: the row opens it */
.activity-step-toggle {
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  color: inherit;
  text-align: left;
  cursor: pointer;
  border-radius: 4px;
}

.activity-step-toggle:hover .activity-step-label {
  color: rgb(var(--ink) / 0.85);
}

.activity-step-toggle:focus-visible {
  outline: 2px solid var(--accent-mint);
  outline-offset: 2px;
}

.activity-step-label {
  min-width: 0;
  overflow-wrap: anywhere;
}

.activity-step-chevron {
  flex-shrink: 0;
  opacity: 0.7;
  transition: transform 0.15s ease;
}

.activity-step-chevron.is-open {
  transform: rotate(90deg);
}

.activity-step-detail {
  margin: 6px 0 4px 13px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgb(var(--ink) / 0.04);
  color: var(--text-2);
  font-size: 13px;
}

/* Files of the turn, under the answer */
.turn-files {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
}

.turn-files .artifact-file-wrapper {
  padding: 4px 0;
}

.activity-step-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgb(var(--ink) / 0.3);
  flex-shrink: 0;
}

.step-running .activity-step-dot {
  background: var(--accent-mint);
}

.step-running .activity-step-label {
  color: rgb(var(--ink) / 0.85);
}

.activity-step-time {
  margin-left: auto;
  padding-left: 12px;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--ink) / 0.35);
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
  position: relative;
}

/* "New messages" pill: floats above the composer while the chat is scrolled up */
.jump-latest {
  position: absolute;
  left: 50%;
  bottom: calc(100% + 10px);
  transform: translateX(-50%);
  z-index: 5;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid rgb(var(--ink) / 0.14);
  background: rgb(32 32 34 / 0.96);
  color: var(--text-1);
  font-size: 12.5px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  box-shadow: 0 4px 14px rgb(0 0 0 / 0.28);
  transition: background-color 0.15s ease, border-color 0.15s ease;
}
.jump-latest:hover {
  border-color: rgb(var(--ink) / 0.28);
}
.jump-latest:focus-visible {
  outline: 2px solid var(--accent-blue-1);
  outline-offset: 2px;
}
.jump-latest-enter-active,
.jump-latest-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.jump-latest-enter-from,
.jump-latest-leave-to {
  opacity: 0;
  transform: translate(-50%, 6px);
}
:root[data-theme="light"] .jump-latest {
  background: var(--surface-1);
  box-shadow: 0 2px 10px rgb(var(--shade) / 0.18);
}

/* A send that failed: inline above the composer, with Retry (like ChatGPT / Claude) */
.send-error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 8px 10px 8px 14px;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent);
  background: color-mix(in srgb, var(--danger) 10%, transparent);
  color: var(--danger-soft);
  font-size: 13px;
  line-height: 1.45;
}
.send-error-text {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
.send-error-btn {
  flex-shrink: 0;
  padding: 4px 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.send-error-btn:hover:not(:disabled) {
  background: rgb(var(--ink) / 0.08);
}
.send-error-btn:focus-visible {
  outline: 2px solid var(--accent-blue-1);
  outline-offset: 2px;
}
.send-error-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.send-error-retry {
  border-color: color-mix(in srgb, var(--danger) 45%, transparent);
  font-weight: 600;
}
.notification-retry {
  margin-top: 6px;
}

/* The lead's open question, pinned right above the composer */
.question-card {
  margin-bottom: 8px;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--warn) 40%, transparent);
  background: color-mix(in srgb, var(--warn) 8%, transparent);
  color: var(--text-1);
  font-size: 13px;
  line-height: 1.5;
  max-height: calc(40 * var(--vh));
  overflow-y: auto;
}
.question-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--warn);
  margin-bottom: 4px;
}
.question-card-dot {
  width: 8px;
  height: 8px;
  flex: none;
  border-radius: 50%;
  background: var(--warn);
  animation: question-pulse 1.6s ease-in-out infinite;
}
@keyframes question-pulse {
  50% { opacity: 0.35; }
}
.question-card-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.question-card-text.is-clamped {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.question-card-toggle {
  margin-top: 4px;
  padding: 0;
  border: none;
  background: none;
  color: var(--accent-blue-1);
  font-size: 12px;
  cursor: pointer;
}
.question-card-toggle:hover {
  text-decoration: underline;
}
@media (prefers-reduced-motion: reduce) {
  .question-card-dot { animation: none; }
  .jump-latest-enter-active,
  .jump-latest-leave-active { transition-duration: 0.01ms; }
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

/* "Your turn" is carried by the send button; the box itself only lights up on focus */
.composer-send.glow:not(:disabled) { box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 25%, transparent); }

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
  font-size: var(--fs-xs);
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
  font-size: var(--fs-xs);
  color: var(--text-3, rgb(var(--ink) / 0.5));
}

.remove-attachment {
  border: none;
  background: transparent;
  color: var(--accent-sky);
  cursor: pointer;
  padding: 0 4px;
}

/* Plan waiting for approval */
.plan-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.plan-card-head { display: flex; align-items: center; gap: 8px; }

.plan-card-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 650;
  color: rgb(var(--ink) / 0.6);
  background: rgb(var(--ink) / 0.06);
  border: 1px solid rgb(var(--ink) / 0.12);
}

.plan-card-open .plan-card-badge {
  color: var(--warn);
  background: color-mix(in srgb, var(--warn) 12%, transparent);
  border-color: color-mix(in srgb, var(--warn) 40%, transparent);
}

.plan-card-summary {
  margin: 0;
  font-size: 14px;
  line-height: 1.55;
  white-space: pre-wrap;
}

.plan-card-details > summary {
  cursor: pointer;
  font-size: 12.5px;
  font-weight: 600;
  color: rgb(var(--ink) / 0.6);
  margin-bottom: 6px;
}

.plan-card-actions { display: flex; flex-wrap: wrap; gap: 8px; padding-top: 4px; }

.plan-btn {
  padding: 7px 14px;
  border-radius: 9px;
  border: 1px solid rgb(var(--ink) / 0.18);
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.plan-btn:hover:not(:disabled) { background: rgb(var(--ink) / 0.06); }
.plan-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.plan-btn-primary {
  border-color: transparent;
  background: var(--accent-indigo);
  color: #fff;
}

.plan-btn-primary:hover:not(:disabled) { background: var(--accent-indigo); filter: brightness(1.1); }

/* View Toggle */
/* The session moved to another tab */
/* Work waiting for your review */
.toggle-badge {
  display: inline-grid;
  place-items: center;
  min-width: 16px;
  height: 16px;
  margin-left: 4px;
  padding: 0 4px;
  border-radius: 99px;
  font-size: var(--fs-xs);
  font-weight: 700;
  line-height: 1;
  color: var(--on-warn);
  background: var(--warn);
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

/* Markdown Styles moved to CollapsibleMessage.vue */

@keyframes glowPulse {
  0% { box-shadow: 0 0 0 0 rgb(var(--accent-indigo-rgb) / 0.4); }
  50% { box-shadow: 0 0 0 5px rgb(var(--accent-sky-rgb) / 0); }
  100% { box-shadow: 0 0 0 0 rgb(var(--accent-indigo-rgb) / 0); }
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

/* The chat panel floats over the left of the canvas: the graph starts right of it, so
   fit-to-view never hides the lead behind the chat */
.graph-flow-panel {
  position: relative;
}
.graph-flow-panel { --graph-bar-h: 52px; }
.graph-flow-panel .vueflow-graph {
  position: absolute;
  top: var(--graph-bar-h);
  right: 0;
  bottom: 0;
  left: var(--graph-inset, 0px);
  width: auto;
  height: auto;
}
/* Title + zoom tools in a bar of their own above the canvas */
.graph-bar {
  position: absolute;
  top: 0;
  right: 0;
  left: var(--graph-inset, 0px);
  height: var(--graph-bar-h);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 0 var(--space-3) 0 var(--space-4);
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}
.graph-bar-title {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 600;
  color: var(--fg);
}
.graph-tools { flex: none; display: flex; align-items: center; gap: 2px; }
.graph-tool {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--fg-muted);
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), color 0.15s var(--ease-out);
}
.graph-tool:hover { background: var(--surface-raised); color: var(--fg); }
.graph-tool[aria-pressed="true"] { background: var(--surface-raised); color: var(--fg); }
.graph-tool:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
.graph-zoom {
  min-width: 44px;
  text-align: center;
  font-size: 12px;
  color: var(--fg-muted);
  font-variant-numeric: tabular-nums;
}

.image-modal {
  position: fixed;
  inset: 0;
  background: rgb(var(--shade) / 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
}

.image-modal-close {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--text-1);
  cursor: pointer;
}

.image-modal-close:hover { background: rgb(var(--ink) / 0.1); }
.image-modal-close:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }

.image-modal-content {
  position: relative;
  max-width: 95vw;
  max-height: calc(95 * var(--vh));
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
  max-height: calc(65 * var(--vh));
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

/* ===========================================================================
 * Shell: header with the persistent view tabs, then sessions | chat+views | status
 * Semantic tokens only, so dark and light themes both resolve from main.css.
 * ========================================================================= */
.launch-view {
  --header-h: 48px;
  width: 100%;
  height: calc(100 * var(--vh));
  height: calc(100 * var(--dvh));
  display: flex;
  flex-direction: column;
  background-color: var(--bg);
  color: var(--fg);
  position: relative;
  overflow: hidden;
  /* Browser-drawn parts follow the theme too */
  caret-color: var(--accent);
  scrollbar-color: color-mix(in srgb, var(--fg-muted) 45%, transparent) transparent;
  scrollbar-width: thin;
}
.launch-view ::selection { background: color-mix(in srgb, var(--accent) 30%, transparent); color: inherit; }
.launch-view :deep(::selection) { background: color-mix(in srgb, var(--accent) 30%, transparent); }

.header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  height: var(--header-h);
  padding: 0 var(--space-4);
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  position: relative;
  z-index: 2;
}

.header h1 {
  margin: 0;
  padding-right: var(--space-2);
  color: var(--fg);
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0;
  white-space: nowrap;
}

.brand-link {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  margin-left: calc(var(--space-2) * -1);
  border-radius: var(--radius-md);
  transition: background-color 0.15s var(--ease-out);
}
.brand-link:hover { background: var(--surface-raised); }
.brand-link img { display: block; width: 24px; height: 24px; }

.header-actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding-left: var(--space-2);
  margin-left: var(--space-1);
  border-left: 1px solid var(--border);
}
.header-btn {
  position: relative;
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 10px;
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--fg-muted);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  text-decoration: none;
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), color 0.15s var(--ease-out);
}
.header-btn svg { flex: none; }
.header-btn:hover { background: var(--surface-raised); color: var(--fg); }
.header-btn.active { background: var(--surface-raised); color: var(--fg); }
.header-btn:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
/* No workflow yet: the panel holding the picker asks for attention */
.header-btn.needs-workflow { color: var(--fg); box-shadow: inset 0 0 0 1.5px var(--accent); }

.view-tabs {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--space-1);
  overflow-x: auto;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 10px, #000 calc(100% - 14px), transparent);
  mask-image: linear-gradient(90deg, transparent, #000 10px, #000 calc(100% - 14px), transparent);
}
.view-tabs::-webkit-scrollbar { display: none; }

.view-tab {
  position: relative;
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 34px;
  padding: 0 var(--space-3);
  border: none;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--fg-muted);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), color 0.15s var(--ease-out);
}
.view-tab::after {
  content: '';
  position: absolute;
  left: var(--space-3);
  right: var(--space-3);
  bottom: 2px;
  height: 2px;
  border-radius: 2px;
  background: var(--accent);
  transform: scaleX(0);
  transition: transform 0.18s var(--ease-out);
}
.view-tab:hover { background: var(--surface-raised); color: var(--fg); }
.view-tab.active { color: var(--fg); font-weight: 600; }
.view-tab.active::after { transform: scaleX(1); }
.view-tab:focus-visible,
.chat-header-btn:focus-visible,
.composer-send:focus-visible,
.composer-icon-btn:focus-visible,
.chat-empty-chip:focus-visible,
.composer-hint-action:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}

/* Labels give way to icons as the header narrows (aria-label/title always name them) */
@media (max-width: 1279.98px) {
  .header-link .header-btn-label { display: none; }
}
@media (max-width: 1099.98px) {
  .header-btn-label:not(.settings-label) { display: none; }
}
@media (max-width: 899.98px) {
  .settings-label { display: none; }
  .header-btn { width: 40px; height: 40px; padding: 0; justify-content: center; }
}
@media (max-width: 639.98px) {
  .header-link { display: none; }
}

.content {
  flex: 1;
  display: flex;
  overflow: hidden;
  padding: var(--space-4);
  gap: var(--space-4);
  position: relative;
  z-index: 1;
  min-height: 0;
}

/* The session list is its own wrapper only so it can become a drawer on narrow screens */
.sessions-drawer:not(.is-drawer) { display: contents; }

.left-panel {
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
  position: relative;
}

/* ---- Chat panel: full width in the chat, a solid card over the canvas elsewhere ---- */
.chat-panel {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: var(--chat-w, 380px);
  z-index: 10;
  display: flex;
  flex-direction: row;
  pointer-events: none;
  /* Slides on the compositor only: no layout or text re-wrapping while it moves */
  transition: transform 0.2s var(--ease-out);
}
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
.chat-panel-collapsed { transform: translateX(calc(-100% - 24px)); }
.chat-panel-collapsed .chat-panel-content {
  visibility: hidden;
  transition: visibility 0s linear 0.2s;
}
.chat-panel-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0;
  min-width: 0;
  min-height: 0;
  pointer-events: auto;
  /* Opaque: scene labels and graph nodes never ghost through the messages */
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  padding: 0;
}
.chat-panel:not(.chat-panel-fullscreen) .chat-panel-content {
  box-shadow: 0 12px 32px -12px rgb(0 0 0 / 0.45);
  animation: panel-in-left 0.2s var(--ease-out);
}
.chat-panel-fullscreen .chat-panel-content { animation: view-in 0.18s var(--ease-out); }

/* ---- Views fade in as they are shown ---- */
.graph-panel { animation: view-in 0.18s var(--ease-out); }
@keyframes view-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: none; }
}
@keyframes panel-in-left {
  from { opacity: 0; transform: translateX(-10px); }
  to { opacity: 1; transform: none; }
}
@keyframes panel-in-right {
  from { opacity: 0; transform: translateX(10px); }
  to { opacity: 1; transform: none; }
}
@keyframes msg-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: none; }
}
@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes nudge {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent) 0%, transparent); }
  50% { box-shadow: 0 0 0 5px color-mix(in srgb, var(--accent) 35%, transparent); }
}

.chat-message-item { animation: msg-in 0.18s var(--ease-out) both; }

/* Chat header: helper text stays >= 12px */
.chat-header { min-height: 60px; padding: 8px 8px 8px 16px; }
.chat-header-actions { gap: 2px; }
.chat-header-btn { position: relative; color: var(--fg-muted); }
.chat-header-btn:hover,
.chat-header-btn.active { background: var(--surface-raised); color: var(--fg); }

/* Reading measure: prose of a turn stops at ~70 characters; code and tables may run wider */
.chat-messages :deep(.dialogue:not(.dialogue-right) .markdown-body) > :not(.md-code):not(.md-table):not(pre):not(table) {
  max-width: 70ch;
}
.activity,
.plan-card { max-width: 76ch; }

/* ---- "Open in another tab": the single notice for it, inside the chat, under the header ---- */
.replaced-banner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-3);
  flex: none;
  margin: var(--space-2) var(--space-3) 0;
  padding: 10px var(--space-3);
  border-radius: var(--radius-md);
  border: 1px solid color-mix(in srgb, var(--warn) 45%, var(--border));
  background: color-mix(in srgb, var(--warn) 12%, var(--surface));
  color: var(--fg);
  font-size: 13px;
  line-height: 1.45;
  animation: msg-in 0.18s var(--ease-out);
}
.replaced-banner-text { flex: 1; min-width: 160px; }
.replaced-banner-button {
  min-height: 32px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.replaced-banner-button:hover { filter: brightness(1.08); }

/* ---- Empty new session: greeting, starter prompts, plan note ---- */
.chat-empty {
  margin: auto;
  max-width: 520px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-5) var(--space-2);
  text-align: center;
}
.chat-empty-avatar {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  margin-bottom: var(--space-2);
  border-radius: 50%;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, var(--surface));
  border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--border));
}
.chat-empty-title {
  margin: 0;
  font-size: 20px;
  line-height: 1.3;
  font-weight: 600;
  color: var(--fg);
  text-wrap: balance;
}
.chat-empty-hint {
  margin: 0;
  font-size: 14px;
  line-height: 1.55;
  color: var(--fg-muted);
  text-wrap: pretty;
}
.chat-empty-suggest {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
.chat-empty-chip {
  max-width: 100%;
  min-height: 36px;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid var(--border-strong);
  background: var(--surface);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  line-height: 1.4;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out), border-color 0.15s var(--ease-out);
}
.chat-empty-chip:hover:not(:disabled) { background: var(--surface-raised); border-color: var(--accent); }
.chat-empty-chip:disabled { opacity: 0.5; cursor: not-allowed; }
.chat-empty-note {
  margin: var(--space-3) 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--fg-muted);
}
.chat-empty-pick { margin-top: var(--space-3); }

.chat-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  width: 100%;
  max-width: 560px;
  margin: 0 auto;
}

/* Attachment line of a user message: one chip per file or folder */
.msg-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 6px 0 8px;
  padding: 0;
  list-style: none;
}
.dialogue-right .msg-attachments { justify-content: flex-end; }
.msg-attachment {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--fg);
  font-size: 13px;
  line-height: 1.4;
}
.msg-attachment svg { flex: none; color: var(--fg-muted); }
.msg-attachment-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 260px; }

/* ---- Composer ---- */
.composer-hint {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px var(--space-2);
  margin: 0;
  padding: var(--space-2) var(--space-4);
  font-size: 13px;
  line-height: 1.4;
  color: var(--fg-muted);
}
.composer-hint svg { flex: none; }
.composer-hint-action {
  padding: 2px 4px;
  border: none;
  background: transparent;
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
  border-radius: var(--radius-sm);
}
.input-shell { background-color: var(--surface); border-color: var(--border-strong); }
.input-shell:focus-within {
  border-color: var(--accent);
  background-color: var(--surface);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent);
}
.composer-icon-btn { border-color: var(--border-strong); color: var(--fg-muted); }
.composer-icon-btn:hover:not(:disabled),
.composer-icon-btn.active { background: var(--surface-raised); color: var(--fg); }
.composer-send {
  border: none;
  background: var(--accent);
  color: var(--on-accent);
}
.composer-send:hover:not(:disabled) { filter: brightness(1.08); }
.composer-send:active:not(:disabled) { transform: scale(0.96); }
/* While a run is active the same button is Stop: neutral, never alarm-red */
.composer-send.is-stop {
  border-radius: 10px;
  background: var(--fg);
  color: var(--bg);
  animation: composer-stop-pulse 1.6s var(--ease-out) infinite;
}
@keyframes composer-stop-pulse {
  0%, 100% { box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 45%, transparent); }
  50% { box-shadow: 0 0 0 5px color-mix(in srgb, var(--accent) 12%, transparent); }
}
.composer-icon-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.task-input::placeholder { color: var(--fg-muted); }
.jump-latest { background: var(--surface-raised); border-color: var(--border-strong); color: var(--fg); font-size: 13px; }

/* ---- Status panel (wide: a column; outside the chat: a floating card) ---- */
.right-panel {
  flex: 0 0 clamp(260px, 22vw, 320px);
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.right-panel-hidden { display: none; }
/* Outside the chat view: a drawer on the right, opened from the header */
.right-panel-overlay {
  position: absolute;
  top: var(--space-4);
  right: var(--space-4);
  bottom: var(--space-4);
  width: 320px;
  max-width: 40%;
  z-index: 10;
  flex: none;
  pointer-events: none;
  transition: transform 0.2s var(--ease-out), opacity 0.2s var(--ease-out);
}
.right-panel-overlay .control-section {
  flex: 1 1 auto;
  pointer-events: auto;
  animation: panel-in-right 0.2s var(--ease-out);
  box-shadow: 0 16px 40px -12px rgb(0 0 0 / 0.5);
}
.right-panel-collapsed { transform: translateX(16px); opacity: 0; }
.right-panel-collapsed .control-section { visibility: hidden; }

.control-section {
  flex: 0 1 auto;
  display: flex;
  flex-direction: column;
  gap: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: var(--space-2) var(--space-4) var(--space-4);
  min-height: 0;
  overflow-y: auto;
  scrollbar-gutter: stable;
}
/* Sections: spacing and a hairline, never cards inside the card */
.panel-block {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
  padding: var(--space-4) 0;
}
.panel-block + .panel-block { border-top: 1px solid var(--border); }
.control-section > .button-section { padding-top: var(--space-4); border-top: 1px solid var(--border); }
.panel-heading-row { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-2); }
.panel-link {
  align-self: flex-start;
  min-height: 28px;
  padding: 2px 6px;
  margin-left: -6px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--accent);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.panel-heading-row .panel-link { margin: 0 -6px 0 0; }
.panel-link:hover { background: var(--surface-raised); text-decoration: underline; text-underline-offset: 3px; }
.panel-link:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 1px; }
.panel-note.is-clamped {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  overflow: hidden;
}

/* Team of this run */
.team-list { display: flex; flex-direction: column; gap: 2px; margin: 0; padding: 0; list-style: none; }
.team-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 32px;
  min-width: 0;
}
.team-avatar {
  flex: none;
  display: grid;
  place-items: end center;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  background: var(--surface-raised);
  border: 1px solid var(--border);
  overflow: hidden;
}
.team-avatar img { width: 22px; height: 22px; object-fit: contain; object-position: 50% 100%; image-rendering: pixelated; }
.team-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 550;
  color: var(--fg);
}

/* Recent activity: newest first, time aligned on the right */
.activity-feed { display: flex; flex-direction: column; gap: var(--space-2); margin: 0; padding: 0; list-style: none; }
.activity-feed-item { display: flex; align-items: baseline; gap: var(--space-2); min-width: 0; font-size: 13px; line-height: 1.4; }
.activity-feed-text {
  flex: 1;
  min-width: 0;
  color: var(--fg);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
  overflow-wrap: anywhere;
}
.activity-feed-time { flex: none; font-size: 12px; color: var(--fg-muted); font-variant-numeric: tabular-nums; }
.panel-heading {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0;
  text-transform: none;
  color: var(--fg);
}
.panel-note,
.workflow-hint { margin: 0; font-size: 12px; line-height: 1.5; color: var(--fg-muted); }
.workflow-picker { border-radius: var(--radius-md); }
.workflow-picker.needs-workflow :deep(.select) {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent);
}
.workflow-picker.nudge { animation: nudge 0.9s var(--ease-out) 2; }

.status-facts { display: flex; flex-direction: column; gap: var(--space-2); margin: 0; }
.status-fact { display: flex; align-items: baseline; justify-content: space-between; gap: var(--space-3); }
.status-fact dt { flex: none; font-size: 12px; color: var(--fg-muted); }
.status-fact dd { margin: 0; min-width: 0; font-size: 13px; color: var(--fg); text-align: right; overflow-wrap: anywhere; }
.status-fact dd.is-num { font-variant-numeric: tabular-nums; }
.button-section { display: flex; flex-direction: column; gap: var(--space-2); }

.sheet-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  position: relative;
  margin-right: calc(var(--space-2) * -1);
  padding-top: var(--space-1);
}
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; color: var(--fg); }
.sheet-backdrop {
  position: fixed;
  inset: var(--header-h) 0 0 0;
  z-index: var(--z-backdrop);
  background: rgb(0 0 0 / 0.5);
  animation: fade-in 0.15s var(--ease-out);
}

/* Canvases keep a solid surface; nothing ghosts behind them */
.graph-panel { background-color: var(--surface); border-color: var(--border); }
.image-modal { background: rgb(0 0 0 / 0.7); }

/* ===========================================================================
 * Narrow (< 900px): status panel = bottom sheet, sessions = left drawer,
 * composer pinned to the bottom of the dynamic viewport.
 * ========================================================================= */
@media (max-width: 899.98px) {
  .content { padding: var(--space-2); gap: 0; flex-direction: column; }
  .left-panel { flex: 1 1 auto; min-height: 0; }
  .chat-panel-content { border-radius: var(--radius-md); }
  .chat-panel-fullscreen .chat-panel-content { border-left: none; border-right: none; border-radius: 0; }
  .chat-panel:not(.chat-panel-fullscreen) { width: calc(100% - 48px); max-width: calc(100% - 48px); }
  .input-area { padding-bottom: env(safe-area-inset-bottom, 0px); background: var(--surface); }
  .chat-messages { padding: var(--space-4) var(--space-3) 52px; }
  .view-tab { height: 40px; }
  .chat-header-btn { width: 40px; height: 40px; }
  .composer-icon-btn,
  .composer-send { width: 40px; height: 40px; }
  .attach-menu-item { min-height: 44px; }

  .sessions-drawer.is-drawer {
    position: fixed;
    top: var(--header-h);
    bottom: 0;
    left: 0;
    width: min(340px, 88vw);
    z-index: var(--z-modal);
    display: flex;
    transform: translateX(-100%);
    visibility: hidden;
    transition: transform 0.2s var(--ease-out), visibility 0s linear 0.2s;
  }
  .sessions-drawer.is-drawer.is-open { transform: none; visibility: visible; transition: transform 0.2s var(--ease-out); }
  .sessions-drawer.is-drawer > .session-sidebar,
  .sessions-drawer.is-drawer > .session-sidebar:not(.collapsed) {
    flex: 1 1 auto;
    width: 100%;
    border-radius: 0 var(--radius-lg) var(--radius-lg) 0;
    background: var(--surface);
    border-left: none;
  }

  .right-panel.is-sheet {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    top: auto;
    width: auto;
    max-width: none;
    flex: none;
    z-index: var(--z-modal);
    transform: translateY(100%);
    visibility: hidden;
    opacity: 1;
    pointer-events: auto;
    transition: transform 0.2s var(--ease-out), visibility 0s linear 0.2s;
  }
  .right-panel.is-sheet.is-open { transform: none; visibility: visible; transition: transform 0.2s var(--ease-out); }
  .right-panel.is-sheet .control-section {
    max-height: calc(80 * var(--dvh));
    border-radius: var(--radius-lg) var(--radius-lg) 0 0;
    border-bottom: none;
    padding: var(--space-3) var(--space-4) calc(var(--space-4) + env(safe-area-inset-bottom, 0px));
    box-shadow: 0 -12px 32px -12px rgb(0 0 0 / 0.5);
    animation: none;
  }
  .sheet-head { padding-top: var(--space-2); }
  .sheet-grip {
    position: absolute;
    top: -4px;
    left: 50%;
    width: 36px;
    height: 4px;
    margin-left: -18px;
    border-radius: 2px;
    background: var(--border-strong);
  }
  .sheet-backdrop { inset: 0; }
}

@media (max-width: 639.98px) {
  .header { padding: 0 var(--space-2) 0 var(--space-3); gap: var(--space-2); }
  /* The tabs need the width more than the title does */
  .header h1 { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
}

/* Wide but not huge: sessions column a little slimmer */
@media (min-width: 900px) and (max-width: 1100px) {
  .content { padding: var(--space-3); gap: var(--space-3); }
  .sessions-drawer:not(.is-drawer) > .session-sidebar:not(.collapsed) { flex-basis: 220px; width: 220px; }
}

@media (prefers-reduced-motion: reduce) {
  .launch-view *,
  .launch-view *::before,
  .launch-view *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    transition-delay: 0s !important;
  }
}

/* ---------- Light theme: legibility (low-alpha ink text is too faint on white) ---------- */
:root[data-theme="light"] .user-name,
:root[data-theme="light"] .message-timestamp,
:root[data-theme="light"] .chat-notification .message-timestamp,
:root[data-theme="light"] .attachment-meta,
:root[data-theme="light"] .no-active-nodes,
:root[data-theme="light"] .artifact-status {
  color: var(--text-muted-1);
}
:root[data-theme="light"] .notification-text,
:root[data-theme="light"] .artifact-filename {
  color: var(--text-soft-3);
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
:root[data-theme="light"] .user-name,
:root[data-theme="light"] .message-bubble {
  color: var(--text-1);
}
:root[data-theme="light"] .dialogue-right .message-bubble {
  background: rgb(var(--ink) / 0.05);
  border-color: rgb(var(--ink) / 0.06);
}
:root[data-theme="light"] .activity-summary,
:root[data-theme="light"] .activity-step {
  color: var(--text-muted-1);
}
:root[data-theme="light"] .attachment-button,
:root[data-theme="light"] .artifact-download-button {
  background: #fff;
  border-color: rgb(var(--ink) / 0.2);
  color: var(--text-soft-3);
}
:root[data-theme="light"] .attachment-button:hover:not(:disabled),
:root[data-theme="light"] .artifact-download-button:hover:not(:disabled) {
  background: var(--surface-4);
  border-color: rgb(var(--ink) / 0.35);
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
:root[data-theme="light"] .attachment-modal {
  border-color: rgb(var(--ink) / 0.14);
  box-shadow: 0 12px 32px -8px rgb(15 23 42 / 0.18);
}
:root[data-theme="light"] .attachment-item {
  background: var(--surface-4);
}
:root[data-theme="light"] .active-node-item {
  background: #fff;
  border: 1px solid rgb(var(--ink) / 0.08);
  color: var(--text-2);
}
:root[data-theme="light"] .node-dot {
  box-shadow: none;
}
:root[data-theme="light"] .chat-panel:not(.chat-panel-fullscreen) .chat-panel-content,
:root[data-theme="light"] .right-panel-overlay .control-section,
:root[data-theme="light"] .chat-rail {
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.06), 0 12px 30px -12px rgb(15 23 42 / 0.22);
}
:root[data-theme="light"] .image-modal {
  background: rgb(15 23 42 / 0.55);
}
:root[data-theme="light"] .image-modal-content {
  background: rgb(255 255 255 / 0.96);
  border-color: rgb(var(--ink) / 0.12);
}

</style>
