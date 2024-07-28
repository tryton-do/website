from node:20
LABEL maintainer="Tryton <foundation@tryton.org>" \
    org.label-schema.name="Tryton" \
    org.label-schema.url="http://www.tryton.org/" \
    org.label-schema.vendor="Tryton"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libasound2 \
        libatk-bridge2.0 \
        libgtk-3-0 \
        libnss3 \
        libx11-xcb1 \
        libxss1 \
        libxtst6 \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g critical

COPY critical.sh /
CMD ["/critical.sh"]
