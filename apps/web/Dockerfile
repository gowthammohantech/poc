FROM node:22-slim

WORKDIR /app/apps/web

# node:22-slim ships npm 10.9.8, whose arborist crashes resolving this
# dependency tree with "Cannot read properties of null (reading 'edgesOut')".
# npm 11 resolves the same tree without complaint.
RUN npm install -g npm@11

# This branch keeps a single lockfile at the workspace root, so the web app is
# installed standalone from its own package.json.
COPY package.json ./
RUN npm install

COPY . ./
RUN npm run build

ENV NODE_ENV=production

EXPOSE 3000

CMD ["npm", "run", "start"]
