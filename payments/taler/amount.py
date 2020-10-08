#  This file is part of TALER
#  (C) 2017 Taler Systems SA
#
#  This library is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 2.1 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
#  @author Marcello Stanisci
#  @version 0.0
#  @repository https://git.taler.net/copylib.git/
#  This code is "copylib", it is versioned under the Git repository
#  mentioned above, and it is meant to be manually copied into any project
#  which might need it.

class BadAmount(Exception):
    def __init__(self, faulty_str):
        self.faulty_str = faulty_str

class Amount:
    # How many "fraction" units make one "value" unit of currency
    # (Taler requires 10^8).  Do not change this 'constant'.
    @staticmethod
    def FRACTION():
        return 10 ** 8

    @staticmethod
    def MAX_VALUE():
        return (2 ** 53) - 1

    def __init__(self, currency, value=0, fraction=0):
        # type: (str, int, int) -> Amount
        assert(value >= 0 and fraction >= 0)
        self.value = value
        self.fraction = fraction
        self.currency = currency
        self.__normalize()
        assert(self.value <= Amount.MAX_VALUE())

    # Normalize amount
    def __normalize(self):
        if self.fraction >= Amount.FRACTION():
            self.value += int(self.fraction / Amount.FRACTION())
            self.fraction = self.fraction % Amount.FRACTION()

    # Parse a string matching the format "A:B.C"
    # instantiating an amount object.
    @classmethod
    def parse(cls, amount_str):
        exp = '^\s*([-_*A-Za-z0-9]+):([0-9]+)\.([0-9]+)\s*$'
        import re
        parsed = re.search(exp, amount_str)
        if not parsed:
            raise BadAmount(amount_str)
        value = int(parsed.group(2))
        fraction = 0
        for i, digit in enumerate(parsed.group(3)):
            fraction += int(int(digit) * (Amount.FRACTION() / 10 ** (i+1)))
        return cls(parsed.group(1), value, fraction)

    # Comare two amounts, return:
    # -1 if a < b
    # 0 if a == b
    # 1 if a > b
    @staticmethod
    def cmp(a, b):
        assert a.currency == b.currency
        if a.value == b.value:
            if a.fraction < b.fraction:
                return -1
            if a.fraction > b.fraction:
                return 1
            return 0
        if a.value < b.value:
            return -1
        return 1

    # Add the given amount to this one
    def add(self, a):
        assert self.currency == a.currency
        self.value += a.value
        self.fraction += a.fraction
        self.__normalize()

    # Subtract passed amount from this one
    def subtract(self, a):
        assert self.currency == a.currency
        if self.fraction < a.fraction:
            self.fraction += Amount.FRACTION()
            self.value -= 1
        if self.value < a.value:
            raise ValueError('self is lesser than amount to be subtracted')
        self.value -= a.value
        self.fraction -= a.fraction

    # Dump string from this amount, will put 'ndigits' numbers
    # after the dot.
    def stringify(self, ndigits):
        assert ndigits > 0
        ret = '%s:%s.' % (self.currency, str(self.value))
        f = self.fraction
        for i in range(0, ndigits):
            ret += str(int(f / (Amount.FRACTION() / 10)))
            f = (f * 10) % (Amount.FRACTION())
        return ret

    # Dump the Taler-compliant 'dict' amount
    def dump(self):
        return dict(value=self.value,
                    fraction=self.fraction,
                    currency=self.currency)
