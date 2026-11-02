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
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes,
    scrollBehavior(to, from, savedPosition) {
        if (savedPosition) {
            return savedPosition
        }
        
        if (to.hash) {
            return {
                el: to.hash,
                behavior: 'smooth',
                // Add a small delay to ensure the element exists
                top: 0
            }
        }
        
        // Otherwise scroll to top
        return { top: 0 }
    }
})

export default router