#!/bin/sh
input="$1"
output="$2"
magick "${input}" -strip -quality 50 -resize 300x200^ -gravity center -extent 300x200 "${output}"
