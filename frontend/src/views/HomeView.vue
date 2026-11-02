<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'

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

const cubeColors = ['#aaffcd', '#99eaf9', '#a0c4ff']
const cubes = Array.from({ length: 80 }, (_, i) => ({
  id: i,
  left: `${Math.random() * 100}%`,
  top: `${Math.random() * 100}%`,
  size: `${Math.random() * 10 + 4}px`, // Wider size range
  color: cubeColors[Math.floor(Math.random() * cubeColors.length)],
  duration: `${Math.random() * 30 + 40}s`, // 30-60 seconds
  delay: `-${Math.random() * 60}s`, // Staggered delays
  blur: `${Math.random() * 2 + 1}px`, // Add blur
  opacity: Math.random() * 0.4 + 0.2, // Add opacity variation
  rotate: `${Math.random() * 360}deg`, // Add initial rotation
  scale: Math.random() * 1 + 0.7 // Add scale variation
}))
</script>

<template>
  <div class="home-view">
    <div class="cubes-background" :class="{ paused: isPageHidden }">
      <div
        v-for="cube in cubes" 
        :key="cube.id"
        class="cube"
        :style="{
          left: cube.left,
          top: cube.top,
          width: cube.size,
          height: cube.size,
          backgroundColor: cube.color,
          boxShadow: `0 0 12px 2px ${cube.color}, 0 0 24px 4px ${cube.color}99`,
          animationDuration: cube.duration,
          animationDelay: cube.delay,
          filter: `blur(${cube.blur})`,
          opacity: cube.opacity,
          '--rotate': cube.rotate,
          '--scale': cube.scale
        }"
      ></div>
    </div>
    <div class="content-wrapper">
      <h1 class="title">
        <span class="title-line">{{ $t('home.title') }}</span>
        <span class="title-line title-highlight">{{ $t('home.highlight') }}</span>
      </h1>
      
      <p class="introduction">
        {{ $t('home.introduction') }}
      </p>

      <div class="actions">
        <button class="btn get-started-btn" @click="goToTutorial">
          {{ $t('home.get_started') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home-view {
  width: 100%;
  height: 100%;
  background-color: var(--bg-base);
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px;
  box-sizing: border-box;
  font-family: 'Inter', sans-serif;
  position: relative;
  overflow: hidden;
}

.cubes-background {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
}

/* Animated gradient overlay */
.cubes-background::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(1200px 600px at 20% 30%, rgb(var(--accent-mint-rgb) / 0.15), transparent 60%),
              radial-gradient(1000px 500px at 80% 70%, rgb(var(--accent-indigo-rgb) / 0.15), transparent 60%),
              linear-gradient(90deg, rgb(var(--accent-mint-rgb) / 0.08), rgb(var(--accent-sky-rgb) / 0.08), rgb(var(--accent-indigo-rgb) / 0.08));
  filter: blur(2px);
  animation: bgFlow 18s ease-in-out infinite;
  will-change: transform, opacity;
}

.cubes-background.paused::before,
.cubes-background.paused .cube {
  animation-play-state: paused;
}

@keyframes bgFlow {
  0% {
    transform: translate3d(0, 0, 0) scale(1);
    opacity: 0.8;
  }
  50% {
    transform: translate3d(-2%, 1%, 0) scale(1.02);
    opacity: 1;
  }
  100% {
    transform: translate3d(0, 0, 0) scale(1);
    opacity: 0.8;
  }
}

.cube {
  position: absolute;
  border-radius: 4px;
  animation: unifiedCubeAnim 18s linear infinite;
  /* Only transform/opacity animate; blur/box-shadow are static and rasterized once per layer */
  will-change: transform, opacity;
  /* Combined transform: initial angle and scale come from CSS variables */
  --rotate: 0deg;
  --scale: 1;
}

/* Note: the background has pointer-events: none, so cubes never receive hover.
   The former :hover rule (and its filter transition) was dead and only added cost. */

@keyframes unifiedCubeAnim {
  0% {
    opacity: 0.1;
    transform:
      translate3d(0, 0, 0)
      rotate(var(--rotate, 0deg))
      scale(var(--scale, 1));
  }
  20% {
    opacity: 0.3;
    transform:
      translate3d(10px, -20px, 0)
      rotate(calc(var(--rotate, 0deg) + 72deg))
      scale(calc(var(--scale, 1) * 1.05));
  }
  40% {
    opacity: 0.5;
    transform:
      translate3d(-20px, 60px, 0)
      rotate(calc(var(--rotate, 0deg) + 144deg))
      scale(calc(var(--scale, 1) * 1.1));
  }
  60% {
    opacity: 0.4;
    transform:
      translate3d(50px, 30px, 0)
      rotate(calc(var(--rotate, 0deg) + 216deg))
      scale(calc(var(--scale, 1) * 0.95));
  }
  80% {
    opacity: 0.3;
    transform:
      translate3d(-30px, -40px, 0)
      rotate(calc(var(--rotate, 0deg) + 288deg))
      scale(calc(var(--scale, 1) * 1.08));
  }
  100% {
    opacity: 0.1;
    transform:
      translate3d(0, 0, 0)
      rotate(calc(var(--rotate, 0deg) + 360deg))
      scale(var(--scale, 1));
  }
}

/* Background cubes drift slowly */
@keyframes drift {
  0% {
    transform: translate3d(0, 0, 0);
  }
  25% {
    transform: translate3d(2px, -2px, 0);
  }
  50% {
    transform: translate3d(-2px, 6px, 0);
  }
  75% {
    transform: translate3d(5px, 3px, 0);
  }
  100% {
    transform: translate3d(0, 0, 0);
  }
}

.content-wrapper {
  max-width: 900px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
  z-index: 1;
}

.title {
  font-size: 76px;
  font-weight: 900;
  line-height: 1.25;
  margin: 0 0 24px 0;
  letter-spacing: -1.5px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.title-line {
  color: var(--text-1);
}

.title-highlight {
  background: linear-gradient(
    90deg,
    var(--accent-mint),
    var(--accent-sky),
    var(--accent-indigo)
  );
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.introduction {
  font-size: 22px;
  color: rgb(var(--ink-softer) / 0.6);
  line-height: 1.5;
  max-width: 700px;
  margin: 0 auto 40px;
}

.actions {
  display: flex;
  gap: 18px;
  justify-content: center;
}

.btn {
  border: none;
  padding: 14px 32px;
  font-size: 16px;
  font-weight: 600;
  border-radius: 50px;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, background-color 0.2s ease;
  text-decoration: none;
}

.secondary-btn {
  background-color: var(--surface-5);
  color: var(--text-1);
}

.secondary-btn:hover {
  background-color: var(--line-2);
  transition: background-color 0.3s ease;
}

.get-started-btn {
  color: var(--bg-base);
  background: linear-gradient(
    90deg,
    var(--accent-mint),
    var(--accent-sky),
    var(--accent-indigo)
  );
  animation: gradientShift 4s ease-in-out infinite;
  background-size: 200% 100%;
  position: relative;
  z-index: 1;
}

.get-started-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 15px rgb(var(--shade) / 0.4);
}

@keyframes gradientShift {
  0%, 100% {
    background-position: 0% 0%;
  }
  50% {
    background-position: 100% 0%;
  }
}

  @media (max-width: 768px) {
  .title {
    font-size: 42px;
  }

  .introduction {
    font-size: 18px;
  }

  .actions {
    flex-direction: column;
  }
}

@media (prefers-reduced-motion: reduce) {
  .cubes-background::before,
  .cube,
  .get-started-btn {
    animation: none;
  }
  .cube {
    /* Keep the static composition visible without motion */
    opacity: 0.3;
  }
}
</style>
