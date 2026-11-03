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
        <button type="button" class="btn get-started-btn" @click="goToTutorial">
          {{ $t('home.get_started') }}
          <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
        </button>
        <router-link to="/workflows" class="btn secondary-btn">{{ $t('home.secondary') }}</router-link>
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
  background: var(--bg-base);
  font-family: 'Inter', sans-serif;
  isolation: isolate;
}

/* ---------------------------------------------------------------- backdrop */
.backdrop {
  position: fixed;
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
  background: var(--accent-sky);
  box-shadow: 0 0 0 3px rgb(var(--accent-sky-rgb) / 0.16), 0 0 12px rgb(var(--accent-sky-rgb) / 0.7);
  transform: rotate(var(--a)) translateX(var(--r));
}

.orbit-1 .orbit-dot { background: var(--accent-mint); box-shadow: 0 0 0 3px rgb(var(--accent-mint-rgb) / 0.16), 0 0 12px rgb(var(--accent-mint-rgb) / 0.7); }
.orbit-2 .orbit-dot { background: var(--accent-indigo); box-shadow: 0 0 0 3px rgb(var(--accent-indigo-rgb) / 0.16), 0 0 12px rgb(var(--accent-indigo-rgb) / 0.7); }

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

.home-view.paused .backdrop *,
.home-view.paused .title-highlight {
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
  color: var(--text-soft-1);
  background: rgb(var(--panel-20) / 0.6);
  box-shadow: inset 0 0 0 1px rgb(var(--ink) / 0.1);
}

.eyebrow-dot {
  position: relative;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent-mint);
}

.eyebrow-dot::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 1.5px solid var(--accent-mint);
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
  font-size: 82px;
  font-weight: 900;
  line-height: 1.12;
  letter-spacing: -0.045em;
}

.title-line {
  color: var(--text-strong);
}

.title-highlight {
  padding-bottom: 0.06em;
  background: linear-gradient(90deg, var(--accent-mint), var(--accent-sky), var(--accent-indigo), var(--accent-sky), var(--accent-mint));
  background-size: 200% 100%;
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: shimmer 8s linear infinite;
}

@keyframes shimmer { to { background-position: -200% 0; } }

.introduction {
  max-width: 680px;
  margin: 0 auto 38px;
  font-size: 20px;
  line-height: 1.6;
  color: rgb(var(--ink-softer) / 0.62);
}

.actions {
  display: flex;
  gap: 14px;
  justify-content: center;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  min-height: 50px;
  padding: 0 30px;
  border: 0;
  border-radius: 999px;
  font-size: 16px;
  font-weight: 650;
  text-decoration: none;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, background-color 0.2s ease;
}

.get-started-btn {
  position: relative;
  color: #04121f;
  background: linear-gradient(90deg, var(--accent-mint), var(--accent-sky), var(--accent-indigo));
  box-shadow: 0 0 0 1px rgb(var(--accent-sky-rgb) / 0.5), 0 10px 34px -8px rgb(var(--accent-sky-rgb) / 0.65);
}

.get-started-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 0 1px rgb(var(--accent-sky-rgb) / 0.7), 0 14px 40px -8px rgb(var(--accent-sky-rgb) / 0.85);
}

.get-started-btn svg {
  transition: transform 0.2s ease;
}

.get-started-btn:hover svg {
  transform: translateX(3px);
}

.secondary-btn {
  color: var(--text-1);
  background: rgb(var(--panel-20) / 0.55);
  box-shadow: inset 0 0 0 1px rgb(var(--ink) / 0.14);
}

.secondary-btn:hover {
  color: var(--text-1);
  background: rgb(var(--ink) / 0.08);
  box-shadow: inset 0 0 0 1px rgb(var(--ink) / 0.24);
}

.btn:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 3px;
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
  color: var(--text-muted-4);
}

.runs-on-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.8;
}

.provider {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-soft-1);
}

/* ---------------------------------------------------------------- quick start */
.quickstart {
  width: 100%;
  margin-top: 40px;
}

.quickstart-title {
  margin: 0 0 14px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted-4);
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
  background: rgb(var(--panel-20) / 0.55);
  box-shadow: inset 0 0 0 1px rgb(var(--ink) / 0.1);
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
  color: #04121f;
  background: var(--accent-mint);
}

.quick-step:nth-child(2) .step-no { background: var(--accent-sky); }
.quick-step:nth-child(3) .step-no { background: var(--accent-indigo); color: #fff; }

.step-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.step-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-strong);
}

.step-desc {
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-soft-1);
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
  gap: 5px;
  font-size: 13px;
  font-weight: 650;
  color: var(--accent-sky);
  text-decoration: none;
}

.step-link:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.step-link.subtle {
  color: var(--text-muted-4);
}

.step-link:focus-visible {
  outline: 2px solid var(--accent-sky);
  outline-offset: 2px;
  border-radius: 4px;
}

/* ---------------------------------------------------------------- light theme */
:root[data-theme='light'] .quick-step {
  background: rgb(255 255 255 / 0.8);
}

:root[data-theme='light'] .step-link:not(.subtle) {
  color: #0369a1;
}

:root[data-theme='light'] .title-highlight {
  background-image: linear-gradient(90deg, #047857, #0369a1, #4338ca, #0369a1, #047857);
}

:root[data-theme='light'] .introduction {
  color: var(--text-soft-1);
}

:root[data-theme='light'] .get-started-btn {
  color: #fff;
  background: linear-gradient(90deg, #047857, #0369a1, #4338ca);
}

:root[data-theme='light'] .eyebrow,
:root[data-theme='light'] .secondary-btn {
  background: rgb(255 255 255 / 0.75);
}

:root[data-theme='light'] .grid-plane {
  background-image:
    linear-gradient(rgb(var(--accent-sky-rgb) / 0.14) 1px, transparent 1px),
    linear-gradient(90deg, rgb(var(--accent-sky-rgb) / 0.14) 1px, transparent 1px);
}

/* ---------------------------------------------------------------- responsive */
@media (max-width: 768px) {
  .title { font-size: 46px; }
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
  .eyebrow-dot::after,
  .title-highlight {
    animation: none;
  }

  .scanline { display: none; }
}
</style>
