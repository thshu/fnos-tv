﻿FROM python:3.12-slim


COPY change-source.sh /change-source.sh
RUN chmod +x /change-source.sh
RUN sh /change-source.sh

# 安装必要工具
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      nginx \
      supervisor \
      gettext-base && \
    rm -rf /var/lib/apt/lists/*

# 创建工作目录
WORKDIR /app

ARG FNOS_URL
ENV FNOS_URL=${FNOS_URL}

# 复制并安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制 Flask 应用及静态资源
COPY . .

# 复制 nginx 和 supervisor 配置
COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# 复制启动脚本
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 暴露 HTTP 端口
EXPOSE 80

# 启动 supervisor（它会同时拉起 nginx 和 gunicorn）
ENTRYPOINT ["/entrypoint.sh"]
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
