// Where a product file browser (LabRunOutputs) and its app runner (LabRunPreview) read from.
// A source is an adapter over one product folder:
//   key                     changes when the folder changes (the browser reloads)
//   files()                 -> {available, root, files: [{path, size, kind}], project, ...}
//   archiveUrl()            the whole product as a .zip (no dependency folders)
//   accounts: {load, save}  test accounts the user keeps for the product's app
//   fileUrl(path)           raw file URL (img/video src, download, text fetch)
//   fileText(path, {signal})
//   siteUrl(path)           the folder served as a static site (HTML pages with relative assets)
//   open(path, reveal)      open on this machine
//   preview: {start, status, stop, heartbeat?}   "Chạy thử" (heartbeat: optional "still watched" ping)
//   deleteOutputs()         optional: absent = the browser offers no delete
//   copy                    optional: {name: [i18nKey, fallback]} for wording that depends on the context
import {
  labPreviewHeartbeat, labPreviewStart, labRunAccounts, labRunAccountsSave, labRunArchiveUrl, labPreviewStatus, labPreviewStop, labRunDeleteOutputs, labRunFileText, labRunFileUrl,
  labRunFiles, labRunOpen, labRunSiteUrl,
  sessionAccounts, sessionAccountsSave, sessionOutputsArchiveUrl, sessionOutputsFileText, sessionOutputsFileUrl, sessionOutputsFiles, sessionOutputsOpen, sessionOutputsSiteUrl,
  sessionPreviewStart, sessionPreviewStatus, sessionPreviewStop
} from '@/api/client'

const SANDBOX_BASE = 'allow-scripts allow-forms allow-popups'

/**
 * The iframe sandbox of a running preview at `url`, shown inside a page of `pageOrigin`.
 * An app served from its own origin (another port) keeps that origin, plus dialogs (confirm/alert) its UI may
 * use: it cannot reach AgentDev's storage, which lives on a different origin. A relative or same-origin URL
 * (a static site served by AgentDev itself) stays fully opaque, so its scripts cannot call AgentDev's API.
 */
export function previewSandbox(url, pageOrigin) {
  let origin = ''
  try {
    origin = /^https?:\/\//i.test(url || '') ? new URL(url).origin : ''
  } catch {
    origin = ''
  }
  if (!origin || origin === pageOrigin) return SANDBOX_BASE
  return `${SANDBOX_BASE} allow-same-origin allow-modals allow-downloads`
}

/** One run of a Lab job (AgentDev/AgentDev_lab/<run>; older runs storage/warehouse/lab_*); `run` is its run_id (position for older jobs). */
export function labOutputSource(jobId, run) {
  return {
    key: `lab:${jobId}:${run}`,
    files: () => labRunFiles(jobId, run),
    archiveUrl: () => labRunArchiveUrl(jobId, run),
    accounts: { load: () => labRunAccounts(jobId, run), save: (rows) => labRunAccountsSave(jobId, run, rows) },
    fileUrl: (path) => labRunFileUrl(jobId, run, path),
    fileText: (path, options) => labRunFileText(jobId, run, path, options),
    siteUrl: (path) => labRunSiteUrl(jobId, run, path),
    open: (path, reveal) => labRunOpen(jobId, run, { path, reveal }),
    preview: {
      start: () => labPreviewStart(jobId, run),
      status: () => labPreviewStatus(jobId, run),
      stop: () => labPreviewStop(jobId, run),
      heartbeat: () => labPreviewHeartbeat(jobId, run)
    },
    deleteOutputs: () => labRunDeleteOutputs(jobId, run)
  }
}

/** A chat session of the Run page: its opened project, else its own workspace folder. Nothing is deletable. */
export function sessionOutputSource(sessionId) {
  return {
    key: `session:${sessionId}`,
    files: () => sessionOutputsFiles(sessionId),
    archiveUrl: () => sessionOutputsArchiveUrl(sessionId),
    accounts: { load: () => sessionAccounts(sessionId), save: (rows) => sessionAccountsSave(sessionId, rows) },
    fileUrl: (path) => sessionOutputsFileUrl(sessionId, path),
    fileText: (path, options) => sessionOutputsFileText(sessionId, path, options),
    siteUrl: (path) => sessionOutputsSiteUrl(sessionId, path),
    open: (path, reveal) => sessionOutputsOpen(sessionId, { path, reveal }),
    preview: {
      start: () => sessionPreviewStart(sessionId),
      status: () => sessionPreviewStatus(sessionId),
      stop: () => sessionPreviewStop(sessionId)
    },
    copy: {
      gone_title: ['launch.products.gone_title', 'Chưa có thư mục kết quả'],
      gone_hint: ['launch.products.gone_hint', 'Nhóm chưa ghi file nào cho phiên này. Khi nhóm tạo mã nguồn, trang web hay tài liệu, chúng sẽ hiện ở đây.'],
      empty_title: ['launch.products.empty_title', 'Thư mục kết quả đang trống'],
      empty_hint: ['launch.products.empty_hint', 'Nhóm chưa tạo file nào. Hãy giao việc trong khung chat, ví dụ "làm trang web giới thiệu sản phẩm".'],
      open_folder_hint: ['launch.products.open_folder_hint', 'Mở thư mục kết quả của phiên trên máy này'],
      tree_label: ['launch.products.tree_label', 'Cây thư mục kết quả']
    }
  }
}
