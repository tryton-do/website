#!/bin/sh
input="$1"
output="$2"
filename=$(basename -- "${input}")
filename="${filename%.*}"
magick "${input}" -strip -quality 50 -resize 1920x500^ -gravity center -extent 1920x500 "${output}/${filename}.webp"
magick "${input}" -strip -quality 50 -resize 800x208^ -gravity center -extent 800x208 "${output}/${filename}-800px.webp"
magick "${input}" -strip -quality 50 -resize 400x104^ -gravity center -extent 400x104 "${output}/${filename}-400px.webp"
