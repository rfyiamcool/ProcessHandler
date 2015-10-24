#coding=utf-8

import msgpack

def serialize(source, default=lambda x: x.to_msgpack()):
    return msgpack.packb(source, default=default)

def deserialize(source):
    return msgpack.unpackb(source)
