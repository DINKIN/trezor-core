from micropython import const
import ustruct
import ubinascii

# trezor wire protocol #2:
#
# # hid report (64B)
# - report marker (1B)
# - session id (4B, BE)
# - payload (59B)
#
# # message
# - streamed as payloads of hid reports
# - message type (4B, BE)
# - data length (4B, BE)
# - data (var-length)
# - data crc32 checksum (4B, BE)
#
# # sessions
# - reports are interleaved, need to be dispatched by session id

REP_MARKER_HEADER = const(72)  # ord('H')
REP_MARKER_DATA = const(68)  # ord('D')
REP_MARKER_OPEN = const(79)  # ord('O')
REP_MARKER_CLOSE = const(67)  # ord('C')

_REP_HEADER = '>BL'  # marker, session id
_MSG_HEADER = '>LL'  # msg type, data length
_MSG_FOOTER = '>L'  # data checksum

_REP_LEN = const(64)
_REP_HEADER_LEN = ustruct.calcsize(_REP_HEADER)
_MSG_HEADER_LEN = ustruct.calcsize(_MSG_HEADER)
_MSG_FOOTER_LEN = ustruct.calcsize(_MSG_FOOTER)


def parse_report(data):
    if len(data) != _REP_LEN:
        raise ValueError('Invalid buffer size')
    marker, session_id = ustruct.unpack(_REP_HEADER, data)
    return marker, session_id, data[_REP_HEADER_LEN:]


def parse_message(data):
    if len(data) != _REP_LEN - _REP_HEADER_LEN:
        raise ValueError('Invalid buffer size')
    msg_type, data_len = ustruct.unpack(_MSG_HEADER, data)
    return msg_type, data_len, data[_MSG_HEADER_LEN:]


def parse_message_footer(data):
    if len(data) != _MSG_FOOTER_LEN:
        raise ValueError('Invalid buffer size')
    data_checksum, = ustruct.unpack(_MSG_FOOTER, data)
    return data_checksum,


def serialize_report_header(data, marker, session_id):
    if len(data) < _REP_HEADER_LEN:
        raise ValueError('Invalid buffer size')
    ustruct.pack_into(_REP_HEADER, data, 0, marker, session_id)


def serialize_message_header(data, msg_type, msg_len):
    if len(data) < _REP_HEADER_LEN + _MSG_HEADER_LEN:
        raise ValueError('Invalid buffer size')
    ustruct.pack_into(_MSG_HEADER, data, _REP_HEADER_LEN, msg_type, msg_len)


def serialize_message_footer(data, checksum):
    if len(data) < _MSG_FOOTER_LEN:
        raise ValueError('Invalid buffer size')
    ustruct.pack_into(_MSG_FOOTER, data, 0, checksum)


def serialize_opened_session(data, session_id):
    serialize_report_header(data, REP_MARKER_OPEN, session_id)


class MessageChecksumError(Exception):
    pass


def decode_stream(session_id, callback, *args):
    '''Decode a wire message from the report data and stream it to target.

Receives report payloads.  After first report, creates target by calling
`callback(session_id, msg_type, data_len, *args)` and sends chunks of message
data.
Throws `EOFError` to target after last data chunk, in case of valid checksum.
Throws `MessageChecksumError` to target if data doesn't match the checksum.

Pass report payloads as `memoryview` for cheaper slicing.
'''
    message = yield  # read first report
    msg_type, data_len, data_tail = parse_message(message)

    target = callback(session_id, msg_type, data_len, *args)
    target.send(None)

    checksum = 0  # crc32

    while data_len > 0:

        data_chunk = data_tail[:data_len]  # slice off the garbage at the end
        data_tail = data_tail[len(data_chunk):]  # slice off what we have read
        data_len -= len(data_chunk)
        target.send(data_chunk)

        checksum = ubinascii.crc32(data_chunk, checksum)

        if data_len > 0:
            data_tail = yield  # read next report

    msg_footer = data_tail[:_MSG_FOOTER_LEN]
    if len(msg_footer) < _MSG_FOOTER_LEN:
        data_tail = yield  # read report with the rest of checksum
        footer_tail = data_tail[:_MSG_FOOTER_LEN - len(msg_footer)]
        msg_footer = bytearray(msg_footer)
        msg_footer.extend(footer_tail)

    data_checksum, = parse_message_footer(msg_footer)
    if data_checksum != checksum:
        target.throw(MessageChecksumError((checksum, data_checksum)))
    else:
        target.throw(EOFError())


def encode(session_id, msg_type, msg_data, callback):
    '''Encode a full wire message directly to reports and stream it to callback.

Callback receives `memoryview`s of HID reports which are valid until the
callback returns.
    '''
    report = memoryview(bytearray(_REP_LEN))
    serialize_report_header(report, REP_MARKER_HEADER, session_id)
    serialize_message_header(report, msg_type, len(msg_data))

    source_data = memoryview(msg_data)
    target_data = report[_REP_HEADER_LEN + _MSG_HEADER_LEN:]

    checksum = ubinascii.crc32(msg_data)

    msg_footer = bytearray(_MSG_FOOTER_LEN)
    serialize_message_footer(msg_footer, checksum)

    first = True

    while True:
        # move as much as possible from source to target
        n = min(len(target_data), len(source_data))
        target_data[:n] = source_data[:n]
        source_data = source_data[n:]
        target_data = target_data[n:]

        # continue with the footer if source is empty and we have space
        if not source_data and target_data and msg_footer:
            source_data = msg_footer
            msg_footer = None
            continue

        # fill the rest of the report with 0x00
        x = 0
        to_fill = len(target_data)
        while x < to_fill:
            target_data[x] = 0
            x += 1

        callback(report)

        if not source_data and not msg_footer:
            break

        # reset to skip the magic and session ID
        if first:
            serialize_report_header(report, REP_MARKER_DATA, session_id)
            first = False
        target_data = report[_REP_HEADER_LEN:]


def encode_session_open(session_id, callback):
    report = bytearray(_REP_LEN)
    serialize_report_header(report, REP_MARKER_OPEN, session_id)
    callback(report)


def encode_session_close(session_id, callback):
    report = bytearray(_REP_LEN)
    serialize_report_header(report, REP_MARKER_CLOSE, session_id)
    callback(report)
