FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/BrentClothier/Playbooks"
LABEL org.opencontainers.image.description="Read-only HomeLab MCP server"

WORKDIR /app

RUN addgroup --system mcp \
    && adduser --system --ingroup mcp mcp

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=mcp:mcp server.py .

USER mcp

EXPOSE 8000

CMD ["python", "server.py"]
