---
name: kich-ban-truyen-ma
description: >-
  Viết kịch bản truyện ma kể miệng (giọng Nam, chen “mọi người”) rồi xuất
  md + JSON TTS trong kich-ban/. JSON series nhiều tập thì gộp một kịch bản,
  chào một lần, sắp theo dòng thời gian, tách chuyện không liên quan ra file
  mới, kể đủ chi tiết, giữ tên series. Tự gợi ý chủ đề (không hỏi user theme).
  Dùng khi gen truyện, gợi ý truyện, tự tạo chuyện, truyện dài, làm kịch bản,
  làm tương tự, series, nhiều tập, ghép json, dòng thời gian, bảy gạo,
  sửa result.json / whisper-jax, hoặc file VieNeu / kênh YouTube.
---

# Kịch bản truyện ma (TTS + kênh riêng)

Bản cho **Cursor**. Claude Code dùng file giống tại `.claude/skills/kich-ban-truyen-ma/SKILL.md` — giữ hai file cùng nội dung khi sửa.

## Khi nào làm gì

1. **Có `result.json` / transcript STT của một chuyện** → đọc hết chữ, bỏ đoạn máy bịa (câu lặp), sửa từ sai theo ngữ cảnh, rồi **viết lại** thành kịch bản gốc (đổi tên người/chỗ/năm). Không chép nguyên lời kênh nguồn. Độ dài bám nguồn; user bảo rút/dài thêm thì theo user.
2. **JSON là series nhiều tập** (nhiều video ghép, user nói series / nhiều tập / kể hết / kiểu bảy gạo) → mục **Series nhiều tập**. Không đổi tên nhân vật của series. Không áp bảng độ dài mặc định.
3. **Không có transcript** (gen / tự tạo / `/kich-ban-truyen-ma` / gợi ý truyện) → **không hỏi theme**. Làm mục **Gợi ý truyện**. Độ dài theo **Độ dài**.
4. **User nói “làm tương tự”** → cùng quy trình với file STT / chủ đề mới, không làm lại tập đã có. “Tương tự bảy gạo” trên một JSON khác = áp mục Series, không viết lại file bảy gạo.

Không quan tâm timestamp. Được xóa hẳn câu ảo. Không commit `.webm` / `.m4a` / `yt-dlp.exe`.

## Series nhiều tập

Khi nguồn là **nhiều tập của một series** ghép trong một JSON:

1. **Một kịch bản** kể hết mọi tập của series. Không tách mỗi tập thành một file.
2. **Giới thiệu một lần.** Một hook, một lời chào kênh, một outro cuối file. Không lặp chào hay outro theo từng tập trong JSON.
3. **Sắp theo dòng thời gian** của chuyện (ai trước, việc nào xảy ra trước). Bỏ thứ tự JSON và thứ tự playlist.
4. **Chuyện khác không dính series** (chen giữa các tập) → **tách file mới** `kich-ban-<slug>.md` + JSON. Mỗi file tách có intro và outro riêng. Cùng họ, cùng mạch (cảnh bên, hồi kết, người nhà) thì **ở lại** file chính. Thấy đoạn không liên quan mà còn nằm trong file series thì tách tiếp.
5. **Kể chi tiết.** Không rút ngắn so với JSON nguồn. Thiếu tình tiết là sai. Vẫn chia đoạn 1–3 câu miệng cho TTS. Không nhét thành vài khối văn dài.
6. **Giữ tên** người, chỗ, năm của series đúng nguồn. Không đổi tên cho ra bản “gốc” khi user đang kể đúng series đó. Chuyện đã tách (không thuộc series) thì viết lại và đổi tên như mục STT một chuyện.
7. **Năm phải khớp.** Ai mất năm nào thì không còn đi lại sau năm đó. Sắp xong thì đọc lại từng mốc năm.
8. **Lời kể nghe một lần là hiểu**, mạch liền, câu miệng. Cấm chữ văn chương khó hiểu (kiểu “dòng họ lụi tàn”, “vỡ”). Cấm câu cụt, cụt ý. Nói về truyện thì **“chuyện này”**, không “lời này”.
9. Nguồn do nhiều người kể: ngay sau lời chào, một câu — chuyện này mình tham khảo từ nhiều nguồn, từ cộng đồng, và từ họ hàng xa của người kể trong chuyện (điền đúng vai, ví dụ họ hàng xa của ông Ba). Không bịa nguồn nếu JSON không có.

Độ dài series = bám nguồn, **không** dùng bảng 90–140 đoạn. Ghi chú trên md: `Series: một mạch, chào một lần`.

Mẫu: `kich-ban/kich-ban-bay-gao.md`. File tách mẫu: `kich-ban-ba-tu`, `kich-ban-tro-nui-sap`.

## Gợi ý truyện (bắt buộc)

Mỗi lần chạy skill **không được** hỏi “muốn kể chuyện gì?”.

1. Liệt kê file `kich-ban/kich-ban-*.md` đã có — **cấm trùng** slug/chủ.
2. Lấy **5 gợi ý** chưa làm từ kho dưới (hoặc biến thể mới nếu kho hết). Mỗi dòng: **tên tập** — một câu móc (chỗ + xương).
3. **Chỉ gợi ý** / “đừng viết” → dừng sau 5 dòng. Không viết file.
4. Còn lại (kể cả user không nói chủ đề) → **viết luôn 1 tập**: ưu tiên chủ user nêu; không nêu thì lấy gợi ý số 1. Mở chat bằng `Tập này: …` rồi xuất md + JSON.
5. **Cuối tin** (sau khi viết file) lại in **5 gợi ý tập sau** (khác tập vừa viết). User chỉ cần “làm cái 3” / “làm cái cầu”.

Kho (bỏ mọi slug đã có file trong `kich-ban/`, kể cả bảy gạo, bà Tư, trọ Núi Sấp, ma trành, lồng đèn, nhà trọ Đà Lạt):

- Cầu khỉ miền Tây — lời thề, đêm nước lớn, giả giọng người nhà bên kia sông
- Nhà thờ họ / nhà từ — lấy đồ cúng, bóng áo dài gọi tên
- Xe khách đêm đèo Hải Vân — ghế số âm, tài xế nghe gọi dừng
- Giếng làng — bịt miệng vụ đuối, gọi từ dưới giếng
- Thợ ảnh đám cưới — ảnh thừa một người, chủ studio giấu xác
- Rẫy cà phê Ban Mê — chủ rẫy cắm bẫy người, ma trành / giả giọng vợ
- Phòng trọ Sài Gòn gác lửng — chủ giữ cọc người chết, gõ trần
- Chợ nổi / vựa lúa — cân gian, vong đòi sổ
- Nghĩa địa mới dời — xây nhà trên mộ, trẻ chỉ người ngoài cửa
- Tàu thủy / bến phà — áo mưa gọi xuống nước
- Lò gạch / lò than — nung đồ của người, đêm nghe thổi lửa
- Trường cấp ba nghỉ hè — phòng trực, sổ điểm danh thừa tên
- Người giữ rừng / kiểm lâm — lấy sừng, đêm hú theo giọng đồng đội
- Tiệm vàng phố cũ — nuốt vòng khách, tủ két kêu đêm
- Máy khoan giếng — trúng huyệt mả, nước lên đen

Viết tập mới: đổi tên người, năm, xã; không copy nguyên câu kho. Hết kho thì tự bịa cùng kiểu (chỗ VN + nghề thất đức / giả giọng / lấy đồ người chết).

## Độ dài

Mặc định (user không nói, và **không** phải series): **vừa** — khoảng 90–140 đoạn JSON, đọc ~15–22 phút. Không viết tập siêu ngắn kiểu 30–40 đoạn trừ user xin ngắn. Series nhiều tập: bám nguồn, xem mục **Series nhiều tập**.

| User nói | Đọc (ước lượng) | JSON | Cách viết |
|----------|-----------------|------|-----------|
| ngắn, clip | ~8–12 phút | 50–80 đoạn | 1 tuyến, 1 đêm, ít nhân vật |
| *(không nói)* / vừa | ~15–22 phút | 90–140 | 2–3 cảnh lớn, 1 người biết |
| **dài**, tập dài, như ma trành | ~30–45 phút | **160–220** | nhiều năm, nhiều nạn, giả giọng, khai tội, nhân quả |
| rất dài, 1 tiếng, full | ~50–70 phút | 220+ hoặc **tách phần** | xem dưới |

Trigger dài: `dài`, `tập dài`, `viết dài`, `như ma trành`, `40 phút`, `1 tiếng`. Ghi dòng chú thích trên md: `Độ dài: dài (~35 phút)`.

**Tập dài bắt buộc có** (không được nhảy cóc):

- Đời thường / nghề / làng (dài hơn hook)
- Lời nói cứng hoặc nghề thất đức
- Chuỗi hậu quả (mất người, dấu vết, đi lùng)
- 1–2 nạn nhân có tên, chi tiết đồ / gia đình
- Đêm rừng hoặc nhà: im đột ngột, giả giọng
- Người biết (thầy, già làng) giải
- Khai / trả đồ / chôn cất
- Nhân quả người gây chuyện + outro

Mẫu độ dài: `kich-ban/kich-ban-ma-tranh.md` (dài). Đừng lấy `kich-ban-nha-tro-da-lat.md` làm chuẩn dài.

**Rất dài / 1 tiếng:** một lần chat không nhét hết chất lượng. Viết **phần 1** đủ outro tạm *“phần sau mình kể tiếp”* chỉ khi user xin nhiều tập. Không thì file `kich-ban-<slug>-p1.md` + p2, JSON riêng từng phần (TTS Studio gen từng file). Phần 2 không mở lại hook kênh dài; “kể tiếp”, nhân vật cũ.

Đoạn md = 1–3 câu miệng. Tập dài = **nhiều đoạn**, không phải vài khối văn dài (TTS VieNeu dễ vỡ).

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
- Kết có nhân quả, không mở ending trừ user xin nhiều tập / phần 2.

## File xuất

Ghi vào `kich-ban/` (repo C-Tools):

| File | Nội dung |
|------|----------|
| `kich-ban-<slug>.md` | Tiêu đề + 2–3 dòng ghi chú (kèm độ dài) + `---` + truyện (mỗi ý 1–3 câu, cách nhau dòng trống) |
| `kich-ban-<slug>.json` | `{ source, speakers: ["SPEAKER_00"], segments: [{speaker, text, id}] }` — mỗi đoạn md = 1 segment, `id` = `s0000`… |

JSON để kéo vào TTS Studio / tab TTS. Một speaker trừ user xin 2 giọng. Mỗi đoạn tối đa khoảng 260 ký tự, tối đa 3 câu. Số đọc thành chữ (`mười bảy`), năm giữ số (`năm 1990`).

Outro mặc định (đổi nếu user đưa tên kênh):

- Cảm ơn bạn đã gửi chuyện.
- Chúc khỏe, bình an.
- Đăng ký kênh ủng hộ dùm mình. Like, chia sẻ, chuông.
- Có chuyện tâm linh thì gửi về. Xin chào, hẹn gặp lại.

## Việc không làm

- Không dịch Anh. Không tóm tắt thay vì viết full kịch bản. User xin dài mà ra bản ngắn là sai skill. Series mà cắt ngắn so với JSON nguồn là sai skill.
- Không để chuyện không liên quan nằm trong file series.
- Không để chữ `you` / rác STT cuối file.
- Không push trừ user bảo push.
