# node-sass is not yet ready for node 16
# https://github.com/sass/node-sass/issues/3077
FROM node:20 as builder-node

ENV INSTALL_PATH /web
RUN mkdir -p $INSTALL_PATH

WORKDIR $INSTALL_PATH
COPY package.json  gulpfile.js ./
COPY js js/
COPY sass sass/
RUN npm install
RUN npx gulp

FROM debian:11-slim
LABEL maintainer="Tryton <foundation@tryton.org>" \
    org.label-schema.name="Tryton" \
    org.label-schema.url="http://www.tryton.org/" \
    org.label-schema.vendor="Tryton"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-setuptools \
        uwsgi \
        uwsgi-plugin-python3 \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --no-log-init -r -M web

ENV INSTALL_PATH /web
RUN mkdir -p $INSTALL_PATH

WORKDIR $INSTALL_PATH
COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app.py uwsgi.conf ./
COPY check-running ./
COPY templates templates/
COPY static/fonts static/fonts/
COPY static/images static/images/
COPY --from=builder-node $INSTALL_PATH/static/css static/css/
COPY --from=builder-node $INSTALL_PATH/static/js static/js/

EXPOSE 5000
USER web
CMD uwsgi --ini uwsgi.conf
