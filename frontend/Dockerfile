# Afe web frontend (SvelteKit, Node server). Talks to the API at AFE_API_URL.
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build && npm prune --omit=dev

FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    BODY_SIZE_LIMIT=20M
COPY --from=build /app/build build
COPY --from=build /app/node_modules node_modules
COPY package.json .
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/ >/dev/null || exit 1
# Set ORIGIN (the public https URL) and AFE_API_URL at run time.
CMD ["node", "build"]
