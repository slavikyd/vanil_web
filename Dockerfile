FROM python:3.12

WORKDIR /app

COPY . .
RUN pip install poetry && poetry install --no-root

COPY . /app

CMD ["poetry", "run", "uvicorn", "bot.web_app:app", "--host", "0.0.0.0", "--port", "8000"]
