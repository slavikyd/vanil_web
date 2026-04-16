FROM python:3.13-alpine

RUN apk add --no-cache socat

WORKDIR /code

RUN pip install poetry

COPY . .
RUN poetry config virtualenvs.create false \
 && poetry install --no-root

COPY . /code
