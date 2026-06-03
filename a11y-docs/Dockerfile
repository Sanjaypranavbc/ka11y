FROM node:24-slim

WORKDIR /docs

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @mintlify/cli@4.0.1049

COPY . /docs

EXPOSE 3000

CMD ["mintlify", "dev", "--no-open"]
