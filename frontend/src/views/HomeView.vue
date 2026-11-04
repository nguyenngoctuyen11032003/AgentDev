<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import ProviderLogo from '@/components/connections/ProviderLogo.vue'

const router = useRouter()

const goToTutorial = () => {
  router.push('/tutorial')
}

// Pause the decorative background animations while the tab is hidden
const isPageHidden = ref(typeof document !== 'undefined' && document.hidden)
const handleVisibilityChange = () => {
  isPageHidden.value = document.hidden
}

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibilityChange)
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})

// "Bắt đầu nhanh": the three things a new user does, in order
const TEMPLATE_WORKFLOW = 'software_company'
const quickSteps = [
  { key: 'connect', to: '/settings/connections' },
  { key: 'workflow', to: `/workflows/${TEMPLATE_WORKFLOW}`, alt: '/workflows' },
  { key: 'chat', to: { path: '/launch', query: { workflow: `${TEMPLATE_WORKFLOW}.yaml` } }, newTab: true }
]

const providers = [
  { id: 'anthropic', label: 'Claude' },
  { id: 'openai', label: 'Codex' },
  { id: 'gemini', label: 'Gemini' }
]

// Agents on the orbit rings: [ring, start angle in degrees]
const orbitDots = [
  [0, 20], [0, 200],
  [1, 80], [1, 250], [1, 320],
  [2, 140], [2, 30]
]
</script>

<template>
  <div class="home-view" :class="{ paused: isPageHidden }">
    <!-- Decorative backdrop: aurora, perspective grid, orbit rings. Transform/opacity animations only. -->
    <div class="backdrop" aria-hidden="true">
      <div class="aurora aurora-a"></div>
      <div class="aurora aurora-b"></div>
      <div class="grid-floor">
        <div class="grid-plane"></div>
      </div>
      <div class="orbits">
        <div v-for="r in 3" :key="r" class="orbit" :class="`orbit-${r - 1}`">
          <span
            v-for="([ring, angle], i) in orbitDots.filter(([ring]) => ring === r - 1)"
            :key="`${ring}-${i}`"
            class="orbit-dot"
            :style="{ '--a': `${angle}deg` }"
          ></span>
        </div>
      </div>
      <div class="scanline"></div>
    </div>

    <div class="content-wrapper">
      <span class="eyebrow">
        <span class="eyebrow-dot"></span>
        {{ $t('home.eyebrow') }}
      </span>

      <h1 class="title">
        <span class="title-line">{{ $t('home.title') }}</span>
        <span class="title-line title-highlight">{{ $t('home.highlight') }}</span>
      </h1>

      <p class="introduction">{{ $t('home.introduction') }}</p>

      <div class="actions">
        <button type="button" class="btn primary get-started-btn" @click="goToTutorial">
          {{ $t('home.get_started') }}
          <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
        </button>
        <router-link to="/workflows" class="btn secondary secondary-btn">{{ $t('home.secondary') }}</router-link>
      </div>

      <div class="runs-on">
        <span class="runs-on-label">{{ $t('home.runs_on') }}</span>
        <span v-for="p in providers" :key="p.id" class="provider">
          <ProviderLogo :vendor="p.id" :label="p.label" :size="22" bare />
          {{ p.label }}
        </span>
      </div>

      <section class="quickstart" aria-labelledby="quickstart-title">
        <h2 id="quickstart-title" class="quickstart-title">{{ $t('home.quickstart.title') }}</h2>
        <ol class="quick-steps">
          <li v-for="(step, i) in quickSteps" :key="step.key" class="quick-step">
            <span class="step-no" aria-hidden="true">{{ i + 1 }}</span>
            <span class="step-body">
              <span class="step-title">{{ $t(`home.quickstart.${step.key}_title`) }}</span>
              <span class="step-desc">{{ $t(`home.quickstart.${step.key}_desc`) }}</span>
              <span class="step-links">
                <router-link
                  :to="step.to"
                  class="step-link"
                  :target="step.newTab ? '_blank' : undefined"
                  :rel="step.newTab ? 'noopener' : undefined"
                >
                  {{ $t(`home.quickstart.${step.key}_cta`) }}
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
                </router-link>
                <router-link v-if="step.alt" :to="step.alt" class="step-link subtle">
                  {{ $t(`home.quickstart.${step.key}_alt`) }}
                </router-link>
              </span>
            </span>
          </li>
        </ol>
      </section>
    </div>
  </div>
</template>

<style scoped>
.home-view {
  position: relative;
  box-sizing: border-box;
  display: flex;
  /* safe: when the content is taller than the window it starts at the top and scrolls */
  align-items: safe center;
  justify-content: center;
  width: 100%;
  height: 100%;
  padding: 24px;
  overflow-x: hidden;
  overflow-y: auto;
  background: var(--bg);
  font-family: 'Inter', sans-serif;
  isolation: isolate;
}

/* ---------------------------------------------------------------- backdrop */
.backdrop {
  position: absolute;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  overflow: hidden;
}

.aurora {
  position: absolute;
  width: 62vmax;
  height: 62vmax;
  border-radius: 50%;
  filter: blur(10px);
  opacity: 0.55;
  will-change: transform;
}

.aurora-a {
  top: -34vmax;
  left: -14vmax;
  background: radial-gradient(circle, rgb(var(--accent-mint-rgb) / 0.22), transparent 62%);
  animation: drift-a 22s ease-in-out infinite alternate;
}

.aurora-b {
  top: -26vmax;
  right: -18vmax;
  background: radial-gradient(circle, rgb(var(--accent-indigo-rgb) / 0.26), transparent 62%);
  animation: drift-b 26s ease-in-out infinite alternate;
}

@keyframes drift-a { to { transform: translate3d(8vmax, 6vmax, 0) scale(1.08); } }
@keyframes drift-b { to { transform: translate3d(-9vmax, 7vmax, 0) scale(1.05); } }

/* Perspective grid "floor" receding to the horizon; the plane slides, the floor stays */
.grid-floor {
  position: absolute;
  left: -50%;
  right: -50%;
  bottom: -2%;
  height: 46%;
  perspective: 520px;
  perspective-origin: 50% 0%;
  -webkit-mask-image: linear-gradient(to top, #000 10%, transparent 92%);
  mask-image: linear-gradient(to top, #000 10%, transparent 92%);
}

.grid-plane {
  position: absolute;
  inset: -100% 0 0;
  transform: rotateX(62deg);
  transform-origin: 50% 100%;
  background-image:
    linear-gradient(rgb(var(--accent-sky-rgb) / 0.22) 1px, transparent 1px),
    linear-gradient(90deg, rgb(var(--accent-sky-rgb) / 0.22) 1px, transparent 1px);
  background-size: 56px 56px;
  animation: grid-move 6s linear infinite;
  will-change: transform;
}

@keyframes grid-move {
  from { transform: rotateX(62deg) translate3d(0, 0, 0); }
  to { transform: rotateX(62deg) translate3d(0, 56px, 0); }
}

/* Orbit rings centred behind the title, each turning at its own pace */
.orbits {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 0;
  height: 0;
}

.orbit {
  --r: 260px;
  position: absolute;
  top: calc(var(--r) * -1);
  left: calc(var(--r) * -1);
  width: calc(var(--r) * 2);
  height: calc(var(--r) * 2);
  border-radius: 50%;
  border: 1px solid rgb(var(--ink) / 0.07);
  animation: spin 60s linear infinite;
  will-change: transform;
}

.orbit-1 { --r: 380px; border-style: dashed; border-color: rgb(var(--ink) / 0.06); animation-duration: 90s; animation-direction: reverse; }
.orbit-2 { --r: 520px; border-color: rgb(var(--ink) / 0.045); animation-duration: 140s; }

.orbit-dot {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 7px;
  height: 7px;
  margin: -3.5px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 3px rgb(var(--accent-sky-rgb) / 0.16), 0 0 12px rgb(var(--accent-sky-rgb) / 0.7);
  transform: rotate(var(--a)) translateX(var(--r));
}

.orbit-1 .orbit-dot { background: var(--success); box-shadow: 0 0 0 3px rgb(var(--accent-mint-rgb) / 0.16), 0 0 12px rgb(var(--accent-mint-rgb) / 0.7); }
.orbit-2 .orbit-dot { background: var(--info); box-shadow: 0 0 0 3px rgb(var(--accent-indigo-rgb) / 0.16), 0 0 12px rgb(var(--accent-indigo-rgb) / 0.7); }

@keyframes spin { to { transform: rotate(360deg); } }

/* A faint light band sweeping down the screen */
.scanline {
  position: absolute;
  inset: 0 0 auto;
  height: 160px;
  background: linear-gradient(to bottom, transparent, rgb(var(--accent-sky-rgb) / 0.05), transparent);
  animation: scan 9s ease-in-out infinite;
  will-change: transform;
}

@keyframes scan {
  0% { transform: translate3d(0, -180px, 0); }
  100% { transform: translate3d(0, 110vh, 0); }
}

.home-view.paused .backdrop * {
  animation-play-state: paused;
}

/* ---------------------------------------------------------------- content */
.content-wrapper {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  max-width: 900px;
  text-align: center;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 26px;
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--fg-muted);
  background: color-mix(in srgb, var(--surface) 75%, transparent);
  box-shadow: inset 0 0 0 1px var(--border);
}

.eyebrow-dot {
  position: relative;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--success);
}

.eyebrow-dot::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 1.5px solid var(--success);
  animation: ping 2s ease-out infinite;
}

@keyframes ping {
  from { transform: scale(0.6); opacity: 0.8; }
  to { transform: scale(1.8); opacity: 0; }
}

.title {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin: 0 0 24px;
  font-size: clamp(40px, 7vw, 82px);
  font-weight: 900;
  line-height: 1.12;
  letter-spacing: -0.035em;
  text-wrap: balance;
}

.title-line {
  color: var(--fg);
}

.title-highlight {
  padding-bottom: 0.06em;
  color: var(--accent);
}

.introduction {
  max-width: 680px;
  margin: 0 auto 38px;
  font-size: 20px;
  line-height: 1.6;
  color: var(--fg-muted);
}

.actions {
  display: flex;
  gap: 14px;
  justify-content: center;
}

.actions .btn {
  gap: 9px;
  min-height: 48px;
  padding: 0 28px;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 650;
  transition: transform 0.2s ease, box-shadow 0.2s ease, background-color 0.2s ease, filter 0.2s ease;
}

.get-started-btn {
  box-shadow: 0 10px 34px -10px rgb(var(--accent-sky-rgb) / 0.6);
}

.get-started-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 40px -10px rgb(var(--accent-sky-rgb) / 0.8);
}

.get-started-btn svg {
  transition: transform 0.2s ease;
}

.get-started-btn:hover svg {
  transform: translateX(3px);
}

.secondary-btn {
  background: color-mix(in srgb, var(--surface) 70%, transparent);
  backdrop-filter: blur(6px);
}

.secondary-btn:hover {
  background: var(--surface-raised);
}

.runs-on {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 10px 22px;
  margin-top: 46px;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--fg-muted);
}

.runs-on-label {
  font-size: 13px;
  font-weight: 600;
}

.provider {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--fg-muted);
}

/* ---------------------------------------------------------------- quick start */
.quickstart {
  width: 100%;
  margin-top: 40px;
}

.quickstart-title {
  margin: 0 0 14px;
  font-size: 15px;
  font-weight: 650;
  color: var(--fg-muted);
}

.quick-steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin: 0;
  padding: 0;
  list-style: none;
  text-align: left;
}

.quick-step {
  display: flex;
  gap: 12px;
  padding: 16px 16px 14px;
  border-radius: 16px;
  background: color-mix(in srgb, var(--surface) 80%, transparent);
  box-shadow: inset 0 0 0 1px var(--border);
  backdrop-filter: blur(6px);
}

.step-no {
  display: grid;
  flex: none;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  font-size: 13px;
  font-weight: 800;
  color: var(--on-success);
  background: var(--success);
}

.quick-step:nth-child(2) .step-no { background: var(--accent); color: var(--on-accent); }
.quick-step:nth-child(3) .step-no { background: var(--info); color: var(--on-info); }

.step-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.step-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--fg);
}

.step-desc {
  font-size: 13px;
  line-height: 1.5;
  color: var(--fg-muted);
}

.step-links {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  margin-top: 6px;
}

.step-link {
  display: inline-flex;
  align-items: center;
  min-height: 40px;
  gap: 5px;
  font-size: 13px;
  font-weight: 650;
  color: var(--accent);
  text-decoration: none;
}

.step-link:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.step-link.subtle {
  color: var(--fg-muted);
}

.step-link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: 4px;
}

/* ---------------------------------------------------------------- light theme */
:root[data-theme='light'] .grid-plane {
  background-image:
    linear-gradient(rgb(var(--accent-sky-rgb) / 0.14) 1px, transparent 1px),
    linear-gradient(90deg, rgb(var(--accent-sky-rgb) / 0.14) 1px, transparent 1px);
}

/* ---------------------------------------------------------------- short screens
   Laptops are wide but short (1280x720, 1366x768, 1536x864). Tighten the hero in steps so
   the headline, the actions and the three quick-start cards all fit the first screen. */
@media (max-height: 900px) and (min-width: 769px) {
  .home-view { padding-top: 12px; padding-bottom: 12px; }
  .eyebrow { margin-bottom: 16px; }
  .title { margin-bottom: 14px; font-size: clamp(40px, 7vw, calc(9.5 * var(--vh))); }
  .introduction { margin-bottom: 24px; font-size: 18px; line-height: 1.5; }
  .runs-on { margin-top: 24px; }
  .quickstart { margin-top: 24px; }
  .quick-step { padding-block: 12px 10px; }
}

@media (max-height: 800px) and (min-width: 769px) {
  .eyebrow { margin-bottom: 12px; }
  .title { margin-bottom: 10px; font-size: clamp(36px, 7vw, calc(8 * var(--vh))); line-height: 1.06; }
  .introduction { margin-bottom: 16px; font-size: 16px; }
  .actions .btn { min-height: 42px; }
  .runs-on { margin-top: 16px; }
  .quickstart { margin-top: 16px; }
  .quickstart-title { margin-bottom: 8px; }
}

/* ---------------------------------------------------------------- responsive */
@media (max-width: 768px) {
  .introduction { font-size: 17px; }
  .actions { flex-direction: column; width: 100%; max-width: 320px; }
  .runs-on { margin-top: 32px; }
  .quick-steps { grid-template-columns: 1fr; }
  .quickstart { margin-top: 32px; }
  .orbit { --r: 170px; }
  .orbit-1 { --r: 250px; }
  .orbit-2 { --r: 340px; }
}

@media (prefers-reduced-motion: reduce) {
  .aurora,
  .grid-plane,
  .orbit,
  .scanline,
  .eyebrow-dot::after {
    animation: none;
  }

  .scanline { display: none; }
}
</style>
