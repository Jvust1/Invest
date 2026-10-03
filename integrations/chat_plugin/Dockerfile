FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN python -m pip install --no-cache-dir '.[chat]'
RUN useradd --uid 10001 --create-home invest
USER invest
EXPOSE 8787
# A public deployment must inject OAuth resource/issuer/JWKS/owner configuration.
CMD ["python", "-m", "invest.chat.mcp_server", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8787"]
