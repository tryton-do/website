#!/bin/bash

set -e

: ${OUTPUT:='/tmp'}
: ${SERVER_NAME:='localhost'}

for page in \
    "/ index" \
    "/success-stories success_stories" \
    "/success_stories/_ success_story" \
    "/download download" \
    "/forum forum" \
    "/presentations presentations" \
    "/events/_ event" \
    "/contribute contribute" \
    "/develop develop" \
    "/develop/guidelines/code guidelines_code" \
    "/develop/guidelines/documentation guidelines_documentation" \
    "/develop/guidelines/help-text guidelines_documentation_help" \
    "/develop/guidelines/howto guidelines_documentation_howto" \
    "/foundation foundation" \
    "/supporters supporters" \
    "/donate donate" \
    "/service-providers service_providers" \
    "/service-providers/start service_providers_start" \
    "/not_found not_found"
do
    set -- ${page}
    critical http://${SERVER_NAME}${1} --width 1500 > "${OUTPUT}/${2}.css"
done

tail -f /dev/null
