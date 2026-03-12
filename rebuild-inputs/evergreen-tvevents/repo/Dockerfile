FROM python:3.10-bookworm@sha256:33f72df2ad8c9f777bf0adb35b9d89c5d62935cee2af1f9c3224fb6f7da1dc6b

WORKDIR /var/www/tvevents

RUN apt-get update && \
    apt-get install --no-install-recommends -y libpam-modules=1.5.2-6+deb12u1 \
        libpam-modules-bin=1.5.2-6+deb12u1 \
        libpam-runtime=1.5.2-6+deb12u1 \
        libpam0g=1.5.2-6+deb12u1 \
        libc6=2.36-9+deb12u10 \
        libglib2.0-0=2.74.6-2+deb12u6 \
        wget=1.21.3-1+deb12u1 \
        libfreetype6=2.12.1+dfsg-5+deb12u4 \
        libopenjp2-7=2.5.0-2+deb12u1 \
        libtiff6=4.5.0-6+deb12u2 \
        libicu-dev=72.1-3+deb12u1 \
        libxml2=2.9.14+dfsg-1.3~deb12u4 \
        libgdk-pixbuf-2.0-0=2.42.10+dfsg-1+deb12u2 \
        libdjvulibre21=3.5.28-2.1~deb12u1 \
        && rm -rf /var/lib/apt/lists/*

RUN apt-get purge -y \
    imagemagick \
    binutils \
    gcc-12 \
    patch \
    m4 \
    git \
    libxslt1.1 \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY ./app ./app
COPY ./cntools_py3/cnlib ./cnlib
COPY ./requirements.txt ./requirements.txt

# Resolve CVE-2023-5752
RUN pip install --no-cache-dir --upgrade pip==24.3.1
ENV PYTHON_PIP_VERSION=24.3.1

# Resolve CVE-2022-40897 & CVE-2024-6345
RUN pip install --no-cache-dir --upgrade setuptools==78.1.1
ENV PYTHON_SETUPTOOLS_VERSION=78.1.1

# Install Requirements and CN Tools Repo
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /var/www/tvevents/cnlib
RUN python setup.py install
WORKDIR /var/www/tvevents

ENV PYTHONUNBUFFERED=1

RUN pip show cnlib
RUN opentelemetry-bootstrap

COPY entrypoint.sh /usr/local/bin/
COPY environment-check.sh /usr/local/bin/

RUN chmod +x /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/environment-check.sh

EXPOSE 8000
ENV FLASK_APP="app"
ENV BLACKLIST_CHANNEL_IDS_CACHE_FILEPATH="/tmp/.blacklisted_channel_ids_cache"
ENV OTEL_EXPORTER_OTLP_COMPRESSION="gzip"
ENV FLASK_ENV=tvevents-k8s

# Make sure we are not running the contianer as the default root user.
RUN groupadd -r -g 10000 flaskuser
RUN useradd -r -u 10000 -g flaskuser -d /home/flaskuser flaskuser
RUN mkdir -p /home/flaskuser
RUN chown -R flaskuser:flaskuser /home/flaskuser
RUN chown -R flaskuser:flaskuser /var/www/tvevents
RUN touch /tmp/.dummy_blacklisted_channel_ids_cache

VOLUME ["/var/log"]
USER flaskuser

HEALTHCHECK --interval=30s --timeout=10s --retries=3 CMD curl -fs http://localhost/status || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
