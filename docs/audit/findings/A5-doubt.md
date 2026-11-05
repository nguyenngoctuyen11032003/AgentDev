
# A5-doubt (P1 only, reviewer mới)
- A5-01: CONFIRMED (đỏ, chạy lại bằng test tạm: monkeypatch copytree raise => dest/SKILL.md mất). Sửa: copytree vào tmp cạnh dest, rồi dest->backup, tmp->dest, xóa backup; lỗi thì khôi phục. Test: test_import_overwrite_keeps_old_on_copy_failure.
- A5-02: CONFIRMED-CODE nhưng DOWNGRADED(P2). openEditor (SkillsView.vue:258) không có seq. Nhưng editor là BaseDialog modal nên phải đóng dialog rồi mở B trong lúc A còn tải (backend cục bộ ms) mới dính. Còn lỗi cùng gốc dễ gặp hơn: bấm Lưu khi content còn rỗng (chưa tải xong) => PUT nội dung rỗng. Sửa: openSeq + editor.loading khóa nút Lưu. Test vitest: fetchSkill A trễ, B nhanh, assert content là của B; và Lưu bị disabled khi loading.
