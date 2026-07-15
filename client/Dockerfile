FROM docker.m.daocloud.io/library/nginx:1.27-alpine

EXPOSE 3002

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY dist /usr/share/nginx/html

HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1:3002/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
