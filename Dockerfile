FROM python:3.12

WORKDIR /code

RUN pip install poetry

COPY . .
RUN poetry config virtualenvs.create false \
 && poetry install --no-root

COPY . /code
