<template>
  <div class="lab-view page">
    <!-- ================================================================ header -->
    <header class="hero">
      <div class="hero-text">
        <h1 class="hero-title">{{ $t('lab.title') }}</h1>
        <p class="hero-sub">{{ $t('lab.subtitle') }}</p>
      </div>
      <router-link to="/batch-run" target="_blank" rel="noopener" class="btn">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M9 21V9" /></svg>
        {{ $t('lab.batch_link').replace(/\s*→\s*$/, '') }}
        <svg class="ext" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17 17 7M8 7h9v9" /></svg>
      </router-link>
    </header>

    <!-- ================================================================ control bar -->
    <section class="control card">
      <BaseSelect
        id="lab-workflow-picker"
        v-model="workflow"
        class="picker-field"
        :label="$t('lab.workflow_label')"
        :disabled="isRunning || starting || generating || loadingWorkflows"
      >
        <template #icon>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="6" height="6" rx="1.5" /><rect x="15" y="14" width="6" height="6" rx="1.5" /><path d="M9 7h3a3 3 0 0 1 3 3v4" /></svg>
        </template>
        <option value="" disabled>{{ loadingWorkflows ? $t('lab.workflows_loading') : listError ? tr('lab.workflows_load_failed', 'Không tải được danh sách quy trình') : $t('lab.workflow_placeholder') }}</option>
        <option v-for="wf in workflows" :key="wf.name" :value="wf.name">{{ wf.name.replace(/.ya?ml$/, '') }}</option>
      </BaseSelect>

      <dl v-if="workflow" class="metrics">
        <div class="metric">
          <dt>{{ tr('lab.summary.config', 'Cấu hình') }}</dt>
          <dd>
            <span v-if="checking" class="muted">{{ $t('lab.checking') }}</span>
            <span v-else-if="health" :class="['health-tag', health]">
              <span class="dot" aria-hidden="true"></span>
              {{ $t(`lab.health.${health}`) }}
            </span>
            <span v-else class="muted">—</span>
          </dd>
        </div>
        <div class="metric">
          <dt>{{ tr('lab.summary.scenarios', 'Kịch bản') }}</dt>
          <dd>{{ filledScenarios }}<span class="unit">/{{ scenarios.length }}</span></dd>
        </div>
        <div class="metric">
          <dt>{{ tr('lab.summary.runs', 'Lượt chạy') }}</dt>
          <dd>{{ plannedRuns }}<span class="unit"> × {{ repeats }}</span></dd>
        </div>
        <div class="metric">
          <dt>{{ tr('lab.summary.last', 'Tỷ lệ đạt') }}</dt>
          <dd>
            <span v-if="passPct !== null" :class="['rate', job.verdict]">{{ passPct }}%</span>
            <span v-else-if="isRunning" class="muted">{{ progressPct }}%</span>
            <span v-else class="muted">—</span>
          </dd>
        </div>
      </dl>
    </section>

    <!-- ================================================================ empty state -->
    <section v-if="!workflow" class="intro card" :aria-label="tr('lab.how_it_works', 'Cách kiểm định')">
      <div v-if="!loadingWorkflows && !workflows.length && !listError" class="empty-state intro-empty">
        <strong>{{ $t('lab.no_workflows_title') }}</strong>
        <p>{{ $t('lab.no_workflows_hint') }}</p>
        <router-link to="/workflows" class="btn primary sm">{{ $t('lab.no_workflows_cta') }}</router-link>
      </div>
      <div v-if="listError" class="intro-error" role="alert">
        <p class="error">
          <strong>{{ tr('lab.workflows_load_failed', 'Không tải được danh sách quy trình') }}</strong>
          <span class="intro-error-detail">{{ listError }}</span>
        </p>
        <button type="button" class="btn secondary sm" :disabled="loadingWorkflows" @click="loadWorkflows">{{ $t('common.retry') }}</button>
      </div>
      <div class="intro-head">
        <p class="intro-cta">{{ tr('lab.empty_cta', 'Chọn một quy trình ở trên để bắt đầu.') }}</p>
        <h2 class="intro-heading">{{ tr('lab.how_it_works', 'Cách kiểm định') }}</h2>
      </div>
      <ol class="intro-steps">
        <li class="intro-step">
          <span class="icon-tile sky" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6l-8-3Z" /><path d="m9 12 2 2 4-4" /></svg>
          </span>
          <div>
            <p class="step-label">{{ tr('lab.step', 'Bước {n}', { n: 1 }) }}</p>
            <h3 class="intro-title">{{ stripNo($t('lab.check_title')) }}</h3>
            <p class="intro-desc">{{ $t('lab.check_hint') }}</p>
          </div>
        </li>
        <li class="intro-step">
          <span class="icon-tile indigo" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6M10 3v6L4.5 18.5A2 2 0 0 0 6.2 21.5h11.6a2 2 0 0 0 1.7-3L14 9V3" /><path d="M7 15h10" /></svg>
          </span>
          <div>
            <p class="step-label">{{ tr('lab.step', 'Bước {n}', { n: 2 }) }}</p>
            <h3 class="intro-title">{{ stripNo($t('lab.eval_title')) }}</h3>
            <p class="intro-desc">{{ $t('lab.eval_hint') }}</p>
          </div>
        </li>
      </ol>
    </section>

    <!-- ================================================================ workspace -->
    <div v-else class="workspace">
      <!-- Config health (sticky side panel) -->
      <aside class="side-col">
        <section class="card panel health-panel">
          <header class="panel-head compact">
            <span class="icon-tile sky" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6l-8-3Z" /><path d="m9 12 2 2 4-4" /></svg>
            </span>
            <div class="panel-text">
              <p class="step-label">{{ tr('lab.step', 'Bước {n}', { n: 1 }) }}</p>
              <h2 class="panel-title">{{ stripNo($t('lab.check_title')) }}</h2>
            </div>
            <button
              type="button"
              class="btn ghost sm icon-only"
              :title="$t('lab.check_run')"
              :aria-label="$t('lab.check_run')"
              :disabled="checking"
              @click="runCheck"
            >
              <span v-if="checking" class="btn-spinner" aria-hidden="true"></span>
              <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.6-6.4L21 8" /><path d="M21 3v5h-5" /></svg>
            </button>
          </header>
          <p class="panel-hint">{{ $t('lab.check_hint') }}</p>

          <p v-if="checkError" class="error" role="alert">{{ checkError }}</p>

          <template v-if="report">
            <div class="meter" role="img" :aria-label="`${checkCounts.pass} ${$t('lab.status.pass')}, ${checkCounts.warn} ${$t('lab.status.warn')}, ${checkCounts.fail} ${$t('lab.status.fail')}`">
              <span v-for="s in ['pass', 'warn', 'fail']" v-show="checkCounts[s]" :key="s" :class="['seg', s]" :style="{ flexGrow: checkCounts[s] }"></span>
            </div>
            <div class="chips">
              <span v-for="s in ['pass', 'warn', 'fail']" v-show="checkCounts[s]" :key="s" :class="['chip', s]">
                <span class="chip-count">{{ checkCounts[s] }}</span>
                {{ $t(`lab.status.${s}`) }}
              </span>
              <span class="chip-total">/ {{ checkTotal }}</span>
            </div>
            <ul class="check-list">
              <li v-for="item in report.checks" :key="item.id" :class="['check-item', item.status]">
                <span class="status-icon" role="img" :aria-label="$t(`lab.status.${item.status}`)">
                  <svg v-if="item.status === 'pass'" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 5 5 9-10" /></svg>
                  <svg v-else-if="item.status === 'warn'" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M12 7v6M12 17h.01" /></svg>
                  <svg v-else viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M7 7l10 10M17 7 7 17" /></svg>
                </span>
                <div class="check-text">
                  <span class="check-name">{{ $t(`lab.checks.${item.id}.title`) }}</span>
                  <span v-if="item.status !== 'pass'" class="check-detail">
                    {{ $t(`lab.checks.${item.id}.problem`) }}
                    <code v-if="item.detail">{{ item.detail }}</code>
                  </span>
                </div>
              </li>
            </ul>
          </template>
          <div v-else-if="checking" class="skel-list" aria-hidden="true">
            <span v-for="n in 5" :key="n"></span>
          </div>
        </section>
      </aside>

      <div class="main-col">
        <!-- Scenarios -->
        <section class="card panel">
          <header class="panel-head">
            <span class="icon-tile indigo" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6M10 3v6L4.5 18.5A2 2 0 0 0 6.2 21.5h11.6a2 2 0 0 0 1.7-3L14 9V3" /><path d="M7 15h10" /></svg>
            </span>
            <div class="panel-text">
              <p class="step-label">{{ tr('lab.step', 'Bước {n}', { n: 2 }) }}</p>
              <h2 class="panel-title">{{ stripNo($t('lab.eval_title')) }}</h2>
              <p class="panel-hint">{{ $t('lab.eval_hint') }}</p>
            </div>
          </header>

          <ol class="scenario-list">
            <li v-for="(sc, index) in scenarios" :key="sc.key" class="scenario">
              <div class="scenario-head">
                <span class="scenario-no" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
                <span class="name-wrap">
                  <input
                    v-model="sc.name"
                    class="scenario-name"
                    :aria-label="$t('lab.scenario_name', { n: index + 1 })"
                    :placeholder="$t('lab.scenario_name', { n: index + 1 })"
                    :disabled="isRunning"
                  />
                  <svg v-if="!isRunning" class="name-pencil" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4ZM14 6l4 4" /></svg>
                </span>
                <span v-if="!sc.prompt.trim()" class="skip-tag">{{ $t('lab.scenario_skipped') }}</span>
                <button
                  v-if="scenarios.length > 1"
                  type="button"
                  class="btn ghost sm icon-only icon-danger"
                  :title="$t('lab.remove')"
                  :aria-label="`${$t('lab.remove')} ${sc.name || $t('lab.scenario_name', { n: index + 1 })}`"
                  :disabled="isRunning"
                  @click="removeScenario(index)"
                >
                  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></svg>
                </button>
              </div>
              <div class="scenario-fields">
                <label class="field">
                  <span class="field-label">{{ $t('lab.prompt_label') }}</span>
                  <textarea v-model="sc.prompt" class="input" rows="3" :placeholder="$t('lab.prompt_placeholder')" :disabled="isRunning"></textarea>
                </label>
                <label class="field">
                  <span class="field-label">{{ $t('lab.criteria_label') }}</span>
                  <textarea v-model="sc.criteria" class="input" rows="3" :placeholder="$t('lab.criteria_placeholder')" :disabled="isRunning"></textarea>
                </label>
              </div>
            </li>
          </ol>

          <div class="scenario-tools">
            <button type="button" class="btn secondary sm" :disabled="isRunning || scenarios.length >= 20" @click="addScenario()">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
              {{ $t('lab.add_scenario') }}
            </button>
            <div ref="sampleMenuEl" class="sample-menu" @keydown.esc="closeSampleMenu(true)" @focusout="onSampleFocusOut">
              <button
                ref="sampleBtnEl"
                type="button"
                class="btn secondary sm"
                aria-haspopup="menu"
                :aria-expanded="sampleMenuOpen"
                :disabled="isRunning || scenarios.length >= MAX_SCENARIOS"
                @click="toggleSampleMenu"
                @keydown.down.prevent="openSampleMenu"
              >
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m12 3 1.9 4.6L18.5 9l-4.6 1.9L12 15.5l-1.9-4.6L5.5 9l4.6-1.4L12 3ZM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" /></svg>
                {{ $t('lab.add_samples') }}
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
              </button>
              <ul
                v-if="sampleMenuOpen"
                ref="sampleListEl"
                class="sample-menu-list"
                role="menu"
                :aria-label="$t('lab.packs.menu.menu_label')"
                @keydown.down.prevent="moveSampleFocus(1)"
                @keydown.up.prevent="moveSampleFocus(-1)"
                @keydown.home.prevent="moveSampleFocus(0, true)"
                @keydown.end.prevent="moveSampleFocus(-1, true)"
              >
                <li role="none">
                  <button type="button" role="menuitem" class="sample-menu-item strong" @click="addSamplePack('auto')">
                    {{ $t('lab.packs.menu.auto') }} <small>({{ $t(`lab.packs.${detectedPack}.title`) }})</small>
                  </button>
                </li>
                <li v-for="id in PACK_IDS.filter((p) => p !== 'general')" :key="id" role="none">
                  <button type="button" role="menuitem" class="sample-menu-item" @click="addSamplePack(id)">
                    {{ $t(`lab.packs.${id}.title`) }}
                  </button>
                </li>
                <li role="none">
                  <button type="button" role="menuitem" class="sample-menu-item" @click="addSamplePack('general')">
                    {{ $t('lab.packs.menu.all_general') }}
                  </button>
                </li>
              </ul>
            </div>
            <button
              type="button"
              class="btn secondary sm ai-btn"
              :disabled="isRunning || generating || !workflow || scenarios.length >= MAX_SCENARIOS"
              :title="tr('lab.ai_generate', 'AI tạo kịch bản theo quy trình')"
              :aria-label="tr('lab.ai_generate', 'AI tạo kịch bản theo quy trình')"
              @click="generateWithAi"
            >
              <span v-if="generating" class="btn-spinner" aria-hidden="true"></span>
              <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="8" width="14" height="11" rx="3" /><path d="M12 8V5M9.5 13h.01M14.5 13h.01M9.5 16.5h5M3 13v2M21 13v2" /><circle cx="12" cy="4" r="1" /></svg>
              {{ generating ? tr('lab.ai_generating', 'AI đang viết kịch bản…') : $t('lab.ai_short') }}
            </button>
            <div class="repeat">
              <BaseSelect
                id="lab-repeats"
                :label="$t('lab.repeats')"
                :model-value="repeats"
                :disabled="isRunning"
                @update:model-value="repeats = Number($event)"
              >
                <option v-for="n in 5" :key="n" :value="n">{{ n }}</option>
              </BaseSelect>
            </div>
          </div>

          <p v-if="configBlocked && !isRunning" class="warn-note">{{ configBlockedHint }}</p>
          <p v-if="evalError" class="error" role="alert">{{ evalError }}</p>

          <p v-if="runHint" class="run-hint">{{ runHint }}</p>

          <footer class="run-bar">
            <p class="run-note">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 8h.01M11 12h1v4h1" /></svg>
              <span>
                {{ $t('lab.cost_note', { runs: plannedRuns }) }}
                <span v-if="plannedRuns" class="cost-estimate">{{ costEstimate }}</span>
              </span>
            </p>
            <button
              v-if="!isRunning"
              type="button"
              class="btn primary"
              :disabled="!plannedRuns || starting || checking || configBlocked"
              :title="configBlocked ? configBlockedHint : undefined"
              @click="startEval"
            >
              <span v-if="starting" class="btn-spinner" aria-hidden="true"></span>
              <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
              {{ $t('lab.eval_run') }}
            </button>
            <button v-else type="button" class="btn secondary sm danger-outline" :disabled="stopping" @click="stopEval">
              <span v-if="stopping" class="btn-spinner" aria-hidden="true"></span>
              <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2" /></svg>
              {{ $t('lab.eval_stop') }}
            </button>
          </footer>
        </section>

        <LabHistory :workflow="workflow" :current-id="job?.id || ''" :refresh-key="storageRefresh + historyRefresh" @open="openPastJob" @loaded="historyJobs = $event" />

        <!-- Results -->
        <!-- Always in the DOM so assistive tech announces the changes (a live region created with its text is often skipped). -->
        <p class="sr-only" role="status" aria-live="polite">{{ srStatus }}</p>
        <section v-if="job" ref="resultsEl" class="card panel results" tabindex="-1" :aria-label="tr('lab.results_title', 'Kết quả')">
          <header class="panel-head">
            <span class="icon-tile mint" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18" /><path d="m7 15 4-4 3 3 5-6" /></svg>
            </span>
            <div class="panel-text">
              <h2 class="panel-title">{{ tr('lab.results_title', 'Kết quả') }}</h2>
              <p class="panel-hint">{{ $t(`lab.job_status.${job.status}`) }} · {{ job.done }}/{{ job.total }}</p>
            </div>
          </header>

          <LabCleanupPrompt
            :workflow="workflow"
            :job-id="job.id"
            :finished="!isRunning && job.status === 'completed'"
            :passed="job.verdict === 'ready'"
            @cleaned="storageRefresh++"
          />

          <div v-if="job.status === 'completed'" :class="['verdict', job.verdict]">
            <div class="ring" :style="{ '--p': passPct + '%' }">
              <span>{{ passPct }}<small>%</small></span>
            </div>
            <div class="verdict-text">
              <strong>{{ $t(`lab.verdict.${job.verdict}`) }}</strong>
              <span>{{ $t('lab.verdict_detail', { rate: passPct, threshold: Math.round(job.threshold * 100), errors: job.errors }) }}</span>
              <span v-if="job.config_failed" class="warn-text">{{ tr('lab.verdict_config_failed', 'Bước 1 (kiểm tra cấu hình) đang có lỗi: chưa thể dùng quy trình này.') }}</span>
              <span v-if="job.basic_graded" class="warn-text">{{ tr('lab.basic_graded_note', '{n} lượt chỉ được chấm cơ bản (không gọi được AI chấm điểm).', { n: job.basic_graded }) }}</span>
              <span v-if="job.unjudged" class="warn-text">{{ tr('lab.unjudged_note', '{n} lượt chưa chấm được, không tính vào tỷ lệ đạt', { n: job.unjudged }) }}</span>
              <span v-for="node in job.skipped_gates || []" :key="`gate-${node}`" class="warn-text">{{ tr('lab.skipped_gate', 'Cổng {node} bị bỏ qua (tốn phí), không phải đã duyệt', { node }) }}</span>
              <template v-if="job.verdict_reasons?.length">
                <strong class="reasons-title">{{ tr('lab.verdict_reasons_title', 'Vì sao chưa đạt') }}</strong>
                <ul class="reasons">
                  <li v-for="(reason, ri) in job.verdict_reasons" :key="ri">{{ reason }}</li>
                </ul>
              </template>
              <a v-if="job.verdict === 'not_ready' && canFix" href="#lab-brief" class="next-step" @click.prevent="focusBrief">{{ $t('lab.next_step_fix') }}</a>
              <span v-if="job.baseline" :class="Object.keys(job.regression || {}).length ? 'warn-text' : ''">
                {{ tr('lab.vs_baseline', 'So với lần đạt trước: đạt {rate}% (trước {was}%), TB {secs}s (trước {wasSecs}s)', { rate: passPct, was: Math.round((job.baseline.pass_rate || 0) * 100), secs: job.avg_seconds ?? '-', wasSecs: job.baseline.avg_seconds ?? '-' }) }}
                <template v-if="Object.keys(job.regression || {}).length"> - {{ tr('lab.vs_baseline_regression', 'Kém đi so với lần đạt trước') }}</template>
              </span>
            </div>
          </div>
          <div v-else-if="job.status === 'error'" class="state-note error-note" role="alert">
            <strong>{{ $t('lab.job_error_title') }}</strong>
            <template v-if="job.interrupted || String(job.error || '').startsWith('interrupted')">
              <span>{{ tr('lab.job_interrupted', 'Máy chủ đã khởi động lại khi lượt kiểm định đang chạy (thường do sửa mã nguồn backend khi chạy chế độ tự nạp lại). Không phải lỗi kết nối mô hình.') }}</span>
              <span class="state-hint">{{ tr('lab.job_interrupted_hint', 'Bấm "Chạy tiếp" để chỉ chạy lại {n} lượt dang dở, giữ nguyên các lượt đã chấm.', { n: job.total - job.judged }) }}</span>
            </template>
            <template v-else>
              <span v-if="job.error || evalError">{{ job.error || evalError }}</span>
              <span class="state-hint">{{ $t('lab.job_error_hint') }}</span>
            </template>
            <button v-if="job.resumable" type="button" class="btn primary sm resume-btn" :disabled="resuming" @click="resumeEval">
              <span v-if="resuming" class="btn-spinner" aria-hidden="true"></span>
              {{ tr('lab.resume', 'Chạy tiếp') }}
            </button>
          </div>
          <div v-else-if="job.status === 'cancelled'" class="state-note">
            <strong>{{ $t('lab.job_cancelled_title') }}</strong>
            <span>{{ $t('lab.job_cancelled_hint', { done: job.done, total: job.total }) }}</span>
            <button v-if="job.resumable" type="button" class="btn secondary sm resume-btn" :disabled="resuming" @click="resumeEval">
              <span v-if="resuming" class="btn-spinner" aria-hidden="true"></span>
              {{ tr('lab.resume', 'Chạy tiếp') }}
            </button>
          </div>
          <div v-else class="progress">
            <div class="progress-row">
              <span class="progress-label">
                <span v-if="isRunning" class="pulse" aria-hidden="true"></span>
                {{ $t(`lab.job_status.${job.status}`) }}
                <span v-if="reconnecting" class="warn-text reconnecting">· {{ tr('lab.reconnecting', 'Mất kết nối, đang thử lại…') }}</span>
              </span>
              <span class="progress-num">{{ job.done }}/{{ job.total }}</span>
            </div>
            <div class="bar" role="progressbar" :aria-label="$t('lab.progress_label')" :aria-valuenow="progressPct" aria-valuemin="0" aria-valuemax="100">
              <div class="fill" :style="{ transform: `scaleX(${job.total ? job.done / job.total : 0})` }"></div>
            </div>
          </div>

          <!-- What the runs made, with a direct way to open each: the first thing people look for in a past job -->
          <LabProducts
            :job-id="job.id"
            :runs="products"
            :scenario-label="scenarioLabel"
            :show-attempt="hasRepeats"
            @show="showRun"
          />

          <dl class="kpis">
            <div class="kpi">
              <dt>{{ tr('lab.kpi.passed', 'Đạt') }}</dt>
              <dd>{{ job.passed }}<span class="unit">/{{ job.done }}</span></dd>
            </div>
            <div class="kpi">
              <dt>{{ tr('lab.kpi.time', 'Thời gian') }}</dt>
              <dd>{{ job.duration_seconds ?? '—' }}<span v-if="job.duration_seconds != null" class="unit">s</span></dd>
            </div>
            <div class="kpi">
              <dt>{{ tr('lab.kpi.tokens', 'Token') }}</dt>
              <dd>{{ job.total_tokens ? job.total_tokens.toLocaleString() : '—' }}</dd>
            </div>
            <div class="kpi">
              <dt>{{ tr('lab.kpi.cost', 'Chi phí') }}</dt>
              <dd>{{ money(job.cost_usd) || '—' }}</dd>
            </div>
          </dl>

          <section v-if="job.status === 'completed' && (job.findings?.length || canFix)" class="diagnosis">
            <h3 class="diag-title">{{ tr('lab.diag_title', 'Chẩn đoán tốc độ và chất lượng') }}</h3>
            <p v-if="job.slow_runs" class="warn-text">{{ tr('lab.slow_note', '{n} lượt chạy vượt ngân sách thời gian (trung bình {avg}s).', { n: job.slow_runs, s: job.slow_seconds, avg: job.avg_seconds }) }}</p>
            <ul v-if="job.findings?.length" class="diag-list">
              <li v-for="(f, fi) in job.findings" :key="fi" :class="f.severity">
                <strong>{{ severityLabel(f.severity) }} · {{ scenarioLabel(f.scenario) }}</strong>
                <span>{{ f.detail }}</span>
                <span class="diag-fix">{{ f.fix }}</span>
              </li>
            </ul>
            <template v-if="canFix">
              <label class="diag-label" for="lab-brief">{{ tr('lab.brief_label', 'Nội dung gửi cho trợ lý quy trình (có thể bổ sung)') }}</label>
              <textarea id="lab-brief" ref="briefEl" v-model="briefText" class="input brief" rows="8"></textarea>
              <div class="brief-actions">
                <button type="button" class="btn primary sm" @click="fixWithAssistant()">{{ tr('lab.fix_with_assistant', 'Chỉnh sửa quy trình theo lỗi này') }}</button>
                <button type="button" class="btn secondary sm" @click="copyBrief">{{ briefCopied ? tr('lab.copied', 'Đã chép') : tr('lab.copy_brief', 'Chép nội dung') }}</button>
              </div>
            </template>
          </section>

          <ul v-if="job.scenarios.some((s) => s.runs)" class="stability">
            <li v-for="s in job.scenarios" :key="s.index">
              <span class="stab-name">{{ scenarioLabel(s.index) }}</span>
              <span class="num">{{ s.passed }}/{{ s.runs }}</span>
              <span v-if="s.runs > 1" :class="s.stable === false ? 'warn-text' : 'ok-text'">{{ s.stable === null ? '' : s.stable ? $t('lab.stable') : $t('lab.unstable') }}</span>
              <span class="stab-meta">{{ scenarioMeta(s) }}</span>
            </li>
          </ul>

          <h3 v-if="job.results?.length" class="runs-title">
            {{ $t('lab.runs_title') }}
            <span v-if="failedRuns.length" class="runs-failed">{{ $t('lab.runs_failed_count', { n: failedRuns.length }) }}</span>
          </h3>
          <div v-if="job.results?.length" class="runs">
            <details v-for="{ r, k } in orderedRuns" :id="`lab-run-${k}`" :key="k" :class="['run', r.status]" @toggle="onRunToggle(k, $event)">
              <summary>
                <span class="run-dot" aria-hidden="true"></span>
                <span class="run-title">{{ scenarioLabel(r.scenario) }} <span class="run-attempt">· {{ $t('lab.attempt', { n: r.repeat }) }}</span></span>
                <span class="pill">{{ runStatusLabel(r.status) }}</span>
                <span v-if="productChips[k]" :class="['product-chip', productChips[k].type]">{{ productChips[k].label }}</span>
                <span v-if="r.judge?.judged_by" :class="['judge-tag', r.judge.judged_by]" :title="r.judge.judge_model || undefined">
                  {{ r.judge.judged_by === 'ai' ? tr('lab.judged_ai', 'AI chấm') : tr('lab.judged_basic', 'Chấm cơ bản') }}
                </span>
                <span class="run-meta">{{ runMeta(r) }}</span>
                <svg class="run-chevron" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
              </summary>
              <div class="run-body">
                <p v-if="r.judge?.reason" class="judge">
                  <!-- Only an AI judge is shown as "Giám khảo (model)"; the basic check says so plainly. -->
                  <strong v-if="r.judge.judged_by === 'ai'">{{ $t('lab.judge') }}<template v-if="r.judge.judge_model"> ({{ r.judge.judge_model }})</template>:</strong>
                  <strong v-else>{{ tr('lab.judged_basic', 'Chấm cơ bản') }}:</strong> {{ r.judge.reason }}
                </p>
                <p v-if="r.status === 'unjudged'" class="meta-line warn-text">{{ tr('lab.unjudged_run_note', 'Lượt này chạy xong nhưng chưa chấm được, nên không tính là đạt hay không đạt.') }}</p>
                <p v-for="node in r.skipped_gates || []" :key="`gate-${node}`" class="meta-line warn-text">{{ tr('lab.skipped_gate', 'Cổng {node} bị bỏ qua (tốn phí), không phải đã duyệt', { node }) }}</p>
                <p v-if="r.error" class="error">{{ r.error }}</p>
                <button v-if="['failed', 'error'].includes(r.status)" type="button" class="btn secondary sm fix-btn" @click="fixWithAssistant(r)">
                  {{ tr('lab.fix_this_run', 'Chỉnh sửa theo lượt này') }}
                </button>
                <!-- What the run produced (scripts, documents, a web app…): loaded only once the run is opened -->
                <LabRunOutputs
                  v-if="openRuns.has(k) && r.status !== 'running'"
                  :job-id="job.id"
                  :run="k"
                  :job-running="!!isRunning"
                  @deleted="storageRefresh++"
                />
                <p v-if="r.members?.length" class="meta-line">
                  <strong>{{ tr('lab.members_used', 'Thành viên đã làm') }}:</strong> {{ r.members.join(', ') }}
                </p>
                <p v-if="r.agents && Object.keys(r.agents).length" class="meta-line">
                  <strong>{{ $t('lab.agents_used') }}:</strong>
                  {{ Object.entries(r.agents).map(([n, c]) => (c > 1 ? `${n} ×${c}` : n)).join(', ') }}
                </p>
                <div v-if="r.questions?.length" class="meta-line">
                  <strong>{{ $t('lab.questions_asked') }}:</strong>
                  <ul>
                    <li v-for="(q, qi) in r.questions" :key="qi">
                      {{ q.node }}: {{ q.question }}
                      <em v-if="q.answer === 'skipped'" class="warn-text"> · {{ tr('lab.question_skipped', 'bỏ qua, không phải đã đồng ý') }}</em>
                    </li>
                  </ul>
                </div>
                <!-- Rendered only once the run is opened: long answers stay out of the DOM until needed -->
                <template v-if="r.plan && openRuns.has(k)">
                  <p class="flow-label">{{ tr('lab.plan_then_result', 'Kế hoạch → Kết quả') }}</p>
                  <p class="meta-line"><strong>{{ tr('lab.plan_label', 'Kế hoạch') }}</strong><template v-if="r.plan.node"> · {{ r.plan.node }}</template></p>
                  <div class="answer plan markdown-body" v-html="render(r.plan.text || r.plan.summary)"></div>
                  <p v-if="!(r.skipped_gates || []).includes(r.plan.node)" class="meta-line">{{ tr('lab.plan_approved', 'Đã tự động duyệt: "Đồng ý, làm đi."') }}</p>
                  <p class="meta-line"><strong>{{ tr('lab.result_label', 'Kết quả') }}</strong></p>
                </template>
                <div v-if="r.answer && openRuns.has(k)" class="answer markdown-body" v-html="render(r.answer)"></div>
              </div>
            </details>
          </div>
        </section>
      </div>
    </div>

    <LabStorage :refresh-key="storageRefresh" />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import MarkdownIt from 'markdown-it'
import BaseSelect from '@/components/ui/BaseSelect.vue'
import LabRunOutputs from '@/components/lab/LabRunOutputs.vue'
import LabStorage from '@/components/lab/LabStorage.vue'
import LabHistory from '@/components/lab/LabHistory.vue'
import LabProducts from '@/components/lab/LabProducts.vue'
import LabCleanupPrompt from '@/components/lab/LabCleanupPrompt.vue'
import { productType } from '@/utils/labProducts.js'
import { toast } from '@/utils/toast.js'
import { MAX_SCENARIOS, PACK_IDS, buildPackScenarios, dedupeSamples, detectPack } from '@/utils/labSamples.js'
import { labErrorText, runKey } from '@/utils/labOutputs.js'
import { useWorkflowAssistant } from '@/composables/useWorkflowAssistant.js'
import { fetchWorkflowNames, labCancel, labCheck, labEvaluate, labGenerate, labJob, labProducts, labResume } from '@/api/client'

const { t, te, locale } = useI18n()
const route = useRoute()
const router = useRouter()
// Some lab strings are newer than the locale files: fall back to Vietnamese until they are added.
const tr = (key, fallback, params) =>
  te(key) ? t(key, params) : String(fallback).replace(/\{(\w+)\}/g, (_, k) => params?.[k] ?? '')
// Lab API errors: translated by their code (lab.errors.<code>), else the server's message.
const errText = (error) => labErrorText(error, { t, te })
const runStatusLabel = (status) =>
  status === 'unjudged' ? tr('lab.run_status_unjudged', 'Chưa chấm được') : te(`lab.run_status.${status}`) ? t(`lab.run_status.${status}`) : status
const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
// Polling replaces the job every 2 s; cache rendered answers so the same text is never parsed twice.
const renderCache = new Map()
const render = (text) => {
  const key = text || ''
  let html = renderCache.get(key)
  if (html === undefined) {
    html = md.render(key)
    if (renderCache.size > 200) renderCache.clear()
    renderCache.set(key, html)
  }
  return html
}
// Opened runs, keyed by run_id (position for older jobs) so a resume or re-order keeps them open.
const openRuns = ref(new Set())
// Bumped when results are added or deleted so the storage line re-reads its totals.
const storageRefresh = ref(0)
const onRunToggle = (key, event) => {
  const next = new Set(openRuns.value)
  if (event.target.open) next.add(key)
  else next.delete(key)
  openRuns.value = next
}
// Step titles carry their own "1. " prefix; the intro cards show the number in a badge instead.
const stripNo = (text) => String(text).replace(/^\d+\.\s*/, '')

const workflows = ref([])
const loadingWorkflows = ref(true)
const listError = ref('')
const workflow = ref('')
const report = ref(null)
const checking = ref(false)
const checkError = ref('')

let keySeq = 1
const newScenario = (data = {}) => reactive({ key: keySeq++, name: '', prompt: '', criteria: '', ...data })
const scenarios = ref([newScenario()])
const repeats = ref(1)
const job = ref(null)
// A new evaluation appears in the history list as soon as it starts
const historyRefresh = ref(0)
watch(() => job.value?.id, (id, before) => { if (id && id !== before) historyRefresh.value += 1 })
const evalError = ref('')
const starting = ref(false)
const stopping = ref(false)
const resuming = ref(false)
const resultsEl = ref(null)
const briefEl = ref(null)
// Scenarios exactly as sent with the run (blank prompts dropped), so result indexes match the backend's.
const submitted = ref([])
let pollTimer = null
let pollErrors = 0
let unmounted = false
// Polling failed (network, server busy): keep retrying with backoff; the job is "lost" only on a 404.
const reconnecting = ref(false)
const POLL_BACKOFF_MAX_MS = 30000
// Past evaluations of this workflow (from the history list): their cost per run feeds the estimate.
const historyJobs = ref([])

// "Fix" hands the failed runs to the workflow assistant: the composer opens pre-filled (never sent
// automatically) so the user can add details first.
const { setDraftSeed } = useWorkflowAssistant()
const failedRuns = computed(() => (job.value?.results || []).filter((r) => ['failed', 'error'].includes(r.status)))
// The server builds the brief (facts, slow nodes, diagnosis, requested changes) once the job is completed.
const canFix = computed(() => !!job.value && job.value.status === 'completed' && !!job.value.fix_brief && !!job.value.workflow)
const briefText = ref('')
watch(() => job.value?.fix_brief, (text) => { briefText.value = text || '' }, { immediate: true })
const briefCopied = ref(false)
async function copyBrief() {
  try {
    await navigator.clipboard.writeText(briefText.value)
    briefCopied.value = true
    setTimeout(() => { briefCopied.value = false }, 2000)
  } catch {
    /* clipboard unavailable: the text stays selectable in the box */
  }
}
// Failed and errored runs first once the job is done: they are what the user has to act on.
const RUN_ORDER = { failed: 0, error: 0, unjudged: 1, cancelled: 1, passed: 2 }
const orderedRuns = computed(() => {
  const list = (job.value?.results || []).map((r, i) => ({ r, i, k: runKey(r, i) }))
  if (job.value?.status !== 'completed') return list
  return list.sort((a, b) => (RUN_ORDER[a.r.status] ?? 1) - (RUN_ORDER[b.r.status] ?? 1) || a.i - b.i)
})
function focusBrief() {
  const el = briefEl.value
  if (!el) return
  el.scrollIntoView({ block: 'center', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
  el.focus({ preventScroll: true })
}
const prefersReducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
const severityLabel = (sev) => (sev === 'fail' ? tr('lab.sev_fail', 'Lỗi') : tr('lab.sev_warn', 'Cần cải thiện'))
function buildFixMessage(runs) {
  const lines = [tr('lab.fix_intro', 'Quy trình này vừa chạy thử trong Phòng thí nghiệm nhưng chưa đạt. Hãy xem lỗi bên dưới, tìm nguyên nhân trong quy trình rồi đề xuất bản sửa.')]
  for (const r of runs.slice(0, 5)) {
    const sc = submitted.value[r.scenario] || {}
    const agents = Object.entries(r.agents || {}).map(([n, c]) => (c > 1 ? `${n} ×${c}` : n)).join(', ')
    lines.push('', `### ${scenarioLabel(r.scenario)} (${t('lab.attempt', { n: r.repeat })})`)
    lines.push(`- ${tr('lab.fix_request', 'Yêu cầu')}: ${sc.prompt || ''}`)
    if (sc.criteria?.trim()) lines.push(`- ${tr('lab.fix_criteria', 'Tiêu chí đạt')}: ${sc.criteria.trim()}`)
    if (r.judge?.reason) lines.push(`- ${tr('lab.fix_judge', 'Giám khảo nhận xét')}: ${r.judge.reason}`)
    if (r.error) lines.push(`- ${tr('lab.fix_error', 'Lỗi')}: ${String(r.error).slice(0, 500)}`)
    if (agents) lines.push(`- ${tr('lab.fix_agents', 'Agent đã chạy')}: ${agents}`)
    if (r.seconds) lines.push(`- ${tr('lab.kpi.time', 'Thời gian')}: ${Math.round(r.seconds)}s, ${t('lab.tokens_n', { n: (r.tokens || 0).toLocaleString() })}`)
    if (r.answer) lines.push(`- ${tr('lab.fix_answer', 'Câu trả lời nhận được')}: ${String(r.answer).replace(/\s+/g, ' ').slice(0, 400)}`)
  }
  lines.push('', tr('lab.fix_outro', 'Thông tin bổ sung của tôi: '))
  return lines.join('\n')
}
function fixWithAssistant(run) {
  if (!job.value?.workflow) return
  const runs = run ? [run] : failedRuns.value
  // Whole job: the edited brief (the user may have added details); one run: that run only.
  const text = run || !briefText.value ? buildFixMessage(runs) : briefText.value
  if (!text) return
  setDraftSeed(text)
  const name = job.value.workflow.replace(/\.yaml$/, '')
  router.push({ path: `/workflows/${name}`, query: { assist: '1' } })
}

const isRunning = computed(() => job.value && ['queued', 'running'].includes(job.value.status))
// A finished job wrote new result folders: refresh the storage totals.
watch(isRunning, (now, before) => { if (before && !now) storageRefresh.value += 1 })
const plannedRuns = computed(() => scenarios.value.filter((s) => s.prompt.trim()).length * repeats.value)
// Average cost of one run in the latest evaluation of this workflow that recorded a cost (none: no price shown).
const avgRunCost = computed(() => {
  const past = historyJobs.value.find((j) => Number(j.cost_usd) > 0 && Number(j.done) > 0)
  if (past) return Number(past.cost_usd) / Number(past.done)
  const cur = job.value
  return cur?.workflow === workflow.value && cur?.cost_usd > 0 && cur?.done > 0 ? cur.cost_usd / cur.done : 0
})
const costEstimate = computed(() => {
  const n = plannedRuns.value
  const counts = tr('lab.cost_estimate_counts', '{scenarios} kịch bản × {repeats} lần = {n} lượt chạy + {n} lượt chấm.', {
    scenarios: filledScenarios.value, repeats: repeats.value, n
  })
  if (!avgRunCost.value) return counts
  return `${counts} ${tr('lab.cost_estimate_money', 'Ước tính ~{total} (trung bình {avg}/lượt ở lần kiểm định trước).', {
    total: money(avgRunCost.value * n), avg: money(avgRunCost.value)
  })}`
})
const scenarioLabel = (index) => submitted.value[index]?.name?.trim() || t('lab.scenario_name', { n: index + 1 })
const hasRepeats = computed(() => (job.value?.results || []).some((r) => r.repeat > 1))

// What each run produced (type, size, running previews): feeds the overview and the chips on the run rows.
const products = ref([])
let productsRequest = 0
async function loadProducts() {
  const id = job.value?.id
  const mine = ++productsRequest
  if (!id) {
    products.value = []
    return
  }
  try {
    const data = await labProducts(id)
    if (mine === productsRequest && !unmounted && job.value?.id === id) products.value = Array.isArray(data?.runs) ? data.runs.map(withRunKey) : []
  } catch {
    // The overview is a shortcut: the run list below still shows every run's files.
    if (mine === productsRequest) products.value = []
  }
}
// Product entries are keyed like the run rows: run_id when the job has one, else the position.
function withRunKey(entry) {
  const key = entry.run_id || runKey(job.value?.results?.[entry.run], entry.run)
  return { ...entry, key }
}
// A new job, a finished run, or deleted folders change what there is to show.
watch(() => job.value?.id, () => { products.value = []; loadProducts() })
watch(() => [job.value?.done, job.value?.status, storageRefresh.value], (now, before) => {
  if (before && job.value?.id) loadProducts()
})
// A preview may have been stopped elsewhere (in a run below, another tab, the idle timer): re-read on return.
const onWindowFocus = () => { if (job.value?.id && !document.hidden) loadProducts() }
const CHIP_FALLBACK = { webapp: 'Web app', site: 'Trang web', media: '{n} ảnh/video', docs: '{n} tài liệu', code: '{n} file mã', files: '{n} file' }
const productChips = computed(() => {
  const chips = {}
  for (const entry of products.value) {
    const kind = productType(entry)
    if (kind) chips[entry.key] = { type: kind.type, label: tr(`lab.products.chip.${kind.type}`, CHIP_FALLBACK[kind.type], { n: kind.count }) }
  }
  return chips
})
// "Xem file" / "Xem trong Lab" on a product card: open that run and bring its products browser into view.
async function showRun(key) {
  const el = document.getElementById(`lab-run-${key}`)
  if (!el) return
  if (!openRuns.value.has(key)) openRuns.value = new Set([...openRuns.value, key])
  el.open = true
  await nextTick()
  // The row itself (its title says which run this is), the products browser right under it
  el.scrollIntoView({ block: 'start', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
  el.querySelector('summary')?.focus({ preventScroll: true })
}

// Summary strip + health panel
const checkCounts = computed(() => {
  const counts = { pass: 0, warn: 0, fail: 0 }
  for (const c of report.value?.checks || []) counts[c.status] = (counts[c.status] || 0) + 1
  return counts
})
const checkTotal = computed(() => checkCounts.value.pass + checkCounts.value.warn + checkCounts.value.fail)
const health = computed(() => {
  if (!report.value) return null
  if (checkCounts.value.fail) return 'fail'
  if (checkCounts.value.warn) return 'warn'
  return 'pass'
})
const passPct = computed(() => (job.value?.status === 'completed' ? Math.round(job.value.pass_rate * 100) : null))
const progressPct = computed(() => (job.value?.total ? Math.round((job.value.done / job.value.total) * 100) : 0))
// Step 1 found errors: running scenarios would only confirm a broken workflow.
const configBlocked = computed(() => health.value === 'fail')
const configBlockedHint = computed(() =>
  tr('lab.run_blocked_config', 'Bước 1 (kiểm tra cấu hình) đang báo lỗi. Hãy sửa các mục "Cần sửa" và kiểm tra lại trước khi chạy kịch bản.')
)
const money = (v) => (v ? `$${v.toFixed(v < 0.1 ? 3 : 2)}` : '')
const joinMeta = (parts) => parts.filter(Boolean).join(' · ')
const runMeta = (r) =>
  joinMeta([r.seconds ? `${r.seconds}s` : '', r.tokens ? t('lab.tokens_n', { n: r.tokens.toLocaleString() }) : '', money(r.cost_usd)])
const scenarioMeta = (s) =>
  joinMeta([
    s.seconds ? `~${s.seconds}s` : '',
    s.tokens ? t('lab.tokens_n', { n: s.tokens.toLocaleString() }) : '',
    money(s.cost_usd),
    s.members?.length ? s.members.join(', ') : ''
  ])
const filledScenarios = computed(() => scenarios.value.filter((s) => s.prompt.trim()).length)
// Why Run is disabled (the config-blocked reason has its own note above the run bar)
const runHint = computed(() => (!isRunning.value && !plannedRuns.value && !configBlocked.value ? t('lab.run_hint_empty') : ''))
// One short line for screen readers instead of announcing the whole results panel on every poll
const srStatus = computed(() => {
  if (!job.value) return ''
  const base = `${t(`lab.job_status.${job.value.status}`)}: ${job.value.done}/${job.value.total}`
  // Say the verdict too: it is the one thing the user is waiting for.
  return job.value.status === 'completed' && job.value.verdict ? `${base}. ${t(`lab.verdict.${job.value.verdict}`)}` : base
})

// Scenarios are kept per workflow in this browser so a test suite can be re-run after changes.
const storageKey = (name) => `agentdev.lab.scenarios.${name}`
function saveScenarios(name = workflow.value) {
  clearTimeout(saveTimer)
  saveTimer = null
  if (!name) return
  try {
    const data = scenarios.value.map(({ name, prompt, criteria }) => ({ name, prompt, criteria }))
    localStorage.setItem(storageKey(name), JSON.stringify({ scenarios: data, repeats: repeats.value }))
  } catch {
    // storage unavailable: scenarios simply aren't remembered
  }
}
// Typing in a scenario must not serialize + write storage on every keystroke: save once typing pauses.
let saveTimer = null
let pendingSave = false
function scheduleSave() {
  pendingSave = true
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    pendingSave = false
    saveScenarios()
  }, 400)
}
function flushSave(name) {
  if (!pendingSave) return
  pendingSave = false
  saveScenarios(name)
}
function loadScenarios(name) {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey(name)) || 'null')
    if (saved?.scenarios?.length) {
      scenarios.value = saved.scenarios.map((s) => newScenario(s))
      repeats.value = saved.repeats || 1
      return
    }
  } catch {
    // ignore unreadable storage
  }
  scenarios.value = [newScenario()]
  repeats.value = 1
}

// The latest run per workflow is remembered for this tab, so a reload shows its results again
// (the server also stores finished jobs; the history list reopens older ones).
const jobKey = (name) => `agentdev.lab.job.${name}`
const LAST_WORKFLOW_KEY = 'agentdev.lab.workflow'
function rememberJob(name, id, list) {
  try {
    sessionStorage.setItem(jobKey(name), JSON.stringify({ id, submitted: list }))
  } catch {
    // storage unavailable: results are simply not restored after a reload
  }
}
// Open a past evaluation from the history list: its scores, runs and the products each run made.
function revealResults() {
  const el = resultsEl.value
  if (!el) return
  el.scrollIntoView({ block: 'start', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
  el.focus({ preventScroll: true })
}
async function openPastJob(id) {
  if (!id) return
  // Already shown ("Đang xem"): just bring the results back into view.
  if (id === job.value?.id) {
    revealResults()
    return
  }
  const name = workflow.value
  try {
    const data = await labJob(id)
    if (unmounted || workflow.value !== name) return
    stopPolling()
    openRuns.value = new Set()
    submitted.value = (data.scenarios || []).map((s) => ({ name: s.name || '', prompt: s.prompt || '', criteria: s.criteria || '' }))
    lastJobSnapshot = JSON.stringify(data)
    pollErrors = 0
    reconnecting.value = false
    job.value = data
    rememberJob(name, data.id, submitted.value)
    if (isRunning.value) schedulePoll(1500)
    await nextTick()
    revealResults()
  } catch (error) {
    toast.error(errText(error) || tr('lab.history.open_failed', 'Không mở được lần kiểm định này'))
  }
}
async function restoreJob(name) {
  let saved = null
  try {
    saved = JSON.parse(sessionStorage.getItem(jobKey(name)) || 'null')
  } catch {
    saved = null
  }
  if (!saved?.id) return
  try {
    const data = await labJob(saved.id)
    if (unmounted || workflow.value !== name || job.value) return
    submitted.value = Array.isArray(saved.submitted) ? saved.submitted : []
    lastJobSnapshot = JSON.stringify(data)
    pollErrors = 0
    job.value = data
    if (isRunning.value) schedulePoll(1500)
  } catch (error) {
    // Only a job the server says is gone is forgotten; a network hiccup keeps it for the next visit.
    if (error?.status !== 404) return
    try {
      sessionStorage.removeItem(jobKey(name))
    } catch {
      // ignore
    }
  }
}

watch(workflow, (name, previous) => {
  flushSave(previous) // edits made just before switching still belong to the previous workflow
  openRuns.value = new Set()
  report.value = null
  checkError.value = ''
  stopPolling()
  reconnecting.value = false
  historyJobs.value = []
  job.value = null
  submitted.value = []
  if (name) {
    // Keep the choice in the address bar and for the next visit
    if (route.query.workflow !== name) router.replace({ query: { ...route.query, workflow: name } })
    try {
      localStorage.setItem(LAST_WORKFLOW_KEY, name)
    } catch {
      // ignore
    }
    loadScenarios(name)
    runCheck()
    restoreJob(name)
  }
})
watch([scenarios, repeats], scheduleSave, { deep: true })

function addScenario(data) {
  scenarios.value.push(newScenario(data))
}
function removeScenario(index) {
  scenarios.value.splice(index, 1)
}
const sampleMenuOpen = ref(false)
const sampleMenuEl = ref(null)
const sampleBtnEl = ref(null)
const sampleListEl = ref(null)
const sampleItems = () => [...(sampleListEl.value?.querySelectorAll('[role="menuitem"]') || [])]
function moveSampleFocus(step, absolute = false) {
  const items = sampleItems()
  if (!items.length) return
  const current = items.indexOf(document.activeElement)
  const next = absolute ? (step < 0 ? items.length - 1 : 0) : (current + step + items.length) % items.length
  items[next].focus()
}
function openSampleMenu() {
  sampleMenuOpen.value = true
  nextTick(() => moveSampleFocus(0, true))
}
function toggleSampleMenu() {
  if (sampleMenuOpen.value) closeSampleMenu()
  else openSampleMenu()
}
const teamMembers = computed(() => report.value?.checks?.find((c) => c.id === 'team')?.members || [])
const detectedPack = computed(() => detectPack(workflow.value, teamMembers.value))
function closeSampleMenu(refocus = false) {
  sampleMenuOpen.value = false
  if (refocus) sampleBtnEl.value?.focus()
}
function onSampleFocusOut(e) {
  if (sampleMenuOpen.value && !sampleMenuEl.value?.contains(e.relatedTarget)) sampleMenuOpen.value = false
}
function addSamplePack(packId) {
  const id = packId === 'auto' ? detectedPack.value : packId
  const candidates = id === 'general' ? generalSamples() : buildPackScenarios(id, t)
  const { toAdd, replaceBlank } = dedupeSamples(scenarios.value, candidates, MAX_SCENARIOS)
  closeSampleMenu(true)
  if (!toAdd.length) return
  if (replaceBlank) scenarios.value = []
  toAdd.forEach((s) => addScenario(s))
}
const generating = ref(false)
async function generateWithAi() {
  if (generating.value || !workflow.value) return
  generating.value = true
  evalError.value = ''
  const name = workflow.value
  try {
    const { scenarios: generated } = await labGenerate({ yamlFile: name, count: 4, language: { vi: 'Vietnamese', en: 'English', zh: 'Chinese' }[locale.value] || 'Vietnamese' })
    if (workflow.value !== name) return
    const { toAdd, replaceBlank } = dedupeSamples(scenarios.value, generated, MAX_SCENARIOS)
    if (replaceBlank) scenarios.value = []
    toAdd.forEach((s) => addScenario(s))
  } catch (err) {
    evalError.value = err?.message || String(err)
  } finally {
    generating.value = false
  }
}
function generalSamples() {
  const samples = [
    { name: t('lab.sample1_name'), prompt: t('lab.sample1_prompt'), criteria: t('lab.sample1_criteria') }
  ]
  // The "one specialist" sample must name a member this workflow really has: the QA Tester sample
  // only fits the software team, other teams (marketing, content, video) get a generic one.
  const members = report.value?.checks?.find((c) => c.id === 'team')?.members || []
  if (members.includes('QA Tester')) {
    samples.push({ name: t('lab.sample2_name'), prompt: t('lab.sample2_prompt'), criteria: t('lab.sample2_criteria') })
  } else if (members.length) {
    const member = members[0]
    samples.push({
      name: t('lab.sample2_name'),
      prompt: t('lab.sample2_generic_prompt', { member }),
      criteria: t('lab.sample2_generic_criteria', { member })
    })
  }
  return samples
}

async function runCheck() {
  if (!workflow.value) return
  checking.value = true
  checkError.value = ''
  const name = workflow.value
  try {
    const result = await labCheck(name)
    // The user switched workflow while this request was in flight: drop the stale answer.
    if (workflow.value === name) report.value = result
  } catch (error) {
    if (workflow.value === name) checkError.value = error.message
  } finally {
    if (workflow.value === name) checking.value = false
  }
}

function stopPolling() {
  clearTimeout(pollTimer)
  pollTimer = null
}

function schedulePoll(delay) {
  stopPolling()
  if (!unmounted) pollTimer = setTimeout(poll, delay)
}

// The server answered 404 for this job: it no longer knows it, so polling would never end.
// (Network errors and 5xx never land here: poll() keeps retrying with backoff.)
function markJobLost() {
  const message = tr('lab.job_lost', 'Không còn theo dõi được lượt chạy này (máy chủ có thể đã khởi động lại). Hãy chạy lại.')
  reconnecting.value = false
  job.value = { ...job.value, status: 'error', error: message }
  evalError.value = message
}

// Each poll reads the whole job summary. The server caches the costly part (diagnosis, fix brief,
// budgets) per version of the results, so polling every 2 s does not recompute it.
async function poll() {
  pollTimer = null
  if (!job.value || unmounted) return
  const id = job.value.id
  try {
    const data = await labJob(id)
    if (unmounted || job.value?.id !== id) return
    // Nothing changed since the last poll: keep the same object so nothing re-renders.
    const snapshot = JSON.stringify(data)
    if (snapshot !== lastJobSnapshot) {
      lastJobSnapshot = snapshot
      job.value = data
    }
    pollErrors = 0
    reconnecting.value = false
    evalError.value = ''
  } catch (error) {
    if (unmounted || job.value?.id !== id) return
    if (error.status === 404) {
      markJobLost()
      return
    }
    // The server may still be running the job: show "reconnecting" and retry, waiting longer each time.
    // Retry whatever the last known status was, or the banner would stay up with nothing retrying;
    // it stops on success, on a 404, on unmount or when another workflow/job is opened.
    pollErrors += 1
    reconnecting.value = true
    schedulePoll(Math.min(2000 * 2 ** pollErrors, POLL_BACKOFF_MAX_MS))
    return
  }
  // Background tab: nobody is watching, poll less often.
  if (isRunning.value) schedulePoll(document.hidden ? 6000 : 2000)
}
let lastJobSnapshot = ''

async function startEval() {
  if (starting.value || isRunning.value) return
  evalError.value = ''
  const list = scenarios.value
    .filter((s) => s.prompt.trim())
    .map(({ name, prompt, criteria }) => ({ name, prompt, criteria }))
  starting.value = true
  // The workflow the user pressed Run for: they may switch to another one while the request is in flight.
  const name = workflow.value
  try {
    const started = await labEvaluate({ yamlFile: name, scenarios: list, repeats: repeats.value })
    if (unmounted) return
    if (workflow.value !== name) {
      // Started for the previous workflow: keep it there (restored when the user goes back), not here.
      rememberJob(name, started.id, list)
      toast.info(tr('lab.started_other_workflow', 'Đã bắt đầu kiểm định quy trình {name}. Mở lại quy trình đó để xem tiến độ.', { name: name.replace(/\.ya?ml$/, '') }))
      return
    }
    submitted.value = list
    pollErrors = 0
    reconnecting.value = false
    lastJobSnapshot = JSON.stringify(started)
    job.value = started
    rememberJob(name, started.id, list)
    schedulePoll(1500)
    // The results panel sits below the scenario list: bring the progress into view and focus it.
    nextTick(revealResults)
  } catch (error) {
    if (workflow.value === name) evalError.value = errText(error)
  } finally {
    starting.value = false
  }
}

// A server restart (or a cancel) stopped the job: run only its unfinished runs again, keep the graded ones.
async function resumeEval() {
  if (!job.value || resuming.value || isRunning.value) return
  resuming.value = true
  evalError.value = ''
  const id = job.value.id
  try {
    const resumed = await labResume(id)
    if (unmounted || job.value?.id !== id) return
    lastJobSnapshot = JSON.stringify(resumed)
    pollErrors = 0
    reconnecting.value = false
    job.value = resumed
    schedulePoll(1500)
  } catch (error) {
    if (job.value?.id !== id) return
    const message = errText(error)
    evalError.value = message
    job.value = { ...job.value, resumable: false, error: message, interrupted: false }
  } finally {
    resuming.value = false
  }
}

async function stopEval() {
  if (!job.value || stopping.value) return
  stopping.value = true
  try {
    const cancelled = await labCancel(job.value.id)
    // Keep the poll's change detector in sync so an in-flight poll cannot restore a stale "running" state.
    lastJobSnapshot = JSON.stringify(cancelled)
    job.value = cancelled
  } catch (error) {
    if (error.status === 404) markJobLost()
    else evalError.value = errText(error)
  } finally {
    stopping.value = false
  }
}

async function loadWorkflows() {
  loadingWorkflows.value = true
  listError.value = ''
  try {
    // Only the names are shown: one request instead of one per workflow
    workflows.value = (await fetchWorkflowNames()).map((name) => ({ name }))
  } catch (error) {
    // Shown in the empty state: the workspace (where checkError lives) is not rendered yet.
    listError.value = error?.message || String(error)
  } finally {
    loadingWorkflows.value = false
  }
}

onMounted(async () => {
  await loadWorkflows()
  let preset = route.query.workflow
  if (!preset) {
    try {
      preset = localStorage.getItem(LAST_WORKFLOW_KEY)
    } catch {
      preset = null
    }
  }
  // Links may name the file with or without its extension (/lab?workflow=my_flow or my_flow.yaml).
  const match = preset && workflows.value.find((w) => [preset, `${preset}.yaml`, `${preset}.yml`].includes(w.name))
  if (match) workflow.value = match.name
  // Empty state: put the cursor on the one thing to do
  else {
    await nextTick() // the picker was disabled while the list loaded
    document.getElementById('lab-workflow-picker')?.focus()
  }
})
onMounted(() => window.addEventListener('focus', onWindowFocus))
onBeforeUnmount(() => {
  window.removeEventListener('focus', onWindowFocus)
  unmounted = true
  stopPolling()
  flushSave()
})
</script>

<style scoped>
.warn-note { margin: 10px 0 0; font-size: 13px; line-height: 1.5; color: var(--warn); }
.diagnosis { margin: 0 0 16px; padding: 14px 16px; border: 1px solid var(--line); border-radius: 10px; background: var(--tint-2); }
.diag-title { margin: 0 0 8px; font-size: 14px; }
.diag-list { list-style: none; margin: 8px 0 12px; padding: 0; display: grid; gap: 8px; }
.diag-list li { display: grid; gap: 2px; font-size: 13px; line-height: 1.5; padding: 8px 10px; border-radius: 8px; background: color-mix(in srgb, var(--warn) 10%, transparent); }
.diag-list li.fail { background: color-mix(in srgb, var(--danger) 10%, transparent); }
.diag-fix { color: var(--fg-muted); }
.diag-label { display: block; margin: 8px 0 4px; font-size: 12.5px; font-weight: 600; }
.brief { width: 100%; box-sizing: border-box; min-height: 120px; font-size: 13px; line-height: 1.5; resize: vertical; }
.brief-actions { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.fix-btn { align-self: flex-start; margin-top: 6px; }
.resume-btn { align-self: flex-start; margin-top: 8px; }
.verdict-text .warn-text { display: block; margin-top: 4px; font-size: 12.5px; }
.reasons-title { margin-top: 6px; font-size: 13px !important; color: var(--fg) !important; }
.reasons { margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.55; color: var(--fg); }
.reasons li + li { margin-top: 2px; }
.next-step { align-self: flex-start; margin-top: 6px; font-size: 13px; font-weight: 600; color: var(--accent); text-underline-offset: 3px; }
.state-note { display: flex; flex-direction: column; gap: 4px; margin-bottom: 14px; padding: 14px 16px; border-radius: 12px; font-size: 13.5px; line-height: 1.5; color: var(--fg-muted); background: var(--tint); box-shadow: inset 0 0 0 1px var(--line); }
.state-note strong { font-size: 15px; color: var(--fg); }
.state-note.error-note { background: color-mix(in srgb, var(--danger) 8%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--danger) 30%, transparent); }
.state-note.error-note strong { color: var(--danger); }
.state-hint { font-size: 12.5px; }
.runs-title { display: flex; align-items: baseline; gap: 10px; margin: 0 0 8px; font-size: 14px; font-weight: 650; color: var(--fg); }
.runs-failed { font-size: 12.5px; font-weight: 600; color: var(--danger); }
.results:focus { outline: none; }
.results:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
.intro-empty { margin-bottom: 24px; }
.intro-error { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin: 0 0 16px; }
.intro-error .error { margin: 0; display: flex; flex-direction: column; gap: 2px; }
.intro-error-detail { font-size: 12.5px; opacity: 0.85; }
.stab-meta { margin-left: auto; font-size: 12px; color: var(--fg-muted); text-align: right; }
.judge-tag { flex: none; padding: 1px 7px; border-radius: 999px; font-size: 11px; font-weight: 600; background: var(--tint-2); color: var(--fg-muted); }
.judge-tag.basic { color: var(--warn); }
.flow-label { margin: 12px 0 4px; font-size: 12px; font-weight: 650; letter-spacing: 0.03em; color: var(--accent); }
.answer.plan { color: var(--fg-muted); }
.lab-view {
  --line: rgb(var(--ink) / 0.08);
  --line-strong: rgb(var(--ink) / 0.14);
  --tint: rgb(var(--ink) / 0.035);
  --tint-2: rgb(var(--ink) / 0.06);
  --radius: 14px;
  max-width: 1240px;
  padding-bottom: 88px;
  color: var(--fg);
  font-variant-numeric: tabular-nums;
}

/* ================================================================ header */
.hero { display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-end; justify-content: space-between; margin-bottom: 24px; }
.hero-title { margin: 0 0 8px; font-size: 30px; line-height: 1.15; font-weight: 750; letter-spacing: -0.03em; color: var(--fg); }
.hero-sub { margin: 0; max-width: 70ch; font-size: 14.5px; line-height: 1.65; color: var(--fg-muted); }
.ext { opacity: 0.6; }

/* ================================================================ cards */
.card {
  border-radius: var(--radius); background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line), 0 1px 2px rgb(0 0 0 / 0.04), 0 12px 32px -24px rgb(0 0 0 / 0.35);
}
.icon-tile {
  display: grid; flex: none; place-items: center; width: 36px; height: 36px; border-radius: 10px;
  --c: var(--accent-sky-rgb); color: rgb(var(--c)); background: rgb(var(--c) / 0.12); box-shadow: inset 0 0 0 1px rgb(var(--c) / 0.22);
}
.icon-tile.indigo { --c: var(--accent-indigo-rgb); }
.icon-tile.mint { --c: var(--accent-mint-rgb); }
.step-label { margin: 0 0 2px; font-size: var(--fs-xs); font-weight: 600; color: var(--fg-muted); }
.muted { color: var(--fg-muted); font-weight: 500; }

/* ================================================================ control bar */
.control { display: flex; align-items: stretch; gap: 0; margin-bottom: 20px; overflow: hidden; }
.picker-field { flex: 1 1 320px; min-width: 240px; padding: 16px 20px; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(104px, auto)); margin: 0; border-left: 1px solid var(--line); }
.metric { display: flex; flex-direction: column; justify-content: center; gap: 6px; padding: 14px 20px; border-left: 1px solid var(--line); }
.metric:first-child { border-left: 0; }
.metric dt { font-size: var(--fs-xs); font-weight: 600; color: var(--fg-muted); white-space: nowrap; }
.metric dd { margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.02em; color: var(--fg); white-space: nowrap; }
.metric dd .muted { font-size: 14px; }
.unit { font-size: 13px; font-weight: 600; color: var(--fg-muted); letter-spacing: 0; }
.rate.ready { color: var(--success); }
.rate.not_ready { color: var(--danger); }
.health-tag { display: inline-flex; align-items: center; gap: 7px; font-size: 14px; font-weight: 650; }
.health-tag .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 22%, transparent); }
.health-tag.pass { color: var(--success); }
.health-tag.warn { color: var(--warn); }
.health-tag.fail { color: var(--danger); }

/* ================================================================ empty state */
.intro { padding: 28px; }
.intro-head { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: baseline; justify-content: space-between; margin-bottom: 20px; }
.intro-heading { margin: 0; font-size: 13px; font-weight: 600; color: var(--fg-muted); }
.intro-cta { margin: 0; font-size: 18px; font-weight: 700; letter-spacing: -0.01em; color: var(--fg); }
.intro-steps { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; position: relative; }
.intro-step { display: flex; gap: 14px; align-items: flex-start; padding: 20px; border-radius: 12px; background: var(--tint); box-shadow: inset 0 0 0 1px var(--line); }
.intro-title { margin: 0 0 6px; font-size: 15.5px; font-weight: 650; color: var(--fg); }
.intro-desc { margin: 0; font-size: 13.5px; line-height: 1.6; color: var(--fg-muted); }

/* ================================================================ workspace */
.workspace { display: grid; grid-template-columns: 340px minmax(0, 1fr); gap: 20px; align-items: start; }
.main-col { display: flex; flex-direction: column; gap: 20px; min-width: 0; }
.side-col { position: sticky; top: 20px; min-width: 0; }
.panel { padding: 22px 24px; }
.panel-head { display: flex; gap: 14px; align-items: flex-start; margin-bottom: 18px; }
.panel-head.compact { margin-bottom: 10px; align-items: center; }
.panel-text { flex: 1; min-width: 0; }
.panel-title { margin: 0; font-size: 16px; font-weight: 700; letter-spacing: -0.01em; color: var(--fg); }
.panel-hint { margin: 4px 0 0; font-size: 13px; color: var(--fg-muted); line-height: 1.55; }
.health-panel > .panel-hint { margin: 0 0 16px; }

/* ================================================================ fields */
.picker-field { min-width: 0; }
.picker-field :deep(.select) { font-weight: 600; }
.scenario-name {
  box-sizing: border-box; flex: 1; min-width: 0; padding: 6px 28px 6px 8px; border: 1px solid transparent; border-radius: var(--radius-sm);
  background: transparent; color: var(--fg); font: inherit; font-size: 14px; font-weight: 650; cursor: text;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}
.scenario-name:hover:not(:disabled):not(:focus-visible) { border-bottom: 1px dashed var(--line-strong); border-radius: 4px; }
.scenario-name:focus-visible { border-color: var(--accent); background: var(--surface); }
.scenario-name:disabled { opacity: 0.55; cursor: not-allowed; }
.scenario-name::placeholder { color: var(--fg-subtle); }

/* ================================================================ buttons */
.btn.danger-outline { color: var(--danger); border-color: color-mix(in srgb, var(--danger) 55%, transparent); }
.btn.danger-outline:hover { background: color-mix(in srgb, var(--danger) 10%, transparent); color: var(--danger); }
.btn.icon-danger:hover:not(:disabled) { color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent); }
.error { color: var(--danger); font-size: 13px; margin: 12px 0 0; line-height: 1.5; }

/* ================================================================ scenarios */
.scenario-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.scenario { padding: 14px 16px 16px; border-radius: 12px; background: var(--tint); box-shadow: inset 0 0 0 1px var(--line); transition: box-shadow 0.15s ease; }
.scenario:focus-within { box-shadow: inset 0 0 0 1px rgb(var(--accent-sky-rgb) / 0.45); }
.scenario-head { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }
.scenario-no { flex: none; font-size: 12px; font-weight: 700; letter-spacing: 0.04em; color: var(--info); font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; }
.name-wrap { position: relative; display: flex; flex: 1; min-width: 0; }
.name-pencil { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); color: var(--fg-muted); opacity: 0; pointer-events: none; transition: opacity 0.15s ease; }
.name-wrap:hover .name-pencil, .name-wrap:focus-within .name-pencil { opacity: 0.8; }
.skip-tag { flex: none; padding: 2px 9px; border-radius: 999px; font-size: var(--fs-xs); font-weight: 600; color: var(--warn); background: color-mix(in srgb, var(--warn) 12%, transparent); }
.scenario-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.sample-menu { position: relative; }
.sample-menu-list { position: absolute; z-index: var(--z-dropdown); left: 0; bottom: calc(100% + 6px); min-width: 260px; max-width: calc(100vw - 32px); margin: 0; padding: 4px; list-style: none; background: var(--surface-raised); border: 1px solid var(--border); border-radius: var(--radius-md); box-shadow: 0 8px 24px rgb(var(--shade) / 0.22); }
.sample-menu-item { display: block; width: 100%; text-align: left; padding: 7px 10px; border: 0; border-radius: 6px; background: transparent; color: inherit; font: inherit; font-size: 13px; cursor: pointer; }
.sample-menu-item { min-height: 36px; }
.sample-menu-item:hover, .sample-menu-item:focus-visible { background: var(--tint-2); }
.sample-menu-item:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.sample-menu-item.strong { font-weight: 600; }
.sample-menu-item small { font-weight: 400; color: var(--fg-muted); }
.scenario-tools { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 14px; }
.repeat { margin-left: auto; font-size: 13px; color: var(--fg-muted); }
.repeat :deep(.field) { flex-direction: row; align-items: center; gap: var(--space-3); }
.repeat :deep(.select-wrap) { min-width: 80px; }
.run-bar {
  display: flex; gap: 16px; align-items: center; justify-content: space-between; flex-wrap: wrap;
  margin: 20px -24px -22px; padding: 16px 24px; border-top: 1px solid var(--line);
  background: var(--tint); border-radius: 0 0 var(--radius) var(--radius);
}
.run-note { display: flex; gap: 8px; align-items: flex-start; flex: 1; min-width: 220px; margin: 0; font-size: 12.5px; line-height: 1.55; color: var(--fg-muted); }
.run-note svg { flex: none; margin-top: 2px; }
.cost-estimate { display: block; margin-top: 2px; font-variant-numeric: tabular-nums; color: var(--fg); }
.reconnecting { font-size: 12px; }
.run-hint { margin: 16px 0 0; font-size: var(--fs-xs); line-height: 1.5; color: var(--fg-muted); }
.run-hint + .run-bar { margin-top: 10px; }
.sr-only { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }

/* ================================================================ config health */
.meter { display: flex; gap: 3px; height: 6px; margin-bottom: 12px; }
.seg { border-radius: 999px; min-width: 6px; }
.seg.pass { background: var(--success); }
.seg.warn { background: var(--warn); }
.seg.fail { background: var(--danger); }
.chips { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-bottom: 14px; }
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.chip-count { font-weight: 750; }
.chip.pass { color: var(--success); background: color-mix(in srgb, var(--success) 12%, transparent); }
.chip.warn { color: var(--warn); background: color-mix(in srgb, var(--warn) 12%, transparent); }
.chip.fail { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, transparent); }
.chip-total { font-size: 12px; color: var(--fg-muted); }
.check-list { list-style: none; margin: 0 -8px; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.check-item { --tone: var(--success); display: flex; gap: 10px; align-items: flex-start; padding: 8px; border-radius: 9px; }
.check-item.warn { --tone: var(--warn); background: color-mix(in srgb, var(--warn) 7%, transparent); }
.check-item.fail { --tone: var(--danger); background: color-mix(in srgb, var(--danger) 8%, transparent); }
.status-icon { flex: none; width: 20px; height: 20px; display: grid; place-items: center; border-radius: 50%; color: var(--tone); background: color-mix(in srgb, var(--tone) 16%, transparent); }
.check-text { display: flex; flex-direction: column; gap: 3px; min-width: 0; padding-top: 1px; }
.check-name { font-weight: 600; font-size: 13px; }
.check-item.pass .check-name { font-weight: 500; color: var(--fg-muted); }
.check-detail { font-size: 12.5px; color: var(--fg-muted); line-height: 1.5; overflow-wrap: anywhere; }
.check-detail code { display: block; margin-top: 6px; padding: 7px 9px; border-radius: 7px; background: var(--tint-2); white-space: pre-wrap; word-break: break-word; font-size: 11.5px; color: var(--fg); font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; }
.skel-list { display: flex; flex-direction: column; gap: 10px; }
.skel-list span { height: 14px; border-radius: 6px; background: linear-gradient(90deg, var(--tint), var(--tint-2), var(--tint)); background-size: 200% 100%; animation: shimmer 1.4s ease-in-out infinite; }
.skel-list span:nth-child(2n) { width: 75%; }
@keyframes shimmer { from { background-position: 100% 0; } to { background-position: -100% 0; } }

/* ================================================================ results */
.verdict {
  --tone: var(--success); display: flex; align-items: center; gap: 20px; padding: 18px 20px; border-radius: 12px; margin-bottom: 14px;
  background: color-mix(in srgb, var(--tone) 8%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--tone) 30%, transparent);
}
.verdict.not_ready { --tone: var(--danger); }
.verdict-text { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.verdict-text strong { font-size: 16px; color: var(--tone); }
.verdict-text span { font-size: 13.5px; color: var(--fg-muted); line-height: 1.5; }
.ring {
  flex: none; width: 72px; height: 72px; border-radius: 50%; display: grid; place-items: center; position: relative;
  background: conic-gradient(var(--tone) var(--p), color-mix(in srgb, var(--tone) 16%, transparent) 0);
}
.ring::before { content: ''; position: absolute; inset: 7px; border-radius: 50%; background: var(--surface); }
.ring span { position: relative; font-size: 19px; font-weight: 750; color: var(--fg); }
.ring small { font-size: 11px; font-weight: 600; margin-left: 1px; color: var(--fg-muted); }
.progress { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.progress-row { display: flex; justify-content: space-between; font-size: 13px; }
.progress-label { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; }
.progress-num { color: var(--fg-muted); }
.pulse { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: 0.35; transform: scale(0.8); } }
.bar { height: 6px; border-radius: 999px; background: var(--tint-2); overflow: hidden; }
/* scaleX instead of width: the bar animates on the compositor, no layout per frame */
.fill { width: 100%; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--accent), var(--info)); transform-origin: 0 50%; transition: transform 0.4s ease; }
.kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 0 0 14px; }
.kpi { padding: 12px 14px; border-radius: 11px; background: var(--tint); box-shadow: inset 0 0 0 1px var(--line); }
.kpi dt { font-size: var(--fs-xs); font-weight: 600; color: var(--fg-muted); margin-bottom: 4px; }
.kpi dd { margin: 0; font-size: 18px; font-weight: 700; color: var(--fg); letter-spacing: -0.01em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.stability { list-style: none; margin: 0 0 14px; padding: 4px 0; border-radius: 11px; box-shadow: inset 0 0 0 1px var(--line); font-size: 13px; }
.stability li { display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: center; padding: 8px 14px; }
.stability li + li { border-top: 1px solid var(--line); }
.stab-name { flex: 1 1 140px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.num { font-weight: 650; }
.warn-text { color: var(--warn); font-weight: 600; }
.ok-text { color: var(--success); font-weight: 600; }

.runs { border-radius: 11px; box-shadow: inset 0 0 0 1px var(--line); overflow: hidden; }
.run { --tone: var(--fg-muted); scroll-margin-top: 72px; }
.run + .run { border-top: 1px solid var(--line); }
.run.passed { --tone: var(--success); }
.run.failed, .run.error { --tone: var(--danger); }
.run.running { --tone: var(--accent); }
.run.unjudged { --tone: var(--warn); }
.run summary { display: flex; gap: 10px; align-items: center; cursor: pointer; font-size: 13px; padding: 11px 14px; list-style: none; transition: background-color 0.15s ease; }
.run summary:hover { background: var(--tint); }
.run summary::-webkit-details-marker { display: none; }
.run[open] summary { background: var(--tint); }
.run-dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--tone); }
.run-title { flex: 1; min-width: 0; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-attempt { font-weight: 500; color: var(--fg-muted); }
.run-meta { color: var(--fg-muted); font-size: 12px; white-space: nowrap; }
.run-chevron { flex: none; color: var(--fg-muted); transition: transform 0.2s ease; }
.run[open] .run-chevron { transform: rotate(180deg); }
.product-chip { flex: none; padding: 1px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; color: var(--fg-muted); background: var(--tint-2); white-space: nowrap; }
.product-chip.webapp, .product-chip.site { color: rgb(var(--accent-sky-rgb)); background: rgb(var(--accent-sky-rgb) / 0.12); }
.pill { flex: none; font-size: 11px; font-weight: 650; padding: 2px 9px; border-radius: 999px; color: var(--tone); background: color-mix(in srgb, var(--tone) 14%, transparent); }
.run-body { padding: 2px 14px 14px 32px; }
.judge, .meta-line { font-size: 13px; line-height: 1.6; margin: 10px 0 0; color: var(--fg-muted); }
.judge strong, .meta-line strong { color: var(--fg); }
.meta-line ul { margin: 4px 0 0; padding-left: 18px; }
.answer { margin: 12px 0 0; padding: 14px 16px; border-radius: 10px; background: var(--tint); box-shadow: inset 0 0 0 1px var(--line); font-size: 13px; overflow-wrap: anywhere; }

/* ================================================================ responsive */
@media (max-width: 1080px) {
  .workspace { grid-template-columns: minmax(0, 1fr); }
  .side-col { position: static; order: -1; }
  .control { flex-wrap: wrap; }
  .metrics { flex: 1 1 100%; border-left: 0; border-top: 1px solid var(--line); grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .lab-view { padding-bottom: 64px; }
  .hero-title { font-size: 26px; }
  .intro { padding: 18px; }
  .intro-steps { grid-template-columns: 1fr; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metric:nth-child(3) { border-left: 0; }
  .metric:nth-child(n + 3) { border-top: 1px solid var(--line); }
  .panel { padding: 16px; }
  .run-bar { margin: 16px -16px -16px; padding: 14px 16px; }
  .run-bar .btn { width: 100%; }
  .btn { min-height: 44px; }
  .btn.icon-only { width: 44px; }
  .scenario-head { flex-wrap: wrap; }
  .scenario-fields { grid-template-columns: 1fr; }
  .repeat { margin-left: 0; }
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .run-meta { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .pulse, .skel-list span { animation: none; }
  .name-pencil { transition: none; }
  .fill, .run-chevron, .scenario, .run summary { transition: none; }
}
</style>
