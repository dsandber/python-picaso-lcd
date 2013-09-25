# -*- coding: utf-8 -*-
from __future__ import print_function, division, absolute_import, unicode_literals

import serial
from . import utils
from .constants import ACK
from .exceptions import PicasoException


# TODO introduce logging

class Display(object):
    """This class represents a 4D Systems serial LCD."""

    def __init__(self, port, baudrate=9600):
        """
        Initialize an instance of the LCD.

        :param port: serial port to which the display is connected
        :type port: str or unicode
        :param baudrate: default 9600 in SPE2 rev 1.1
        :type baudrate: int
        :rtype: Display instance
        """
        self._ser = serial.Serial(port, baudrate=baudrate, stopbits=1)
        self._contrast = 15

        # Initialize subsystems
        self.text = DisplayText(self)

    ### Serial communication handling ###

    def write_cmd(self, cmd):
        """
        Write list of words to the serial port.

        Values are always converted into a word (16bit value, consisting of two
        bytes: high byte, low byte) even if they would fit into a single byte.

        The communication protocol is based on exchanging words. Only a few
        special commands use single byte values, in this case use write_raw_cmd
        instead.

        :param cmd: The list of command words (16 bit) to send.
        :type cmd: list of int

        """
        for c in cmd:
            high_byte, low_byte = utils.int_to_dword(c)
            self._ser.write(chr(high_byte))
            self._ser.write(chr(low_byte))

    def write_raw_cmd(self, cmd):
        """
        Write list of bytes directly to the serial port.

        :param cmd: List containing numeric bytes.
        :type cmd: list of int

        """
        for c in cmd:
            self._ser.write(chr(c))

    def _get_ack(self, return_bytes=0):
        """
        Wait for the ACK byte. If applicable, fetch and return the response
        values.

        TODO: Shouldn't this automatically be called from ``write_cmd``?

        :param return_bytes: Number of return bytes. Default 0.
        :type return_bytes: int
        :returns: List of response bytes if there are any, else None.
        :rtype: list or none

        """
        # First return value must be an ACK byte (0x06).
        ack = self._ser.read()
        if ord(ack) != ACK:
            msg = 'Instead of an ACK byte, "{!r}" was returned.'.format(ord(ack))
            print(msg)
            raise PicasoException(msg)

        # If applicable, fetch response values
        values = [] if return_bytes else None
        for i in xrange(return_bytes):
            val = ord(self._ser.read())
            print('Return byte: {0}'.format(val))
            values.append(val)

        return values

    def gfx_rect(self, x1, y1, x2, y2, color, filled=False):
        cmd = 0xffc5
        if filled:
            cmd = 0xffc4
        self.write_cmd([cmd, x1, y1, x2, y2, color])
        return self._get_ack()

    def gfx_triangle(self, vertices, filled=False):
        self.gfx_polyline(vertices, closed=True, filled=filled)

    def gfx_polyline(self, lines, color, closed=False, filled=False):
        """
        A polyline could be closed or filled, where filled is always closed.
        """
        cmd = 0x0015
        if closed:
            cmd = 0x0013
        if filled:
            cmd = 0x0014
        size = len(lines)
        print(size)
        cmd_list = [cmd, size]
        for point in lines:
            x, y = point
            cmd_list.append(x)
        for point in lines:
            x, y = point
            cmd_list.append(y)
        cmd_list.append(color)
        self.write_cmd(cmd_list)
        self._get_ack()

    def gfx_circle(self, x, y, rad, color, filled=False):
        self.gfx_ellipse(x, y, rad, rad, color, filled=filled)

    def gfx_ellipse(self, x, y, xrad, yrad, color, filled=False):
        cmd = 0xffb2
        if filled:
            cmd = 0xffb1
        self.write_cmd([cmd, x, y, xrad, yrad, color])
        self._get_ack()

    def gfx_line(self, x1, y1, x2, y2, color):
        self.write_cmd([0xffc8, x1, y1, x2, y2, color])
        self._get_ack()

    def cls(self):
        self.write_cmd([0xffcd])
        self._get_ack()

    def set_pixel(self, x, y, color):
        """Set the color of the pixel at ``x``/``y`` to ``color``."""
        self.write_cmd([0xffc1, x, y, color])
        self._get_ack()

    def set_font_size(self, size):
        self.write_cmd([0xffe4, size])
        self._get_ack(2)
        self.write_cmd([0xffe3, size])
        self._get_ack(2)

    def set_font(self, font):
        """
        :param font:
        0 - Font1 -> System Font
        1 - Font2
        3 - Font3 -> Default Font
        """
        self.write_cmd([0xffe5, font])
        self._get_ack(2)

    def set_text_color(self, color):
        self.write_cmd([0xffe7, color])
        return self._get_ack(2)

    def set_background_color(self, color):
        self.write_cmd([0xffa4, color])
        self._get_ack(2)

    def set_contrast(self, contrast):
        """Set the contrast. Note that this has no effect on most LCDs."""
        self.write_cmd([0xff9c, contrast])
        val = self._get_ack(2)
        print('turning off, contrast was: {0}'.format(val))
        dword = map(ord, val)
        self._contrast = utils.dword_to_int(*dword)

    def off(self):
        self.set_contrast(0)

    def on(self):
        print('contrast is: {0}'.format(self._contrast))
        self.set_contrast(self._contrast)

    def set_orientation(self, value):
        """Set display orientation
        0 = Landscape
        1 = Landscape reverse
        2 = portrait
        3 = portrait reverse

        :returns: previous orientation
        """
        self.write_cmd([0xff9e, value])
        return self._get_ack(2)[0]

    def get_display_size(self):
        self.write_cmd([0xffa6, 0])
        x = self._get_ack(2)
        x_dword = map(ord, [x[0], x[1]])
        self.write_cmd([0xffa6, 1])
        y = self._get_ack(2)
        y_dword = map(ord, [y[0], y[1]])
        return utils.dword_to_int(*x_dword), utils.dword_to_int(*y_dword)


class DisplayText(object):
    """Text/String related functions."""

    def __init__(self, display):
        """
        :param display: The display instance.
        :type display: Display
        """
        self.d = display

    def move_cursor(self, line, column):
        """
        Move cursor to specified position.

        The *Move Cursor* command moves the text cursor to a screen position
        set by line and column parameters. The line and column position is
        calculated, based on the size and scaling factor for the currently
        selected font. When text is outputted to screen it will be displayed
        from this position. The text position could also be set with *Move
        Origin* command if required to set the text position to an exact pixel
        location. Note that lines and columns start from 0, so line 0, column 0
        is the top left corner of the display.

        :param line: Line number (0..n)
        :type line: int
        :param column: Column number (0..n)
        :type column: int

        """
        self.d.write_cmd([0xffe9, line, column])
        self.d._get_ack()

    def put_character(self, char):
        """
        Write a single character to the display.

        The *Put Character* command prints a single character to the display.

        :param char: The character to print. Must be a printable ASCII character.
        :type char: str

        """
        self.d.write_cmd([0xfffe, ord(char)])
        self.d._get_ack()

    def put_string(self, string):
        """
        Write a string to the display.

        The *Put String* command prints a string to the display. Maximum string
        length is 511 chars.

        """
        # Validate input
        if len(string) > 511:
            raise ValueError('Max string length is 511 chars')

        # Build and send command
        cmd = [0x00, 0x18]
        for char in string:
            cmd.append(ord(char))
        cmd.append(0x00)
        self.d.write_raw_cmd(cmd)

        # Verify return values
        length_written = utils.dword_to_int(*self.d._get_ack(2))
        assert length_written == len(string), \
                'Length of string does not match length of original string'
