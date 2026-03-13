#!/bin/bash

export BAR=1

function foo {
    echo ..$1..
    echo ..$BAR..
}
    
foo "testtest"
BAR=5 foo "blabhblah"

retry() 
{
    local retry_max=$1 && shift
    local sleep_time=$1 && shift

    local count=$retry_max
    while [ $count -gt 0 ]; do
        "$@" && break
        echo "retry failed attempt" $(($retry_max - $count + 1))
        count=$(($count - 1))
        [ $count -gt 0 ] && sleep $sleep_time
    done

    [ $count -eq 0 ] && {
        echo "retry failed [$retry_max]: $@"
        # TODO alert? die?
        return 1
    }
    return 0
}

retry 2 3 echo "sdflsdkfj"
#retry 3 3 chown root ~/notafile

# usage:
#    retry 5 30 /home/ubuntu/foo echo "foo present"

file_retry()
{
    local retry_max=$1 && shift
    local sleep_time=$1 && shift
    local test_file=$1 && shift
    local count=$retry_max
    while [ $count -gt 0 ]; do
        "$@"
        [ -s "$test_file" ] && break
        echo "retry_file failed attempt" $(($retry_max - $count + 1))
        count=$(($count - 1))
        [ $count -gt 0 ] && sleep $sleep_time
    done
    [ $count -eq 0 ] && {
        echo "retry failed [$retry_max]: $@"
        # TODO alert? die?
        return 1
    }
    return 0
}

echo xxxxxx
file_retry 2 3 ~/nofile echo "file not found"
file_retry 2 3 ~/.bashrc echo "file found"
echo xxxxxx
