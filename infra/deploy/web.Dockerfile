FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/user-web/package.json apps/user-web/package.json
COPY apps/admin-web/package.json apps/admin-web/package.json
COPY packages/ packages/
RUN npm ci
COPY tsconfig.json ./
COPY apps/ apps/
COPY scripts/frontend/ scripts/frontend/
COPY backend/src/zhigenews/contracts/openapi.json backend/src/zhigenews/contracts/openapi.json
RUN npm run build && npm run test:api

FROM caddy:2-alpine
COPY infra/deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/apps/user-web/dist /srv/user
COPY --from=build /app/apps/admin-web/dist /srv/admin
