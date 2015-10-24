#coding=utf-8

import zlib

def compress(source):
    return zlib.compress(source, 6) # use default level

def decompress(data):
    return zlib.decompress(data)  # default buffer size 16K
