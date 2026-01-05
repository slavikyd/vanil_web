FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./

RUN npm config set fetch-retries 5 \
 && npm config set fetch-retry-mintimeout 20000 \
 && npm config set fetch-retry-maxtimeout 120000

RUN npm install react@^18.2.0
RUN npm install react-dom@^18.2.0

RUN npm install axios@^1.6.0



COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
