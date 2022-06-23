import asyncio
import functools
import logging
import re
import serial
from functools import wraps
from serial_asyncio import create_serial_connection
from threading import RLock

_LOGGER = logging.getLogger(__name__)
ZONE_PATTERN_OFF = re.compile('#Z0(\d)PWROFF')
ZONE_PATTERN_ON = re.compile('#Z0(\d)PWRON,SRC(\d),GRP(\d),VOL-(\w\w),POFF')

EOL = b'\r'
LEN_EOL = len(EOL)
TIMEOUT = 2  # Number of seconds before serial operation timeout

TREBLE_DEFAULT = 7
BASS_DEFAULT = 7
BALANCE_DEFAULT = 32
MAX_VOLUME = 78

class ZoneStatus(object):

    def __init__(self,
            zone: int,
            volume: int,   # 0 - 100
            power: bool,
            mute: bool,
            source: int,   # 1 - 6
        ):

        self.zone = zone
        self.volume = volume
        self.power = bool(power)
        self.mute = bool(mute)
        self.source = source

        # These aren't passed in the Zone Status response, lets worry about them later
        # self.treble = treble
        # self.bass = bass
        # self.balance = balance
        # self.treble = TREBLE_DEFAULT
        # self.bass = BASS_DEFAULT
        # self.balance = BALANCE_DEFAULT

    @classmethod
    def from_string(cls, string: str):

        if not string:
            return None

        # Is the zone turned off?
        match = re.search(ZONE_PATTERN_OFF, string)
        if match:
            groups = match.groups()
            zone = int(groups[0])
            volume = 0
            mute = False
            power = False
            source = 1
            return ZoneStatus(zone, volume, power, mute, source)
        else:  # Is the zone on?
            match = re.search(ZONE_PATTERN_ON, string)
            if match:
                groups = match.groups()
                zone = int(groups[0])
                source = int(groups[1])
                volume = groups[3]
                if volume == "MT" or volume == "XM":
                    volume = 0
                    mute = True
                    power = True
                    return ZoneStatus(zone, volume, power, mute, source)
                else:
                    volume = int(groups[3]) / MAX_VOLUME * 100
                    mute = False
                    power = True
                    return ZoneStatus(zone, volume, power, mute, source)

            else:
                return None

class BreatheAudio(object):
    """
    BreatheAudio amplifier interface
    """

    def zone_status(self, zone: int):
        """
        Get the structure representing the status of the zone
        :param zone: zone 1..6
        :return: status of the zone or None
        """
        raise NotImplemented()

    def set_power(self, zone: int, power: bool):
        """
        Turn zone on or off
        :param zone: zone 1..6
        :param power: True to turn on, False to turn off
        """
        raise NotImplemented()

    def set_mute(self, zone: int, mute: bool):
        """
        Mute zone on or off
        :param zone: zone 1..6
        :param mute: True to mute, False to unmute
        """
        raise NotImplemented()

    def set_volume(self, zone: int, volume: int):
        """
        Set volume for zone
        :param zone: zone 1..6
        :param volume: integer from 0 to 100 inclusive
        """
        raise NotImplemented()

    #def set_treble(self, zone: int, treble: int):
    #    """
    #    Set treble for zone
    #    :param zone: zone 1..6
    #    :param treble: integer from 0 to 14 inclusive, where 0 is -7 treble and 14 is +7
    #    """
    #    raise NotImplemented()

    #def set_bass(self, zone: int, bass: int):
    #    """
    #    Set bass for zone
    #    :param zone: zone 1..6
    #    :param bass: integer from 0 to 14 inclusive, where 0 is -7 bass and 14 is +7
    #    """
    #    raise NotImplemented()

    #def set_balance(self, zone: int, balance: int):
    #    """
    #    Set balance for zone
    #    :param zone: zone 1..6
    #    :param balance: integer from 0 to 20 inclusive, where 0 is -10(left), 0 is center and 20 is +10 (right)
    #    """
    #    raise NotImplemented()

    def set_source(self, zone: int, source: int):
        """
        Set source for zone
        :param zone: zone 1..6
        :param source: integer from 0 to 6 inclusive
        """
        raise NotImplemented()

    def restore_zone(self, status: ZoneStatus):
        """
        Restores zone to it's previous state
        :param status: zone state to restore
        """
        raise NotImplemented()


# Helpers

def _format_zone_status_request(zone: int) -> bytes:
    return '*Z0{}CONSR\r'.format(zone).encode()


def _format_set_power(zone: int, power: bool) -> bytes:
    return '*Z0{}{}\r'.format(zone, 'ON' if power else 'OFF').encode()


def _format_set_mute(zone: int, mute: bool) -> bytes:
    return '*Z0{}{}\r'.format(zone, 'MTON' if mute else 'MTOFF').encode()


def _format_set_volume(zone: int, volume: int) -> bytes:
    volume_percentage = volume / 100
    volume = int(max(0, min(MAX_VOLUME * volume_percentage, MAX_VOLUME)))
    return '*Z0{}VOL{:02}\r'.format(zone, volume).encode()

""" No clue how to implement these yet """
#def _format_set_treble(zone: int, treble: int) -> bytes:
#    treble = int(max(0, min(treble, 14)))
#    return '!{}TR{:02}+'.format(zone, treble).encode()


#def _format_set_bass(zone: int, bass: int) -> bytes:
#    bass = int(max(0, min(bass, 14)))
#    return '!{}BS{:02}+'.format(zone, bass).encode()


#def _format_set_balance(zone: int, balance: int) -> bytes:
#    balance = max(0, min(balance, 63))
#    return '!{}BA{:02}+'.format(zone, balance).encode()


def _format_set_source(zone: int, source: int) -> bytes:
    source = int(max(0, min(source, 6)))
    return '*Z0{}SRC{}\r'.format(zone, source).encode()


def get_breatheaudio(port_url):
    """
    Return synchronous version of BreatheAudio interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :return: synchronous implementation of BreatheAudio interface
    """

    lock = RLock()

    def synchronized(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                return func(*args, **kwargs)
        return wrapper

    class BreatheAudioSync(BreatheAudio):
        def __init__(self, port_url):
            self._port = serial.serial_for_url(port_url, do_not_open=True)
            self._port.baudrate = 9600
            self._port.stopbits = serial.STOPBITS_ONE
            self._port.bytesize = serial.EIGHTBITS
            self._port.parity = serial.PARITY_NONE
            self._port.timeout = TIMEOUT
            self._port.write_timeout = TIMEOUT
            self._port.open()

        def _process_request(self, request: bytes, skip=0):
            """
            :param request: request that is sent to the breatheaudio
            :param skip: number of bytes to skip for end of transmission decoding
            :return: ascii string returned by breatheaudio
            """
            _LOGGER.debug('Sending %s', request)
            # clear
            self._port.reset_output_buffer()
            self._port.reset_input_buffer()
            # send
            self._port.write(request)
            self._port.flush()
            # receive
            result = bytearray()
            while True:
                c = self._port.read(1)
                if not c:
                    raise serial.SerialTimeoutException(
                        'Connection timed out! Last received bytes {}'.format([hex(a) for a in result]))
                result += c
                if len(result) > skip and result[-LEN_EOL:] == EOL:
                    break
            ret = bytes(result)
            _LOGGER.debug('Received: %s', ret.decode('ascii'))
            return ret.decode('ascii')

        @synchronized
        def zone_status(self, zone: int):
            return ZoneStatus.from_string(self._process_request(_format_zone_status_request(zone), skip=LEN_EOL))

        @synchronized
        def set_power(self, zone: int, power: bool):
            self._process_request(_format_set_power(zone, power))

        @synchronized
        def set_mute(self, zone: int, mute: bool):
            self._process_request(_format_set_mute(zone, mute))

        @synchronized
        def set_volume(self, zone: int, volume: int):
            self._process_request(_format_set_volume(zone, volume))

        @synchronized
        def set_treble(self, zone: int, treble: int):
            self._process_request(_format_set_treble(zone, treble))

        @synchronized
        def set_bass(self, zone: int, bass: int):
            self._process_request(_format_set_bass(zone, bass))

        @synchronized
        def set_balance(self, zone: int, balance: int):
            self._process_request(_format_set_balance(zone, balance))

        @synchronized
        def set_source(self, zone: int, source: int):
            self._process_request(_format_set_source(zone, source))

        @synchronized
        def restore_zone(self, status: ZoneStatus):
            self.set_power(status.zone, status.power)
            self.set_mute(status.zone, status.mute)
            self.set_volume(status.zone, status.volume)
            self.set_treble(status.zone, status.treble)
            self.set_bass(status.zone, status.bass)
            self.set_balance(status.zone, status.balance)
            self.set_source(status.zone, status.source)

    return BreatheAudioSync(port_url)


@asyncio.coroutine
def get_async_breatheaudio(port_url, loop):
    """
    Return asynchronous version of BreatheAudio interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :return: asynchronous implementation of BreatheAudio interface
    """

    lock = asyncio.Lock()

    def locked_coro(coro):
        @asyncio.coroutine
        @wraps(coro)
        def wrapper(*args, **kwargs):
            with (yield from lock):
                return (yield from coro(*args, **kwargs))
        return wrapper

    class BreatheAudioAsync(BreatheAudio):
        def __init__(self, breatheaudio_protocol):
            self._protocol = breatheaudio_protocol

        @locked_coro
        @asyncio.coroutine
        def zone_status(self, zone: int):
            string = yield from self._protocol.send(_format_zone_status_request(zone))
            return ZoneStatus.from_string(string)

        @locked_coro
        @asyncio.coroutine
        def set_power(self, zone: int, power: bool):
            yield from self._protocol.send(_format_set_power(zone, power))

        @locked_coro
        @asyncio.coroutine
        def set_mute(self, zone: int, mute: bool):
            yield from self._protocol.send(_format_set_mute(zone, mute))

        @locked_coro
        @asyncio.coroutine
        def set_volume(self, zone: int, volume: int):
            yield from self._protocol.send(_format_set_volume(zone, volume))

        @locked_coro
        @asyncio.coroutine
        def set_treble(self, zone: int, treble: int):
            yield from self._protocol.send(_format_set_treble(zone, treble))

        @locked_coro
        @asyncio.coroutine
        def set_bass(self, zone: int, bass: int):
            yield from self._protocol.send(_format_set_bass(zone, bass))

        @locked_coro
        @asyncio.coroutine
        def set_balance(self, zone: int, balance: int):
            yield from self._protocol.send(_format_set_balance(zone, balance))

        @locked_coro
        @asyncio.coroutine
        def set_source(self, zone: int, source: int):
            yield from self._protocol.send(_format_set_source(zone, source))

        @locked_coro
        @asyncio.coroutine
        def restore_zone(self, status: ZoneStatus):
            yield from self._protocol.send(_format_set_power(status.zone, status.power))
            yield from self._protocol.send(_format_set_mute(status.zone, status.mute))
            yield from self._protocol.send(_format_set_volume(status.zone, status.volume))
            yield from self._protocol.send(_format_set_treble(status.zone, status.treble))
            yield from self._protocol.send(_format_set_bass(status.zone, status.bass))
            yield from self._protocol.send(_format_set_balance(status.zone, status.balance))
            yield from self._protocol.send(_format_set_source(status.zone, status.source))

    class BreatheAudioProtocol(asyncio.Protocol):
        def __init__(self, loop):
            super().__init__()
            self._loop = loop
            self._lock = asyncio.Lock()
            self._transport = None
            self._connected = asyncio.Event(loop=loop)
            self.q = asyncio.Queue(loop=loop)

        def connection_made(self, transport):
            self._transport = transport
            self._connected.set()
            _LOGGER.debug('port opened %s', self._transport)

        def data_received(self, data):
            asyncio.ensure_future(self.q.put(data), loop=self._loop)

        @asyncio.coroutine
        def send(self, request: bytes, skip=0):
            yield from self._connected.wait()
            result = bytearray()
            # Only one transaction at a time
            with (yield from self._lock):
                self._transport.serial.reset_output_buffer()
                self._transport.serial.reset_input_buffer()
                while not self.q.empty():
                    self.q.get_nowait()
                self._transport.write(request)
                try:
                    while True:
                        result += yield from asyncio.wait_for(self.q.get(), TIMEOUT, loop=self._loop)
                        if len(result) > skip and result[-LEN_EOL:] == EOL:
                            ret = bytes(result)
                            _LOGGER.debug('Received "%s"', ret.decode('ascii'))
                            return ret.decode('ascii')
                except asyncio.TimeoutError:
                    _LOGGER.error("Timeout during receiving response for command '%s', received='%s'", request, result)
                    raise

    _, protocol = yield from create_serial_connection(loop, functools.partial(BreatheAudioProtocol, loop),port_url, baudrate=9600)
    return BreatheAudioAsync(protocol)
