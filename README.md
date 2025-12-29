Luồng hoạt động đầy đủ trong hệ thống:

1. Container khởi động → entrypoint.sh xóa và tạo mới thư mục PROMETHEUS_MULTIPROC_DIR.
2. Gunicorn khởi động → fork ra nhiều worker (mỗi worker có PID riêng).
3. Mỗi worker ghi metrics vào file riêng trong thư mục đó.
4. Khi một worker chết (ví dụ do timeout request dài, hoặc bạn reload Gunicorn):
5. Hook child_exit được gọi.
6. mark_process_dead(worker.pid) chạy → file metrics của worker đó được đánh dấu "dead" và không còn được gộp nữa.
8. Prometheus scrape /metrics → chỉ thấy metrics từ các worker đang sống → chính xác 100%.