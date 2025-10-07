# Gunicorn 配置文件
import os

# 服务器配置
bind = "0.0.0.0:50001"
workers = 4
worker_class = "sync"
worker_connections = 1000
timeout = 300
keepalive = 2

# 进程配置
max_requests = 1000
max_requests_jitter = 100
preload_app = True

# 日志配置
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# 安全配置
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# 开发环境配置
if os.getenv('FLASK_ENV') == 'development':
    reload = True
    loglevel = "debug"
