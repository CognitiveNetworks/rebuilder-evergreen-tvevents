"""
Consolidating the conversion from MAC to hashed token
"""

import hashlib
import os

region = os.environ.get('AWS_REGION')
if region == 'eu-west-1':
    hashfunc = hashlib.sha256
else:
    hashfunc = hashlib.md5


def security_hash_token(token, passed_salt):
    """
    Given a token and salt, generate the 'h' value that a TV would
    pass when it requests control. Use this to construct token + 'h'
    pairs that control servers would accept
    """
    try:
        hash_token = hashfunc(token + passed_salt).hexdigest()
    except Exception as e:
        hash_token = hashfunc((token + passed_salt).encode('utf-8')).hexdigest()
    return hash_token



def security_hash_match(token, passed_hash, passed_salt):
    """
    Checks that the 'h' value passed to control matches the hashed
    token that is sent along with it. The salt is also passed by TVC.
    Sort of a poor man's security
    """
    return passed_hash == security_hash_token(token, passed_salt)


# ============================================================================
# This line is made for humans; it's to indicate that the above function has
# nothing to do with the below functions. Like, at all.
# ============================================================================

TVID_SALT = {
    'vizio': 'stupidquestionhowtotithelotswife'
}


def normalize_mac(mac_address):
    """
    Convert a string, presumably a MAC address, to all lower case
    and strip out the ':' characters
    """
    return mac_address.replace(":", "").lower()


def hash_mac_vizio(normalized_mac):
    """
    Given a normalized MAC address, hash it the way Vizio TVs hash
    MAC addresses to create the token that gets sent to our client code
    """
    try:
        result = hashlib.md5(normalized_mac + TVID_SALT.get('vizio')).hexdigest()
    except Exception as e:
        result = hashlib.md5((normalized_mac + TVID_SALT.get('vizio')).encode('utf-8')).hexdigest()
    return result




def hash_mac_lg(normalized_mac):
    """
    Given a normalized MAC address, hash it the way LG TVs hash
    MAC addresses to create the token that gets sent to our client code
    """
    try:
        return hashlib.sha512(":".join([normalized_mac[x:x + 2] for x in range(0, len(normalized_mac), 2)]).upper()).hexdigest()
    except Exception as e:
        return hashlib.sha512(
            (":".join([normalized_mac[x:x + 2] for x in range(0, len(normalized_mac), 2)]).upper()).encode(
                'utf-8')).hexdigest()


def hash_mac(mac_address, oem):
    """
    Given a MAC address and an OEM, normalize the MAC then hash it
    An unhashed MAC is exactly 12 characters long
    If the token we are passed is longer than that (probably 32 or 128)
    assume it's already hashed and do nothing
    """
    normalized_mac = normalize_mac(mac_address)
    if len(normalized_mac) <= 12 and oem.lower() == 'vizio':
        return hash_mac_vizio(normalized_mac)
    elif len(normalized_mac) <= 12 and oem.lower() == 'lg':
        return hash_mac_lg(normalized_mac)
    else:
        return normalized_mac
