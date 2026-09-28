---
name: kich-ban-truyen-ma
description: >-
  Viết kịch bản truyện ma kể miệng (giọng Nam, chen “mọi người”) rồi xuất
  md + JSON TTS trong kich-ban/. Dùng khi user bảo gen truyện, tự tạo chuyện,
  làm kịch bản, làm tương tự, sửa result.json / whisper-jax, hoặc cần file
  cho VieNeu / kênh YouTube riêng.
---

# Kịch bản truyện ma (TTS + kênh riêng)

## Khi nào làm gì

1. **Có `result.json` / transcript STT** → đọc hết chữ, bỏ đoạn máy bịa (câu lặp), sửa từ sai theo ngữ cảnh, rồi **viết lại** thành kịch bản gốc (đổi tên người/chỗ/năm). Không chép nguyên lời kênh nguồn.
2. **Không có transcript, user bảo tự tạo / gen truyện** → tự nghĩ cốt (dân gian VN, nhân quả, đêm rừng, nhà quê, nghề cũ). Đủ đầu đuôi ~8–20 phút đọc. Hỏi theme nếu user đã nói (ma trành, lồng đèn, bùa, nhà trọ…). Không hỏi nếu đã đủ ý.
3. **User nói “làm tương tự”** → cùng quy trình với file STT / chủ đề mới, không làm lại tập đã có.

Không quan tâm timestamp. Được xóa hẳn câu ảo. Không commit `.webm` / `.m4a` / `yt-dlp.exe`.

## Giọng kể (bắt buộc)

Giống hai file mẫu: `kich-ban/kich-ban-ma-tranh.md`, `kich-ban/kich-ban-long-den.md`.

- Kể miệng: câu ngắn, “mọi người”, “nè”, “ta nói”, chen lời giữa truyện.
- Một giọng dẫn `mình`. Frame: bạn X gửi chuyện / ông bà kể.
- Hook mở (khái niệm sợ) → chào kênh → vào chuyện → climax → nhân quả → outro.
- Tiếng Việt Nam Bộ. Số viết chữ khi đọc TTS (`mười bảy`, không `17`) trừ năm (`năm 1990`).

**Cấm:** tên hoặc câu cửa miệng kênh khác (Lê Huy An, Nguyễn Huy, “Hé!”, kêu sub kênh họ). Folklore công (ma trành, cọp ba móng) dùng được; cốt + lời phải là bản mình.

## Tự tạo chuyện

Tự chọn (đừng trùng tập đã có trong `kich-ban/`):

- Nơi: Tây Nguyên, miền Tây, phố cũ, chợ, rẫy, suối, nhà chữ U…
- Xương: lời nói cứng quay lại / nghề thất đức / giả giọng người thương / đồ lấy của người chết / đêm im đột ngột.
- Nhân vật tên mới mỗi tập. 1–2 người gửi chuyện + ông/bà nội + 1 “người biết” (thầy, già làng).
- Kết có nhân quả, không mở ending trừ user xin.

## File xuất

Ghi vào `kich-ban/` (repo C-Tools):

| File | Nội dung |
|------|----------|
| `kich-ban-<slug>.md` | Tiêu đề + 2–3 dòng ghi chú + `---` + truyện (mỗi ý 1–3 câu, cách nhau dòng trống) |
| `kich-ban-<slug>.json` | `{ source, speakers: ["SPEAKER_00"], segments: [{speaker, text, id}] }` — mỗi đoạn md = 1 segment, `id` = `s0000`… |

JSON để kéo vào tab TTS C-tool. Một speaker trừ user xin 2 giọng.

Outro mặc định (đổi nếu user đưa tên kênh):

- Cảm ơn bạn đã gửi chuyện.
- Chúc khỏe, bình an.
- Đăng ký kênh ủng hộ dùm mình. Like, chia sẻ, chuông.
- Có chuyện tâm linh thì gửi về. Xin chào, hẹn gặp lại.

## Việc không làm

- Không dịch Anh. Không tóm tắt thay vì viết full kịch bản.
- Không để chữ `you` / rác STT cuối file.
- Không push trừ user bảo push.
