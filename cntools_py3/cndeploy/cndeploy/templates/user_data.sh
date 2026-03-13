#!/bin/bash

# Cognitive Networks deployment script (generic)

# globals
if [ -n "${HOME}" ]
then
    export HOME=/home/ubuntu
fi
export USER=ubuntu
export INSTALL_DIR=${HOME}
export INSTALL_LOG=${HOME}/install.log
START_TIME=$(python -c 'import time; print time.time()')
echo "Starting: ${START_TIME}" >> ${INSTALL_LOG}
echo "Installing to ${INSTALL_DIR}; log=${INSTALL_LOG}" >> ${INSTALL_LOG}
chmod a+rw ${INSTALL_LOG}


# update ubuntu packages
echo "Updating ubuntu packages" >> ${INSTALL_LOG}
apt-get -y update
DEBIAN_FRONTEND=noninteractive apt-get -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" dist-upgrade

# git
echo "Installing git" >> ${INSTALL_LOG}
apt-get -y install git
# TODO: set up .gitconfig

#install aws-cli and pip
apt-get -y install python-pip
pip install six==1.8.0
pip install awscli

#get private data from S3(ssh keys, creds, etc)
mkdir /home/ubuntu/.ssh
chmod 700 /home/ubuntu/.ssh
aws s3 cp s3://cn-secure/id_rsa /home/ubuntu/.ssh/
chown -R ubuntu:ubuntu /home/ubuntu/.ssh
chmod 600 /home/ubuntu/.ssh/id_rsa

# ssh
KEYS=${INSTALL_DIR}/.ssh
KEY_FILE=${KEYS}/deploy_id_rsa
sudo -u ${USER} mkdir -p ${KEYS}
if [ -n "{{KEY}}" ]
then
cat > ${KEY_FILE} <<DEPLOYKEY
{{KEY}}
DEPLOYKEY
fi
SSH_CONFIG=${KEYS}/config
cat >> ${SSH_CONFIG} <<SSHCONFIG
StrictHostKeyChecking no
Host deploy
        Hostname deploy.cognet.tv
        IdentityFile ~/.ssh/deploy_id_rsa
SSHCONFIG
for f in ${KEY_FILE} ${SSH_CONFIG}
do
    if [ -e "${f}" ]
    then
        chmod 600 ${f}
        chown ${USER}.${USER} ${f}
    fi
done
