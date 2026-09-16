FROM node:22-slim

WORKDIR /app/apps/web

# This branch keeps a single lockfile at the workspace root, so the web app is
# installed standalone from its own package.json.
COPY package.json ./
RUN npm install

COPY . ./
RUN npm run build

ENV NODE_ENV=production

EXPOSE 3000

CMD ["npm", "run", "start"]
