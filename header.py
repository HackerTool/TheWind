#!/usr/bin/env python
#encoding: utf-8

import socket, SocketServer,  struct, sys, subprocess, select
from scapy.all import *
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from OpenSSL import crypto

PORT = 8888
SO_ORIGINAL_DST = 80

import logging
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M',
                    filename='wind.log',
                    filemode='w')
console = logging.StreamHandler()
console.setLevel(logging.ERROR)
formatter = logging.Formatter('%(name)-12s: %(levelname)-8s %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)


def lookup(address, port, s):
    """
        Parse the pfctl state output s, to look up the destination host
        matching the client (address, port).

        Returns an (address, port) tuple, or None.
    """
    spec = "%s:%s" % (address, port)
    for i in s.split("\n"):
        if "ESTABLISHED:ESTABLISHED" in i and spec in i:
            s = i.split()
            if len(s) > 4:
                if sys.platform == "freebsd10":
                    # strip parentheses for FreeBSD pfctl
                    s = s[3][1:-1].split(":")
                else:
                    s = s[4].split(":")

                if len(s) == 2:
                    return s[0], int(s[1])
    raise RuntimeError("Could not resolve original destination.")

def get_original_addr(csock):
    output = subprocess.check_output("uname")
    if not output.strip() == "Linux":
        address, port = csock.getpeername()
        s = subprocess.check_output(("sudo", "-n", "/sbin/pfctl", "-s", "state"), stderr=subprocess.STDOUT)
        return lookup(address, port, s)
    odestdata = csock.getsockopt(socket.SOL_IP, SO_ORIGINAL_DST, 16)
    _, port, a1, a2, a3, a4 = struct.unpack("!HHBBBBxxxxxxxx", odestdata)
    address = "%d.%d.%d.%d" % (a1, a2, a3, a4)
    return address, port

class NullCipher(object):
    """ Implements a pycrypto like interface for the Null Cipher
    """
    
    block_size = 0
    key_size = 0
    
    @classmethod
    def new(cls, *args, **kwargs):
        return cls()
    
    def encrypt(self, cleartext):
        return cleartext
    
    def decrypt(self, ciphertext):
        return ciphertext

class NullHash(object):
    """ Implements a pycrypto like interface for the Null Hash
    """

    blocksize = 0
    digest_size = 0
    
    def __init__(self, *args, **kwargs):
        pass
    
    @classmethod
    def new(cls, *args, **kwargs):
        return cls(*args, **kwargs)
    
    def update(self, data):
        pass
    
    def digest(self):
        return ""
    
    def hexdigest(self):
        return ""
    
    def copy(self):
        return copy.deepcopy(self)

class DHE(object):
    pass


HASH_LENGTH = {
    "NONE":     0,
    "MD5":      16,
    "SHA":      20,
    "SHA224":   28,
    "SHA256":   32,
    "SHA384":   48,
    "SHA512":   64
 }


TLS_CIPHER_SUITE_REGISTRY = {
    0x0000: 'NULL_WITH_NULL_NULL',
    0x0001: 'RSA_WITH_NULL_MD5',
    0x0002: 'RSA_WITH_NULL_SHA',
    0x0003: 'RSA_EXPORT_WITH_RC4_40_MD5',
    0x0004: 'RSA_WITH_RC4_128_MD5',
    0x0005: 'RSA_WITH_RC4_128_SHA',
    0x0006: 'RSA_EXPORT_WITH_RC2_CBC_40_MD5',
    0x0007: 'RSA_WITH_IDEA_CBC_SHA',
    0x0008: 'RSA_EXPORT_WITH_DES40_CBC_SHA',
    0x0009: 'RSA_WITH_DES_CBC_SHA',
    0x000a: 'RSA_WITH_3DES_EDE_CBC_SHA',
    0x000b: 'DH_DSS_EXPORT_WITH_DES40_CBC_SHA',
    0x000c: 'DH_DSS_WITH_DES_CBC_SHA',
    0x000d: 'DH_DSS_WITH_3DES_EDE_CBC_SHA',
    0x000e: 'DH_RSA_EXPORT_WITH_DES40_CBC_SHA',
    0x000f: 'DH_RSA_WITH_DES_CBC_SHA',
    0x0010: 'DH_RSA_WITH_3DES_EDE_CBC_SHA',
    0x0011: 'DHE_DSS_EXPORT_WITH_DES40_CBC_SHA',
    0x0012: 'DHE_DSS_WITH_DES_CBC_SHA',
    0x0013: 'DHE_DSS_WITH_3DES_EDE_CBC_SHA',
    0x0014: 'DHE_RSA_EXPORT_WITH_DES40_CBC_SHA',
    0x0015: 'DHE_RSA_WITH_DES_CBC_SHA',
    0x0016: 'DHE_RSA_WITH_3DES_EDE_CBC_SHA',
    0x0017: 'DH_anon_EXPORT_WITH_RC4_40_MD5',
    0x0018: 'DH_anon_WITH_RC4_128_MD5',
    0x0019: 'DH_anon_EXPORT_WITH_DES40_CBC_SHA',
    0x001a: 'DH_anon_WITH_DES_CBC_SHA',
    0x001b: 'DH_anon_WITH_3DES_EDE_CBC_SHA',
    0x001e: 'KRB5_WITH_DES_CBC_SHA',
    0x001f: 'KRB5_WITH_3DES_EDE_CBC_SHA',
    0x0020: 'KRB5_WITH_RC4_128_SHA',
    0x0021: 'KRB5_WITH_IDEA_CBC_SHA',
    0x0022: 'KRB5_WITH_DES_CBC_MD5',
    0x0023: 'KRB5_WITH_3DES_EDE_CBC_MD5',
    0x0024: 'KRB5_WITH_RC4_128_MD5',
    0x0025: 'KRB5_WITH_IDEA_CBC_MD5',
    0x0026: 'KRB5_EXPORT_WITH_DES_CBC_40_SHA',
    0x0027: 'KRB5_EXPORT_WITH_RC2_CBC_40_SHA',
    0x0028: 'KRB5_EXPORT_WITH_RC4_40_SHA',
    0x0029: 'KRB5_EXPORT_WITH_DES_CBC_40_MD5',
    0x002a: 'KRB5_EXPORT_WITH_RC2_CBC_40_MD5',
    0x002b: 'KRB5_EXPORT_WITH_RC4_40_MD5',
    0x002c: 'PSK_WITH_NULL_SHA',
    0x002d: 'DHE_PSK_WITH_NULL_SHA',
    0x002e: 'RSA_PSK_WITH_NULL_SHA',
    0x002f: 'RSA_WITH_AES_128_CBC_SHA',
    0x0030: 'DH_DSS_WITH_AES_128_CBC_SHA',
    0x0031: 'DH_RSA_WITH_AES_128_CBC_SHA',
    0x0032: 'DHE_DSS_WITH_AES_128_CBC_SHA',
    0x0033: 'DHE_RSA_WITH_AES_128_CBC_SHA',
    0x0034: 'DH_anon_WITH_AES_128_CBC_SHA',
    0x0035: 'RSA_WITH_AES_256_CBC_SHA',
    0x0036: 'DH_DSS_WITH_AES_256_CBC_SHA',
    0x0037: 'DH_RSA_WITH_AES_256_CBC_SHA',
    0x0038: 'DHE_DSS_WITH_AES_256_CBC_SHA',
    0x0039: 'DHE_RSA_WITH_AES_256_CBC_SHA',
    0x003a: 'DH_anon_WITH_AES_256_CBC_SHA',
    0x003b: 'RSA_WITH_NULL_SHA256',
    0x003c: 'RSA_WITH_AES_128_CBC_SHA256',
    0x003d: 'RSA_WITH_AES_256_CBC_SHA256',
    0x003e: 'DH_DSS_WITH_AES_128_CBC_SHA256',
    0x003f: 'DH_RSA_WITH_AES_128_CBC_SHA256',
    0x0040: 'DHE_DSS_WITH_AES_128_CBC_SHA256',
    0x0041: 'RSA_WITH_CAMELLIA_128_CBC_SHA',
    0x0042: 'DH_DSS_WITH_CAMELLIA_128_CBC_SHA',
    0x0043: 'DH_RSA_WITH_CAMELLIA_128_CBC_SHA',
    0x0044: 'DHE_DSS_WITH_CAMELLIA_128_CBC_SHA',
    0x0045: 'DHE_RSA_WITH_CAMELLIA_128_CBC_SHA',
    0x0046: 'DH_anon_WITH_CAMELLIA_128_CBC_SHA',
    0x0060: 'RSA_EXPORT1024_WITH_RC4_56_MD5',
    0x0061: 'RSA_EXPORT1024_WITH_RC2_CBC_56_MD5',
    0x0062: 'RSA_EXPORT1024_WITH_DES_CBC_SHA',
    0x0063: 'DHE_DSS_EXPORT1024_WITH_DES_CBC_SHA',
    0x0064: 'RSA_EXPORT1024_WITH_RC4_56_SHA',
    0x0065: 'DHE_DSS_EXPORT1024_WITH_RC4_56_SHA',
    0x0066: 'DHE_DSS_WITH_RC4_128_SHA',
    0x0067: 'DHE_RSA_WITH_AES_128_CBC_SHA256',
    0x0068: 'DH_DSS_WITH_AES_256_CBC_SHA256',
    0x0069: 'DH_RSA_WITH_AES_256_CBC_SHA256',
    0x006a: 'DHE_DSS_WITH_AES_256_CBC_SHA256',
    0x006b: 'DHE_RSA_WITH_AES_256_CBC_SHA256',
    0x006c: 'DH_anon_WITH_AES_128_CBC_SHA256',
    0x006d: 'DH_anon_WITH_AES_256_CBC_SHA256',
    0x0084: 'RSA_WITH_CAMELLIA_256_CBC_SHA',
    0x0085: 'DH_DSS_WITH_CAMELLIA_256_CBC_SHA',
    0x0086: 'DH_RSA_WITH_CAMELLIA_256_CBC_SHA',
    0x0087: 'DHE_DSS_WITH_CAMELLIA_256_CBC_SHA',
    0x0088: 'DHE_RSA_WITH_CAMELLIA_256_CBC_SHA',
    0x0089: 'DH_anon_WITH_CAMELLIA_256_CBC_SHA',
    0x008a: 'PSK_WITH_RC4_128_SHA',
    0x008b: 'PSK_WITH_3DES_EDE_CBC_SHA',
    0x008c: 'PSK_WITH_AES_128_CBC_SHA',
    0x008d: 'PSK_WITH_AES_256_CBC_SHA',
    0x008e: 'DHE_PSK_WITH_RC4_128_SHA',
    0x008f: 'DHE_PSK_WITH_3DES_EDE_CBC_SHA',
    0x0090: 'DHE_PSK_WITH_AES_128_CBC_SHA',
    0x0091: 'DHE_PSK_WITH_AES_256_CBC_SHA',
    0x0092: 'RSA_PSK_WITH_RC4_128_SHA',
    0x0093: 'RSA_PSK_WITH_3DES_EDE_CBC_SHA',
    0x0094: 'RSA_PSK_WITH_AES_128_CBC_SHA',
    0x0095: 'RSA_PSK_WITH_AES_256_CBC_SHA',
    0x0096: 'RSA_WITH_SEED_CBC_SHA',
    0x0097: 'DH_DSS_WITH_SEED_CBC_SHA',
    0x0098: 'DH_RSA_WITH_SEED_CBC_SHA',
    0x0099: 'DHE_DSS_WITH_SEED_CBC_SHA',
    0x009a: 'DHE_RSA_WITH_SEED_CBC_SHA',
    0x009b: 'DH_anon_WITH_SEED_CBC_SHA',
    0x009c: 'RSA_WITH_AES_128_GCM_SHA256',
    0x009d: 'RSA_WITH_AES_256_GCM_SHA384',
    0x009e: 'DHE_RSA_WITH_AES_128_GCM_SHA256',
    0x009f: 'DHE_RSA_WITH_AES_256_GCM_SHA384',
    0x00a0: 'DH_RSA_WITH_AES_128_GCM_SHA256',
    0x00a1: 'DH_RSA_WITH_AES_256_GCM_SHA384',
    0x00a2: 'DHE_DSS_WITH_AES_128_GCM_SHA256',
    0x00a3: 'DHE_DSS_WITH_AES_256_GCM_SHA384',
    0x00a4: 'DH_DSS_WITH_AES_128_GCM_SHA256',
    0x00a5: 'DH_DSS_WITH_AES_256_GCM_SHA384',
    0x00a6: 'DH_anon_WITH_AES_128_GCM_SHA256',
    0x00a7: 'DH_anon_WITH_AES_256_GCM_SHA384',
    0x00a8: 'PSK_WITH_AES_128_GCM_SHA256',
    0x00a9: 'PSK_WITH_AES_256_GCM_SHA384',
    0x00aa: 'DHE_PSK_WITH_AES_128_GCM_SHA256',
    0x00ab: 'DHE_PSK_WITH_AES_256_GCM_SHA384',
    0x00ac: 'RSA_PSK_WITH_AES_128_GCM_SHA256',
    0x00ad: 'RSA_PSK_WITH_AES_256_GCM_SHA384',
    0x00ae: 'PSK_WITH_AES_128_CBC_SHA256',
    0x00af: 'PSK_WITH_AES_256_CBC_SHA384',
    0x00b0: 'PSK_WITH_NULL_SHA256',
    0x00b1: 'PSK_WITH_NULL_SHA384',
    0x00b2: 'DHE_PSK_WITH_AES_128_CBC_SHA256',
    0x00b3: 'DHE_PSK_WITH_AES_256_CBC_SHA384',
    0x00b4: 'DHE_PSK_WITH_NULL_SHA256',
    0x00b5: 'DHE_PSK_WITH_NULL_SHA384',
    0x00b6: 'RSA_PSK_WITH_AES_128_CBC_SHA256',
    0x00b7: 'RSA_PSK_WITH_AES_256_CBC_SHA384',
    0x00b8: 'RSA_PSK_WITH_NULL_SHA256',
    0x00b9: 'RSA_PSK_WITH_NULL_SHA384',
    0x00ba: 'RSA_WITH_CAMELLIA_128_CBC_SHA256',
    0x00bb: 'DH_DSS_WITH_CAMELLIA_128_CBC_SHA256',
    0x00bc: 'DH_RSA_WITH_CAMELLIA_128_CBC_SHA256',
    0x00bd: 'DHE_DSS_WITH_CAMELLIA_128_CBC_SHA256',
    0x00be: 'DHE_RSA_WITH_CAMELLIA_128_CBC_SHA256',
    0x00bf: 'DH_anon_WITH_CAMELLIA_128_CBC_SHA256',
    0x00c0: 'RSA_WITH_CAMELLIA_256_CBC_SHA256',
    0x00c1: 'DH_DSS_WITH_CAMELLIA_256_CBC_SHA256',
    0x00c2: 'DH_RSA_WITH_CAMELLIA_256_CBC_SHA256',
    0x00c3: 'DHE_DSS_WITH_CAMELLIA_256_CBC_SHA256',
    0x00c4: 'DHE_RSA_WITH_CAMELLIA_256_CBC_SHA256',
    0x00c5: 'DH_anon_WITH_CAMELLIA_256_CBC_SHA256',
    0x00ff: 'EMPTY_RENEGOTIATION_INFO_SCSV',
    0x5600: 'FALLBACK_SCSV',
    0xc001: 'ECDH_ECDSA_WITH_NULL_SHA',
    0xc002: 'ECDH_ECDSA_WITH_RC4_128_SHA',
    0xc003: 'ECDH_ECDSA_WITH_3DES_EDE_CBC_SHA',
    0xc004: 'ECDH_ECDSA_WITH_AES_128_CBC_SHA',
    0xc005: 'ECDH_ECDSA_WITH_AES_256_CBC_SHA',
    0xc006: 'ECDHE_ECDSA_WITH_NULL_SHA',
    0xc007: 'ECDHE_ECDSA_WITH_RC4_128_SHA',
    0xc008: 'ECDHE_ECDSA_WITH_3DES_EDE_CBC_SHA',
    0xc009: 'ECDHE_ECDSA_WITH_AES_128_CBC_SHA',
    0xc00a: 'ECDHE_ECDSA_WITH_AES_256_CBC_SHA',
    0xc00b: 'ECDH_RSA_WITH_NULL_SHA',
    0xc00c: 'ECDH_RSA_WITH_RC4_128_SHA',
    0xc00d: 'ECDH_RSA_WITH_3DES_EDE_CBC_SHA',
    0xc00e: 'ECDH_RSA_WITH_AES_128_CBC_SHA',
    0xc00f: 'ECDH_RSA_WITH_AES_256_CBC_SHA',
    0xc010: 'ECDHE_RSA_WITH_NULL_SHA',
    0xc011: 'ECDHE_RSA_WITH_RC4_128_SHA',
    0xc012: 'ECDHE_RSA_WITH_3DES_EDE_CBC_SHA',
    0xc013: 'ECDHE_RSA_WITH_AES_128_CBC_SHA',
    0xc014: 'ECDHE_RSA_WITH_AES_256_CBC_SHA',
    0xc015: 'ECDH_anon_WITH_NULL_SHA',
    0xc016: 'ECDH_anon_WITH_RC4_128_SHA',
    0xc017: 'ECDH_anon_WITH_3DES_EDE_CBC_SHA',
    0xc018: 'ECDH_anon_WITH_AES_128_CBC_SHA',
    0xc019: 'ECDH_anon_WITH_AES_256_CBC_SHA',
    0xc01a: 'SRP_SHA_WITH_3DES_EDE_CBC_SHA',
    0xc01b: 'SRP_SHA_RSA_WITH_3DES_EDE_CBC_SHA',
    0xc01c: 'SRP_SHA_DSS_WITH_3DES_EDE_CBC_SHA',
    0xc01d: 'SRP_SHA_WITH_AES_128_CBC_SHA',
    0xc01e: 'SRP_SHA_RSA_WITH_AES_128_CBC_SHA',
    0xc01f: 'SRP_SHA_DSS_WITH_AES_128_CBC_SHA',
    0xc020: 'SRP_SHA_WITH_AES_256_CBC_SHA',
    0xc021: 'SRP_SHA_RSA_WITH_AES_256_CBC_SHA',
    0xc022: 'SRP_SHA_DSS_WITH_AES_256_CBC_SHA',
    0xc023: 'ECDHE_ECDSA_WITH_AES_128_CBC_SHA256',
    0xc024: 'ECDHE_ECDSA_WITH_AES_256_CBC_SHA384',
    0xc025: 'ECDH_ECDSA_WITH_AES_128_CBC_SHA256',
    0xc026: 'ECDH_ECDSA_WITH_AES_256_CBC_SHA384',
    0xc027: 'ECDHE_RSA_WITH_AES_128_CBC_SHA256',
    0xc028: 'ECDHE_RSA_WITH_AES_256_CBC_SHA384',
    0xc029: 'ECDH_RSA_WITH_AES_128_CBC_SHA256',
    0xc02a: 'ECDH_RSA_WITH_AES_256_CBC_SHA384',
    0xc02b: 'ECDHE_ECDSA_WITH_AES_128_GCM_SHA256',
    0xc02c: 'ECDHE_ECDSA_WITH_AES_256_GCM_SHA384',
    0xc02d: 'ECDH_ECDSA_WITH_AES_128_GCM_SHA256',
    0xc02e: 'ECDH_ECDSA_WITH_AES_256_GCM_SHA384',
    0xc02f: 'ECDHE_RSA_WITH_AES_128_GCM_SHA256',
    0xc030: 'ECDHE_RSA_WITH_AES_256_GCM_SHA384',
    0xc031: 'ECDH_RSA_WITH_AES_128_GCM_SHA256',
    0xc032: 'ECDH_RSA_WITH_AES_256_GCM_SHA384',
    0xc033: 'ECDHE_PSK_WITH_RC4_128_SHA',
    0xc034: 'ECDHE_PSK_WITH_3DES_EDE_CBC_SHA',
    0xc035: 'ECDHE_PSK_WITH_AES_128_CBC_SHA',
    0xc036: 'ECDHE_PSK_WITH_AES_256_CBC_SHA',
    0xc037: 'ECDHE_PSK_WITH_AES_128_CBC_SHA256',
    0xc038: 'ECDHE_PSK_WITH_AES_256_CBC_SHA384',
    0xc039: 'ECDHE_PSK_WITH_NULL_SHA',
    0xc03a: 'ECDHE_PSK_WITH_NULL_SHA256',
    0xc03b: 'ECDHE_PSK_WITH_NULL_SHA384',
    0xc03c: 'RSA_WITH_ARIA_128_CBC_SHA256',
    0xc03d: 'RSA_WITH_ARIA_256_CBC_SHA384',
    0xc03e: 'DH_DSS_WITH_ARIA_128_CBC_SHA256',
    0xc03f: 'DH_DSS_WITH_ARIA_256_CBC_SHA384',
    0xc040: 'DH_RSA_WITH_ARIA_128_CBC_SHA256',
    0xc041: 'DH_RSA_WITH_ARIA_256_CBC_SHA384',
    0xc042: 'DHE_DSS_WITH_ARIA_128_CBC_SHA256',
    0xc043: 'DHE_DSS_WITH_ARIA_256_CBC_SHA384',
    0xc044: 'DHE_RSA_WITH_ARIA_128_CBC_SHA256',
    0xc045: 'DHE_RSA_WITH_ARIA_256_CBC_SHA384',
    0xc046: 'DH_anon_WITH_ARIA_128_CBC_SHA256',
    0xc047: 'DH_anon_WITH_ARIA_256_CBC_SHA384',
    0xc048: 'ECDHE_ECDSA_WITH_ARIA_128_CBC_SHA256',
    0xc049: 'ECDHE_ECDSA_WITH_ARIA_256_CBC_SHA384',
    0xc04a: 'ECDH_ECDSA_WITH_ARIA_128_CBC_SHA256',
    0xc04b: 'ECDH_ECDSA_WITH_ARIA_256_CBC_SHA384',
    0xc04c: 'ECDHE_RSA_WITH_ARIA_128_CBC_SHA256',
    0xc04d: 'ECDHE_RSA_WITH_ARIA_256_CBC_SHA384',
    0xc04e: 'ECDH_RSA_WITH_ARIA_128_CBC_SHA256',
    0xc04f: 'ECDH_RSA_WITH_ARIA_256_CBC_SHA384',
    0xc050: 'RSA_WITH_ARIA_128_GCM_SHA256',
    0xc051: 'RSA_WITH_ARIA_256_GCM_SHA384',
    0xc052: 'DHE_RSA_WITH_ARIA_128_GCM_SHA256',
    0xc053: 'DHE_RSA_WITH_ARIA_256_GCM_SHA384',
    0xc054: 'DH_RSA_WITH_ARIA_128_GCM_SHA256',
    0xc055: 'DH_RSA_WITH_ARIA_256_GCM_SHA384',
    0xc056: 'DHE_DSS_WITH_ARIA_128_GCM_SHA256',
    0xc057: 'DHE_DSS_WITH_ARIA_256_GCM_SHA384',
    0xc058: 'DH_DSS_WITH_ARIA_128_GCM_SHA256',
    0xc059: 'DH_DSS_WITH_ARIA_256_GCM_SHA384',
    0xc05a: 'DH_anon_WITH_ARIA_128_GCM_SHA256',
    0xc05b: 'DH_anon_WITH_ARIA_256_GCM_SHA384',
    0xc05c: 'ECDHE_ECDSA_WITH_ARIA_128_GCM_SHA256',
    0xc05d: 'ECDHE_ECDSA_WITH_ARIA_256_GCM_SHA384',
    0xc05e: 'ECDH_ECDSA_WITH_ARIA_128_GCM_SHA256',
    0xc05f: 'ECDH_ECDSA_WITH_ARIA_256_GCM_SHA384',
    0xc060: 'ECDHE_RSA_WITH_ARIA_128_GCM_SHA256',
    0xc061: 'ECDHE_RSA_WITH_ARIA_256_GCM_SHA384',
    0xc062: 'ECDH_RSA_WITH_ARIA_128_GCM_SHA256',
    0xc063: 'ECDH_RSA_WITH_ARIA_256_GCM_SHA384',
    0xc064: 'PSK_WITH_ARIA_128_CBC_SHA256',
    0xc065: 'PSK_WITH_ARIA_256_CBC_SHA384',
    0xc066: 'DHE_PSK_WITH_ARIA_128_CBC_SHA256',
    0xc067: 'DHE_PSK_WITH_ARIA_256_CBC_SHA384',
    0xc068: 'RSA_PSK_WITH_ARIA_128_CBC_SHA256',
    0xc069: 'RSA_PSK_WITH_ARIA_256_CBC_SHA384',
    0xc06a: 'PSK_WITH_ARIA_128_GCM_SHA256',
    0xc06b: 'PSK_WITH_ARIA_256_GCM_SHA384',
    0xc06c: 'DHE_PSK_WITH_ARIA_128_GCM_SHA256',
    0xc06d: 'DHE_PSK_WITH_ARIA_256_GCM_SHA384',
    0xc06e: 'RSA_PSK_WITH_ARIA_128_GCM_SHA256',
    0xc06f: 'RSA_PSK_WITH_ARIA_256_GCM_SHA384',
    0xc070: 'ECDHE_PSK_WITH_ARIA_128_CBC_SHA256',
    0xc071: 'ECDHE_PSK_WITH_ARIA_256_CBC_SHA384',
    0xc072: 'ECDHE_ECDSA_WITH_CAMELLIA_128_CBC_SHA256',
    0xc073: 'ECDHE_ECDSA_WITH_CAMELLIA_256_CBC_SHA384',
    0xc074: 'ECDH_ECDSA_WITH_CAMELLIA_128_CBC_SHA256',
    0xc075: 'ECDH_ECDSA_WITH_CAMELLIA_256_CBC_SHA384',
    0xc076: 'ECDHE_RSA_WITH_CAMELLIA_128_CBC_SHA256',
    0xc077: 'ECDHE_RSA_WITH_CAMELLIA_256_CBC_SHA384',
    0xc078: 'ECDH_RSA_WITH_CAMELLIA_128_CBC_SHA256',
    0xc079: 'ECDH_RSA_WITH_CAMELLIA_256_CBC_SHA384',
    0xc07a: 'RSA_WITH_CAMELLIA_128_GCM_SHA256',
    0xc07b: 'RSA_WITH_CAMELLIA_256_GCM_SHA384',
    0xc07c: 'DHE_RSA_WITH_CAMELLIA_128_GCM_SHA256',
    0xc07d: 'DHE_RSA_WITH_CAMELLIA_256_GCM_SHA384',
    0xc07e: 'DH_RSA_WITH_CAMELLIA_128_GCM_SHA256',
    0xc07f: 'DH_RSA_WITH_CAMELLIA_256_GCM_SHA384',
    0xc080: 'DHE_DSS_WITH_CAMELLIA_128_GCM_SHA256',
    0xc081: 'DHE_DSS_WITH_CAMELLIA_256_GCM_SHA384',
    0xc082: 'DH_DSS_WITH_CAMELLIA_128_GCM_SHA256',
    0xc083: 'DH_DSS_WITH_CAMELLIA_256_GCM_SHA384',
    0xc084: 'DH_anon_WITH_CAMELLIA_128_GCM_SHA256',
    0xc085: 'DH_anon_WITH_CAMELLIA_256_GCM_SHA384',
    0xc086: 'ECDHE_ECDSA_WITH_CAMELLIA_128_GCM_SHA256',
    0xc087: 'ECDHE_ECDSA_WITH_CAMELLIA_256_GCM_SHA384',
    0xc088: 'ECDH_ECDSA_WITH_CAMELLIA_128_GCM_SHA256',
    0xc089: 'ECDH_ECDSA_WITH_CAMELLIA_256_GCM_SHA384',
    0xc08a: 'ECDHE_RSA_WITH_CAMELLIA_128_GCM_SHA256',
    0xc08b: 'ECDHE_RSA_WITH_CAMELLIA_256_GCM_SHA384',
    0xc08c: 'ECDH_RSA_WITH_CAMELLIA_128_GCM_SHA256',
    0xc08d: 'ECDH_RSA_WITH_CAMELLIA_256_GCM_SHA384',
    0xc08e: 'PSK_WITH_CAMELLIA_128_GCM_SHA256',
    0xc08f: 'PSK_WITH_CAMELLIA_256_GCM_SHA384',
    0xc090: 'DHE_PSK_WITH_CAMELLIA_128_GCM_SHA256',
    0xc091: 'DHE_PSK_WITH_CAMELLIA_256_GCM_SHA384',
    0xc092: 'RSA_PSK_WITH_CAMELLIA_128_GCM_SHA256',
    0xc093: 'RSA_PSK_WITH_CAMELLIA_256_GCM_SHA384',
    0xc094: 'PSK_WITH_CAMELLIA_128_CBC_SHA256',
    0xc095: 'PSK_WITH_CAMELLIA_256_CBC_SHA384',
    0xc096: 'DHE_PSK_WITH_CAMELLIA_128_CBC_SHA256',
    0xc097: 'DHE_PSK_WITH_CAMELLIA_256_CBC_SHA384',
    0xc098: 'RSA_PSK_WITH_CAMELLIA_128_CBC_SHA256',
    0xc099: 'RSA_PSK_WITH_CAMELLIA_256_CBC_SHA384',
    0xc09a: 'ECDHE_PSK_WITH_CAMELLIA_128_CBC_SHA256',
    0xc09b: 'ECDHE_PSK_WITH_CAMELLIA_256_CBC_SHA384',
    0xc09c: 'RSA_WITH_AES_128_CCM',
    0xc09d: 'RSA_WITH_AES_256_CCM',
    0xc09e: 'DHE_RSA_WITH_AES_128_CCM',
    0xc09f: 'DHE_RSA_WITH_AES_256_CCM',
    0xc0a0: 'RSA_WITH_AES_128_CCM_8',
    0xc0a1: 'RSA_WITH_AES_256_CCM_8',
    0xc0a2: 'DHE_RSA_WITH_AES_128_CCM_8',
    0xc0a3: 'DHE_RSA_WITH_AES_256_CCM_8',
    0xc0a4: 'PSK_WITH_AES_128_CCM',
    0xc0a5: 'PSK_WITH_AES_256_CCM',
    0xc0a6: 'DHE_PSK_WITH_AES_128_CCM',
    0xc0a7: 'DHE_PSK_WITH_AES_256_CCM',
    0xc0a8: 'PSK_WITH_AES_128_CCM_8',
    0xc0a9: 'PSK_WITH_AES_256_CCM_8',
    0xc0aa: 'PSK_DHE_WITH_AES_128_CCM_8',
    0xc0ab: 'PSK_DHE_WITH_AES_256_CCM_8',
    0xc0ac: 'ECDHE_ECDSA_WITH_AES_128_CCM',
    0xc0ad: 'ECDHE_ECDSA_WITH_AES_256_CCM',
    0xc0ae: 'ECDHE_ECDSA_WITH_AES_128_CCM_8',
    0xc0af: 'ECDHE_ECDSA_WITH_AES_256_CCM_8',
}

crypto_params = {
    'NULL_WITH_NULL_NULL':             {"name":TLS_CIPHER_SUITE_REGISTRY[0x0000], "export":False, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":NullCipher, "name":"Null", "keyLen":0, "mode":None, "mode_name":""}, "hash":{"type":NullHash, "name":"Null"}},
    'RSA_WITH_NULL_MD5':               {"name":TLS_CIPHER_SUITE_REGISTRY[0x0001], "export":False, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":NullCipher, "name":"Null", "keyLen":0, "mode":None, "mode_name":""}, "hash":{"type":MD5, "name":"MD5"}},
    'RSA_WITH_NULL_SHA':               {"name":TLS_CIPHER_SUITE_REGISTRY[0x0002], "export":False, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":NullCipher, "name":"Null", "keyLen":0, "mode":None, "mode_name":""}, "hash":{"type":SHA, "name":"SHA"}},
    'RSA_EXPORT_WITH_RC4_40_MD5':      {"name":TLS_CIPHER_SUITE_REGISTRY[0x0003], "export":True, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":ARC4, "name":"RC4", "keyLen":5, "mode":None, "mode_name":"Stream"}, "hash":{"type":MD5, "name":"MD5"}},
    'RSA_WITH_RC4_128_MD5':            {"name":TLS_CIPHER_SUITE_REGISTRY[0x0004], "export":False, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":ARC4, "name":"RC4", "keyLen":16, "mode":None, "mode_name":"Stream"}, "hash":{"type":MD5, "name":"MD5"}},
    'RSA_WITH_RC4_128_SHA':            {"name":TLS_CIPHER_SUITE_REGISTRY[0x0005], "export":False, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":ARC4, "name":"RC4", "keyLen":16, "mode":None, "mode_name":"Stream"}, "hash":{"type":SHA, "name":"SHA"}},
    'RSA_EXPORT_WITH_RC2_CBC_40_MD5':  {"name":TLS_CIPHER_SUITE_REGISTRY[0x0006], "export":True, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":ARC2, "name":"RC2", "keyLen":5, "mode":ARC2.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":MD5, "name":"MD5"}},
    # 0x0007: RSA_WITH_IDEA_CBC_SHA => IDEA support would require python openssl bindings
    'RSA_EXPORT_WITH_DES40_CBC_SHA':   {"name":TLS_CIPHER_SUITE_REGISTRY[0x0008], "export":True, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":DES, "name":"DES", "keyLen":5, "mode":DES.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'RSA_WITH_DES_CBC_SHA':            {"name":TLS_CIPHER_SUITE_REGISTRY[0x0009], "export":False, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":DES, "name":"DES", "keyLen":8, "mode":DES.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'RSA_WITH_3DES_EDE_CBC_SHA':       {"name":TLS_CIPHER_SUITE_REGISTRY[0x000a], "export":False, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":DES3, "name":"DES3", "keyLen":24, "mode":DES3.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'RSA_WITH_AES_128_CBC_SHA':        {"name":TLS_CIPHER_SUITE_REGISTRY[0x002f], "export":False, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":AES, "name":"AES", "keyLen":16, "mode":AES.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'RSA_WITH_AES_256_CBC_SHA':        {"name":TLS_CIPHER_SUITE_REGISTRY[0x0035], "export":False, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":AES, "name":"AES", "keyLen":32, "mode":AES.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'RSA_WITH_NULL_SHA256':            {"name":TLS_CIPHER_SUITE_REGISTRY[0x003b], "export":False, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":NullCipher, "name":"Null", "keyLen":0, "mode":None, "mode_name":""}, "hash":{"type":SHA256, "name":"SHA256"}},
    'RSA_EXPORT1024_WITH_RC4_56_MD5':  {"name":TLS_CIPHER_SUITE_REGISTRY[0x0060], "export":True, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":ARC4, "name":"RC4", "keyLen":8, "mode":None, "mode_name":"Stream"}, "hash":{"type":MD5, "name":"MD5"}},
    'RSA_EXPORT1024_WITH_RC2_CBC_56_MD5': {"name":TLS_CIPHER_SUITE_REGISTRY[0x0061], "export":True, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":ARC2, "name":"RC2", "keyLen":8, "mode":ARC2.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":MD5, "name":"MD5"}},
    'RSA_EXPORT1024_WITH_DES_CBC_SHA': {"name":TLS_CIPHER_SUITE_REGISTRY[0x0062], "export":True, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":DES, "name":"DES", "keyLen":8, "mode":DES.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'RSA_EXPORT1024_WITH_RC4_56_SHA':  {"name":TLS_CIPHER_SUITE_REGISTRY[0x0064], "export":True, "key_exchange":{"type":RSA, "name":RSA, "sig":None}, "cipher":{"type":ARC4, "name":"RC4", "keyLen":8, "mode":None, "mode_name":"Stream"}, "hash":{"type":SHA, "name":"SHA"}},
    # 0x0084: RSA_WITH_CAMELLIA_256_CBC_SHA => Camelia support should use camcrypt or the camelia patch for pycrypto
    'DHE_DSS_EXPORT_WITH_DES40_CBC_SHA':   {"name":TLS_CIPHER_SUITE_REGISTRY[0x0011], "export":True, "key_exchange":{"type":DHE, "name":DHE, "sig":DSA}, "cipher":{"type":DES, "name":"DES", "keyLen":5, "mode":DES.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'DHE_DSS_WITH_DES_CBC_SHA':        {"name":TLS_CIPHER_SUITE_REGISTRY[0x0012], "export":False, "key_exchange":{"type":DHE, "name":DHE, "sig":DSA}, "cipher":{"type":DES, "name":"DES", "keyLen":8, "mode":DES.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'DHE_DSS_WITH_3DES_EDE_CBC_SHA':   {"name":TLS_CIPHER_SUITE_REGISTRY[0x0013], "export":False, "key_exchange":{"type":DHE, "name":DHE, "sig":DSA}, "cipher":{"type":DES3, "name":"DES3", "keyLen":24, "mode":DES3.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'DHE_RSA_EXPORT_WITH_DES40_CBC_SHA':   {"name":TLS_CIPHER_SUITE_REGISTRY[0x0014], "export":True, "key_exchange":{"type":DHE, "name":DHE, "sig":RSA}, "cipher":{"type":DES, "name":"DES", "keyLen":5, "mode":DES.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'DHE_RSA_WITH_DES_CBC_SHA':        {"name":TLS_CIPHER_SUITE_REGISTRY[0x0015], "export":False, "key_exchange":{"type":DHE, "name":DHE, "sig":RSA}, "cipher":{"type":DES, "name":"DES", "keyLen":8, "mode":DES.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'DHE_RSA_WITH_3DES_EDE_CBC_SHA':   {"name":TLS_CIPHER_SUITE_REGISTRY[0x0016], "export":False, "key_exchange":{"type":DHE, "name":DHE, "sig":RSA}, "cipher":{"type":DES3, "name":"DES3", "keyLen":24, "mode":DES3.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'DHE_DSS_WITH_AES_128_CBC_SHA':    {"name":TLS_CIPHER_SUITE_REGISTRY[0x0032], "export":False, "key_exchange":{"type":DHE, "name":DHE, "sig":DSA}, "cipher":{"type":AES, "name":"AES", "keyLen":16, "mode":AES.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'DHE_RSA_WITH_AES_128_CBC_SHA':    {"name":TLS_CIPHER_SUITE_REGISTRY[0x0033], "export":False, "key_exchange":{"type":DHE, "name":DHE, "sig":RSA}, "cipher":{"type":AES, "name":"AES", "keyLen":16, "mode":AES.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'DHE_DSS_WITH_AES_256_CBC_SHA':    {"name":TLS_CIPHER_SUITE_REGISTRY[0x0038], "export":False, "key_exchange":{"type":DHE, "name":DHE, "sig":DSA}, "cipher":{"type":AES, "name":"AES", "keyLen":32, "mode":AES.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'DHE_RSA_WITH_AES_256_CBC_SHA':    {"name":TLS_CIPHER_SUITE_REGISTRY[0x0039], "export":False, "key_exchange":{"type":DHE, "name":DHE, "sig":RSA}, "cipher":{"type":AES, "name":"AES", "keyLen":32, "mode":AES.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'DHE_DSS_EXPORT1024_WITH_DES_CBC_SHA': {"name":TLS_CIPHER_SUITE_REGISTRY[0x0063], "export":True, "key_exchange":{"type":DHE, "name":DHE, "sig":DSA}, "cipher":{"type":DES, "name":"DES", "keyLen":8, "mode":DES.MODE_CBC, "mode_name":"CBC"}, "hash":{"type":SHA, "name":"SHA"}},
    'DHE_DSS_EXPORT1024_WITH_RC4_56_SHA':  {"name":TLS_CIPHER_SUITE_REGISTRY[0x0065], "export":True, "key_exchange":{"type":DHE, "name":DHE, "sig":DSA}, "cipher":{"type":ARC4, "name":"RC4", "keyLen":8, "mode":None, "mode_name":"Stream"}, "hash":{"type":SHA, "name":"SHA"}},
    'DHE_DSS_WITH_RC4_128_SHA':            {"name":TLS_CIPHER_SUITE_REGISTRY[0x0066], "export":False, "key_exchange":{"type":DHE, "name":DHE, "sig":DSA}, "cipher":{"type":ARC4, "name":"RC4", "keyLen":16, "mode":None, "mode_name":"Stream"}, "hash":{"type":SHA, "name":"SHA"}},
    # 0x0087: DHE_DSS_WITH_CAMELLIA_256_CBC_SHA => Camelia support should use camcrypt or the camelia patch for pycrypto
    # 0x0088: DHE_RSA_WITH_CAMELLIA_256_CBC_SHA => Camelia support should use camcrypt or the camelia patch for pycrypto
}
def parseCS(num):
    return TLS_CIPHER_SUITE_REGISTRY[num]


def recvall(sock, length):
    rlen = length
    data = ''
    while rlen > 0:
        tmp = sock.recv(rlen)
        if not tmp:
            break
        data += tmp
        rlen -= len(tmp)
    return data

def recv_one(ssock, csock):
    readable = select.select([ssock, csock],[],[],30)[0]
    datalist = []
    for r in readable:
        data = r.recv(2048)
        datalist.append((r, data))
    return datalist
