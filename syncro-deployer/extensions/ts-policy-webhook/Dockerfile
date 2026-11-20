FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json tsconfig.json ./
RUN npm install
COPY src ./src
COPY tests ./tests
RUN npm run build

FROM node:22-alpine
RUN addgroup -g 10001 aegis && adduser -u 10001 -G aegis -D aegis
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY package.json ./
USER 10001:10001
EXPOSE 9102
CMD ["node", "dist/src/index.js"]
