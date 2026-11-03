import { createRouter, createWebHistory } from 'vue-router'

const routes = [
    {
        path: '/',
        component: () => import('@/views/HomeView.vue')
    },
    {
        path: '/tutorial',
        // No hide-on-scroll here: hiding the bar animates its margin and resizes the article's
        // scroll box, which re-lays out the whole long page on every frame and makes scrolling stutter.
        component: () => import('@/views/TutorialView.vue')
    },
    {
        path: '/launch',
        component: () => import('@/views/LaunchView.vue')
    },
    {
        path: '/lab',
        name: 'lab',
        component: () => import('@/views/LabView.vue')
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
        // Settings page: general preferences plus the shared resources every agent uses
        path: '/settings',
        component: () => import('@/views/SettingsView.vue'),
        children: [
            { path: '', redirect: '/settings/general' },
            {
                path: 'general',
                name: 'settings-general',
                component: () => import('@/views/settings/GeneralSettingsPage.vue')
            },
            {
                path: 'connections',
                name: 'connections',
                component: () => import('@/views/ConnectionsView.vue')
            },
            {
                path: 'skills',
                name: 'skills',
                component: () => import('@/views/SkillsView.vue')
            }
        ]
    },
    // Old top-level addresses keep working (bookmarks, links in docs, ?connect= deep links)
    { path: '/connections', redirect: (to) => ({ path: '/settings/connections', query: to.query, hash: to.hash }) },
    { path: '/skills', redirect: (to) => ({ path: '/settings/skills', query: to.query, hash: to.hash }) },
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
