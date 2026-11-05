# A6 doubt review (fresh adversarial pass)

Pham vi: chi P1/P0 cua A6.md (chi co A6-01).

## A6-01 (P1) - CONFIRMED-CODE
Tim lai: grep `AUTO_EXPAND_MESSAGES|autoExpand|auto_expand|configStore[` trong frontend/src (bo locales). Chi co: khai bao mac dinh (configStore.js:10, SettingsModal.vue:32), danh sach toggle (GeneralSettings.vue:99), ghi (GeneralSettingsPage.vue:20) va LaunchView.vue:282 (chi nam trong mang khoa `v-memo`). Khong co truy cap khoa dong, khong co consumer khac trong components/launch (khong co state collapse/expand cho tin nhan). Khong co guard nao khien no "co tac dung" -> khong the REFUTE. Day la cong tac gia (chi gay re-render).
Muc do: P1 la hop ly voi quy tac "UI hua suong"; co the DOWNGRADED(P2) vi khong mat du lieu/an toan, nhung giu P1 theo CLAUDE.md (UI khong dua thong tin sai).
Fix nho nhat: bo toggle + khoa store + i18n vi/en/zh + dong v-memo (S); hoac noi co vao mac dinh mo cua tin nhan dai (M).
Test: vitest cho GeneralSettings/configStore khong con khoa (neu bo) va `node scripts/check-i18n.mjs`; neu noi co: test mount message dai voi AUTO_EXPAND_MESSAGES=true -> mac dinh mo (do truoc khi sua).
