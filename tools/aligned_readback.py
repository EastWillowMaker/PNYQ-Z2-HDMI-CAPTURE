#!/usr/bin/env python3
"""Linux O_DIRECT SHA256 with explicitly aligned pread storage. Read-only."""
import ctypes as C
import hashlib
import os
import sys


def direct_hash(path, length, progress=None):
    if length <= 0 or length % 512:
        raise ValueError('Read size must be a positive multiple of512')
    libc = C.CDLL(None, use_errno=True)
    libc.posix_memalign.argtypes = [C.POINTER(C.c_void_p), C.c_size_t, C.c_size_t]
    libc.posix_memalign.restype = C.c_int
    libc.pread.argtypes = [C.c_int, C.c_void_p, C.c_size_t, C.c_longlong]
    libc.pread.restype = C.c_ssize_t
    libc.free.argtypes = [C.c_void_p]
    size = 8 * 1024 * 1024
    pointer = C.c_void_p()
    error = libc.posix_memalign(C.byref(pointer), 4096, size)
    if error:
        raise OSError(error, os.strerror(error))
    fd = None
    digest = hashlib.sha256()
    offset = 0
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECT | os.O_CLOEXEC)
        while offset < length:
            request = min(size, length - offset)
            result = libc.pread(fd, pointer, request, offset)
            if result < 0:
                error = C.get_errno()
                raise OSError(error, f'O_DIRECT pread at byte{offset}: {os.strerror(error)}')
            if result != request:
                raise OSError(f'Short O_DIRECT read at byte{offset}: {result}/{request}')
            data = (C.c_ubyte * result).from_address(pointer.value)
            digest.update(memoryview(data).cast('B'))
            offset += result
            if progress:
                progress(offset)
        return offset, digest.hexdigest()
    finally:
        if fd is not None:
            os.close(fd)
        libc.free(pointer)


if __name__ == '__main__':
    import json
    if len(sys.argv) != 3:
        raise SystemExit('Usage: aligned-readback.py PATH BYTE_COUNT')
    try:
        count, digest = direct_hash(sys.argv[1], int(sys.argv[2]))
        print(json.dumps({'bytes': count, 'sha256': digest, 'mode': 'aligned_pread_O_DIRECT'}))
    except Exception as error:
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        raise SystemExit(1)
