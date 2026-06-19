# Dani-like Auto TTS Studio

Ứng dụng Windows tạo giọng đọc miễn phí bằng Edge TTS. Project dùng virtual
environment riêng tại `.venv`, nên pip không cài nhầm sang phiên bản Python khác.

## Chạy ứng dụng

Nhấp đúp `run.bat`. Script tự:

1. Chuyển vào đúng thư mục project.
2. Kiểm tra Python Launcher.
3. Tạo `.venv` nếu chưa có.
4. Cài và kiểm tra toàn bộ dependency.
5. Nâng cấp Edge TTS và chứng chỉ `certifi`.
6. Test hai voice Việt.
7. Chạy ứng dụng.

## Chỉ cài thư viện

Nhấp đúp `install.bat`. Script tạo `.venv`, cài requirements và chạy
`test_imports.py`, nhưng không mở app.

## Test nhanh

```bat
.venv\Scripts\python.exe -m compileall .
.venv\Scripts\python.exe test_imports.py
.venv\Scripts\python.exe test_edge_tts.py
```

## Tìm và import voice tiếng Việt

Danh sách mặc định và nút **Load Free Voices** chỉ hiển thị voice có locale
`vi-VN` để giao diện gọn hơn.

Cách dễ nhất:

1. Chọn **Edge TTS Free**.
2. Nhấn **Load Free Voices**.
3. Chọn một voice Việt Nam trong danh sách.

Tìm voice bằng Terminal:

```bat
.venv\Scripts\python.exe -m edge_tts --list-voices | findstr vi-VN
```

Sau đó nhấn **Import Voice** và dán nguyên mã voice. Ví dụ:

```text
vi-VN-HoaiMyNeural
vi-VN-NamMinhNeural
```

Khi cần dùng voice nước ngoài, bạn vẫn có thể tự nhập mã bằng **Import Voice**,
ví dụ `en-US-GuyNeural`. Voice vừa import sẽ được thêm vào danh sách hiện tại.

File test Edge TTS:

```text
output\test_hoaimy.mp3
output\test_namminh.mp3
```

## Cơ chế không mất audio

- `DONE`: Edge TTS thành công.
- `DONE_WITH_FALLBACK`: Edge TTS lỗi nhưng gTTS tạo audio thành công.
- `SILENT_FALLBACK`: Edge TTS và gTTS đều lỗi, app tạo silent audio thay thế.
- `ERROR`: chỉ khi không thể tạo bất kỳ audio nào hoặc không ghi được output.

Edge TTS gọi lần đầu và retry tối đa 5 lần với thời gian chờ tăng dần
1, 2, 4, 6 và 8 giây, sau đó chuyển sang gTTS rồi silent audio.

## Import nhiều voice Piper offline

Piper chạy hoàn toàn trên máy, không cần API và không tính phí. Mỗi voice cần
hai file đặt cạnh nhau:

```text
ten_voice.onnx
ten_voice.onnx.json
```

Cách dùng:

1. Chọn engine **Piper Offline**.
2. Nhấn **Import Piper Model**.
3. Chọn file `.onnx`.
4. Đặt tên hiển thị rồi nhấn OK.
5. Chọn voice vừa import và nhấn Start.

App sao chép model vào `voices\piper` và lưu lại để dùng ở những lần mở sau.
Có thể import nhiều model. Nút **Remove Piper Model** xóa model đang chọn khỏi
thư viện.

Nguồn model chính thức:

- Piper hiện hành: https://github.com/OHF-Voice/piper1-gpl
- Kho model: https://huggingface.co/rhasspy/piper-voices/tree/main
- Nghe mẫu: https://rhasspy.github.io/piper-samples/

Hãy kiểm tra giấy phép của từng model và chỉ dùng giọng bạn có quyền sử dụng.
Piper xuất WAV nội bộ; app tự chuyển sang MP3 khi pydub/ffmpeg hoạt động. Nếu
không chuyển được, file WAV vẫn được giữ lại thay vì mất audio.

## Local Voice Clone: thêm nhiều giọng từ WAV/MP3

Đây là chế độ phù hợp nhất để có nhiều giọng Việt mà không dùng API trả phí.
App dùng Edge TTS tạo phát âm tiếng Việt, sau đó OpenVoice chạy local để chuyển
màu giọng theo file mẫu.

Cài runtime một lần:

```text
install_openvoice.bat
```

Runtime dùng Python 3.9 riêng tại `D:\AutoTTS_OpenVoice`, không ảnh hưởng `.venv`
của app. Máy không có NVIDIA vẫn chạy được bằng CPU nhưng mỗi đoạn sẽ chậm hơn.

Cách thêm voice:

1. Chuẩn bị WAV/MP3 giọng mẫu dài khoảng 10–30 giây.
2. Audio nên chỉ có một người nói, rõ tiếng, ít vang và không có nhạc nền.
3. Chọn engine **Local Voice Clone**.
4. Nhấn **Import WAV/MP3 Voice**.
5. Đặt tên và chọn voice vừa thêm.
6. Import TXT/SRT rồi nhấn Start.

Có thể import gần như không giới hạn voice. Các file được lưu trong
`voices\references`. Nút **Remove Clone Voice** xóa voice đang chọn.

Khi import, app tự:

- đổi file về mono WAV 22050 Hz ổn định cho OpenVoice;
- cắt khoảng lặng dài ở đầu/cuối và giữ phần nói rõ nhất;
- lọc bớt tiếng ù trầm, giảm nhiễu gắt và chuẩn hóa âm lượng;
- giới hạn voice mẫu khoảng 25 giây để clone ổn định hơn.

Muốn độ giống cao hơn, hãy ghi một đoạn nói đều giọng, không nhạc nền, không vang,
ít nhất 10 giây và tốt nhất là 15–25 giây.

Chỉ sử dụng giọng của bạn hoặc giọng đã được chủ sở hữu cho phép. Kết quả clone
phụ thuộc mạnh vào chất lượng audio mẫu; đây là công cụ đổi màu giọng, không bảo
đảm sao chép tuyệt đối danh tính giọng nói.

## XTTS Local: giống hơn nhưng chậm hơn

XTTS Local là hướng clone giọng sâu hơn Local Voice Clone, nên tiềm năng giống hơn
 khi dùng ngôn ngữ mà XTTS hỗ trợ. Đổi lại, runtime nặng hơn và chạy CPU khá chậm.

Cài runtime một lần:

```text
install_xtts.bat
```

Cách dùng:

1. Chọn engine **XTTS Local**.
2. Chọn **Language = English**.
3. Nhấn **Import WAV/MP3 Voice** để thêm voice mẫu.
4. Import file TXT/SRT rồi nhấn Start.

Lưu ý quan trọng:

- XTTS trong bản tích hợp hiện tại chưa phải đường tốt cho tiếng Việt.
- Nếu bạn làm nội dung tiếng Việt, hãy tiếp tục dùng **Local Voice Clone**.
- Nếu bạn làm nội dung tiếng Anh hoặc ngôn ngữ XTTS hỗ trợ, XTTS thường cho độ giống cao hơn.

Test runtime XTTS:

```text
.venv\Scripts\python.exe test_xtts_runtime.py
```

## Output mặc định

App ưu tiên:

```text
D:\AutoTTS_Output
```

Nếu ổ D không tồn tại hoặc không ghi được, app tự dùng thư mục `output` trong
project.

## Xem lỗi

Lỗi hiển thị trong log box và cột Error. Full traceback được ghi tại:

```text
logs\error.log
```

Log gồm thời gian, file/function, exception và traceback.

## Nối MP3 và pydub

Nối MP3 cần `pydub` và `ffmpeg`. Nếu thiếu pydub, app chỉ báo:
“Thiếu pydub nên chưa thể nối MP3” và không làm hỏng các dòng đã DONE.
Trên Python 3.13/3.14, project cài thêm `audioop-lts` để pydub hoạt động.

Cài ffmpeg:

```bat
winget install Gyan.FFmpeg
```

Nếu pydub hoặc ffmpeg không dùng được khi tạo silent MP3, app thử ffmpeg trực
tiếp, sau đó fallback sang silent WAV bằng module `wave` chuẩn Python.
