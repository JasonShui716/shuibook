FROM node:20-alpine AS deps
ARG NEXT_PUBLIC_API_URL
ARG API_INTERNAL_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV API_INTERNAL_URL=${API_INTERNAL_URL}
WORKDIR /app
COPY web/package.json ./
RUN npm install
COPY web ./
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=deps /app/.next/standalone ./
COPY --from=deps /app/.next/static ./.next/static
COPY --from=deps /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
