FROM python:3.13-alpine


WORKDIR /code

RUN pip install poetry
RUN pip install django

COPY . .
RUN poetry config virtualenvs.create false \
 && poetry install --no-root

COPY . /code
