<template>
  <div ref="launchRootRef" class="launch-view">
    <div class="header">
      <!-- The app's own nav is hidden on this page (it opens in a tab of its own): the logo is the way back -->
      <router-link to="/" target="_blank" rel="noopener" class="brand-link" :aria-label="$t('launch.shell.home')" :title="$t('launch.shell.home')">
        <img src="/media/logo.svg?v=2" alt="" width="24" height="24" />
      </router-link>
      <h1>{{ $t('launch.title') }}</h1>
      <!-- Persistent view switcher: the same in every mode and at every width -->
      <div ref="viewTabsRef" class="view-tabs" :class="{ 'is-overflowing': viewTabsOverflow }" role="tablist" :aria-label="$t('launch.view')" @keydown="onViewTabKey">
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
          :aria-label="tabLabel(option)"
          :title="tabLabel(option)"
          @click="selectView(option.mode)"
        >
          <!-- Icons only show on very narrow screens, where inactive tabs drop their label -->
          <svg class="view-tab-icon" aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path v-for="(d, i) in option.icon" :key="i" :d="d"></path></svg>
          <span class="view-tab-label">{{ tabLabel(option) }}</span>
          <span v-if="option.mode === 'review' && reviewPendingCount" class="toggle-badge">{{ reviewPendingCount }}</span>
          <!-- How many files the team wrote for this session (a dot while its app runs) -->
          <span v-if="option.mode === 'products' && productsSummary?.file_count" class="toggle-badge products-badge" :class="{ 'is-live': productsLive }">{{ productsSummary.file_count > 999 ? '999+' : productsSummary.file_count }}</span>
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
          <!-- Outside the chat view the chat toggle joins this rail: one strip instead of two -->
          <template v-if="viewMode !== 'chat'">
            <span class="rail-sep" aria-hidden="true"></span>
            <button
              type="button"
              class="rail-btn rail-btn-chat"
              :class="{ 'is-active': isChatPanelOpen }"
              :title="isChatPanelOpen ? $t('launch.shell.chat_collapse') : $t('launch.shell.chat_expand')"
              :aria-label="isChatPanelOpen ? $t('launch.shell.chat_collapse') : $t('launch.shell.chat_expand')"
              :aria-expanded="isChatPanelOpen"
              @click="isChatPanelOpen = !isChatPanelOpen"
            >
              <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
              <span v-if="!isChatPanelOpen && (pendingQuestion || hasUnseenMessages)" class="rail-dot" :class="{ 'is-waiting': pendingQuestion }" :title="pendingQuestion ? $t('launch.shell.lead_waiting') : $t('launch.jump_to_latest')"></span>
            </button>
          </template>
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
          :load-error="sessionsLoadFailed"
          @retry="refreshSessions"
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
        <div v-if="viewMode !== 'chat' && !isChatPanelOpen && !isChatRailMerged" class="chat-rail">
          <button
            type="button"
            class="rail-btn rail-btn-chat"
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
                  <span class="chat-header-status" role="status">
                    <StatusPill v-if="selectedFile" compact :tone="statusPillTone" :label="isStopping ? $t('launch.stopping') : statusLabel" />
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
                <div v-if="isReplaying || (isReconnecting && !chatMessages.length)" class="chat-skeleton" role="status" :aria-label="$t('launch.loading')">
                  <BaseSkeleton width="40%" height="14px" />
                  <BaseSkeleton height="14px" />
                  <BaseSkeleton width="85%" height="14px" />
                  <BaseSkeleton width="55%" height="14px" />
                </div>
                <!-- A long session renders only its latest messages; older ones on demand -->
                <div v-if="hiddenMessageCount" class="chat-older">
                  <button type="button" class="chat-older-btn" @click="showOlderMessages">
                    {{ $t('launch.history.show_older', { n: Math.min(hiddenMessageCount, WINDOW.step) }) }}
                  </button>
                  <span class="chat-older-note">{{ $t('launch.history.hidden', { n: hiddenMessageCount }) }}</span>
                </div>
                <!-- Notifications and dialogues in order -->
                <div
                  v-for="message in visibleMessages"
                  :key="messageKey(message)"
                  :data-msg-key="messageKey(message)"
                  class="chat-message-item"
                  v-memo="[
                    message.rev,
                    messageAvatar(message),
                    message.duration,
                    message.loading,
                    message.dataUri,
                    message.error,
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
                  <div class="notification-text">{{ message.message }}<span v-if="message.repeat > 1" class="notification-repeat">×{{ message.repeat }}</span></div>
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

              <!-- Tool calls that failed during one agent's step, grouped: the agent gets the
                   reason and usually fixes it itself, so once it moves on the group goes quiet -->
              <div
                v-else-if="message.type === 'tool_issues'"
                class="tool-issues"
                :class="{ 'is-recovered': message.recovered, 'is-open': message.open }"
                :data-tool-issues="message.nodeId"
              >
                <button
                  type="button"
                  class="tool-issues-summary"
                  :aria-expanded="!!message.open"
                  @click="toggleToolIssues(message)"
                >
                  <svg class="tool-issues-chevron" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"></path></svg>
                  <span class="tool-issues-text">{{ toolIssuesHeadline(message) }}</span>
                  <span class="message-timestamp">{{ formatTime(message.timestamp) }}</span>
                </button>
                <ul v-if="message.open" class="tool-issues-list">
                  <li v-for="item in message.items" :key="item.key" class="tool-issues-item">
                    <span class="tool-issues-tool">{{ item.tool }}</span>
                    <span class="tool-issues-reason">{{ item.reason }}</span>
                    <span v-if="item.count > 1" class="tool-issues-count">×{{ item.count }}</span>
                  </li>
                </ul>
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
                        :html-content="message.plan.plan ? renderRowMarkdown(message, message.plan.plan) : (message.htmlContent || renderRowMarkdown(message, message.text))"
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
                      :html-content="userAttachments(message) ? renderRowMarkdown(message, userAttachments(message).body) : (message.htmlContent || renderRowMarkdown(message, message.text))"
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
                          {{ file.loading ? $t('launch.preparing') : file.openLocal ? $t('launch.open_file') : $t('launch.download') }}
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
                      {{ message.loading ? $t('launch.preparing') : message.openLocal ? $t('launch.open_file') : $t('launch.download') }}
                    </button>
                  </div>
                </div>
                </div>
              </div>
            </div>
                <div v-if="hiddenNewerCount" class="chat-older chat-newer">
                  <button type="button" class="chat-newer-btn" @click="showNewerMessages">
                    {{ $t('launch.history.show_newer', { n: Math.min(hiddenNewerCount, WINDOW.step) }) }}
                  </button>
                  <span class="chat-older-note">{{ $t('launch.history.hidden_newer', { n: hiddenNewerCount }) }}</span>
                </div>
          </div>
            </div>
            <div ref="inputAreaRef" class="input-area">
              <!-- Scrolled up while new messages came in: one click back to the latest -->
              <Transition name="jump-latest">
                <button
                  v-if="hasUnseenMessages || isScrolledUp"
                  type="button"
                  class="jump-latest"
                  :class="{ 'has-new': hasUnseenMessages }"
                  :aria-label="hasUnseenMessages ? $t('launch.jump_to_latest') : $t('launch.chat_ui.scroll_to_bottom')"
                  :title="hasUnseenMessages ? $t('launch.jump_to_latest') : $t('launch.chat_ui.scroll_to_bottom')"
                  @click="jumpToLatest"
                >
                  <span v-if="hasUnseenMessages" class="jump-latest-label">{{ $t('launch.jump_to_latest') }}</span>
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
              <!-- The live region stays in the DOM (one that appears together with its text is often not announced) -->
              <div role="status" class="composer-hint-live">
              <p v-if="composerHint" class="composer-hint">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><line x1="12" y1="8" x2="12" y2="12.5"></line><circle cx="12" cy="16" r="0.6" fill="currentColor"></circle></svg>
                <span>{{ composerHint }}</span>
                <button v-if="(!selectedFile || missingWorkflow) && !loading && (chatMessages.length || missingWorkflow)" type="button" class="composer-hint-action" @click="focusWorkflowPicker">
                  {{ $t('launch.composer.pick_workflow_action') }}
                </button>
              </p>
              </div>
              <!-- The last run stopped before it finished: one click continues it with what it already did -->
              <p v-if="canResumeRun" class="composer-hint" role="status">
                <span>{{ $t('launch.resume.banner') }}</span>
                <button type="button" class="composer-hint-action" @click="resumeRun">{{ $t('launch.resume.action') }}</button>
              </p>
              <!-- One tray above the box: while the team works, the live line on top; once the turn is
                   over, the next-step chips on the left and its totals as a quiet line on the right -->
              <div
                v-if="liveLineVisible || quickReplies.length"
                class="turn-footer"
                :class="{ 'is-settled': !liveLineVisible }"
              >
              <LiveProgress
                v-if="liveLineVisible"
                :workers="liveProgress.workers"
                :headline="liveProgress.headline"
                :tone="liveProgress.tone"
                :started-at="liveProgress.startedAt"
                :ended-at="liveProgress.endedAt"
                :steps="liveProgress.steps"
                :issues="liveProgress.issues"
                :usage="liveProgress.usage"
                :last-event-at="lastEventAt"
                @show-issues="revealToolIssues"
                @stall-level="stallLevel = $event"
              />
              <!-- What makes sense to say next in this state (approve the plan, ask for progress, retry...) -->
              <QuickReplies
                :items="quickReplies"
                :disabled="isStopping"
                :label="$t('launch.quick.label')"
                @pick="pickQuickReply"
              />
              </div>
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
                    :title="attachment.kind === 'project' ? attachment.workspacePath : (attachment.url || attachment.query || attachment.name)"
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
                  :title="$t('launch.shortcuts.hint')"
                  :aria-label="$t(leadName ? 'launch.chat_ui.composer_label' : 'launch.chat_ui.composer_label_agent')"
                  ref="taskInputRef"
                  @input="autoResizeTaskInput"
                  @keydown.enter="handleEnterKey"
                  @keydown.up="recallLastPrompt"
                  @keydown.tab.shift.exact.prevent="cycleRunMode"
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
                      :disabled="!isConnectionReady || !sessionId || isUploadingAttachment || isStopping || (isWorkflowRunning && !isWaitingForInput)"
                      @click="toggleAttachMenu"
                    >
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="12" y1="5" x2="12" y2="19"></line>
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                      </svg>
                    </button>
                    <Transition name="attachment-popover">
                      <div v-if="showAttachMenu && !webForm" class="attach-menu" role="menu">
                        <button type="button" class="attach-menu-item" role="menuitem" @click="pickAttachmentFile">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path></svg>
                          {{ $t('launch.upload_file') }}
                        </button>
                        <button type="button" class="attach-menu-item" role="menuitem" @click="pickAttachmentImage">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
                          {{ $t('launch.attach.image') }}
                        </button>
                        <button type="button" class="attach-menu-item" role="menuitem" :title="$t('launch.upload_folder_hint')" @click="pickAttachmentFolder">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                          {{ $t('launch.upload_folder') }}
                        </button>
                        <div class="attach-menu-sep" role="separator"></div>
                        <button type="button" class="attach-menu-item" role="menuitem" :title="$t('launch.attach.link_hint')" @click="openWebForm('url')">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
                          {{ $t('launch.attach.link') }}
                        </button>
                        <button type="button" class="attach-menu-item" role="menuitem" :title="$t('launch.attach.search_hint')" @click="openWebForm('search')">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                          {{ $t('launch.attach.search') }}
                        </button>
                      </div>
                      <!-- Add a web page / search the web: the server reads it and attaches the text -->
                      <form v-else-if="showAttachMenu && webForm" class="attach-menu attach-web" @submit.prevent="submitWebForm">
                        <label class="attach-web-label" for="attach-web-input">
                          {{ webForm === 'url' ? $t('launch.attach.link') : $t('launch.attach.search') }}
                        </label>
                        <input
                          id="attach-web-input"
                          ref="webInputRef"
                          v-model="webInput"
                          class="attach-web-input"
                          :type="webForm === 'url' ? 'url' : 'search'"
                          :placeholder="webForm === 'url' ? $t('launch.attach.link_placeholder') : $t('launch.attach.search_placeholder')"
                          :disabled="isAddingWeb"
                          autocomplete="off"
                          @keydown.esc.prevent="closeWebForm"
                        />
                        <p class="attach-web-note">{{ webForm === 'url' ? $t('launch.attach.link_hint') : $t('launch.attach.search_hint') }}</p>
                        <p v-if="webError" class="attach-web-error" role="alert">{{ webError }}</p>
                        <div class="attach-web-actions">
                          <button type="button" class="attach-web-btn" :disabled="isAddingWeb" @click="closeWebForm">{{ $t('common.cancel') }}</button>
                          <button type="submit" class="attach-web-btn is-primary" :disabled="isAddingWeb || !webInput.trim()">
                            {{ isAddingWeb ? $t('launch.attach.adding') : $t('launch.attach.add') }}
                          </button>
                        </div>
                      </form>
                    </Transition>
                  </div>
                  <input
                    ref="attachmentInputRef"
                    type="file"
                    multiple
                    class="hidden-file-input"
                    @change="onAttachmentSelected"
                  />
                  <input
                    ref="imageInputRef"
                    type="file"
                    accept="image/*"
                    multiple
                    class="hidden-file-input"
                    @change="onAttachmentSelected"
                  />
                  <div class="composer-actions">
                  <!-- Time, steps and token use of the finished turn: a small icon, shown on hover -->
                  <TurnInfo
                    v-if="settledTurn"
                    :headline="settledTurn.headline"
                    :tone="settledTurn.tone"
                    :started-at="settledTurn.startedAt"
                    :ended-at="settledTurn.endedAt"
                    :steps="settledTurn.steps"
                    :usage="settledTurn.usage"
                  />
                  <!-- How much this turn asks before acting (sent with each message) -->
                  <ModePicker v-model="runMode" :run-active="isWorkflowRunning" />
                  <!-- While the team works: Send (a message for the lead) next to Stop -->
                  <button
                    v-if="canInterject"
                    type="button"
                    class="composer-send"
                    :title="$t('launch.interject.send')"
                    :aria-label="$t('launch.interject.send')"
                    @click="sendInterjection"
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                      <line x1="12" y1="19" x2="12" y2="5"></line>
                      <polyline points="5 12 12 5 19 12"></polyline>
                    </svg>
                  </button>
                  <button
                    type="button"
                    class="composer-send"
                    :class="{ glow: shouldGlow && !isStopMode, 'is-stop': isStopMode, 'is-stalled': isStopMode && stallLevel >= 2 }"
                    :title="buttonLabel"
                    :aria-label="buttonLabel"
                    :disabled="isStopping || (!isStopMode && (loading || launchPending || (isWorkflowRunning && !hasComposerContent) || (!isWorkflowRunning && !isRunFinished && !isConnectionReady)))"
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
                </div>
                <div v-if="isDragActive" class="drag-overlay">
                  <div class="drag-overlay-content">{{ $t('launch.drop_files') }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="visitedViews.graph" v-show="viewMode === 'graph'" class="graph-panel graph-flow-panel" :style="insetStyle">
          <div v-if="!graphParts" class="graph-parts-state" :role="graphPartsFailed ? 'alert' : 'status'">
            <template v-if="graphPartsFailed">
              <p>{{ $t('common.lazy.load_failed') }}</p>
              <button type="button" class="graph-tool graph-parts-retry" @click="loadGraphParts">{{ $t('common.retry') }}</button>
            </template>
            <p v-else>{{ $t('common.lazy.loading') }}</p>
          </div>
          <VueFlow v-else class="vueflow-graph">
            <template #node-workflow-node="props">
              <component :is="graphParts.WorkflowNode"
                :id="props.id"
                :data="props.data"
                :is-active="activeNodes.includes(props.id)"
                :sprite="nodeSpriteMap.get(props.id) || ''"
                @hover="onNodeHover"
                @leave="onNodeLeave"
              />
            </template>
            <template #node-start-node="props">
              <component :is="graphParts.StartNode" :id="props.id" :data="props.data" />
            </template>
            <template #edge-workflow-edge="props">
              <component :is="graphParts.WorkflowEdge"
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
            <component :is="graphParts.Background" pattern-color="var(--canvas-dot)"/>
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
            :tracker="trackerFor('office')"
            :visible="viewMode === 'office'"
          />
        </div>

        <div v-if="visitedViews.board" v-show="viewMode === 'board'" class="graph-panel insight-panel" :style="insetStyle">
          <KanbanView
            :graph="officeGraph"
            :sprite-map="nodeSpriteMap"
            :tracker="trackerFor('board')"
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

        <!-- What the team made for this session: browse the files, open them, run the web app -->
        <div v-if="visitedViews.products" v-show="viewMode === 'products'" class="graph-panel insight-panel" :style="insetStyle">
          <ProductsView
            :session-id="activeSessionId || ''"
            :refresh-key="productsRefreshKey"
            :autostart-key="productsAutostart"
            :visible="viewMode === 'products'"
          />
        </div>

        <div v-if="visitedViews.dashboard" v-show="viewMode === 'dashboard'" class="graph-panel insight-panel" :style="insetStyle">
          <DashboardView
            :graph="officeGraph"
            :sprite-map="nodeSpriteMap"
            :tracker="trackerFor('dashboard')"
            :status="status"
            :workflow-name="workflowTitle"
            :sessions="sessions"
            :current-session-id="activeSessionId || ''"
            :visible="viewMode === 'dashboard'"
            @open-session="openSession"
          />
        </div>

      </div>

      <div v-if="isNarrow && isControlSheetOpen" class="sheet-backdrop sheet-backdrop-above-composer" @click="isControlSheetOpen = false"></div>

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
        <LaunchControlPanel
          v-show="isNarrow || isControlsVisible"
          ref="controlPanelRef"
          :show-head="isNarrow || viewMode !== 'chat'"
          :show-grip="isNarrow"
          :visible="isControlsVisible"
          :loading="loading"
          :workflow-files="workflowFiles"
          :selected-file="selectedFile"
          :is-workflow-running="isWorkflowRunning"
          :picker-nudge="pickerNudge"
          :selected-description="selectedDescription"
          :workflow-hint="workflowHint"
          :run-facts="runFacts"
          :started-at="runTracker.state.startedAt"
          :ended-at="runTracker.state.endedAt"
          :team-size="teamSize"
          :team-members="teamMembers"
          :recent-events="recentEvents"
          :is-run-finished="isRunFinished"
          :format-time="formatTime"
          :show-products="!!activeSessionId"
          :products-summary="productsSummary"
          :products-live="productsLive"
          :products-line="productsLine"
          @close="closeControls"
          @select-workflow="selectWorkflow"
          @open-team="selectView('office')"
          @download-logs="downloadLogs"
          @open-products="openProducts"
        />
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
        <button ref="imageModalCloseRef" type="button" class="image-modal-close" :aria-label="$t('launch.close_image')" @click="closeImageModal">
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
    v-if="showSettingsModal || settingsModalSeen"
    :is-visible="showSettingsModal"
    @update:is-visible="showSettingsModal = $event"
  />

  <LocalFolderPicker
    v-if="showFolderPicker || folderPickerSeen"
    :open="showFolderPicker"
    :busy="isOpeningFolder"
    :hint="folderPickerHint"
    @open="onFolderPicked"
    @cancel="cancelFolderPicker"
  />
</template>

<script setup>
import { ref, reactive, shallowRef, computed, onMounted, onUnmounted, watch, nextTick, toRaw } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { checkWorkflowConnections, fetchWorkflowsWithDesc, fetchLogsZip, fetchWorkflowYAML, postFile, getAttachment, fetchVueGraph, saveSessionReview, renameSession, deleteSession, updateSessionWorkflow, cloneProjectIntoSession, openLocalProject, openLocalProjectFile, postWorkflowExecute, sessionOutputsSummary, addWebReference } from '@/api/client.js'
import { lazyPanel } from '@/components/common/lazyPanel.js'
import { WINDOW, openAtLatest, showOlder, showNewer, onLengthChange, revealIndex, sliceWindow, hiddenOlder, hiddenNewer, followTail } from '@/utils/messageWindow.js'
import { collectDroppedItems } from '@/utils/projectFiles.js'
const LocalFolderPicker = lazyPanel(() => import('@/components/launch/LocalFolderPicker.vue'), { overlay: true })
const ProductsView = lazyPanel(() => import('@/components/launch/ProductsView.vue'))
import { formatBytes } from '@/utils/labOutputs.js'
const KanbanView = lazyPanel(() => import('@/components/launch/KanbanView.vue'))
const DashboardView = lazyPanel(() => import('@/components/launch/DashboardView.vue'))
const ReviewView = lazyPanel(() => import('@/components/launch/ReviewView.vue'))
import { createRunTracker, usageTotals, formatCost, stepStatus } from '@/utils/runTracker.js'
import StatusPill from '@/components/launch/StatusPill.vue'
import LiveProgress from '@/components/launch/chat/LiveProgress.vue'
import TurnInfo from '@/components/launch/chat/TurnInfo.vue'
import QuickReplies from '@/components/launch/chat/QuickReplies.vue'
import ModePicker from '@/components/launch/chat/ModePicker.vue'
import { localizeErrorText } from '@/utils/errorTranslate.js'
import { confirmDialog } from '@/utils/confirm'
import { toast } from '@/utils/toast.js'
import { spriteFetcher } from '@/utils/spriteFetcher.js'
import { onWorkflowChanged, workflowKey } from '@/utils/workflowSync.js'
import OfficeView from '@/components/office/OfficeView.vue'
import SessionSidebar from '@/components/launch/SessionSidebar.vue'
import LaunchControlPanel from '@/components/launch/LaunchControlPanel.vue'
import BaseSkeleton from '@/components/ui/BaseSkeleton.vue'
import { computeTeamLinks, layoutOrgTree } from '@/utils/teamLinks.js'
import yaml from 'js-yaml'
import { useMarkdown } from '@/composables/useMarkdown.js'
import { useSessions } from '@/composables/useSessions.js'
import {
  userMessageParts,
  userMessageRole,
  resumedSessionPlan,
  humanInputPrompt,
  artifactFile,
  logAlert,
  infoLogKind,
  memoryStepLabelKey,
  noticeCoalesceKey,
  nodeEndOutcome,
  isCancelRequestLog,
  handoffOf,
  completionNotice,
  errorKind,
  isEchoOfLastReply
} from '@/views/launch/launchEvents.js'
import { buildSocketUrl, createClientId, createIncomingQueue, createReconnector, parseSocketFrame } from '@/composables/useLaunchSocket.js'
import { useLaunchLayout, useChatColumn, CHAT_MIN_W, CHAT_MAX_W, CHAT_DEFAULT_W } from '@/composables/useLaunchLayout.js'
import { readStorage, writeStorage } from '@/views/launch/layoutStorage.js'
const SettingsModal = lazyPanel(() => import('@/components/common/SettingsModal.vue'), { overlay: true })
// Markdown rendering lives in useMarkdown(); it is wired up after useI18n() below

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
import '@vue-flow/core/dist/style.css'
import '@/assets/styles/vueflow.css'
import CollapsibleMessage from '@/components/common/CollapsibleMessage.vue'
// Ticking durations render themselves; the chat list no longer re-renders every second.
import LiveDuration from '@/components/common/LiveDuration.js'
import { localizedWorkflowDescription } from '@/utils/workflowDescription.js'
import { RUN_STATUS, STATUS_LABEL_KEYS, isFinishedStatus } from '@/components/launch/runStatus.js'

const router = useRouter()
const route = useRoute()
const { t, te, locale: i18nLocale } = useI18n()
const { preformatted, renderMarkdown, renderRowMarkdown, handleChatClick } = useMarkdown({ t, locale: i18nLocale })

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
// Actionable hint for well-known backend/provider failures (appended after the raw detail).
// The auth pattern also matches the CLIs' own "invalid api key" wording when the account sign-in expired.
const ERROR_HINTS = [
  [/MAC_ALLOW_UNSAFE_CODE_EXECUTION/, 'launch.error_hints.python_disabled'],
  [/invalid.?api.?key|incorrect api key|api key not valid|authentication.?(error|failed)|unauthorized|\b401\b/i, 'launch.error_hints.auth_rejected'],
  [/rate.?limit|quota|\b429\b/i, 'launch.error_hints.rate_limit'],
  [/model.{0,40}(not found|does not exist)|\b404\b/i, 'launch.error_hints.model_not_found'],
  // A CLI that ran past its limit is a slow answer (often one huge file in a single step), not a network fault.
  [/CLI (timed out|produced no output)/i, 'launch.error_hints.cli_slow'],
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
  // Internal status values (RUN_STATUS, kept in English for logic) -> i18n keys
  const key = STATUS_LABEL_KEYS[statusText]
  return key ? localizeOrRaw(key, statusText) : statusText
}

// Task input state
const taskPrompt = ref('')

// File selector state
const workflowFiles = ref([])
const selectedFile = ref('')

// Status state
const status = ref(RUN_STATUS.NO_WORKFLOW)
const loading = ref(false)

// Session ID for downloads
let sessionIdToDownload = null

// All notifications and dialogues
const chatMessages = ref([])
// Every change to a chat row goes through here. Rows are memoized on `rev` (v-memo in the
// template): a change that does not bump it stays invisible until something else re-renders
// the row. `patch` is an object of fields to set, or a function that mutates the message.
const updateMessage = (message, patch = null) => {
  if (!message) return message
  if (typeof patch === 'function') patch(message)
  else if (patch) Object.assign(message, patch)
  message.rev = (message.rev || 0) + 1
  return message
}
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

// A long session (hundreds of turns, steps and notices) renders only its latest messages: the
// list stays light while events stream in, and older ones come back with one click. The
// window only slides while you are at the bottom, so what you read further up never moves.
const renderWin = ref({ start: 0, end: null })
// A reopened session is rebuilt from its replayed events (often thousands). While that runs the
// list is not rendered at all: no "old chat replaying" on screen, and no re-render per event.
// It appears once, complete, when session_resumed arrives. A backstop timer never leaves it hidden.
const isReplaying = ref(false)
let replayBackstop = null
const setReplaying = (on) => {
  clearTimeout(replayBackstop)
  replayBackstop = on ? setTimeout(() => { isReplaying.value = false }, 20000) : null
  if (isReplaying.value === on) return
  isReplaying.value = on
  // Open at the latest messages, like a session that was followed live
  if (!on) renderWin.value = openAtLatest(chatMessages.value.length)
}
const visibleMessages = computed(() => (isReplaying.value ? [] : sliceWindow(chatMessages.value, renderWin.value)))
const hiddenMessageCount = computed(() => (isReplaying.value ? 0 : hiddenOlder(renderWin.value)))
const hiddenNewerCount = computed(() => (isReplaying.value ? 0 : hiddenNewer(renderWin.value, chatMessages.value.length)))
// A new list (other session, reconnect, new workflow) starts from its top
watch(chatMessages, () => { renderWin.value = { start: 0, end: null } })
watch(
  () => chatMessages.value.length,
  (length) => {
    const next = onLengthChange(renderWin.value, length, isNearBottom)
    if (next.start !== renderWin.value.start || next.end !== renderWin.value.end) renderWin.value = next
  }
)
// Change the window while the message at the top of the viewport stays where it is
// (items are added above it and/or unmounted below it)
const withScrollAnchor = (change) => {
  const el = chatMessagesRef.value
  let key = null
  let offset = 0
  if (el) {
    const top = el.getBoundingClientRect().top
    for (const item of el.querySelectorAll('.chat-message-item')) {
      const rect = item.getBoundingClientRect()
      if (rect.bottom > top) { key = item.dataset.msgKey; offset = rect.top - top; break }
    }
  }
  change()
  nextTick(() => {
    if (!el || key === null) return
    const item = el.querySelector(`.chat-message-item[data-msg-key="${key}"]`)
    if (item) el.scrollTop += item.getBoundingClientRect().top - el.getBoundingClientRect().top - offset
  })
}
const showOlderMessages = () => {
  withScrollAnchor(() => { renderWin.value = showOlder(renderWin.value, chatMessages.value.length) })
}
const showNewerMessages = () => {
  withScrollAnchor(() => { renderWin.value = showNewer(renderWin.value, chatMessages.value.length) })
}

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
  updateMessage(nodeState.message)
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
  updateMessage(nodeState.message)
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
    updateMessage(nodeState.message)
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
  updateMessage(message)
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
    if (interrupted) updateMessage(message, { interrupted: true })
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
  updateMessage(message)
  scheduleScrollToBottom()
  return true
}

// Running steps say what is going on ("Đang suy nghĩ…"), finished ones what was done
const stepLabel = (entry) => (entry.status === 'running' ? entry.label : entry.doneLabel || entry.label)

const toggleStepDetail = (message, entry) => {
  updateMessage(message, () => {
    entry.detailOpen = !entry.detailOpen
  })
}

// A file the turn produced: one card on the bubble that speaks for the turn, however many
// times it is reported (the member makes it, the lead hands the same file over again)
const attachTurnFile = (message, { nodeId, fileName, mimeType, attachmentId, openLocal = false, relativePath = '' }) => {
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
    message.files.push({ fileName, mimeType, attachmentId, openLocal, relativePath, isImage, dataUri: null, loading: false, error: null })
    file = message.files[message.files.length - 1]
    // A member's file also shows up as a step of the lead's work
    if (nodeId && nodeId !== message.name && message.loadingEntries) {
      addTeamStep(message, { label: t('launch.activity.member_file', { member: nodeId, file: fileName }) })
    }
  }
  updateMessage(message)
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
        updateMessage(message)
      })
  }
}

const downloadTurnFile = async (message, file) => {
  const pending = downloadArtifact(file)
  updateMessage(message)
  await pending
  updateMessage(message)
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
// The template asks for these several times per row and per render: computed once per `rev`
// (every change to a row bumps it, see updateMessage)
const stepCache = new WeakMap()
const stepsOf = (message) => {
  const raw = toRaw(message)
  const cached = stepCache.get(raw)
  if (cached && cached.rev === raw.rev && cached.loading === raw.isLoading && cached.open === raw.activityOpen) {
    return cached
  }
  // Read through the reactive message: the rows keep tracking their entries' fields
  const entries = message.loadingEntries || []
  const finished = entries.filter((entry) => entry.status !== 'running')
  const value = {
    rev: raw.rev,
    loading: raw.isLoading,
    open: raw.activityOpen,
    finished,
    shown: !message.isLoading ? entries : message.activityOpen ? finished : finished.slice(-LIVE_STEP_ROWS)
  }
  stepCache.set(raw, value)
  return value
}
const finishedSteps = (message) => stepsOf(message).finished
const shownSteps = (message) => stepsOf(message).shown
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
  updateMessage(message)
  scheduleScrollToBottom()
}

const endMemberStep = (key, found, at) => {
  memberStepKeys.delete(key)
  found.entry.status = 'done'
  found.entry.endedAt = Math.max(at, found.entry.startedAt)
  updateMessage(found.message)
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
  updateMessage(message, (m) => {
    m.activityOpen = !m.activityOpen
  })
}

// Global timer for updating loading bubble durations
// (Running durations live in the small LiveDuration component, which has its own clock: no
// page-wide ticker re-renders this view every second.)
const runningLoadingEntries = ref(0)
const startLoadingTimer = () => {}
const stopLoadingTimer = () => {}

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

// A view hidden by v-show gets the tracker without reactivity: it does not re-render on every
// event of a live run while nobody sees it, and gets the live object back (and refreshes) when shown.
const trackerFor = (mode) => (viewMode.value === mode ? runTracker.state : toRaw(runTracker.state))

// A passed connection pre-check is reused for the next sends of the same workflow: it is redone
// only when the workflow changed (workflowSync), after a failed launch or run, or after
// PRECHECK_TTL_MS (an account may have been disconnected meanwhile).
const PRECHECK_TTL_MS = 5 * 60 * 1000
let precheckPassed = { key: '', at: 0 }
const invalidatePrecheck = () => {
  precheckPassed = { key: '', at: 0 }
}
const precheckIsFresh = (file) =>
  Boolean(file) && precheckPassed.key === workflowKey(file) && Date.now() - precheckPassed.at < PRECHECK_TTL_MS

const handleWorkflowChanged = (detail) => {
  if (detail?.key && workflowKey(detail.key) === precheckPassed.key) invalidatePrecheck()
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
// Modals are separate chunks: mount on first open, then keep (closing animation, state)
const settingsModalSeen = ref(false)
watch(showSettingsModal, (open) => { if (open) settingsModalSeen.value = true })

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
// Node, edge and background components of the graph tab load with the first visit to that tab
const graphParts = shallowRef(null)
const graphPartsFailed = ref(false)
const loadGraphParts = () => {
  graphPartsFailed.value = false
  Promise.all([
    import('@/components/workflow/WorkflowNode.vue'),
    import('@/components/workflow/WorkflowEdge.vue'),
    import('@/components/workflow/StartNode.vue'),
    import('@vue-flow/background')
  ]).then(
    ([node, edge, start, bg]) => {
      graphParts.value = { WorkflowNode: node.default, WorkflowEdge: edge.default, StartNode: start.default, Background: bg.Background }
    },
    () => { graphPartsFailed.value = true }
  )
}
const visitedViews = reactive({ graph: false, board: false, dashboard: false, review: false, products: false })
watch(viewMode, (mode) => {
  if (mode in visitedViews) visitedViews[mode] = true
  if (mode === 'graph' && !graphParts.value) loadGraphParts()
}, { immediate: true })
// Outside the chat the control panel is a drawer over the view: after picking a view, get it
// out of the way (the "Bảng điều khiển" button in the header brings it back).
watch(viewMode, (mode) => {
  if (mode !== 'chat') isRightPanelOpen.value = false
})
// Most used first: talk to the lead, then watch the team, then the work around it
const viewOptions = [
  { mode: 'chat', label: 'launch.chat', icon: ['M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'] },
  { mode: 'products', label: 'launch.products.view', fallback: 'Sản phẩm', icon: ['M21 8 12 3 3 8v8l9 5 9-5z', 'M3 8l9 5 9-5', 'M12 13v8'] },
  { mode: 'office', label: 'launch.office.view', icon: ['M6 3h12a2 2 0 0 1 2 2v16H4V5a2 2 0 0 1 2-2z', 'M9 7h1M14 7h1M9 11h1M14 11h1', 'M10 21v-4h4v4'] },
  { mode: 'board', label: 'launch.board.view', icon: ['M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z', 'M9 3v18M15 3v18'] },
  { mode: 'review', label: 'launch.review.view', icon: ['M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z', 'm9 12 2 2 4-4'] },
  { mode: 'dashboard', label: 'launch.dashboard.view', icon: ['M3 20h18', 'M6 20v-6M11 20V6M16 20v-9M21 20V4'] },
  { mode: 'graph', label: 'launch.graph', icon: ['M3 6a3 3 0 1 0 6 0 3 3 0 1 0-6 0M15 6a3 3 0 1 0 6 0 3 3 0 1 0-6 0M9 18a3 3 0 1 0 6 0 3 3 0 1 0-6 0', 'M9 6h6M7.5 8.6l3 6.8M16.5 8.6l-3 6.8'] }
]
// A tab whose key a locale still lacks shows its Vietnamese fallback
const tabLabel = (option) => (option.fallback && !te(option.label) ? option.fallback : t(option.label))
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
const revealActiveTab = (mode) => {
  nextTick(() => document.getElementById(`view-tab-${mode}`)?.scrollIntoView?.({ inline: 'nearest', block: 'nearest' }))
}
watch(viewMode, revealActiveTab)
// Fade the strip's edges only when it actually scrolls (the fade is the "more tabs" cue)
const viewTabsRef = ref(null)
const viewTabsOverflow = ref(false)
let viewTabsObserver = null
const measureViewTabs = () => {
  const el = viewTabsRef.value
  viewTabsOverflow.value = Boolean(el && el.scrollWidth > el.clientWidth + 1)
}
onMounted(() => {
  revealActiveTab(viewMode.value)
  measureViewTabs()
  if (typeof ResizeObserver === 'function' && viewTabsRef.value) {
    viewTabsObserver = new ResizeObserver(measureViewTabs)
    viewTabsObserver.observe(viewTabsRef.value)
  }
})
onUnmounted(() => viewTabsObserver?.disconnect())
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


// ---------------------------------------------------------------- layout: wide vs narrow
const {
  isNarrow,
  isControlSheetOpen,
  isSessionsDrawerOpen,
  inputAreaRef,
  launchRootRef,
  isStatusColumnOpen,
  isControlsVisible,
  closeControls,
  toggleControls,
  revealControls,
  toggleSessionsPanel
} = useLaunchLayout({
  viewMode,
  isRightPanelOpen,
  showSettingsModal,
  toggleSessionSidebar: () => { isSessionSidebarOpen.value = !isSessionSidebarOpen.value }
})
const onSidebarSelect = (...args) => {
  isSessionsDrawerOpen.value = false
  return openSession(...args)
}
const onSidebarNew = (...args) => {
  isSessionsDrawerOpen.value = false
  return startNewSession(...args)
}

// ---------------------------------------------------------------- status panel
// The control panel component; its workflow picker box is focused from the composer's hint
const controlPanelRef = ref(null)
const workflowPickerRef = computed(() => controlPanelRef.value?.picker || null)
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
  if (value === RUN_STATUS.RUNNING || value === RUN_STATUS.LAUNCHING) return 'running'
  if (value === RUN_STATUS.WAITING_INPUT) return 'warn'
  if (value === RUN_STATUS.COMPLETED) return 'success'
  if (value === RUN_STATUS.ERROR || value === RUN_STATUS.FAILED) return 'danger'
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
  if (missingWorkflow.value && !isWorkflowRunning.value) {
    return t('launch.composer.workflow_missing', { name: missingWorkflow.value.replace(/\.ya?ml$/i, '') })
  }
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
// The chat's mode (manual / plan / auto / bypass): sent with each turn, remembered across visits
const RUN_MODE_KEY = 'agentdev.launch.runMode'
const RUN_MODES = ['manual', 'plan', 'auto', 'bypass']
const runMode = ref(RUN_MODES.includes(readStorage(RUN_MODE_KEY)) ? readStorage(RUN_MODE_KEY) : 'manual')
watch(runMode, (mode) => writeStorage(RUN_MODE_KEY, mode))
// Shift+Tab in the message box steps through the modes (like the mode menu's hint says)
const cycleRunMode = () => {
  runMode.value = RUN_MODES[(RUN_MODES.indexOf(runMode.value) + 1) % RUN_MODES.length]
}
const {
  chatWidth,
  setChatWidth,
  leftPanelRef,
  isResizingChat,
  startChatResize,
  onChatResizeKey,
  chatWidthStyle,
  insetStyle,
  officeInsetStyle
} = useChatColumn({ viewMode, isChatPanelOpen, isChatRailMerged: () => isChatRailMerged.value })

// ---------------------------------------------------------------- control panel content
// (the workflow description folding lives in LaunchControlPanel)
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

// The URL carries the open session (?session=...), so it is the single source of truth
const activeSessionId = computed(() => {
  const value = route.query?.session
  return typeof value === 'string' ? value : ''
})
const {
  sessions,
  sessionsLoaded,
  sessionsLoadFailed,
  hasLiveSession,
  refreshSessions,
  scheduleSessionsRefresh,
  startSessionsPolling,
  stopSessionsPolling
} = useSessions({
  t,
  activeSessionId,
  sessionProject: (item) => sessionProject(item),
  openSession: (item) => openSession(item),
  // Edits made elsewhere (another browser, a teammate) show up when the tab is back
  onVisible: () => { if (isPageReady) scheduleWorkflowRefresh() }
})
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
// Wide screen with the sessions list folded: the chat toggle sits in the sessions rail
const isChatRailMerged = computed(() => !isNarrow.value && !isSessionSidebarOpen.value)
const sessionsDrawerRef = ref(null)
// Rail search: open the list and put the cursor in its search box
const openSessionSearch = async () => {
  isSessionSidebarOpen.value = true
  await nextTick()
  sessionsDrawerRef.value?.querySelector('.session-sidebar input[type="text"]')?.focus()
}

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

// Background sessions (polling, toasts, title badge): see useSessions()

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
// The run is being (or was) stopped, whoever asked: the engine's cancel line or the server's
// confirmation. Steps that end after it were cut short, never "done". Cleared by the next launch.
let cancelRequested = false
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
const isWaitingForInput = computed(() => status.value === RUN_STATUS.WAITING_INPUT)
// A run the server is working on, also while it waits for your answer (it can be stopped then too)
const isRunActive = computed(() =>
  isWorkflowRunning.value && (status.value === RUN_STATUS.RUNNING || status.value === RUN_STATUS.LAUNCHING || isWaitingForInput.value)
)
// While the workflow is working the composer button turns into a Stop button; while it waits
// for your answer it becomes Send again as soon as you type one.
const isStopMode = computed(() => isStopping.value || (isRunActive.value && !(isWaitingForInput.value && hasComposerContent.value)))

// ---------------------------------------------------------------- messages while the team works
// A message typed while the run is going is a note for the lead (not an answer to a question):
// a status question is answered at once from the real progress, anything else is handed to the
// lead, who picks it up before its next model call. Nothing that is running gets interrupted.
const canInterject = computed(() =>
  status.value === RUN_STATUS.RUNNING && isWorkflowRunning.value && !isStopping.value && Boolean(taskPrompt.value.trim())
)
// Notes the lead has not picked up yet: id -> { text, bubble }. Whatever is still here when the
// run ends is sent as a follow-up turn, so nothing the user wrote is lost.
const pendingNotes = new Map()
let noteSeq = 0
const dropNoteBubble = (note) => {
  const index = note?.bubble ? chatMessages.value.indexOf(note.bubble) : -1
  if (index > -1) chatMessages.value.splice(index, 1)
}
const sendInterjection = () => {
  if (!canInterject.value) return
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    toast.warning(t('launch.errors.input_not_sent'))
    return
  }
  const text = taskPrompt.value.trim()
  const id = `note-${Date.now()}-${++noteSeq}`
  try {
    ws.send(JSON.stringify({ type: 'interject', data: { id, text, locale: i18nLocale.value } }))
  } catch (sendError) {
    console.warn('Failed to send note:', sendError)
    toast.warning(t('launch.errors.input_not_sent'))
    return
  }
  pendingNotes.set(id, { text, bubble: addDialogue(USER_SENDER, text) })
  taskPrompt.value = ''
  nextTick(() => {
    autoResizeTaskInput()
    const input = taskInputRef.value
    if (input && !input.disabled) input.focus({ preventScroll: true })
  })
}
// The run ended with notes the lead never picked up: they become the next turn
const flushPendingNotes = () => {
  if (!pendingNotes.size) return
  const notes = [...pendingNotes.values()]
  pendingNotes.clear()
  notes.forEach(dropNoteBubble)
  const text = notes.map((note) => note.text).join('\n\n')
  const draft = taskPrompt.value.trim()
  if (draft) {
    taskPrompt.value = `${text}\n\n${draft}`
    toast.info(t('launch.interject.moved_to_box'))
    return
  }
  taskPrompt.value = text
  nextTick(() => launchWorkflow())
}
// The run failed or was stopped with notes the lead never picked up: they go back into the box
// (not sent on their own: after a stop or an error the user decides what comes next).
const returnPendingNotes = () => {
  if (!pendingNotes.size) return
  const notes = [...pendingNotes.values()]
  pendingNotes.clear()
  notes.forEach(dropNoteBubble)
  const text = notes.map((note) => note.text).join('\n\n')
  const draft = taskPrompt.value.trim()
  taskPrompt.value = draft ? `${text}\n\n${draft}` : text
  toast.info(t('launch.interject.moved_to_box'))
}
// Replayed notes still on screen: a note the lead never took was sent again as the next turn's
// message, so that message replaces its note bubble (instead of showing the text twice).
let replayedNotes = []
// Answer put back in the box when the socket dropped before the server confirmed it.
let unconfirmedAnswer = ''

// A finished run (completed, cancelled or failed) whose composer holds a new message continues
// the same session as a follow-up turn; with an empty composer the button relaunches instead.
const isRunFinished = computed(() => isFinishedStatus(status.value))

// ---------------------------------------------------------------- products ("Sản phẩm")
// What the team wrote for this session (its opened project, else its own folder): a one-line
// summary in the control panel and on the view tab, refreshed when a turn ends or the folder changes.
const trl = (key, fallback, params) =>
  te(key) ? t(key, params) : String(fallback).replace(/\{(\w+)\}/g, (_, k) => params?.[k] ?? '')
const productsSummary = ref(null)
const productsRefreshKey = ref(0)
const productsAutostart = ref(0)
const PREVIEW_LIVE = ['installing', 'starting', 'running']
const productsLive = computed(() => PREVIEW_LIVE.includes(productsSummary.value?.preview?.status))
const productsLine = computed(() => {
  const data = productsSummary.value
  if (!data?.file_count) return ''
  const parts = []
  if (data.project?.type && data.project.type !== 'none') parts.push(data.project.summary)
  parts.push(trl('launch.products.files', '{n} file', { n: data.file_count.toLocaleString(i18nLocale.value) }) + (data.scan_capped ? '+' : ''))
  parts.push(formatBytes(data.total_bytes, i18nLocale.value))
  return parts.join(' · ')
})
let productsToken = 0
const loadProductsSummary = async () => {
  const id = ++productsToken
  const sessionId = activeSessionId.value
  if (!sessionId) {
    productsSummary.value = null
    return
  }
  try {
    const data = await sessionOutputsSummary(sessionId)
    if (id === productsToken) productsSummary.value = data
  } catch {
    if (id === productsToken) productsSummary.value = null
  }
}
const refreshProducts = () => {
  productsRefreshKey.value += 1
  loadProductsSummary()
}
watch(activeSessionId, loadProductsSummary, { immediate: true })
// A turn ended (its files are final) or another folder was opened for the session
watch(isRunFinished, (done) => { if (done) refreshProducts() })
watch(currentProjectName, () => refreshProducts())
// The tab and the panel show whether the app still runs: re-read when the view is left
watch(viewMode, (mode, previous) => { if (previous === 'products') loadProductsSummary() })
const openProducts = (run = false) => {
  if (run) productsAutostart.value += 1
  selectView('products')
}

// ---------------------------------------------------------------- plan approval
// The lead ended its turn with a plan: the run is "done" for the server, but for you it
// waits on your go-ahead. Your next message (approval or changes) opens the next turn.
const isAwaitingPlan = computed(() => Boolean(runTracker.state.plan) && !isWorkflowRunning.value && status.value === RUN_STATUS.COMPLETED)
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
  updateMessage(target, { plan })
  scheduleScrollToBottom()
}
const approvePlan = () => {
  if (!isAwaitingPlan.value || loading.value || isStopping.value) return
  taskPrompt.value = t('launch.plan.approve_message')
  handleButtonClick()
}
// A run that was stopped or failed can be continued: the backend resumes from its saved progress
const canResumeRun = computed(() => {
  if (missingWorkflow.value) return false
  if (loading.value || isStopping.value || isAwaitingPlan.value || !isRunFinished.value) return false
  if ([RUN_STATUS.CANCELLED, RUN_STATUS.ERROR, RUN_STATUS.FAILED].includes(status.value)) return true
  return Boolean(sessions.value.find((s) => s.session_id === activeSessionId.value)?.resumable)
})
const resumeRun = () => {
  if (!canResumeRun.value) return
  taskPrompt.value = t('launch.resume.message')
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

// ---------------------------------------------------------------- live progress line
// Who is working on what right now (most recently active first), read from the run tracker
const liveWorkers = () => {
  const list = []
  for (const [id, node] of Object.entries(runTracker.state.nodes)) {
    const run = node.runs[node.runs.length - 1]
    if (!run || run.endedAt) continue
    let doing
    if (node.waiting) doing = t('launch.live.waiting_answer')
    else if (run.activity?.kind === 'tool') doing = toolActivityLabel(run.activity.name, null)
    else if (run.activity?.kind === 'model') doing = t(isNativeNode(id) ? 'launch.activity.working' : 'launch.activity.thinking')
    else doing = t('launch.activity.working')
    list.push({ id, doing, lastAt: node.lastAt || 0 })
  }
  return list.sort((a, b) => b.lastAt - a.lastAt)
}
const turnStepCount = () => {
  let steps = 0
  for (const node of Object.values(runTracker.state.nodes)) {
    for (const run of node.runs) steps += (run.models || 0) + (run.tools?.length || 0)
  }
  return steps
}
const liveProgress = computed(() => {
  const tracker = runTracker.state
  // The plan card and the question card already say what is going on
  if (isAwaitingPlan.value || isReconnecting.value || !selectedFile.value) return null
  if (isRunActive.value) {
    const workers = isStopping.value ? [] : liveWorkers()
    let headline = t('launch.live.starting')
    if (isStopping.value) headline = t('launch.live.stopping')
    else if (isWaitingForInput.value) headline = t('launch.live.waiting_you')
    return {
      workers,
      headline,
      tone: isStopping.value || isWaitingForInput.value ? 'waiting' : 'running',
      startedAt: tracker.startedAt || 0,
      endedAt: 0,
      steps: turnStepCount(),
      issues: openToolIssueCount.value,
      usage: ''
    }
  }
  if (isRunFinished.value && tracker.outcome && tracker.startedAt && tracker.endedAt) {
    const tone = { completed: 'done', error: 'danger' }[tracker.outcome] || 'muted'
    return {
      workers: [],
      headline: t(`launch.live.finished_${['completed', 'error'].includes(tracker.outcome) ? tracker.outcome : 'cancelled'}`),
      tone,
      startedAt: tracker.startedAt,
      endedAt: tracker.endedAt,
      steps: turnStepCount(),
      issues: 0,
      usage: usageSummary.value
    }
  }
  return null
})
// A running / waiting / failed turn keeps its live line above the box; a finished or stopped one is only a
// fact, so it moves behind the small info icon in the box.
const settledTurn = computed(() => (liveProgress.value && ['done', 'muted'].includes(liveProgress.value.tone) ? liveProgress.value : null))
const liveLineVisible = computed(() => !!liveProgress.value && !settledTurn.value)

// ---------------------------------------------------------------- quick replies
// What makes sense to say next, by state. `act`: done at once (no new text to write);
// `text`: goes into the box to edit and send; `send`: a status question, answered at once
// from the real progress (no model call), so it is sent straight away.
const quickReplies = computed(() => {
  if (!selectedFile.value || !chatMessages.value.length || isReconnecting.value || !isConnectionReady.value) return []
  if (hasComposerContent.value || isStopping.value || loading.value) return []
  if (isAwaitingPlan.value) {
    return [
      { key: 'approve', label: t('launch.plan.approve'), primary: true, hint: t('launch.quick.approve_hint'), act: 'approve' },
      { key: 'changes', label: t('launch.plan.request_changes'), act: 'changes' },
      { key: 'explain_plan', label: t('launch.quick.explain_plan'), text: t('launch.quick.explain_plan_text') },
      { key: 'smaller_plan', label: t('launch.quick.smaller_plan'), text: t('launch.quick.smaller_plan_text') }
    ]
  }
  // The lead's question card is above the box: the answer is yours to write
  if (isWaitingForInput.value) return []
  if (isRunActive.value) {
    if (status.value !== RUN_STATUS.RUNNING || !isWorkflowRunning.value) return []
    return [
      { key: 'progress', label: t('launch.quick.progress'), text: t('launch.quick.progress_text'), send: true, hint: t('launch.quick.progress_hint') },
      { key: 'note', label: t('launch.quick.note'), text: t('launch.quick.note_text') }
    ]
  }
  if ([RUN_STATUS.ERROR, RUN_STATUS.FAILED, RUN_STATUS.CANCELLED].includes(status.value)) {
    // "Continue" lives on the resume banner right above
    // A stopped run did not fail: asking why makes no sense there
    const failed = status.value !== RUN_STATUS.CANCELLED
    return [
      ...(failed ? [{ key: 'why', label: t('launch.quick.why_failed'), text: t('launch.quick.why_failed_text') }] : []),
      { key: 'other_way', label: t('launch.quick.other_way'), text: t('launch.quick.other_way_text') }
    ]
  }
  return []
})
const pickQuickReply = (item) => {
  if (!item || isStopping.value) return
  if (item.act === 'approve') return approvePlan()
  if (item.act === 'changes') return requestPlanChanges()
  if (item.send && canInterjectWith(item.text)) {
    taskPrompt.value = item.text
    sendInterjection()
    return
  }
  if (item.text) pickSuggestion(item.text)
}
// Could a note be sent now (same rule as canInterject, for a text not typed yet)
const canInterjectWith = (text) =>
  status.value === RUN_STATUS.RUNNING && isWorkflowRunning.value && !isStopping.value && Boolean(String(text || '').trim())

// Arrow Up in an empty box brings back your last message to edit (like a terminal or Slack)
const recallLastPrompt = (event) => {
  if (taskPrompt.value || event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) return
  const list = chatMessages.value
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const message = list[i]
    if (message.type !== 'dialogue' || !message.isRight) continue
    const text = userAttachments(message)?.body ?? message.text
    if (!text) return
    event.preventDefault()
    pickSuggestion(text)
    return
  }
}

// Chip icon by kind: project folder, video, audio, archive, any other file
const attachmentIcon = (attachment) => {
  if (attachment.kind === 'project') return '📁'
  if (attachment.kind === 'web') return '🌐'
  if (attachment.kind === 'web_search') return '🔎'
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
  if (isWorkflowRunning.value) {
    return t(leadName.value ? 'launch.interject.placeholder' : 'launch.interject.placeholder_agent', { name: leadName.value })
  }
  if (isRunFinished.value) return t('launch.followup_placeholder')
  return t('launch.enter_prompt')
})

// The question the run is waiting on (the latest one an agent asked), pinned above the composer
// The message holding the open question (set when the run asks; see human_input_required)
const askedMessage = shallowRef(null)
const questionView = (message) => {
  const text = String(message.text || '').trim()
  // Clamped to three lines; longer ones get a "show more"
  const isLong = text.length > 180 || text.split('\n').length > 3
  return { name: getDisplayName(message), text, isLong }
}
const pendingQuestion = computed(() => {
  if (!isWaitingForInput.value) return null
  const list = chatMessages.value
  // A note you sent while the lead worked may sit below its question: the question still counts
  const asked = askedMessage.value
  if (asked?.isQuestion && list.includes(asked)) return questionView(asked)
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const message = list[i]
    if (message.type === 'dialogue' && message.isRight) break
    if (message.isQuestion) return questionView(message)
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
  // A replay that never finished (socket gone) must not keep the chat hidden
  setReplaying(false)
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
    cancelRequested = false
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
    // Loading rows that never finished must not keep the shared timer ticking
    runningLoadingEntries.value = 0
    stopLoadingTimer()
    clearToolIssues()
    // Notes for the lead of the session you leave never become a turn of the next one
    pendingNotes.clear()
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

const imageInputRef = ref(null)
const pickAttachmentImage = () => {
  showAttachMenu.value = false
  if (!isAttachmentUploadAllowed()) return
  imageInputRef.value?.click()
}

// "Add web link" / "Search the web": a small form in the + menu ('' = the menu itself)
const webForm = ref('')
const webInput = ref('')
const webError = ref('')
const isAddingWeb = ref(false)
const webInputRef = ref(null)
const toggleAttachMenu = () => {
  showAttachMenu.value = !showAttachMenu.value
  if (!showAttachMenu.value) closeWebForm()
}
const openWebForm = (mode) => {
  webForm.value = mode
  webInput.value = ''
  webError.value = ''
  nextTick(() => webInputRef.value?.focus())
}
const closeWebForm = () => {
  if (isAddingWeb.value) return
  webForm.value = ''
  webInput.value = ''
  webError.value = ''
  showAttachMenu.value = false
}
const submitWebForm = async () => {
  const value = webInput.value.trim()
  if (!value || isAddingWeb.value) return
  if (!isAttachmentUploadAllowed()) return
  const targetSession = sessionId
  isAddingWeb.value = true
  webError.value = ''
  try {
    const result = await addWebReference(
      targetSession,
      webForm.value === 'url' ? { url: value } : { query: value, language: i18nLocale.value }
    )
    if (targetSession !== sessionId) return // the user moved to another session meanwhile
    if (result?.success && result.attachmentId) {
      uploadedAttachments.value.push(result)
      isAddingWeb.value = false
      closeWebForm()
      nextTick(() => taskInputRef.value?.focus())
    } else {
      webError.value = result?.detail || result?.message || t('errors.api.web_reference_failed')
    }
  } finally {
    isAddingWeb.value = false
  }
}

const handleClickOutside = (event) => {
  if (showAttachMenu.value && attachMenuRef.value && !attachMenuRef.value.contains(event.target)) {
    if (isAddingWeb.value) return // the page is being read: keep the form (and its result) open
    closeWebForm()
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
  if (isRight) renderWin.value = followTail(renderWin.value, chatMessages.value.length)
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
  for (const state of nodesLoadingMessagesMap.values()) updateMessage(state.message)
}

// Add a notification (supports levels)
// `coalesce`: a key for a line that replaces its previous version instead of piling up (e.g. an
// agent's "still thinking" note every few minutes). A warning or error identical to the line
// right before it counts up ("×3") instead of adding a bubble.
const COALESCE_LOOKBACK = 8
const addChatNotification = (message, { type = 'notification', at = null, retryPrompt = '', coalesce = '' } = {}) => {
  const list = chatMessages.value
  if (coalesce) {
    for (let i = list.length - 1; i >= Math.max(0, list.length - COALESCE_LOOKBACK); i -= 1) {
      const item = list[i]
      if (item.coalesce !== coalesce) continue
      updateMessage(item, { message, timestamp: at ?? Date.now() })
      return
    }
  }
  const last = list[list.length - 1]
  if (!retryPrompt && type !== 'notification' && last && last.type === type && last.message === message && !last.retryPrompt) {
    updateMessage(last, { repeat: (last.repeat || 1) + 1, timestamp: at ?? Date.now() })
    return
  }
  list.push({
    type,
    message,
    timestamp: at ?? Date.now(),
    rev: 0,
    ...(retryPrompt ? { retryPrompt } : {}),
    ...(coalesce ? { coalesce } : {})
  })
  scheduleScrollToBottom()
}

// ---------------------------------------------------------------- tool problems, grouped
// A failed tool call is fed back to the agent, which nearly always fixes it on its own (another
// path, another command). One quiet group per agent and step instead of one yellow bubble per
// failure: the same tool + reason counts up, and the group folds away once the agent moves on.
// nodeId -> the open group of that agent's current step
const toolIssueGroups = new Map()
const openToolIssueCount = ref(0)
const TOOL_REASON_MAX = 240
const TOOL_ITEMS_MAX = 20
const recountToolIssues = () => {
  let open = 0
  for (const group of toolIssueGroups.values()) if (!group.recovered) open += 1
  openToolIssueCount.value = open
}
const addToolIssue = (nodeId, toolName, reason, at = null) => {
  const id = nodeId || ''
  const tool = bareToolName(toolName) || String(toolName || '') || t('launch.unknown_name')
  const text = String(reason || '').replace(/\s+/g, ' ').trim()
  const short = text.length > TOOL_REASON_MAX ? `${text.slice(0, TOOL_REASON_MAX - 1)}…` : text
  let group = toolIssueGroups.get(id)
  if (!group) {
    chatMessages.value.push({
      type: 'tool_issues',
      nodeId: id,
      items: [],
      total: 0,
      lastTool: '',
      lastReason: '',
      recovered: false,
      open: false,
      timestamp: at ?? Date.now(),
      rev: 0
    })
    group = chatMessages.value[chatMessages.value.length - 1]
    toolIssueGroups.set(id, group)
    scheduleScrollToBottom()
  }
  const key = `${tool}\u0000${short}`
  const item = group.items.find((entry) => entry.key === key)
  if (item) item.count += 1
  else group.items.push({ key, tool, reason: short, count: 1 })
  if (group.items.length > TOOL_ITEMS_MAX) group.items.splice(0, group.items.length - TOOL_ITEMS_MAX)
  group.total += 1
  group.lastTool = tool
  group.lastReason = short
  group.recovered = false
  group.timestamp = at ?? Date.now()
  updateMessage(group)
  recountToolIssues()
}
// The agent moved on (a tool call worked, or its step ended): the group folds away.
// `close`: the step is over, its next failure starts a new group.
const markToolsRecovered = (nodeId, { close = false } = {}) => {
  const id = nodeId || ''
  const group = toolIssueGroups.get(id)
  if (!group) return
  if (!group.recovered) {
    updateMessage(group, { recovered: true, open: false })
  }
  if (close) toolIssueGroups.delete(id)
  recountToolIssues()
}
const settleAllToolIssues = ({ recovered = true } = {}) => {
  for (const id of [...toolIssueGroups.keys()]) {
    if (recovered) markToolsRecovered(id, { close: true })
    else toolIssueGroups.delete(id)
  }
  recountToolIssues()
}
const clearToolIssues = () => {
  toolIssueGroups.clear()
  openToolIssueCount.value = 0
}
const toggleToolIssues = (message) => {
  updateMessage(message, (m) => {
    m.open = !m.open
  })
}
const toolIssuesHeadline = (message) => {
  const name = message.nodeId || t('launch.unknown_node')
  if (message.recovered) return t('launch.tool_issues.recovered', { name, n: message.total })
  const last = message.lastReason ? `${message.lastTool}: ${message.lastReason}` : message.lastTool
  return message.total > 1
    ? t('launch.tool_issues.open_many', { name, n: message.total, last })
    : t('launch.tool_issues.open_one', { name, last })
}
// From the live progress line: open the oldest problem still unsolved and bring it into view
const revealToolIssues = () => {
  const group = [...toolIssueGroups.values()].find((item) => !item.recovered)
  if (!group) return
  const index = chatMessages.value.indexOf(group)
  if (index > -1) renderWin.value = revealIndex(renderWin.value, chatMessages.value.length, index)
  if (!group.open) toggleToolIssues(group)
  nextTick(() => {
    const el = chatMessagesRef.value?.querySelector(`[data-tool-issues="${CSS.escape(group.nodeId)}"]:not(.is-recovered)`)
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  })
}

// A tool call ended (worked or failed): close its step on the bubble, the office and the board
const handleToolCallEnd = (nodeId, details, eventAt, timestamp) => {
  const toolName = details?.tool_name || ''
  finishLoadingEntry(nodeId, `tool-${toolName || 'unknown'}`, eventAt)
  if (delegatedNodes.has(nodeId)) {
    finishMemberStep(nodeId, toolName, eventAt)
    setMemberNow(nodeId, null, eventAt)
    touchWorkingTurns()
  }
  officeRef.value?.activity(nodeId, 'tool', toolName, false, details?.arguments || null)
  runTracker.activity(nodeId, 'tool', toolName, false, timestamp)
  if (details?.success !== false) markToolsRecovered(nodeId)
}

// Format a millisecond timestamp as mm:ss
const formatDuration = (startedAt, endedAt = null) => {
  if (!startedAt) {
    return ''
  }
  const end = endedAt ?? Date.now()
  const totalSeconds = Math.max(0, Math.floor((end - startedAt) / 1000))
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, '0')
  const seconds = String(totalSeconds % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
}

const isAttachmentUploadAllowed = () => {
  if (!isConnectionReady.value || !sessionId || isUploadingAttachment.value) {
    return false
  }
  if (isWorkflowRunning.value && status.value !== RUN_STATUS.WAITING_INPUT) {
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

  // Every file goes to the session it was picked in; switching sessions stops the rest
  const targetSession = sessionId
  isUploadingAttachment.value = true
  try {
    for (const file of files) {
      if (targetSession !== sessionId) break
      try {
        const result = await postFile(targetSession, file)
        if (targetSession !== sessionId) break

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
const folderPickerSeen = ref(false)
watch(showFolderPicker, (open) => { if (open) folderPickerSeen.value = true })
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
    const targetSession = sessionId
    const result = await openLocalProject(targetSession, path, { yamlFile: selectedFile.value })
    if (targetSession !== sessionId) return // another session was opened meanwhile
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

const isEditableTarget = (target) =>
  Boolean(target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)))
const handleKeydown = (event) => {
  if (event.key === 'Escape' && selectedArtifactImage.value) {
    closeImageModal()
    return
  }
  if (event.defaultPrevented || event.isComposing || selectedArtifactImage.value) return
  // Alt+1..9: the n-th quick reply under the chat (also from inside the message box)
  if (event.altKey && !event.ctrlKey && !event.metaKey && /^Digit[1-9]$/.test(event.code || '')) {
    const item = quickReplies.value[Number(event.code.slice(5)) - 1]
    if (item) {
      event.preventDefault()
      pickQuickReply(item)
    }
    return
  }
  // "/" anywhere outside a field: straight into the message box
  if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !isEditableTarget(event.target)) {
    const input = taskInputRef.value
    if (input && !input.disabled && input.offsetParent !== null) {
      event.preventDefault()
      input.focus()
    }
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
  // Ctrl/Cmd+Enter in an empty box approves the plan that waits for you
  if ((e.ctrlKey || e.metaKey) && isAwaitingPlan.value && !hasComposerContent.value) {
    approvePlan()
    return
  }
  // The team is working: Enter sends the text as a message for the lead
  if (canInterject.value) {
    sendInterjection()
    return
  }
  // Check disabled state logically similar to button
  if (isStopMode.value || loading.value || launchPending.value || (isWorkflowRunning.value && !hasComposerContent.value) || (!isWorkflowRunning.value && !isRunFinished.value && !isConnectionReady.value)) {
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
// Bumped by every selection and session switch: a slow load that is no longer current must not
// put its instructions into another chat or rebind another workflow's sprites
let yamlSelectionSeq = 0
// Name of the selected workflow when its file is gone (deleted or renamed): nothing can run until
// another one is picked, so the box says so instead of letting a send fail on the server
const missingWorkflow = ref('')
const handleYAMLSelection = async (fileName) => {
  const seq = ++yamlSelectionSeq
  missingWorkflow.value = ''
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
    if (seq !== yamlSelectionSeq) return
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
    if (seq !== yamlSelectionSeq) return
    console.error('Failed to load YAML file:', error)
    workflowYaml.value = {}
    if (error?.status === 404) {
      missingWorkflow.value = fileName
      addChatNotification(t('launch.errors.workflow_missing', { name: fileName }), { type: 'error' })
    } else {
      addChatNotification(
        errorWithDetail('launch.errors.load_yaml_failed', error, { name: fileName }),
        { type: 'error' }
      )
    }
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

    status.value = RUN_STATUS.RUNNING
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
  if (code !== 'not_waiting' && status.value === RUN_STATUS.RUNNING && statusBefore === RUN_STATUS.WAITING_INPUT) status.value = statusBefore
}

// The workflow file of a session being opened is fetched while the socket connects
let prefetchedYaml = null
const prefetchWorkflowYaml = (file) => {
  const promise = fetchWorkflowYAML(file)
  promise.catch(() => {})
  prefetchedYaml = { file, promise }
}
const takeWorkflowYaml = (file) => {
  const hit = prefetchedYaml?.file === file ? prefetchedYaml.promise : null
  prefetchedYaml = null
  return hit || fetchWorkflowYAML(file)
}
// Incoming events are collected and applied together once per frame: one reactive pass
// (and one render) for a burst instead of one per event. The order is kept.
const lastEventAt = ref(0)
const stallLevel = ref(0)
// Messages of the socket are handled strictly in order (see onmessage)
const { enqueue: enqueueMessage } = createIncomingQueue({
  isCurrent: (socket) => ws === socket,
  process: (msg) => processMessage(msg),
  onFlush: () => { lastEventAt.value = Date.now() }
})

// Establish a WebSocket connection
// One id per page load plus a counter per socket: the server tells our own overlapping
// sockets (reconnect, draft -> session switch) from a really different tab.
const clientId = createClientId()
let socketSeq = 0
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
    status.value = RUN_STATUS.CONNECTING
  } else {
    resetConnectionState()
    if (!selectedFile.value) {
      return
    }
  }

  socketSeq += 1
  const wsUrl = buildSocketUrl({ sessionId: reconnecting ? reconnectSid : '', clientId, seq: socketSeq })
  const socket = new WebSocket(wsUrl)
  ws = socket

  socket.onopen = () => {
    // Ignore events from stale sockets
    if (ws !== socket) return
  }

  socket.onmessage = (event) => {
    // Ignore messages from sockets that are no longer current
    if (ws !== socket) return

    const frame = parseSocketFrame(event.data)
    if (frame.kind === 'invalid') {
      if (frame.error) console.warn('Ignoring malformed WebSocket message:', frame.error)
      return
    }
    // A replay sent as one frame: handle its messages like single ones, in order
    if (frame.kind === 'batch') {
      for (const inner of frame.messages) enqueueMessage(socket, inner)
      return
    }
    // Another tab took this session: remember it so the close that follows is not
    // mistaken for a dropped connection (which would reconnect and take it back).
    if (frame.kind === 'replaced') {
      socket.__replaced = true
      return
    }
    const { msg } = frame

    if (msg.type === 'connection') {
      sessionId = msg.data?.session_id || null

      if (!sessionId) {
        status.value = RUN_STATUS.CONNECTION_ERROR
        toast.error(t('launch.errors.missing_session'))
        resetConnectionState()
        return
      }

      isConnectionReady.value = true
      // This socket is connected: any "opened in another tab" notice is out of date
      replacedSessionId.value = ''
      reconnector.attempts = 0
      if (reconnector.auto) {
        reconnector.auto = false
        if (msg.data?.resumed) clearReplayedState()
      }
      // The saved events follow, then session_resumed: build the chat off screen meanwhile
      if (msg.data?.resumed) setReplaying(true)

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
        status.value = RUN_STATUS.READY
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
      // In order, one at a time: session_resumed waits for the workflow file, and events that
      // arrive meanwhile (a live run) must not be applied before it, nor be overwritten by it
      enqueueMessage(socket, msg)
    }
  }

  socket.onerror = (error) => {
    // Ignore errors from sockets that are no longer current; onclose always follows and
    // takes care of the state (and of reconnecting)
    if (ws !== socket) return
    console.error('WebSocket error:', error)
    // Retries after a dropped connection stay quiet: the status line already says it
    if (!reconnector.attempts) toast.error(t('launch.errors.ws_connection'))
  }

  socket.onclose = (event) => {
    // Ignore close events from sockets that are no longer current (closed on purpose)
    if (ws !== socket) return

    const lostSession = sessionId
    status.value = RUN_STATUS.DISCONNECTED
    pendingOpenSessionId = null
    // An answer sent just before the drop may never have reached the server: put it back in
    // the box. If the replay after the reconnect shows it was received, the box is cleared again.
    if (pendingInput?.text && !taskPrompt.value.trim()) {
      taskPrompt.value = pendingInput.text
      unconfirmedAnswer = pendingInput.text
    }
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
const reconnector = createReconnector()
const cancelReconnect = () => reconnector.cancel()
const scheduleReconnect = (lostSession) => {
  reconnector.schedule(() => {
    // Something else opened a connection meanwhile (the user switched sessions)
    if (ws || sessionId !== lostSession) return
    const attempts = reconnector.attempts
    establishWebSocketConnection({ sessionId: lostSession })
    reconnector.attempts = attempts
    reconnector.auto = true
  })
}
// The session moved to another tab: take it back here (the newest socket wins on the
// server). Like an automatic reconnect, the chat stays until the server replays it.
const takeOverSession = () => {
  const target = replacedSessionId.value
  if (!target) return
  replacedSessionId.value = ''
  establishWebSocketConnection({ sessionId: target })
  reconnector.auto = true
}

// Set while an automatic reconnect is in flight: the chat is cleared only once the server
// answers (it then replays the whole session), so a failed retry leaves it on screen.
const clearReplayedState = () => {
  locallyCancelled = false
  cancelRequested = false
  endStopping()
  chatMessages.value = []
  replayedNotes = []
  nodesLoadingMessagesMap.clear()
  runningLoadingEntries.value = 0
  stopLoadingTimer()
  clearToolIssues()
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
  // A draft's workflow still loading must not drop its instructions into this session's replay
  yamlSelectionSeq += 1
  pendingProject = null
  // Set before the URL changes so the route watch does not open a draft
  isReconnecting.value = true
  status.value = RUN_STATUS.CONNECTING
  taskPrompt.value = ''
  currentProjectName.value = sessionProject(item)?.name || ''
  if (item.yaml_file) setWorkflowSelection(item.yaml_file)
  // The socket, the workflow file and the URL change all start at once: none waits for another
  if (item.yaml_file) prefetchWorkflowYaml(item.yaml_file)
  establishWebSocketConnection({ sessionId: item.session_id })
  await router.replace({ query: { ...route.query, workflow: item.yaml_file, session: item.session_id } })
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
  status.value = RUN_STATUS.CONNECTING
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
    } else if (source.localPath && result?.status === 404) {
      // The project's folder was moved or deleted: the new session still opens, without it
      currentProjectName.value = ''
      toast.warning(t('launch.sessions.project_folder_missing', { name: source.name }), {
        detail: source.localPath,
        action: {
          label: t('launch.sessions.project_folder_pick'),
          run: () => handleFolderButtonClick()
        }
      })
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
  // force: the open session is gone (deleted), so even a "fresh" one must be replaced
  let force = false
  if (isGroup) {
    project = target.isProject ? target.label : ''
    file = target.isProject ? '' : target.workflow
  } else if (target && typeof target === 'object') {
    project = target.project || ''
    file = target.file || ''
    force = Boolean(target.force)
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
    !force &&
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
  if (['running', 'waiting_for_input', 'cancelling'].includes(item.status)) {
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
    startNewSession({ project: sessionProject(item)?.name || '', file: item.yaml_file, force: true })
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
    startNewSession({ project: '', file: group.workflow || selectedFile.value, force: true })
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
  window.addEventListener('pagehide', onPageHide)
  stopWorkflowSync = onWorkflowChanged(handleWorkflowChanged)
  startSessionsPolling()
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
    status.value = RUN_STATUS.NO_WORKFLOW
  }
  isPageReady = true
})

// Leaving or reloading the page: close the socket right now, so the server releases the
// session before the reloaded page reconnects (a socket left to time out kept the session
// tied to the page that is gone, e.g. while a human gate waits).
const onPageHide = (event) => {
  if (event?.persisted) return // kept in the back/forward cache: the page may come back as is
  const socket = ws
  if (!socket) return
  ws = null // its onclose must not schedule a reconnect
  try {
    socket.close(1000, 'Page closed')
  } catch {
    // already closing
  }
}

onUnmounted(() => {
  stopSessionsPolling()
  clearTimeout(workflowRefreshTimer)
  clearTimeout(stopFallbackTimer)
  stopWorkflowSync?.()
  window.removeEventListener('pagehide', onPageHide)
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

// True from the click until the execute request answered: the checks before the POST await
// (connection pre-check), so without it a double click could post two launches.
const launchPending = ref(false)
const launchWorkflow = async () => {
  if (launchPending.value) return
  launchPending.value = true
  try {
    await launchWorkflowOnce()
  } finally {
    launchPending.value = false
  }
}

const launchWorkflowOnce = async () => {
  if (!selectedFile.value || missingWorkflow.value) {
    toast.warning(t('launch.alert_choose_workflow'))
    focusWorkflowPicker()
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
  // The session this send belongs to. The user may open another one while a request is in
  // flight: from then on nothing here may touch the screen, which shows the other session.
  const launchSid = sessionId
  const switchedAway = () => sessionId !== launchSid

  // Block the run early when a node references a connection that is missing or has no credential.
  // A failed check (e.g. network) must not stop the launch; the runtime still reports the error.
  try {
    const checkedFile = selectedFile.value
    const check = precheckIsFresh(checkedFile)
      ? { ok: true }
      : await checkWorkflowConnections(await fetchWorkflowYAML(checkedFile))
    if (switchedAway()) return
    if (check.ok && !precheckIsFresh(checkedFile)) precheckPassed = { key: workflowKey(checkedFile), at: Date.now() }
    if (!check.ok) {
      toast.error(t('connections.precheck_failed'), {
        items: check.problems.map((problem) => `${problem.nodeId}: ${problem.message}`)
      })
      return
    }
  } catch (error) {
    console.warn('Connection pre-check skipped:', error)
  }
  if (switchedAway()) return

  shouldGlow.value = false
  launchError.value = ''
  // A failed follow-up leaves a finished session as it was (not a draft "waiting for launch")
  const statusBefore = isFinishedStatus(status.value) ? status.value : RUN_STATUS.READY
  // The run is live from the moment it is posted: the server may already stream its first
  // events (a question, an error, even the end) before the POST returns, and those must win
  // over what happens below. This also stops a second launch while this one is in flight.
  status.value = RUN_STATUS.LAUNCHING
  isWorkflowRunning.value = true
  locallyCancelled = false
  cancelRequested = false
  // begin() only replaces top-level fields and appends to events/turns: a shallow copy undoes it
  // (a deep JSON copy of the whole session's tracker cost a lot on long sessions)
  const trackerRaw = toRaw(runTracker.state)
  const trackerBefore = { ...trackerRaw, events: [...trackerRaw.events], turns: [...trackerRaw.turns] }
  const startedBefore = workflowStartedCount
  const rejectedBefore = launchRejectedCount
  runTracker.begin(trimmedPrompt, attachmentNames)
  // Set before the POST: a start failure can arrive over the socket before the POST returns, and
  // its Retry must resend this prompt (not the previous turn's).
  const lastPromptBefore = lastLaunchPrompt
  lastLaunchPrompt = trimmedPrompt
  // A launch that did not happen puts everything back as it was
  const undoLaunch = () => {
    takeBackBubble()
    Object.assign(runTracker.state, trackerBefore)
    isWorkflowRunning.value = false
    lastLaunchPrompt = lastPromptBefore
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
    const response = await postWorkflowExecute({
      yamlFile: selectedFile.value,
      taskPrompt: trimmedPrompt,
      sessionId,
      attachments: attachmentIds,
      mode: runMode.value
    })
    // Opened another session meanwhile: this run goes on (or not) on the server and shows up when
    // the user comes back; the session on screen must not be changed by it.
    if (switchedAway()) return

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
      if (status.value === RUN_STATUS.LAUNCHING && workflowStartedCount === startedBefore) {
        pendingLaunch = { undo: undoRejected }
      }

      // Clear uploaded attachments
      clearUploadedAttachments()

      // Only clear what was sent (not an answer typed meanwhile to an early question)
      if (taskPrompt.value.trim() === trimmedPrompt) taskPrompt.value = ''

      // Events that arrived during the POST (question, error, end) already set the state
      if (status.value === RUN_STATUS.LAUNCHING) status.value = RUN_STATUS.RUNNING
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
      console.warn('Launch rejected, a run is in progress:', response.data)
      undoLaunch()
      status.value = statusBefore
      toast.warning(t('launch.run_in_progress'))
    } else {
      const error = response.data || {}
      console.error('Failed to launch workflow:', error)
      undoLaunch()
      invalidatePrecheck()
      status.value = RUN_STATUS.FAILED
      launchError.value = errorWithDetail('launch.errors.launch_failed', error.detail || error.error?.message || (response.status ? `HTTP ${response.status}` : ''))
      shouldGlow.value = true
      if (isConnectionReady.value) {
        status.value = statusBefore
      }
    }
  } catch (error) {
    console.error('Error calling execute API:', error)
    if (switchedAway()) return
    undoLaunch()
    invalidatePrecheck()
    status.value = RUN_STATUS.ERROR
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
  !missingWorkflow.value &&
  message === chatMessages.value[chatMessages.value.length - 1] &&
  !isWorkflowRunning.value &&
  isRunFinished.value
const retryRun = async (message) => {
  if (!canRetryRun(message) || loading.value || isStopping.value) return
  const draft = taskPrompt.value
  taskPrompt.value = message.retryPrompt
  await launchWorkflow()
  // Sent: the box is empty again. Not sent (pre-check, 409, network): the retry text is still in
  // the box. Either way the user's own draft comes back.
  if (draft.trim() && (!taskPrompt.value.trim() || taskPrompt.value === message.retryPrompt)) taskPrompt.value = draft
  nextTick(() => taskInputRef.value?.focus())
}

// Another session's failed send is not this one's
watch(activeSessionId, () => {
  launchError.value = ''
  lastLaunchPrompt = ''
})

// When workflow is finished or cancelled, re-enable glow
watch(status, (newStatus) => {
  if (newStatus === RUN_STATUS.COMPLETED || newStatus === RUN_STATUS.CANCELLED) {
    shouldGlow.value = true
  }
})

const downloadArtifact = async (message) => {
  if (sessionId && message?.openLocal) {
    // Project opened in place: show the real file on this machine, no copy
    try {
      await openLocalProjectFile(sessionId, message.relativePath || message.fileName)
    } catch (error) {
      toast.error(t('launch.open_file_failed', { error: error?.message || String(error) }))
    }
    return
  }
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

// A handoff: an edge of the workflow really fired (structured event from the engine, see
// the HANDOFF branch of the log handler). The source agent walks over to the target, the
// run tracker records it and a sprite runs along the edge.
const handleHandoff = (sourceNode, targetNode, at) => {
  if (!sourceNode || !targetNode) return
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
    const { text, names } = userMessageParts(msg.data)
    const parts = [text.trim(), names.length ? t('launch.attachments_line', { names: names.join(', ') }) : '']
    for (const note of replayedNotes) {
      if (note.text && text.includes(note.text)) dropNoteBubble(note)
    }
    replayedNotes = []
    // The server did get the answer that was put back in the box when the socket dropped.
    if (unconfirmedAnswer && text.trim() === unconfirmedAnswer.trim()) {
      if (taskPrompt.value.trim() === unconfirmedAnswer.trim()) taskPrompt.value = ''
      unconfirmedAnswer = ''
    }
    addDialogue(USER_SENDER, parts.filter(Boolean).join('\n\n'), at)
    // The task of a new turn, or the answer to a pending question (see userMessageRole)
    if (userMessageRole(runTracker.state) === 'reply') runTracker.inputSent(text, at ?? undefined)
    else {
      runTracker.begin(text, names, at ?? undefined, { closeOpen: true })
      // A replayed new turn: an earlier turn's stop says nothing about this one
      cancelRequested = false
    }
    return
  }

  // A note the user wrote while the team worked (only arrives when a saved session is replayed)
  if (msg.type === 'user_note') {
    const text = (msg.data?.text || '').trim()
    replayedNotes.push({ text, bubble: addDialogue(USER_SENDER, msg.data?.text || '', at) })
    return
  }
  // The lead's answer to such a note: a status report, or "passed to the lead"
  if (msg.type === 'lead_note_reply') {
    const noteId = msg.data?.note_id
    if (msg.data?.kind === 'status') pendingNotes.delete(noteId)
    addDialogue(msg.data?.lead || leadName.value || t('launch.unknown_node'), msg.data?.text || '', at)
    return
  }
  // The lead has the note in its conversation now
  if (msg.type === 'interject_applied') {
    if (pendingNotes.delete(msg.data?.note_id)) {
      addChatNotification(t('launch.interject.applied', { name: msg.data?.node || leadName.value || '' }), at ? { at } : {})
    }
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
      const socketBefore = ws
      missingWorkflow.value = ''
      try {
        const yamlContentString = await takeWorkflowYaml(data.yaml_file)
        // Another session was opened while the file loaded: this answer is no longer ours
        if (ws !== socketBefore) return
        const parsedYaml = yaml.load(yamlContentString)
        workflowYaml.value = parsedYaml || {}
        // Always rebind: the session may belong to another workflow than the last one
        // bound, and its mascots may have been edited since the session started.
        applyWorkflowSprites(parsedYaml?.graph?.nodes, yamlContentString)
      } catch (e) {
        console.error('Failed to load YAML on reconnect:', e)
        if (ws === socketBefore && e?.status === 404) missingWorkflow.value = data.yaml_file
      }
      if (ws !== socketBefore) return
    }

    const plan = resumedSessionPlan(data, { hasOpenTurn: Boolean(runTracker.state.task && !runTracker.state.outcome) })
    isReconnecting.value = false
    setReplaying(false)
    pendingOpenSessionId = null
    currentProjectName.value = stripSlash(data.projects?.[0]?.name)
    hasLaunched.value = plan.hasLaunched
    const composer = takeComposer(sessionId)
    if (composer?.prompt) taskPrompt.value = composer.prompt

    // Restore workflow status (an unknown server status reads as just connected)
    status.value = plan.status

    if (plan.running) {
      isWorkflowRunning.value = true
      if (plan.stopping) startStopping()
    } else {
      // The run this page was following ended while the connection was down (e.g. a server
      // restart): unlock the box instead of still saying the team is at work
      isWorkflowRunning.value = false
      endStopping()
    }
    if (plan.closeOutcome) {
      // The replay never recorded the end of the last turn, but the server is not running it:
      // close it, so the next request starts a turn of its own
      const reason = plan.restarted ? t('launch.sessions.interrupted_restart') : data.error_message
      runTracker.finish(plan.closeOutcome, { error: plan.closeOutcome === 'error' ? formatErrorDetail(reason) : '', settled: true })
      activeNodes.value = []
    }
    // Nothing runs any more: tool problems of the replay no longer count as being handled
    if (plan.settleToolIssues) settleAllToolIssues(plan.settleToolIssues)
    if (plan.settleOpenTurns) {
      // The replay left turns open (the run was cut off, e.g. by a server restart): close them
      // at their last recorded activity rather than letting their timers run on
      const lastAt = (state) => Math.max(state.message.startedAt, ...state.message.loadingEntries.map((e) => e.endedAt || e.startedAt))
      for (const [nodeId, state] of [...nodesLoadingMessagesMap.entries()]) {
        const message = state.message
        settleNodeTurn(nodeId, null, lastAt(state))
        if (plan.markTurnsInterrupted) updateMessage(message, { interrupted: true })
      }
    }

    if (plan.glow) {
      shouldGlow.value = true
    }

    // Reopened draft: put its projects back in the message box, ready for the first prompt
    if (plan.restoreProjects) {
      uploadedAttachments.value = composer?.attachments?.length ? composer.attachments : (data.projects || []).map((project) => ({
        success: true,
        kind: 'project',
        name: `${project.name}/`,
        attachmentId: project.attachment_id,
        fileCount: project.file_count,
        workspacePath: project.workspace_path
      }))
    } else if (plan.restoreComposerAttachments && composer?.attachments?.length) {
      uploadedAttachments.value = composer.attachments
    }

    if (plan.downloadable) {
      sessionIdToDownload = sessionId
    }

    if (plan.activeNode && !activeNodes.value.includes(plan.activeNode)) {
      activeNodes.value.push(plan.activeNode)
    }

    isConnectionReady.value = true
    // The replay is in: open at the latest message, once now and once more after late layout
    // (fonts, tables, images) has settled
    scheduleScrollToBottom(true)
    setTimeout(() => scheduleScrollToBottom(true), 250)
    if (plan.notice === 'interrupted') {
      addChatNotification(t('launch.sessions.interrupted_notice'), { type: 'warning' })
    } else if (plan.notice === 'reconnected') {
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
    const { lastAgentBubble, repeatsLast, fullMessage } = humanInputPrompt(chatMessages.value, msg.data, localizeInputHeaders)
    // The question closes the agent's current activity row and becomes its message;
    // work after the user's answer starts a fresh row below it.
    const askingNode = msg.data?.node_id
    // Without a server time it follows the agent's last logged event (right for replays too)
    const askedAt = at || lastLogAt || Date.now()
    let question = null
    askedMessage.value = null
    if (repeatsLast && !fullMessage) {
      // Nothing new to say: the reply on screen is the question
      settleNodeTurn(askingNode, null, askedAt)
      question = lastAgentBubble
    } else {
      // The asker's own bubble (a note you sent meanwhile may sit below it): the question goes there
      const askingBubble = askingNode ? nodesLoadingMessagesMap.get(askingNode)?.message || null : null
      if (settleNodeTurn(askingNode, fullMessage || t('launch.input_required'), askedAt)) {
        question = askingBubble
      } else {
        question = addDialogue(askingNode || t('launch.unknown_node'), fullMessage || t('launch.input_required'), at) || null
      }
    }
    // Shown as the lead's question, waiting for your answer
    if (question?.type === 'dialogue' && !question.isRight) {
      updateMessage(question, { isQuestion: true })
      askedMessage.value = question
    }
    // Ready to answer: the box takes the focus unless you are typing somewhere else
    nextTick(() => {
      const active = document.activeElement
      if (!active || active === document.body) taskInputRef.value?.focus()
    })
    officeRef.value?.waitingInput(msg.data?.node_id, msg.data?.task_description || msg.data?.input)
    runTracker.waitingInput(msg.data?.node_id)

    status.value = RUN_STATUS.WAITING_INPUT
    shouldGlow.value = true
  }

  // Handle artifact messages (file/image output)
  if (msg.type === 'artifact_created') {
    const events = msg?.data?.events
    if (Array.isArray(events)) {
      for (const event of events) {
        const { nodeName, fileName, mimeType, attachmentId, openLocal, relativePath, isImage } = artifactFile(event, t('launch.artifact_sender'))

        // The turn's agent bubble (the lead's, for a member's file) shows it once, under its answer
        const turnBubble = findTurnBubble(event?.node_id)
        if (turnBubble) {
          attachTurnFile(turnBubble, { nodeId: event?.node_id, fileName, mimeType, attachmentId, openLocal, relativePath })
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
          openLocal,
          relativePath,
          isImage,
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

  const alert = logAlert(msg)
  // Account ran out of quota: say plainly which account took over (or that none is left)
  if (alert?.kind === 'account') {
    const key = alert.event === 'account_fallback' ? 'launch.account_fallback' : 'launch.account_exhausted'
    addChatNotification(t(key, alert.params), { type: alert.level, at })
    // A replayed session shows past switches in the chat only, not as if they happened now
    if (!isReconnecting.value) toast[alert.level](t(key, alert.params))
  }

  // Handle warning/error messages
  else if (alert) {
    // A failed tool call is fed back to the agent, which retries on its own: show it as a
    // warning with the real reason instead of the bare "Tool call X for node Y" line.
    if (alert.kind === 'tool_failure') {
      // Grouped per agent and step (see addToolIssue); the failed call's step also ends here,
      // or its spinner would run on until the whole turn settles
      const details = msg.data.details || {}
      addToolIssue(
        msg.data.node_id,
        details.tool_name,
        formatErrorDetail(details.error || details.tool_result || msg.data.message),
        at
      )
      if (details.stage !== 'before' && msg.data.node_id) {
        handleToolCallEnd(msg.data.node_id, { ...details, success: false }, eventTime(msg.data.timestamp), msg.data.timestamp)
      }
    } else {
      const notificationType = alert.level
      // Backend warning/error text is technical English; give it a localized lead-in
      const detail = formatErrorDetail(msg.data.message)
      const fallbackKey = notificationType === 'warning' ? 'launch.unknown_warning' : 'launch.unknown_error'
      addChatNotification(
        detail ? withErrorHint(t(`launch.log_events.backend_${notificationType}`, { detail })) : t(fallbackKey),
        { type: notificationType, at }
      )
    }
  }

  // Handle log messages
  if (msg.type === 'log' && msg.data.level === 'INFO') {
    const eventType = msg.data.event_type
    const nodeId = msg.data.node_id

    const delegatedBy = msg.data.details?.delegated_by
    const eventAt = eventTime(msg.data.timestamp)
    if (isCancelRequestLog(msg.data)) cancelRequested = true
    const kind = infoLogKind(msg.data, { setupLogRe: SETUP_LOG_RE, logEventKeys: LOG_EVENT_KEYS, turnHasAgentBubble })

    // Node active
    if (kind === 'node_start') {
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
    else if (kind === 'model_call') {
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
    else if (kind === 'tool_call') {
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

      // Tool call ended (a failure the agent handles itself is an INFO entry with success: false)
      if (msg.data.details.stage === "after") {
        handleToolCallEnd(nodeId, msg.data.details, eventAt, msg.data.timestamp)
      }
    }

    // Node ended (with output)
    else if (kind === 'node_end') {
      if (nodeId) {
        // Remove from active node list
        const index = activeNodes.value.indexOf(nodeId)
        if (index > -1) {
          activeNodes.value.splice(index, 1)
        }

      }

      // A member cut short by Stop ends with nothing to hand over: it did not report anything
      const details = msg.data.details || {}
      const { memberReported, endStatus } = nodeEndOutcome(details, { delegatedBy, stopping: isStopping.value || locallyCancelled || cancelRequested })
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
        // A step that just forwards the reply already shown (e.g. a passthrough end node) adds no bubble
        const forwarded = buildDialogueContent(msg.data.details?.output)?.text
        if (!isEchoOfLastReply(chatMessages.value, forwarded, { userSender: USER_SENDER })) {
          addDialogue(nodeId || t('launch.unknown_node'), msg.data.details?.output, at)
        }
      }
      // The step is over: its tool problems were handled (or no longer matter)
      if (nodeId) markToolsRecovered(nodeId, { close: true })
      if (nodeId) officeRef.value?.nodeEnd(nodeId, msg.data.details?.output)
      // An optional step (continue_on_error) that failed ends with failed: true: it is not done (nodeEndOutcome)
      runTracker.nodeEnd(nodeId, msg.data.details?.output, msg.data.timestamp, { status: endStatus })
    }

    // An edge fired: details {from, to}. Built only from this structured event: "Edge condition
    // met" lines also come for edges with trigger: false, which hand nothing over.
    else if (kind === 'handoff') {
      const { from, to, timestamp } = handoffOf(msg)
      handleHandoff(from, to, timestamp)
    }

    // Nothing to add (see infoLogKind): "Edge condition met for A -> B" (only that a condition
    // held), "Received your input for CTO" (your own bubble says it), run started / finished
    // (the turn's bubble shows it working and done), set-up chatter
    else if (kind === 'quiet') {
      // nothing to add
    }

    // An agent looked up / saved memory or reflected: a step of its own turn, not a chat line
    // (a member's goes nowhere: its lead's block lists what it did)
    else if (kind === 'memory') {
      if (nodeId && !delegatedNodes.has(nodeId)) {
        const label = t(memoryStepLabelKey(eventType, msg.data.details))
        const baseKey = `note-${eventType}`
        addLoadingEntry(nodeId, baseKey, label, { at: eventAt, doneLabel: label })
        finishLoadingEntry(nodeId, baseKey, eventAt)
      } else if (!nodeId) {
        addChatNotification(localizeLogMessage(msg.data), { at })
      }
    }

    // Only logs the UI knows how to say reach the chat: a mapped event type (localized) or a tagged event such as
    // "still thinking". Any other INFO line is the engine's own English bookkeeping ("Cancellation requested for
    // workflow session_...", "Executing node X with edge dynamic config ...") and stays in the downloadable log.
    else if (kind === 'notice') {
      // "Still thinking (N+ min)" comes back every few minutes: one line per agent, kept current
      const coalesce = noticeCoalesceKey(msg.data)
      addChatNotification(localizeLogMessage(msg.data), { at, coalesce })
    }
  }

  // The lead ended its turn with a plan that waits for your approval (replayed on reload)
  // The same handoff as a top-level event: {type: 'handoff', data: {from, to, timestamp}}
  if (msg.type === 'handoff') {
    const { from, to, timestamp } = handoffOf(msg)
    handleHandoff(from, to, timestamp)
    return
  }

  if (msg.type === 'plan_proposed') {
    showProposedPlan(msg.data || {})
    scheduleSessionsRefresh()
    return
  }

  // Workflow completed
  if (msg.type === 'workflow_completed') {
    // The backend summary ("Workflow finished with N node outputs...") is technical and the
    // WORKFLOW_END log line already said the run is over: only say it when nothing did.
    // A turn that ended with a plan waiting for approval: "finished" would mislead
    const notice = completionNotice({
      lastMessage: chatMessages.value[chatMessages.value.length - 1],
      endLine: t('launch.log_events.workflow_end'),
      hasPlan: Boolean(runTracker.state.plan),
      turnHasAgentBubble
    })
    if (notice.dropEndLine) chatMessages.value.pop()
    else if (notice.addCompleted) addChatNotification(t('launch.workflow_completed'), { at })
    runTracker.finish('completed', { summary: formatErrorDetail(msg.data?.summary), tokenUsage: msg.data?.token_usage })
    settleAllNodeTurns({ at: at || Date.now() })
    // The run got to its end: every tool problem on the way was dealt with
    settleAllToolIssues()
    status.value = RUN_STATUS.COMPLETED
    isWorkflowRunning.value = false
    sessionIdToDownload = sessionId
    endStopping()
    pendingLaunch = null
    // Notes the lead never got to see become the next turn (not while replaying a saved session)
    if (!isReconnecting.value) flushPendingNotes()
    else pendingNotes.clear()
  }

  // The server has the answer that was sent (also acknowledges a cancel request)
  // A question nobody answered in time: the server moved the run on, so close it here too
  // The turn's mode answered a question for the user: say so, so nothing is decided silently
  if (msg.type === 'auto_answered') {
    const node = msg.data?.node_id || ''
    addChatNotification(t('launch.mode.auto_answered', { node }), { type: 'notification', at })
    return
  }

  if (msg.type === 'human_input_timeout') {
    for (const item of chatMessages.value) {
      if (item.isQuestion) updateMessage(item, { isQuestion: false })
    }
    runTracker.inputTimedOut(msg.data?.node_id)
    if (status.value === RUN_STATUS.WAITING_INPUT) status.value = RUN_STATUS.RUNNING
    shouldGlow.value = false
    addChatNotification(t('launch.human_input_timeout'), { type: 'warning', at })
    return
  }

  if (msg.type === 'input_received') {
    if (msg.data?.message !== 'Cancellation requested') confirmPendingInput()
    return
  }

  // Workflow cancelled: from the server, or the confirmation that Stop really stopped it
  if (msg.type === 'workflow_cancelled') {
    // Always our own wording: the server's reason is English bookkeeping ("User requested cancellation")
    const message = t('launch.workflow_cancelled')
    markRunCancelled(message, { at, summary: formatErrorDetail(msg.data?.message) })
  }

  // Handle direct error messages (e.g., workflow execution errors)
  const failure = msg.type === 'error' ? errorKind(msg.data) : null
  if (failure === 'run_in_progress') {
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
  if (failure === 'note_not_running') {
    // The run ended just before the note arrived: take the note back into the box
    const note = pendingNotes.get(msg.data.note_id)
    pendingNotes.delete(msg.data.note_id)
    if (note) {
      dropNoteBubble(note)
      if (!taskPrompt.value.trim()) taskPrompt.value = note.text
    }
    return
  }
  if (failure === 'rejected') {
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
  if (failure === 'fatal') {
    const errorMessage = withErrorHint(errorWithDetail('launch.errors.workflow_error', msg.data?.message))
    // Live failures of a turn sent from this page can be retried in place
    const retryPrompt = !isReconnecting.value ? lastLaunchPrompt : ''
    addChatNotification(errorMessage, { type: 'error', at, retryPrompt })
    runTracker.finish('error', { error: formatErrorDetail(msg.data?.message) })
    settleAllNodeTurns({ at: at || Date.now(), interrupted: true })
    invalidatePrecheck()
    status.value = RUN_STATUS.ERROR
    isWorkflowRunning.value = false
    sessionIdToDownload = sessionId
    endStopping()
    pendingInput = null
    pendingLaunch = null
    if (isReconnecting.value) pendingNotes.clear()
    else returnPendingNotes()
    // The problems the run died with stay readable; the next turn starts its own groups
    settleAllToolIssues({ recovered: false })
  }
}

// The "Stopping…" line of the stop in progress (replaced by the final notice)
let stoppingNotice = null
// The run is over after a stop: notice, run record, status, and the open activity rows
const markRunCancelled = (message, { at = null, summary = '' } = {}) => {
  cancelRequested = true
  endStopping()
  locallyCancelled = false
  pendingInput = null
  pendingLaunch = null
  if (isReconnecting.value) pendingNotes.clear()
  else returnPendingNotes()
  settleAllToolIssues({ recovered: false })
  // The "Stopping…" line of this stop becomes the final notice (never left behind, never reused later)
  const stopping = stoppingNotice
  stoppingNotice = null
  if (message && stopping && chatMessages.value.includes(stopping)) {
    updateMessage(stopping, { message, timestamp: at ?? Date.now() })
  } else if (message) {
    addChatNotification(message, at ? { at } : {})
  }
  if (runTracker.state.task && !runTracker.state.outcome) runTracker.finish('cancelled', { summary })
  status.value = RUN_STATUS.CANCELLED
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
  // Same line as the final 'cancelled' notice: it is replaced, not left behind as a stale "Đang dừng…"
  addChatNotification(t('launch.stopping'))
  const last = chatMessages.value[chatMessages.value.length - 1]
  stoppingNotice = last?.type === 'notification' ? last : null
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
  if (renderWin.value.end !== null) renderWin.value = openAtLatest(chatMessages.value.length)
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

<style scoped src="./launch/styles/rails-header.css"></style>
<style scoped src="./launch/styles/messages.css"></style>
<style scoped src="./launch/styles/activity.css"></style>
<style scoped src="./launch/styles/composer.css"></style>
<style scoped src="./launch/styles/views.css"></style>
<style scoped src="./launch/styles/shell.css"></style>
<style scoped src="./launch/styles/narrow.css"></style>
<style scoped src="./launch/styles/light-theme.css"></style>
