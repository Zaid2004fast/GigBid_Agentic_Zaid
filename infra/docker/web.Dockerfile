FROM node:22-alpine AS build
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci || npm install
COPY apps/web ./
COPY apps/api/openapi.json /api/openapi.json
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /web/dist /usr/share/nginx/html
COPY infra/docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80