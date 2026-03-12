#!/bin/bash

show_help() {
  printf "Usage: %s <url> <method>\n" "$0"
  printf "This script makes repeated requests to the provided URL using the specified method (curl or oha).\n"
  printf "Arguments:\n"
  printf "  <url>    The URL to which the requests will be made.\n"
  printf "  <method> The method to use for making the requests. Must be either 'curl' or 'oha'.\n"
}

generate_random_string() {
  local length=$1
  LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c $length
}

if [ "$1" == "--help" ]; then
  show_help
  exit 0
fi

if [ "$#" -ne 2 ]; then
  printf "Usage: %s <url> <curl/oha>\n" "$0"
  printf "Use --help for more info\n"
  exit 1
fi

if [ "$2" != "curl" ] && [ "$2" != "oha" ]; then
  echo "The method must be either 'curl' or 'oha'"
  exit 1
fi

host_url=$1
method=$2
app_id=$(generate_random_string 6)
channel_id=$(generate_random_string 6)
program_id=$(generate_random_string 6)
url="${host_url}?tvid=2180993&event_type=NATIVEAPP_TELEMETRY"

headers=(
  "-H" "cache-control: no-cache"
  "-H" "content-type: application/json"
)

data="{ \
  \"TvEvent\": { \
    \"tvid\": \"2180993\", \
    \"h\": \"554ab50be11666cf2c4c4c196448faa8\", \
    \"client\": \"acr\", \
    \"timestamp\": 1599860922441, \
    \"EventType\": \"NATIVEAPP_TELEMETRY\" \
  }, \
  \"EventData\": { \
    \"AppId\": \"${app_id}\", \
    \"AppName\": \"WatchFree+\", \
    \"Timestamp\": 1599860922440, \
    \"EventType\": \"ChannelChange\", \
    \"AdId\": { \
        \"LMT\": 0, \
        \"IFA\": \"aa84c930-asdf-asdf-8cc0-123b55b2ff07\", \
        \"IFA_TYPE\": \"dpid\" \
    }, \
    \"ChannelId\": \"${channel_id}\", \
    \"ProgramId\": \"${program_id}\", \
    \"WatchFreePlusSessionId\": \"68b429c2-347b-4075-98a9-6d18d237cf68\", \
    \"ChannelName\": \"Newsy\", \
    \"NameSpace\": 4, \
    \"Environment\": \"LOCAL\", \
    \"IsContentBlocked\": false \
  } \
}"

printf '\n%*s' "${COLUMNS:-$(tput cols)}" '' | tr ' ' -
printf "\n\n\nMaking requests to %s with App ID: %s, Channel ID: %s, and Program ID: %s \n\n\n" "${host_url}" "${app_id}" "${channel_id}" "${program_id}"
printf '%*s\n\n' "${COLUMNS:-$(tput cols)}" '' | tr ' ' -

if [ "$method" == "curl" ]; then
  while true; do
    printf "Making request to %s : " "$url"
    curl -X POST -k --insecure  "${url}" "${headers[@]}" -d "${data}"
    printf "\n \n"
    sleep 1
  done
elif [ "$method" == "oha" ]; then
  if ! command -v oha &> /dev/null; then
    echo "'oha' is not installed. Please install it using Homebrew:"
    echo "brew install oha"
    exit 1
  fi

  echo "Running oha load test on $url"
  oha -z 8h -m POST -q 100 -c 10 --no-pre-lookup --disable-keepalive --http-version=1.1 "${url}" "${headers[@]}" -d "${data}"
fi
