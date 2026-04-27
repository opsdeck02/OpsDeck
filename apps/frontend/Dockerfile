FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
COPY apps/frontend/package.json ./apps/frontend/package.json
COPY packages/contracts/package.json ./packages/contracts/package.json

RUN npm install

COPY apps/frontend ./apps/frontend
COPY packages/contracts ./packages/contracts

WORKDIR /app/apps/frontend

EXPOSE 3000

