// Where a product file browser (LabRunOutputs) and its app runner (LabRunPreview) read from.
// A source is an adapter over one product folder:
//   key                     changes when the folder changes (the browser reloads)
//   files()                 -> {available, root, files: [{path, size, kind}], project, ...}
//   fileUrl(path)           raw file URL (img/video src, download, text fetch)
//   fileText(path, {signal})
//   siteUrl(path)           the folder served as a static site (HTML pages with relative assets)
//   open(path, reveal)      open on this machine
//   preview: {start, status, stop, heartbeat?}   "Chạy thử" (heartbeat: optional "still watched" ping)
//   deleteOutputs()         optional: absent = the browser offers no delete
//   copy                    optional: {name: [i18nKey, fallback]} for wording that depends on the context
import {
  labPreviewHeartbeat, labPreviewStart, labPreviewStatus, labPreviewStop, labRunDeleteOutputs, labRunFileText, labRunFileUrl,
  labRunFiles, labRunOpen, labRunSiteUrl,
  sessionOutputsFileText, sessionOutputsFileUrl, sessionOutputsFiles, sessionOutputsOpen, sessionOutputsSiteUrl,
  sessionPreviewStart, sessionPreviewStatus, sessionPreviewStop
} from '@/api/client'

/** One run of a Lab job (storage/warehouse/lab_*); `run` is its run_id (position for older jobs). */
export function labOutputSource(jobId, run) {
  return {
    key: `lab:${jobId}:${run}`,
    files: () => labRunFiles(jobId, run),
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
