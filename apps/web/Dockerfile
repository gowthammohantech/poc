FROM node:22-slim

WORKDIR /app/apps/web

COPY package.json package-lock.json ./
RUN npm ci

COPY . ./
RUN npm run build

ENV NODE_ENV=production

EXPOSE 3000

CMD ["npm", "run", "start"]
