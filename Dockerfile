FROM alfg/ffmpeg

WORKDIR /app

RUN apk add --no-cache --virtual .build-deps alpine-sdk gcc g++ make linux-headers
RUN apk add --no-cache sox python3 python3-dev py3-pip
RUN chown -R 1000:1000 /app

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt
COPY audiovoodoo.py audiovoodoo.py

CMD ["/usr/bin/python3", "audiovoodoo.py"]
