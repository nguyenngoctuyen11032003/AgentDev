import { createRouter, createWebHistory } from 'vue-router'

const routes = [
    {
        path: '/',
        component: () => import('@/views/HomeView.vue')
    },
    {
        path: '/tutorial',
        component: () => import('@/views/TutorialView.vue'),
        meta: { hideNavOnScroll: true }
    },
    {
        path: '/launch',
        component: () => import('@/views/LaunchView.vue')
    },
    {
        path: '/batch-run',
        component: () => import('@/views/BatchRunView.vue')
    },
    {
        path: '/workflows/:name?',
        component: () => import('@/views/WorkflowWorkbench.vue')
    },
    {
        path: '/connections',
        name: 'connections',
        component: () => import('@/views/ConnectionsView.vue')
    },
]

const router = createRouter({
    history: createWebHistory(),
    routes,
    scrollBehavior(to, from, savedPosition) {
        if (savedPosition) {
            return savedPosition
        }

        // Hash targets live inside views with their own scroll container and are
        // only rendered after async content loads (e.g. TutorialView), so the view
        // performs the (smooth) scroll itself. Returning nothing here avoids a
        // competing window scroll and the "element not found" warning.
        if (to.hash) {
            return
        }

        // Otherwise scroll to top
        return { top: 0 }
    }
})

export default router
