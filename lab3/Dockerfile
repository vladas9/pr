FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
COPY tsconfig.json ./

RUN npm ci

COPY src/ ./src/
COPY test/ ./test/
COPY board/ ./board/
COPY public/ ./public/

RUN npm run compile

EXPOSE 8080

CMD ["node", "dist/src/server.js", "8080", "board/ab.txt"]