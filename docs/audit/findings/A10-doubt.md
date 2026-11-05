
# A10 doubt review (P1 only: A10-04)

- A10-04: CONFIRMED-CODE (khong reproduce song, khong khoi dong server). Bang chung: ConfirmHost.vue:87 va BaseDialog.vue:151 deu `z-index: var(--z-modal)` (1100, main.css:21), ca hai Teleport to="body"; ConfirmHost mount som o App.vue:39 nen node cua no nam truoc dialog mo sau trong body, cung z-index thi dialog (DOM sau) de len confirm. Khop log phase0-e2e.md P0-E2E-01. Khong guard/caller nao lam no unreachable.
  Fix nho nhat: main.css them `--z-confirm: 1150` (< --z-toast 1200), ConfirmHost dung token do; sau do thay calc(z-modal+N) o FormGenerator/LocalFolderPicker/DynamicFormField neu cac lop do can nam tren/duoi confirm.
  Regression test (red truoc): Playwright mo BaseDialog (vd Skills/Connections) -> goi confirm() -> `document.elementFromPoint` tai tam nut xac nhan phai nam trong `.confirm`; them unit test doc main.css khang dinh --z-confirm > --z-modal va < --z-toast.
- Khong co P0 nao trong A10.
