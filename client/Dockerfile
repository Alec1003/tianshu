FROM node:20-alpine AS build

WORKDIR /app

ENV NPM_CONFIG_REGISTRY=https://registry.npmmirror.com

ARG VITE_ENV=standalone
ARG VITE_API_SERVER_URL=
ARG VITE_AI_SERVER_URL=
ARG VITE_CESIUM_ION_TOKEN=

ENV VITE_ENV=$VITE_ENV \
    VITE_API_SERVER_URL=$VITE_API_SERVER_URL \
    VITE_AI_SERVER_URL=$VITE_AI_SERVER_URL \
    VITE_CESIUM_ION_TOKEN=$VITE_CESIUM_ION_TOKEN

COPY package*.json ./
RUN npm install --registry=https://registry.npmmirror.com --no-audit --no-fund

COPY . .
RUN npm run build

FROM docker.m.daocloud.io/library/nginx:1.27-alpine

EXPOSE 3002

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1:3002/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
